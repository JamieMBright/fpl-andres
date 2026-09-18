create table public.public_team_snapshots (
	season text not null check (season ~ '^[0-9]{4}-[0-9]{2}$'),
	entry_id bigint not null check (entry_id between 1 and 4294967295),
	event integer not null check (event between 1 and 38),
	context_hash text not null check (context_hash ~ '^[0-9a-f]{64}$'),
	captured_at timestamptz not null,
	expires_at timestamptz not null,
	state jsonb not null,
	primary key (season, entry_id, event),
	constraint public_team_snapshots_bounded_retention
		check (expires_at > captured_at and expires_at <= captured_at + interval '30 days'),
	constraint public_team_snapshots_required_fields
		check (state ?& array['entryId', 'event', 'evidenceLevel', 'stateAsOf', 'dataAvailableAt', 'picks', 'sourceHashes']),
	constraint public_team_snapshots_observed_only
		check (state->>'evidenceLevel' = 'observed'),
	constraint public_team_snapshots_identity_matches
		check ((state->>'entryId')::bigint = entry_id and (state->>'event')::integer = event),
	constraint public_team_snapshots_original_timestamp
		check ((state->>'dataAvailableAt')::timestamptz = captured_at and (state->>'stateAsOf')::timestamptz <= captured_at),
	constraint public_team_snapshots_fifteen_picks
		check (jsonb_typeof(state->'picks') = 'array' and jsonb_array_length(state->'picks') = 15),
	constraint public_team_snapshots_bounded_payload
		check (octet_length(state::text) <= 65536)
);

create index public_team_snapshots_captured_at_idx
	on public.public_team_snapshots (captured_at);

alter table public.public_team_snapshots enable row level security;
alter table public.public_team_snapshots force row level security;
revoke all on table public.public_team_snapshots from public, anon, authenticated;
grant select, insert, update, delete on table public.public_team_snapshots to service_role;
