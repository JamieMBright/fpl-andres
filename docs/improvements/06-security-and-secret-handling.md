# 6. Security and secret handling — work orders

Detailed briefs for items 70–82 of the [improvement audit](../../IMPROVEMENTS.md).
Each brief is self-contained: a sub-agent should be able to implement one item
from its brief alone.

Every brief obeys the repository rules: test-first, never default a missing
controlling FPL rule, never expose a Supabase secret, Resend key or subscriber
email to browser code or logs, apply only tracked migrations that pass local
policy tests and Linux CI (never iterate directly on the production project),
and keep manual team-state overrides separate from public last-deadline state.

---

## 70 — Remove internal failure detail from the `x-fpl-andres-debug` response header (Impact: H)

**Files**: `api/fpl/[...path].ts` (`fplProxyHandler` catch block, lines 22–35),
`api/team/[id].ts` (`teamPublicStateHandler` catch block, lines 24–38)

**Problem**: Both handlers set an `x-fpl-andres-debug` response header containing
the first 300 characters of the thrown `Error.message` when the handler crashes
unexpectedly (lines 26–29 and 29–31 respectively). This header is forwarded to
every client that receives a 502 or 503 response. Internal exception messages may
include stack-frame paths, third-party upstream hostnames, or partial payloads
that an attacker could use to fingerprint the server configuration. The trust
boundary crossed is the serverless function → public internet edge: internal
diagnostic detail belongs in server logs, not in response headers.

**Change**:

1. In both catch blocks, generate a short opaque `requestId` with
   `crypto.randomUUID()` (available in Node ≥ 19 / Vercel runtime).
2. Log the full error to `console.error` keyed by `requestId`:
   `console.error("fplProxyHandler crash", { requestId, error })`.
3. Replace the `x-fpl-andres-debug` header with `x-fpl-andres-request-id`
   carrying only the `requestId`, so an operator can correlate a client-reported
   ID to the server log without exposing the detail publicly.
4. Remove `x-fpl-andres-debug` from both handlers entirely.

**Constraints**: The `console.error` call that currently logs the full error (lines
23 and 26) must be retained; structured logging with `requestId` is additive. The
`x-fpl-andres-request-id` header must appear on the 502/503 response only, not
on successful proxy responses. Do not touch `api/_lib/fpl-proxy.ts` or
`api/_lib/team-public-state-response.ts`. No migration needed.

**Tests first**: Add tests in the relevant test file (or create
`api/tests/fpl-path-handler.test.ts` if one does not exist) that:

- Assert the 502 response carries `x-fpl-andres-request-id` that is a valid UUID.
- Assert the 502 response does **not** carry `x-fpl-andres-debug`.
- Assert the UUID in the header also appears in a `console.error` call (spy on
  `console.error`).

**Done when**:

1. A client receiving a 502 or 503 sees `x-fpl-andres-request-id: <uuid>` but no
   `x-fpl-andres-debug` header.
2. Server logs contain the full error keyed by the same UUID.
3. `corepack pnpm typecheck` exits 0.

**Validate**: `corepack pnpm typecheck` then
`corepack pnpm --filter @fpl-andres/web test` (or the API test suite if one exists)

---

## 71 — Redact user-supplied metadata before it is persisted to `workflow_runs` (Impact: H)

**Files**: `python/fpl_andres/persistence/workflow.py` (`open_run`, lines 105–118;
`WorkflowRunRecorder.__enter__`, lines 45–67), `python/tests/test_persistence.py`

**Problem**: `open_run()` (lines 105–118) constructs a `WorkflowRun` with
`metadata=dict(parts)` (line 116) and passes it unchanged into
`WorkflowRunRecorder.__enter__`, which persists it to the `workflow_runs.metadata`
column (line 57). The `parts` dict is caller-controlled: nothing prevents a caller
from including a key whose value is a credential or a subscriber email. Example:
`open_run(client, workflow_name="live-contracts", parts={"SUPABASE_SECRET_KEY": "sk_live_..."}, ...)`.
The metadata column is a JSONB field with no encryption. The threat is inadvertent
credential commit to an application table that is queryable by anyone with
service-role access, and potentially surfaced in admin dashboards.

**Change**:

