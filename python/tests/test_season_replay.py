"""Replaying a completed season week by week.

The point of the ledger is that a total can be argued with. These pin the
arithmetic that makes that possible: the weeks add up to the total, the
transfers in the log are the transfers that were made, and the season starts
where a real one starts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus
from fpl_andres.simulation.minileague_state import LeagueSettings
from fpl_andres.simulation.replay import (
    benchmark_against,
    cohort_totals,
    replay_season,
)
from fpl_andres.simulation.season import LineupRules
from fpl_andres.simulation.squad import SquadRules

KICKOFF = datetime(2025, 8, 15, 18, 30, tzinfo=UTC)

SQUAD_RULES = SquadRules(budget_tenths=1000, club_limit=3, position_counts={1: 2, 2: 5, 3: 5, 4: 3})
LINEUP_RULES = LineupRules(
    starting_size=11,
    minimum_by_position={1: 1, 2: 3, 3: 2, 4: 1},
    maximum_by_position={1: 1, 2: 5, 3: 5, 4: 3},
)

REPLAY_SETTINGS = LeagueSettings(
    squad_rules=SQUAD_RULES,
    lineup_rules=LINEUP_RULES,
    managers=1,
    advised_share=1.0,
    start_gameweek=1,
)


def corpus_for(season: str, *, gameweeks: int = 10) -> SeasonCorpus:
    """A small but legal season: forty players, points fixed by element id."""
    corpus = SeasonCorpus(season=season)
    element_id = 1
    for position, count in ((1, 6), (2, 16), (3, 16), (4, 10)):
        for index in range(count):
            corpus.position_by_element[element_id] = position
            corpus.team_by_element[element_id] = 1 + (index % 12)
            corpus.name_by_element[element_id] = f"P{element_id}"
            element_id += 1

    for gameweek in range(1, gameweeks + 1):
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


def replay() -> object:
    return replay_season(
        corpus_for("2025-26"),
        previous=corpus_for("2024-25"),
        settings=REPLAY_SETTINGS,
    )


def test_the_replay_opens_in_gameweek_one_and_plays_to_the_end() -> None:
    """A total measured over 32 weeks is not comparable to one over 38."""
    result = replay()

    assert result.start_gameweek == 1
    assert [week.event for week in result.weeks] == list(range(1, 11))


def test_the_weeks_add_up_to_the_total() -> None:
    result = replay()

    assert sum(week.points for week in result.weeks) == result.total_points
    assert sum(week.hit_points for week in result.weeks) == result.hit_points
    # The running total is what a league table would show, so it is net.
    assert result.weeks[-1].running_total == result.net_points


def test_the_running_total_only_ever_moves_by_that_weeks_net_score() -> None:
    result = replay()

    running = 0
    for week in result.weeks:
        running += week.points - week.hit_points
        assert week.running_total == running


def test_every_transfer_made_appears_in_the_log() -> None:
    """A ledger that under-reports its own moves cannot be audited."""
    result = replay()

    logged = sum(len(week.transfers) for week in result.weeks)

    assert logged == result.transfers
    for week in result.weeks:
        for out, incoming in week.transfers:
            assert out != incoming


def test_a_hit_is_only_charged_in_a_week_that_transferred() -> None:
    result = replay()

    for week in result.weeks:
        if week.hit_points:
            assert week.transfers, f"GW{week.event} charged a hit with no transfer"


def test_the_opening_fifteen_comes_from_the_projection_not_the_seed() -> None:
    """Opening at GW1 there is no ownership to read, and the fallback is random.

    Handed last season the opening is built off the opening projection instead,
    so two runs of the same season open with the same team.
    """
    first = replay_season(
        corpus_for("2025-26"),
        previous=corpus_for("2024-25"),
        settings=REPLAY_SETTINGS,
        seed=1,
    )
    second = replay_season(
        corpus_for("2025-26"),
        previous=corpus_for("2024-25"),
        settings=REPLAY_SETTINGS,
        seed=99,
    )

    assert first.weeks[0].squad == second.weeks[0].squad


def test_the_bench_is_reported_separately_from_the_score() -> None:
    result = replay()

    for week in result.weeks:
        assert week.bench_points >= 0
        assert len(week.starters) <= len(week.squad)


def test_a_benchmark_needs_real_totals_to_compare_against() -> None:
    assert benchmark_against("2025-26", 2400, []) is None


def test_a_benchmark_counts_only_the_managers_it_beat() -> None:
    benchmark = benchmark_against("2025-26", 2000, [1900, 2000, 2100, 2200])

    assert benchmark is not None
    assert benchmark.managers == 4
    # Equal is not beaten.
    assert benchmark.beaten == 1
    assert benchmark.percentile == 25.0
    assert benchmark.best == 2200


def test_the_cohort_carries_real_totals_for_the_last_completed_season() -> None:
    """The comparison is only worth making if somebody real is on the other side."""
    totals = cohort_totals("2025-26")

    assert len(totals) > 1000
    assert max(totals) > 2000
