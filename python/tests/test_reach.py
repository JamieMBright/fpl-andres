"""What a squad could actually reach, measured on a played season.

The published tables score a ranking against the whole game. These score a
season against the fifteen the method owned at the time, which is the only
population a manager ever chooses from.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fpl_andres.backtesting.captain_policies import CaptainCandidate, policy_names
from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus
from fpl_andres.simulation.minileague import (
    LeagueSettings,
    _candidate_pool,
    _opening_squad,
    simulate_league,
)
from fpl_andres.simulation.minileague_state import (
    GameweekSquad,
    LeagueResult,
    ManagerResult,
)
from fpl_andres.simulation.reach import (
    captaincy_reach,
    first_acquisition,
    giant_reach,
    owned_captain_policy_scores,
)
from fpl_andres.simulation.season import LineupRules
from fpl_andres.simulation.squad import SquadRules, validate_squad

SQUAD_RULES = SquadRules(budget_tenths=1000, club_limit=3, position_counts={1: 2, 2: 5, 3: 5, 4: 3})
LINEUP_RULES = LineupRules(
    starting_size=11,
    minimum_by_position={1: 1, 2: 3, 3: 2, 4: 1},
    maximum_by_position={1: 1, 2: 5, 3: 5, 4: 3},
)
KICKOFF = datetime(2024, 8, 17, 14, 0, tzinfo=UTC)


def synthetic_corpus() -> SeasonCorpus:
    """Twelve gameweeks, forty-eight players, points fixed by element id."""
    corpus = SeasonCorpus(season="2024-25")
    element_id = 1
    for position, count in ((1, 6), (2, 16), (3, 16), (4, 10)):
        for index in range(count):
            corpus.position_by_element[element_id] = position
            corpus.team_by_element[element_id] = 1 + (index % 12)
            corpus.name_by_element[element_id] = f"P{element_id}"
            element_id += 1

    for gameweek in range(1, 13):
        corpus.rows_by_gameweek[gameweek] = [
            ElementRow(
                gameweek=gameweek,
                element_id=player,
                element_code=player,
                fixture_id=gameweek * 100 + player,
                minutes=90,
                started=True,
                goals=1 if player % 7 == 0 else 0,
                assists=0,
                expected_goals=0.2,
                expected_assists=0.1,
                total_points=2 + (player % 5),
                price_tenths=40 + (position * 5),
                selected=1000,
                kickoff_time=KICKOFF + timedelta(days=7 * gameweek),
            )
            for player, position in corpus.position_by_element.items()
        ]
    return corpus


def played_season() -> LeagueResult:
    settings = LeagueSettings(
        squad_rules=SQUAD_RULES,
        lineup_rules=LINEUP_RULES,
        managers=4,
        advised_share=0.5,
        start_gameweek=7,
    )
    return simulate_league(synthetic_corpus(), settings, seed=1)


def staged(weeks: list[GameweekSquad], best: dict[int, int]) -> LeagueResult:
    """A league whose one advised manager played exactly these gameweeks."""
    result = LeagueResult(
        season="2024-25",
        settings=LeagueSettings(squad_rules=SQUAD_RULES, lineup_rules=LINEUP_RULES),
    )
    manager = ManagerResult(manager_id=0, policy="advised", seed=0)
    manager.gameweek_squads.extend(weeks)
    result.managers.append(manager)
    result.best_projected.update(best)
    return result


class TestTheSeasonKeepsItsSquads:
    def test_a_played_gameweek_records_the_squad_it_was_played_with(self) -> None:
        result = played_season()

        for manager in result.managers:
            assert len(manager.gameweek_squads) == len(manager.weekly_points)
            for week in manager.gameweek_squads:
                assert len(week.squad) == 15
                assert len(week.starters) == 11
                assert set(week.starters) <= set(week.squad)

    def test_the_captain_is_one_of_the_eleven(self) -> None:
        result = played_season()

        for manager in result.managers:
            for week in manager.gameweek_squads:
                assert week.captain in week.starters

    def test_the_best_projection_is_named_for_every_scored_gameweek(self) -> None:
        result = played_season()

        events = {week.event for week in result.managers[0].gameweek_squads}
        assert set(result.best_projected) >= events


class TestHowOftenTheGiantIsOnTheField:
    def test_counts_a_giant_the_squad_never_owned_as_out_of_reach(self) -> None:
        weeks = [
            GameweekSquad(event=index, squad=(1, 2, 3), starters=(1, 2), captain=1)
            for index in (1, 2, 3)
        ]
        reach = giant_reach(staged(weeks, {1: 99, 2: 99, 3: 99}))

        assert reach.gameweeks == 3
        assert reach.owned == 0
        assert reach.started_share == 0.0

    def test_separates_owning_him_from_playing_him(self) -> None:
        weeks = [
            GameweekSquad(event=1, squad=(1, 2, 9), starters=(1, 2), captain=1),
            GameweekSquad(event=2, squad=(1, 2, 9), starters=(1, 9), captain=9),
        ]
        reach = giant_reach(staged(weeks, {1: 9, 2: 9}))

        # Owned in both, benched in the first: a benched giant scores nothing.
        assert reach.owned == 2
        assert reach.started == 1
        assert reach.captained == 1

    def test_says_how_many_weeks_each_player_led_the_game(self) -> None:
        weeks = [
            GameweekSquad(event=index, squad=(), starters=(), captain=None) for index in (1, 2)
        ]
        reach = giant_reach(staged(weeks, {1: 7, 2: 7, 3: 8}))

        assert reach.weeks_at_the_top == {7: 2, 8: 1}

    def test_answers_nothing_rather_than_zero_for_a_season_never_played(self) -> None:
        reach = giant_reach(staged([], {1: 7}))

        assert reach.gameweeks == 0
        assert reach.owned_share == 0.0
        assert reach.captained_share == 0.0


class TestWhenAPremiumIsFinallyBought:
    def test_counts_the_weeks_played_before_he_was_owned(self) -> None:
        weeks = [
            GameweekSquad(event=1, squad=(1, 2), starters=(1,), captain=1),
            GameweekSquad(event=2, squad=(1, 2), starters=(1,), captain=1),
            GameweekSquad(event=3, squad=(1, 9), starters=(9,), captain=9),
        ]
        got = first_acquisition(staged(weeks, {}), 9)

        assert got.mean_wait == 2
        assert got.owned_gameweeks == 1
        assert got.never == 0

    def test_says_so_when_he_was_never_owned(self) -> None:
        weeks = [GameweekSquad(event=1, squad=(1, 2), starters=(1,), captain=1)]
        got = first_acquisition(staged(weeks, {}), 9)

        assert got.never == 1
        assert got.owned_gameweeks == 0
        assert got.mean_wait == 0.0

    def test_opening_with_him_is_no_wait_at_all(self) -> None:
        weeks = [GameweekSquad(event=1, squad=(9,), starters=(9,), captain=9)]
        got = first_acquisition(staged(weeks, {}), 9)

        assert got.mean_wait == 0.0
        assert got.never == 0


class TestOpeningWithANamedPlayer:
    def settings(self, open_with: tuple[int, ...] = ()) -> LeagueSettings:
        return LeagueSettings(
            squad_rules=SQUAD_RULES,
            lineup_rules=LINEUP_RULES,
            managers=4,
            advised_share=0.5,
            start_gameweek=7,
            open_with=open_with,
        )

    def test_puts_the_named_player_in_the_opening_fifteen(self) -> None:
        # The first recorded gameweek is the squad after that week's transfers,
        # so the opening fifteen is asked for directly rather than inferred.
        corpus = synthetic_corpus()
        pool = _candidate_pool(corpus, self.settings().start_gameweek)
        plain = _opening_squad(corpus, pool, self.settings(), 1)
        held = {player.element_id for player in plain}
        wanted = next(element for element in corpus.position_by_element if element not in held)

        forced = _opening_squad(corpus, pool, self.settings(open_with=(wanted,)), 1)

        assert wanted in {player.element_id for player in forced}

    def test_still_returns_a_legal_fifteen(self) -> None:
        corpus = synthetic_corpus()
        pool = _candidate_pool(corpus, self.settings().start_gameweek)

        forced = _opening_squad(corpus, pool, self.settings(open_with=(1,)), 1)

        assert len(forced) == 15
        validate_squad(list(forced), SQUAD_RULES)

    def test_changes_nothing_else_about_how_the_season_is_played(self) -> None:
        corpus = synthetic_corpus()
        plain = simulate_league(corpus, self.settings(), seed=1)
        forced = simulate_league(corpus, self.settings(open_with=()), seed=1)

        assert [manager.net_points for manager in forced.managers] == [
            manager.net_points for manager in plain.managers
        ]


class TestWhatCaptaincyCostsFromYourOwnEleven:
    def test_every_policy_can_choose_only_from_the_model_owned_xi(self) -> None:
        corpus = synthetic_corpus()
        actual = corpus.actual_points(7)
        weeks = [GameweekSquad(event=7, squad=(1, 2, 3), starters=(1, 2), captain=1)]
        candidates = {
            7: tuple(
                CaptainCandidate(
                    element_id=element,
                    expected_points={1: 4.0, 2: 8.0, 3: 20.0}[element],
                    component_points={1: 4.0, 2: 8.0, 3: 20.0}[element],
                    recent_points=5.0,
                    recent_deviation=0.0,
                    probability_start=1.0,
                    ownership={1: 50.0, 2: 10.0, 3: 100.0}[element],
                )
                for element in (1, 2, 3)
            )
        }

        scores = owned_captain_policy_scores(corpus, [staged(weeks, {})], candidates)

        assert tuple(scores) == policy_names()
        assert scores["crowd"].picks[0].element_id == 1
        assert {pick.element_id for score in scores.values() for pick in score.picks} <= {1, 2}
        assert {score.best_points for score in scores.values()} == {max(actual[1], actual[2])}

    def test_scores_the_armband_that_was_actually_worn(self) -> None:
        corpus = synthetic_corpus()
        actual = corpus.actual_points(7)
        weeks = [GameweekSquad(event=7, squad=(1, 2, 3), starters=(1, 2), captain=1)]

        reach = captaincy_reach(corpus, staged(weeks, {}))

        assert reach.gameweeks == 1
        assert reach.chosen_points == float(actual[1])

    def test_the_owned_ceiling_is_the_best_of_the_eleven_not_the_game(self) -> None:
        corpus = synthetic_corpus()
        actual = corpus.actual_points(7)
        weeks = [GameweekSquad(event=7, squad=(1, 2, 3), starters=(1, 2), captain=1)]

        reach = captaincy_reach(corpus, staged(weeks, {}))

        assert reach.owned_ceiling_points == float(max(actual[1], actual[2]))
        assert reach.game_ceiling_points == float(max(actual.values()))

    def test_names_the_regret_a_manager_could_have_avoided(self) -> None:
        corpus = synthetic_corpus()
        actual = corpus.actual_points(7)
        worse = min((1, 2, 3, 4, 5), key=lambda element: actual[element])
        better = max((1, 2, 3, 4, 5), key=lambda element: actual[element])
        weeks = [
            GameweekSquad(event=7, squad=(1, 2, 3, 4, 5), starters=(worse, better), captain=worse)
        ]

        reach = captaincy_reach(corpus, staged(weeks, {}))

        assert reach.owned_regret == float(actual[better] - actual[worse])

    def test_separates_a_bad_call_from_a_squad_that_could_not_reach(self) -> None:
        corpus = synthetic_corpus()
        actual = corpus.actual_points(7)
        weeks = [GameweekSquad(event=7, squad=(1,), starters=(1,), captain=1)]

        reach = captaincy_reach(corpus, staged(weeks, {}))

        # Perfect captaincy from a one-man eleven, and still short of the game.
        assert reach.owned_regret == 0.0
        assert reach.reach_gap == float(max(actual.values()) - actual[1])

    def test_a_played_season_reaches_less_than_the_whole_game(self) -> None:
        corpus = synthetic_corpus()
        reach = captaincy_reach(corpus, played_season())

        assert reach.gameweeks > 0
        assert reach.mean_chosen <= reach.mean_owned_ceiling
        assert reach.mean_owned_ceiling <= reach.mean_game_ceiling
