"""The player-market survey: what it catalogues, and what it refuses to hide.

The survey exists to answer "which source has player props, and what exactly
does it return". Its only real failure mode is a silent one: a source that
stopped answering, reported as though it never had a credential, or a probe
that raised and took the other six down with it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from fpl_andres.adapters.player_props import (
    PROP_SOURCES,
    ProbeResult,
    PropSource,
    _api_football_season,
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

    def test_tackles_alone_are_not_direct_defcon_coverage(self) -> None:
        api_football = source_by_key("api-football")

        assert "defensive_contribution" not in api_football.covers


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


def _api_football(bets: list[dict[str, object]]) -> object:
    """A handler serving the three calls the api-football probe makes."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/odds/bets"):
            return httpx.Response(
                200, json={"response": [{"id": 1, "name": "Anytime Goal Scorer"}]}
            )
        if request.url.path.endswith("/fixtures"):
            return httpx.Response(200, json={"response": [{"fixture": {"id": 7001}}]})
        return httpx.Response(
            200,
            json={"response": [{"bookmakers": [{"id": 8, "name": "Bet365", "bets": bets}]}]},
        )

    return handler


class TestWhetherApiFootballPricesFootballers:
    """A catalogue of bet types is not an offer.

    Knowing this provider has heard of "Anytime Goal Scorer" says nothing about
    whether a Premier League fixture carries one, and nothing at all about
    whether its selections name footballers rather than sides. Only the second
    decides whether the source can be joined onto FPL element ids, and it was
    the question the survey never asked.
    """

    def _probe(self, bets: list[dict[str, object]]) -> str:
        with _client(_api_football(bets)) as client:  # type: ignore[arg-type]
            return probe_source(
                source_by_key("api-football"),
                client,
                env={"API_FOOTBALL_API_KEY": "k"},
            ).note

    def test_the_fixture_query_uses_the_campaign_start_year(self) -> None:
        assert _api_football_season(datetime(2026, 8, 17, tzinfo=UTC)) == "2026"
        assert _api_football_season(datetime(2027, 1, 17, tzinfo=UTC)) == "2026"

    def test_a_player_bet_is_named_with_a_selection_off_it(self) -> None:
        note = self._probe(
            [
                {
                    "name": "Anytime Goal Scorer",
                    "values": [
                        {"value": "Bukayo Saka", "odd": "2.50"},
                        {"value": "Kai Havertz", "odd": "3.10"},
                    ],
                }
            ]
        )

        assert "fixture 7001" in note
        assert "1 books" in note
        assert "Anytime Goal Scorer (2 selections, e.g. Bukayo Saka)" in note

    def test_a_fixture_priced_only_on_the_result_says_so(self) -> None:
        note = self._probe([{"name": "Match Winner", "values": [{"value": "Home", "odd": "1.50"}]}])

        assert "none of them player-level" in note

    def test_an_empty_market_is_not_reported_as_a_player_market(self) -> None:
        """A bet named but carrying nothing is a shut market, not a source."""
        note = self._probe([{"name": "Anytime Goal Scorer", "values": []}])

        assert "none of them player-level" in note

    def test_a_fixture_nobody_has_priced_is_told_apart_from_no_fixture(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/odds/bets"):
                return httpx.Response(200, json={"response": [{"id": 1, "name": "Match Winner"}]})
            if request.url.path.endswith("/fixtures"):
                return httpx.Response(200, json={"response": [{"fixture": {"id": 7001}}]})
            return httpx.Response(200, json={"response": []})

        with _client(handler) as client:
            note = probe_source(
                source_by_key("api-football"),
                client,
                env={"API_FOOTBALL_API_KEY": "k"},
            ).note

        assert "priced by nobody yet" in note

    def test_no_fixture_at_all_is_its_own_answer(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/odds/bets"):
                return httpx.Response(200, json={"response": [{"id": 1, "name": "Match Winner"}]})
            return httpx.Response(200, json={"response": []})

        with _client(handler) as client:
            note = probe_source(
                source_by_key("api-football"),
                client,
                env={"API_FOOTBALL_API_KEY": "k"},
            ).note

        assert "no Premier League fixture scheduled" in note

    def test_a_refusal_dressed_as_success_is_not_read_as_an_empty_league(self) -> None:
        """This host answers 200 and puts the refusal in `errors`.

        A plan that does not carry the odds endpoint, an exhausted allowance
        and a rejected key all arrive this way. Reading only `response` turns
        every one of them into "no Premier League fixture scheduled", which is
        a sentence about football rather than about the subscription, and it
        is why this source sat unwired while looking merely out of season.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/odds/bets"):
                return httpx.Response(200, json={"response": [{"id": 1, "name": "Match Winner"}]})
            return httpx.Response(
                200,
                json={"errors": {"plan": "Free plans do not have access to this endpoint."}},
            )

        with _client(handler) as client:
            note = probe_source(
                source_by_key("api-football"),
                client,
                env={"API_FOOTBALL_API_KEY": "k"},
            ).note

        assert "no Premier League fixture scheduled" not in note
        assert "Free plans do not have access" in note

    def test_the_catalogue_call_reports_its_own_refusal(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"errors": {"token": "Invalid API key."}})

        with _client(handler) as client:
            result = probe_source(
                source_by_key("api-football"),
                client,
                env={"API_FOOTBALL_API_KEY": "k"},
            )

        assert result.status == "refused"
        assert "Invalid API key." in result.note

    def test_an_empty_errors_list_is_the_hosts_way_of_saying_all_well(self) -> None:
        # The same field is `[]` on success and an object on failure.
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/odds/bets"):
                return httpx.Response(
                    200,
                    json={"errors": [], "response": [{"id": 1, "name": "Anytime Goal Scorer"}]},
                )
            if request.url.path.endswith("/fixtures"):
                return httpx.Response(
                    200, json={"errors": [], "response": [{"fixture": {"id": 7001}}]}
                )
            return httpx.Response(
                200,
                json={
                    "errors": [],
                    "response": [
                        {
                            "bookmakers": [
                                {
                                    "id": 8,
                                    "name": "Bet365",
                                    "bets": [
                                        {
                                            "name": "Anytime Goal Scorer",
                                            "values": [{"value": "Saka", "odd": "2.5"}],
                                        }
                                    ],
                                }
                            ]
                        }
                    ],
                },
            )

        with _client(handler) as client:
            result = probe_source(
                source_by_key("api-football"),
                client,
                env={"API_FOOTBALL_API_KEY": "k"},
            )

        assert result.status == "ok"
        assert "Anytime Goal Scorer (1 selections, e.g. Saka)" in result.note


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
