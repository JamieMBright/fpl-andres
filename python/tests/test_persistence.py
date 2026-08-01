from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from fpl_andres.persistence.supabase import (
    MissingCredentialsError,
    SupabaseCredentials,
    SupabaseRestClient,
    SupabaseWriteError,
)
from fpl_andres.persistence.workflow import (
    WorkflowAlreadyRunningError,
    build_idempotency_key,
    open_run,
)

BASE_URL = "https://project.supabase.co"
SECRET = "service-role-secret-value"


def _credentials() -> SupabaseCredentials:
    return SupabaseCredentials(url=BASE_URL, secret_key=SECRET)


def test_credentials_fail_closed_when_environment_is_incomplete() -> None:
    with pytest.raises(MissingCredentialsError) as missing_both:
        SupabaseCredentials.from_env({})
    assert "SUPABASE_SECRET_KEY" in str(missing_both.value)
    assert "SUPABASE_URL" in str(missing_both.value)

    with pytest.raises(MissingCredentialsError):
        SupabaseCredentials.from_env({"SUPABASE_URL": BASE_URL})

    with pytest.raises(MissingCredentialsError):
        SupabaseCredentials.from_env({"SUPABASE_URL": BASE_URL, "SUPABASE_SECRET_KEY": "   "})


def test_credentials_reject_a_non_https_url() -> None:
    with pytest.raises(MissingCredentialsError):
        SupabaseCredentials.from_env(
            {"SUPABASE_URL": "http://project.supabase.co", "SUPABASE_SECRET_KEY": SECRET}
        )


def test_credentials_never_expose_the_secret_in_a_repr() -> None:
    rendered = repr(
        SupabaseCredentials.from_env({"SUPABASE_URL": BASE_URL, "SUPABASE_SECRET_KEY": SECRET})
    )

    assert SECRET not in rendered
    assert "<redacted>" in rendered


@respx.mock
def test_insert_ignoring_duplicates_makes_a_rerun_a_no_op() -> None:
    route = respx.post(f"{BASE_URL}/rest/v1/seasons").mock(
        return_value=httpx.Response(201, json=[])
    )

    with SupabaseRestClient(_credentials()) as client:
        for _ in range(2):
            client.insert_ignoring_duplicates(
                "seasons", [{"season": "2024-25"}], on_conflict="season"
            )

    assert route.call_count == 2
    for call in route.calls:
        assert "resolution=ignore-duplicates" in call.request.headers["Prefer"]
        assert call.request.url.params["on_conflict"] == "season"


@respx.mock
def test_upsert_sends_merge_duplicates_with_the_conflict_target() -> None:
    route = respx.post(f"{BASE_URL}/rest/v1/element_gameweek_stats").mock(
        return_value=httpx.Response(201, json=[])
    )

    with SupabaseRestClient(_credentials()) as client:
        client.upsert(
            "element_gameweek_stats",
            [{"season": "2024-25", "gameweek": 1, "element_id": 7, "minutes": 90}],
            on_conflict="season,gameweek,element_id",
        )

    request = route.calls[0].request
    assert "resolution=merge-duplicates" in request.headers["Prefer"]
    assert request.url.params["on_conflict"] == "season,gameweek,element_id"


@respx.mock
def test_writes_are_chunked_so_a_full_season_does_not_ship_in_one_request() -> None:
    route = respx.post(f"{BASE_URL}/rest/v1/element_gameweek_stats").mock(
        return_value=httpx.Response(201, json=[])
    )
    rows = [{"element_id": index} for index in range(1101)]

    with SupabaseRestClient(_credentials()) as client:
        client.insert("element_gameweek_stats", rows)

    assert route.call_count == 3
    batched = [len(json.loads(call.request.content)) for call in route.calls]
    assert batched == [500, 500, 101]


@respx.mock
def test_an_empty_write_never_reaches_the_network() -> None:
    route = respx.post(f"{BASE_URL}/rest/v1/teams")

    with SupabaseRestClient(_credentials()) as client:
        assert client.insert("teams", []) == []

    assert route.call_count == 0


