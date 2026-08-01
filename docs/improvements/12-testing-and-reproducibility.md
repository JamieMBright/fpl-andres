# 12. Testing and reproducibility — work orders

Detailed briefs for items 149–167 of the [improvement audit](../../IMPROVEMENTS.md).
Each brief is self-contained: a sub-agent should be able to implement one item
from its brief alone.

Every brief obeys the repository rules: test-first, never default a missing
controlling FPL rule (fail the source contract visibly), keep `EvidenceLevel`
and source timestamps attached to recommendations, and keep the Pydantic and Zod
contracts generated and in parity.

## 149 — Add missing negative-path tests for the FPL adapter (Impact: H)

**Files**: `python/tests/test_fpl_adapter.py` (263 lines); `python/fpl_andres/adapters/fpl.py`

**Problem**: The audit claim that oversize responses are untested is **stale**:
`test_bootstrap_fetch_rejects_declared_oversized_response` (line 128) and
`test_entry_fetch_stops_chunked_body_at_size_limit` (line 147) already exist.
A 503 → 200 retry sequence is covered at line 72. What is genuinely missing:

- **Exhausted retries**: all three attempts (`MAX_ATTEMPTS = 3`) return a retryable
  status (e.g. three consecutive 503s); the adapter must raise rather than return.
- **Malformed JSON**: the server returns HTTP 200 with a body that is not valid JSON;
  the adapter must raise `FplContractError` (not a bare `json.JSONDecodeError`).
- **Timeout / connect error**: `httpx.ConnectTimeout` or `httpx.ReadTimeout` on every
  attempt; the adapter must raise an informative error after exhausting retries.
- **Truncated stream**: the server sends a partial JSON body and closes the connection
  mid-transfer; the adapter must not silently return partial data.

**Change**:

1. In `python/tests/test_fpl_adapter.py`, add four new async test functions, each
   decorated `@pytest.mark.asyncio`, using `respx.mock` or `httpx.MockTransport` to
   inject the failure mode. Use `AsyncMock` for the `sleep` parameter to assert
   correct backoff without real delays.
2. For the exhausted-retries test, configure `respx` to return 503 on all three
   routes and assert the correct exception type is raised.
3. For the malformed-JSON test, return HTTP 200 with `content=b"not json"` and assert
   `FplContractError` is raised with a descriptive message.

**Constraints**: Tests must be deterministic: pass `random=lambda: 0.5` and a fixed
clock. No network calls. `MAX_ATTEMPTS` and `RETRYABLE_STATUSES` are importable
constants from `adapters/fpl.py`; use them rather than hardcoding.

**Tests first**: The tests _are_ the deliverable. A run of
`python -m pytest python/tests/test_fpl_adapter.py -q` must show the four new tests
passing. A failing run before the adapter is fixed should show the specific exception
type mismatch.

**Done when**:

1. Four new tests cover: exhausted retries, malformed JSON, connect timeout,
   truncated stream.
2. All 263 + 4 tests in `test_fpl_adapter.py` pass.
3. `python -m mypy` exits 0 (no new `Any` introduced by test helpers).

**Validate**: `python -m pytest python/tests/test_fpl_adapter.py -q`

---

## 150 — Add tests that exercise the real PostgREST dialect and batch limits (Impact: H)

**Files**: `python/tests/test_backtest_persistence.py` (118 lines);
`python/fpl_andres/persistence/supabase.py`

**Problem**: `test_backtest_persistence.py` uses `FakeClient` (a hand-rolled in-memory
stub) for all 5 test functions. The `SupabaseRestClient` in `supabase.py` builds HTTP
requests against the PostgREST dialect (Prefer headers, `resolution=merge-duplicates`
upsert, `on_conflict` query parameters, JSON body encoding). None of these wire-level
details are exercised. Silent regressions can occur if a header name or query
parameter is misspelled — the fake client accepts anything.

**Change**:

1. Add a new test module `python/tests/test_supabase_client.py` that uses `respx` to
   intercept HTTP calls made by `SupabaseRestClient` and asserts:
   - The `Prefer: resolution=merge-duplicates` header is present on upsert calls.
   - The `Prefer: return=representation` header is present when `returning=True`.
   - The `on_conflict` query parameter matches the caller-supplied value.
   - Rows are JSON-encoded in the request body.
   - A non-2xx response raises `PostgRESTError` (defined in `supabase.py` line 30).
2. Add a batch-limit test: if `SupabaseRestClient` (or its callers) imposes a
   per-request row limit, assert that a batch of rows exceeding the limit is split
   into multiple requests. If no limit exists today, document that as the tested
   invariant ("single request regardless of batch size") so a future limit addition
   is a deliberate, tested change.
3. Use `respx.mock` with `assert_all_called=True` to ensure no unintended extra
   requests are made.

**Constraints**: No live Supabase connection. Tests must be fully offline. `respx`
is already a dev dependency. `python -m mypy` must remain clean.

**Tests first**: The new `test_supabase_client.py` must fail before any production
changes; once the assertions match the actual `SupabaseRestClient` implementation,
they pass.

**Done when**:

1. `test_supabase_client.py` covers Prefer headers, on_conflict param, error raising,
   and batch behaviour with at least 5 test functions.
2. `python -m pytest python/tests/test_supabase_client.py -q` exits 0.
3. `python -m mypy` exits 0.

**Validate**: `python -m pytest python/tests/test_supabase_client.py -q`

---

## 151 — Extend browser journeys to cover more override and storage edge cases (Impact: H)

