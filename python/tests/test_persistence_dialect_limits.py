"""Batching, error codes and configuration for the PostgREST client.

Each is a place where the client was correct
for the inputs it had been given and wrong for one it had not.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from tests.builders import TEST_SECRET, credentials

from fpl_andres.persistence.supabase import (
    UNIQUE_VIOLATION,
    BatchLimits,
    MissingCredentialsError,
    SupabaseCredentials,
    SupabaseRestClient,
    SupabaseWriteError,
)
from fpl_andres.persistence.workflow import (
    WorkflowAlreadyRunningError,
    WorkflowRun,
    WorkflowRunRecorder,
)


def _client(handler: Any, *, batch_limits: BatchLimits | None = None) -> SupabaseRestClient:
    return SupabaseRestClient(
        credentials(),
        transport=httpx.MockTransport(handler),
        batch_limits=batch_limits,
    )


class TestBatchSizing:
    """#64: a row count alone does not bound the payload."""

    def test_a_batch_stops_at_the_byte_limit_before_the_row_limit(self) -> None:
        # Rows here range from a few hundred bytes to several kilobytes. Five
        # hundred wide rows are an order of magnitude larger than five hundred
        # narrow ones, and the difference arrives as a 413 in the middle of a
        # run rather than at the start of one.
        sizes: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sizes.append(len(request.content))
            return httpx.Response(201)

        rows = [{"id": index, "blob": "x" * 1_000} for index in range(100)]
        with _client(handler, batch_limits=BatchLimits(max_rows=500, max_bytes=10_000)) as client:
            client.insert("wide_table", rows)

        assert len(sizes) > 1
        assert max(sizes) <= 10_000 + 2_000

    def test_a_batch_stops_at_the_row_limit_when_rows_are_small(self) -> None:
        counts: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            counts.append(len(json.loads(request.content)))
            return httpx.Response(201)

        rows = [{"id": index} for index in range(250)]
        with _client(
            handler, batch_limits=BatchLimits(max_rows=100, max_bytes=10_000_000)
        ) as client:
            client.insert("narrow_table", rows)

        assert counts == [100, 100, 50]

    def test_every_row_is_written_exactly_once(self) -> None:
        # The bound that matters most: a splitting rule that drops or repeats a
        # row is worse than one that sends too much.
        seen: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.extend(row["id"] for row in json.loads(request.content))
            return httpx.Response(201)

        rows = [{"id": index, "blob": "y" * (index % 400)} for index in range(1_000)]
        with _client(handler, batch_limits=BatchLimits(max_rows=37, max_bytes=5_000)) as client:
            client.insert("mixed", rows)

        assert seen == list(range(1_000))

    def test_a_single_oversized_row_travels_alone_rather_than_being_refused(self) -> None:
        # Splitting one row is not possible, and refusing it here would turn a
        # server-side limit into a client-side one -- hiding which row is at
        # fault behind our own error instead of the database's.
        counts: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            counts.append(len(json.loads(request.content)))
            return httpx.Response(201)

        rows = [{"id": 1, "blob": "z" * 50_000}, {"id": 2}]
        with _client(handler, batch_limits=BatchLimits(max_rows=500, max_bytes=1_000)) as client:
            client.insert("t", rows)

        assert counts == [1, 1]

    def test_no_request_is_made_for_no_rows(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(201)

        with _client(handler) as client:
            client.insert("t", [])
        assert calls == 0

    def test_the_default_limits_are_the_shipped_ones(self) -> None:
        limits = BatchLimits()
        assert limits.max_rows == 500
        assert limits.max_bytes == 6 * 1024 * 1024

    @pytest.mark.parametrize(
        ("max_rows", "max_bytes"),
        [(0, 1_000), (-1, 1_000), (10, 0), (10, -1)],
    )
    def test_a_limit_below_one_is_refused(self, max_rows: int, max_bytes: int) -> None:
        # A max_rows of zero would loop forever producing empty batches.
        with pytest.raises(ValueError):
            BatchLimits(max_rows=max_rows, max_bytes=max_bytes)


class TestConfigurableBatching:
    """#65: the right batch size differs per table and per deployment."""

    def test_a_call_may_override_the_client_default(self) -> None:
        counts: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            counts.append(len(json.loads(request.content)))
            return httpx.Response(201)

        rows = [{"id": index} for index in range(20)]
        with _client(handler, batch_limits=BatchLimits(max_rows=500)) as client:
            client.insert("t", rows, batch_limits=BatchLimits(max_rows=5))

        assert counts == [5, 5, 5, 5]

    def test_an_override_does_not_leak_into_the_next_call(self) -> None:
        counts: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            counts.append(len(json.loads(request.content)))
            return httpx.Response(201)

        rows = [{"id": index} for index in range(20)]
        with _client(handler, batch_limits=BatchLimits(max_rows=500)) as client:
            client.insert("t", rows, batch_limits=BatchLimits(max_rows=5))
            counts.clear()
            client.insert("t", rows)

        assert counts == [20]

    def test_upsert_carries_the_conflict_target_into_every_batch(self) -> None:
        # A batch that lost it would insert duplicates for its share of rows.
        targets: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            targets.append(request.url.params.get("on_conflict"))
            return httpx.Response(201)

        rows = [{"id": index, "value": index} for index in range(12)]
        with _client(handler, batch_limits=BatchLimits(max_rows=5)) as client:
            client.upsert("t", rows, on_conflict="id")

        assert targets == ["id", "id", "id"]


class TestSqlstate:
    """#63: match the code, not the sentence."""

    def test_a_unique_violation_carries_its_sqlstate(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                409,
                json={
                    "code": "23505",
                    "message": 'duplicate key value violates unique constraint "t_pkey"',
                    "details": None,
                    "hint": None,
                },
            )

        with _client(handler) as client, pytest.raises(SupabaseWriteError) as caught:
            client.insert("t", [{"id": 1}])
        assert caught.value.code == UNIQUE_VIOLATION

    def test_a_foreign_key_violation_is_a_different_code(self) -> None:
        # The old test was "does the message contain 'duplicate key'". A foreign
        # key violation reads "insert or update on table ... violates foreign key
        # constraint", which does not contain it -- but neither would a unique
        # violation phrased by a future Postgres, or by a server in another
        # locale. The code is the part that does not move.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(409, json={"code": "23503", "message": "fk violation"})

        with _client(handler) as client, pytest.raises(SupabaseWriteError) as caught:
            client.insert("t", [{"id": 1}])
        assert caught.value.code == "23503"
        assert caught.value.code != UNIQUE_VIOLATION

    def test_a_non_json_error_has_no_code_rather_than_a_wrong_one(self) -> None:
        # A 4xx rather than a 5xx so the client does not retry: what is being
        # checked is the absence of a code, not the backoff.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="<html>Bad Request</html>")

        with _client(handler) as client, pytest.raises(SupabaseWriteError) as caught:
            client.insert("t", [{"id": 1}])
        assert caught.value.code is None

    def test_reads_and_updates_carry_the_code_too(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"code": "42703", "message": "no such column"})

        with _client(handler) as client:
            with pytest.raises(SupabaseWriteError) as read_error:
                client.select("t")
            with pytest.raises(SupabaseWriteError) as update_error:
                client.update("t", {"a": 1}, filters={"id": "eq.1"})
        assert read_error.value.code == "42703"
        assert update_error.value.code == "42703"


