# 11. Contracts, typing and API surface — work orders

Detailed briefs for items 138–148 of the [improvement audit](../../IMPROVEMENTS.md).
Each brief is self-contained: a sub-agent should be able to implement one item
from its brief alone.

Every brief obeys the repository rules: test-first, never default a missing
controlling FPL rule (fail the source contract visibly), keep `EvidenceLevel`
and source timestamps attached to recommendations, and keep the Pydantic and Zod
contracts generated and in parity.

## 138 — Enforce `no-explicit-any` as an error in ESLint (Impact: H)

**Files**: `eslint.config.js` (lines 27–41)

**Problem**: `eslint.config.js` spreads `tseslint.configs.recommended`, which includes
`@typescript-eslint/no-explicit-any` only at severity `"warn"`. The project does not
override it to `"error"`, so `any` annotations in TypeScript source compile and lint
cleanly. A future contributor can add `: any` anywhere in `apps/web/src/`,
`api/_lib/`, or `api/` without a CI failure. A grep of all `.ts`/`.tsx` files
under `apps/web/src/` and `api/` (excluding `.test.` and `spec.` files) currently
finds zero explicit `any` uses, so the blast radius of enabling the rule today is
zero files. The rule should be promoted to `"error"` now while the codebase is clean.

**Change**:

1. In `eslint.config.js`, inside the `rules` block (currently lines 33–40), add
   `"@typescript-eslint/no-explicit-any": "error"` alongside the two existing
   overrides. No files need to change to pass the rule because the codebase is
   currently clean.
2. Verify that `api/_lib/fpl-proxy.ts` (which uses `Record<string, string>` and
   typed unions throughout) and `api/_lib/team-public-state.ts` remain lint-clean.

**Constraints**: The `tseslint.configs.recommended` spread must be preserved.
Contract regeneration (`corepack pnpm contracts:check`) must still pass. The rule
must not be applied to `**/*.js` files (the config already restricts the TS rules to
`files: ["**/*.{ts,tsx}"]`).

**Tests first**: This is a lint-infrastructure change; no new test file is required.
The CI gate that proves it is the `pnpm lint` step. To verify locally before
committing, run `corepack pnpm lint` and confirm zero warnings or errors.

**Done when**:

1. `eslint.config.js` rules block contains `"@typescript-eslint/no-explicit-any": "error"`.
2. `corepack pnpm lint` exits 0 on an unmodified tree.
3. Introducing `: any` in any `.ts` file under `api/` or `apps/web/src/` causes
   `pnpm lint` to exit non-zero.
4. All other `pnpm check` steps continue to pass.

**Validate**: `corepack pnpm lint`

---

## 139 — Replace unchecked element-field casts in `publish_opening_squad.py` with schema-validated access (Impact: H)

**Files**: `python/fpl_andres/cli/publish_opening_squad.py` (lines 148, 155, 165,
173–177); `python/fpl_andres/adapters/fpl.py` (lines 77–82)

**Problem**: The loop over `bootstrap["elements"]` (starting at line 147) reads raw
dict fields and converts them with bare casts such as `int(element["element_type"])`,
`int(element["code"])`, `int(element["id"])`, `int(element["team"])`,
`int(element["now_cost"])`, and `float(element["probabilityStart"])` (the last one
supplied by the projection record rather than the bootstrap). If FPL renames or
removes a field, Python raises a `KeyError` or `ValueError` at runtime with no
diagnostic pointing to the contract boundary. The bootstrap payload enters via
`FplClient.fetch_bootstrap()` as `FetchedPayload[dict[str, Any]]` — it is never
validated against a schema before the CLI reads individual fields.

**Change**:

1. Define a Pydantic model (e.g. `BootstrapElement`) in
   `python/fpl_andres/contracts.py` or a new `python/fpl_andres/models/bootstrap.py`
   that covers the fields consumed by this CLI: `id`, `code`, `element_type`, `team`,
   `now_cost`, `status`, `web_name`. Use strict integer and string types.
