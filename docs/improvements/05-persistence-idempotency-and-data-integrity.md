# 5. Persistence, idempotency and data integrity — work orders

Detailed briefs for items 58–69 of the [improvement audit](../../IMPROVEMENTS.md).
Each brief is self-contained: a sub-agent should be able to implement one item
from its brief alone.

Every brief obeys the repository rules: test-first, never default a missing
controlling FPL rule, never expose a Supabase secret, Resend key or subscriber
email to browser code or logs, apply only tracked migrations that pass local
policy tests and Linux CI (never iterate directly on the production project),
and keep manual team-state overrides separate from public last-deadline state.

---

## 58 — Validate `on_conflict` columns are present in every upsert payload (Impact: H)

**Files**: `python/fpl_andres/persistence/supabase.py` (`upsert`, lines 144–158;
`insert`, lines 105–142; `_chunked`, line 212), `python/tests/test_persistence.py`

**Problem**: `upsert()` (line 144) accepts an `on_conflict: str` column list and
delegates to `insert()`, which sends the column name(s) to PostgREST as a query
parameter. There is no validation that every row in `rows` actually contains all
the columns named in `on_conflict`. PostgREST interprets a missing conflict column
as a NULL and performs a fresh insert rather than an update, silently creating a
duplicate row. Example trigger: calling `upsert("elements", rows, on_conflict="season,element_id")`
where a normaliser bug omits `season` from one row produces a spurious second row
that poisons downstream joins.

**Change**:

1. Before the first chunk is sent in `insert()`, when `resolution` is
   `"merge-duplicates"` or `"ignore-duplicates"` and `on_conflict` is set, split
   the `on_conflict` string on commas, strip whitespace, and assert every column
   name is present as a key in every row mapping.
2. Raise a new `SupabaseConflictColumnError(ValueError)` (add it to
   `persistence/supabase.py` and to `__all__`) naming the first offending column
   and row index when the check fails.
3. Export `SupabaseConflictColumnError` from `persistence/__init__.py` alongside
   the existing exports.

**Constraints**: The check must occur before any network I/O so no partial write
is attempted. Existing callers (`ingest/historical.py`, `persistence/backtest.py`,
`cli/capture_crowd.py`) must not require changes because they already supply the
correct columns — the new guard is a safety net, not a behaviour change. Do not
add a migration; this is a pure Python change.

**Tests first**: In `python/tests/test_persistence.py`, add:

- `test_upsert_raises_when_on_conflict_column_is_absent_from_a_row` — call
  `client.upsert("elements", [{"element_id": 1}], on_conflict="season,element_id")`
  and assert `SupabaseConflictColumnError` is raised mentioning `"season"` before
  any HTTP request is made (use a `respx.mock` block with no registered route and
  verify `route.call_count == 0`).
- `test_insert_ignoring_duplicates_raises_when_conflict_column_absent` — same
  pattern via `insert_ignoring_duplicates`.
- `test_upsert_succeeds_when_all_on_conflict_columns_present` — regression that
  the existing happy-path tests still pass.

**Done when**:

1. `SupabaseConflictColumnError` is importable from `fpl_andres.persistence.supabase`.
2. Calling `upsert` with a row missing any `on_conflict` column raises
   `SupabaseConflictColumnError` before touching the network.
3. All existing `test_persistence.py` tests still pass.
4. `python -m pytest python/tests/test_persistence.py -q` exits 0.

**Validate**: `python -m pytest python/tests/test_persistence.py -q`

---

## 59 — Make multi-table season ingest atomic or resumable (Impact: H)

**Files**: `python/fpl_andres/ingest/historical.py` (`HistoricalIngest.ingest_season`,
lines 96–159), `python/tests/test_historical_ingest.py`

**Problem**: `ingest_season()` writes five independent tables in sequence:
`seasons` (line 104), `teams` (line 113), `elements` (line 120), `fixtures`
(line 127), and `element_gameweek_stats` per gameweek (line 146). Each is a
separate PostgREST request with no transaction boundary. If the process is killed
after the `teams` upsert succeeds but before `elements` completes, the database is
left with `teams` rows that reference a season whose `elements` are absent. On a
re-run, `source_snapshots` are reused correctly (via `ignore-duplicates` on
content hash), but the partially written season tables are not rolled back. The
audit cites lines 104–151; the actual method spans lines 96–159.

