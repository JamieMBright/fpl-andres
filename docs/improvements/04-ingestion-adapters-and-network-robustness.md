# 4. Ingestion, adapters and network robustness — work orders

Detailed briefs for items 41–57 of the [improvement audit](../../IMPROVEMENTS.md).
Each brief is self-contained: a sub-agent should be able to implement one item
from its brief alone.

Every brief obeys the repository rules: test-first (failing focused test, minimal
code, refactor), never default a missing controlling FPL rule (fail the source
contract visibly), and nothing may exceed `docs/LIMITATIONS.md`.

No timeout, retry count, or delay value may be invented silently: every configurable
limit that does not already exist in the codebase must be sourced from a named
constant or a config argument, documented in the work order, and must raise a
contract error if it is absent or out of range.

---

## 41 — Verify and document the transport-error backoff in `FplClient` (Impact: H)

**Files**: `python/fpl_andres/adapters/fpl.py` (`_request_with_retries` lines 224–255,
`_retry_delay` lines 275–284, constants `MAX_ATTEMPTS`, `MAX_RETRY_AFTER_SECONDS`),
`python/tests/test_fpl_adapter.py`

**Audit claim correction**: The audit states that transport errors lack a "bounded,
capped backoff." In the current code, `_request_with_retries` catches
`httpx.TransportError` and calls `_retry_delay(None, attempt, self._random)`, which
returns `0.5 * 2^attempt * jitter` (lines 282–284). With `MAX_ATTEMPTS = 3`, the retry
loop runs at most twice before re-raising, so the total maximum backoff is approximately
1.5 seconds. The bound IS present via `MAX_ATTEMPTS`. The real gap is that the
transport-error path and the HTTP-error path share `_retry_delay` but the `Retry-After`
cap (`MAX_RETRY_AFTER_SECONDS = 30.0`, line 27) applies only when the header is present.
There is no separately named cap for the pure exponential branch, making it hard to
audit the worst-case delay without reading the math.

**Problem**: The retry contract is implicit and untested at the per-attempt delay
level. A future change that raises `MAX_ATTEMPTS` to, say, 10 would silently extend
the total transport-error wait to `0.5 + 1.0 + 2.0 + 4.0 + … = 255 s` — far longer
than acceptable for a scheduled workflow. Additionally, the test
`test_bootstrap_fetch_retries_transient_status_with_bounded_backoff` (line 73) exists
for HTTP errors but there is no test that exercises the transport-error retry path
with a mock `Sleep` and asserts bounded per-attempt delays.

**Change**:

1. Add a named constant `MAX_TRANSPORT_RETRY_DELAY_SECONDS` (e.g., `4.0`) alongside
   the existing constants at the top of `adapters/fpl.py`.
2. In `_retry_delay`, when `retry_after` is `None`, cap the exponential result at
   `MAX_TRANSPORT_RETRY_DELAY_SECONDS` rather than returning it uncapped.
3. Update the docstring of `_retry_delay` to name both cap constants and explain when
   each applies.

**Constraints**: `MAX_ATTEMPTS`, `MAX_RETRY_AFTER_SECONDS`, and `RETRYABLE_STATUSES`
are existing public constants; do not rename or remove them. `FplContractError` and
`FplPicksUnavailable` must not change. Callers (`cli/ingest_historical.py`,
`cli/verify_veterans.py`) must not require changes.

**Tests first**: in `python/tests/test_fpl_adapter.py`:

- Add `test_transport_error_retries_use_bounded_per_attempt_delay`: use a mock `Sleep`
  (list-recording) and a mock HTTP transport that raises `httpx.TransportError` on the
  first two attempts and succeeds on the third. Assert that every recorded sleep value
  is ≤ `MAX_TRANSPORT_RETRY_DELAY_SECONDS` and that the final response is returned.
- Add `test_transport_error_raises_after_max_attempts`: mock all attempts raising
  `httpx.TransportError`; assert that `httpx.TransportError` is raised (not
  `RuntimeError`) and that exactly `MAX_ATTEMPTS - 1` sleep calls occurred.

**Done when**:

1. `MAX_TRANSPORT_RETRY_DELAY_SECONDS` is a named, importable constant.
2. Each transport-error sleep is ≤ `MAX_TRANSPORT_RETRY_DELAY_SECONDS`.
3. Both new tests pass.
4. `python -m pytest python/tests/test_fpl_adapter.py -q` is green.

**Validate**: `python -m pytest python/tests/test_fpl_adapter.py -q`

---

## 42 — Add an instance-level circuit breaker to `FplClient` (Impact: H)

**Files**: `python/fpl_andres/adapters/fpl.py` (`FplClient`, `_request_with_retries`
lines 224–255), `python/tests/test_fpl_adapter.py`

**Problem**: Within a single `_request_with_retries` call, the loop stops after
`MAX_ATTEMPTS` (3). But `FplClient` has no cross-call state. A sweeping workflow that
calls `fetch_entry_history` in a loop for 2 million entries will retry each one
independently; if the endpoint is returning 503 for all requests, the client hammers it
in blocks of 3 retries each rather than stopping the sweep. The `sweep_managers.py`
module has its own refusal counter (`REFUSAL_LIMIT = 25`) but that code does not use
`FplClient`. Any workflow built on `FplClient` has no equivalent guard.

**Change**:

1. Add two optional constructor parameters to `FplClient.__init__`: `circuit_break_after:
int = 5` (number of consecutive 5xx/transport failures across calls) and
   `circuit_broken_error: type[Exception] = FplContractError` (the exception to raise).
2. Add a private `_consecutive_failures: int` counter that increments on each 5xx or
   transport error and resets on any successful 2xx response in `_request_with_retries`.
3. At the top of `_request_with_retries`, if `_consecutive_failures >= circuit_break_after`,
   raise `FplContractError("FPL circuit breaker open after N consecutive failures")`
   before making any network request.
4. `circuit_break_after` must be ≥ 1; raise `ValueError` in `__init__` if it is not.
   Do not invent a default silently — document it in the docstring.

**Constraints**: `FplContractError` is the existing typed error for "FPL responded
with a shape unsafe for downstream use" — reusing it for circuit-breaker trips is
acceptable only if the message clearly identifies the cause. `MAX_ATTEMPTS` must not
change. The `_consecutive_failures` counter must be reset on success, not merely
decremented. `cli/verify_veterans.py` constructs `FplClient` with only `http` and
`clock`; the new parameters must be optional with documented defaults.