1. Define a module-level `_SENSITIVE_KEY_PATTERNS: tuple[re.Pattern[str], ...]`
   in `workflow.py` matching common secret key names
   (e.g., `r"(?i)(secret|key|token|password|api.?key|auth)`).
2. Add a `_redact_metadata(parts: Mapping[str, Any]) -> dict[str, Any]` function
   that returns a copy of `parts` with any matching value replaced by
   `"<redacted>"`.
3. Apply `_redact_metadata` in `open_run()` before assigning `metadata=` (line 116) and in `WorkflowRunRecorder.__exit__` before closing metadata (line 80).

**Constraints**: The redaction must be applied to values, not keys. Key names must
remain visible so operators can see which parameter triggered the redaction. Do not
redact values whose key does not match a sensitive pattern — normal workflow
parameters such as `season`, `gameweek`, and `source` must pass through unchanged.
No migration needed.

**Tests first**: In `python/tests/test_persistence.py`, add:

- `test_metadata_containing_a_secret_key_name_is_redacted` — call `open_run` with
  `parts={"season": "2024-25", "api_key": "abc123"}`; intercept the POST body
  with `respx`; assert `metadata["api_key"] == "<redacted>"` and
  `metadata["season"] == "2024-25"`.
- `test_metadata_without_sensitive_keys_passes_through_unchanged` — assert
  `metadata["season"]` is not `"<redacted>"`.

**Done when**:

1. A `parts` dict containing a value keyed `"api_key"` persists as `"<redacted>"`
   in `workflow_runs.metadata`.
2. Non-sensitive keys are unchanged.
3. `python -m pytest python/tests/test_persistence.py -q` exits 0.

**Validate**: `python -m pytest python/tests/test_persistence.py -q`

---

## 72 — Add per-client rate limiting in front of `/api/fpl/*` and `/api/team/*` (Impact: H)

**Files**: `vercel.json` (root, lines 7–11), `api/fpl/[...path].ts`,
`api/team/[id].ts`, `api/_lib/fpl-proxy.ts`

**Problem**: Both `/api/fpl/*` and `/api/team/*` are unauthenticated serverless
functions acting as proxies to the FPL public API. They carry no per-client
request budget. A single abusive client can exhaust the Vercel function invocation
quota, trigger FPL's upstream rate limiter (which bans the Vercel egress IP), and
degrade service for all users. `vercel.json` sets a `maxDuration: 10` for all API
functions but provides no request-rate ceiling. The trust boundary crossed is
anonymous public internet → authenticated FPL upstream.

**Change**:

1. Add a `rateLimit` configuration block to `vercel.json` under
   `"functions": { "api/**/*.ts": { ..., "rateLimit": { "windowMs": 10000, "max": 30 } } }`
   if supported by the deployed Vercel plan; otherwise implement an in-process
   sliding-window counter using the `X-Forwarded-For` header as the key in a
   module-level `Map<string, number[]>` in a new `api/_lib/rate-limit.ts` module.
2. Return HTTP 429 with `Retry-After: 10` and `Cache-Control: no-store` when the
   limit is exceeded.
3. Apply the rate limiter as the first check in both `fplProxyHandler` and
   `teamPublicStateHandler`, before any upstream fetch.

**Constraints**: Vercel's platform-level rate limiting (if available) is preferred
because it applies before the function is invoked and incurs no cost. If
implementing in-process, document that the counter resets across cold starts
(it is best-effort, not hard). The `api/health.ts` endpoint must not be rate
limited. Do not alter `api/_lib/fpl-proxy.ts` business logic.

**Tests first**: If implementing in-process, in a new test file for the rate-limit
module, add:

- `test_rate_limit_passes_first_n_requests` — assert requests within the window
  return `null` (allowed).
- `test_rate_limit_rejects_request_over_the_window` — assert the (n+1)th request
  returns a 429 `Response`.
- `test_rate_limit_resets_after_window_expires` — advance a mock `now` clock
  past the window; assert the next request is allowed.

**Done when**:

1. A client making more than 30 requests in a 10-second window receives HTTP 429
   with `Retry-After: 10`.
2. Normal single-request usage is unaffected.
3. `corepack pnpm typecheck` exits 0.

**Validate**: `corepack pnpm typecheck`

---

## 73 — Assert the Supabase secret never appears in `SupabaseRestClient` repr or exception context (Impact: H)

