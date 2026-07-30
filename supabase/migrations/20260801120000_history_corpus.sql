-- Match and player history corpus.
--
-- Unlike the evidence and projection artifact tables, these are deliberately
-- NOT immutable. FPL revises in-season data after a gameweek closes (late bonus
-- points, stat corrections, rescheduled fixtures), so a row must be able to
-- track its upstream. Provenance is preserved because every write records the
-- immutable source_snapshots row it came from, and those raw payloads are
-- retained, so any historical state is reconstructible from raw bytes.

create table public.seasons (
    season text primary key check (season ~ '^20[0-9]{2}-[0-9]{2}$'),
    created_at timestamptz not null default now()
);

create table public.teams (
    season text not null references public.seasons(season),
    team_id integer not null check (team_id > 0),
    code integer not null check (code > 0),
    name text not null check (char_length(name) between 1 and 100),
    short_name text not null check (char_length(short_name) between 1 and 10),
    strength integer check (strength is null or strength between 1 and 5),
    strength_overall_home integer,
    strength_overall_away integer,
    strength_attack_home integer,
    strength_attack_away integer,
    strength_defence_home integer,
    strength_defence_away integer,
    source_snapshot_id uuid not null references public.source_snapshots(id),
    ingested_at timestamptz not null default now(),
    primary key (season, team_id)
);

create index teams_code_idx on public.teams (code);

create table public.elements (
    season text not null references public.seasons(season),
    element_id integer not null check (element_id > 0),
    -- FPL's player code is stable across seasons; element_id is not.
    code integer not null check (code > 0),
    first_name text not null,
    second_name text not null,
    web_name text not null,
    element_type integer not null check (element_type between 1 and 5),
    team_id integer not null check (team_id > 0),
    start_cost integer check (start_cost is null or start_cost > 0),
    source_snapshot_id uuid not null references public.source_snapshots(id),
    ingested_at timestamptz not null default now(),
    primary key (season, element_id),
    constraint elements_team_fk foreign key (season, team_id) references public.teams(season, team_id)
);

create index elements_code_idx on public.elements (code);
create index elements_season_team_idx on public.elements (season, team_id);

create table public.fixtures (
    season text not null references public.seasons(season),
    fixture_id integer not null check (fixture_id > 0),
    event integer check (event is null or event between 1 and 38),
    kickoff_time timestamptz,
    team_h integer not null check (team_h > 0),
    team_a integer not null check (team_a > 0),
    team_h_score integer check (team_h_score is null or team_h_score >= 0),
    team_a_score integer check (team_a_score is null or team_a_score >= 0),
    team_h_difficulty integer check (team_h_difficulty is null or team_h_difficulty between 1 and 5),
    team_a_difficulty integer check (team_a_difficulty is null or team_a_difficulty between 1 and 5),
    finished boolean not null default false,
    source_snapshot_id uuid not null references public.source_snapshots(id),
    ingested_at timestamptz not null default now(),
    primary key (season, fixture_id),
    constraint fixtures_distinct_sides check (team_h <> team_a),
    constraint fixtures_score_pairing check (
        (team_h_score is null) = (team_a_score is null)
    ),
    constraint fixtures_finished_has_score check (
        not finished or team_h_score is not null
    )
);

create index fixtures_season_event_idx on public.fixtures (season, event);
create index fixtures_kickoff_idx on public.fixtures (season, kickoff_time);