**Tests first**: in `python/tests/test_fpl_adapter.py`:

- Add `test_circuit_breaker_opens_after_configured_consecutive_failures`: construct
  `FplClient(circuit_break_after=2, …)`, mock responses to always return 503, assert
  that after 2 failed calls (each exhausting `MAX_ATTEMPTS` retries) the third call
  raises `FplContractError` without making any network request.
- Add `test_circuit_breaker_resets_on_success`: after 1 failure, mock a success,
  then another failure; assert the breaker does not open (counter was reset).
- Add `test_circuit_break_after_must_be_positive`: assert `ValueError` when
  `circuit_break_after=0`.

**Done when**:

1. `FplClient` raises `FplContractError` on the first call after `circuit_break_after`
   consecutive all-attempt failures.
2. The counter resets on any 2xx response.
3. All three new tests pass; existing adapter tests pass unchanged.
4. `python -m pytest python/tests/test_fpl_adapter.py -q` is green.

**Validate**: `python -m pytest python/tests/test_fpl_adapter.py -q`

---

## 43 — Replace bare `except Exception` with typed handling in `cli/ingest_historical.py` (Impact: H)

**Files**: `python/fpl_andres/cli/ingest_historical.py` (`main` function,
`try…except Exception` block lines 158–178),
`python/fpl_andres/ingest/historical.py` (`ArchiveFetchError`, `ArchiveFileNotPublished`),
`python/fpl_andres/ingest/normalise.py` (`ColumnMappingError`),
`python/fpl_andres/persistence/supabase.py` (`SupabaseWriteError`),
`python/tests/test_historical_ingest.py`

**Problem**: The `try` block at line 158 wraps `ingest.ingest_season(…)` and
`run.record_rows(…)` in a bare `except Exception as error:` (line 176). Any of the
following error types can reach this handler: `ArchiveFetchError` (transport or
HTTP), `ArchiveFileNotPublished` (missing file — which for non-gameweek files is
fatal, not normal), `ColumnMappingError` (schema drift), `SupabaseWriteError`
(persistence failure), `httpx.HTTPError` (network), or `ValidationError` (Pydantic
contract). All are formatted identically with `{type(error).__name__}: {error}` and
logged as a plain failure, making it impossible to distinguish a transient network
hiccup from a permanent schema break or a misconfigured secret.

**Change**:

1. Replace the bare `except Exception` with an ordered sequence of typed handlers:
   - `except ColumnMappingError` → log `"SCHEMA: {error}"` and append to `failures`
     with a `"schema"` prefix; this is permanent and warrants aborting the season.
   - `except ArchiveFileNotPublished` → log `"MISSING: {error}"`; this is fatal for
     teams/fixtures files but normal for gameweeks (already handled inside
     `ingest_season`); here it means a top-level file is absent, so treat it as a
     failure.
   - `except (ArchiveFetchError, httpx.HTTPError)` → log `"NETWORK: {error}"`; retry
     semantics are handled inside `ArchiveFetcher`; at this level it means all retries
     were exhausted.
   - `except SupabaseWriteError` → log `"PERSISTENCE: {error}"`.
   - `except Exception` → log `"UNEXPECTED: {type(error).__name__}: {error}"` as a
     catch-all for anything not classified above; the `return 1` behaviour does not
     change.
2. Keep the `failures` list structure unchanged so the summary at lines 183–188
   needs no modification.
3. Import `httpx` explicitly in `cli/ingest_historical.py` (it is already imported
   at line 19).

**Constraints**: The `open_run` context manager (line 147) and `SupabaseRestClient`
context manager (line 141) must still be exited cleanly on any exception — the
`with` blocks already guarantee this. Do not add retry logic here; that belongs in
the adapter (items 41, 60). The `failures` list schema (season, reason string) must
not change.

**Tests first**: in `python/tests/test_historical_ingest.py`:

- Add `test_schema_error_is_classified_and_continues_to_next_season`: mock
  `HistoricalIngest.ingest_season` to raise `ColumnMappingError("bad column")` for
  the first season; assert the second season is still attempted and the exit code
  is 1.
- Add `test_network_error_is_classified_and_continues`: mock to raise
  `httpx.ConnectError("refused")` (which is an `httpx.HTTPError` subclass); assert
  the failure reason string starts with `"NETWORK:"`.

**Done when**:

1. `ColumnMappingError`, `ArchiveFileNotPublished`, `ArchiveFetchError`,
   `httpx.HTTPError`, and `SupabaseWriteError` each produce a distinctly prefixed
   log line.
2. All existing `test_historical_ingest.py` tests pass unchanged.
3. Both new tests pass.
4. `python -m pytest python/tests/test_historical_ingest.py -q` is green.

**Validate**: `python -m pytest python/tests/test_historical_ingest.py -q`

---

## 44 — Wrap numeric conversions in `ingest/normalise.py` with `ColumnMappingError` (Impact: H)

**Files**: `python/fpl_andres/ingest/normalise.py` (`_int` lines 113–117, `_float`
lines 127–130, `_required_int` lines 120–124), `python/tests/test_historical_ingest.py`

**Problem**: `_float` returns `float(value)` and `_int` returns `int(float(value))`
without guarding the conversion. If an archive column changes type — for example,
`minutes` arriving as `"N/A"` or `goals_scored` arriving as `"1.5abc"` — Python's
`float()` raises `ValueError` with a generic message like `"could not convert string
to float: 'N/A'"`. This `ValueError` propagates as an undecorated exception out of
`normalise_gameweek_stats` and ultimately reaches the bare `except Exception` handler
in `cli/ingest_historical.py`, where it is misclassified as an unexpected error.
The column name and offending value are not present in the exception message.

**Change**:

1. In `_float`, wrap `float(value)` in a `try/except ValueError` and re-raise as
   `ColumnMappingError(f"column value {value!r} is not a valid float")`. Include the
   value in the message.
2. In `_int`, wrap `int(float(value))` similarly and re-raise as
   `ColumnMappingError(f"column value {value!r} is not a valid integer")`.
3. In `_required_int`, which calls `_int`, its `ColumnMappingError` path already
   names the column; but since `_int` itself does not have the column name, add an
   optional `column: str = ""` parameter to `_int` and `_float` that, if provided,
   is included in the error message for callers that do know the column name.
4. Pass the column name from `_required_int` to `_int` so the error reads
   `"column 'minutes': value '...' is not a valid integer"`.

