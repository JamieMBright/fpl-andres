# 7. API and serverless functions — work orders

Detailed briefs for items 83–96 of the [improvement audit](../../IMPROVEMENTS.md).
Each brief is self-contained: a sub-agent should be able to implement one item
from its brief alone.

Every brief obeys the repository rules: test-first, never leak internal failure
detail or secrets to browser-visible responses or logs, and apply only tracked
migrations that pass local policy tests and Linux CI — the hosted Supabase
project is production and must never be edited by hand or inspected through AI
tools.

## 83 — Replace `console.error` with structured JSON logs (Impact: H)

**Files**: `api/fpl/[...path].ts` (line 23), `api/team/[id].ts` (line 26)

**Problem**: Both top-level catch blocks emit `console.error("fplProxyHandler crash:", error)` and
`console.error("teamPublicStateHandler crash:", error)` respectively. Vercel captures
`console.error` as plain text. This makes it impossible to reliably query logs by route, upstream
status, or request identity. A spike in 502s is unqueriable without string-scanning raw log lines.

**Change**:

1. Introduce a `logError(fields: Record<string, unknown>): void` helper in
   `api/_lib/log.ts` that emits a single `JSON.stringify` line to `process.stdout` (not
   `stderr`, so Vercel captures it as a structured log entry).
2. The log object must include at minimum: `level: "error"`, `route` (the handler filename or a
   short constant), `requestId` sourced from the incoming `request.headers["x-vercel-id"]` value
   (already present on Vercel invocations), `message`, and `durationMs` computed from a
   `Date.now()` call at handler entry.
3. Replace both `console.error(...)` calls with `logError({...})`.
4. The `x-fpl-andres-debug` response header must **not** echo the structured log body; it only
   carries the truncated error message (existing behaviour, item 95 extends it).

**Constraints**: The structured log must not contain the full error stack or any upstream response
body; those can contain PII or upstream credential hints. The `reason` field in the JSON response
body remains `"unreachable"` — log enrichment is server-side only.

**Tests first**: `apps/web/src/api/fpl-handler.test.ts` and
`apps/web/src/api/team-public-state-vercel-handler.test.ts` — add cases that spy on
`process.stdout.write` and assert the emitted string is valid JSON containing `level`, `route`, and
`requestId`. Confirm the response body does not contain the log payload.

**Done when**:

- Both handlers emit a single valid-JSON line on `process.stdout` for every unhandled error.
- The JSON object contains `level`, `route`, `requestId`, `message`, and `durationMs`.
- Neither `console.error` nor `console.log` is called in the two handler files.
- Existing handler tests remain green.
- `corepack pnpm -r test` passes.

**Validate**: `corepack pnpm -r test`

---

## 84 — Correlate retries under a single trace ID in `fetchWithRetries` (Impact: H)

**Files**: `api/_lib/fpl-proxy.ts` (`fetchWithRetries`, lines 117–178), `api/_lib/log.ts` (new,
per item 83)

**Problem**: `fetchWithRetries` loops up to `MAX_ATTEMPTS` (3) times. When a request succeeds on
attempt 3, the two preceding failures are silently discarded — no log entry names the upstream URL,
the failing status codes, or the attempt number. Diagnosing intermittent FPL instability requires
re-running the exact conditions that triggered retries.

**Change**:

1. Accept an optional `traceId: string` parameter in `createFplProxyResponse` (defaulting to a
   `crypto.randomUUID()` call) and thread it through to `fetchWithRetries`.
2. In `fetchWithRetries`, emit a structured log entry via `logError` (item 83) or a companion
   `logWarn` on every failed attempt that is _not_ the final one. Include: `traceId`, `attempt`
   (0-indexed), `upstreamUrl` (URL without query string), `upstreamStatus` (if a response was
   received), and `remainingMs`.
3. On terminal failure (null return), emit a final log entry at `level: "error"` with all retry
   attempt summaries.
4. The `traceId` must not appear in any response header or body sent to the browser.

