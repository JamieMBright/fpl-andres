create function private.positive_unique_bigint_array(items bigint[])
returns boolean
language sql
immutable
strict
set search_path = ''
as $$
    select not exists (
        select 1
        from pg_catalog.unnest(items) as expanded(item)
        where item <= 0
    )
    and pg_catalog.cardinality(items) = (
        select pg_catalog.count(distinct item)::integer
        from pg_catalog.unnest(items) as expanded(item)
    );
$$;

create function private.unique_sha256_array(items text[])
returns boolean
language sql
immutable
strict
set search_path = ''
as $$
    select not exists (
        select 1
        from pg_catalog.unnest(items) as expanded(item)
        where item !~ '^sha256:[0-9a-f]{64}$'
    )
    and pg_catalog.cardinality(items) = (
        select pg_catalog.count(distinct item)::integer
        from pg_catalog.unnest(items) as expanded(item)
    );
$$;

create function private.bigint_array_is_subset(candidate bigint[], container bigint[])
returns boolean
language sql
immutable
strict
set search_path = ''
as $$
    select not exists (
        select 1
        from pg_catalog.unnest(candidate) as expanded(item)
        where not (item = any(container))
    );
$$;

create function private.bigint_arrays_are_disjoint(left_items bigint[], right_items bigint[])
returns boolean
language sql
immutable
strict
set search_path = ''
as $$
    select not exists (
        select 1
        from pg_catalog.unnest(left_items) as expanded(item)
        where item = any(right_items)
    );
$$;

revoke all on function private.positive_unique_bigint_array(bigint[]) from public;
revoke all on function private.positive_unique_bigint_array(bigint[]) from anon;
revoke all on function private.positive_unique_bigint_array(bigint[]) from authenticated;
revoke all on function private.unique_sha256_array(text[]) from public;
revoke all on function private.unique_sha256_array(text[]) from anon;
revoke all on function private.unique_sha256_array(text[]) from authenticated;
revoke all on function private.bigint_array_is_subset(bigint[], bigint[]) from public;
revoke all on function private.bigint_array_is_subset(bigint[], bigint[]) from anon;
revoke all on function private.bigint_array_is_subset(bigint[], bigint[]) from authenticated;
revoke all on function private.bigint_arrays_are_disjoint(bigint[], bigint[]) from public;
revoke all on function private.bigint_arrays_are_disjoint(bigint[], bigint[]) from anon;
revoke all on function private.bigint_arrays_are_disjoint(bigint[], bigint[]) from authenticated;