**Constraints**: `ColumnMappingError` is a subclass of `ValueError` (line 30–31); the
new raises must use exactly that class, not bare `ValueError`. The `_int` and `_float`
helpers are also used by `normalise_teams`, `normalise_players`, and `normalise_fixtures`
— all call sites must benefit from the improved messages without requiring changes.
The `None`-and-empty-string fast paths at the top of `_int` and `_float` must not
change.

**Tests first**: in `python/tests/test_historical_ingest.py`:

- Add `test_non_numeric_minutes_raises_column_mapping_error`: pass a gameweek CSV
  where the `minutes` column contains `"N/A"` and assert `ColumnMappingError` is
  raised with a message that includes the offending value.
- Add `test_non_numeric_float_column_raises_column_mapping_error`: pass a gameweek
  CSV where `expected_goals` contains `"bad"` and assert `ColumnMappingError` is
  raised (not bare `ValueError`).

**Done when**:

1. A non-numeric archive cell raises `ColumnMappingError` (not `ValueError`) from
   `_int` or `_float`.
2. The error message includes the offending value and, where the column name is
   available, the column name.
3. All existing `test_historical_ingest.py` tests pass unchanged.
4. `python -m pytest python/tests/test_historical_ingest.py -q` is green.

**Validate**: `python -m pytest python/tests/test_historical_ingest.py -q`

---

## 45 — Audit handle-leak claims for `verify_veterans.py` and `sweep_managers.py` (Impact: H)

**Files**: `python/fpl_andres/cli/verify_veterans.py` (`_fetch_records` lines 51–67),
`python/fpl_andres/cli/sweep_managers.py` (`run` lines 124–215),
`python/tests/test_manager_sweep.py`, `python/tests/test_veteran_extraction.py`

**Audit claim correction**: The audit states that both files "leak handles on failure."
This premise is stale in the current code:

- `verify_veterans.py` line 55: `async with httpx.AsyncClient() as http:` — the
  `AsyncClient` is managed by a context manager and is closed even if `_fetch_records`
  raises. The `FplClient` does not own the underlying transport; cleanup is the
  `AsyncClient`'s responsibility.
- `sweep_managers.py` line 148: `with RESULTS.open("a", encoding="utf-8") as sink:` —
  the file handle is managed by a context manager and is closed even if
  `asyncio.gather` raises.

**Real gap**: The `RESULTS.open("a", …)` file handle (line 148) is opened inside the
`async with httpx.AsyncClient(…)` block (line 143), which is correct. However, if
`asyncio.gather` at line 159 raises an exception that is not `Refused` or
`KeyboardInterrupt`, it propagates past the `_save_progress` call (line 195), leaving
the last checkpoint stale. The progress is saved after each block (line 195), but any
exception from `asyncio.gather` itself exits the `while` loop before `_save_progress`
is called for that block.

**Change**:

1. Wrap the `asyncio.gather` call and the subsequent result-processing loop (lines
   159–193) in a `try/finally` block; in the `finally` clause, call `_save_progress(progress)`
   so the checkpoint reflects whatever work was completed before the exception.
2. Do not add any other structural change to either file; the handle-cleanup path is
   already correct.
3. Add a comment in both files explicitly noting that handle cleanup is guaranteed by
   the enclosing context manager.

**Constraints**: `_save_progress` must be called at most once per block iteration;
wrapping with `try/finally` must not cause a second save on the non-exception path.
The `Refused` and `KeyboardInterrupt` handlers in `main` (lines 221–226) must still
function correctly.

**Tests first**: in `python/tests/test_manager_sweep.py`:

- Add `test_checkpoint_is_saved_when_gather_raises`: inject a mock `asyncio.gather`
  that raises `RuntimeError` after processing one block; assert that `_save_progress`
  was called with the partial progress before the exception propagates.

**Done when**:

1. `_save_progress` is called in a `finally` clause wrapping `asyncio.gather`.
2. The file handle and `AsyncClient` cleanup paths are each annotated with a comment.
3. The new test passes.
4. `python -m pytest python/tests/test_manager_sweep.py -q` is green.

**Validate**: `python -m pytest python/tests/test_manager_sweep.py -q`

---

## 46 — Source HTTP timeouts from a single config object (Impact: M)

**Files**: `python/fpl_andres/persistence/supabase.py` (`SupabaseRestClient.__init__`
line 77, `timeout: float = 30.0`),
`python/fpl_andres/cli/ingest_historical.py` (`main` line 142,
`httpx.Client(timeout=60.0, …)`),
`python/tests/test_historical_ingest.py`, `python/tests/test_persistence.py`

**Problem**: `SupabaseRestClient` defaults to a 30-second timeout (line 77) while
`cli/ingest_historical.py` constructs its archive `httpx.Client` with a 60-second
timeout (line 142). Neither is wrong in isolation, but the two values are uncoordinated
bare literals. A future change to one is not reflected in the other, and an operator
tuning for slow networks must edit two files. Additionally, `ArchiveFetcher` accepts
the `httpx.Client` from outside, so its effective timeout is set by the CLI rather than
the adapter — this is fine, but should be explicit.

**Change**:

1. Introduce a `NetworkConfig` dataclass (or `NamedTuple`) in
   `python/fpl_andres/adapters/config.py` (new file) with fields:
   `archive_timeout_seconds: float = 60.0` and
   `supabase_timeout_seconds: float = 30.0`. Add range validation:
   each value must be finite and positive, raising `ValueError` otherwise.
2. In `cli/ingest_historical.py`, construct a `NetworkConfig` from CLI arguments
   (or leave the defaults), and pass `config.archive_timeout_seconds` to
   `httpx.Client(timeout=…)` and `config.supabase_timeout_seconds` to
   `SupabaseRestClient(timeout=…)`.
3. `SupabaseRestClient` already accepts `timeout` as a constructor argument (line 77);
   the default may remain `30.0` but a note in the docstring should name
   `NetworkConfig` as the canonical source.
4. Do not add CLI flags for timeouts unless the repository already has a precedent;
   instead, source from environment variables `FPL_ARCHIVE_TIMEOUT` and
   `FPL_SUPABASE_TIMEOUT` if present, falling back to the dataclass defaults.

**Constraints**: Do not change `SupabaseRestClient`'s public constructor signature
(the `timeout` parameter must remain optional). `ArchiveFetcher` must not be modified.
`NetworkConfig` must not import from any module that imports `NetworkConfig` (no
circular dependency).

