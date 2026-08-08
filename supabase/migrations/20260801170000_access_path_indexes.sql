-- Indexes and constraints that match how the tables are actually read, and a
-- trigger message that says which table refused a write.
--
-- Access-path indexes.

-- #99. The corpus is read one of two ways and neither was fully served.
--
-- `SeasonCorpus.before(gameweek)` scans a season up to a cutoff and needs the
-- element on the same row to avoid a heap fetch per row; the existing
-- (season, gameweek) index gives the range but not the payload.
--
-- The crosswalk and the projector walk one element across a whole season, which
-- the (element_code, season, gameweek) index serves only when the code is
-- known. Joining from `elements` gives element_id, not code.
create index element_gameweek_stats_season_gw_element_idx
    on public.element_gameweek_stats (season, gameweek, element_id);

create index element_gameweek_stats_season_element_idx
    on public.element_gameweek_stats (season, element_id, gameweek);

-- Fixture-grain reads: every row for one fixture, used when reconciling a
-- double gameweek against the fixture list.
create index element_gameweek_stats_fixture_idx
    on public.element_gameweek_stats (season, fixture_id);

-- #101. An impossible event id should not be recordable. FPL runs 1..38 in a
-- normal season; 2019/20 was suspended and resumed, running to 47, which the
-- history schema already allows, so the ceiling is 47 rather than 38.
alter table public.workflow_runs
    add constraint workflow_runs_event_id_range
    check (event_id is null or (event_id >= 1 and event_id <= 47));

-- #102. The run queue is read as "what is this workflow doing now", which the
-- existing (status, started_at) index cannot answer without scanning every
-- workflow's rows of that status.
create index workflow_runs_name_status_idx
    on public.workflow_runs (workflow_name, status, started_at desc);

-- #103. The immutability triggers raised a bare message, so a failed publish
-- said only that something was immutable, not what or why. Name the table and
-- the operation, and hint at the correct action.
create or replace function private.reject_immutable_snapshot_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    raise exception
        'evidence snapshots are immutable: % on %.% was rejected',
        tg_op, tg_table_schema, tg_table_name
        using hint = 'Insert a new snapshot; the superseded one stays for audit.';
end;
$$;

create or replace function private.reject_immutable_model_artifact_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    raise exception
        'model artifacts are immutable: % on %.% was rejected',
        tg_op, tg_table_schema, tg_table_name
        using hint = 'Publish a new artifact; the superseded one stays for audit.';
end;
$$;