**Constraints**: `upstreamUrl` logged must strip any query-string parameters to avoid leaking
manager-specific path segments. Existing function signature is public via
`createTeamPublicStateResponse` — maintain backward compatibility by making `traceId` optional with
a default.

**Tests first**: `apps/web/src/api/fpl-proxy.test.ts` — add cases using the injected
`fetchUpstream` stub that returns retryable statuses (e.g. 503 twice then 200). Assert that two
warning log entries and one success entry (or error entry on terminal failure) are emitted to
`process.stdout`, each containing `traceId` and matching `attempt` values.

**Done when**:

- Every retry attempt emits a structured log line with `traceId`, `attempt`, `upstreamStatus`, and
  `remainingMs`.
- Terminal failures emit a final `level: "error"` entry.
- `traceId` is absent from all HTTP response headers and bodies.
- `corepack pnpm -r test` passes.

**Validate**: `corepack pnpm -r test`

---

## 85 — Add an error-monitoring sink for API failures (Impact: H)

**Files**: `api/_lib/log.ts` (new, per item 83), `api/fpl/[...path].ts`, `api/team/[id].ts`,
`vercel.json`

**Problem**: There is no alerting sink today. A sustained spike in 502/503 responses from
`/api/fpl/` or `/api/team/[id]` is entirely invisible until a user files a report. `console.error`
output exists in Vercel log drain but is not routed to any pager or aggregation system.

**Change**:

1. Evaluate whether the existing Vercel log drain (configured outside the repository, in the Vercel
   dashboard) is sufficient to trigger alerts via a connected sink (e.g. Datadog, Axiom, or a
   Vercel integration). Document the chosen sink in `docs/RUNBOOK.md` under a new "Monitoring"
   section.
2. If a code-level sink is preferred (e.g. a Vercel Edge Config flag that enables sending a
   summarised alert payload to a pre-configured webhook URL), add the outbound call inside
   `logError` in `api/_lib/log.ts`, guarded by the environment variable
   `ALERT_WEBHOOK_URL`. The payload must contain only: `route`, `requestId`, `durationMs`,
   `level` — never error messages or upstream bodies.
3. Ensure `ALERT_WEBHOOK_URL` is listed in `.env.example` with an empty default and a comment
   explaining its purpose.
4. The alert call must be fire-and-forget (do not `await`) so it cannot add latency to the
   response path.

**Constraints**: `ALERT_WEBHOOK_URL` must never be logged or included in a response. The feature
must degrade silently when the variable is absent (local and CI environments).

**Tests first**: `apps/web/src/api/fpl-handler.test.ts` — add a case that sets
`process.env.ALERT_WEBHOOK_URL` to a stub URL, triggers a crash, and asserts the fetch was called
with the correct shape. Assert the response to the browser is unchanged.

**Done when**:

- A webhook alert is sent (non-blocking) whenever `logError` is called and `ALERT_WEBHOOK_URL` is
  set.
- The alert payload contains no error message text or upstream response content.
- `ALERT_WEBHOOK_URL` appears in `.env.example`.
- `corepack pnpm -r test` passes.

**Validate**: `corepack pnpm -r test`

---

## 86 — Reconcile the 8.5 s internal budget with the 10 s `maxDuration`; set per-route limits (Impact: H)

**Files**: `vercel.json` (lines 7–10, `"api/**/*.ts": { "maxDuration": 10 }`),
`api/_lib/fpl-proxy.ts` (`FPL_PROXY_BUDGET_MS = 8_500`, line 7), `api/health.ts`

**Problem**: `vercel.json` applies a single `maxDuration: 10` to every file matching
`api/**/*.ts`. This covers `api/health.ts`, which is a trivial synchronous handler, as well as
`api/fpl/[...path].ts` and `api/team/[id].ts`, which legitimately need up to 9 s. The 1.5 s gap
between the internal budget (8 500 ms) and the Vercel timeout (10 000 ms) is undocumented: if
`FPL_PROXY_BUDGET_MS` ever increases past 10 000 ms, Vercel will kill the function before it can
return a graceful 502.