2. Define a `BootstrapPayload` model that validates the top-level `elements`, `teams`,
   and `events` arrays from the bootstrap response.
3. In `publish_opening_squad.py`, call `BootstrapPayload.model_validate(bootstrap)` at
   the entry point of the build step, replacing the current ad-hoc loop casts. Remove
   all `int(element["..."])` calls and read typed attributes instead.
4. Follow the repository rule: if a required field is absent, raise a
   `FplContractError` (already defined in `adapters/fpl.py`) rather than silently
   defaulting.

**Constraints**: `mypy --strict` must remain green. The new Pydantic model must not
duplicate fields already in the shared `FplEntry` contract (`packages/contracts/`).
`corepack pnpm contracts:check` must still pass unchanged.

**Tests first**: Add tests in `python/tests/test_opening_squad.py` (already exists)
that construct a minimal bootstrap dict with a missing or wrong-typed field (e.g.
`"now_cost": "abc"`) and assert that `publish_opening_squad.main()` raises
`FplContractError` rather than a bare `KeyError` or `ValueError`.

**Done when**:

1. All `int(element["..."])` and `float(record["..."])` casts in the element loop are
   replaced by attribute access on validated model instances.
2. A test confirms that a malformed bootstrap element raises `FplContractError`.
3. `python -m mypy` exits 0.
4. `python -m pytest python/tests/test_opening_squad.py -q` passes.

**Validate**: `python -m pytest python/tests/test_opening_squad.py -q && python -m mypy`

---

## 140 — Replace `dict[str, Any]` return types on `FplClient` methods with typed models (Impact: M)

**Files**: `python/fpl_andres/adapters/fpl.py` (lines 77, 87, 94, 101, 113, 129, 143,
163, 168, 177, 185)

**Problem**: Every public method on `FplClient` returns
`FetchedPayload[dict[str, Any]]` or `FetchedPayload[list[dict[str, Any]]]`.
Callers downstream (the CLIs and publishing scripts) must re-validate or cast the
payload, and mypy cannot catch field-name typos or type mismatches at the call site.
The methods affected include `fetch_bootstrap`, `fetch_fixtures`, `fetch_entry`,
`fetch_entry_history`, `fetch_entry_picks`, `fetch_element_summary`,
`fetch_standings`, and `_fetch_json_object` / `_fetch_json_array`.

**Change**:

1. Define `TypedDict` or Pydantic models for each upstream response shape, grouped by
   endpoint. Suitable candidates: `BootstrapPayload` (elements, teams, events,
   game_settings), `FixtureItem`, `EntryHistory`, `EntryPicks`. Place them in
   `python/fpl_andres/models/bootstrap.py` or alongside the existing contracts.
2. Change each `FplClient` method's return type from `FetchedPayload[dict[str, Any]]`
   to the appropriate concrete type (e.g. `FetchedPayload[BootstrapPayload]`), running
   `model_validate` immediately after the raw bytes are decoded.
3. Remove the `cast(dict[str, Any], ...)` calls at lines 168 and 185.
4. The internal helpers `_fetch_json_object` and `_fetch_json_array` may remain
   generic; only the public surface needs concrete types.

**Constraints**: `mypy --strict` must remain clean. The existing `FetchedPayload`
generic wrapper must not be broken. Callers (`publish_opening_squad.py`,
`capture_crowd.py`, etc.) will need corresponding updates to use the new types; list
every caller touched. `corepack pnpm contracts:check` is unaffected (Python-only
change).

**Tests first**: Extend `python/tests/test_fpl_adapter.py` with a test that verifies
`client.fetch_bootstrap()` returns a `FetchedPayload` whose `.payload` is a typed
model, not a bare dict — asserting attribute access (e.g. `fetched.payload.elements`)
rather than key lookup.

**Done when**:

1. No public method on `FplClient` has `dict[str, Any]` in its return annotation.
2. `python -m mypy` exits 0 without `type: ignore` additions.
3. Existing `test_fpl_adapter.py` suite passes.
4. A new test validates typed attribute access on the returned payload.

