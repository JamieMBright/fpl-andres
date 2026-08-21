from __future__ import annotations

from datetime import UTC, datetime

import httpx

from fpl_andres.adapters.api_football_historical import (
    probe_historical_seasons,
)


def _client(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_probe_reports_an_accessible_historical_fixture_without_exposing_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/fixtures"):
            return httpx.Response(
                200,
                headers={"x-ratelimit-requests-remaining": "97"},
                json={"errors": [], "response": [{"fixture": {"id": 123}}]},
            )
        return httpx.Response(
            200,
            headers={"x-ratelimit-requests-remaining": "96"},
            json={
                "errors": [],
                "response": [
                    {
                        "fixture": {"id": 123},
                        "bookmakers": [
                            {
                                "name": "ExampleBook",
                                "bets": [
                                    {
                                        "name": "Anytime Goal Scorer",
                                        "values": [{"value": "Player", "odd": "2.5"}],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        )

    fetched_at = datetime(2026, 8, 21, 12, tzinfo=UTC)
    with _client(handler) as client:
        result = probe_historical_seasons(
            client,
            "secret-must-not-appear",
            seasons=(2022,),
            fetched_at=fetched_at,
        )

    assert len(result) == 1
    assert result[0].status == "accessible"
    assert result[0].fixture_id == "123"
    assert result[0].bookmakers == 1
    assert result[0].bets == 1
    assert result[0].player_named_selections == 1
    assert result[0].response_bytes > 0
    assert result[0].fetched_at == fetched_at
    assert result[0].quota_remaining == 96
    assert result[0].error is None


def test_probe_preserves_plan_refusal_without_logging_the_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-ratelimit-requests-remaining": "98"},
            json={"errors": {"plan": "Historical odds require a paid plan."}},
        )

    with _client(handler) as client:
        result = probe_historical_seasons(
            client,
            "secret-must-not-appear",
            seasons=(2022,),
            fetched_at=datetime(2026, 8, 21, 12, tzinfo=UTC),
        )[0]

    assert result.status == "refused"
    assert result.error == "plan: Historical odds require a paid plan."
    assert "secret" not in repr(result)


def test_probe_distinguishes_no_fixture_and_no_player_selection() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"errors": [], "response": []})
        return httpx.Response(
            200,
            json={
                "errors": [],
                "response": [{"fixture": {"id": 456}}],
            },
        )

    with _client(handler) as client:
        results = probe_historical_seasons(
            client,
            "k",
            seasons=(2022, 2023),
            fetched_at=datetime(2026, 8, 21, 12, tzinfo=UTC),
        )

    assert results[0].status == "no-fixture"
    assert results[1].status == "no-player-selections"