class TestWorkflowDuplicateDetection:
    """#63 at the caller."""

    def test_a_second_run_with_the_same_key_is_told_from_any_other_failure(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(409, json={"code": "23505", "message": "unique_violation"})

        run = WorkflowRun(workflow_name="ingest", idempotency_key="2026-08-01")
        with _client(handler) as client:
            recorder = WorkflowRunRecorder(client, run)
            with pytest.raises(WorkflowAlreadyRunningError):
                recorder.__enter__()

    def test_a_permission_failure_is_not_mistaken_for_a_duplicate(self) -> None:
        # This is the failure the phrase match could not see. A run refused for
        # want of a grant would have been reported as "already running", and
        # the schedule would have looked healthy while writing nothing.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                403, json={"code": "42501", "message": "permission denied for table workflow_runs"}
            )

        run = WorkflowRun(workflow_name="ingest", idempotency_key="2026-08-01")
        with _client(handler) as client:
            recorder = WorkflowRunRecorder(client, run)
            with pytest.raises(SupabaseWriteError):
                recorder.__enter__()

    def test_a_message_mentioning_a_duplicate_without_the_code_is_not_a_duplicate(
        self,
    ) -> None:
        # A check constraint named "no_duplicate_events" would have tripped the
        # old substring match and been silently swallowed as idempotency.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={
                    "code": "23514",
                    "message": 'new row violates check constraint "no_duplicate_events"',
                },
            )

        run = WorkflowRun(workflow_name="ingest", idempotency_key="2026-08-01")
        with _client(handler) as client:
            recorder = WorkflowRunRecorder(client, run)
            with pytest.raises(SupabaseWriteError):
                recorder.__enter__()