**Change**:

1. Split `vercel.json` `functions` into three explicit entries:
   - `"api/health.ts": { "maxDuration": 5 }` — generous for a sync handler.
   - `"api/fpl/[...path].ts": { "maxDuration": 10 }` — retains current value.
   - `"api/team/[id].ts": { "maxDuration": 10 }` — retains current value.
     Remove the catch-all `"api/**/*.ts"` entry once all three are listed.
2. Add a comment (in `vercel.json` if the schema allows `//` comments, or in a companion
   `docs/adr/` entry) explaining that `maxDuration` must always exceed `FPL_PROXY_BUDGET_MS` by at
   least 500 ms to allow for graceful 502 serialisation time.
3. In `api/_lib/fpl-proxy.ts`, add a compile-time assertion (a top-level `if` statement with a
   `throw` or an `as const satisfies` expression) that `FPL_PROXY_BUDGET_MS < 9_500`, so a future
   increase will surface at test time.

**Constraints**: Vercel JSON does not support comments; the documentation must live elsewhere (ADR
or `RUNBOOK.md`). The handler response contract must not change.

**Tests first**: `apps/web/src/api/fpl-handler.test.ts` — verify `FPL_PROXY_BUDGET_MS` is
exported and strictly less than 9 500. Add a schema-validation test for `vercel.json` that asserts
`health.ts` has a lower `maxDuration` than the proxy routes.

**Done when**:

- `vercel.json` has three separate function entries, no catch-all `api/**/*.ts` entry.
- `api/health.ts` is limited to 5 s.
- A static assertion ensures `FPL_PROXY_BUDGET_MS < 9_500`.
- The ADR or runbook explains the 500 ms safety margin.
- `corepack pnpm -r test` passes.

**Validate**: `corepack pnpm -r test`

---

## 87 — Add short-lived response cache or request coalescing for `/api/team/[id]` (Impact: M)

**Files**: `api/_lib/team-public-state-response.ts` (`createTeamPublicStateResponse`),
`api/team/[id].ts`

**Problem**: `createTeamPublicStateResponse` currently returns `Cache-Control: private, no-store`
for every response (via the `jsonResponse` helper). Two browser tabs belonging to the same manager,
or a rapid page reload, each fire independent upstream FPL fetches for `/entry/{id}/`,
`/bootstrap-static/`, and `/entry/{id}/event/{gw}/picks/`. During peak traffic windows (just after
a gameweek deadline) this triples the upstream load per user.

**Change**:

1. For `status: "ready"` responses, change the `Cache-Control` header to
   `private, max-age=30, stale-while-revalidate=60`. Degraded and unavailable responses must remain
   `private, no-store`.
2. Alternatively (or additionally), introduce an in-memory request-coalescing map keyed by
   `entryId` inside the serverless function module. Concurrent requests for the same ID within a
   100 ms window share a single upstream `Promise`. The map entry must be deleted on resolution or
   rejection.
3. If coalescing is implemented, guard it with a size limit (e.g. 50 in-flight entries) to prevent
   unbounded memory growth.
4. Do not add any persistent external cache (Redis, KV); the scope is limited to the Vercel
   function's own execution context.

**Constraints**: Error and degraded responses must never be cached by the browser. The response
shape defined in `@fpl-andres/contracts` must not change. Coalescing must not swallow individual
request errors.

**Tests first**: `apps/web/src/api/team-public-state-handler.test.ts` — add cases asserting that
a `status: "ready"` response carries `Cache-Control: private, max-age=30, stale-while-revalidate=60`
and that degraded/unavailable responses carry `private, no-store`. If coalescing is added, add a
concurrency test asserting that two simultaneous calls with the same `entryId` result in exactly
one upstream fetch invocation.

**Done when**:

- `status: "ready"` responses carry the agreed `Cache-Control` value.
- Degraded responses carry `private, no-store`.
- If coalescing is implemented, concurrent identical requests produce one upstream call.
- `corepack pnpm -r test` passes.

