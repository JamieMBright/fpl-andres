-- Backtest results, so a published claim can be traced to the run that produced it.
--
-- The calibration page currently ships a committed JSON artifact. That is
-- deliberate and stays: a claim about a commit belongs in the commit. These
-- tables serve the other need, which is comparing runs over time to see whether
-- the method is actually improving or merely changing.
--
-- Immutable like the other model artifacts. A backtest whose numbers can be
-- edited after the fact is not evidence of anything.

create table public.backtest_runs (
    id uuid primary key default gen_random_uuid(),
    season text not null references public.seasons(season),
    method text not null check (char_length(method) between 1 and 60),
    first_scored_gameweek integer not null check (first_scored_gameweek between 1 and 47),
    scored_observations integer not null check (scored_observations >= 0),
    mean_absolute_error double precision check (mean_absolute_error is null or mean_absolute_error >= 0),
    root_mean_squared_error double precision check (
        root_mean_squared_error is null or root_mean_squared_error >= 0
    ),
    bias double precision,
    spearman double precision check (spearman is null or spearman between -1 and 1),
    top_n_hit_rate double precision check (top_n_hit_rate is null or top_n_hit_rate between 0 and 1),
    spearman_gkp double precision check (spearman_gkp is null or spearman_gkp between -1 and 1),
    spearman_def double precision check (spearman_def is null or spearman_def between -1 and 1),
    spearman_mid double precision check (spearman_mid is null or spearman_mid between -1 and 1),
    spearman_fwd double precision check (spearman_fwd is null or spearman_fwd between -1 and 1),
    -- Ties the row to the exact code that produced it.
    code_revision text not null check (code_revision ~ '^[0-9a-f]{7,40}$'),
    data_available_at timestamptz not null,
    created_at timestamptz not null default now(),
    constraint backtest_runs_scored_has_metrics check (
        scored_observations = 0 or spearman is not null
    ),
    constraint backtest_runs_unique_evaluation unique (
        season, method, code_revision, first_scored_gameweek
    )
);

create table public.backtest_predictions (
    run_id uuid not null references public.backtest_runs(id) on delete cascade,
    gameweek integer not null check (gameweek between 1 and 47),
    element_id integer not null check (element_id > 0),
    predicted_points double precision not null,
    actual_points integer not null,
    fixture_count integer not null default 1 check (fixture_count >= 0),
    primary key (run_id, gameweek, element_id)
);

create index backtest_runs_season_method_idx
    on public.backtest_runs (season, method, created_at desc);
create index backtest_predictions_run_idx
    on public.backtest_predictions (run_id, gameweek);

alter table public.backtest_runs enable row level security;
alter table public.backtest_runs force row level security;
alter table public.backtest_predictions enable row level security;
alter table public.backtest_predictions force row level security;

create trigger backtest_runs_are_immutable
    before update or delete on public.backtest_runs
    for each row execute function private.reject_immutable_model_artifact_mutation();

create trigger backtest_predictions_are_immutable
    before update or delete on public.backtest_predictions
    for each row execute function private.reject_immutable_model_artifact_mutation();

comment on table public.backtest_runs is
    'One scored method against one season. Immutable, and keyed by the code revision so two runs of the same season are comparable only when the code matches.';
comment on column public.backtest_runs.code_revision is
    'Git commit that produced the run. Without it a metric cannot be attributed to a change.';
comment on table public.backtest_predictions is
    'Per-player predictions behind a run, kept so a headline metric can be re-derived rather than trusted.';
