-- 2026-07-30 v0.5.1 hardening: cover foreign-key columns that lacked their own
-- indexes. Postgres does not auto-index FK columns, so cascading DELETE and
-- JOIN-then-filter queries against workflow_runs or source_snapshots would
-- degrade to sequential scans on the referrer. CONCURRENTLY plus IF NOT EXISTS
-- lets the SQL Editor apply this to production without blocking writers and
-- makes the file safe to re-run.

create index concurrently if not exists rules_snapshots_source_snapshot_idx
    on public.rules_snapshots (source_snapshot_id);

create index concurrently if not exists projection_runs_workflow_run_idx
    on public.projection_runs (workflow_run_id);

create index concurrently if not exists model_promotion_decisions_workflow_run_idx
    on public.model_promotion_decisions (workflow_run_id);

create index concurrently if not exists optimization_runs_workflow_run_idx
    on public.optimization_runs (workflow_run_id);

comment on index public.rules_snapshots_source_snapshot_idx is
    'Covers the FK to public.source_snapshots so cascade and reverse joins stay indexed.';
comment on index public.projection_runs_workflow_run_idx is
    'Covers the FK to public.workflow_runs so cascade and reverse joins stay indexed.';
comment on index public.model_promotion_decisions_workflow_run_idx is
    'Covers the FK to public.workflow_runs so cascade and reverse joins stay indexed.';
comment on index public.optimization_runs_workflow_run_idx is
    'Covers the FK to public.workflow_runs so cascade and reverse joins stay indexed.';