**Change**:

1. Add a `HistoricalIngestCheckpoint` dataclass in `ingest/historical.py` that
   records which tables have been successfully written for a given
   `(season, revision.commit_sha)` tuple, serialised to a caller-supplied
   `pathlib.Path` using the existing atomic-write pattern (write to a `.tmp`
   sibling, then `Path.rename`).
2. Accept an optional `checkpoint_path: Path | None = None` parameter in
   `ingest_season()`. When provided, load any existing checkpoint for the season
   and skip already-completed table writes; write the checkpoint after each
   successful table.
3. Add a `skip_completed: bool = False` keyword to `ingest_season()` that, when
   `True`, checks each upsert result count against the checkpoint's stored count
   and raises `ArchiveFetchError` if they differ (guards against a stale
   checkpoint).

**Constraints**: The change must not break the no-rollback nature of the existing
individual upserts — PostgREST has no cross-table transactions. The checkpoint
is a best-effort resumption aid, not a hard guarantee. No new migration is needed.
All existing callers in `cli/ingest_historical.py` must still work unchanged (the
new parameters default to `None`/`False`).

**Tests first**: In `python/tests/test_historical_ingest.py`, add:

- `test_ingest_resumes_from_checkpoint_skipping_completed_tables` — mock the
  Supabase client and a pre-written checkpoint that marks `teams` and `elements`
  done; assert only `fixtures` and stats upserts are called.
- `test_checkpoint_is_written_after_each_successful_upsert` — after a full
  successful run, assert the checkpoint file lists all tables.
- `test_checkpoint_path_none_leaves_no_file` — default behaviour creates no file.

**Done when**:

1. A run interrupted after `teams` can be resumed and completes without
   re-fetching or re-writing the `teams` archive file.
2. A fresh run with no checkpoint produces the same result as before.
3. `python -m pytest python/tests/test_historical_ingest.py -q` exits 0.
4. No new migration is required (pure Python change).

**Validate**: `python -m pytest python/tests/test_historical_ingest.py -q`

---

## 60 — Retry transient Supabase 5xx writes with backoff (Impact: H)

**Files**: `python/fpl_andres/persistence/supabase.py` (`insert`, lines 128–141;
`_chunked`, line 212; `update`, lines 169–184), `python/tests/test_persistence.py`

**Problem**: The write loop in `insert()` (lines 129–141) calls
`self._client.post(...)` once per chunk and raises `SupabaseWriteError`
immediately on any `status_code >= 400`. A transient PostgREST 500, 502, 503, or
504 — from a Supabase infrastructure blip lasting a few seconds — aborts the
entire scheduled ingest run, requiring a full manual restart. The same applies to
`update()` (lines 176–184). The Python FPL adapter (`adapters/fpl.py`) already
demonstrates the correct pattern: `MAX_ATTEMPTS = 3` retries with exponential
backoff and a capped `Retry-After` ceiling.

**Change**:

1. Extract the single-request dispatch in `insert()` and `update()` into a private
   `_post_with_retry(url, ...)` / `_patch_with_retry(url, ...)` helper on
   `SupabaseRestClient` that retries up to `_MAX_WRITE_ATTEMPTS` times (default 3) on status codes in a `_RETRYABLE_WRITE_STATUSES` frozenset
   `{500, 502, 503, 504}`.
2. Between retries, sleep using exponential backoff: `min(2.0 ** attempt, 30.0)`
   seconds, drawn from an injectable `_sleep` parameter (default `time.sleep`) so
   tests run instantly.
3. After all attempts are exhausted, raise `SupabaseWriteError` with the final
   status and `_safe_detail(response)` as today.
4. Add module-level constants `_MAX_WRITE_ATTEMPTS` and `_RETRYABLE_WRITE_STATUSES`
   with docstrings.