**Validate**: `python -m mypy && python -m pytest python/tests/test_fpl_adapter.py -q`

---

## 141 — Model frontend fetch errors as a discriminated union instead of `unknown` (Impact: M)

**Files**: `apps/web/src/components/PlayerPoolTable.tsx` (line 111);
`apps/web/src/components/ManagerHistory.tsx` (line 48)

**Problem**: In `PlayerPoolTable.tsx` at line 111, the `.catch` callback receives
`error: unknown` and immediately narrows with an `instanceof PlayerPoolError` check;
the narrowing is correct but ad-hoc and the `"unreachable"` fallback is a plain
string. In `ManagerHistory.tsx` at line 48, the `catch` block receives no binding at
all (`catch { … }`) and silently sets `profile: null` with no distinction between a
network error, a contract violation, and an abort — callers cannot tell whether to
retry or suppress. Neither component models the full error surface as a named
discriminated union that TypeScript can exhaustively check.

**Change**:

1. Define a `FetchError` discriminated union (e.g. in a shared
   `apps/web/src/lib/fetch-error.ts`) with variants such as `{ kind: "aborted" }`,
   `{ kind: "network" }`, `{ kind: "contract"; detail: string }`, and
   `{ kind: "not_found" }`.
2. Replace the bare `catch` in `ManagerHistory.tsx` with a typed handler that
   classifies the thrown value into a `FetchError` variant and exposes it to the
   component's error state rather than mapping everything to `null`.
3. Update `PlayerPoolTable.tsx` to use the same `FetchError` union so that
   `PlayerPoolError.reason` maps to a `FetchError` variant rather than a raw string
   fallback.
4. Update any component props or state types that currently accept `string` error
   reasons to accept the new union.

**Constraints**: `corepack pnpm typecheck` must pass. The `@typescript-eslint/no-explicit-any`
rule (item 138) must remain satisfied. Existing Playwright journeys in
`apps/web/e2e/` that exercise error states (`feature-walk.spec.ts` lines 222–244,
268–275; `team-entry.spec.ts` lines 185–205) must continue to pass.

**Tests first**: Add a Vitest unit test in `apps/web/src/` that feeds a mocked fetch
throwing each error variant into the `ManagerHistory` component and asserts that the
correct rendered output appears (e.g. a retry button for `"network"`, suppression for
`"aborted"`).

**Done when**:

1. `ManagerHistory.tsx` has no bare `catch` block — every error path is classified.
2. `PlayerPoolTable.tsx` uses the shared `FetchError` union instead of an inline
   string fallback.
3. `corepack pnpm typecheck` exits 0.
4. New unit tests cover at least three error variant branches.

**Validate**: `corepack pnpm typecheck && corepack pnpm test`

---

## 142 — Require a contracts package version bump whenever the generated schema changes (Impact: M)

**Files**: `packages/contracts/package.json` (current version `0.5.1`);
`packages/contracts/scripts/export-schema.ts`; `.github/workflows/ci.yml`

**Problem**: The `schema:check` script (`tsx scripts/export-schema.ts --check`)
detects schema drift but does not assert that `packages/contracts/package.json`
`"version"` was incremented to match. A contributor can regenerate the schema
(`corepack pnpm contracts:generate`) and commit the new `generated/contracts.schema.json`
without bumping the package version, making consumers unable to detect the silent
change via semver. CI runs `pnpm contracts:check` inside `pnpm check`, but there is
no step that checks whether the version field moved.

**Change**:

1. In `packages/contracts/scripts/export-schema.ts`, record the content hash of
   `generated/contracts.schema.json` before and after the `--check` run. When
   running in `--check` mode, if the generated schema differs from the committed file,
   also assert that `package.json` `"version"` is strictly greater than the last
   committed version (read from git via `git show HEAD:packages/contracts/package.json`
   or a recorded baseline file). Emit a clear error message such as
   `"Schema changed but package.json version was not bumped"` and exit non-zero.