**Tests first**: in `python/tests/test_historical_ingest.py`:

- Add `test_network_config_validates_positive_timeouts`: assert `ValueError` for
  `archive_timeout_seconds=0` and `supabase_timeout_seconds=-1`.
- Add `test_network_config_reads_from_environment`: mock environment variables
  `FPL_ARCHIVE_TIMEOUT=45` and `FPL_SUPABASE_TIMEOUT=15`; assert `NetworkConfig.from_env()`
  returns those values.

**Done when**:

1. `NetworkConfig` is importable from `fpl_andres.adapters.config`.
2. Both timeout values in `cli/ingest_historical.py` are sourced from `NetworkConfig`.
3. `NetworkConfig` raises `ValueError` for non-positive values.
4. Both new tests pass; existing tests pass unchanged.
5. `python -m pytest python/tests/test_historical_ingest.py python/tests/test_persistence.py -q` is green.

**Validate**: `python -m pytest python/tests/test_historical_ingest.py -q`

---

## 47 — Honour `Retry-After` header in `sweep_managers.py` (Impact: M)

**Files**: `python/fpl_andres/cli/sweep_managers.py` (`_fetch` lines 95–121),
`python/tests/test_manager_sweep.py`

**Audit claim correction**: The audit points to `adapters/fpl.py` as the file lacking
`Retry-After` support. This is stale: `adapters/fpl.py` already parses `Retry-After`
in `_retry_delay` (line 280) and caps it at `MAX_RETRY_AFTER_SECONDS`. The real gap
is `cli/sweep_managers.py`. Its `_fetch` function at line 112 handles 429 responses
with `await asyncio.sleep(min(60.0, 2.0 * len(refusals)))` — a refusal-count heuristic
— rather than reading the `Retry-After` header from the response.

**Problem**: The sleep amount in `_fetch` is derived from `len(refusals)` (a shared
mutable list), not from the server's instruction. If the FPL API sets `Retry-After: 5`,
the sweep either sleeps too long (wasting time) or not long enough (getting refused
again). The `min(60.0, …)` cap is also an unnamed literal.

**Change**:

1. Add a named constant `_MAX_RETRY_AFTER_SWEEP_SECONDS = 60.0` at the top of
   `sweep_managers.py`.
2. In `_fetch`, when `response.status_code == 429 or response.status_code >= 500`,
   read `response.headers.get("Retry-After")` and, if it is a non-empty digit string,
   use `min(float(retry_after), _MAX_RETRY_AFTER_SWEEP_SECONDS)` as the sleep duration.
   If the header is absent or non-numeric, fall back to the existing heuristic
   `min(_MAX_RETRY_AFTER_SWEEP_SECONDS, 2.0 * len(refusals))`.
3. Do not change the `REFUSAL_LIMIT` guard or the `refusals` list mechanism.

**Constraints**: `_fetch` is an inner async function and receives `response` directly;
no import of `FplClient` or `_retry_delay` is needed. The existing `httpx.AsyncClient`
in `run` does not use `FplClient`; keep them separate. The `min(…, _MAX_RETRY_AFTER_SWEEP_SECONDS)`
cap must always apply so a malicious or buggy `Retry-After: 9999` cannot stall the
sweep indefinitely.

**Tests first**: in `python/tests/test_manager_sweep.py`:

- Add `test_fetch_respects_retry_after_header_on_429`: mock an `httpx.AsyncClient`
  that returns a 429 response with `Retry-After: 10`, a recording `asyncio.sleep`,
  and then a 200 on retry; assert the first sleep value is `10.0`.
- Add `test_fetch_caps_retry_after_at_max`: respond with `Retry-After: 3600`; assert
  sleep is capped at `_MAX_RETRY_AFTER_SWEEP_SECONDS`.
- Add `test_fetch_falls_back_to_heuristic_when_header_absent`: respond with 429 and
  no `Retry-After` header; assert sleep equals `min(_MAX_RETRY_AFTER_SWEEP_SECONDS,
2.0 * len(refusals))`.

**Done when**:

1. A `Retry-After` digit string is honoured and capped at
   `_MAX_RETRY_AFTER_SWEEP_SECONDS`.
2. Absent or non-numeric headers fall back to the heuristic.
3. All three new tests pass; existing sweep tests pass unchanged.
4. `python -m pytest python/tests/test_manager_sweep.py -q` is green.

**Validate**: `python -m pytest python/tests/test_manager_sweep.py -q`

---

## 48 — Add conditional-request support for bootstrap fetches (Impact: M)

**Files**: `python/fpl_andres/adapters/fpl.py` (`fetch_bootstrap` lines 77–81,
`_request_with_retries` lines 224–255), `python/tests/test_fpl_adapter.py`

**Problem**: `fetch_bootstrap` fetches the full bootstrap-static payload on every call.
The bootstrap endpoint is stable within a gameweek and changes only at deadline time.
Repeated fetches within the same workflow run (e.g., a planning sweep that calls
bootstrap once per scenario) refetch up to 8 MB each time. HTTP conditional requests
using `ETag` / `If-None-Match` or `Last-Modified` / `If-Modified-Since` would allow
the server to return 304 Not Modified, saving bandwidth and latency.

**Change**:

1. Add an optional `etag: str | None = None` and
   `last_modified: str | None = None` parameter to `fetch_bootstrap` (and
   `_fetch_json_object` and `_fetch_json` where needed, as keyword-only parameters
   threaded through from `fetch_bootstrap`).
2. In `_fetch_json`, if `etag` is provided, add `If-None-Match: {etag}` to the
   request headers; if `last_modified` is provided, add
   `If-Modified-Since: {last_modified}`.
3. Handle a 304 response in `_fetch_json`: return a sentinel (e.g., a new
   `FetchedPayload` subtype or a `None` payload) that the caller can distinguish from
   a fresh payload. Alternatively, `fetch_bootstrap` may accept a callback to the
   last fetched payload and return it unchanged on 304.
4. Do not invent a caching layer inside `FplClient`; callers are responsible for
   storing the `ETag` and re-passing it. `FetchedPayload` may expose the `ETag`
   from the response headers so callers can store it.
5. 304 must not be treated as an error by `raise_for_status`; guard the call
   accordingly.

**Constraints**: `FetchedPayload` is a frozen Pydantic model imported from
`fpl_andres.contracts`; adding fields to it may require a version bump. Alternatively,
return the `ETag` as a separate field on a new `BootstrapFetchResult` dataclass scoped
to the adapter. The existing `fetch_bootstrap` signature must remain backward-compatible
(new parameters must be optional). `FplContractError` must still be raised for non-JSON,
oversized, or truly erroneous responses.

