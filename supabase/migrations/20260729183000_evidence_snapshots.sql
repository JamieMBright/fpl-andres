create schema if not exists private;

create table public.source_snapshots (
    id uuid primary key default extensions.gen_random_uuid(),
    source text not null check (source in ('fpl', 'vaastav', 'derived')),
    upstream_reference text not null check (char_length(upstream_reference) between 1 and 2048),
    fetched_at timestamptz not null,
    data_available_at timestamptz not null,
    content_hash text not null check (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    storage_path text not null check (char_length(storage_path) between 1 and 1024),
    compressed_bytes bigint not null check (compressed_bytes > 0),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    constraint source_snapshots_chronology check (data_available_at <= fetched_at),
    constraint source_snapshots_content unique (source, content_hash)
);

create index source_snapshots_reference_fetched_idx
    on public.source_snapshots (source, upstream_reference, fetched_at desc);

create table public.rules_snapshots (
    id uuid primary key default extensions.gen_random_uuid(),
    season text not null check (season ~ '^20[0-9]{2}-[0-9]{2}$'),
    source_snapshot_id uuid not null references public.source_snapshots(id),
    rules_hash text not null check (rules_hash ~ '^sha256:[0-9a-f]{64}$'),
    rules_json jsonb not null,
    created_at timestamptz not null default now(),
    constraint rules_snapshots_version unique (season, rules_hash)
);

create index rules_snapshots_season_created_idx
    on public.rules_snapshots (season, created_at desc);

alter table public.source_snapshots enable row level security;
alter table public.source_snapshots force row level security;
alter table public.rules_snapshots enable row level security;
alter table public.rules_snapshots force row level security;

create function private.reject_immutable_snapshot_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    raise exception 'evidence snapshots are immutable';
end;
$$;

revoke all on function private.reject_immutable_snapshot_mutation() from public;
revoke all on function private.reject_immutable_snapshot_mutation() from anon;
revoke all on function private.reject_immutable_snapshot_mutation() from authenticated;

create trigger source_snapshots_are_immutable
before update or delete on public.source_snapshots
for each row execute function private.reject_immutable_snapshot_mutation();

create trigger rules_snapshots_are_immutable
before update or delete on public.rules_snapshots
for each row execute function private.reject_immutable_snapshot_mutation();

comment on table public.source_snapshots is
    'Immutable provenance metadata for content-addressed raw evidence in private storage.';
comment on table public.rules_snapshots is
    'Immutable, versioned FPL rules extracted from an exact source snapshot.';