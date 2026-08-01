# 8. Database schema and migrations — work orders

Detailed briefs for items 97–108 of the [improvement audit](../../IMPROVEMENTS.md).
Each brief is self-contained: a sub-agent should be able to implement one item
from its brief alone.

Every brief obeys the repository rules: every schema change must be a **new** tracked migration
file with a timestamp prefix that follows the existing `supabase/migrations/` convention
(`YYYYMMDDHHmmss_<slug>.sql`). Applied migrations are never edited. Every new migration must pass
`python -m pytest python/tests/test_migrations.py -q` and the full `pnpm check` before being
committed. The hosted Supabase project is production and must never be modified by hand or
inspected through AI tools.

## 97 — Document the deny-all RLS posture and add named policies before any browser-readable table is introduced (Impact: H)

**Files**: All ten migration files in `supabase/migrations/`, `python/tests/test_migrations.py`,
`docs/RUNBOOK.md` or a new `docs/adr/` entry

**Problem**: Every table is created with `enable row level security` and `force row level security`
but with no `create policy` statement. This is the correct deny-all posture for a system whose
tables are written only by server-side workers, but it is undocumented. A future migration that
introduces a browser-readable table (e.g. a public leaderboard) could accidentally omit the
policy, leaving the table locked by RLS with no documented explanation.

**Change**:

1. Add a "Row-level security posture" section to `docs/RUNBOOK.md` (or a new ADR file under
   `docs/adr/`) explaining: every `public.*` table is deny-all by design; no `grant` and no
   `create policy` statements exist because all writes come from privileged service-role workers
   that bypass RLS. Before introducing any table readable by the `anon` or `authenticated` role,
   a named policy and an explicit `grant select` must be added in the same migration.
2. Add a top-of-file comment to `20260729180000_foundation.sql` (or a shared migration header
   convention document) that states the RLS convention.
3. In `python/tests/test_migrations.py`, add a test
   `test_no_migration_grants_without_an_explicit_policy` that iterates all migration files and
   asserts that any file containing `grant select` also contains at least one `create policy`.
4. Add a companion test `test_all_tables_enable_rls` that asserts every `create table public.*`
   statement in any migration has a matching `alter table public.* enable row level security` in
   the same or an earlier migration file.

**Constraints**: No DDL change is required; the migration files are unchanged. Only documentation
and Python policy tests are added. The new tests must be additive (they must not break any existing
passing test).

**Tests first**: The two Python tests listed in point 3 and 4 above must be written before the
documentation, confirming the current state is compliant.

**Done when**:

- `docs/RUNBOOK.md` contains the RLS posture explanation.
- `test_no_migration_grants_without_an_explicit_policy` exists and passes.
- `test_all_tables_enable_rls` exists and passes.
- `python -m pytest python/tests/test_migrations.py -q` passes with no failures.

**Validate**: `python -m pytest python/tests/test_migrations.py -q`

---

## 98 — Plan partitioning or archival strategy for `element_gameweek_stats` (Impact: H)

**Files**: `supabase/migrations/20260801120000_history_corpus.sql` (table definition at lines
82–142), `supabase/migrations/20260801140000_fixture_grain_and_event_range.sql` (primary-key
revision at line 39), `python/tests/test_migrations.py`, `docs/RUNBOOK.md`

**Problem**: `public.element_gameweek_stats` is a plain, unpartitioned heap table whose primary
key is now `(season, gameweek, element_id, fixture_id)` (after the fixture-grain migration). The
table grows by approximately `38 gameweeks × 620 players × n fixtures per player` per season. At
roughly 24 000 rows per season and no deletion or archival mechanism, the table will accumulate
unbounded rows over time. Query planners will begin preferring sequential scans over index scans as
the table grows past several hundred thousand rows without `VACUUM` statistics to narrow estimates.

**Change**:

1. Write a new migration (suggested filename:
   `20260802120000_element_gameweek_stats_partitioning_plan.sql`) that does **not** yet partition
   the table (partitioning an existing populated table requires a multi-step online migration
   strategy), but adds a `COMMENT ON TABLE` explaining the intended future partition key
   (`RANGE` on `season`) and referencing the runbook entry.
2. Add a "Corpus growth and archival" section to `docs/RUNBOOK.md` documenting: the expected row
   count per season, the intended partitioning strategy (native Postgres declarative range
   partitioning by `season`), and the steps required to perform the online migration (create the
   partitioned parent, attach each season as a partition, detach the old heap table).