**Tests first**: in `python/tests/test_fpl_adapter.py`:

- Add `test_bootstrap_fetch_sends_if_none_match_when_etag_provided`: mock a 304
  response; assert the request includes `If-None-Match` and the result indicates
  "not modified."
- Add `test_bootstrap_fetch_without_etag_does_not_send_conditional_header`: assert
  no `If-None-Match` header is present in the request.
- Add `test_bootstrap_fetch_returns_etag_from_response_for_subsequent_calls`:
  mock a 200 response with `ETag: "abc123"`; assert the result exposes `"abc123"`.

**Done when**:

1. A 304 response from `fetch_bootstrap` does not raise and is distinguishable from
   a fresh 200 response.
2. The `ETag` from a 200 response is accessible to the caller.
3. All three new tests pass; existing adapter tests pass unchanged.
4. `python -m pytest python/tests/test_fpl_adapter.py -q` is green.

**Validate**: `python -m pytest python/tests/test_fpl_adapter.py -q`

---

## 49 — Configure explicit connection pool limits (Impact: M)

**Files**: `python/fpl_andres/cli/sweep_managers.py` (`run` line 143),
`python/fpl_andres/cli/verify_veterans.py` (`_fetch_records` line 55),
`python/tests/test_manager_sweep.py`

**Audit claim correction**: Both CLIs already create one `httpx.AsyncClient` per run,
so connection reuse IS active. The real gap is that neither client passes explicit
`httpx.Limits(max_connections=…, max_keepalive_connections=…)`, leaving httpx to use
its defaults (`max_connections=100`, `max_keepalive_connections=20`). The
`sweep_managers.py` run already uses an `asyncio.Semaphore(args.concurrency)` to cap
in-flight requests; the httpx pool limit should match or exceed that concurrency so
the semaphore, not httpx, is the binding constraint.

**Problem**: If `args.concurrency` exceeds `max_keepalive_connections`, httpx closes
keep-alive connections under load, forcing expensive TCP reconnections. If it exceeds
`max_connections`, requests queue inside httpx silently. An operator who raises
`--concurrency` expecting it to work does not know that a separate httpx limit is
quietly constraining throughput.

**Change**:

1. In `sweep_managers.py` `run`, pass `limits=httpx.Limits(max_connections=args.concurrency + 4,
max_keepalive_connections=args.concurrency)` to `httpx.AsyncClient`.
2. In `verify_veterans.py` `_fetch_records`, choose a fixed small limit appropriate
   for the sequential fetch pattern (e.g., `max_connections=4,
max_keepalive_connections=2`), stored as named constants
   `_MAX_CONNECTIONS = 4` and `_MAX_KEEPALIVE = 2`.
3. Document the relationship between `--concurrency` and the pool limit in
   `sweep_managers.py`'s module docstring.

**Constraints**: Do not change `Throttle` or `asyncio.Semaphore` semantics. The new
pool limits must be ≥ 1; raise `ValueError` if `args.concurrency < 1`. The
`_MAX_CONNECTIONS` and `_MAX_KEEPALIVE` constants in `verify_veterans.py` must be
module-level and importable.

**Tests first**: in `python/tests/test_manager_sweep.py`:

- Add `test_asyncclient_pool_limits_match_concurrency`: capture the `httpx.AsyncClient`
  constructor arguments via monkeypatching and assert that `max_connections >=
args.concurrency` and `max_keepalive_connections == args.concurrency`.

**Done when**:

1. `httpx.AsyncClient` in `sweep_managers.py` is constructed with explicit `Limits`
   derived from `args.concurrency`.
2. `httpx.AsyncClient` in `verify_veterans.py` uses named constant limits.
3. The new test passes; existing tests pass unchanged.
4. `python -m pytest python/tests/test_manager_sweep.py -q` is green.

**Validate**: `python -m pytest python/tests/test_manager_sweep.py -q`

---

## 50 — Drain response body before closing when size limit trips (Impact: M)

**Files**: `python/fpl_andres/adapters/fpl.py` (`_read_bounded_content` lines 264–272,
`_fetch_json` lines 189–222), `python/tests/test_fpl_adapter.py`

**Problem**: When `_read_bounded_content` detects the response body exceeds `size_limit`,
it raises `FplContractError` immediately (line 270). Control returns to `_fetch_json`,
where the `finally: await response.aclose()` runs (line 209). At this point the response
body has been only partially consumed. For HTTP/1.1 connections, a `close()` on a
partially-read response signals that the connection cannot be reused; httpx will discard
the socket. Under HTTP/2 or HTTP/1.1 with keep-alive this wastes the socket and forces
a reconnect for the next request. The correct approach is to drain the remaining body
before closing so the connection can be returned to the pool.

**Problem clarification**: `response.aclose()` in httpx already attempts to clean up,
but an unread body on an HTTP/1.1 transport typically forces the connection to close
rather than be reused. Explicitly draining (or signalling a reset) before `aclose()`
allows httpx to return the connection to the pool.

**Change**:

1. In `_read_bounded_content`, when `total > limit`, before raising, do not try to
   drain the stream (the body may be huge). Instead, set a flag or return a sentinel
   that tells `_fetch_json` to call `response.aclose()` immediately after the error
   path rather than draining.
2. In `_fetch_json`, in the `finally` block, after catching the
   `FplContractError("FPL response exceeded the allowed size")`, call
   `await response.aclose()` unconditionally — this is already present. The additional
   change: before `aclose()`, call `response.stream.aclose()` (or equivalently
   rely on `aclose()` which internally calls the stream closer). If the httpx version
   in use exposes `response.aclose()` as a no-op when already closed, this is safe.
3. Add a test to verify that after a size-limit trip the mock stream's `aclose()`
   method is called exactly once.

**Constraints**: The existing `OversizedAsyncStream` fixture in `test_fpl_adapter.py`
(visible at the top of that test file) already models this scenario; extend it rather
than replacing it. `FplContractError` must still be raised on oversize. Do not attempt
to drain the full body — that defeats the size limit.

**Tests first**: in `python/tests/test_fpl_adapter.py`:

- Extend `test_entry_fetch_stops_chunked_body_at_size_limit` (line 148) to also
  assert that `OversizedAsyncStream.closed` is `True` after the error, confirming
  `aclose()` was called.