2. Alternatively, store a `schema-version` field inside
   `generated/contracts.schema.json` itself and assert it equals the `package.json`
   version; a mismatch fails both `schema:check` and `schema:generate` if the caller
   forgets to update both.
3. Document the versioning requirement in `packages/contracts/README.md` (create if
   absent) or in `CONTRIBUTING.md`.

**Constraints**: The check must not require a git history fetch that would break
offline builds. `corepack pnpm contracts:check` must still be the canonical gate.

**Tests first**: Add a test in `packages/contracts/src/fpl.test.ts` (already exists)
that imports the generated schema and asserts the embedded `schemaVersion` field
equals the `version` field from `package.json`.

**Done when**:

1. Regenerating the schema without bumping `package.json` version causes
   `corepack pnpm contracts:check` to exit non-zero.
2. The `fpl.test.ts` version assertion passes.
3. Current tree passes `corepack pnpm contracts:check` without modification.

**Validate**: `corepack pnpm contracts:check`

---

## 143 — Promote schema-drift detection to a named CI gate (Impact: M)

**Files**: `.github/workflows/ci.yml`; `package.json` (line 12, the `"check"` script)

**Problem**: The root `package.json` `"check"` script runs
`corepack pnpm contracts:check` as its first subcommand (line 12), but the CI
`"Validate repository"` step invokes the entire `pnpm check` chain. If the schema
drifts, the failure message appears deep inside the combined output of a step labelled
"Validate repository", making triage harder. There is no separately named, skippable
CI job or step whose sole responsibility is verifying contract parity.

**Change**:

1. In `.github/workflows/ci.yml`, add a dedicated step named `"Check contract schema
parity"` (before the existing `"Validate repository"` step) that runs only
   `corepack pnpm contracts:check`. This step will fail fast and with a clear label
   before the expensive typecheck/build/test chain runs.
2. Optionally, extract the contracts check into its own CI job with
   `needs: []` so it can run in parallel with linting on pull requests.
3. Keep the `contracts:check` call inside the `"check"` script as a second line of
   defence; the dedicated CI step is additive.

**Constraints**: Total CI wall time must not increase significantly. The existing
`pnpm check` script must remain unchanged. The new step must use the same pinned
action versions (Node `20.20.2`, pnpm `9.15.9`) as the existing job.

**Tests first**: This is a CI-infrastructure change. Verify by running
`corepack pnpm contracts:check` locally and confirming it exits 0. The proof that the
gate exists is the named step appearing in the GitHub Actions workflow summary.

**Done when**:

1. `.github/workflows/ci.yml` contains a step named `"Check contract schema parity"`
   that runs `corepack pnpm contracts:check` before `pnpm check`.
2. The step exits 0 on the current tree.
3. Deliberately corrupting `generated/contracts.schema.json` and pushing causes only
   this step to fail, not the entire "Validate repository" step.

**Validate**: `corepack pnpm contracts:check` (locally); inspect CI step labels on a
pull request.

---

## 144 — Add `explicit-module-boundary-types` for exported helpers in `api/_lib/` (Impact: M)

**Files**: `eslint.config.js` (lines 27–41); `api/_lib/fpl-path.ts`,
`api/_lib/fpl-proxy.ts`, `api/_lib/team-public-state.ts`,
`api/_lib/team-public-state-response.ts`

**Problem**: The `@typescript-eslint/explicit-module-boundary-types` rule is absent
from `eslint.config.js`. The exported functions in `api/_lib/` — specifically
`normalizeVercelProxyUrl`, `resolveFplUpstreamUrl` (`fpl-path.ts`),
`createFplProxyResponse` (`fpl-proxy.ts`), `assembleTeamPublicState`
(`team-public-state.ts`), and `createTeamPublicStateResponse`
(`team-public-state-response.ts`) — form the internal API surface of the Vercel edge
handlers. Without explicit return-type annotations enforced by the linter, TypeScript
infers return types, meaning a refactor can silently widen a return type (e.g. from
`Promise<Response>` to `Promise<Response | undefined>`) without a compile error.