**Validate**: `corepack pnpm -r test`

---

## 88 — Give each parallel upstream fetch its own per-source deadline (Impact: M)

**Files**: `api/_lib/team-public-state-response.ts` (`createTeamPublicStateResponse`, the
`Promise.all` at lines ~102–126)

**Problem**: A single `deadline` timestamp is computed at the start of `createTeamPublicStateResponse`
as `now() + FPL_PROXY_BUDGET_MS` and passed unmodified to both the entry-summary and
bootstrap-static `fetchSource` calls in the `Promise.all`. Because both calls share the same
absolute deadline, a slow bootstrap response that consumes 7 of the 8.5 s budget leaves only 1.5 s
for the picks fetch that follows, even if the picks endpoint is fast. The result is a spurious
`fpl_unreachable` degradation caused by budget starvation rather than a genuine FPL outage.

**Change**:

1. Compute a `parallelDeadline` as `now() + Math.floor(FPL_PROXY_BUDGET_MS * 0.6)` for the first
   `Promise.all` (entry + bootstrap) so the sequential picks fetch always has at least 40 % of the
   total budget remaining.
2. After the `Promise.all` resolves, compute a fresh `remainingDeadline = now() + Math.max(remainingMs, MIN_PICKS_BUDGET_MS)` for the picks fetch, where `MIN_PICKS_BUDGET_MS` is a new
   exported constant set to 2 000 ms.
3. Export `MIN_PICKS_BUDGET_MS` alongside `FPL_PROXY_BUDGET_MS` so tests can assert its value.

**Constraints**: The total wall-clock time must still be bounded by the outer
`FPL_PROXY_BUDGET_MS`; the change only re-distributes the budget within that envelope. The
response contract shape is unchanged.

**Tests first**: `apps/web/src/api/team-public-state-handler.test.ts` — add a case where the
bootstrap fetch artificially consumes 70 % of the budget (via a delayed `sleep` stub) and assert
that the picks fetch still receives a deadline of at least `MIN_PICKS_BUDGET_MS` ms in the future.
Verify the degraded response reason is `fpl_unreachable` only when the bootstrap fetch itself
fails, not when it is merely slow.

**Done when**:

- The parallel phase uses at most 60 % of the budget.
- The picks fetch always receives a deadline of at least `MIN_PICKS_BUDGET_MS` (2 000 ms).
- `MIN_PICKS_BUDGET_MS` is exported from `team-public-state-response.ts`.
- `corepack pnpm -r test` passes.

**Validate**: `corepack pnpm -r test`

---

## 89 — Parse each upstream body exactly once and cache the parsed value (Impact: M)

**Files**: `api/_lib/team-public-state-response.ts` (`parseSource`, called at ~lines 140–141;
`assembleTeamPublicState` called at ~line 200+), `api/_lib/team-public-state.ts` (`parseJsonBytes`)

**Problem**: The entry and bootstrap bodies are each decoded twice. First, `parseSource` in
`team-public-state-response.ts` calls `JSON.parse(new TextDecoder(...).decode(source.body))` to
validate the raw bytes against the Zod schemas `entrySummarySchema` and `bootstrapSchema`. Then the
same raw `source.body` bytes are forwarded to `assembleTeamPublicState`, which calls `parseJsonBytes`
to decode and re-validate them a second time. For the bootstrap body (up to 8 MB compressed,
potentially several MB JSON), this is a material redundant allocation.

**Change**:

1. Extend the `FetchedSource` interface (currently `{ body: Uint8Array; fetchedAt: string; status: number }`) with an optional `parsed?: unknown` field.
2. After calling `parseSource(entrySource, entrySummarySchema)` and
   `parseSource(bootstrapSource, bootstrapSchema)`, store the validated parsed objects on
   `entrySource.parsed` and `bootstrapSource.parsed`.