> **Audit correction**: The audit cites line 85 and mentions "relying on a masked
> literal". Inspection shows `SupabaseCredentials.__repr__` (lines 64–65) already
> redacts the secret as `<redacted>`, and
> `test_credentials_never_expose_the_secret_in_a_repr` (test_persistence.py:50–56)
> already asserts this. The existing test covers only `SupabaseCredentials`. The
> real gap is that `SupabaseRestClient` stores `self._credentials` (line 78) and
> `self._client` (an `httpx.Client` whose default `__repr__` may include its
> headers, which contain the Authorization bearer token). There is no regression
> test asserting that the secret is absent from `repr(client)`,
> `str(exception_with_client_in_context)`, or a formatted traceback.

**Files**: `python/fpl_andres/persistence/supabase.py` (`SupabaseRestClient.__init__`,
lines 71–89; `close`, lines 102–103), `python/tests/test_persistence.py`

**Problem**: The `httpx.Client` stored at `self._client` may include its request
headers in its `__repr__` or in the `str()` of an `httpx.RequestError`. Those
headers include `apikey: <secret>` and `Authorization: ****** (lines
84–85). If an `httpx.RequestError`propagates up with`**context**`or`**cause**`that includes the client, a logging handler printing`repr(exc)` could
leak the secret. Threat: server-side log aggregation or Sentry that captures
exception context exposes the service-role secret.

**Change**:

1. Add `__repr__` to `SupabaseRestClient` returning
   `f"SupabaseRestClient(url={self._credentials.url!r})"` (no secret, no client
   details).
2. Override `__str__` to return the same string.
3. Verify in the test that `str(SupabaseWriteError("...", client))` does not
   contain the secret, if `SupabaseWriteError` is ever constructed with the client
   as context.

**Constraints**: The bearer token must still be sent correctly in every HTTP
request — only the Python object repr must be sanitised. The existing
`test_credentials_never_expose_the_secret_in_a_repr` must continue to pass
unchanged. No migration needed.

**Tests first**: In `python/tests/test_persistence.py`, add:

- `test_client_repr_does_not_expose_the_secret` — construct a
  `SupabaseRestClient` with a known secret; assert `SECRET not in repr(client)`
  and `SECRET not in str(client)`.
- `test_write_error_caught_from_client_does_not_expose_the_secret_via_context` —
  catch a `SupabaseWriteError` from a mocked 500 response; assert
  `SECRET not in repr(error.__context__)` if a context is set.

**Done when**:

1. `repr(SupabaseRestClient(...))` does not contain the secret key.
2. `str(SupabaseRestClient(...))` does not contain the secret key.
3. `python -m pytest python/tests/test_persistence.py -q` exits 0.

**Validate**: `python -m pytest python/tests/test_persistence.py -q`

---

## 74 — URL-decode the proxy path before the allow-list check (Impact: M)

> **Audit correction**: The audit cites `api/_lib/fpl-path.ts ~line 66`.
> `rejectUnsafePath()` (lines 48–57) already rejects `%2e`, `%2f`, and `%5c`
> via the pattern `/%(?:2e|2f|5c)/i`. However, the `endpointPath` passed to
> `validateEndpointPath()` is the raw undecoded string, so a doubly-encoded
> sequence like `%252f` (which becomes `%2f` after one decode, then `/` after a
> second) is not caught. The allow-list regex patterns in `validateEndpointPath()`
> match only the raw string; an attacker who can cause two layers of URL decoding
> could potentially reach a path that looks like an allowed pattern after one
> decode but expands to something else after a second. The real gap is the absence
> of full URL-decode-then-recheck.

**Files**: `api/_lib/fpl-path.ts` (`rejectUnsafePath`, lines 48–57;
`resolveFplUpstreamUrl`, lines 30–46), `api/_lib/fpl-path.test.ts` (if it exists,
otherwise create it)

**Problem**: `rejectUnsafePath()` rejects one round of percent-encoding for `/`
(`%2f`) and `.` (`%2e`), but not double-encoded forms (`%252f`, `%252e`). When
Vercel or an intermediate proxy applies a second round of decoding, these pass
the guard and enter `validateEndpointPath()` as literal `/` or `.`, potentially
producing a match that targets an endpoint outside the intended allow-list pattern.
Trust boundary: public HTTP request → `new URL(endpointPath, FPL_API_ORIGIN)`.

**Change**:

1. After stripping the `PROXY_PREFIX` in `resolveFplUpstreamUrl()` (line 40),
   apply `decodeURIComponent(endpointPath)` and check whether the decoded form
   differs from the original; if it does, re-run `rejectUnsafePath` on the decoded
   form as well.
2. Extend `rejectUnsafePath()` to also reject any string that still contains `%`
   after the first decode (i.e., any double-encoded sequence).
3. Pass only the fully decoded and validated `endpointPath` to `validateEndpointPath()`.

**Constraints**: `decodeURIComponent` throws a `URIError` on malformed sequences
(e.g., lone `%`); catch and convert to `FplPathError`. Valid percent-encoded
characters that decode to safe unreserved characters (e.g., `%41` → `A`) must not
cause rejection; only sequences that decode to `/`, `.`, `\`, or a further `%`
must trigger the guard. No migration needed.

**Tests first**: In the path test file, add:

- `test_double_encoded_slash_is_rejected` — call `resolveFplUpstreamUrl("/api/fpl/entry%252F123%252F")`
  and assert `FplPathError` is thrown.
- `test_double_encoded_dot_is_rejected` — `%252e%252e` should throw `FplPathError`.
- `test_malformed_percent_sequence_is_rejected` — `%zz` should throw `FplPathError`.
- `test_valid_path_still_resolves` — `"/api/fpl/bootstrap-static/"` must still
  resolve correctly.

**Done when**:

1. Any doubly-encoded traversal sequence raises `FplPathError`.
2. A malformed `%` sequence raises `FplPathError`.
3. All existing path tests pass.
4. `corepack pnpm typecheck` exits 0.

**Validate**: `corepack pnpm typecheck` then
`corepack pnpm --filter @fpl-andres/web test` (or the API test suite)

---

## 75 — _(Premise already false)_ Content-type validation before upstream JSON parsing (Impact: M)

> **Audit correction**: The claim that content-type validation is missing is
> **false as of the current codebase**. `api/_lib/fpl-proxy.ts` lines 74–83
> already implement this check:
>
> ```
> const contentType = upstreamResponse.headers.get("Content-Type") ?? "";
> if (!contentType.toLowerCase().includes("application/json")) {
>   await upstreamResponse.body?.cancel();
>   return jsonError("FPL returned an unexpected response format.", 502, {}, "unexpected_format");
> }
> ```
>
> The upstream response is rejected with a 502 and `reason: "unexpected_format"`
> if the content-type does not include `application/json`. No code change is
> needed for this item. The only genuine gap is the absence of a test asserting
> this behaviour, which is described below.

**Files**: `api/_lib/fpl-proxy.ts` (`createFplProxyResponse`, lines 73–83)

**Residual gap**: There is no automated test verifying that a 200 response from
FPL with `Content-Type: text/html` is rejected as 502. Add one to prevent the
existing guard from being accidentally removed.

**Tests first**: In the proxy test file, add:

- `test_upstream_text_html_response_is_rejected_as_502_unexpected_format` — mock
  `fetchUpstream` to return a 200 with `Content-Type: text/html`; assert the
  proxy returns status 502 and `reason: "unexpected_format"`.
- `test_upstream_missing_content_type_is_rejected` — return a 200 with no
  `Content-Type` header; assert 502 `"unexpected_format"`.

**Done when**:

1. The tests pass, confirming the guard is present and tested.
2. No code in `fpl-proxy.ts` is modified (the guard already exists).

**Validate**: `corepack pnpm --filter @fpl-andres/web test` (or the API test suite)

---

## 76 — Harden `Cache-Control` for leagues-standings responses against shared-CDN leakage (Impact: M)

> **Audit correction**: The audit says entry-specific responses lack a `private`
> directive. Inspection of `cachePolicyFor()` in `api/_lib/fpl-proxy.ts`
> (lines 251–261) shows that `bootstrap-static` and `fixtures` return
> `public, s-maxage=…`, `element-summary` returns `public, s-maxage=…`, and
> **everything else** returns `private, no-store`. Entry paths
> (`/entry/…/`, `/entry/…/picks/`, `/entry/…/history/`) fall into the
> `private, no-store` branch. The primary concern stated in the audit is already
> addressed for entry-specific endpoints. The genuine residual gap is the
> `leagues-classic` standings endpoint: its path matches `return "private, no-store"`
> today, but standings pages are actually _public_ (anyone can read a public
> league table), and serving them as `private` prevents edge caching that would
> reduce latency and upstream API calls. Additionally, the 502 error path in
> `jsonError()` (line 275) correctly uses `"Cache-Control": "no-store"`, so the
> error path is safe.

**Files**: `api/_lib/fpl-proxy.ts` (`cachePolicyFor`, lines 251–261),
`api/_lib/fpl-path.ts` (`EndpointKind` type, line 7)

**Problem**: Standings pages (`leagues-classic/<id>/standings/`) are public
league tables and could be served from a shared CDN edge cache to reduce load on
the FPL upstream API. Currently they fall into the default `private, no-store`
branch and are never cached. Meanwhile, `element-summary` responses are served
as `public, s-maxage=300` — a player-level summary is no more sensitive than a
league standings page. The inconsistency means standings requests always hit
origin.

**Change**:

1. Add a new `EndpointKind` value `"standings-public"` to the `EndpointKind` type
   in `fpl-path.ts` (line 7).
2. Update `validateEndpointPath()` to return `"standings-public"` for
   `leagues-classic` paths (currently returns `"standings"`, line 87).
3. In `cachePolicyFor()`, add a branch:
   `if (pathname.includes("/leagues-classic/")) return "public, s-maxage=60, stale-while-revalidate=300";`
   before the catch-all `return "private, no-store"`.
4. Confirm `cachePolicyFor` for all entry-specific paths still returns
   `"private, no-store"` by adding explicit test coverage.

**Constraints**: Entry endpoints (`/entry/…/`, `/entry/…/picks/`) must remain
`private, no-store`. League standings are public by FPL's own design and carry no
manager-specific state. No migration needed.

**Tests first**: In the proxy/path test file, add:

- `test_standings_endpoint_gets_public_cache_policy` — assert
  `cachePolicyFor("/leagues-classic/123/standings/") === "public, s-maxage=60, stale-while-revalidate=300"`.
- `test_entry_picks_endpoint_gets_private_no_store` — assert
  `cachePolicyFor("/entry/123/event/38/picks/") === "private, no-store"`.
- `test_entry_endpoint_gets_private_no_store` — assert
  `cachePolicyFor("/entry/123/") === "private, no-store"`.

**Done when**:

1. Standings responses are served with `public, s-maxage=60`.
2. Entry and picks responses remain `private, no-store`.
3. `corepack pnpm typecheck` exits 0.

**Validate**: `corepack pnpm typecheck` then the proxy test suite

---

## 77 — Validate the Supabase environment mapping with a named configuration error at startup (Impact: M)

**Files**: `python/fpl_andres/persistence/supabase.py` (`SupabaseCredentials.from_env`,
lines 47–62), `python/tests/test_persistence.py`

**Problem**: `SupabaseCredentials.from_env()` (lines 47–62) accepts a
`Mapping[str, str]` but performs only presence and `startswith("https://")` checks.
It does not guard against non-string values (which would cause `AttributeError` on
`.strip()`) or transposed keys (e.g., a caller accidentally passing the URL value
under the secret key name, which would pass the non-empty check but fail the
`startswith("https://")` guard with a misleading message). A misconfigured
deployment then surfaces as an opaque `AttributeError` or a confusing
`MissingCredentialsError: SUPABASE_URL must be an https URL` rather than
a clear configuration error.

**Change**:

1. At the start of `from_env()`, iterate over `(_URL_ENV, _SECRET_ENV)` and assert
   each is present in `env` and `isinstance(env[key], str)`. If either value is
   not a `str`, raise `MissingCredentialsError` with the message:
   `"environment variable <name> must be a string, got <type>"`.
2. After stripping whitespace, validate that `secret_key` does not start with
   `"https://"` (which would indicate the URL and secret are transposed); raise
   `MissingCredentialsError("SUPABASE_SECRET_KEY looks like a URL; check variable assignment")`.
3. Extend the existing error message for a non-HTTPS URL to include a hint that
   the variables may be transposed.

**Constraints**: The type annotation `env: Mapping[str, str]` is correct at the
call sites; the runtime guard is a defence-in-depth measure for misconfigured
environment injection (e.g., a GitHub Actions secret passed to the wrong variable).
No migration needed.

**Tests first**: In `python/tests/test_persistence.py`, add:

- `test_from_env_raises_on_non_string_value` — pass
  `{"SUPABASE_URL": 12345, "SUPABASE_SECRET_KEY": "sk"}` and assert
  `MissingCredentialsError` mentioning `"string"`.
- `test_from_env_raises_on_transposed_url_in_secret_field` — pass
  `{"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SECRET_KEY": "https://x.supabase.co"}`
  and assert `MissingCredentialsError` mentioning `"transposed"` or `"URL"`.

**Done when**:

1. A non-string environment value raises `MissingCredentialsError` with a clear
   message identifying the variable name and the received type.
2. A transposed URL-in-secret raises `MissingCredentialsError` with a hint.
3. `python -m pytest python/tests/test_persistence.py -q` exits 0.

**Validate**: `python -m pytest python/tests/test_persistence.py -q`

---

## 78 — Add secret scanning as a CI gate (Impact: M)

**Files**: `.github/workflows/ci.yml`, `.gitignore` (root),
`.env.example` (root, documents live secret names)

**Problem**: `.env.example` documents several sensitive variable names
(`SUPABASE_SECRET_KEY`, `SUPABASE_URL`, etc.) that are used by the Python
ingest pipeline. There is no automated CI gate that scans commits for accidental
inclusion of real secrets. A developer who copies `.env` from `.env.example` and
then runs `git add -A` could commit live credentials. The dependency-review
workflow (`.github/workflows/dependency-review.yml`) catches vulnerable packages
but not secret leakage. There is no gitleaks, detect-secrets, or similar scanner
in the pipeline.

**Change**:

1. Add a new job `secret-scan` to `.github/workflows/ci.yml` using the
   `gitleaks/gitleaks-action` (or the `trufflesecurity/trufflehog-actions-scan`
   action) to scan every pushed commit and every pull-request diff for known
   secret patterns.
2. Use the pinned SHA form of the action reference (consistent with the existing
   actions in the repository, e.g., `actions/checkout@<sha>`).
3. Add a `.gitleaks.toml` (or equivalent) at the repository root to allowlist
   `.env.example` (which contains key _names_ but not real values) and the test
   fixtures in `packages/contracts/fixtures/` (which use synthetic data).

**Constraints**: The scan must run on `pull_request` and on pushes to `main`.
It must not block CI for false positives on existing fixture files. The chosen
action must be from the official gitleaks or trufflehog organisation (not a
fork) to avoid supply-chain risk. Pin to a commit SHA. Do not store any secret
in the workflow YAML; the scanner needs no credentials to scan public content.

**Tests first**: There are no unit tests for a CI workflow step. Verify by:

- Pushing a branch that adds a file containing a fake AWS key matching the gitleaks
  pattern and confirming the CI job fails.
- Pushing a branch that touches only `.md` files and confirming the scan passes.

**Done when**:

1. A PR containing a line matching `AKIA[0-9A-Z]{16}` (AWS key pattern) is blocked
   by the `secret-scan` CI job.
2. The existing repository passes the scan with the allowlist in place.
3. The action reference is pinned to a commit SHA.

**Validate**: Observe CI run on the PR branch; confirm `secret-scan` job appears
in the Actions UI.

---

## 79 — Document the suppressed advisory `GHSA-qwww-vcr4-c8h2` with justification and review date (Impact: M)

**Files**: `package.json` (root, `pnpm.auditConfig.ignoreGhsas`, lines 41–45),
`.github/workflows/dependency-review.yml` (`allow-ghsas`, line 30)

**Problem**: Advisory `GHSA-qwww-vcr4-c8h2` is suppressed in two places
(`package.json` and `dependency-review.yml`) with no inline comment explaining
which package is affected, why the vulnerability does not apply to this project,
who made the decision, and when it should be reviewed. Without this context, the
suppression becomes permanent by inertia: no future reviewer knows whether the
risk was ever assessed or whether the affected package has since been patched.

**Change**:

1. Add an inline comment directly above the `"GHSA-qwww-vcr4-c8h2"` entry in
   `package.json` (JSON does not support comments; instead, add a companion
   `"pnpm.auditConfig.justifications"` key with an object entry for the advisory
   ID, or document it in a `docs/security/advisory-suppressions.md` file).
2. Add an inline YAML comment in `dependency-review.yml` above `allow-ghsas`
   with the format:
   ```yaml
   # GHSA-qwww-vcr4-c8h2: <package> — <one-line reason this project is unaffected>.
   # Review date: <ISO date>. Re-evaluate when <package> releases a fix.
   ```
3. Create `docs/security/advisory-suppressions.md` documenting:
   - Advisory ID and CVE (if any).
   - Affected package name and version range.
   - Why this project is not affected (e.g., the vulnerable code path is not
     reachable, or the package is a dev-only dependency not present in production).
   - Decision date and reviewer.
   - Scheduled review date (suggest 90 days or when the next major version of the
     package is released).

**Constraints**: Do not remove the suppression without first confirming the
advisory is patched in the currently used version. The suppression must remain in
both `package.json` and `dependency-review.yml` until the package is updated. No
migration needed.

**Tests first**: No automated test is possible for a documentation change. Verify
by running `pnpm audit` locally and confirming the advisory is still suppressed
and the justification file exists.

**Done when**:

1. `docs/security/advisory-suppressions.md` exists and names the affected package,
   the reason for suppression, and a review date.
2. A YAML comment in `dependency-review.yml` references the justification document.
3. The suppression in `package.json` has a discoverable justification (via the
   companion document).

**Validate**: `pnpm audit --audit-level=high` (should pass with the suppression
in place); read `docs/security/advisory-suppressions.md` for completeness.

---

## 80 — Gate the commit SHA in `api/health.ts` behind an authenticated probe or remove it (Impact: L)

> **Audit correction**: The audit mentions exposing both "commit SHA and
> environment". Inspection of `api/health.ts` (lines 8–14) shows only the commit
> SHA field (`revision`), derived from `process.env.VERCEL_GIT_COMMIT_SHA`. There
> is no explicit `environment` field in the response body. The SHA alone is the
> concern.

**Files**: `api/health.ts` (`healthHandler`, lines 1–15)

**Problem**: `healthHandler` unconditionally includes
`revision: process.env.VERCEL_GIT_COMMIT_SHA` in the JSON response (lines 11–13).
A public commit SHA allows an attacker to identify the exact deployed version,
correlate it to a known-vulnerable dependency release, or enumerate recent commits
on the public GitHub repository. The health endpoint is used by Vercel's own
infrastructure monitoring and is publicly reachable without authentication. The
trust boundary crossed is: unauthenticated public probe → deployment version
disclosure.

**Change**:

Option A (preferred): Remove `revision` from the public response body entirely;
log it server-side on startup (`console.log("deployed revision:", VERCEL_GIT_COMMIT_SHA)`)
so Vercel's own function logs carry the information for operators.

Option B (if a monitored health check requires the SHA): Require a
`Authorization: ****** header; return the `revision`field only
when the header matches an environment variable`HEALTH_SECRET`; return the
standard `{ status: "ok" }`body without`revision` when the header is absent or
wrong.

