create table public.projection_runs (
    id uuid primary key default extensions.gen_random_uuid(),
    workflow_run_id uuid not null references public.workflow_runs(id),
    season text not null check (season ~ '^20[0-9]{2}-[0-9]{2}$'),
    event integer not null check (event between 1 and 38),
    prediction_cutoff timestamptz not null,
    model_name text not null check (char_length(model_name) between 1 and 100),
    model_version text not null check (char_length(model_version) between 1 and 100),
    evidence_level text not null check (
        evidence_level in ('observed', 'inferred', 'experimental', 'unavailable')
    ),
    configuration jsonb not null,
    input_hash text not null check (input_hash ~ '^sha256:[0-9a-f]{64}$'),
    created_at timestamptz not null default now(),
    constraint projection_runs_identity unique (
        season,
        event,
        prediction_cutoff,
        model_name,
        model_version,
        input_hash
    ),
    constraint projection_runs_cutoff_key unique (id, prediction_cutoff)
);

create table public.team_goal_projections (
    id uuid primary key default extensions.gen_random_uuid(),
    projection_run_id uuid not null,
    prediction_cutoff timestamptz not null,
    home_team_id integer not null check (home_team_id > 0),
    away_team_id integer not null check (away_team_id > 0),
    home_expected_goals double precision not null check (home_expected_goals >= 0),
    away_expected_goals double precision not null check (away_expected_goals >= 0),
    evidence_level text not null check (
        evidence_level in ('observed', 'inferred', 'experimental', 'unavailable')
    ),
    reason_codes text[] not null check (cardinality(reason_codes) > 0),
    data_available_at timestamptz not null,
    source_hashes text[] not null check (cardinality(source_hashes) > 0),
    created_at timestamptz not null default now(),
    constraint team_goal_projections_teams_differ check (home_team_id <> away_team_id),
    constraint team_goal_projections_chronology check (
        data_available_at <= prediction_cutoff
    ),
    constraint team_goal_projections_run_cutoff foreign key (
        projection_run_id,
        prediction_cutoff
    ) references public.projection_runs(id, prediction_cutoff),
    constraint team_goal_projections_fixture unique (
        projection_run_id,
        home_team_id,
        away_team_id
    )
);

create index team_goal_projections_run_idx
    on public.team_goal_projections (projection_run_id);

create table public.model_promotion_decisions (
    id uuid primary key default extensions.gen_random_uuid(),
    workflow_run_id uuid not null references public.workflow_runs(id),
    season text not null check (season ~ '^20[0-9]{2}-[0-9]{2}$'),
    decision_cutoff timestamptz not null,
    baseline_model text not null check (char_length(baseline_model) between 1 and 100),
    baseline_version text not null check (char_length(baseline_version) between 1 and 100),
    candidate_model text not null check (char_length(candidate_model) between 1 and 100),
    candidate_version text not null check (char_length(candidate_version) between 1 and 100),
    metric_name text not null check (char_length(metric_name) between 1 and 100),
    baseline_point double precision not null check (baseline_point >= 0),
    candidate_point double precision not null check (candidate_point >= 0),
    paired_improvement double precision not null,
    paired_improvement_lower double precision not null,
    paired_improvement_upper double precision not null,
    confidence double precision not null check (confidence > 0 and confidence < 1),
    resamples integer not null check (resamples >= 0),
    seed bigint not null,
    sample_size integer not null check (sample_size > 0),
    minimum_sample_size integer not null check (minimum_sample_size > 0),
    promoted boolean not null,
    reason_codes text[] not null check (cardinality(reason_codes) > 0),
    data_available_at timestamptz not null,
    source_hashes text[] not null check (cardinality(source_hashes) > 0),
    evaluation_hash text not null check (evaluation_hash ~ '^sha256:[0-9a-f]{64}$'),
    created_at timestamptz not null default now(),
    constraint model_promotion_decisions_interval check (
        paired_improvement_lower <= paired_improvement_upper
    ),
    constraint model_promotion_decisions_chronology check (
        data_available_at <= decision_cutoff
    ),
    constraint model_promotion_decisions_consistent check (
        promoted = (
            sample_size >= minimum_sample_size
            and paired_improvement_lower > 0
        )
    ),
    constraint model_promotion_decisions_resamples check (
        resamples > 0 or sample_size < minimum_sample_size
    ),
    constraint model_promotion_decisions_evaluation unique (
        candidate_model,
        candidate_version,
        baseline_model,
        baseline_version,
        evaluation_hash
    )
);

alter table public.projection_runs enable row level security;
alter table public.projection_runs force row level security;
alter table public.team_goal_projections enable row level security;
alter table public.team_goal_projections force row level security;
alter table public.model_promotion_decisions enable row level security;
alter table public.model_promotion_decisions force row level security;

create function private.reject_immutable_model_artifact_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    raise exception 'model artifacts are immutable';
end;
$$;

revoke all on function private.reject_immutable_model_artifact_mutation() from public;
revoke all on function private.reject_immutable_model_artifact_mutation() from anon;
revoke all on function private.reject_immutable_model_artifact_mutation() from authenticated;

create trigger projection_runs_are_immutable
before update or delete on public.projection_runs
for each row execute function private.reject_immutable_model_artifact_mutation();

create trigger team_goal_projections_are_immutable
before update or delete on public.team_goal_projections
for each row execute function private.reject_immutable_model_artifact_mutation();

create trigger model_promotion_decisions_are_immutable
before update or delete on public.model_promotion_decisions
for each row execute function private.reject_immutable_model_artifact_mutation();

comment on table public.projection_runs is
    'Immutable model identity, cutoff and configuration for a projection execution.';
comment on table public.team_goal_projections is
    'Immutable expected-goal outputs with exact source hashes and availability time.';
comment on table public.model_promotion_decisions is
    'Immutable paired-bootstrap evidence for activating or rejecting a candidate model.';