3. Update `assembleTeamPublicState` in `team-public-state.ts` to accept an optional
   `entryParsed?: unknown` and `bootstrapParsed?: unknown` parameter alongside the existing byte
   arrays. When the pre-parsed value is provided, skip `parseJsonBytes` for that source.
4. Pass the already-validated objects through the call in `createTeamPublicStateResponse`.

**Constraints**: The `assembleTeamPublicState` function must remain callable with raw bytes only
(for tests that exercise it directly). The `sourceHashes` in `PublicTeamState` must continue to be
computed from the original bytes, not the parsed representation.

**Tests first**: `apps/web/src/api/team-public-state.test.ts` — add a case confirming
`assembleTeamPublicState` accepts a pre-parsed entry object and does not call `JSON.parse` for
that source. Add a spy on `TextDecoder.prototype.decode` in the handler test to confirm it is
called at most once per source per request.

**Done when**:

- `TextDecoder.decode` is called at most once per upstream source per request in the full handler
  path.
- `assembleTeamPublicState` still works when called with raw bytes only (no pre-parsed values).
- `corepack pnpm -r test` passes.

**Validate**: `corepack pnpm -r test`

---

## 90 — Return a distinct `timeout` reason when `AbortSignal.timeout` fires (Impact: M)

**Files**: `api/_lib/fpl-proxy.ts` (`fetchWithRetries` catch block, ~line 155;
`FplProxyErrorReason` union at line 282; `createFplProxyResponse` unreachable return at lines
51–56)

**Problem**: When `AbortSignal.timeout` fires, the runtime throws a `DOMException` with
`name === "TimeoutError"`. The `catch` block inside `fetchWithRetries` does not inspect the error
type; it treats all thrown errors as network failures. After all retries are exhausted,
`createFplProxyResponse` returns a response with `reason: "unreachable"`. Callers (including
`fetchSource` in `team-public-state-response.ts`) cannot distinguish a per-attempt timeout from a
genuine network refusal, making it impossible to tune retry delays separately for the two cases.

**Change**:

1. In the `catch` block inside `fetchWithRetries`, check whether `error instanceof DOMException &&
error.name === "TimeoutError"`. If so, record the attempt as a `"timeout"` failure rather than
   a generic network error.
2. Extend `FplProxyErrorReason` to include `"timeout"` alongside `"unreachable"`,
   `"unexpected_format"`, and `"oversize"`.