**Constraints**: Client 4xx errors (including `409 Conflict`, used for duplicate
detection in `workflow.py`) must not be retried — they are deterministic failures.
The injectable `_sleep` parameter must not appear in the public API of the class
(pass it to `__init__` as `_sleep: Callable[[float], None] = time.sleep`). Do not
add a migration.

**Tests first**: In `python/tests/test_persistence.py`, add:

- `test_insert_retries_on_503_and_succeeds_on_second_attempt` — use `respx` to
  serve a 503 on the first call and 201 on the second; assert `call_count == 2`
  and no exception is raised.
- `test_insert_raises_after_all_retry_attempts_exhausted` — mock three consecutive
  503s; assert `SupabaseWriteError` is raised and `call_count == 3`.
- `test_insert_does_not_retry_409_conflict` — mock a 409; assert `call_count == 1`
  and `SupabaseWriteError` is raised immediately.

**Done when**:

1. A single transient 503 does not fail an ingest run.
2. Three consecutive 5xx responses raise `SupabaseWriteError` after exactly three
   attempts.
3. 4xx responses are not retried.
4. `python -m pytest python/tests/test_persistence.py -q` exits 0.

**Validate**: `python -m pytest python/tests/test_persistence.py -q`

---

## 61 — Write sweep checkpoints atomically via temp-file rename (Impact: H)

**Files**: `python/fpl_andres/cli/sweep_managers.py` (`_save_progress`, lines
86–88), `python/tests/test_manager_sweep.py`

**Problem**: `_save_progress()` (lines 86–88) calls
`CHECKPOINT.write_text(json.dumps(progress.__dict__, indent=2), encoding="utf-8")`
which writes the JSON directly to the live checkpoint file. If the process is
killed mid-write (e.g., by a `SIGKILL` or a disk-full error), the checkpoint file
is left truncated or empty. On the next `--resume` run, `json.loads(CHECKPOINT.read_text(...))` at line 81 raises `json.JSONDecodeError` and the
entire sweep restarts from `--start`, discarding up to 16 hours of progress.

**Change**:

1. Replace the `CHECKPOINT.write_text(...)` call in `_save_progress()` with an
   atomic write helper: write the JSON to a `.tmp` sibling path
   (`CHECKPOINT.with_suffix(".json.tmp")`), `fsync` the file descriptor, close
   it, then call `Path.rename(CHECKPOINT)`. On POSIX systems, `rename` is atomic
   within the same filesystem so the checkpoint is either the full old version or
   the full new version, never a partial write.
2. In `_load_progress()` (lines 79–83), if `CHECKPOINT.read_text()` raises
   `json.JSONDecodeError` or `OSError`, fall back to `Progress(next_id=start)` and
   emit a `stderr` warning rather than crashing, so a corrupted checkpoint does
   not prevent resumption.
3. At startup, delete any stale `.json.tmp` sibling left by a previous crash.

**Constraints**: Windows does not guarantee atomic rename semantics, but the
sweep CLI is documented as a Linux-only long-running job (see
`cli/sweep_managers.py` module docstring). The `.tmp` sibling must be on the same
filesystem as `CHECKPOINT` (`OUTPUT_DIR / "data/cohort"`). Do not change the
`Progress` dataclass fields or the serialisation format.

**Tests first**: In `python/tests/test_manager_sweep.py`, add:

- `test_save_progress_writes_atomically_via_rename` — mock `Path.rename` and
  assert it is called rather than a direct `write_text` to the target path.
- `test_load_progress_falls_back_gracefully_on_corrupt_checkpoint` — write invalid
  JSON to the checkpoint path; assert `_load_progress(1, resume=True)` returns
  `Progress(next_id=1)` without raising.
- `test_stale_tmp_file_is_deleted_at_startup` — create a `.json.tmp` sibling;
  assert it is removed by `_save_progress` or `_load_progress` before the first
  write.

**Done when**:

1. `_save_progress` never writes directly to the live checkpoint path.
2. A corrupted checkpoint causes a warning and a clean restart, not a crash.
3. `python -m pytest python/tests/test_manager_sweep.py -q` exits 0.

**Validate**: `python -m pytest python/tests/test_manager_sweep.py -q`

---

## 62 — Hash idempotency key inputs instead of pipe-concatenating them (Impact: M)