- Add `test_size_limit_trip_does_not_read_beyond_limit`: use
  `OversizedAsyncStream.read_beyond_limit` to assert that the adapter never reads
  past the limit before closing. This test already exists structurally; verify it
  passes with the refactored close path.

**Done when**:

1. `response.aclose()` is provably called after a size-limit `FplContractError`.
2. The stream's `aclose` is called exactly once (no double-close).
3. `FplContractError` is still raised.
4. All adapter tests pass.
5. `python -m pytest python/tests/test_fpl_adapter.py -q` is green.

**Validate**: `python -m pytest python/tests/test_fpl_adapter.py -q`

---

## 51 — Verify semaphore release on task failure in `sweep_managers.py` (Impact: M)

**Files**: `python/fpl_andres/cli/sweep_managers.py` (`one` inner function lines
153–157), `python/tests/test_manager_sweep.py`

**Audit claim correction**: The audit states the semaphore may not be released on
inner-task failure. This is stale. The `one` coroutine uses `async with semaphore:` at
line 156, which is an `asyncio.Semaphore` context manager. Python's `asyncio.Semaphore`
guarantees release on normal exit and on exception, identically to `asyncio.Lock`. No
code change is needed for the semaphore itself.

**Real gap**: `asyncio.gather` at line 159 uses default `return_exceptions=False`, which
means the first exception from any task cancels the gather and re-raises. The remaining
tasks' semaphore acquisitions are cancelled via `asyncio.CancelledError`, which the
`async with semaphore:` block handles correctly by releasing before propagating the
cancellation. So the semaphore is safe.

**Change**:

1. Add a comment above the `async with semaphore:` line noting that `asyncio.Semaphore`
   releases on exception and cancellation, so no explicit `try/finally` is needed.
2. Add a docstring to the `one` coroutine.
3. No logic change is required.

**Constraints**: No behaviour change; this is documentation only. Do not change
`asyncio.gather`'s `return_exceptions` parameter — doing so would silently swallow
errors.

**Tests first**: in `python/tests/test_manager_sweep.py`:

- Add `test_semaphore_is_released_after_fetch_raises`: construct a `Throttle` and a
  semaphore with value 1; mock `_fetch` to raise `RuntimeError`; call `one(1)` in a
  coroutine and assert that the semaphore's internal counter is back to 1 after the
  `RuntimeError` propagates.

**Done when**:

1. The comment and docstring are added.
2. The semaphore-release test passes.
3. All existing sweep tests pass unchanged.
4. `python -m pytest python/tests/test_manager_sweep.py -q` is green.

**Validate**: `python -m pytest python/tests/test_manager_sweep.py -q`

---

## 52 — Log explicitly when a requested gameweek is not published (Impact: M)

**Files**: `python/fpl_andres/ingest/historical.py` (`HistoricalIngest.ingest_season`
lines 132–151), `python/fpl_andres/cli/ingest_historical.py` (`main` lines 168–178),
`python/tests/test_historical_ingest.py`

**Problem**: In `ingest_season`, when `ArchiveFileNotPublished` is caught at line 135,
the gameweek is silently skipped with `continue` (line 137). The `SeasonIngestResult`
only contains written gameweeks in its `gameweeks` dict, so the caller cannot easily
tell whether GW39 was "not requested" versus "requested but not published." In `main`,
after `ingest.ingest_season` completes, there is no log entry identifying which
gameweeks were skipped. An operator who passes `--gameweeks 1-47` for a non-disrupted
season silently skips GW39–47 with no output.

**Change**:

1. Add a `skipped_gameweeks: dict[int, str]` field to `SeasonIngestResult` (alongside
   `gameweeks`) that maps each requested-but-unpublished gameweek to the reason string
   `"not_published"`.
2. In `ingest_season`, when `ArchiveFileNotPublished` is caught, add the gameweek
   to `skipped_gameweeks` before continuing.
3. In `cli/ingest_historical.py` `main`, after logging the "OK" line, also log
   `"  SKIP {season} GW{gw}: not_published"` for each entry in
   `result.skipped_gameweeks`.
4. Do not change the function signature or the `SeasonIngestResult.total_stat_rows`
   property — those must remain stable.

**Constraints**: `SeasonIngestResult` is a `dataclass(frozen=True)` (line 54); adding
a mutable default requires using `field(default_factory=dict)`. `ArchiveFileNotPublished`
must still not be re-raised here — silent skip with logging is the intended contract for
missing gameweek files. The `gameweeks` dict retains only written gameweeks; the
`skipped_gameweeks` dict is separate and additive.

**Tests first**: in `python/tests/test_historical_ingest.py`:

- Extend `test_a_gameweek_the_archive_never_published_is_skipped_not_fatal` (line 394)
  to assert that `result.skipped_gameweeks` contains the unpublished gameweek with
  reason `"not_published"`.
- Add `test_all_gameweeks_written_leaves_skipped_empty`: run a full ingest where all
  requested gameweeks are published; assert `result.skipped_gameweeks == {}`.

**Done when**:

1. `SeasonIngestResult.skipped_gameweeks` maps unpublished-but-requested gameweeks
   to `"not_published"`.
2. `main` logs each skipped gameweek.
3. Both new tests and all existing tests pass.
4. `python -m pytest python/tests/test_historical_ingest.py -q` is green.

**Validate**: `python -m pytest python/tests/test_historical_ingest.py -q`

---

## 53 — Add structured attributes to `ArchiveFileNotPublished` (Impact: M)

**Files**: `python/fpl_andres/ingest/historical.py` (`ArchiveFileNotPublished` lines
35–40, `ArchiveFetcher.fetch` line 76),
`python/tests/test_historical_ingest.py`

**Problem**: `ArchiveFileNotPublished` carries only a free-text message:
`f"archive file not published: {url}"` (line 76). The season and gameweek are embedded
in the URL string (e.g., `.../data/2024-25/gws/gw7.csv`) but are not accessible as
structured attributes. Code that catches this exception and wants to log
`"2024-25 GW7 not published"` must parse the URL string, which is fragile. The class
docstring at lines 36–40 notes its distinction from a transport failure but does not
document its fields.

**Change**:

1. Add `season: str`, `path: str`, and `url: str` attributes to
   `ArchiveFileNotPublished` by giving it a custom `__init__`:
   `def __init__(self, *, season: str, path: str, url: str) -> None` that calls
   `super().__init__(f"archive file not published: {url}")` and stores the three
   attributes.
