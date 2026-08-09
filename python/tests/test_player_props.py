"""The player-market survey: what it catalogues, and what it refuses to hide.

The survey exists to answer "which source has player props, and what exactly
does it return". Its only real failure mode is a silent one: a source that
stopped answering, reported as though it never had a credential, or a probe
that raised and took the other six down with it.
"""

from __future__ import annotations

import httpx
import pytest

from fpl_andres.adapters.player_props import (
    PROP_SOURCES,
    ProbeResult,
    PropSource,
    field_paths,
    probe_source,
    source_by_key,
    survey,
)
from fpl_andres.cli.survey_player_props import _as_json, _selected, main


def _client(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


class TestFieldPaths:
    def test_reports_every_dotted_path_in_a_document(self) -> None:
        paths = field_paths({"a": {"b": 1}, "c": 2})

        assert paths == {"a", "a.b", "c"}

    def test_collapses_a_list_to_one_shape(self) -> None:
        # A hundred fixtures describe one schema. Reporting a hundred
        # near-identical paths would bury the difference that matters.
        paths = field_paths({"events": [{"id": 1}, {"id": 2}, {"home": "x"}]})

        assert paths == {"events", "events[].id", "events[].home"}

    def test_a_string_is_a_value_and_not_a_sequence(self) -> None:
        assert field_paths({"name": "Haaland"}) == {"name"}


class TestCatalogue:
    def test_every_source_has_a_unique_key(self) -> None:
        keys = [source.key for source in PROP_SOURCES]

        assert len(keys) == len(set(keys))

    def test_every_source_states_its_terms(self) -> None:
        # Depending on a feed whose licence nobody read is how a project
        # acquires an obligation it cannot see.
        for source in PROP_SOURCES:
            assert source.terms.strip(), source.key
            assert source.homepage.startswith("https://"), source.key

    def test_an_unknown_key_names_the_ones_that_exist(self) -> None:
        with pytest.raises(KeyError, match="the-odds-api"):
            source_by_key("betfair-but-misspelled")


class TestProbing:
    def test_a_missing_credential_is_reported_not_raised(self) -> None:
        source = source_by_key("the-odds-api")

        with _client(lambda request: httpx.Response(200, json={})) as client:
            result = probe_source(source, client, env={})

        assert result.status == "no_credential"
        assert "THE_ODDS_API_KEY" in result.note

    def test_a_credential_never_reaches_the_report(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "bad key"})

        source = source_by_key("the-odds-api")
        with _client(handler) as client:
            result = probe_source(source, client, env={"THE_ODDS_API_KEY": "s3cret"})

        assert result.status == "refused"
        assert "s3cret" not in result.note
        assert "s3cret" not in str(result)

    def test_a_blocked_host_is_reported_as_blocked(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("tls handshake refused", request=request)

        source = source_by_key("football-data")
        with _client(handler) as client:
            result = probe_source(source, client, env={})

        assert result.status == "unreachable"
        assert "ConnectError" in result.note

    def test_one_broken_source_does_not_stop_the_rest(self) -> None:
        # The whole point of a survey is the comparison. A single dead host
        # taking the table with it is the one outcome that makes it useless.
        def handler(request: httpx.Request) -> httpx.Response:
            if "football-data" in str(request.url):
                raise httpx.ConnectError("blocked", request=request)
            return httpx.Response(200, json={"elements": [{"id": 1, "web_name": "x"}]})

        sources = (source_by_key("football-data"), source_by_key("fpl-bootstrap"))
        with _client(handler) as client:
            results = survey(client, sources, env={})

        assert [result.status for result in results] == ["unreachable", "ok"]

    def test_football_data_reports_its_columns(self) -> None:
        csv = "Div,Date,HomeTeam,AwayTeam,AvgH,AvgD,AvgA\nE0,01/01/26,Arsenal,Chelsea,1.5,4,6\n"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=csv.encode("utf-8-sig"))

        with _client(handler) as client:
            result = probe_source(source_by_key("football-data"), client, env={})

        assert result.status == "ok"
        # The BOM must not become part of the first column's name; that exact
        # failure once cost this project a whole season of odds.
        assert result.fields[0] == "AvgA"
        assert "Div" in result.fields

    def test_the_odds_api_names_the_markets_it_returned(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/events"):
                return httpx.Response(200, json=[{"id": "abc", "home_team": "Arsenal"}])
            return httpx.Response(
                200,
                json={
                    "id": "abc",
                    "bookmakers": [
                        {
                            "key": "williamhill",
                            "markets": [
                                {"key": "player_goal_scorer_anytime", "outcomes": []},
                                {"key": "player_assists", "outcomes": []},
                            ],
                        },
                    ],
                },
            )

        with _client(handler) as client:
            result = probe_source(
                source_by_key("the-odds-api"),
                client,
                env={"THE_ODDS_API_KEY": "k"},
            )

        assert result.status == "ok"
        assert result.markets == ("player_assists", "player_goal_scorer_anytime")
        assert "bookmakers[].markets[].key" in result.fields

    def test_the_odds_api_probes_the_soonest_fixture(self) -> None:
        """Props open days before kickoff, so an arbitrary fixture has none.

        The host does not list fixtures in date order. Probing whichever came
        first reported an empty catalogue for a source that has one, which is
        why this reads far thinner than the sources beside it.
        """
        asked: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/events"):
                return httpx.Response(
                    200,
                    json=[
                        {"id": "december", "commence_time": "2026-12-26T15:00:00Z"},
                        {"id": "saturday", "commence_time": "2026-08-22T14:00:00Z"},
                    ],
                )
            asked.append(request.url.path)
            return httpx.Response(200, json={"id": "saturday", "bookmakers": []})

        with _client(handler) as client:
            probe_source(source_by_key("the-odds-api"), client, env={"THE_ODDS_API_KEY": "k"})

        assert asked == ["/v4/sports/soccer_epl/events/saturday/odds"]

    def test_the_odds_api_reports_its_depth_and_what_it_cost(self) -> None:
        """A shut market and a wrong request both return nothing.

        Naming the fixture, the books, the outcomes and the markets that did
        not arrive is what separates them. The quota is here because a free
        tier shared with the ingest can be spent without any host warning.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/events"):
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": "abc",
                            "home_team": "Arsenal",
                            "away_team": "Bournemouth",
                            "commence_time": "2026-08-22T14:00:00Z",
                        }
                    ],
                )
            return httpx.Response(
                200,
                headers={"x-requests-remaining": "412", "x-requests-last": "80"},
                json={
                    "id": "abc",
                    "bookmakers": [
                        {
                            "key": "williamhill",
                            "markets": [
                                {
                                    "key": "player_goal_scorer_anytime",
                                    "outcomes": [{"description": "Saka", "price": 3.0}],
                                }
                            ],
                        },
                        {"key": "bet365", "markets": []},
                    ],
                },
            )

        with _client(handler) as client:
            result = probe_source(
                source_by_key("the-odds-api"),
                client,
                env={"THE_ODDS_API_KEY": "k"},
            )

        assert "Arsenal v Bournemouth" in result.note
        assert "2 books, 1 outcomes" in result.note
        assert "player_assists" in result.note
        assert "cost 80, 412 left" in result.note

    def test_api_football_reports_what_its_daily_allowance_has_left(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"x-ratelimit-requests-remaining": "63"},
                json={"response": [{"id": 1, "name": "Anytime Goal Scorer"}]},
            )

        with _client(handler) as client:
            result = probe_source(
                source_by_key("api-football"),
                client,
                env={"API_FOOTBALL_API_KEY": "k"},
            )

        assert "63 left" in result.note

    def test_a_host_that_publishes_no_counter_says_so(self) -> None:
        """Nought left and no answer must never read the same."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"response": []})

        with _client(handler) as client:
            result = probe_source(
                source_by_key("api-football"),
                client,
                env={"API_FOOTBALL_API_KEY": "k"},
            )

        assert "quota not reported" in result.note


class TestCli:
    def test_no_selection_probes_everything(self) -> None:
        assert _selected(None) == PROP_SOURCES

    def test_the_json_catalogue_carries_every_field(self) -> None:
        source = PropSource(
            key="stub",
            name="Stub",
            homepage="https://example.invalid",
            credential_env=(),
            covers=("goal",),
            terms="None.",
            probe=lambda client, env: ProbeResult(key="stub", status="ok", note=""),
        )
        result = ProbeResult(
            key="stub",
            status="ok",
            note="",
            fields=("a", "b"),
            markets=("m",),
        )

        payload = _as_json([source], [result])

        assert payload["sources"] == [
            {
                "key": "stub",
                "name": "Stub",
                "homepage": "https://example.invalid",
                "terms": "None.",
                "credentialEnv": [],
                "covers": ["goal"],
                "status": "ok",
                "note": "",
                "httpStatus": None,
                "markets": ["m"],
                "fields": ["a", "b"],
            },
        ]

    def test_a_required_source_that_stayed_silent_fails_the_run(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Without this, a key that quietly expired reads as a clean run that
        # simply found nothing -- the failure mode the whole CLI guards.
        monkeypatch.setattr(
            "fpl_andres.cli.survey_player_props.survey",
            lambda client, sources: tuple(
                ProbeResult(key=source.key, status="no_credential", note="") for source in sources
            ),
        )

        assert main(["--source", "football-data", "--require", "football-data"]) == 1

    def test_requiring_a_source_that_was_not_probed_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "fpl_andres.cli.survey_player_props.survey",
            lambda client, sources: tuple(
                ProbeResult(key=source.key, status="ok", note="") for source in sources
            ),
        )

        assert main(["--source", "football-data", "--require", "the-odds-api"]) == 1

    def test_a_clean_survey_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "fpl_andres.cli.survey_player_props.survey",
            lambda client, sources: tuple(
                ProbeResult(key=source.key, status="ok", note="") for source in sources
            ),
        )

        assert main(["--source", "football-data", "--require", "football-data"]) == 0