create table public.element_gameweek_stats (
    season text not null references public.seasons(season),
    gameweek integer not null check (gameweek between 1 and 38),
    element_id integer not null check (element_id > 0),
    element_code integer not null check (element_code > 0),
    fixture_id integer check (fixture_id is null or fixture_id > 0),
    opponent_team integer check (opponent_team is null or opponent_team > 0),
    was_home boolean,
    kickoff_time timestamptz,

    minutes integer not null check (minutes between 0 and 120),
    starts integer check (starts is null or starts >= 0),
    goals_scored integer not null default 0 check (goals_scored >= 0),
    assists integer not null default 0 check (assists >= 0),
    clean_sheets integer not null default 0 check (clean_sheets >= 0),
    goals_conceded integer not null default 0 check (goals_conceded >= 0),
    own_goals integer not null default 0 check (own_goals >= 0),
    penalties_saved integer not null default 0 check (penalties_saved >= 0),
    penalties_missed integer not null default 0 check (penalties_missed >= 0),
    yellow_cards integer not null default 0 check (yellow_cards >= 0),
    red_cards integer not null default 0 check (red_cards >= 0),
    saves integer not null default 0 check (saves >= 0),
    bonus integer not null default 0 check (bonus between 0 and 3),
    bps integer not null default 0,

    influence numeric(8, 2),
    creativity numeric(8, 2),
    threat numeric(8, 2),
    ict_index numeric(8, 2),

    expected_goals numeric(8, 3),
    expected_assists numeric(8, 3),
    expected_goal_involvements numeric(8, 3),
    expected_goals_conceded numeric(8, 3),

    -- Observed defensive-contribution labels begin in 2025/26; null before that.
    defensive_contribution integer check (
        defensive_contribution is null or defensive_contribution >= 0
    ),

    total_points integer not null,
    value integer check (value is null or value > 0),
    selected bigint check (selected is null or selected >= 0),
    transfers_in bigint check (transfers_in is null or transfers_in >= 0),
    transfers_out bigint check (transfers_out is null or transfers_out >= 0),

    source_snapshot_id uuid not null references public.source_snapshots(id),
    ingested_at timestamptz not null default now(),

    primary key (season, gameweek, element_id),
    constraint element_gameweek_stats_element_fk
        foreign key (season, element_id) references public.elements(season, element_id)
);

create index element_gameweek_stats_code_idx
    on public.element_gameweek_stats (element_code, season, gameweek);
create index element_gameweek_stats_season_gw_idx
    on public.element_gameweek_stats (season, gameweek);
create index element_gameweek_stats_snapshot_idx
    on public.element_gameweek_stats (source_snapshot_id);

create table public.element_price_observations (
    season text not null references public.seasons(season),
    element_id integer not null check (element_id > 0),
    observed_on date not null,
    value integer not null check (value > 0),
    selected bigint check (selected is null or selected >= 0),
    transfers_in_event bigint check (transfers_in_event is null or transfers_in_event >= 0),
    transfers_out_event bigint check (transfers_out_event is null or transfers_out_event >= 0),
    source_snapshot_id uuid not null references public.source_snapshots(id),
    ingested_at timestamptz not null default now(),
    primary key (season, element_id, observed_on),
    constraint element_price_observations_element_fk
        foreign key (season, element_id) references public.elements(season, element_id)
);

create index element_price_observations_snapshot_idx
    on public.element_price_observations (source_snapshot_id);

alter table public.seasons enable row level security;
alter table public.seasons force row level security;
alter table public.teams enable row level security;
alter table public.teams force row level security;
alter table public.elements enable row level security;
alter table public.elements force row level security;
alter table public.fixtures enable row level security;
alter table public.fixtures force row level security;
alter table public.element_gameweek_stats enable row level security;
alter table public.element_gameweek_stats force row level security;
alter table public.element_price_observations enable row level security;
alter table public.element_price_observations force row level security;

comment on table public.seasons is
    'Season identity anchor for the match and player history corpus.';
comment on table public.teams is
    'Per-season club identity and FPL strength ratings.';
comment on table public.elements is
    'Per-season player identity. code is stable across seasons; element_id is not.';
comment on table public.fixtures is
    'Per-season fixture list with results and FPL difficulty ratings.';
comment on table public.element_gameweek_stats is
    'Per-player per-gameweek observed match statistics. Upsertable because FPL revises in-season data; provenance is retained through source_snapshot_id.';
comment on table public.element_price_observations is
    'Daily price and transfer observations backing calibrated price-movement probabilities.';