**Constraints**: The endpoint must remain unauthenticated for its primary purpose
(load-balancer liveness check). If Option B is chosen, `HEALTH_SECRET` must be
documented in `.env.example` and must never be committed as a literal. No
migration needed.

**Tests first**:

- If Option A: assert the response body does not contain a `revision` key.
- If Option B: assert the response without the correct token omits `revision`;
  assert the response with the correct token includes it.

**Done when**:

1. An unauthenticated request to `GET /api/health` does not reveal the commit SHA.
2. The endpoint still returns HTTP 200 with `{ status: "ok" }` for liveness checks.
3. `corepack pnpm typecheck` exits 0.

**Validate**: `corepack pnpm typecheck`

---

## 81 — Confirm `X-Content-Type-Options: nosniff` applies to all API error responses (Impact: L)

> **Audit correction**: `vercel.json` (line 17) already adds
> `{ "key": "X-Content-Type-Options", "value": "nosniff" }` to the headers block
> with `source: "/(.*)"`. Vercel applies config-level headers to all responses
> including those from serverless functions, so the 502 error path in
> `api/fpl/[...path].ts` should receive the header from infrastructure. The code
> in the catch block (lines 21–36) sets `Content-Type` and `Cache-Control`
> programmatically but does not set `X-Content-Type-Options`; however, Vercel
> merges config headers on top of function-set headers, so the header should be
> present. The real gap is the absence of a test or documentation confirming this
> behaviour is relied upon.