3. When all attempts fail due to timeouts, return `reason: "timeout"` in the 502 JSON body.
4. Update `fetchSource` in `team-public-state-response.ts` to map `reason === "timeout"` to the
   `"unreachable"` outcome kind (timeout is a subclass of unreachable for the caller's purposes),
   but include the `timeout` classification in the structured log (item 84).

**Constraints**: The browser-facing response shape must remain backward compatible — adding a new
`reason` value is safe because existing clients treat unknown reasons as generic degradation.

**Tests first**: `apps/web/src/api/fpl-proxy.test.ts` — add a case where `fetchUpstream` throws a
`DOMException("AbortError", "TimeoutError")` on every attempt. Assert the returned response has
`status: 502` and `body.reason === "timeout"`.

**Done when**:

- `FplProxyErrorReason` includes `"timeout"`.
- A `DOMException` with `name === "TimeoutError"` produces `reason: "timeout"` in the 502 body.
- Generic network errors still produce `reason: "unreachable"`.
- `corepack pnpm -r test` passes.

**Validate**: `corepack pnpm -r test`

---

## 91 — Surface retryable vs terminal classification in structured logs (Impact: M)

**Files**: `api/_lib/fpl-proxy.ts` (`RETRYABLE_STATUSES`, line 12; `fetchWithRetries`, ~lines
145–147), `api/_lib/log.ts` (new, per item 83)

**Problem**: `RETRYABLE_STATUSES` encodes the distinction between retryable HTTP status codes
(408, 425, 429, 500, 502, 503, 504) and terminal ones, but this classification is never surfaced to
logs. An operational dashboard cannot tell whether a run of 502s represents an FPL outage (all
retryable, eventually resolved) or a contract break (terminal on first attempt, immediately
re-sent). The difference is crucial: one calls for patience, the other calls for a code fix.

**Change**:

1. Extend the per-attempt log entry (introduced in item 84) with a `retryable: boolean` field.
   Derive it from `RETRYABLE_STATUSES.has(response.status)` when a response was received, and from
   the error type when an exception was thrown (timeout → `true`, unknown → `false`).
2. Extend the terminal failure log entry with a `terminalReason` field taking one of:
   `"exhausted_retries"`, `"budget_exceeded"`, or `"non_retryable_status"`.
3. Export a `isRetryableStatus(status: number): boolean` helper from `fpl-proxy.ts` so tests can
   assert the full set of retryable codes without inspecting the private `Set`.

**Constraints**: `RETRYABLE_STATUSES` must not change its membership; the change is logging-only.
The response body and headers sent to the browser are unchanged.

**Tests first**: `apps/web/src/api/fpl-proxy.test.ts` — add cases asserting: (a) a 503 upstream
response emits a log entry with `retryable: true`; (b) a 400 upstream response emits `retryable:
false`; (c) a budget-exceeded terminal failure emits `terminalReason: "budget_exceeded"`.

**Done when**:

- Every per-attempt log entry includes `retryable`.
- Terminal failures include `terminalReason`.
- `isRetryableStatus` is exported and tested.
- `corepack pnpm -r test` passes.

**Validate**: `corepack pnpm -r test`

---

## 92 — Log upstream status alongside `TeamPublicStateContractError` (Impact: M)

**Files**: `api/_lib/team-public-state.ts` (`TeamPublicStateContractError`, lines 50–59),
`api/_lib/team-public-state-response.ts` (catch block in `createTeamPublicStateResponse`, ~line 220)

**Problem**: When `assembleTeamPublicState` throws `TeamPublicStateContractError`, the caller in
`createTeamPublicStateResponse` catches it and returns `degradedResponse("source_contract_failed")`
with no log entry. The upstream HTTP status codes, the source that failed, and the Zod validation
error are all discarded. If FPL changes its response shape (a real occurrence each season), the
first symptom is a `source_contract_failed` degraded response with no log evidence of which source
or field failed.

**Change**:

1. In the catch block within `createTeamPublicStateResponse` that catches
   `TeamPublicStateContractError | ZodError`, emit a `logWarn` (or `logError`) entry via the
   helper from item 83. Include: `upstreamEntryStatus`, `upstreamBootstrapStatus`,
   `upstreamPicksStatus` (the HTTP status codes already stored in `FetchedSource`), and the
   `error.message` (but not the full stack or the raw response body).
2. Extend `TeamPublicStateContractError` with an optional `source: "entry" | "picks" | "bootstrap"`
   field so the throwing site can indicate which upstream payload broke the contract.
3. Populate `source` at the three `parseJsonBytes` call sites in `assembleTeamPublicState`.

**Constraints**: The log entry must not include raw FPL response bytes. The HTTP response shape
is unchanged — degraded responses continue to carry `{ status: "degraded", reason: "source_contract_failed" }`.

**Tests first**: `apps/web/src/api/team-public-state-handler.test.ts` — add a case where the entry
upstream returns a 200 with a malformed payload. Assert a log entry is emitted with
`upstreamEntryStatus: 200` and `source: "entry"`.
`apps/web/src/api/team-public-state.test.ts` — verify `TeamPublicStateContractError` carries
`source` when thrown from `parseJsonBytes`.

**Done when**:

- A log entry is emitted on every `source_contract_failed` degraded response.
- The entry includes upstream status codes and `source`.
- Raw response bytes are absent from the log.
- `corepack pnpm -r test` passes.

**Validate**: `corepack pnpm -r test`

---

## 93 — Add latency instrumentation split between upstream wait and local processing (Impact: M)

**Files**: `api/fpl/[...path].ts`, `api/team/[id].ts`, `api/_lib/fpl-proxy.ts`
(`createFplProxyResponse`), `api/_lib/team-public-state-response.ts`
(`createTeamPublicStateResponse`), `api/_lib/log.ts` (new, per item 83)

**Problem**: There is no timing instrumentation anywhere in `api/`. Today it is impossible to
determine from logs whether a slow response was caused by a slow FPL upstream or by local
processing (JSON parsing, Zod validation, hash computation). Both handlers record a single
`console.error` on crash with no elapsed time.

**Change**:

1. Record `handlerStartMs = Date.now()` at the top of each handler (before any async work).
2. In `createFplProxyResponse`, return the upstream wait duration as an additional
   `upstreamMs` field alongside the existing `Response`. Alternatively, accept an optional
   `onTiming: (upstreamMs: number) => void` callback parameter.
3. In `createTeamPublicStateResponse`, record separate timings for: (a) the parallel upstream
   phase (entry + bootstrap), (b) the sequential picks fetch, and (c) local processing
   (parsing + assembly).
4. Emit a structured `logInfo` entry (a new log level alongside `logWarn` / `logError` from item 83) at successful handler exit containing: `route`, `requestId`, `totalMs`,
   `upstreamParallelMs`, `upstreamPicksMs`, `localMs`, and the response `status`.

**Constraints**: Timing fields must not appear in the HTTP response body or headers. The `now()`
injection already present in both functions must be used for timing, so tests can control the clock.

**Tests first**: `apps/web/src/api/team-public-state-handler.test.ts` — add a case that stubs
`now` to advance 200 ms during the parallel phase and asserts the emitted log entry has
`upstreamParallelMs >= 200` and `totalMs >= 200`. Assert the HTTP response body is unchanged.

**Done when**:

- A `logInfo` entry is emitted for every successful response containing `totalMs`,
  `upstreamParallelMs`, `upstreamPicksMs`, and `localMs`.
- Timing values use the injected `now()` so tests are deterministic.
- No timing fields appear in HTTP response bodies or headers.
- `corepack pnpm -r test` passes.

**Validate**: `corepack pnpm -r test`

---

## 94 — Eliminate the redundant `ArrayBuffer` copy when forwarding the response body (Impact: L)

**Files**: `api/_lib/fpl-proxy.ts` (`createFplProxyResponse`, lines 105–107)

**Problem**: After `readBoundedBody` returns a `Uint8Array`, the code allocates a fresh
`ArrayBuffer`, constructs a new `Uint8Array` view over it, and calls `.set(body)` to copy all
bytes before passing the `ArrayBuffer` to `new Response(...)`:

```
const responseBody = new ArrayBuffer(body.byteLength);
new Uint8Array(responseBody).set(body);
return new Response(responseBody, { ... });
```

`Response` accepts a `Uint8Array` (a `BufferSource`) directly. The intermediate allocation and
copy are unnecessary and double the peak memory for the response body (up to 8 MB for the
bootstrap endpoint).

**Change**:

1. Replace the three lines at 105–107 with `return new Response(body, { ... })`, passing the
   `Uint8Array` from `readBoundedBody` directly as the response body.
2. Confirm that `Response` constructed from a `Uint8Array` serialises identically to one
   constructed from an `ArrayBuffer` in the Node.js / Vercel runtime (both are `BufferSource`).

**Constraints**: The `Content-Type` and `Cache-Control` headers set at line 108–111 must be
preserved unchanged. The change must not affect observable response semantics (status, headers,
body bytes).

**Tests first**: `apps/web/src/api/fpl-proxy.test.ts` — the existing test suite already asserts
correct response bodies; no new test cases are strictly needed. Confirm all existing tests still
pass, and add an assertion that the response body bytes equal the upstream bytes byte-for-byte.

**Done when**:

- Lines 105–107 of `fpl-proxy.ts` are replaced with a direct `Uint8Array` pass to `Response`.
- No intermediate `ArrayBuffer` allocation exists in the hot path.
- All existing `fpl-proxy.test.ts` tests pass.
- `corepack pnpm -r test` passes.

**Validate**: `corepack pnpm -r test`

---

## 95 — Indicate truncation explicitly when the debug header is clipped (Impact: L)

**Files**: `api/fpl/[...path].ts` (lines 27–29), `api/team/[id].ts` (lines 30–32)

**Problem**: Both handlers set the `x-fpl-andres-debug` response header to
`message.slice(0, 300).replace(/[^\x20-\x7e]/g, "?")`. When a message is exactly 300 characters
or longer, the header value is silently clipped. A developer reading the header cannot know whether
the message ended naturally or was cut short, which makes diagnosing deeply nested errors harder.

**Change**:

1. Extract a shared `truncateDebugMessage(message: string, limit = 300): string` helper into
   `api/_lib/log.ts` (introduced in item 83).
2. The helper returns the sanitised message unchanged if it is within the limit. If the original
   (unsanitised) message length exceeds `limit - 14` characters, the helper clips the sanitised
   string and appends the literal suffix `"…[truncated]"` (14 bytes), so the header value never
   exceeds `limit` bytes.
3. Apply `truncateDebugMessage` in both handler catch blocks in place of the inline `.slice(0, 300)`
   expression.

**Constraints**: The header value must never exceed 300 bytes after the transformation. The suffix
must be ASCII-safe (no multi-byte characters). The helper must handle empty strings without error.

**Tests first**: Add unit tests for `truncateDebugMessage` in a new
`api/_lib/log.test.ts` file. Cases: (a) message under 300 chars — returned unchanged, no suffix;
(b) message over 286 chars — clipped and suffixed; (c) message exactly 300 chars — clipped and
suffixed; (d) message containing non-ASCII — sanitised before length check.

**Done when**:

- `truncateDebugMessage` is exported from `api/_lib/log.ts` and tested.
- Both handler catch blocks use `truncateDebugMessage` instead of inline `slice`.
- The header value never exceeds 300 bytes for any input.
- `corepack pnpm -r test` passes.

**Validate**: `corepack pnpm -r test`

---

## 96 — Document the intended CORS posture for `api/` in one place (Impact: L)

**Files**: `vercel.json`, `api/fpl/[...path].ts`, `api/team/[id].ts`, `api/health.ts`,
`docs/RUNBOOK.md` or a new `docs/adr/` entry

**Problem**: No `Access-Control-Allow-Origin` header is set in `vercel.json` or any handler. This
is intentional — all `api/` routes are same-origin by design, consumed only by the bundled
frontend. However, this posture is nowhere documented. A future contributor adding a new handler
may inadvertently add a permissive CORS header without realising the existing handlers are
deliberately same-origin, or may add a CORS header to `vercel.json` thinking the existing absence
is an oversight.

**Change**:

1. Add a comment block at the top of `vercel.json` (if the Vercel schema allows it) or a companion
   note in `docs/RUNBOOK.md` explaining: "All `/api/*` routes are same-origin. No
   `Access-Control-Allow-Origin` header is set deliberately; adding one would allow any origin to
   call these routes cross-origin, which is not the intended posture."
2. Add a brief "CORS posture" paragraph to `docs/RUNBOOK.md` under an "API security" or
   "Headers" section.
3. In `apps/web/src/api/fpl-handler.test.ts` and
   `apps/web/src/api/team-public-state-vercel-handler.test.ts`, add assertions that the response
   does **not** contain an `Access-Control-Allow-Origin` header, acting as a regression guard.

**Constraints**: No code change to handler logic is required. The only source changes are the
documentation and the regression-guard test assertions.

**Tests first**: The regression-guard assertions described in point 3 above must be added before
the documentation is written, to confirm the current behaviour is `no CORS header`.

**Done when**:

- `docs/RUNBOOK.md` contains an explicit same-origin CORS posture statement.
- Both handler test files assert absence of `Access-Control-Allow-Origin` in responses.
- `corepack pnpm -r test` passes.

**Validate**: `corepack pnpm -r test`