@respx.mock
def test_a_rejected_write_raises_with_the_upstream_reason() -> None:
    respx.post(f"{BASE_URL}/rest/v1/elements").mock(
        return_value=httpx.Response(
            409,
            json={"code": "23503", "message": "violates foreign key constraint"},
        )
    )

    with SupabaseRestClient(_credentials()) as client, pytest.raises(SupabaseWriteError) as error:
        client.insert("elements", [{"element_id": 1}])

    assert "violates foreign key constraint" in str(error.value)
    assert SECRET not in str(error.value)


@respx.mock
def test_every_request_carries_the_service_role_headers() -> None:
    route = respx.post(f"{BASE_URL}/rest/v1/seasons").mock(
        return_value=httpx.Response(201, json=[])
    )

    with SupabaseRestClient(_credentials()) as client:
        client.insert("seasons", [{"season": "2023-24"}])

    headers = route.calls[0].request.headers
    assert headers["apikey"] == SECRET
    assert headers["Authorization"] == f"Bearer {SECRET}"


def test_idempotency_key_is_order_independent() -> None:
    assert build_idempotency_key({"season": "2024-25", "gameweek": 3}) == build_idempotency_key(
        {"gameweek": 3, "season": "2024-25"}
    )
    # Hashed rather than concatenated: the old "gameweek=3|season=2024-25" form
    # stored caller values in cleartext and could collide when one contained the
    # separator. Full coverage of both properties is in test_secret_hygiene.py.
    assert build_idempotency_key({"season": "2024-25", "gameweek": 3}) == (
        "3c52f80323bd001a240bd9a2bf53093a7af7b9bb21f85a2bf1db3b7d0a834d07"
    )


@respx.mock
def test_workflow_run_records_success_with_row_counts() -> None:
    created = respx.post(f"{BASE_URL}/rest/v1/workflow_runs").mock(
        return_value=httpx.Response(201, json=[])
    )
    finished = respx.patch(f"{BASE_URL}/rest/v1/workflow_runs").mock(
        return_value=httpx.Response(204)
    )

    with (
        SupabaseRestClient(_credentials()) as client,
        open_run(
            client,
            workflow_name="historical-ingest",
            parts={"season": "2024-25", "gameweek": 1},
        ) as run,
    ):
        run.record_rows("element_gameweek_stats", 640)
        run.record_rows("element_gameweek_stats", 20)

    opened: dict[str, Any] = json.loads(created.calls[0].request.content)[0]
    assert opened["status"] == "running"
    assert opened["workflow_name"] == "historical-ingest"

    closed: dict[str, Any] = json.loads(finished.calls[0].request.content)
    assert closed["status"] == "succeeded"
    assert closed["metadata"]["row_counts"] == {"element_gameweek_stats": 660}
    assert closed["finished_at"]


@respx.mock
def test_workflow_run_records_failure_without_leaking_the_payload() -> None:
    respx.post(f"{BASE_URL}/rest/v1/workflow_runs").mock(return_value=httpx.Response(201, json=[]))
    finished = respx.patch(f"{BASE_URL}/rest/v1/workflow_runs").mock(
        return_value=httpx.Response(204)
    )

    with (
        SupabaseRestClient(_credentials()) as client,
        pytest.raises(ValueError),
        open_run(client, workflow_name="historical-ingest", parts={"season": "2024-25"}),
    ):
        raise ValueError("gameweek 7 column map is missing 'defensive_contribution'")

    closed: dict[str, Any] = json.loads(finished.calls[0].request.content)
    assert closed["status"] == "failed"
    assert closed["failure_reason"].startswith("ValueError:")
    assert "defensive_contribution" in closed["failure_reason"]


@respx.mock
def test_a_duplicate_run_is_rejected_rather_than_silently_repeated() -> None:
    respx.post(f"{BASE_URL}/rest/v1/workflow_runs").mock(
        return_value=httpx.Response(
            409, json={"code": "23505", "message": "duplicate key value violates unique constraint"}
        )
    )

    with (
        SupabaseRestClient(_credentials()) as client,
        pytest.raises(WorkflowAlreadyRunningError),
        open_run(client, workflow_name="historical-ingest", parts={"season": "2024-25"}),
    ):
        pass
