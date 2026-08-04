-- Two things the site cannot learn by reading what FPL publishes.
--
-- 1. Who asked for an analysis, and when. The plan is generated for a manager's
--    own squad, so the request is the only record that it happened. Kept so a
--    rate limit and a "you last looked at this on ..." line have something to
--    read, and so a bug report can be tied to the inputs that produced it.
--
-- 2. Transfers a manager has already made that FPL has not published yet. A
--    manager's picks for the coming gameweek are private until the deadline
--    passes, so between a transfer and the deadline the public API still shows
--    the old squad. Planning from the old squad recommends a transfer that has
--    already been made. The manager tells us instead.
--
-- Both hold a manager's private team state, so both stay behind forced RLS with
-- no policy: only `service_role` reads or writes them, and the browser key
-- cannot. See docs/adr/0001-forced-rls-with-no-policies.md.

create table public.analysis_requests (
    id uuid primary key default gen_random_uuid(),
    season text not null references public.seasons(season),
    entry_id bigint not null check (entry_id > 0),
    -- The gameweek the manager was planning from, not the one they asked in.
    -- Those differ either side of a deadline and the plan depends on the former.
    event integer not null check (event between 1 and 47),
    requested_at timestamptz not null default now(),
    -- Which published state the answer was built on, so a plan can be
    -- reproduced without guessing which snapshot was current at the time.
    source_snapshot_id uuid references public.source_snapshots(id),
    -- Free text, capped, because it is echoed nowhere and only ever read by a
    -- human debugging a report.
    note text check (note is null or char_length(note) <= 500)
);

create index analysis_requests_entry_idx
    on public.analysis_requests (entry_id, requested_at desc);
create index analysis_requests_season_event_idx
    on public.analysis_requests (season, event, requested_at desc);
create index analysis_requests_snapshot_idx
    on public.analysis_requests (source_snapshot_id);

alter table public.analysis_requests enable row level security;
alter table public.analysis_requests force row level security;

comment on table public.analysis_requests is
    'One row per plan generated for a manager. Private team state: forced RLS, no policy, service_role only.';
comment on column public.analysis_requests.event is
    'The gameweek planned from. Differs from the gameweek the request was made in either side of a deadline.';

-- A transfer the manager has made but FPL has not published.
--
-- Recorded as the pair it was, because a transfer is a swap: one out, one in,
-- inside one gameweek. Storing them separately would let a half-entered swap
-- reach the planner as a fourteen-player squad.
create table public.declared_transfers (
    id uuid primary key default gen_random_uuid(),
    season text not null references public.seasons(season),
    entry_id bigint not null check (entry_id > 0),
    -- The gameweek the transfer takes effect in.
    event integer not null check (event between 1 and 47),
    element_out integer not null check (element_out > 0),
    element_in integer not null check (element_in > 0),
    -- Whether the manager paid four points for it. The planner has to know:
    -- an unaffordable hit changes what the rest of the week should look like.
    points_charged integer not null default 0 check (points_charged >= 0),
    declared_at timestamptz not null default now(),
    -- Cleared once the public API catches up, so the override stops being
    -- applied twice. Null while it is still needed.
    superseded_at timestamptz,
    constraint declared_transfers_out_fk
        foreign key (season, element_out) references public.elements(season, element_id),
    constraint declared_transfers_in_fk
        foreign key (season, element_in) references public.elements(season, element_id),
    -- Swapping a player for himself is a typo, not a transfer.
    constraint declared_transfers_move_a_player check (element_out <> element_in),
    -- The same swap entered twice would remove a player who is already gone.
    constraint declared_transfers_are_declared_once
        unique (season, entry_id, event, element_out, element_in)
);

create index declared_transfers_entry_idx
    on public.declared_transfers (season, entry_id, event)
    where superseded_at is null;
create index declared_transfers_out_idx
    on public.declared_transfers (season, element_out);
create index declared_transfers_in_idx
    on public.declared_transfers (season, element_in);

alter table public.declared_transfers enable row level security;
alter table public.declared_transfers force row level security;

comment on table public.declared_transfers is
    'Transfers a manager reports before FPL publishes them. Private team state: forced RLS, no policy, service_role only.';
comment on column public.declared_transfers.superseded_at is
    'Set once the public API shows the transfer. Until then the planner applies it on top of the published squad.';
comment on column public.declared_transfers.points_charged is
    'Four per hit already taken. The planner needs it to price the rest of the gameweek honestly.';
