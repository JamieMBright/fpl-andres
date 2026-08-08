"""Workflow status changes leave a history, and every growing table has a policy.

Audit items #104 and #105.

#105: `workflow_runs` holds one row per (workflow, idempotency key) and that row
is overwritten as the run proceeds. By the time anyone looks it says 'failed'
and when it began, and everything between is gone -- whether it ran once or was
retried, how long it spent running, whether an earlier attempt had already
succeeded. That is the shape of question asked during an incident and it was
unanswerable.

#104: several tables only ever grow and nothing recorded what the plan was. An
unrecorded decision becomes whatever the free tier decides, usually during a
season and usually by refusing a write.

These are static checks against the migration and the document. The trigger's
runtime behaviour is exercised by the `migrations` CI job, which resets a real
Postgres and applies the file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260801200000_workflow_run_audit.sql"
ROLLBACK = REPO_ROOT / "supabase" / "rollback" / "down.sql"
RETENTION = REPO_ROOT / "README.md"


@pytest.fixture(scope="module")
def migration() -> str:
    return MIGRATION.read_text(encoding="utf-8")


class TestAuditTrail:
    def test_the_table_exists_and_points_at_the_run(self, migration: str) -> None:
        assert "create table public.workflow_run_events" in migration
        assert "references public.workflow_runs(id) on delete cascade" in migration

    def test_it_is_written_by_a_trigger_not_by_the_application(self, migration: str) -> None:
        # The Python recorder is a context manager. A process killed between the
        # status update and a separate insert would move the state without
        # recording it. In the trigger they are one transaction by construction.
        assert "create trigger workflow_runs_record_transitions" in migration
        assert "after insert or update on public.workflow_runs" in migration

    def test_the_history_is_immutable(self, migration: str) -> None:
        assert "create trigger workflow_run_events_are_immutable" in migration
        assert "before update or delete on public.workflow_run_events" in migration
        assert "private.reject_immutable_model_artifact_mutation" in migration

    def test_a_transition_to_the_same_status_is_refused(self, migration: str) -> None:
        # Otherwise a retry loop writing 'running' repeatedly becomes an
        # unbounded write against the table meant to explain it.
        assert "workflow_run_events_is_a_change" in migration
        assert "from_status is null or from_status <> to_status" in migration

    def test_only_a_terminal_status_may_carry_a_failure_reason(self, migration: str) -> None:
        # A 'running' row with a reason attached is a contradiction that reads
        # as a real failure to anyone scanning the table.
        assert "workflow_run_events_reason_is_terminal" in migration
        assert "to_status in ('succeeded', 'failed')" in migration

    def test_both_status_columns_are_constrained_to_the_same_alphabet(self, migration: str) -> None:
        # A history that can record a status the run row cannot hold is a
        # history of something else.
        foundation = (
            REPO_ROOT / "supabase" / "migrations" / "20260729180000_foundation.sql"
        ).read_text(encoding="utf-8")
        run_statuses = re.search(r"status in \(([^)]+)\)", foundation)
        assert run_statuses is not None
        allowed = {value.strip() for value in run_statuses.group(1).split(",")}
        for column in ("from_status", "to_status"):
            match = re.search(rf"{column} in \(([^)]+)\)", migration)
            assert match is not None, f"{column} is unconstrained"
            assert {value.strip() for value in match.group(1).split(",")} == allowed

    def test_the_function_is_hardened_like_every_other_definer(self, migration: str) -> None:
        # A security definer without an empty search_path is a privilege
        # escalation waiting for someone to create a same-named function.
        assert "security definer" in migration
        assert "set search_path = ''" in migration

    def test_the_indexes_match_the_two_questions_asked_of_it(self, migration: str) -> None:
        assert "workflow_run_events_run_idx" in migration
        assert "(run_id, occurred_at)" in migration
        assert "workflow_run_events_status_idx" in migration

    def test_the_teardown_drops_the_table_before_the_run_it_references(self) -> None:
        rollback = ROLLBACK.read_text(encoding="utf-8")
        events = rollback.index("drop table if exists public.workflow_run_events;")
        runs = rollback.index("drop table if exists public.workflow_runs;")
        assert events < runs, "dropping the parent first would fail on the foreign key"

    def test_the_teardown_drops_the_trigger_function(self) -> None:
        assert (
            "drop function if exists private.record_workflow_run_transition();"
            in ROLLBACK.read_text(encoding="utf-8")
        )


@pytest.fixture(scope="module")
def policy() -> str:
    return RETENTION.read_text(encoding="utf-8")


class TestRetentionPolicy:
    def test_every_growing_table_has_a_policy(self, policy: str) -> None:
        for table in (
            "element_gameweek_stats",
            "element_price_observations",
            "crowd_snapshots",
            "backtest_predictions",
            "source_snapshots",
            "workflow_run_events",
        ):
            assert f"`{table}`" in policy, f"{table} has no stated retention policy"

    def test_keeping_everything_is_justified_with_a_number(self, policy: str) -> None:
        # "Keep everything" is only a defensible answer with a measurement
        # attached; without one it is a hope about disk.
        assert "500 MB" in policy
        assert "6.6 MB" in policy
        assert "185,954" in policy

    def test_the_one_table_that_can_reach_the_ceiling_is_named(self, policy: str) -> None:
        # backtest_predictions: 20 seeds per promotion, ~186,000 rows a run.
        # It is the only one that grows in a season rather than in a century.
        assert "backtest_predictions" in policy

    def test_personal_data_is_the_stated_exception(self, policy: str) -> None:
        # "Keep everything" cannot apply to a subscriber's address. The one
        # category that must not be kept indefinitely has to be named.
        assert "personal data" in policy
        assert "never exported" in policy
