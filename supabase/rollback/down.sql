-- Forward-repair teardown for the whole schema. Audit item #100.
--
-- CI validated `supabase db reset` but never exercised undoing anything, so
-- nothing proved the schema could be torn down and rebuilt. That matters here
-- more than in most projects: the production bootstrap is an ordered SQL Editor
-- checklist, not `db push`, and 20 `create table`, 34 `create index`, 12
-- `create trigger` and 6 `create function` statements across the migration set
-- are written without `if not exists`. A file re-run after a partial paste
-- fails on the first object that already exists. This is the escape hatch: drop
-- to empty, then re-apply the migrations in order.
--
-- NOT a per-migration `down`. Reversing one migration in isolation invites
-- dropping a column that holds the only copy of some data. Teardown is
-- all-or-nothing on purpose, and destroys everything, which is why it lives in
-- its own directory rather than in `migrations/` where `db reset` would run it.
--
-- Order is reverse dependency. `cascade` is deliberately not used on the
-- tables: if a drop fails for an unlisted dependent, that dependent is
-- something this file has not been taught about, and silently removing it is
-- how a teardown script drifts out of step with the schema.
-- `python/tests/test_rollback_harness.py` fails if a migration creates an
-- object this file does not drop.

begin;

drop table if exists public.backtest_predictions;
drop table if exists public.backtest_runs;
drop table if exists public.crowd_snapshots;
drop table if exists public.declared_transfers;
drop table if exists public.analysis_requests;
drop table if exists public.model_promotion_decisions;
drop table if exists public.optimization_event_plans;
drop table if exists public.optimization_runs;
drop table if exists public.team_goal_projections;
drop table if exists public.projection_runs;
drop table if exists public.element_price_observations;
drop table if exists public.element_gameweek_stats;
drop table if exists public.fixtures;
drop table if exists public.elements;
drop table if exists public.teams;
drop table if exists public.seasons;
drop table if exists public.rules_snapshots;
drop table if exists public.source_snapshots;
drop table if exists public.workflow_run_events;
drop table if exists public.workflow_runs;

-- After the tables, because the immutability triggers depend on them.
drop function if exists private.record_workflow_run_transition();
drop function if exists private.reject_immutable_model_artifact_mutation();
drop function if exists private.reject_immutable_snapshot_mutation();
drop function if exists private.bigint_array_is_subset(bigint[], bigint[]);
drop function if exists private.bigint_arrays_are_disjoint(bigint[], bigint[]);
drop function if exists private.positive_unique_bigint_array(bigint[]);
drop function if exists private.unique_sha256_array(text[]);

drop schema if exists private;

-- pgcrypto is deliberately left in place. It lives in the `extensions` schema,
-- other Supabase machinery uses it, and dropping it is not this schema's
-- business.

commit;