3. Add a Python policy test `test_element_gameweek_stats_has_season_comment` that asserts the word
   "partition" or "archiv" appears in the `COMMENT ON TABLE public.element_gameweek_stats`
   statement across all migration files.

**Constraints**: No data migration or schema restructuring is attempted in this item; the
deliverable is a documented plan and a comment migration. A live partitioning migration belongs to a
separate, carefully tested milestone. Every migration file must still pass `supabase db reset`.

**Tests first**: Write `test_element_gameweek_stats_has_season_comment` before creating the
migration, confirm it fails, then create the migration to make it pass.

**Done when**:

- A new migration adds a `COMMENT ON TABLE` mentioning the partitioning plan.
- `docs/RUNBOOK.md` contains the corpus growth section.
- `test_element_gameweek_stats_has_season_comment` passes.
- `python -m pytest python/tests/test_migrations.py -q` passes.

**Validate**: `python -m pytest python/tests/test_migrations.py -q`

---

## 99 — Add composite indexes matching real access paths for `element_gameweek_stats` (Impact: H)

**Files**: `supabase/migrations/20260801120000_history_corpus.sql` (indexes at lines 136–141),
`supabase/migrations/20260801140000_fixture_grain_and_event_range.sql` (primary key revision),
`python/tests/test_migrations.py`

**Problem**: The current indexes on `element_gameweek_stats` are:
`element_gameweek_stats_code_idx` on `(element_code, season, gameweek)`,
`element_gameweek_stats_season_gw_idx` on `(season, gameweek)`, and
`element_gameweek_stats_snapshot_idx` on `(source_snapshot_id)`. The primary key after the
fixture-grain migration is `(season, gameweek, element_id, fixture_id)`. Two common access paths
are unindexed: fetching all stats for a player across seasons using their stable `element_code`
(the existing `element_gameweek_stats_code_idx` covers this, but only for specific gameweeks, not
for full cross-season lookups), and fetching all stats within a single gameweek ordered by a
scoring metric (currently a full `season, gameweek` scan with no covering columns). The audit
references `event_id` as a column name — **this is stale**: the column is named `gameweek` in the
actual schema.

**Change**:

1. Write a new migration (suggested filename:
   `20260802130000_element_gameweek_stats_access_indexes.sql`) that adds:
   - `create index concurrently if not exists element_gameweek_stats_element_code_season_idx on public.element_gameweek_stats (element_code, season)` — supports cross-season lookups by player code without a gameweek predicate.
   - `create index concurrently if not exists element_gameweek_stats_season_gw_points_idx on public.element_gameweek_stats (season, gameweek, total_points desc)` — supports ranking queries within a gameweek.
     Note: `concurrently` requires the migration to run outside a transaction block; prefix with
     `set local statement_timeout = '0'` and run as a separate transaction if the Supabase CLI
     requires it.
2. Add a Python policy test `test_element_gameweek_stats_has_cross_season_index` that asserts
   `element_gameweek_stats_element_code_season_idx` appears in the migration files.

**Constraints**: `concurrently` index creation cannot run inside a transaction block; verify the
Supabase CLI migration runner supports this before using it. If not, omit `concurrently` and add a
note to the runbook. The column is `gameweek`, not `event_id` — the audit wording is incorrect and
must not be reproduced in the migration DDL.

**Tests first**: Write the Python test first, confirm it fails, then write the migration.

**Done when**:

- Two new indexes exist: `element_gameweek_stats_element_code_season_idx` and
  `element_gameweek_stats_season_gw_points_idx`.
- `test_element_gameweek_stats_has_cross_season_index` passes.
- `python -m pytest python/tests/test_migrations.py -q` passes.

**Validate**: `python -m pytest python/tests/test_migrations.py -q`

---

## 100 — Add a migration rollback / forward-repair harness and test it in CI (Impact: H)

**Files**: `.github/workflows/ci.yml` ("Validate database migrations" step, lines ~44–48),
`python/tests/test_migrations.py`, `docs/RUNBOOK.md`

**Problem**: The CI job runs `supabase db reset --local` and `supabase db lint --local` but never
exercises undoing or selectively re-applying a single migration. A broken migration that was applied
to production but has since been superseded by a forward-repair migration cannot be validated in CI.
If a future migration contains a destructive DDL error that only manifests on partial rollback, CI
provides no safety net.