2. Update `ArchiveFetcher.fetch` to raise
   `ArchiveFileNotPublished(season=revision.season, path=path, url=url)` — but since
   `ArchiveFetcher.fetch` does not currently receive `season` or a structured path,
   pass them through from the `VaastavRevision` or parse them from the URL.
   Prefer: add `season` and `path` as keyword arguments to `ArchiveFetcher.fetch`
   (the existing callers in `HistoricalIngest.ingest_season` already know both).
3. Update all three call sites in `HistoricalIngest.ingest_season` (teams, players,
   fixtures files) and the gameweek loop to pass `season` and `path`.
4. Update `ArchiveFileNotPublished` in `__all__` (line 199).

**Constraints**: `ArchiveFileNotPublished` is a subclass of `ArchiveFetchError` (a
subclass of `RuntimeError`); its `str()` message must remain `"archive file not
published: {url}"` so any log line that formats the exception directly does not change.
`HistoricalIngest.ingest_season`'s caller in `cli/ingest_historical.py` must not
require changes — it catches `Exception` broadly.

**Tests first**: in `python/tests/test_historical_ingest.py`:

- Extend `test_a_missing_archive_file_raises_rather_than_writing_partial_state`
  (line 377) to assert that the raised `ArchiveFileNotPublished` has `.season`,
  `.path`, and `.url` attributes with the expected values.
- Add `test_archive_file_not_published_message_is_stable`: assert that
  `str(error)` starts with `"archive file not published:"`.

**Done when**:

1. `ArchiveFileNotPublished` exposes `.season`, `.path`, and `.url` attributes.
2. Its `str()` representation is unchanged.
3. Both new tests and all existing tests pass.
4. `python -m pytest python/tests/test_historical_ingest.py -q` is green.

**Validate**: `python -m pytest python/tests/test_historical_ingest.py -q`

---

## 54 — Detect duplicate and reordered CSV headers in `ingest/normalise.py` (Impact: M)

**Files**: `python/fpl_andres/ingest/normalise.py` (`_rows` lines 96–104, `_require`
lines 107–110), `python/tests/test_historical_ingest.py`

**Problem**: `_rows` uses `csv.DictReader`, which silently handles a CSV header with
duplicate column names by keeping only the last value for each duplicated key. A header
like `"element,element,minutes"` would cause `_rows` to return rows with an `element`
key whose value is the second column, silently discarding the first. Additionally,
`_require` checks only that required column names are present in the header set; it does
not verify that each required column appears exactly once, or that the header row is
well-formed (e.g., no empty-string keys from trailing commas). The `csv.DictReader`
at line 97 also silently ignores an empty `fieldnames[i]` if the last column header
is empty.

**Change**:

1. In `_rows`, after `reader.fieldnames` is obtained (line 100), check for duplicates:
   if `len(reader.fieldnames) != len(set(reader.fieldnames))`, raise
   `ColumnMappingError("archive CSV header contains duplicate column names: {…}")`,
   naming the duplicated columns.
2. Check for empty-string keys: if `""` is in `reader.fieldnames`, raise
   `ColumnMappingError("archive CSV header contains an empty column name")`.
3. Do not check header ordering — `csv.DictReader` is order-independent by design, and
   column order is not a contract of the archive.

**Constraints**: `ColumnMappingError` must be used (not bare `ValueError`). The
existing `_require` function need not change — presence checking is correct and
separate from the new duplication check. The `_drop_identical_duplicates` function
already handles row-level duplicates; this change addresses header-level duplicates
only. No change to `normalise_players`, `normalise_teams`, or `normalise_fixtures`
call sites is needed.

**Tests first**: in `python/tests/test_historical_ingest.py`:

- Add `test_duplicate_header_column_raises_column_mapping_error`: pass a gameweek CSV
  bytes string with `"element,element,minutes,…"` as the header; assert
  `ColumnMappingError` is raised and its message names the duplicated column.
- Add `test_empty_header_column_raises_column_mapping_error`: pass a CSV with a
  trailing comma in the header line; assert `ColumnMappingError` is raised.

**Done when**:

1. A duplicated header column name raises `ColumnMappingError` naming the column.
2. An empty-string header entry raises `ColumnMappingError`.
3. Valid headers continue to parse normally.
4. Both new tests and all existing tests pass.
5. `python -m pytest python/tests/test_historical_ingest.py -q` is green.

**Validate**: `python -m pytest python/tests/test_historical_ingest.py -q`

---

## 55 — Handle malformed-JSON `ValueError` in `verify_veterans.py` (Impact: L)

**Files**: `python/fpl_andres/cli/verify_veterans.py` (`_fetch_records` lines 51–67),
`python/fpl_andres/adapters/fpl.py` (`_fetch_json` line 207),
`python/tests/test_veteran_extraction.py`

**Problem**: `sweep_managers.py` guards `response.json()` with `except ValueError`
(line 119), correctly catching malformed-JSON responses. `verify_veterans.py` takes a
different path: `_fetch_records` calls `FplClient.fetch_entry_history`, which calls
`_fetch_json`, which calls `json.loads(content)` at line 207. If the FPL API returns
a non-JSON body (e.g., an HTML error page that passes the Content-Type check), `json.loads`
raises `json.JSONDecodeError` (a subclass of `ValueError`). This propagates out of
`_fetch_json` and then out of `FplClient.fetch_entry_history` as an unhandled
`ValueError`, bypassing the `except (CohortError, httpx.HTTPError)` handler at line 61
and causing `_fetch_records` to raise rather than recording a problem entry.

**Change**:

1. In `adapters/fpl.py` `_fetch_json`, wrap the `json.loads(content)` call at line
   207 in a `try/except json.JSONDecodeError` and re-raise as
   `FplContractError(f"FPL response was not valid JSON: {error}")`. This ensures that
   all decode failures are converted to `FplContractError` before leaving the adapter.
2. In `verify_veterans.py` `_fetch_records`, the `except (CohortError, httpx.HTTPError)`
   handler at line 61 must be extended to also catch `FplContractError` from
   `fpl_andres.adapters.fpl`, since that is the typed error the adapter raises for
   malformed responses. Import `FplContractError` and add it to the except clause.
3. Do not add a bare `except ValueError` in `verify_veterans.py`; let the adapter's
   typed conversion do the work.