class TestCredentialValidation:
    """#77: a configuration error must name the variable at fault."""

    def test_a_missing_variable_is_named(self) -> None:
        with pytest.raises(MissingCredentialsError, match="SUPABASE_SECRET_KEY"):
            SupabaseCredentials.from_env({"SUPABASE_URL": "https://project.supabase.co"})

    def test_both_missing_variables_are_named(self) -> None:
        with pytest.raises(MissingCredentialsError) as caught:
            SupabaseCredentials.from_env({})
        assert "SUPABASE_SECRET_KEY" in str(caught.value)
        assert "SUPABASE_URL" in str(caught.value)

    @pytest.mark.parametrize("value", [None, 1, [], {}, object()])
    def test_a_non_string_value_names_the_variable_and_the_type(self, value: object) -> None:
        # Without this the failure is AttributeError from inside a credentials
        # constructor, which names neither the variable nor the problem.
        env: Any = {"SUPABASE_URL": value, "SUPABASE_SECRET_KEY": TEST_SECRET}
        with pytest.raises(MissingCredentialsError, match="SUPABASE_URL must be a string"):
            SupabaseCredentials.from_env(env)

    def test_transposed_values_say_so_rather_than_blaming_the_url(self) -> None:
        # Both are non-empty strings, so nothing else catches it. The old error
        # was "SUPABASE_URL must be an https URL" -- true, and unhelpful: the
        # URL is fine, it is just in the other variable.
        with pytest.raises(MissingCredentialsError, match="transposed"):
            SupabaseCredentials.from_env(
                {
                    "SUPABASE_URL": TEST_SECRET,
                    "SUPABASE_SECRET_KEY": "https://project.supabase.co",
                }
            )

    def test_a_whitespace_only_value_counts_as_missing(self) -> None:
        with pytest.raises(MissingCredentialsError, match="missing required"):
            SupabaseCredentials.from_env(
                {"SUPABASE_URL": "   ", "SUPABASE_SECRET_KEY": TEST_SECRET}
            )

    def test_a_plain_http_url_is_refused(self) -> None:
        with pytest.raises(MissingCredentialsError, match="https"):
            SupabaseCredentials.from_env(
                {"SUPABASE_URL": "http://project.supabase.co", "SUPABASE_SECRET_KEY": TEST_SECRET}
            )

    def test_a_trailing_slash_is_removed_so_paths_do_not_double_up(self) -> None:
        parsed = SupabaseCredentials.from_env(
            {"SUPABASE_URL": "https://project.supabase.co/", "SUPABASE_SECRET_KEY": TEST_SECRET}
        )
        assert parsed.url == "https://project.supabase.co"

    def test_the_secret_never_appears_in_a_repr(self) -> None:
        parsed = SupabaseCredentials.from_env(
            {"SUPABASE_URL": "https://project.supabase.co", "SUPABASE_SECRET_KEY": TEST_SECRET}
        )
        assert TEST_SECRET not in repr(parsed)
        assert "<redacted>" in repr(parsed)