**Change**:

1. Add a new CI step "Test migration forward-repair" in `.github/workflows/ci.yml` that:
   - Runs `supabase db reset --local` to start clean.
   - Applies all migrations except the most recent one (`pnpm exec supabase migration repair`
     or by temporarily renaming the newest file).
   - Applies the newest migration to confirm it succeeds in isolation.
   - Confirms `supabase db lint --local --level warning` still passes after the targeted apply.
2. Add a new CI step "Test db lint on clean reset" that simply re-runs `supabase db lint --local
--level warning` after `supabase db reset` to catch lint regressions introduced by new
   migrations.
3. Document the forward-repair workflow in `docs/RUNBOOK.md` under a new "Migration recovery"
   section, explaining: (a) how to create a forward-repair migration if a bad migration reaches
   production; (b) how to test the repair locally; (c) the prohibition on editing applied
   migrations.
4. In `python/tests/test_migrations.py`, add `test_no_migration_contains_drop_table` that asserts
   no migration file outside a clearly named `*_drop_*` or `*_repair_*` slug contains a `drop
table` statement, preventing accidental destructive DDL.

**Constraints**: The Supabase CLI does not support true rollback by default — the strategy is
forward-repair only. CI must not break for any merged migration that has already been applied to
production. The new CI steps must run in the same job after `supabase db start`.

**Tests first**: Write `test_no_migration_contains_drop_table` before modifying CI, confirm it
passes on the current migration set.

**Done when**:

- CI includes a step that applies the newest migration in isolation after a partial reset.
- `test_no_migration_contains_drop_table` exists and passes.
- `docs/RUNBOOK.md` contains the migration recovery section.
- `python -m pytest python/tests/test_migrations.py -q` passes.

**Validate**: `python -m pytest python/tests/test_migrations.py -q`, then inspect CI output.

---

## 101 — Constrain `workflow_runs.event_id` to the real FPL event range (Impact: M)

**Files**: `supabase/migrations/20260729180000_foundation.sql` (line 8, `event_id` column),
`python/tests/test_migrations.py`

**Problem**: The `event_id` column in `workflow_runs` is defined as
`integer check (event_id is null or event_id > 0)`. The only lower bound is `> 0`; there is no
upper bound. A workflow run recorded against `event_id = 99` or `event_id = 1000` would pass the
constraint even though FPL gameweeks run from 1 to 38 in a normal season (and up to 47 in the
disrupted 2019/20 season, per the fixture-grain migration's explicit `event between 1 and 47`
check). An out-of-range `event_id` would be silently stored with no validation error.

**Change**:

1. Write a new migration (suggested filename:
   `20260802140000_workflow_runs_event_id_range.sql`) that alters the check constraint:
   `alter table public.workflow_runs drop constraint if exists <existing_check_name>;`
   then adds:
   `alter table public.workflow_runs add constraint workflow_runs_event_id_range check (event_id is null or event_id between 1 and 47);`
   The upper bound of 47 matches the fixture-grain migration's established precedent for disrupted
   seasons.
2. Name the new constraint `workflow_runs_event_id_range` to follow the
   `<table>_<column>_<purpose>` naming convention used in other migrations.
3. Add a Python policy test `test_workflow_runs_event_id_is_range_constrained` that asserts the
   string `event_id between 1 and 47` appears in the combined migration SQL.

**Constraints**: The existing `workflow_runs_finished_state` and `workflow_runs_idempotency`
constraints must remain intact. This is a new constraint migration — do not edit
`20260729180000_foundation.sql`. The migration must be idempotent (`drop constraint if exists`
before `add constraint`).

**Tests first**: Write `test_workflow_runs_event_id_is_range_constrained` before writing the
migration, confirm it fails, then write the migration to make it pass.

**Done when**:

- A new migration adds `constraint workflow_runs_event_id_range check (event_id is null or event_id between 1 and 47)`.
- `test_workflow_runs_event_id_is_range_constrained` exists and passes.
- `python -m pytest python/tests/test_migrations.py -q` passes.

**Validate**: `python -m pytest python/tests/test_migrations.py -q`

---

## 102 — Add a `(workflow_name, status)` index for run-queue lookups (Impact: M)

**Files**: `supabase/migrations/20260729180000_foundation.sql` (index at line 20:
`workflow_runs_status_started_idx on public.workflow_runs (status, started_at desc)`),
`python/tests/test_migrations.py`

