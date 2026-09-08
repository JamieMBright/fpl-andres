-- A compact, derived recommendation captured for one manager and deadline.
-- The underlying table remains service-role-only. The browser reads the safe
-- latest view, never the table, and the row contains no solve inputs.
create table public.recommendation_snapshots (
    id uuid primary key default gen_random_uuid(),
    season text not null references public.seasons(season),
    entry_id bigint not null check (entry_id > 0),
    event integer not null check (event between 1 and 47),
    deadline timestamptz not null,
    model_version text not null check (char_length(model_version) <= 100),
    starters bigint[] not null,
    bench bigint[] not null,
    captain bigint not null check (captain > 0),
    vice_captain bigint not null check (vice_captain > 0),
    transfer_in bigint,
    transfer_out bigint,
    chip text check (chip is null or chip in ('Free Hit', 'Wildcard')),
    projected_points numeric not null,
    net_expected_points numeric not null,
    paid_transfers integer not null check (paid_transfers between 0 and 47),
    transfer_cost numeric not null check (transfer_cost >= 0),
    confidence text not null check (confidence in ('firm', 'projected', 'provisional')),
    recorded_at timestamptz not null default now(),
    source_reference text,
    constraint recommendation_snapshots_one_per_team_event
        unique (entry_id, event),
    constraint recommendation_snapshots_starters_shape
        check (cardinality(starters) = 11),
    constraint recommendation_snapshots_bench_shape
        check (cardinality(bench) = 4),
    constraint recommendation_snapshots_starters_positive_unique
        check (private.positive_unique_bigint_array(starters)),
    constraint recommendation_snapshots_bench_positive_unique
        check (private.positive_unique_bigint_array(bench)),
    constraint recommendation_snapshots_lineup_disjoint
        check (private.bigint_arrays_are_disjoint(starters, bench)),
    constraint recommendation_snapshots_captain_starts
        check (captain = any(starters)),
    constraint recommendation_snapshots_vice_captain_starts
        check (vice_captain = any(starters)),
    constraint recommendation_snapshots_captains_differ
        check (captain <> vice_captain),
    constraint recommendation_snapshots_transfer_pair
        check ((transfer_in is null) = (transfer_out is null)),
    constraint recommendation_snapshots_transfer_differs
        check (transfer_in is null or transfer_in <> transfer_out)
);

create index recommendation_snapshots_entry_event_idx
    on public.recommendation_snapshots (entry_id, event desc);
create index recommendation_snapshots_recorded_idx
    on public.recommendation_snapshots (entry_id, recorded_at desc);

alter table public.recommendation_snapshots enable row level security;
alter table public.recommendation_snapshots force row level security;

comment on table public.recommendation_snapshots is
    'Derived recommendation memory only: forced-RLS table, service_role writes, safe latest view reads.';
comment on column public.recommendation_snapshots.source_reference is
    'Optional model/provenance reference. It never contains manager inputs.';

create view public.recommendation_snapshots_latest
with (security_invoker = true)
as
select distinct on (entry_id)
    season,
    entry_id,
    event,
    deadline,
    model_version,
    starters,
    bench,
    captain,
    vice_captain,
    transfer_in,
    transfer_out,
    chip,
    projected_points,
    net_expected_points,
    paid_transfers,
    transfer_cost,
    confidence,
    recorded_at,
    source_reference
from public.recommendation_snapshots
order by entry_id, event desc, recorded_at desc;

revoke all on table public.recommendation_snapshots from anon, authenticated;
grant select on public.recommendation_snapshots_latest to anon, authenticated;
