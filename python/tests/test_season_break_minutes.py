"""A season ends. "Lately" stops meaning anything.

Inside a season, a four-event half-life is the right question: a player rotated
last month is likely to be rotated next week. Across the summer break it is the
wrong question and an actively misleading one, because the last month of a
decided season is the least representative football anybody plays -- rotation,
rested legs, dead rubbers, and a title or a relegation already settled.

Left decayed, a striker who started thirty-five of thirty-eight but five of his
last seven is published as a sixty-three per cent starter for a season that has
not begun. That is not a claim about him; it is a claim about April. Across the
break the whole campaign is the evidence, because none of it is recent and all
of it is his record.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus
from fpl_andres.backtesting.projector import project_next_match

KICKOFF = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)
FORWARD = 4
#: The whole season, so the last event is 38 and the next match is a new one.
FULL_SEASON = 38


def corpus_for(starts: list[bool], *, through: int) -> SeasonCorpus:
    """One forward, plus a supporting cast so the league rates are readable."""
    corpus = SeasonCorpus(season="2025-26")
    for element_id in (1, 2, 3, 4, 5, 6):
        corpus.position_by_element[element_id] = FORWARD
        corpus.team_by_element[element_id] = element_id
        corpus.name_by_element[element_id] = f"P{element_id}"
        corpus.code_by_element[element_id] = 1000 + element_id

    for gameweek in range(1, through + 1):
        started = starts[gameweek - 1]
        rows = [
            ElementRow(
                gameweek=gameweek,
                element_id=1,
                element_code=1001,
                fixture_id=gameweek * 100 + 1,
                minutes=90 if started else 0,
                started=started,
                goals=1 if started else 0,
                assists=0,
                expected_goals=0.6 if started else 0.0,
                expected_assists=0.1 if started else 0.0,
                total_points=8 if started else 0,
                price_tenths=140,
                selected=1_000_000,
                kickoff_time=KICKOFF + timedelta(days=7 * gameweek),
            )
        ]
        # Everyone else plays every week, so nothing about the league rate is
        # being decided by the one player under test.
        rows.extend(
            ElementRow(
                gameweek=gameweek,
                element_id=other,
                element_code=1000 + other,
                fixture_id=gameweek * 100 + other,
                minutes=90,
                started=True,
                goals=0,
                assists=0,
                expected_goals=0.2,
                expected_assists=0.1,
                total_points=3,
                price_tenths=60,
                selected=100_000,
                kickoff_time=KICKOFF + timedelta(days=7 * gameweek),
            )
            for other in (2, 3, 4, 5, 6)
        )
        corpus.rows_by_gameweek[gameweek] = rows
    return corpus


def start_rate(starts: list[bool], *, through: int) -> float:
    projections = project_next_match(corpus_for(starts, through=through))
    for projection in projections:
        if projection.element_id == 1:
            return projection.minutes.probability_start
    raise AssertionError("the player under test was not projected")


#: Started thirty-five of thirty-eight, but rested for two of the last three.
RESTED_FINISH = [gameweek not in (36, 38, 20) for gameweek in range(1, 39)]
#: The same record, with the three misses early instead of late.
RESTED_START = [gameweek not in (2, 4, 20) for gameweek in range(1, 39)]


class AcrossTheBreakTheWholeSeasonCounts(unittest.TestCase):
    def test_a_rested_finish_does_not_define_the_next_season(self) -> None:
        # The reader's complaint, as an assertion. Thirty-five starts in
        # thirty-eight is a nailed starter whatever April looked like.
        assert start_rate(RESTED_FINISH, through=FULL_SEASON) > 0.8

    def test_when_the_misses_fell_no_longer_changes_the_answer(self) -> None:
        # The same record either way. A half-life of a whole season still leaves
        # the oldest observation at half the weight of the newest, so the two
        # are close rather than identical: measured at 0.874 against 0.905,
        # where the four-event decay had the late-rested reading at 0.63.
        late = start_rate(RESTED_FINISH, through=FULL_SEASON)
        early = start_rate(RESTED_START, through=FULL_SEASON)

        assert abs(late - early) < 0.05
        assert late > 0.85

    def test_a_player_who_lost_his_place_is_still_marked_down(self) -> None:
        # Flattening the decay must not turn into ignoring the record. Somebody
        # who started ten of thirty-eight is not a starter.
        fringe = [gameweek <= 10 for gameweek in range(1, 39)]

        assert start_rate(fringe, through=FULL_SEASON) < 0.45

    def test_mid_season_still_asks_what_he_is_doing_lately(self) -> None:
        # Inside a season the decay is the right question and is untouched: a
        # player dropped for the last three of twenty is not the same bet as one\
        # who missed three in August.
        dropped = [gameweek not in (18, 19, 20) for gameweek in range(1, 21)]
        early = [gameweek not in (2, 3, 4) for gameweek in range(1, 21)]

        assert start_rate(dropped, through=20) < start_rate(early, through=20)
