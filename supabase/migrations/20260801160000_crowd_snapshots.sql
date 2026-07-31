-- Crowd signal: what the field owns, captains and is moving toward.
--
-- Aggregate ownership is published before a deadline and is legal to read at any
-- time, including gameweek one. Individual rival picks are not, and are handled
-- separately after a deadline has passed. This table holds the aggregate only.
--
-- Captaincy is stored beside ownership because effective ownership is the sum of
-- the two: a captained player scores twice, so he is owned twice for the purpose
-- of working out what a rival gains on you.
--
-- Snapshots are per gameweek and immutable, because the whole point is to see
-- how the crowd moved. Overwriting yesterday's ownership destroys the signal.

create table public.crowd_snapshots (
    season text not null references public.seasons(season),
    event integer not null check (event between 1 and 47),
    element_id integer not null check (element_id > 0),
    captured_at timestamptz not null,
    selected_by_percent numeric(5, 2) not null check (
        selected_by_percent between 0 and 100
    ),
    captained_by integer check (captained_by is null or captained_by >= 0),
    vice_captained_by integer check (vice_captained_by is null or vice_captained_by >= 0),
    transfers_in_event bigint check (transfers_in_event is null or transfers_in_event >= 0),
    transfers_out_event bigint check (transfers_out_event is null or transfers_out_event >= 0),
    total_managers bigint check (total_managers is null or total_managers > 0),
    source_snapshot_id uuid not null references public.source_snapshots(id),
    ingested_at timestamptz not null default now(),
    primary key (season, event, element_id, captured_at),
    constraint crowd_snapshots_element_fk
        foreign key (season, element_id) references public.elements(season, element_id),
    -- A captaincy count without a denominator cannot become a share.
    constraint crowd_snapshots_captaincy_needs_a_denominator check (
        captained_by is null or total_managers is not null
    )
);

create index crowd_snapshots_season_event_idx
    on public.crowd_snapshots (season, event, captured_at desc);
create index crowd_snapshots_element_idx
    on public.crowd_snapshots (season, element_id, captured_at desc);
create index crowd_snapshots_snapshot_idx
    on public.crowd_snapshots (source_snapshot_id);

alter table public.crowd_snapshots enable row level security;
alter table public.crowd_snapshots force row level security;

create trigger crowd_snapshots_are_immutable
    before update or delete on public.crowd_snapshots
    for each row execute function private.reject_immutable_model_artifact_mutation();

comment on table public.crowd_snapshots is
    'Aggregate ownership and captaincy per gameweek. Immutable: overwriting a snapshot destroys the movement the table exists to record.';
comment on column public.crowd_snapshots.selected_by_percent is
    'Published aggregate ownership. Legal to read before a deadline, unlike individual rival picks.';
comment on column public.crowd_snapshots.captained_by is
    'Manager count, not a share. Stored raw so a later change to total_managers cannot silently rewrite history.';