> **Audit correction**: The claim that `apps/web/e2e/` "currently covers the happy
> paths of two flows" is **stale**. Both `feature-walk.spec.ts` and `team-entry.spec.ts`
> already cover `degraded`, `unavailable`, and stale-cache states (lines 222–244,
> 268–275 of `feature-walk.spec.ts`; lines 156–205 of `team-entry.spec.ts`). The
> genuine gap is the **override-storage edge cases** described in item 164 — see that
> brief for the concrete deliverable.

**Files**: `apps/web/e2e/feature-walk.spec.ts`; `apps/web/e2e/team-entry.spec.ts`

**Remaining gap**: The e2e suite does not cover:

- The `"error"` state where the server returns HTTP 500 (rather than a structured
  degraded/unavailable envelope) and the UI must show an honest failure message.
- The transition from a previous entry's cached state being visible when a _different_
  entry ID is entered (stale cross-entry cache).

**Change**:

1. In `team-entry.spec.ts`, add a test that mocks `**/api/team/*` to return HTTP 500
   (raw server error, not the structured envelope) and asserts the UI renders an
   appropriate error heading and does not display a squad.
2. Add a test that pre-populates `localStorage` with a cached state for entry
   `212279`, navigates to entry `999999`, and asserts the old entry's squad is not
   shown for the new entry.

**Constraints**: Tests must work with the existing `mockTeamResponse` helper. Must
not add new Playwright project configurations. CI wall time impact must be minimal
(both tests should complete in under 5 s each).

**Tests first**: Write the tests first; both will initially fail because the UI
behaviour may not be implemented. Implement the minimal UI change if needed, then
confirm the tests pass.

**Done when**:

1. A test for the HTTP-500 error state exists and passes.
2. A test for the stale cross-entry cache exists and passes.
3. `corepack pnpm test:e2e` exits 0.
4. Existing journeys continue to pass.

**Validate**: `corepack pnpm test:e2e`

---

## 152 — Enforce coverage thresholds in CI for Python and the web workspace (Impact: H)

**Files**: `pyproject.toml` (`[tool.pytest.ini_options]`); `.github/workflows/ci.yml`;
`package.json`

**Problem**: `pytest-cov>=6` is listed as a dev dependency in `pyproject.toml` but
`addopts` (line 40) does not include `--cov`, `--cov-report`, or `--cov-fail-under`.
The `pnpm test` command runs Vitest for the contracts package but there is no coverage
collection or minimum threshold enforced for the web workspace. Both deficiencies mean
a PR can delete tests or comment out branches without any CI failure.

**Change**:

1. In `pyproject.toml` `[tool.pytest.ini_options]`, extend `addopts` with
   `--cov=python/fpl_andres --cov-report=term-missing --cov-fail-under=<threshold>`.
   Determine the threshold by running `python -m pytest --cov=python/fpl_andres`
   once and rounding the current line coverage down to the nearest 5 % (as a
   conservative floor). Record the chosen threshold in a comment.
2. For the web workspace, add `coverage: { enabled: true, thresholds: { lines: N } }`
   to `apps/web/vitest.config.ts` (create if it does not exist) where `N` is the
   current measured line coverage rounded down to the nearest 5 %.
3. In `.github/workflows/ci.yml`, the coverage thresholds are enforced automatically
   via `pnpm check` (which calls `python -m pytest` and `corepack pnpm test`); no
   separate CI step is needed.

**Constraints**: Coverage collection must not add more than 30 s to CI wall time.
The `PYTHONHASHSEED` and clock-freezing requirements of item 161 should be applied
first so coverage runs are reproducible. Do not set thresholds above the current
measured coverage — the goal is a floor, not a target.

**Tests first**: The thresholds are the test. Run `python -m pytest --cov=python/fpl_andres --cov-fail-under=<threshold>` locally and confirm it exits 0 before committing.

**Done when**:

1. `pyproject.toml` `addopts` includes `--cov-fail-under=<N>`.
2. `python -m pytest` exits 0 and reports coverage above the threshold.
3. Deleting a test function causes `python -m pytest` to exit non-zero.
4. Web coverage threshold is configured in `apps/web/vitest.config.ts` (or equivalent).

**Validate**: `python -m pytest -q && corepack pnpm test`

---

## 153 — Pin and checksum the historical corpus revision used by backtests (Impact: H)

**Files**: `python/tests/test_backtest.py`; `pyproject.toml`; `docs/BUILD_PLAN.md`
(referenced in audit — verify it exists; create if absent)

**Problem**: `test_backtest.py` constructs `EventWindow`, `PlayerPrediction`, and
synthetic outcome maps entirely in-memory with no reference to a real historical
corpus revision. The audit mentions `docs/BUILD_PLAN.md` and a "golden backtest run
that can be replayed" — neither currently exists. There is no pinned corpus revision
hash that would let a contributor reproduce a failing simulation run identically on a
different machine or at a future date.

**Change**:

1. Define a `CORPUS_REVISION` constant (a git SHA or a content hash of the corpus
   source files) in `python/tests/test_backtest.py` or in a shared
   `python/tests/conftest.py`. Tests that depend on the corpus must assert the loaded
   revision matches this constant, failing visibly if it drifts.
2. Create `docs/BUILD_PLAN.md` (or extend it if it already exists) with a
   reproducible backtest recipe: the exact command to run, the expected output metrics
   (Spearman correlation range, absolute error range), and the corpus revision hash.
3. Add a `test_backtest_golden_metrics` test that loads the pinned corpus, runs
   `run_backtest`, and asserts the resulting `MethodScore` metrics fall within a
   documented tolerance band. Use `PYTHONHASHSEED=0` and a frozen clock (`clock`
   parameter) for determinism.