**Change**:

1. In `eslint.config.js`, add
   `"@typescript-eslint/explicit-module-boundary-types": "error"` to the `rules`
   block. This rule applies to all `.ts`/`.tsx` files already covered by the config's
   `files` glob.
2. Add explicit return-type annotations to any exported function in `api/_lib/` that
   TypeScript currently infers. Based on a current inspection, all five exported
   functions appear to be fully typed, so the blast radius is expected to be zero
   files. Confirm by running `corepack pnpm lint` after adding the rule.
3. If `apps/web/src/` exports any function without an explicit return type, add
   annotations there too.

**Constraints**: The rule applies only to _exported_ symbols; internal helper
functions (`fetchWithRetries`, `readBoundedBody`, etc. in `fpl-proxy.ts`) are exempt.
`mypy` is unaffected (Python-only rule). `corepack pnpm contracts:check` must still
pass.

**Tests first**: No new test file required. The lint rule is the gate. Run
`corepack pnpm lint` before and after adding the rule to confirm zero new violations.

**Done when**:

1. `eslint.config.js` contains the `explicit-module-boundary-types` rule at `"error"`.
2. `corepack pnpm lint` exits 0 on the unmodified tree.
3. Removing a return-type annotation from an exported function in `api/_lib/` causes
   `pnpm lint` to fail.

**Validate**: `corepack pnpm lint`

---

## 145 — Add `require-await` and `no-floating-promises` to catch async misuse (Impact: L)

**Files**: `eslint.config.js` (lines 27–41); all `.ts`/`.tsx` files under
`apps/web/src/`, `api/`, `api/_lib/`

**Problem**: `@typescript-eslint/require-await` and
`@typescript-eslint/no-floating-promises` are not in `eslint.config.js`. Without
`require-await`, an `async` function that never uses `await` compiles and lints
cleanly even though the `async` keyword is redundant and can mask missing `await`
calls. Without `no-floating-promises`, an unawaited `Promise` (e.g.
`void read()` patterns in React effects, or fire-and-forget handler calls) goes
undetected. The Vercel handlers in `api/` and React effects in `apps/web/src/` are
particularly susceptible.

**Change**:

1. Add `"@typescript-eslint/require-await": "error"` and
   `"@typescript-eslint/no-floating-promises": "error"` to the `rules` block in
   `eslint.config.js`.
2. Run `corepack pnpm lint` and enumerate any new violations. Common false-positive
   patterns: intentional `void` casts (already used in `ManagerHistory.tsx` as
   `void read()`). For legitimate fire-and-forget calls, the `void` operator satisfies
   `no-floating-promises`; add `void` prefixes where appropriate rather than disabling
   the rule.
3. For `require-await`, remove the `async` keyword from any function that does not
   contain an `await` expression and can be synchronous.

**Constraints**: Neither rule requires `parserOptions.project` (type-aware linting).
If type-aware linting is needed for `no-floating-promises`, enable
`languageOptions.parserOptions.project: true` in `eslint.config.js` for the affected
file globs only, and ensure CI wall time does not regress. Existing Playwright e2e
journeys must continue to pass.

**Tests first**: No new test file needed. The lint gate is the proof. Enumerate
violation sites by running `corepack pnpm lint` with only the new rules enabled in
isolation before committing.

**Done when**:

1. Both rules appear in `eslint.config.js` at `"error"`.
2. `corepack pnpm lint` exits 0 with no suppressions added.
3. Introducing an unawaited `fetch(...)` call in a handler causes `pnpm lint` to fail.

**Validate**: `corepack pnpm lint`

---

## 146 — Define `__all__` in every Python package that lacks it (Impact: L)

**Files**: The following `__init__.py` and module files currently have no `__all__`
declaration:

- `python/fpl_andres/__init__.py`
- `python/fpl_andres/adapters/__init__.py` (1-line file)
- `python/fpl_andres/optimization/__init__.py` (1-line file)
- `python/fpl_andres/models/__init__.py`
- `python/fpl_andres/cli/__init__.py`
- `python/fpl_andres/adapters/fpl.py`
- `python/fpl_andres/contracts.py`
- `python/fpl_andres/models/deployment.py`
- `python/fpl_andres/models/contracts.py`
- `python/fpl_andres/models/baselines.py`
- `python/fpl_andres/models/dixon_coles.py`
- `python/fpl_andres/models/metrics.py`
- `python/fpl_andres/models/promotion.py`
- `python/fpl_andres/models/walk_forward.py`
- `python/fpl_andres/persistence/supabase.py`
- And several `cli/` modules: `publish_projections.py`, `publish_opening_squad.py`,
  `sweep_managers.py`, `crosswalk.py`, `validate.py`, `ingest_historical.py`,
  `live_contracts.py`

**Problem**: Public surface is implicit for all the above. A wildcard import or an
IDE auto-complete will expose internal helpers alongside the intended API.
Inconsistency with modules that _do_ declare `__all__` (e.g. `persistence/__init__.py`
at line 16, `persistence/workflow.py` at line 121, `crosswalk/resolve.py` at line 35)
makes the boundary hard to understand at a glance.

**Change**:

1. For each file above, add `__all__` listing only the names that external callers
   should import. For `__init__.py` files that currently re-export from submodules,
   list the re-exported names. For implementation modules (`fpl.py`,
   `supabase.py`, etc.), list only the public classes, functions, and constants
   (e.g. `FplClient`, `FplContractError`, `FplPicksUnavailable`, `normalize_entry`
   for `adapters/fpl.py`).
2. CLI entry-point modules (`publish_projections.py`, etc.) should export at minimum
   `build_parser` and `main` to match the pattern established in `capture_crowd.py`
   and `verify_veterans.py`.

**Constraints**: No runtime behaviour changes. `python -m mypy` must remain clean.
`ruff` enforces `__all__` completeness via `F401`; ensure no accidental re-export
suppression. Existing tests must pass unchanged.

**Tests first**: No new test file needed. Run `python -m ruff check python` and
confirm `F401` (unused import) does not trigger new errors after `__all__` is added.

**Done when**:

1. Every `__init__.py` and public module file in `python/fpl_andres/` declares
   `__all__`.
2. `python -m ruff check python` exits 0.
3. `python -m mypy` exits 0.

**Validate**: `python -m ruff check python && python -m mypy`

---

## 147 — Type the sort-key callable in `publish_projections.py` (Impact: L)

**Files**: `python/fpl_andres/cli/publish_projections.py` (line 117)

**Problem**: Line 117 reads:

```
key=lambda entry: entry["code"],  # type: ignore[arg-type,return-value]
```

The `# type: ignore` suppresses two mypy errors rather than fixing the underlying
type gap. The `_entry()` helper (defined earlier in the file) returns a
`dict[str, Any]`, so `entry["code"]` has type `Any`, which confuses mypy's
`sorted()` overload resolution. If the `_entry()` return type were concrete (e.g. a
`TypedDict` with a typed `code: int` field), the `type: ignore` would be unnecessary
and a future rename of `"code"` to another key would cause a mypy error rather than a
silent bug.

**Change**:

1. Define a `ProjectionRow` `TypedDict` (or dataclass) in `publish_projections.py` or
   in `python/fpl_andres/models/bootstrap.py` that captures the shape returned by the
   `_entry()` helper: at minimum `code: int`, `webName: str`, and
   `expectedPoints: float`.
2. Change `_entry()` to return `ProjectionRow` instead of `dict[str, Any]`.
3. Remove the `# type: ignore[arg-type,return-value]` comment from line 117; mypy
   should now resolve the `sorted()` key type correctly.
4. Verify that `python -m mypy` passes without the suppression.