**Files**: `vercel.json` (header rules, lines 13–33), `api/fpl/[...path].ts`
(catch block, lines 21–35), `api/team/[id].ts` (catch block, lines 24–38)

**Problem**: The `nosniff` header is set by Vercel's infrastructure layer for
all paths matching `/(.*)`; however, a future developer who extracts the error
response into a `Response` object returned directly (bypassing Vercel's header
injection) could inadvertently remove it. There is no test asserting the header
is present on 502 or 503 error responses.

**Change**:

1. In the catch blocks of `api/fpl/[...path].ts` (lines 24–30) and
   `api/team/[id].ts` (lines 27–31), explicitly set
   `response.setHeader("X-Content-Type-Options", "nosniff")` alongside the
   existing `Content-Type` and `Cache-Control` headers. This makes the guard
   resilient to changes in the Vercel header injection order.
2. Add a test asserting that an error response from `fplProxyHandler` includes
   `X-Content-Type-Options: nosniff`.

**Constraints**: The explicit `setHeader` call is additive — Vercel will merge
it with its own header injection, producing no duplicate because HTTP headers
coalesce. Do not remove the `vercel.json` header rule; belt-and-suspenders is
appropriate for this header. No migration needed.

**Tests first**: In the handler test file, add:

- `test_502_error_response_carries_nosniff_header` — mock `createFplProxyResponse`
  to throw; assert the response from `fplProxyHandler` has header
  `x-content-type-options: nosniff`.