**Problem**: The existing index `workflow_runs_status_started_idx` is defined on `(status,
started_at desc)`. A worker that polls for pending runs of a specific workflow (e.g.
`where workflow_name = 'projection' and status = 'pending'`) must filter `workflow_name` as a
residual predicate after the index scan, since `workflow_name` is not in the index. In a busy
system with many workflow names and statuses, this degrades to scanning all pending rows rather than
reading only the relevant workflow's pending rows.

**Change**:

1. Write a new migration (suggested filename:
   `20260802150000_workflow_runs_queue_index.sql`) that adds:
   `create index if not exists workflow_runs_name_status_idx on public.workflow_runs (workflow_name, status, started_at desc);`
   This covers the `where workflow_name = $1 and status = $2 order by started_at desc` access
   pattern directly.
2. Name the index `workflow_runs_name_status_idx` consistent with the
   `<table>_<descriptive_columns>_idx` pattern used throughout the migrations.
3. Add a Python policy test `test_workflow_runs_has_name_status_index` that asserts
   `workflow_runs_name_status_idx` appears in the migration files.

**Constraints**: The existing `workflow_runs_status_started_idx` must **not** be dropped — it may
serve other queries (e.g. a dashboard showing all pending/running rows regardless of workflow name).
The new index is additive. The migration must be idempotent (`create index if not exists`).

**Tests first**: Write `test_workflow_runs_has_name_status_index` before writing the migration,
confirm it fails, then write the migration.

**Done when**:

- A new migration creates `workflow_runs_name_status_idx` on `(workflow_name, status, started_at desc)`.
- `test_workflow_runs_has_name_status_index` exists and passes.
- `python -m pytest python/tests/test_migrations.py -q` passes.

**Validate**: `python -m pytest python/tests/test_migrations.py -q`

---

## 103 — Make immutability-trigger errors name the table and operation (Impact: M)

**Files**: `supabase/migrations/20260729183000_evidence_snapshots.sql`
(`private.reject_immutable_snapshot_mutation`, line 39; `raise exception` at line 45),
`supabase/migrations/20260730120000_projection_artifacts.sql`
(`private.reject_immutable_model_artifact_mutation`, line 116; `raise exception` at line 122),
`python/tests/test_migrations.py`

**Problem**: Two trigger functions are shared across multiple tables. `private.reject_immutable_snapshot_mutation` fires on both `source_snapshots` and `rules_snapshots`;
`private.reject_immutable_model_artifact_mutation` fires on `projection_runs`,
`team_goal_projections`, `model_promotion_decisions`, `optimization_runs`,
`optimization_event_plans`, `backtest_runs`, `backtest_predictions`, and `crowd_snapshots`. Both
functions raise a generic message (`'evidence snapshots are immutable'` and `'model artifacts are
immutable'` respectively) that does not name which table was mutated or which operation was
attempted. When a failed publish raises one of these errors, the application log shows the generic
string with no indication of the operation or the table.

**Change**:

1. Write a new migration (suggested filename:
   `20260802160000_immutable_trigger_error_detail.sql`) that replaces both trigger functions in
   place using `create or replace function`:
   - `private.reject_immutable_snapshot_mutation` should raise:
     `raise exception '% on % is forbidden: evidence is immutable', TG_OP, TG_TABLE_NAME;`
   - `private.reject_immutable_model_artifact_mutation` should raise:
     `raise exception '% on % is forbidden: artifact is immutable', TG_OP, TG_TABLE_NAME;`
     Both changes use the PL/pgSQL special variables `TG_OP` (operation: `'UPDATE'` or `'DELETE'`)
     and `TG_TABLE_NAME` (the table name the trigger fired on).
2. No triggers need to be dropped or re-created; the functions are used by reference, so replacing
   the function body is sufficient.
3. Add a Python policy test `test_immutable_trigger_functions_include_tg_table_name` that asserts
   both trigger function bodies contain `tg_table_name` and `tg_op` (case-insensitive).

**Constraints**: `create or replace function` is safe to apply to a function already in use —
all triggers referencing the function will automatically use the new body without re-creation.
The migration must still pass `alter table * enable row level security` policy checks.

**Tests first**: Write `test_immutable_trigger_functions_include_tg_table_name` before writing
the migration, confirm it fails, then write the migration.

**Done when**:

- Both trigger functions' `raise exception` messages include `TG_OP` and `TG_TABLE_NAME`.
- `test_immutable_trigger_functions_include_tg_table_name` exists and passes.
- `python -m pytest python/tests/test_migrations.py -q` passes.

**Validate**: `python -m pytest python/tests/test_migrations.py -q`

---

## 104 — Define a retention and revision policy for `element_price_observations` and other append-only observation tables (Impact: M)

**Files**: `supabase/migrations/20260801120000_history_corpus.sql` (`element_price_observations`
at lines 143–160), `docs/RUNBOOK.md`

**Problem**: `element_price_observations` is an append-only table with primary key `(season,
element_id, observed_on)`, accumulating one row per player per day during an active season.
`element_gameweek_stats` (covered by item 98) has the same issue. Neither table has a documented
retention window, a deletion schedule, or a policy for what happens to observations when a player
is deleted from FPL mid-season. The `source_snapshot_id` foreign key links each row to a
provenance snapshot but provides no basis for bulk expiry.

**Change**:

1. Add a "Observation table retention" section to `docs/RUNBOOK.md` documenting:
   - The expected row count per season for `element_price_observations` (approximately
     `38 weeks × 7 days × 620 players ≈ 165 000 rows/season`).
   - The intended retention window: retain all seasons indefinitely until a size threshold
     (suggested: 10 M rows) triggers a review; document this threshold.
   - The revision policy: because FPL does not revise historical price data, rows are effectively
     immutable once written. A duplicate `(season, element_id, observed_on)` insert is a primary
     key conflict and is rejected.
   - The deletion policy: rows for a retired season may be archived to cold storage and deleted
     after the `source_snapshots` provenance record is preserved.
2. Write a new migration (suggested filename:
   `20260802170000_price_observations_table_comment.sql`) that adds a
   `COMMENT ON TABLE public.element_price_observations` explaining the retention policy.
3. Add a Python policy test `test_price_observations_has_retention_comment` that asserts the word
   "retain" or "retention" appears in the `COMMENT ON TABLE public.element_price_observations`
   across the migration files.

**Constraints**: No DDL change to the table structure is required. The migration adds only a
comment. The documentation must not mention specific row counts that could become stale; prefer
order-of-magnitude estimates.

**Tests first**: Write `test_price_observations_has_retention_comment` before writing the
migration.

**Done when**:

- `docs/RUNBOOK.md` contains the observation table retention section.
- A new migration adds a comment to `element_price_observations`.
- `test_price_observations_has_retention_comment` passes.
- `python -m pytest python/tests/test_migrations.py -q` passes.

**Validate**: `python -m pytest python/tests/test_migrations.py -q`

---

## 105 — Add an audit trail for `workflow_runs` status transitions (Impact: M)

**Files**: `supabase/migrations/20260729180000_foundation.sql` (`workflow_runs` table),
`python/tests/test_migrations.py`

**Problem**: `workflow_runs` stores the current status of each job run in a single mutable row.
When a run transitions from `pending` → `running` → `succeeded`, the intermediate states are
overwritten with no history. A failed run that was retried and eventually succeeded leaves no
evidence of the failure or its duration. Diagnosing job instability (e.g. intermittent `failed →
running → succeeded` cycles) requires correlating external log timestamps with the final row state,
which is unreliable.

**Change**:

1. Write a new migration (suggested filename:
   `20260802180000_workflow_run_status_log.sql`) that creates a companion table
   `public.workflow_run_status_log` with columns: `id uuid primary key default
extensions.gen_random_uuid()`, `run_id uuid not null references
public.workflow_runs(id) on delete cascade`, `old_status text`, `new_status text not null`,
   `changed_at timestamptz not null default now()`, `changed_by text`. Apply RLS with `enable` and
   `force row level security` and no policy (deny-all, consistent with the rest of the schema).
2. Add a trigger `private.log_workflow_run_status_change()` in the same migration that fires
   `after update of status on public.workflow_runs for each row when (old.status is distinct from
new.status)` and inserts a row into `workflow_run_status_log`.
3. The `changed_by` column should default to `current_user` to record the Postgres role that
   performed the update.
4. Add a Python policy test `test_workflow_run_status_log_is_rls_protected` that asserts both
   `enable row level security` and `force row level security` appear for
   `workflow_run_status_log`, and that no `create policy` or `grant` appears in the same migration.