**Constraints**: The golden test may be slow; mark it `@pytest.mark.slow` (see item 165) and exclude it from the default `pytest` run with `-m "not slow"`. The corpus
data must not be committed to the repository if it is large; reference it by hash and
document where to obtain it.

**Tests first**: Write `test_backtest_golden_metrics` first with a known-wrong
expected metric; confirm it fails. Run the real backtest to find the correct values;
update the test; confirm it passes.

**Done when**:

1. `CORPUS_REVISION` is defined and checked in the backtest test module.
2. `test_backtest_golden_metrics` exists, is marked `@pytest.mark.slow`, and passes
   with `PYTHONHASHSEED=0`.
3. `docs/BUILD_PLAN.md` documents the reproducible recipe.
4. Standard `python -m pytest` (without `-m slow`) exits 0 without running the golden test.

**Validate**: `PYTHONHASHSEED=0 python -m pytest -m slow python/tests/test_backtest.py -q`

---

## 154 — Add property-based tests for statistical invariants (Impact: M)

**Files**: `python/tests/` (new files); `python/fpl_andres/models/minutes.py`,
`python/fpl_andres/models/player_rates.py`,
`python/fpl_andres/backtesting/projector.py`

**Problem**: No Hypothesis-based tests exist anywhere in `python/tests/`. The
modules `models/minutes.py` (Beta-Binomial shrinkage, recency half-life),
`models/player_rates.py` (shrinkage and season carry-forward), and
`backtesting/projector.py` (shrinkage target for thin histories) contain statistical
invariants that are not enumerated as unit tests. The invariants to verify:

- Shrinkage output is bounded between the prior and the observation.
- Recency decay weights are monotonically decreasing with event distance.
- Effective rank (used in optimizer output) lies within `[1, n]` for any `n >= 1`.

**Change**:

1. Add `hypothesis>=6` to the `[project.optional-dependencies] dev` list in
   `pyproject.toml`.
2. Create `python/tests/test_statistical_invariants.py`. Use
   `hypothesis.strategies` to generate random (prior, observation, sample_size,
   half_life) tuples within domain-valid ranges. For each invariant, write a
   `@given`-decorated test that calls the relevant function and asserts the property.
3. Set `@settings(max_examples=200, deriving=...)` and `PYTHONHASHSEED=0` (via the
   session fixture in item 161) for reproducibility.
4. Use `from hypothesis import given, settings, assume` only — no `numpy` strategies
   until `hypothesis[numpy]` is confirmed safe with the CI Python version.

**Constraints**: Hypothesis must be pinned to a specific minor version range to avoid
non-determinism from strategy changes. The `@given` decorator is incompatible with
`@pytest.mark.asyncio`; keep tests synchronous. CI wall time budget: under 60 s for
200 examples per property.

**Tests first**: Write the properties before verifying the production code satisfies
them. A property failure with a small counterexample is the expected first run.

**Done when**:

1. Three `@given` tests exist covering shrinkage bounds, monotone decay, and effective
   rank.
2. `python -m pytest python/tests/test_statistical_invariants.py -q` passes.
3. `python -m mypy` exits 0 (no `Any` in test helpers).

**Validate**: `python -m pytest python/tests/test_statistical_invariants.py -q`

---

## 155 — Add property-based tests for `ingest/normalise.py` and `crosswalk/resolve.py` (Impact: M)

**Files**: `python/tests/` (new file); `python/fpl_andres/ingest/normalise.py`;
`python/fpl_andres/crosswalk/resolve.py`

