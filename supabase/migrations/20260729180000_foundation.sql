create extension if not exists pgcrypto with schema extensions;

create table public.workflow_runs (
    id uuid primary key default extensions.gen_random_uuid(),
    workflow_name text not null check (char_length(workflow_name) between 1 and 100),
    idempotency_key text not null check (char_length(idempotency_key) between 1 and 200),
    status text not null check (status in ('pending', 'running', 'succeeded', 'failed')),
    event_id integer check (event_id is null or event_id > 0),
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    failure_reason text,
    metadata jsonb not null default '{}'::jsonb,
    constraint workflow_runs_idempotency unique (workflow_name, idempotency_key),
    constraint workflow_runs_finished_state check (
        (status in ('pending', 'running') and finished_at is null)
        or (status in ('succeeded', 'failed') and finished_at is not null)
    )
);

create index workflow_runs_status_started_idx
    on public.workflow_runs (status, started_at desc);

alter table public.workflow_runs enable row level security;
alter table public.workflow_runs force row level security;

comment on table public.workflow_runs is
    'Durable idempotency and execution history for scheduled FPL Andres jobs.';
