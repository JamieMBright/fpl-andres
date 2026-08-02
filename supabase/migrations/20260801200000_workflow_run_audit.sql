-- Audit item #105: a history of what a scheduled run did, not just where it ended.
--
-- `workflow_runs` holds one row per (workflow, idempotency key) and that row is
-- overwritten as the run proceeds. By the time anyone looks, `status` says
-- 'failed' and `started_at` says when it began, and everything in between is
-- gone: whether it ran once or was retried, how long it spent running before it
-- failed, whether a previous attempt had already succeeded and something moved
-- it back.
--
-- That is the shape of question asked during an incident, and it was
-- unanswerable. The row is the current state; this table is what happened.
--
-- Append-only and immutable by trigger, for the same reason as every other
-- observation table here: a history that can be edited is not a history.

create table public.workflow_run_events (
    id bigint generated always as identity primary key,
    run_id uuid not null references public.workflow_runs(id) on delete cascade,
    -- Null on the first event: there was no previous status to leave.
    from_status text check (
        from_status is null
        or from_status in ('pending', 'running', 'succeeded', 'failed')
    ),
    to_status text not null check (
        to_status in ('pending', 'running', 'succeeded', 'failed')
    ),
    occurred_at timestamptz not null default now(),
    -- Recorded rather than derived, because the failure text on the run row is
    -- overwritten by a later attempt and this is the copy that survives it.
    failure_reason text check (
        failure_reason is null or char_length(failure_reason) between 1 and 2000
    ),
    -- Free-form context from the writer: row counts, event id, attempt number.
    -- Never credentials; `redact_metadata` in the Python layer is what keeps
    -- that true, and this column trusts it rather than duplicating it.
    metadata jsonb not null default '{}'::jsonb,
    -- A transition to the same status is not a transition. Recording one would
    -- turn a retry loop into an unbounded write.
    constraint workflow_run_events_is_a_change check (
        from_status is null or from_status <> to_status
    ),
    -- Only a terminal status carries a reason. A 'running' row with a failure
    -- reason attached is a contradiction that would be read as a real failure.
    constraint workflow_run_events_reason_is_terminal check (
        failure_reason is null or to_status in ('succeeded', 'failed')
    )
);

-- The query this table exists for: one run's history, oldest first.
create index workflow_run_events_run_idx
    on public.workflow_run_events (run_id, occurred_at);

-- The other one: every failure across every workflow in a window.
create index workflow_run_events_status_idx
    on public.workflow_run_events (to_status, occurred_at desc);

alter table public.workflow_run_events enable row level security;
alter table public.workflow_run_events force row level security;

create trigger workflow_run_events_are_immutable
    before update or delete on public.workflow_run_events
    for each row execute function private.reject_immutable_model_artifact_mutation();

comment on table public.workflow_run_events is
    'Append-only history of workflow_runs status transitions. The run row is the current state; this is what happened to get there.';
comment on column public.workflow_run_events.from_status is
    'Null on the first event only. A non-null value equal to to_status is refused: a transition to the same status is not a transition.';
comment on column public.workflow_run_events.failure_reason is
    'Copy of the reason at the moment of failure. The run row is overwritten by a later attempt; this survives it.';

-- Recording the transition in the trigger rather than in the application is
-- deliberate. The Python recorder is a context manager: if the process is
-- killed between the update and a separate insert, the state moves and the
-- history does not. Here they are the same transaction by construction, and
-- a second writer -- a manual correction in the SQL editor, a future job in
-- another language -- is recorded whether or not it knows this table exists.
create or replace function private.record_workflow_run_transition()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if tg_op = 'INSERT' then
        insert into public.workflow_run_events (
            run_id, from_status, to_status, occurred_at, failure_reason, metadata
        )
        values (
            new.id,
            null,
            new.status,
            coalesce(new.started_at, now()),
            case when new.status in ('succeeded', 'failed') then new.failure_reason end,
            new.metadata
        );
        return new;
    end if;

    if new.status is distinct from old.status then
        insert into public.workflow_run_events (
            run_id, from_status, to_status, occurred_at, failure_reason, metadata
        )
        values (
            new.id,
            old.status,
            new.status,
            coalesce(new.finished_at, now()),
            case when new.status in ('succeeded', 'failed') then new.failure_reason end,
            new.metadata
        );
    end if;
    return new;
end;
$$;

comment on function private.record_workflow_run_transition() is
    'Writes a workflow_run_events row in the same transaction as the status change, so the history cannot fall behind the state.';

create trigger workflow_runs_record_transitions
    after insert or update on public.workflow_runs
    for each row execute function private.record_workflow_run_transition();