**Constraints**: The new table must cascade-delete when the parent `workflow_runs` row is deleted.
The trigger must not fire on `insert` — only on `update` of the `status` column. All existing
`workflow_runs` tests in `python/tests/test_migrations.py` must remain green.

**Tests first**: Write `test_workflow_run_status_log_is_rls_protected` before writing the
migration.

**Done when**:

- `public.workflow_run_status_log` exists with RLS enabled and no policies.
- A trigger inserts a log row on every `status` change.
- `test_workflow_run_status_log_is_rls_protected` passes.
- `python -m pytest python/tests/test_migrations.py -q` passes.

**Validate**: `python -m pytest python/tests/test_migrations.py -q`

---

## 106 — Add referential integrity or a reconciliation job for `source_snapshots.storage_path` (Impact: L)

**Files**: `supabase/migrations/20260729183000_evidence_snapshots.sql` (`source_snapshots` table,
`storage_path` column at line 10), `docs/RUNBOOK.md`

**Problem**: `source_snapshots.storage_path` is a plain `text` column with a length check (`1 to
1024 characters`) but no foreign-key relationship to Supabase Storage objects. If a storage object
is deleted (manually, via a lifecycle policy, or by accident), the corresponding
`source_snapshots` row becomes an orphan: `storage_path` points to a non-existent object, and
`content_hash` can never be verified. The `source_snapshots` immutability trigger prevents the row
from being deleted or corrected, so the orphan is permanent.

**Change**:

1. Postgres cannot natively enforce a foreign key into Supabase Storage's internal
   `storage.objects` table from the `public` schema (it is a separate schema managed by the Supabase
   platform). Instead, document the limitation in `docs/RUNBOOK.md` under a "Storage integrity"
   section.
2. Add a reconciliation script specification to `docs/RUNBOOK.md`: a scheduled worker (suggested:
   a Python script triggered by a `workflow_runs` entry) that periodically queries
   `source_snapshots` and checks each `storage_path` against the Storage API, logging any missing
   objects to a designated alerting channel. The script must be read-only against the database; it
   must not delete or mutate `source_snapshots` rows.
3. Add a `COMMENT ON COLUMN public.source_snapshots.storage_path` to a new migration
   (suggested filename: `20260802190000_source_snapshots_storage_path_comment.sql`) explaining
   that the path refers to a Supabase Storage object and that referential integrity is maintained
   by the reconciliation worker described in the runbook.
4. Add a Python policy test `test_source_snapshots_storage_path_has_comment` that asserts the
   string `comment on column public.source_snapshots.storage_path` appears in the migration files.

**Constraints**: No DDL change to `source_snapshots` is possible (the immutability trigger
prevents updates; and altering a column that is used in a unique constraint would require a
concurrent re-index). The migration must add only a comment. The reconciliation worker
specification is a design document only — no implementation is required in this item.

**Tests first**: Write `test_source_snapshots_storage_path_has_comment` before writing the
migration.

**Done when**:

- A new migration adds a `COMMENT ON COLUMN` to `storage_path`.
- `docs/RUNBOOK.md` contains the storage integrity and reconciliation section.
- `test_source_snapshots_storage_path_has_comment` passes.
- `python -m pytest python/tests/test_migrations.py -q` passes.

**Validate**: `python -m pytest python/tests/test_migrations.py -q`

---

## 107 — Publish a schema reference (ERD plus column notes) generated from migrations (Impact: L)

**Files**: All ten migration files under `supabase/migrations/`, `docs/` (new file), CI workflow
`.github/workflows/ci.yml`

**Problem**: Ten migration files collectively define the schema for `workflow_runs`,
`source_snapshots`, `rules_snapshots`, `projection_runs`, `team_goal_projections`,
`model_promotion_decisions`, `optimization_runs`, `optimization_event_plans`, `seasons`, `teams`,
`elements`, `fixtures`, `element_gameweek_stats`, `element_price_observations`,
`backtest_runs`, `backtest_predictions`, and `crowd_snapshots`. There is no single readable view.
A contributor wanting to understand the data model must read all ten files in order. The
`COMMENT ON TABLE` statements in the migrations are the only column-level notes available, and they
are not aggregated anywhere.

**Change**:

1. Create `docs/SCHEMA.md` as a hand-maintained (not auto-generated) schema reference. For each
   table, include: table purpose (drawn from the `COMMENT ON TABLE`), primary key, foreign keys,
   notable constraints, and a one-line description of each non-obvious column. Order tables by
   their introducing migration timestamp.