**Constraints**: The structure of the emitted `projections.json` artifact must not
change (the field names are consumed by the frontend). `corepack pnpm contracts:check`
is unaffected. `python -m ruff check python` must remain clean.

**Tests first**: The existing `python/tests/test_opening_squad.py` does not exercise
`publish_projections.py` directly. Add a small test in `python/tests/test_opening_squad.py`
or a new `python/tests/test_publish_projections.py` that calls `_entry()` (imported
directly) and asserts the returned dict has a typed-compatible `code` key, confirming
the suppression is gone.

**Done when**:

1. Line 117 of `publish_projections.py` has no `# type: ignore` comment.
2. `_entry()` return annotation is a concrete `TypedDict` or dataclass, not `dict[str, Any]`.
3. `python -m mypy` exits 0.
4. The emitted JSON structure is identical to the pre-change artifact.

**Validate**: `python -m mypy && python -m pytest python/tests/ -q -k "projections"`

---

## 148 — Reduce remaining `Any` annotations in `persistence/` and `cli/` (Impact: L)

**Files** (current violation sites):

- `python/fpl_andres/persistence/supabase.py` lines 113, 128, 151, 195, 208 —
  methods returning `list[dict[str, Any]]`
- `python/fpl_andres/persistence/workflow.py` lines 30, 80, 83 —
  `metadata: dict[str, Any]`
- `python/fpl_andres/cli/capture_crowd.py` lines 49, 69, 82, 88, 90, 108, 155 —
  bootstrap helper parameters and return types annotated `Any`

**Problem**: The persistence layer's `SupabaseRestClient.insert()` and related methods
return `list[dict[str, Any]]`, preventing mypy from verifying that callers read the
correct field names from the returned rows. `WorkflowRun.metadata` typed as
`dict[str, Any]` allows arbitrary keys without schema checks. In `capture_crowd.py`,
functions accepting `bootstrap: dict[str, Any]` repeat the same unsafe pattern
identified in items 139 and 140.

**Change**:

1. For `supabase.py`: introduce a `RowData = TypeAlias` for `Mapping[str, object]`
   (read-only row input) and `InsertedRow = TypeAlias` for `dict[str, object]`
   (returned row). Replace `dict[str, Any]` with these aliases in the method
   signatures. Where the actual shape is known (e.g. `backtest` rows returned from
   `insert(..., returning=True)`), use the appropriate Pydantic model or `TypedDict`.
2. For `workflow.py`: define a `WorkflowMetadata` `TypedDict` covering the keys
   actually stored (inspect existing callers to enumerate them) and replace
   `dict[str, Any]` at lines 30, 80, and 83.
3. For `capture_crowd.py`: replace `bootstrap: dict[str, Any]` parameters with the
   `BootstrapPayload` model introduced in item 139 (or 140), and remove the
   `_optional_int(value: Any)` annotation once `value` is narrowed at call sites.

**Constraints**: `python -m mypy` (strict mode) must remain clean. No behaviour
changes. The `supabase.py` changes must not break `python/tests/test_persistence.py`
or `python/tests/test_backtest_persistence.py`. Avoid making `supabase.py` import
from domain modules (keep the persistence layer dependency-free from model types if
a `TypedDict` alias suffices).

**Tests first**: Run `python -m mypy` before and after each file change. The mypy
output is the test; the goal is to remove `Any` occurrences counted by
`python -m mypy --any-exprs-report` (or equivalent) without adding new suppressions.

**Done when**:

1. `supabase.py`, `workflow.py`, and `capture_crowd.py` contain no unqualified `Any`
   annotations that mypy flags as unsafe (i.e., no `Revealed type is 'Any'` lines for
   these modules).
2. `python -m mypy` exits 0.
3. `python -m pytest python/tests/test_persistence.py python/tests/test_backtest_persistence.py -q` passes.

**Validate**: `python -m mypy && python -m pytest python/tests/test_persistence.py python/tests/test_backtest_persistence.py -q`
