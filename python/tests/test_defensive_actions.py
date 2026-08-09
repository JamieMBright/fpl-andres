"""Counting the defensive-contribution bar for the position being projected.

FPL publishes the count for the position a player held at the time and it
reclassifies players. The components let the count be re-derived, which is the
difference between judging a converted wing-back on his midfield record and
judging him on a defender's version of it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fpl_andres.backtesting.corpus import ElementRow
from fpl_andres.backtesting.rates import defensive_actions

KICKOFF = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)


def _row(
    *,
    defensive_contribution: int | None = None,
    clearances_blocks_interceptions: int | None = None,
    tackles: int | None = None,
    recoveries: int | None = None,
) -> ElementRow:
    return ElementRow(
        gameweek=1,
        element_id=1,
        element_code=1,
        fixture_id=1,
        minutes=90,
        started=True,
        goals=0,
        assists=0,
        expected_goals=None,
        expected_assists=None,
        total_points=2,
        price_tenths=50,
        selected=None,
        kickoff_time=KICKOFF,
        defensive_contribution=defensive_contribution,
        clearances_blocks_interceptions=clearances_blocks_interceptions,
        tackles=tackles,
        recoveries=recoveries,
    )


DEFENDER = 2
MIDFIELDER = 3
FORWARD = 4
GOALKEEPER = 1


def test_a_defender_counts_clearances_and_tackles_and_not_recoveries() -> None:
    """Verified against the live bootstrap: Gabriel 239 + 38 = 277, 64 recoveries ignored."""
    row = _row(clearances_blocks_interceptions=239, tackles=38, recoveries=64)

    assert defensive_actions(row, DEFENDER) == 277


def test_a_midfielder_counts_recoveries_too() -> None:
    """Rice: 127 + 69 + 180 = 376, which is what FPL published for him."""
    row = _row(clearances_blocks_interceptions=127, tackles=69, recoveries=180)

    assert defensive_actions(row, MIDFIELDER) == 376


def test_a_forward_counts_the_same_three_as_a_midfielder() -> None:
    row = _row(clearances_blocks_interceptions=10, tackles=5, recoveries=20)

    assert defensive_actions(row, FORWARD) == 35


def test_a_reclassified_defender_gets_his_recoveries_back() -> None:
    """The case the components exist for.

    Timber's published count as a defender is 82 + 66 = 148 and excludes 97
    recoveries. Moved to midfield he faces a bar of twelve rather than ten, and
    counting him on the label would apply the higher bar to the lower count --
    penalising him twice for a change FPL made on his behalf.
    """
    row = _row(
        defensive_contribution=148,
        clearances_blocks_interceptions=82,
        tackles=66,
        recoveries=97,
    )

    assert defensive_actions(row, DEFENDER) == 148
    assert defensive_actions(row, MIDFIELDER) == 245


def test_a_keeper_has_no_bar_rather_than_a_count_of_zero() -> None:
    row = _row(clearances_blocks_interceptions=37, tackles=1, recoveries=304)

    assert defensive_actions(row, GOALKEEPER) is None


def test_the_published_label_stands_in_when_a_component_is_missing() -> None:
    """Every season before 2025/26, where the archive published no components."""
    assert defensive_actions(_row(defensive_contribution=11), DEFENDER) == 11


def test_a_missing_recovery_count_falls_back_rather_than_undercounting() -> None:
    """A midfielder's bar counts recoveries, so summing without them is not the count."""
    row = _row(
        defensive_contribution=30,
        clearances_blocks_interceptions=12,
        tackles=8,
    )

    assert defensive_actions(row, MIDFIELDER) == 30


def test_nothing_published_at_all_stays_unmeasured() -> None:
    assert defensive_actions(_row(), DEFENDER) is None