**Files**: `python/fpl_andres/persistence/workflow.py` (`build_idempotency_key`,
lines 100–102), `python/tests/test_persistence.py`

**Problem**: `build_idempotency_key()` (lines 100–102) produces a key by
joining sorted `key=value` pairs with `|` as a separator:
`"|".join(f"{key}={parts[key]}" for key in sorted(parts))`. A workflow whose
`parts` dict contains a value that itself includes `|` or `=` can collide with a
legitimately distinct set of parts. Example: `{"a": "x|b", "b": "y"}` produces
`"a=x|b|b=y"` which is identical to `{"a": "x", "b": "b=y"}` producing the same
string. A collision silently prevents a legitimate second run from being recorded.

**Change**:

1. Rewrite `build_idempotency_key()` to serialise `parts` as a
   deterministic JSON string (sorted keys, compact separators,
   `ensure_ascii=True`) and return its SHA-256 hex digest prefixed with `"sha256:"`.
2. Keep the function signature identical: `(parts: Mapping[str, Any]) -> str`.
3. Update the assertion in `test_idempotency_key_is_order_independent` (line 155)
   which currently asserts the raw string `"gameweek=3|season=2024-25"` — replace
   it with an assertion that the two dicts produce the same hash and that the hash
   starts with `"sha256:"`.

**Constraints**: The new key format is incompatible with any existing
`workflow_runs` rows (their `idempotency_key` column still holds the old
pipe-joined form). A new tracked migration is not needed because there is no
migration that depends on the key format — the unique constraint only requires
uniqueness, not a specific format. However, if a production run exists with the
old format, a re-run after this change would not detect the duplicate. Document
this one-time risk in the function docstring.

**Tests first**: In `python/tests/test_persistence.py`, add:

- `test_idempotency_key_is_collision_resistant` — assert
  `build_idempotency_key({"a": "x|b=y"}) != build_idempotency_key({"a": "x", "b": "y"})`.
- `test_idempotency_key_starts_with_sha256_prefix` — assert the result of any
  call starts with `"sha256:"`.
- Update `test_idempotency_key_is_order_independent` to check hash equality
  rather than a literal string.

**Done when**:

1. Separator-colliding inputs produce distinct keys.
2. The key format starts with `"sha256:"`.
3. `python -m pytest python/tests/test_persistence.py -q` exits 0.

**Validate**: `python -m pytest python/tests/test_persistence.py -q`

---

## 63 — Detect duplicate workflow runs from the PostgREST error code, not phrase matching (Impact: M)

**Files**: `python/fpl_andres/persistence/workflow.py` (`WorkflowRunRecorder.__enter__`,
lines 61–66), `python/tests/test_persistence.py`

**Problem**: The duplicate-run guard at lines 61–66 matches the error string with
`"duplicate key" in str(error).lower() or "23505" in str(error)`. The
`"duplicate key"` branch is a fragile English-phrase match against the PostgREST
error body, which could change with a PostgREST version upgrade, a locale change,
or a custom error message set by an RLS policy. The `"23505"` branch is already
correct (it matches the Postgres SQLSTATE code emitted in the `code` field of the
PostgREST JSON body). The brittle phrase match still stands as a fallback and
should be removed.

**Change**:

1. Remove the `"duplicate key" in str(error).lower()` branch from the condition
   at line 62, keeping only `"23505" in str(error)`.
2. Verify that `_safe_detail()` (lines 216–225 of `supabase.py`) always includes
   the `code` field from the PostgREST JSON body when present (it already does —
   see the `parts` list at line 223 which includes `"code"`).
3. Update the function docstring on `WorkflowRunRecorder.__enter__` to state that
   duplicate detection relies on Postgres SQLSTATE `23505`.

**Constraints**: The `"23505"` check relies on `_safe_detail()` in `supabase.py`
serialising the `code` field. If `_safe_detail` is refactored, the check must be
updated too. Add a comment coupling the two. No migration needed.

**Tests first**: In `python/tests/test_persistence.py`, add:

- `test_duplicate_run_detected_via_sqlstate_code_not_english_phrase` — mock a 409
  response whose JSON body is `{"code": "23505", "message": ""}` (empty message,
  no English phrase); assert `WorkflowAlreadyRunningError` is raised.
- `test_non_duplicate_conflict_is_not_swallowed` — mock a 409 response with code
  `"23503"` (foreign key violation); assert the original `SupabaseWriteError` is
  re-raised, not `WorkflowAlreadyRunningError`.

**Done when**:

1. A PostgREST 409 response with `code: "23505"` raises `WorkflowAlreadyRunningError`
   regardless of the English message.
2. A PostgREST 409 with any other code raises `SupabaseWriteError`.
3. `python -m pytest python/tests/test_persistence.py -q` exits 0.

**Validate**: `python -m pytest python/tests/test_persistence.py -q`

---

## 64 — Size upsert batches by serialised payload bytes as well as row count (Impact: M)

**Files**: `python/fpl_andres/persistence/supabase.py` (`_chunked`, line 212;
`insert`, lines 128–141; `_MAX_ROWS_PER_REQUEST`, line 22),
`python/tests/test_persistence.py`

**Problem**: `_chunked()` (line 212) slices `rows` into chunks of at most
`_MAX_ROWS_PER_REQUEST = 500` rows. A gameweek stats row can carry many wide
string columns; 500 rows of wide JSON may exceed PostgREST's default 10 MB body
limit, producing an opaque `413 Payload Too Large` that is indistinguishable from
a server error. Conversely, a table with tiny rows (e.g., `seasons`) could be
batched at 500 even if the underlying limit allows far more. The row-count limit
is a proxy for the actual payload size.

**Change**:

1. Add a `_MAX_BYTES_PER_REQUEST: int = 8 * 1024 * 1024` constant (8 MiB) to
   `supabase.py`.
2. Rewrite `_chunked()` to accept a `max_bytes` parameter alongside `size` and
   accumulate rows into the current chunk until adding the next serialised row
   would exceed `max_bytes` _or_ the chunk already has `size` rows, whichever
   comes first. Serialise each row with `json.dumps(row, separators=(",", ":"), default=str)`
   to estimate its byte footprint.
3. Pass `max_bytes=_MAX_BYTES_PER_REQUEST` from the `insert()` loop.

**Constraints**: Chunks must always contain at least one row, even if a single
row exceeds `max_bytes`, to avoid an infinite loop. Rows must never be split
across chunks. The row-count limit of 500 remains in force as a secondary cap.
No migration is needed.

**Tests first**: In `python/tests/test_persistence.py`, add:

- `test_chunking_splits_on_byte_limit_before_row_limit` — call `_chunked` with
  three rows whose combined serialised size exceeds `max_bytes` but whose count is
  below `size`; assert two chunks are produced.
- `test_single_oversized_row_is_not_dropped` — a single row larger than `max_bytes`
  must still produce one chunk containing that row.
- Update `test_writes_are_chunked_so_a_full_season_does_not_ship_in_one_request`
  to remain correct.

**Done when**:

1. A batch of rows whose combined JSON exceeds 8 MiB is split into multiple
   requests without dropping any row.
2. A single row larger than 8 MiB is sent in one request (no infinite loop).
3. `python -m pytest python/tests/test_persistence.py -q` exits 0.

**Validate**: `python -m pytest python/tests/test_persistence.py -q`

---

## 65 — Make the upsert batch size configurable per table and per environment (Impact: M)

**Files**: `python/fpl_andres/persistence/supabase.py` (`_MAX_ROWS_PER_REQUEST`,
line 22; `SupabaseRestClient.__init__`, lines 71–89; `insert`, lines 105–142),
`python/tests/test_persistence.py`

**Problem**: `_MAX_ROWS_PER_REQUEST = 500` at line 22 is a single module-level
constant. There is no way for a caller to request a different chunk size for a
specific table (e.g., `crowd_snapshots` may safely use 1000, while `backtesting_predictions`
may require 100 to stay within the PostgREST body limit). A tuning exercise
today requires modifying the module constant and re-deploying, affecting every
table simultaneously.

**Change**:

1. Add a `default_max_rows: int = _MAX_ROWS_PER_REQUEST` parameter to
   `SupabaseRestClient.__init__`, stored as `self._default_max_rows`.
2. Add an optional `max_rows: int | None = None` parameter to `insert()` (and
   therefore transitively to `upsert()` and `insert_ignoring_duplicates()`).
   When `None`, fall back to `self._default_max_rows`.
3. Update `_chunked()` to use the resolved value; see item 64 for the byte-budget
   parameter that should land in the same function signature.

**Constraints**: All existing callers of `upsert`, `insert`, and
`insert_ignoring_duplicates` omit `max_rows` and must continue to work unchanged.
The module-level constant `_MAX_ROWS_PER_REQUEST` should be retained as the
documented default. No migration is needed.

**Tests first**: In `python/tests/test_persistence.py`, add:

- `test_caller_supplied_max_rows_overrides_the_default` — construct a client with
  `default_max_rows=2`; call `insert("t", [row] * 5)`; assert five chunks of at
  most two rows each are sent (use `respx` to count calls).
- `test_per_call_max_rows_overrides_the_instance_default` — client default 500;
  call `insert("t", [row] * 5, max_rows=2)`; assert three requests.

**Done when**:

1. A caller can set `max_rows=100` on `upsert()` without changing the module
   constant.
2. Existing tests pass unchanged.
3. `python -m pytest python/tests/test_persistence.py -q` exits 0.

**Validate**: `python -m pytest python/tests/test_persistence.py -q`

---

## 66 — Add optimistic concurrency to browser-persisted manual team-state overrides (Impact: M)

> **Audit correction**: The audit cites `team_state.py ~line 166`. The actual
> persistence of overrides happens in the browser via
> `apps/web/src/state/team-state-overrides.ts` (`saveTeamStateOverrides`, line 26),
> not in the Python layer. `team_state.py` line 166 assigns `overrides_updated_at`
> inside `resolve_team_state()` which is an in-memory computation, not a write.
> The real gap is in the TypeScript frontend.

**Files**: `apps/web/src/state/team-state-overrides.ts` (`saveTeamStateOverrides`,
lines 26–36), `apps/web/src/state/team-state-overrides.test.ts`,
`apps/web/src/components/TeamStateCorrections.tsx` (`handleSave`, ~line 160)

**Problem**: `saveTeamStateOverrides()` (line 34) calls
`storage.setItem(key, JSON.stringify(overrides))` unconditionally. If a manager
has two browser tabs open and edits overrides in both, the tab that calls `setItem`
last wins silently. The earlier correction is discarded without any signal to the
user. The `TeamStateOverrides` contract already carries an `updatedAt` timestamp
(from `packages/contracts`), which is the natural version vector.

**Change**:

1. Add an optional `expectedUpdatedAt: string | null = null` parameter to
   `saveTeamStateOverrides()`. Before writing, read the currently stored value;
   if it parses successfully and its `updatedAt` differs from `expectedUpdatedAt`,
   throw a new `TeamStateConflictError(Error)` exported from
   `team-state-overrides.ts`.
2. In `TeamStateCorrections.tsx` (`handleSave`, ~line 160), pass the
   `overrides.updatedAt` of the currently displayed overrides as
   `expectedUpdatedAt` and catch `TeamStateConflictError` to show a user-visible
   conflict message rather than silently overwriting.
3. The first save (no existing overrides) passes `expectedUpdatedAt: null`, which
   succeeds when `loadTeamStateOverrides` returns `null`.

**Constraints**: `localStorage` operations are synchronous and single-threaded
within one tab, but two tabs share `localStorage`. The check-then-set is not
atomic across tabs; it is a best-effort guard, not a guarantee. Document this
limitation in the function's JSDoc. Do not touch `team_state.py` or any Python
file. Keep manual overrides separate from public last-deadline state per
repository rules.

**Tests first**: In `apps/web/src/state/team-state-overrides.test.ts`, add:

- `test_saveTeamStateOverrides_raises_on_concurrent_write` — save overrides with
  `updatedAt: "T1"`, then call `saveTeamStateOverrides` again with
  `expectedUpdatedAt: "T1"` (succeeds), then call it with `expectedUpdatedAt: "T1"`
  again after a second save with `updatedAt: "T2"` exists; assert
  `TeamStateConflictError`.