create table public.optimization_runs (
    id uuid primary key default extensions.gen_random_uuid(),
    workflow_run_id uuid not null references public.workflow_runs(id),
    entry_id bigint not null check (entry_id > 0),
    season text not null check (season ~ '^20[0-9]{2}-[0-9]{2}$'),
    initial_event integer not null check (initial_event between 1 and 38),
    prediction_cutoff timestamptz not null,
    plan_kind text not null check (plan_kind in ('quick', 'scheduled')),
    solver text not null check (solver in ('quick-beam', 'scipy-highs')),
    solver_status text not null check (solver_status in ('bounded', 'optimal')),
    objective text not null check (objective = 'expected_value'),
    chip_scenario text not null check (chip_scenario = 'none'),
    price_scenario text not null check (
        price_scenario in ('current_prices', 'provided_event_prices')
    ),
    evidence_level text not null check (evidence_level in ('inferred', 'experimental')),
    data_available_at timestamptz not null,
    public_state_as_of timestamptz not null,
    public_data_available_at timestamptz not null,
    overrides_updated_at timestamptz not null,
    manager_overrides_hash text not null check (
        manager_overrides_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    public_source_hashes text[] not null check (
        cardinality(public_source_hashes) > 0
        and private.unique_sha256_array(public_source_hashes)
    ),
    source_hashes text[] not null check (
        cardinality(source_hashes) > 0
        and private.unique_sha256_array(source_hashes)
    ),
    rules_hash text not null check (rules_hash ~ '^sha256:[0-9a-f]{64}$'),
    input_hash text not null check (input_hash ~ '^sha256:[0-9a-f]{64}$'),
    reason_codes text[] not null check (cardinality(reason_codes) > 0),
    configuration jsonb not null,
    created_at timestamptz not null default now(),
    constraint optimization_runs_public_chronology check (
        public_state_as_of <= public_data_available_at
    ),
    constraint optimization_runs_override_chronology check (
        public_state_as_of <= overrides_updated_at
    ),
    constraint optimization_runs_evidence_cutoff check (
        data_available_at <= prediction_cutoff
        and public_data_available_at <= prediction_cutoff
        and overrides_updated_at <= prediction_cutoff
    ),
    constraint optimization_runs_solver_kind check (
        (plan_kind = 'quick' and solver = 'quick-beam' and solver_status = 'bounded')
        or (plan_kind = 'scheduled' and solver = 'scipy-highs' and solver_status = 'optimal')
    ),
    constraint optimization_runs_price_scenario check (
        (plan_kind = 'quick' and price_scenario = 'current_prices')
        or (plan_kind = 'scheduled' and price_scenario = 'provided_event_prices')
    ),
    constraint optimization_runs_identity unique (
        entry_id,
        initial_event,
        prediction_cutoff,
        plan_kind,
        input_hash
    )
);

create index optimization_runs_entry_cutoff_idx
    on public.optimization_runs (entry_id, prediction_cutoff desc);

create table public.optimization_event_plans (
    id uuid primary key default extensions.gen_random_uuid(),
    optimization_run_id uuid not null references public.optimization_runs(id),
    event integer not null check (event between 1 and 38),
    objective_weight double precision not null check (objective_weight > 0),
    squad_size integer not null check (squad_size > 0),
    lineup_size integer not null check (lineup_size >= 2 and lineup_size <= squad_size),
    squad_element_ids bigint[] not null check (
        cardinality(squad_element_ids) = squad_size
        and private.positive_unique_bigint_array(squad_element_ids)
    ),
    starter_element_ids bigint[] not null check (
        cardinality(starter_element_ids) = lineup_size
        and private.positive_unique_bigint_array(starter_element_ids)
    ),
    bench_element_ids bigint[] not null check (
        cardinality(bench_element_ids) = squad_size - lineup_size
        and private.positive_unique_bigint_array(bench_element_ids)
    ),
    captain_element_id bigint not null check (captain_element_id > 0),
    vice_captain_element_id bigint not null check (vice_captain_element_id > 0),
    transfers_in bigint[] not null default '{}'::bigint[],
    transfers_out bigint[] not null default '{}'::bigint[],
    free_transfers_before integer not null check (free_transfers_before >= 0),
    free_transfers_used integer not null check (free_transfers_used >= 0),
    paid_transfers integer not null check (paid_transfers >= 0),
    free_transfers_next_event integer not null check (free_transfers_next_event >= 0),
    transfer_cost_points integer not null check (transfer_cost_points >= 0),
    projected_points_before_cost double precision not null,
    net_expected_points double precision not null,
    bank_after_tenths integer not null check (bank_after_tenths >= 0),
    created_at timestamptz not null default now(),
    constraint optimization_event_plans_captains check (
        captain_element_id <> vice_captain_element_id
        and captain_element_id = any(starter_element_ids)
        and vice_captain_element_id = any(starter_element_ids)
    ),
    constraint optimization_event_plans_partition check (
        private.bigint_array_is_subset(starter_element_ids, squad_element_ids)
        and private.bigint_array_is_subset(bench_element_ids, squad_element_ids)
        and private.bigint_arrays_are_disjoint(starter_element_ids, bench_element_ids)
    ),
    constraint optimization_event_plans_transfers check (
        cardinality(transfers_in) = cardinality(transfers_out)
        and private.positive_unique_bigint_array(transfers_in)
        and private.positive_unique_bigint_array(transfers_out)
        and private.bigint_arrays_are_disjoint(transfers_in, transfers_out)
        and private.bigint_array_is_subset(transfers_in, squad_element_ids)
        and private.bigint_arrays_are_disjoint(transfers_out, squad_element_ids)
        and free_transfers_used + paid_transfers = cardinality(transfers_in)
        and free_transfers_used <= free_transfers_before
    ),
    constraint optimization_event_plans_points check (
        net_expected_points = projected_points_before_cost - transfer_cost_points
    ),
    constraint optimization_event_plans_event unique (optimization_run_id, event)
);

create index optimization_event_plans_run_event_idx
    on public.optimization_event_plans (optimization_run_id, event);

alter table public.optimization_runs enable row level security;
alter table public.optimization_runs force row level security;
alter table public.optimization_event_plans enable row level security;
alter table public.optimization_event_plans force row level security;

create trigger optimization_runs_are_immutable
before update or delete on public.optimization_runs
for each row execute function private.reject_immutable_model_artifact_mutation();

create trigger optimization_event_plans_are_immutable
before update or delete on public.optimization_event_plans
for each row execute function private.reject_immutable_model_artifact_mutation();

comment on table public.optimization_runs is
    'Immutable plan identity and provenance. Manager overrides are represented only by a hash.';
comment on table public.optimization_event_plans is
    'Immutable structured decisions emitted by a bounded quick or optimal scheduled plan.';