**Done when**:

1. Both catch blocks explicitly set `X-Content-Type-Options: nosniff`.
2. A test asserts the header is present on 502/503 responses.
3. `corepack pnpm typecheck` exits 0.

**Validate**: `corepack pnpm typecheck`

---

## 82 — Reduce version detail in the outbound `FPL_USER_AGENT` strings (Impact: L)

**Files**: `python/fpl_andres/adapters/fpl.py` (`FPL_USER_AGENT`, line 18),
`api/_lib/fpl-proxy.ts` (`FPL_USER_AGENT`, lines 3–4)

**Problem**: Both the Python adapter and the TypeScript proxy send a `User-Agent`
header that includes the application version number:
`FPLAndres/0.5 (+https://github.com/JamieMBright/fpl-andres)` (Python, line 18)
and `FPLAndres/0.5.1 (+https://github.com/JamieMBright/fpl-andres)` (TypeScript,
line 3). The version numbers differ between the two (0.5 vs 0.5.1), indicating
the strings are maintained independently. The version in the User-Agent reveals
the exact deployed release to FPL's server logs, allowing correlation of known
bugs or vulnerabilities to a particular deployment. Additionally, the two values
diverging quietly means one of them is always stale.

**Change**:

1. Remove the version component from both strings, leaving only the contact URI:
   `FPLAndres (+https://github.com/JamieMBright/fpl-andres)`. This follows the
   convention of RFC 9110 §10.1.5 which allows a product token without a version.
2. Define the string once in each language layer from a single authoritative
   constant (they cannot share code, but the format must be identical).
3. Add a test in `python/tests/test_fpl_adapter.py` asserting that the sent
   `User-Agent` header does not contain a version number (pattern:
   `r"FPLAndres/\d"` must not match).

**Constraints**: The contact URI (`+https://github.com/JamieMBright/fpl-andres`)
must be retained so FPL can reach the project maintainer. Do not replace the
string with an empty value or a generic `python-httpx` default — that would
make attribution impossible. No migration needed.

**Tests first**: In `python/tests/test_fpl_adapter.py`, add:

- `test_user_agent_does_not_contain_version_number` — assert that the `User-Agent`
  sent in a proxied request does not match `r"FPLAndres/\d"`.
- `test_user_agent_contains_contact_uri` — assert `"github.com/JamieMBright/fpl-andres"`
  is present in the header.

**Done when**:

1. Both `FPL_USER_AGENT` constants omit the version number.
2. Both strings are identical in format.
3. `python -m pytest python/tests/test_fpl_adapter.py -q` exits 0.

**Validate**: `python -m pytest python/tests/test_fpl_adapter.py -q`