**Constraints**: `FplContractError` is a subclass of `ValueError` (line 33); catching
it by name in `_fetch_records` is explicit and preferred over catching `ValueError`
broadly. The existing `test_fpl_adapter.py` tests must not be affected. The `sweep_managers.py`
`except ValueError` guard remains unchanged — it catches the raw `response.json()`
call, not going through `FplClient`.

**Tests first**: in `python/tests/test_veteran_extraction.py` (or a new
`test_verify_veterans.py`):

- Add `test_malformed_json_response_is_recorded_as_problem_not_raised`: mock
  `FplClient.fetch_entry_history` to raise `FplContractError("not valid JSON")`;
  assert that `_fetch_records([1])` returns `([], ["entry 1: FplContractError"])` and
  does not raise.

Also add to `python/tests/test_fpl_adapter.py`:

- Add `test_non_json_body_raises_fpl_contract_error_not_value_error`: mock a 200
  response with `Content-Type: application/json` but body `b"<html>"`;
  assert `FplContractError` is raised (not bare `ValueError`).

**Done when**:

1. `_fetch_json` converts `json.JSONDecodeError` to `FplContractError`.
2. `_fetch_records` catches `FplContractError` and appends to `problems`.
3. Both new tests pass; all existing tests pass unchanged.
4. `python -m pytest python/tests/test_fpl_adapter.py python/tests/test_veteran_extraction.py -q` is green.

**Validate**: `python -m pytest python/tests/test_fpl_adapter.py python/tests/test_veteran_extraction.py -q`

---

## 56 — Preserve all transport errors when re-raising in `FplClient` (Impact: L)

**Files**: `python/fpl_andres/adapters/fpl.py` (`_request_with_retries` lines 224–255,
`last_transport_error` variable line 225), `python/tests/test_fpl_adapter.py`

**Problem**: `_request_with_retries` stores only the most recent `httpx.TransportError`
in `last_transport_error` (lines 225, 240). When all attempts are exhausted and a
transport error is re-raised at line 254, the context from earlier attempts is lost.
An operator diagnosing a `ConnectTimeout` on attempt 3 cannot see that attempt 1 was
`ConnectError` (e.g., DNS failure) and attempt 2 was `ReadTimeout`, which might point
to a different root cause. Python's exception chaining allows preserving the full
history with `raise current from previous`.

**Change**:

1. Replace `last_transport_error: httpx.TransportError | None` with
   `last_transport_error: httpx.TransportError | None` as before, but chain it:
   after catching `httpx.TransportError as error` at line 239, do
   `error.__context__ = last_transport_error` before storing `last_transport_error = error`.
   This chains the new exception to the previous one using implicit context.
2. Alternatively, use explicit chaining: store the previous error and do
   `raise error from last_transport_error` when re-raising. However, `raise from`
   suppresses the implicit context chain and only shows one level, so prefer the
   `__context__` approach if the full chain is desired.
3. Do not change `MAX_ATTEMPTS` or the retry logic.

**Constraints**: `FplContractError` must not be raised for transport errors; only
`httpx.TransportError` (the last one, now chained to its predecessors) is re-raised.
The fallback `raise RuntimeError("FPL retry loop ended without a response")` at line
255 is a defensive guard and must not be removed. The new chaining must not break
the `test_bootstrap_fetch_retries_transient_status_with_bounded_backoff` test.

**Tests first**: in `python/tests/test_fpl_adapter.py`:

- Add `test_transport_errors_are_chained_across_retries`: mock all three attempts to
  raise distinct `httpx.TransportError` subclasses (e.g., `httpx.ConnectError` then
  `httpx.ReadTimeout` then `httpx.ConnectTimeout`); catch the final raised error and
  walk `__context__` chain; assert all three exception types appear in the chain.

**Done when**:

1. The re-raised `httpx.TransportError` has `__context__` set to the previous error.
2. A chain of N attempts produces a chain of depth N−1.
3. The new test passes; all existing adapter tests pass unchanged.
4. `python -m pytest python/tests/test_fpl_adapter.py -q` is green.

**Validate**: `python -m pytest python/tests/test_fpl_adapter.py -q`

---

## 57 — Mark truncated detail strings in `_safe_detail` (Impact: L)

**Files**: `python/fpl_andres/persistence/supabase.py` (`_safe_detail` lines 216–226),
`python/tests/test_persistence.py`

**Problem**: `_safe_detail` limits its return value to 500 characters by slicing with
`[:500]` in three places (lines 221, 225, 226). When the upstream error message is
longer than 500 characters, the returned string is a silent truncation: a reader of
the log entry sees `"column 'element_id' violates not-null constraint on table 'element_…"` and does
not know whether the message ends there or was cut. Treating a clipped message as
complete can hide the cause of a write failure.

**Change**:

1. Replace the three bare `[:500]` slices with a helper `_truncate(text: str,
limit: int = 500) -> str` that returns `text` unchanged if `len(text) <= limit`, or
   `text[:limit - 1] + "…"` (one Unicode ellipsis character) otherwise.
2. Apply `_truncate` at all three sites: `response.text[:500]` (line 221),
   `" | ".join(parts)[:500]` (line 225), and `str(body)[:500]` (line 226).
3. Keep the 500-character limit as the named constant `_DETAIL_LIMIT = 500` defined
   at the top of `_safe_detail` or as a module constant.

**Constraints**: `_safe_detail` is a private function used only inside `supabase.py`
within `insert` (line 138), `update` (line 183), and `select` (line 206). Its return
value is embedded in `SupabaseWriteError` messages; changing it from a plain slice to
a truncated-with-marker string is a log-only change with no contract effect.
`SupabaseWriteError` must not change its class hierarchy. Do not change the 500
character limit without an explicit requirement; it must remain a named constant, not
an inline magic number.

**Tests first**: in `python/tests/test_persistence.py`:

- Add `test_safe_detail_appends_ellipsis_when_truncated`: call `_safe_detail` with a
  mocked `httpx.Response` whose text body is 600 characters; assert the result ends
  with `"…"` and has length `_DETAIL_LIMIT`.
- Add `test_safe_detail_does_not_append_ellipsis_when_not_truncated`: call with a
  50-character text; assert the result equals the text exactly (no `"…"`).

**Done when**:

1. `_safe_detail` appends `"…"` when the returned string was truncated.
2. Short messages are returned unchanged.
3. Both new tests pass; all existing persistence tests pass unchanged.
4. `python -m pytest python/tests/test_persistence.py -q` is green.

**Validate**: `python -m pytest python/tests/test_persistence.py -q`