- `test_saveTeamStateOverrides_first_save_with_null_expected_succeeds` — no prior
  entry, `expectedUpdatedAt: null` must not throw.

**Done when**:

1. `saveTeamStateOverrides` with a stale `expectedUpdatedAt` throws `TeamStateConflictError`.
2. The first save (null expected) always succeeds.
3. `corepack pnpm --filter @fpl-andres/web test` exits 0.

**Validate**: `corepack pnpm --filter @fpl-andres/web test`

---

## 67 — Stamp published JSON artifacts with a schema version (Impact: M)

**Files**: `python/fpl_andres/cli/publish_projections.py` (`main`, lines 120–128),
`python/fpl_andres/cli/publish_opening_squad.py` (`main`, lines 222–242),
`python/tests/test_next_match.py`, `python/tests/test_opening_squad.py`

**Problem**: The `projections.json` artifact written by `publish_projections.py`
(lines 120–128) and the `opening-squad.json` artifact written by
`publish_opening_squad.py` (lines 222–242) contain no schema version field. The
web app reads these files at build time; if a field is renamed or removed in a
future publish run, the web app silently reads `undefined`. There is no mechanism
for the web app to detect that an artifact produced by an older CLI is
incompatible with the current reader.

**Change**:

1. Add `"schemaVersion": 1` as the first key of the `artifact` dict in
   `publish_projections.py` (before `"generatedAt"`).
2. Add `"schemaVersion": 1` as the first key of the JSON object written by
   `publish_opening_squad.py` (before `"generatedAt"`).
3. In the web-app TypeScript layer that reads these artifacts (look for the
   `projections.json` import or fetch), assert `schemaVersion === 1` and raise
   a typed error if not. The schema version must be a compile-time constant in
   both the writer and the reader.

**Constraints**: The existing `generatedAt`, `season`, `throughGameweek`,
`basis`, `players`, and `clubs` fields must remain at the same nesting level.
The schema version is `1`; it must be incremented in any future PR that makes a
breaking field change. Do not add a migration. If the web app currently imports
the JSON file as a static asset, a TypeScript narrowing guard (not a runtime
`JSON.parse`) is sufficient.

**Tests first**: In `python/tests/test_next_match.py` and
`python/tests/test_opening_squad.py`, add:

- `test_published_projections_artifact_includes_schema_version` — call
  `main(["--output", str(tmp_path / "out.json")])` with mocked Supabase reads and
  assert `json.loads(out)["schemaVersion"] == 1`.
- `test_published_opening_squad_artifact_includes_schema_version` — same for the
  opening-squad writer.

**Done when**:

1. Both artifact files contain `"schemaVersion": 1` as their first key.
2. The web-app reader asserts the version and exposes a typed error if it mismatches.
3. `python -m pytest python/tests/test_next_match.py python/tests/test_opening_squad.py -q`
   exits 0.

**Validate**: `python -m pytest python/tests/test_next_match.py python/tests/test_opening_squad.py -q`
then `corepack pnpm typecheck`

---

## 68 — Make `SupabaseRestClient.__exit__` safe after partial initialisation (Impact: L)

**Files**: `python/fpl_andres/persistence/supabase.py` (`SupabaseRestClient.__init__`,
lines 71–89; `SupabaseRestClient.__exit__`, lines 94–100; `close`, lines 102–103),
`python/tests/test_persistence.py`

**Problem**: If `SupabaseRestClient.__init__` raises after
`self._credentials = credentials` (line 78) but before `self._client = httpx.Client(...)`
completes (e.g., because a custom `transport` argument is invalid), Python still
calls `__exit__` when the context manager is exited. `__exit__` calls `self.close()`
(line 100), which references `self._client` (line 103). Because `self._client`
was never assigned, this raises `AttributeError: 'SupabaseRestClient' object has
no attribute '_client'`, masking the original `__init__` exception. The audit cites
lines 102–103; the `__exit__` entry point is lines 94–100.

**Change**:

1. In `close()` (line 102), guard the `self._client.close()` call:
   `if hasattr(self, "_client"): self._client.close()`.
2. Alternatively, initialise `self._client` to `None` at the top of `__init__`
   and update `close()` to `if self._client is not None: self._client.close()`.
   The second approach is preferred for clarity and type-checker friendliness
   (update the annotation to `httpx.Client | None`).

**Constraints**: The normal execution path must be unchanged: `close()` must still
call `self._client.close()` when `_client` is fully initialised. No migration
needed.

**Tests first**: In `python/tests/test_persistence.py`, add:

- `test_exit_is_safe_when_init_fails_before_client_is_created` — subclass or
  mock `httpx.Client.__init__` to raise `ValueError`; assert that constructing a
  `SupabaseRestClient` inside a `with` block re-raises `ValueError` rather than
  `AttributeError`.

**Done when**:

1. An `__init__` failure raises the original exception, not `AttributeError`.
2. Normal `with SupabaseRestClient(...) as client:` usage is unchanged.
3. `python -m pytest python/tests/test_persistence.py -q` exits 0.

**Validate**: `python -m pytest python/tests/test_persistence.py -q`

---

## 69 — Round-trip validate ISO timestamps written by `team_state.py` (Impact: L)

**Files**: `python/fpl_andres/team_state.py` (`normalize_public_team_state`, lines
29–107; `resolve_team_state`, lines 110–169), `python/fpl_andres/contracts.py`
(`PublicTeamState`, ~line 135; `PlanningTeamState`, ~line 260),
`python/tests/test_team_state.py`

**Problem**: `normalize_public_team_state()` accepts a `state_as_of: datetime`
that is validated to be UTC-aware (line 37) and embeds it in a `PublicTeamState`
model. When the model is serialised to JSON (e.g., for caching or logging) via
`model.model_dump(mode="json")`, the `datetime` is rendered as an ISO string.
If it is later deserialised from that string, sub-second precision and the `+00:00`
vs `Z` suffix form may differ between Python versions and Pydantic configurations.
There is no existing round-trip assertion that checks
`parse(serialise(state_as_of)) == state_as_of`. A silently different timestamp on
read-back would break the `overrides.based_on_state_as_of == public.state_as_of`
equality check in `resolve_team_state()` (line 114).

**Change**:

1. Add a private helper `_assert_timestamp_roundtrip(dt: datetime) -> None` in
   `team_state.py` that serialises `dt` to ISO format with
   `dt.isoformat()`, parses it back with `datetime.fromisoformat()`, and raises
   `TeamStateContractError` if the result differs from `dt`.
2. Call `_assert_timestamp_roundtrip(state_as_of)` immediately after the UTC
   guard in `normalize_public_team_state()` (after line 38).
3. Ensure that `TeamStateOverrides.validate_overrides()` (in `contracts.py`,
   ~line 228) applies the same check to `based_on_state_as_of` and `updated_at`
   via a shared utility imported from a new `python/fpl_andres/time_utils.py` module
   so the check is not duplicated.

**Constraints**: The check must not change the stored datetime value, only assert
it survives the round-trip. If `datetime.fromisoformat` returns a timezone-aware
datetime with `+00:00` suffix while the original used `UTC` tzinfo directly,
those must compare equal (`datetime(2026, 8, 1, tzinfo=UTC) ==
datetime.fromisoformat("2026-08-01T00:00:00+00:00")` is `True` in Python 3.11+;
the test must confirm this). No migration needed.

**Tests first**: In `python/tests/test_team_state.py`, add:

- `test_normalize_raises_on_timestamp_that_does_not_survive_roundtrip` — patch
  `datetime.fromisoformat` to return a different datetime; assert
  `TeamStateContractError` is raised.
- `test_normalize_accepts_timestamps_that_survive_roundtrip` — supply normal UTC
  datetimes and assert no error.

**Done when**:

1. A `state_as_of` that does not survive ISO round-trip raises `TeamStateContractError`.
2. All existing `test_team_state.py` tests pass.
3. `python -m pytest python/tests/test_team_state.py -q` exits 0.

**Validate**: `python -m pytest python/tests/test_team_state.py -q`
