"""Every scoring route, priced.

Audit item #13. Split from `projector.py`, which was 882 lines covering rate
estimation, scoring and orchestration together.

The numbers here are the published FPL scoring table, not parameters. They were
verified by reconstructing realised points from component columns: 2025-26
reconciles to 34,383 against an actual 34,382, and 27,353 of 27,605 rows in
2024-25 match exactly, the remainder being managers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from fpl_andres.backtesting.corpus import ElementRow
from fpl_andres.backtesting.fixtures import RouteAdjustment
from fpl_andres.backtesting.rates import LeagueRates, shrunk_rate
from fpl_andres.models.minutes import MinutesProjection
from fpl_andres.models.player_rates import PlayerRateProjection

_MINUTES_PER_90 = 90.0

# Position priors, expressed per 90. Sourced from league-wide long-run rates
# rather than tuned, so the backtest cannot flatter itself by fitting them.
_GOAL_PRIOR: Mapping[int, float] = {1: 0.00, 2: 0.05, 3: 0.12, 4: 0.28}
_ASSIST_PRIOR: Mapping[int, float] = {1: 0.00, 2: 0.06, 3: 0.13, 4: 0.12}
# Appearance points only; the full scoring composition arrives with a promoted
# team-goal model. Stated here so the number is never mistaken for full xPTS.
_GOAL_POINTS: Mapping[int, int] = {1: 10, 2: 6, 3: 5, 4: 4}
_ASSIST_POINTS = 3
_CLEAN_SHEET_POINTS: Mapping[int, int] = {1: 4, 2: 4, 3: 1, 4: 0}
_SAVES_PER_POINT = 3
_GOALKEEPER = 1
_NEUTRAL_ADJUSTMENT = RouteAdjustment(1.0, 1.0, 1.0, 1.0, 1.0)
# Every remaining scoring route. Verified by reconstructing realised points from
# component columns: 2025-26 reconciles to 34,383 against an actual 34,382, and
# 27,353 of 27,605 rows in 2024-25 match exactly, the remainder being managers.
_CONCEDED_POINTS: Mapping[int, int] = {1: -1, 2: -1, 3: 0, 4: 0}
_CONCEDED_PER_POINT = 2
_YELLOW_CARD_POINTS = -1
_RED_CARD_POINTS = -3
_OWN_GOAL_POINTS = -2
_PENALTY_SAVE_POINTS = 5
_PENALTY_MISS_POINTS = -2
# Defensive contribution, new for 2025/26. Threshold is on the raw action count.
_DEFCON_POINTS: Mapping[int, int] = {1: 0, 2: 2, 3: 2, 4: 2}
_DEFCON_THRESHOLD: Mapping[int, int] = {2: 10, 3: 12, 4: 12}


def fixture_points(
    rows: Sequence[ElementRow],
    position: int,
    minutes: MinutesProjection,
    rates: PlayerRateProjection,
    league: LeagueRates,
    prior_nineties: float,
    adjustment: RouteAdjustment,
) -> float:
    ninety = minutes.expected_minutes / _MINUTES_PER_90
    appearance = (
        minutes.probability_appear - minutes.probability_sixty_minutes
    ) + minutes.probability_sixty_minutes * 2
    attacking = (
        ninety
        * (rates.goals_per_90 * _GOAL_POINTS[position] + rates.assists_per_90 * _ASSIST_POINTS)
        * adjustment.attacking
    )
    supporting = supporting_points(rows, position, minutes, league, prior_nineties, adjustment)
    return appearance + attacking + supporting


def supporting_points(
    rows: Sequence[ElementRow],
    position: int,
    minutes: MinutesProjection,
    league: LeagueRates,
    prior_nineties: float,
    adjustment: RouteAdjustment,
) -> float:
    """Every scoring route other than appearance, goals and assists.

    Priced from the player's own observed rate, shrunk toward the league rate for
    the position. These routes are position-specific, so omitting them shifts
    whole positions against each other rather than simply adding noise.
    """
    appearances = [row for row in rows if row.minutes > 0]
    if not appearances:
        return 0.0

    played = len(appearances)
    ninety = minutes.expected_minutes / _MINUTES_PER_90
    nineties_played = sum(row.minutes for row in appearances) / _MINUTES_PER_90

    def rate(events: float, prior: float) -> float:
        return shrunk_rate(events, nineties_played, prior, prior_nineties)

    clean_sheet_rate = sum(row.clean_sheets for row in appearances) / played
    # The fixture multiplier reaches 2.2, and the best defenders keep a clean
    # sheet in over half their matches, so the product can exceed one. A
    # probability cannot, and paying more than four points for one clean sheet
    # would flatter exactly the premium defenders in the softest fixtures.
    adjusted_clean_sheet = min(1.0, clean_sheet_rate * adjustment.clean_sheet)
    total = (
        minutes.probability_sixty_minutes
        * adjusted_clean_sheet
        * _CLEAN_SHEET_POINTS.get(position, 0)
    )
    total += ninety * (sum(row.bonus for row in appearances) / played)

    if position == _GOALKEEPER:
        # Saves pay one point per three, so the division happens per match and
        # is averaged after. Dividing the mean instead over-estimates by 0.34
        # points a start, about thirteen points across a keeper's season.
        # Shrunk like every other route: a keeper with two appearances was
        # otherwise priced on two appearances, and the thin bucket ranges from
        # zero to 1.50 save points a match against a league rate near 0.65.
        total += (
            ninety
            * rate(
                sum(row.saves // _SAVES_PER_POINT for row in appearances),
                league.save_points.get(position, 0.0),
            )
            * adjustment.saves
        )
        total += (
            ninety
            * rate(
                sum(row.penalties_saved for row in appearances),
                league.penalties_saved.get(position, 0.0),
            )
            * _PENALTY_SAVE_POINTS
        )

    conceded_points = _CONCEDED_POINTS.get(position, 0)
    if conceded_points:
        deductions = sum(row.goals_conceded // _CONCEDED_PER_POINT for row in appearances)
        total += (
            ninety
            * rate(deductions, league.conceded_deductions.get(position, 0.0))
            * conceded_points
            * adjustment.conceding
        )

    routes = (
        (sum(row.yellow_cards for row in appearances), league.yellow_cards, _YELLOW_CARD_POINTS),
        (sum(row.red_cards for row in appearances), league.red_cards, _RED_CARD_POINTS),
        (sum(row.own_goals for row in appearances), league.own_goals, _OWN_GOAL_POINTS),
        (
            sum(row.penalties_missed for row in appearances),
            league.penalties_missed,
            _PENALTY_MISS_POINTS,
        ),
    )
    for events, league_rate, points in routes:
        total += ninety * rate(events, league_rate.get(position, 0.0)) * points

    total += defensive_contribution_points(
        appearances,
        position,
        ninety,
        league,
        prior_nineties,
        nineties_played,
        adjustment.defensive_contribution,
    )

    return total


def defensive_contribution_points(
    appearances: Sequence[ElementRow],
    position: int,
    ninety: float,
    league: LeagueRates,
    prior_nineties: float,
    nineties_played: float,
    adjustment: float,
) -> float:
    """Zero before 2025/26, where the column is absent because the route did not exist."""
    threshold = _DEFCON_THRESHOLD.get(position)
    if threshold is None:
        return 0.0
    observed = [row for row in appearances if row.defensive_contribution is not None]
    if not observed:
        return 0.0
    hits = sum(1 for row in observed if (row.defensive_contribution or 0) >= threshold)
    seen = sum(row.minutes for row in observed) / _MINUTES_PER_90
    rate = shrunk_rate(hits, seen, league.defcon_hits.get(position, 0.0), prior_nineties)
    # A hit rate is a share of matches, so the fixture multiplier cannot lift it
    # past one however much pressure the opponent applies.
    adjusted = min(1.0, rate * adjustment)
    # Scaled by the share of the player's history that even had the column.
    coverage = min(1.0, seen / nineties_played) if nineties_played > 0 else 0.0
    return ninety * adjusted * _DEFCON_POINTS[position] * coverage


__all__ = [
    "defensive_contribution_points",
    "fixture_points",
    "supporting_points",
]