2. Add a "Schema reference" link in `docs/RUNBOOK.md` pointing to `docs/SCHEMA.md`.
3. In `.github/workflows/ci.yml`, add a step that asserts `docs/SCHEMA.md` exists and is
   non-empty, as a lightweight reminder to update it when migrations are added. The step should
   use a simple `test -s docs/SCHEMA.md` shell check, not a diff or content comparison.
4. Add a Python policy test `test_schema_doc_mentions_all_public_tables` that extracts every
   `create table public.\w+` name from all migration files and asserts each name appears in
   `docs/SCHEMA.md`.

**Constraints**: The schema reference must be hand-maintained, not auto-generated from `pg_catalog`,
because the production database must never be queried by AI tools. Every table name that appears in
a `create table public.*` statement must be covered. The document must be updated whenever a new
migration adds a table — the Python test enforces this.

**Tests first**: Write `test_schema_doc_mentions_all_public_tables` before writing the document,
confirm it fails (because `docs/SCHEMA.md` does not exist yet), then write the document.

**Done when**:

- `docs/SCHEMA.md` exists and covers all 18+ public tables.
- `test_schema_doc_mentions_all_public_tables` passes.
- CI includes a non-empty check for `docs/SCHEMA.md`.
- `python -m pytest python/tests/test_migrations.py -q` passes.

**Validate**: `python -m pytest python/tests/test_migrations.py -q`, then `corepack pnpm check`.

---

## 108 — Document naming conventions for tables, indexes, constraints, and triggers (Impact: L)

**Files**: All migration files (as evidence sources), `docs/RUNBOOK.md` or a new
`docs/adr/` entry, `python/tests/test_migrations.py`

**Problem**: Ten migrations have established a consistent naming pattern through usage, but it is
nowhere written down. The observed conventions are: tables use `snake_case` plural nouns (e.g.
`workflow_runs`, `element_gameweek_stats`); indexes use `<table>_<column(s)>_idx`; constraints use
`<table>_<purpose>` (e.g. `workflow_runs_idempotency`, `workflow_runs_finished_state`); trigger
functions use `private.reject_immutable_<noun>_mutation()`; triggers use `<table>_are_immutable`.
Without documentation, future migrations may deviate (e.g. using `tbl_` prefixes or inconsistent
`_index` vs `_idx` suffixes), making the schema harder to navigate.

**Change**:

1. Add a "Migration naming conventions" section to `docs/RUNBOOK.md` (or a new ADR under
   `docs/adr/naming-conventions.md`) specifying:
   - **Tables**: plural `snake_case` noun, no prefix.
   - **Indexes**: `<table_name>_<column_or_purpose>_idx`.
   - **Unique constraints**: `<table_name>_<purpose>` (no `_idx` suffix).
   - **Check constraints**: `<table_name>_<column_or_condition>` (no `_check` suffix).
   - **Trigger functions**: `private.<verb>_<noun>_<context>()` in the `private` schema.
   - **Triggers**: `<table_name>_are_<adjective>` or `<table_name>_<verb>_<noun>`.
   - **Migration filenames**: `YYYYMMDDHHmmss_<slug>.sql` where `<slug>` is a lowercase
     underscore-separated description of the migration's primary purpose.
2. Add a Python policy test `test_all_indexes_follow_naming_convention` that iterates all migration
   files and asserts every `create index` statement produces a name matching
   `[a-z][a-z0-9_]*_idx`.
3. Add a companion test `test_all_migration_filenames_follow_convention` that asserts every `.sql`
   filename in `supabase/migrations/` matches `^\d{14}_[a-z][a-z0-9_]*\.sql$`.

**Constraints**: No DDL change is required; the existing migrations already comply with the
conventions being documented. The tests must be purely additive and must all pass against the
current migration set without modification.

**Tests first**: Write both Python tests before writing the documentation, confirm they pass
against the existing migrations (they should, since the conventions are derived from the existing
files).

**Done when**:

- `docs/RUNBOOK.md` (or an ADR) contains the naming conventions section covering tables, indexes,
  constraints, triggers, and migration filenames.
- `test_all_indexes_follow_naming_convention` exists and passes.
- `test_all_migration_filenames_follow_convention` exists and passes.
- `python -m pytest python/tests/test_migrations.py -q` passes.

**Validate**: `python -m pytest python/tests/test_migrations.py -q`