**Problem**: `test_historical_ingest.py` and `test_crosswalk.py` exist but contain
only example-based tests. Neither exercises boundary and tolerance behaviour
systematically. `normalise.py` processes raw historical CSV rows into typed records
and should be robust to: missing optional fields, numeric fields supplied as strings,
and out-of-range event numbers. `resolve.py` matches player names across sources
using fuzzy matching and should maintain: identity (a name resolves to itself if
present), symmetry (if A resolves to B, no other A' resolves to B), and non-empty
results for any name that is in the crosswalk.

**Change**:

1. Add `hypothesis` to dev dependencies (see item 154).
2. Create `python/tests/test_ingest_normalise_properties.py` with `@given` tests for:
   - Any dict with required fields present normalises without raising.
   - Optional fields absent produce `None`, not a default sentinel.
   - Event numbers outside `[1, 38]` raise `ValueError` (not a silent truncation).
3. Create `python/tests/test_crosswalk_resolve_properties.py` with `@given` tests for:
   - Identity: any name in `crosswalk.names` resolves to a non-empty result.
   - No hallucination: the resolved code is always drawn from the known corpus.

**Constraints**: Strategy generation must use only `hypothesis.strategies` (text,
integers, dictionaries with fixed keys). `PYTHONHASHSEED=0` must be set for
reproducibility (item 161). Tests must be purely synchronous.

**Tests first**: Write properties first; the first run is expected to surface at least
one boundary case that the production code does not handle gracefully.

**Done when**:

1. Both new test files exist with at least two `@given` tests each.
2. `python -m pytest python/tests/test_ingest_normalise_properties.py python/tests/test_crosswalk_resolve_properties.py -q` passes.
3. `python -m mypy` exits 0.

**Validate**: `python -m pytest python/tests/test_ingest_normalise_properties.py python/tests/test_crosswalk_resolve_properties.py -q`

---

## 156 — Add shared fixture builders to eliminate inline construction across `python/tests/` (Impact: M)

**Files**: `python/tests/` (new `conftest.py` or `python/tests/builders.py`); all
existing test files that inline-construct player, observation, or rules objects

**Problem**: Across `python/tests/`, player, observation, and rules objects are
constructed inline in each test. A grep for `PlayerPrediction(`, `EventWindow(`, and
similar constructors reveals repetition in at least `test_backtest.py`,
`test_expected_points.py`, `test_simulation.py`, and `test_walk_forward.py`. When a
model field is renamed or a required field is added, every inline construction site
must be updated, and the update is likely to be incomplete. There is currently only
one `@pytest.fixture` (scope `"module"`) in `test_expected_points.py`.

**Change**:

1. Create `python/tests/builders.py` (not a pytest file, so it can be imported
   without triggering collection) with factory functions: `make_player(...)`,
   `make_observation(...)`, `make_rules(...)`, `make_event_window(...)`, and
   `make_player_prediction(...)`. Each function should have keyword-only parameters
   with sensible defaults, returning the fully constructed model object.
2. Create or extend `python/tests/conftest.py` to expose these builders as
   session-scoped `@pytest.fixture` functions where shared state is appropriate (e.g.
   a default `Rules` object that most tests use unchanged).
3. Update at least `test_backtest.py` and `test_simulation.py` to import and use the
   builders, removing their inline construction.

**Constraints**: Builders must not introduce `Any` return types — all factory
functions must be fully annotated. `python -m mypy` must remain clean. No production
code changes.

**Tests first**: No new test cases needed; the goal is reducing duplication. Verify
by running the full suite before and after to confirm identical results.

**Done when**:

1. `python/tests/builders.py` exists with at least five factory functions.
2. `test_backtest.py` and `test_simulation.py` use the builders instead of inline
   construction.
3. `python -m pytest python/tests/ -q` passes with identical test count to before.
4. `python -m mypy` exits 0.

**Validate**: `python -m pytest python/tests/ -q`

---

## 157 — Add fixture files for upstream error responses so retry/backoff is data-driven (Impact: M)

**Files**: `python/tests/fixtures/fpl/` (currently contains
`bootstrap_rules_2026_27.json` and `entry_preseason.json`);
`python/tests/test_fpl_adapter.py`

**Problem**: Retry and backoff logic in `adapters/fpl.py` is tested with inline
`httpx.Response(503, ...)` objects constructed in test functions. The error response
body format (`{"detail": "temporarily unavailable"}`) and the `Retry-After` header
value are hardcoded in the test, not in a fixture file. This means the test does not
verify that the adapter correctly handles the _actual_ FPL API error format, and it
cannot be reused for other adapter methods without copy-pasting. Response shapes for
429, 500, 503, and partial-body cases should live as fixture JSON files so they can
be updated if the upstream format changes.

**Change**:

1. Create fixture files in `python/tests/fixtures/fpl/`:
   - `error_429_rate_limited.json`: `{"detail": "Too many requests."}` with a
     `Retry-After` header value of `"30"`.
   - `error_500_server_error.json`: `{"detail": "Internal server error."}`.
   - `error_503_unavailable.json`: `{"detail": "temporarily unavailable."}`.
2. Add a metadata wrapper to each fixture (following the format of
   `bootstrap_rules_2026_27.json`: `captured_at`, `source_url`) so the fixture is
   attributable and dateable per item 160.
3. Update `test_fpl_adapter.py` to load the 503 body from
   `error_503_unavailable.json` rather than constructing it inline.
4. Add new parameterised tests that iterate over all three error fixtures and assert
   the correct retry behaviour for each status code.

**Constraints**: Fixture files must not contain real credentials or personally
identifiable information. Tests remain fully offline (no network). `PYTHONHASHSEED=0`
must be set.

**Tests first**: Write the parameterised test before creating the fixture files;
confirm it fails with a missing-fixture `FileNotFoundError`. Create the fixtures;
confirm the test passes.

**Done when**:

1. Three error-response fixture files exist in `python/tests/fixtures/fpl/`.
2. `test_fpl_adapter.py` parameterises at least one test over the fixture files.
3. `python -m pytest python/tests/test_fpl_adapter.py -q` passes.

**Validate**: `python -m pytest python/tests/test_fpl_adapter.py -q`

---

## 158 — Add round-trip serialisation tests between Pydantic and Zod contracts using real payloads (Impact: M)

**Files**: `python/tests/test_contract_parity.py`; `packages/contracts/fixtures/`
(all five case files); `packages/contracts/src/fpl.test.ts`

**Problem**: `test_contract_parity.py` validates that Python Pydantic models accept or
reject the same shared JSON fixtures as Zod schemas do. This is correct for
_structural_ parity. However, it does not round-trip _real_ upstream payloads: a real
FPL bootstrap response parsed by the Python adapter and then re-serialised as JSON
should produce a document that the Zod schema also accepts, and vice versa. Currently
the fixtures (`fpl-entry-cases.json` etc.) are hand-crafted; a field added to the
real API but not to the fixture goes undetected.

**Change**:

1. Extend `test_contract_parity.py` with a `test_bootstrap_entry_round_trips_through_pydantic_and_json`
   test. Load `python/tests/fixtures/fpl/entry_preseason.json`, run `normalize_entry`
   to get an `FplEntry`, serialise it with `model_dump(by_alias=True, mode="json")`,
   and assert the result validates against the shared `fpl-entry-cases.json` valid
   schema (or directly against `FplEntry.model_validate`).
2. In `packages/contracts/src/fpl.test.ts`, add a test that imports
   `python/tests/fixtures/fpl/entry_preseason.json` as a JSON import and runs it
   through the Zod `fplEntrySchema`, asserting it parses without error. This closes
   the cross-language loop.
3. The `bootstrap_rules_2026_27.json` fixture (which contains `captured_at`,
   `source_url`, and `payload`) should be used to verify `SourceSnapshot` round-trips
   correctly.

**Constraints**: The TypeScript test must import JSON without `any` assertions
(`resolveJsonModule: true` should already be in `tsconfig.json`). `python -m mypy`
and `corepack pnpm typecheck` must pass. `corepack pnpm contracts:check` must pass
unchanged.

**Tests first**: Write the Python round-trip test first; it may initially fail if
`normalize_entry` produces a field that the shared case file does not cover.

**Done when**:

1. `test_contract_parity.py` contains at least one round-trip test using a real
   fixture file.
2. `packages/contracts/src/fpl.test.ts` contains a Zod parse test for the same fixture.
3. Both `python -m pytest python/tests/test_contract_parity.py -q` and
   `corepack pnpm test` exit 0.

**Validate**: `python -m pytest python/tests/test_contract_parity.py -q && corepack pnpm test`

---

## 159 — Add tests for CLI argument validation across `cli/` (Impact: M)

**Files**: `python/tests/` (new `python/tests/test_cli_args.py`);
`python/fpl_andres/cli/sweep_managers.py`,
`python/fpl_andres/cli/publish_projections.py`,
`python/fpl_andres/cli/validate.py`,
`python/fpl_andres/cli/verify_veterans.py`

**Problem**: No test file covers argument validation for the CLI entry points. The
parsers in `sweep_managers.py` accept `--rate` (float), `--concurrency` (int),
`--start`/`--until` (int range), `--since-start-year` (int), and `--rank-ceiling`
(int). `validate.py` accepts `--seasons` (comma-separated season strings) and
`--seeds` (comma-separated integers). No parser currently uses `argparse`'s `type=`
validator to reject negative rates, reversed ranges (`--start > --until`), or
malformed season strings (e.g. `"2024_25"` instead of `"2024-25"`). A misspelled CLI
invocation in a cron job silently uses defaults rather than failing.

**Change**:

1. Add argument validation in each parser: `--rate` must be positive;
   `--start` must be less than `--until`; season strings must match the pattern
   `YYYY-YY`; seeds must be positive integers. Use `argparse`'s `type=` callable or
   a `post_parse` validator.
2. Create `python/tests/test_cli_args.py` with `pytest.mark.parametrize` tests
   that call `build_parser().parse_args([...])` for each CLI module and assert that
   invalid arguments raise `SystemExit` (argparse exits on validation failure) with
   a non-zero code, while valid arguments produce the expected `Namespace`.

**Constraints**: Tests must not invoke the CLI `main()` function (which requires
live credentials). Only `build_parser()` and `parse_args()` are called. No network
calls. `python -m mypy` must remain clean.

**Tests first**: Write the `test_cli_args.py` parametrised tests first. They will
initially pass (because the parsers do not yet validate), showing that the tests
are wrong — then add the validation, and re-run to confirm the tests now correctly
reject invalid inputs.

**Done when**:

1. `test_cli_args.py` contains at least 8 parametrised cases covering valid and
   invalid inputs for `sweep_managers`, `validate`, and `verify_veterans` parsers.
2. Negative `--rate`, reversed ranges, and malformed season strings all cause
   `SystemExit`.
3. `python -m pytest python/tests/test_cli_args.py -q` passes.
4. `python -m mypy` exits 0.

**Validate**: `python -m pytest python/tests/test_cli_args.py -q`

---

## 160 — Version fixture files in `python/tests/fixtures/` with source, capture date, and schema version (Impact: M)

**Files**: `python/tests/fixtures/fpl/bootstrap_rules_2026_27.json` (has
`captured_at` and `source_url` but no schema version);
`python/tests/fixtures/fpl/entry_preseason.json` (raw dict, no metadata);
`python/tests/fixtures/statsbomb/lineups_sample.json` (no metadata)

**Problem**: `bootstrap_rules_2026_27.json` already records `captured_at` and
`source_url` — a good start, but it lacks a `schema_version` field that would make a
stale fixture immediately visible when the upstream API changes its structure.
`entry_preseason.json` is a bare dict with no provenance metadata at all.
`lineups_sample.json` has no attribution. Without a schema version, a fixture that
was correct for FPL API v1 but is invalid for v2 cannot be identified without
manually comparing it to the live API.

**Change**:

1. Define a fixture envelope schema: every fixture JSON file must have a top-level
   object with fields `captured_at` (ISO 8601), `source_url` (string), and
   `schema_version` (a string matching the `@fpl-andres/contracts` version, e.g.
   `"0.5.1"`). The `payload` field holds the actual data.
2. Wrap `entry_preseason.json` in this envelope: add `captured_at`, `source_url`
   (the FPL entry endpoint URL), and `schema_version`. Update references in
   `test_fpl_adapter.py` (`ENTRY_FIXTURE_PATH`) to read `fixture["payload"]` instead
   of the bare dict.
3. Wrap `lineups_sample.json` similarly, with the StatsBomb open-data URL as
   `source_url`.
4. Add a test in `python/tests/test_fixtures.py` (already exists) or a new
   `test_fixture_metadata.py` that reads every file in `python/tests/fixtures/`
   recursively and asserts the envelope fields are present and non-empty.

**Constraints**: All existing tests that read fixture files must be updated to access
`fixture["payload"]` rather than the top-level dict. `python -m mypy` must remain
clean. No production code changes.

**Tests first**: Write `test_fixture_metadata.py` first; it will fail for
`entry_preseason.json` and `lineups_sample.json`. Add the envelopes; confirm the test
passes.

**Done when**:

1. All three fixture files have `captured_at`, `source_url`, and `schema_version`.
2. `test_fixture_metadata.py` passes for every file in `python/tests/fixtures/`.
3. Existing tests that read these fixtures are updated and pass.

**Validate**: `python -m pytest python/tests/test_fixtures.py python/tests/test_fpl_adapter.py -q`

---

## 161 — Set `PYTHONHASHSEED` and a session-level seed fixture in CI (Impact: M)

**Files**: `.github/workflows/ci.yml`; `python/tests/conftest.py` (create if absent);
`pyproject.toml`

**Problem**: `PYTHONHASHSEED` is not set in `.github/workflows/ci.yml` or
`pyproject.toml`. Python's default hash randomisation means that any test relying on
dict iteration order, set ordering, or string-hash-dependent sampling is
non-deterministic across runs. No session-level seed fixture exists to freeze
randomised construction in tests that use `random`, `numpy.random`, or simulation
seeds. A test that passes 99 % of the time can be silently flaky without PYTHONHASHSEED
being fixed.

**Change**:

1. In `.github/workflows/ci.yml`, add `env: PYTHONHASHSEED: "0"` to the `validate`
   job (or at the step level for the `python -m pytest` step). This ensures every CI
   run uses the same hash seed.
2. Create (or extend) `python/tests/conftest.py` with a session-scoped fixture named
   `_fixed_seed` that calls `random.seed(0)` and (if `numpy` is available)
   `numpy.random.seed(0)` at session start. Apply it automatically via
   `autouse=True`.
3. In `pyproject.toml` `[tool.pytest.ini_options]`, add the env var via `env =
["PYTHONHASHSEED=0"]` if `pytest-env` is added, or document the CI env var
   approach as the canonical method.

**Constraints**: `PYTHONHASHSEED=0` must not break any existing test. Tests that rely
on genuine randomness (e.g. Monte Carlo simulation tests with large `n`) should use
the seeded `random` module via the fixture rather than the system default.
`python -m mypy` must remain clean for `conftest.py`.

**Tests first**: Run the full suite with `PYTHONHASHSEED=0 python -m pytest python/tests/ -q`
before making any changes. If any test fails, that test has a latent ordering
dependency and must be fixed first.

**Done when**:

1. `PYTHONHASHSEED: "0"` appears in `.github/workflows/ci.yml`.
2. `conftest.py` contains the `_fixed_seed` autouse fixture.
3. `PYTHONHASHSEED=0 python -m pytest python/tests/ -q` exits 0.
4. The same suite exits 0 with `PYTHONHASHSEED=1` (confirming no hidden ordering
   dependency was introduced).

**Validate**: `PYTHONHASHSEED=0 python -m pytest python/tests/ -q`

---

## 162 — Document the seeding strategy (Impact: M)

**Files**: `docs/` (create `docs/SEEDING.md` or extend `docs/BUILD_PLAN.md`);
`python/tests/conftest.py`; `pyproject.toml`

**Problem**: There is no written explanation of which seeds are used, why those values
were chosen, how to reproduce a specific failing simulation or bootstrap run, or what
a developer should do when they see a random test failure. The `validate.py` CLI
accepts `--seeds 1,2,3,4,5` (line 54), implying replicated simulation runs, but the
rationale for this default is undocumented.

**Change**:

1. Create `docs/SEEDING.md` (or a `## Seeding` section in `docs/BUILD_PLAN.md`)
   that documents:
   - `PYTHONHASHSEED=0`: set in CI; reason (hash-table order determinism).
   - `random.seed(0)` in `conftest.py` `_fixed_seed` fixture: reason (all
     simulation and sampling calls in tests use a reproducible sequence).
   - The `--seeds 1,2,3,4,5` default in `validate.py`: reason (five independent
     replications to estimate variance; how to run a single seed for debugging).
   - How to reproduce a failing run locally: `PYTHONHASHSEED=0 python -m pytest
python/tests/<failing_test>.py -q -s`.
2. Add a one-line docstring to the `_fixed_seed` conftest fixture referencing the
   documentation file.

**Constraints**: Documentation only — no production code changes beyond the
conftest docstring. The document must be accurate with respect to the seeds
actually used (verify against `conftest.py` and `.github/workflows/ci.yml` after
item 161 is implemented).

**Tests first**: Not applicable for documentation. However, the document should be
reviewed by running the described reproduction command and confirming it produces the
expected output.

**Done when**:

1. `docs/SEEDING.md` (or equivalent section) exists and covers PYTHONHASHSEED,
   the conftest fixture, the `--seeds` CLI parameter, and the local reproduction recipe.
2. The `_fixed_seed` conftest fixture has a docstring referencing the doc.
3. The commands in the documentation execute without error.

**Validate**: `cat docs/SEEDING.md` (visual review); `PYTHONHASHSEED=0 python -m pytest python/tests/ -q`

---

## 163 — Add golden-file tests for published artifacts (Impact: M)

**Files**: `python/tests/` (new `python/tests/test_artifact_golden.py`);
`apps/web/src/data/projections.json`, `apps/web/src/data/opening-squad.json`,
`apps/web/src/data/validation.json`; `python/fpl_andres/cli/publish_projections.py`
(line 30), `publish_opening_squad.py` (line 38), `validate.py` (line 30)

**Problem**: No test compares the structure of the three published JSON artifacts
against a recorded golden copy. A format change (field rename, added key, dropped
key) introduced by a refactor of the CLI publishing scripts goes undetected until
it breaks the frontend. The artifact schemas are consumed by TypeScript components
in `apps/web/src/` and by the Pydantic contracts layer, but neither enforces the
complete top-level JSON structure.

**Change**:

1. Create `python/tests/golden/projections_structure.json`,
   `opening_squad_structure.json`, and `validation_structure.json`. These files
   record only the _keys_ and _types_ of the top-level and one level of nested
   structure (not actual data values), so they remain stable across data updates.
2. Create `python/tests/test_artifact_golden.py` with three tests — one per artifact.
   Each test reads the committed artifact from `apps/web/src/data/`, asserts the
   top-level keys match the golden structure file, and asserts the type of each
   value (string, list, object) is unchanged.
3. If an artifact is absent (the repository is checked out without running the CLIs),
   the test is skipped with `pytest.skip("artifact not present")`, not failed.

**Constraints**: Tests must not run the CLIs (which require live FPL credentials).
They inspect the _existing committed_ artifact files. `PYTHONHASHSEED=0` must be set.
If the artifact format changes deliberately, the golden file is updated as part of the
same commit.

**Tests first**: Write the test before creating the golden files; the first run will
fail with a `FileNotFoundError`. Create the golden files from the current committed
artifacts; confirm the test passes.

**Done when**:

1. Three golden structure files exist in `python/tests/golden/`.
2. `test_artifact_golden.py` passes for all three artifacts (or skips if absent).
3. Renaming a top-level key in the artifact JSON causes the test to fail.
4. `python -m pytest python/tests/test_artifact_golden.py -q` exits 0.

**Validate**: `python -m pytest python/tests/test_artifact_golden.py -q`

---

## 164 — Add web tests for override storage edge cases (Impact: M)

**Files**: `apps/web/e2e/team-entry.spec.ts`; `apps/web/src/components/TeamStateCorrections.tsx`
(line 160, 187, 575); `apps/web/src/state/team-analysis.ts` (line 138)

**Problem**: `team-entry.spec.ts` does not cover three localStorage edge cases for
team-state overrides:

1. **Quota-exceeded storage**: `localStorage.setItem` throws `QuotaExceededError`;
   the comment in `team-analysis.ts` at line 138 says "Storage failure … does not
   invalidate" — but this is not tested.
2. **Corrupted cache entry**: `localStorage.getItem` returns a string that is not
   valid JSON; the component should fall back to the server state gracefully.
3. **Cache entry for a different entry ID**: a stored override for entry `212279` must
   not appear when the user switches to entry `999999`.

**Change**:

1. In `team-entry.spec.ts`, add three tests using `page.addInitScript` (or
   `page.evaluate`) to inject a broken `localStorage` stub before the page loads:
   - For quota: override `localStorage.setItem` to throw `DOMException` with name
     `"QuotaExceededError"`; assert the page renders the server state without crashing.
   - For corrupted entry: pre-populate `localStorage` with the override key set to
     `"not-json"`; assert the page renders without an unhandled error overlay.
   - For different entry: pre-populate `localStorage` with a valid override for entry
     `212279`; navigate to entry `999999`; assert the override UI does not show the
     `212279` override.
2. Use the existing `mockTeamResponse` helper and `publicTeamState()` factory for
   the mocked API responses.

**Constraints**: Tests must work with the `desktop-chromium` and `mobile-chromium`
Playwright projects. Must not modify production source files unless the tested
behaviour is genuinely absent (fix the bug, then the test).
`corepack pnpm test:e2e` must exit 0.

**Tests first**: Write the three tests first. The quota and corrupted tests may
immediately pass if the production code already handles them gracefully (the
`team-analysis.ts` comment at line 138 suggests it does). The cross-entry test may
reveal a real bug.

**Done when**:

1. Three new Playwright tests exist covering quota, corrupt, and cross-entry override
   edge cases.
2. `corepack pnpm test:e2e` exits 0.
3. Each test has a screenshot assertion (`path: testInfo.outputPath(...)`) on failure.

**Validate**: `corepack pnpm test:e2e`

---

## 165 — Mark slow tests and add per-test timeouts (Impact: L)

**Files**: `pyproject.toml` (`[tool.pytest.ini_options]`); `python/tests/` (all files
that contain slow tests); `python/tests/conftest.py`

**Problem**: `pyproject.toml` `addopts` includes `--strict-markers`, which means any
`@pytest.mark.slow` usage would fail immediately — the marker is not yet registered.
No test is currently marked as slow. No per-test timeout is configured (no
`pytest-timeout` dependency). A future slow integration test or network-bound
simulation can cause CI to hang until the 20-minute job timeout is hit, with no
fast failure or diagnostic.

**Change**:

1. Register the `slow` marker in `pyproject.toml`:
   ```
   [tool.pytest.ini_options]
   markers = ["slow: marks tests as slow (deselect with '-m not slow')"]
   ```
2. Add `pytest-timeout>=2` to the `[project.optional-dependencies] dev` list in
   `pyproject.toml`. Set a default timeout: `timeout = 30` in
   `[tool.pytest.ini_options]` (30 seconds per test; slow tests may override with
   `@pytest.mark.timeout(300)`).
3. Apply `@pytest.mark.slow` to any test that is expected to take more than 10 s
   (e.g. `test_backtest_golden_metrics` from item 153, any future corpus-loading test).
4. In CI (`.github/workflows/ci.yml`), add `-m "not slow"` to the `python -m pytest`
   invocation inside `pnpm check` to exclude slow tests from the standard gate.
   Add a separate optional/weekly CI step that runs `python -m pytest -m slow`.

**Constraints**: The default pytest run (`python -m pytest`) must complete in under
5 minutes in CI. The `--strict-markers` flag in `addopts` must be preserved.

**Tests first**: This is infrastructure; the proof is that adding a test with
`@pytest.mark.slow` and a body of `time.sleep(35)` causes the default run to skip it
and the slow run to execute (and timeout at 30 s unless overridden).

**Done when**:

1. `markers = [...]` includes `"slow"` in `pyproject.toml`.
2. `pytest-timeout` is in the dev dependencies with a `timeout = 30` default.
3. `python -m pytest -m "not slow" -q` excludes all `@pytest.mark.slow` tests.
4. `python -m pytest -m slow -q` runs only those tests.

**Validate**: `python -m pytest -m "not slow" -q`

---

## 166 — Trial mutation testing on the rules and scoring modules (Impact: L)

**Files**: `python/fpl_andres/models/` (target modules); `pyproject.toml`;
`python/tests/` (test suite)

**Problem**: The test suite has no mutation-testing pass. It is unknown whether the
tests actually catch regressions in the scoring and rules logic, or merely achieve
statement coverage without exercising branch conditions. The modules most deserving
of mutation scrutiny are `models/expected_points.py`, `models/minutes.py`,
`models/player_rates.py`, `models/deployment.py`, and the backtesting scorer
(`backtesting/score.py`). Mutation testing with `mutmut` or `cosmic-ray` would
surface tests that pass even when a `<` becomes `<=` or a `+` becomes `-`.

**Change**:

1. Add `mutmut>=2` to the `[project.optional-dependencies] dev` list (or a separate
   `[project.optional-dependencies] mutation` group) in `pyproject.toml`.
2. Create a `mutmut` config section in `pyproject.toml` (or `setup.cfg`) that limits
   mutation to `python/fpl_andres/models/` and `python/fpl_andres/backtesting/score.py`,
   and uses `python -m pytest python/tests/ -x -q` as the test runner.
3. Run `mutmut run` once and capture the mutation score in `docs/MUTATION_REPORT.md`.
   Document any surviving mutants (mutations that pass the test suite) as known gaps
   and file them as follow-up test improvements.
4. This is a _trial_ (item says "trial mutation testing"); the goal is a baseline
   score, not 100 % kill rate.

**Constraints**: `mutmut run` is slow (O(minutes) per module); run it in a separate
CI job triggered manually or on a weekly schedule, not in the standard `pnpm check`
gate. `python -m mypy` must remain clean.

**Tests first**: Not applicable — mutation testing _assesses_ the existing tests
rather than adding new ones. The deliverable is `docs/MUTATION_REPORT.md` plus any
new tests added to kill surviving mutants.

**Done when**:

1. `mutmut` is in dev dependencies and `pyproject.toml` contains a scope config.
2. `docs/MUTATION_REPORT.md` records the baseline mutation score and lists surviving
   mutants.
3. At least two new tests are added to kill surviving mutants found in the trial.

**Validate**: `python -m mutmut run --paths-to-mutate python/fpl_andres/models/expected_points.py` (then inspect `mutmut results`)

---

## 167 — Track flaky-test history for Playwright journeys and set an explicit retry policy (Impact: L)

**Files**: `apps/web/playwright.config.ts` (line 6: `retries: process.env.CI ? 2 : 0`);
`.github/workflows/ci.yml`

**Problem**: `playwright.config.ts` sets `retries: 2` in CI, which silently masks
flaky tests: a test that fails on the first two attempts and passes on the third is
reported as a pass with no record of the flakiness. There is no historical log of
which tests have been retried across CI runs. The GitHub Actions reporter (`"github"`)
does not aggregate retry history. A test that is flaky 30 % of the time will
consistently consume two retry slots before passing, inflating CI wall time without
any alert.

**Change**:

1. Reduce `retries` to `1` in `playwright.config.ts` to limit the masking window.
   One retry is still sufficient to absorb a single transient network hiccup in CI.
2. Add a `"json"` reporter alongside `"github"` in `playwright.config.ts` when
   `process.env.CI` is set: `reporter: [["github"], ["json", { outputFile: "playwright-report/results.json" }]]`.
   This file contains per-test `retry` counts.
3. In `.github/workflows/ci.yml`, add an `Upload Playwright results` step (after
   `Run browser journeys`) that uploads `playwright-report/results.json` as a CI
   artifact with a 7-day retention period. This creates a historical record.
4. Add a comment in `playwright.config.ts` above `retries` explaining the policy:
   why 1 retry (not 0, not 2) was chosen and what the flaky-test process is.

**Constraints**: CI wall time must not increase (fewer retries means faster total
runtime). The `forbidOnly: Boolean(process.env.CI)` setting must be preserved.
Existing passing tests must continue to pass.

**Tests first**: Not applicable — this is infrastructure. Verify by running
`corepack pnpm test:e2e` locally and confirming all tests pass without retries
before reducing the retry count in CI.

**Done when**:

1. `retries` is `1` in `playwright.config.ts`.
2. JSON reporter is configured and writes `playwright-report/results.json` in CI.
3. `.github/workflows/ci.yml` uploads the results file as an artifact.
4. A comment in `playwright.config.ts` documents the retry policy.

**Validate**: `corepack pnpm test:e2e` (local, confirming all tests pass on first attempt)
