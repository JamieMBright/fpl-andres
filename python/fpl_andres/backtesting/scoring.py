"""Every scoring route, priced.

Split from `projector.py`, which was 882 lines covering rate
estimation, scoring and orchestration together.

The numbers here are the published FPL scoring table, not parameters. They were
verified by reconstructing realised points from component columns: 2025-26
reconciles to 34,383 against an actual 34,382, and 27,353 of 27,605 rows in
2024-25 match exactly, the remainder being managers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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

# Public names for the same table. `backtesting/reconcile.py` prices realised
# gameweeks from it to check this project's scoring against FPL's own, and a
# second copy of the constants would make that check vacuous.
GOAL_POINTS = _GOAL_POINTS
ASSIST_POINTS = _ASSIST_POINTS
CLEAN_SHEET_POINTS = _CLEAN_SHEET_POINTS
CONCEDED_POINTS = _CONCEDED_POINTS
CONCEDED_PER_POINT = _CONCEDED_PER_POINT
SAVES_PER_POINT = _SAVES_PER_POINT
YELLOW_CARD_POINTS = _YELLOW_CARD_POINTS
RED_CARD_POINTS = _RED_CARD_POINTS
OWN_GOAL_POINTS = _OWN_GOAL_POINTS
PENALTY_SAVE_POINTS = _PENALTY_SAVE_POINTS
PENALTY_MISS_POINTS = _PENALTY_MISS_POINTS
DEFCON_POINTS = _DEFCON_POINTS
DEFCON_THRESHOLD = _DEFCON_THRESHOLD


@dataclass(frozen=True)
class PointsBreakdown:
    """Expected points by route, in one match.

    A single expected-points number cannot be checked and cannot be argued with.
    These are the parts it is made of, and each responds to a fixture
    differently: a hard away tie suppresses clean sheets while raising saves.
    """

    appearance: float
    attacking: float
    clean_sheet: float
    bonus: float
    saves: float
    conceding: float
    discipline: float
    defensive_contribution: float

    @property
    def total(self) -> float:
        return (
            self.appearance
            + self.attacking
            + self.clean_sheet
            + self.bonus
            + self.saves
            + self.conceding
            + self.discipline
            + self.defensive_contribution
        )


def fixture_points(
    rows: Sequence[ElementRow],
    position: int,
    minutes: MinutesProjection,
    rates: PlayerRateProjection,
    league: LeagueRates,
    prior_nineties: float,
    adjustment: RouteAdjustment,
) -> float:
    return fixture_points_breakdown(
        rows, position, minutes, rates, league, prior_nineties, adjustment
    ).total


def fixture_points_breakdown(
    rows: Sequence[ElementRow],
    position: int,
    minutes: MinutesProjection,
    rates: PlayerRateProjection,
    league: LeagueRates,
    prior_nineties: float,
    adjustment: RouteAdjustment,
) -> PointsBreakdown:
    ninety = minutes.expected_minutes / _MINUTES_PER_90
    appearance = (
        minutes.probability_appear - minutes.probability_sixty_minutes
    ) + minutes.probability_sixty_minutes * 2
    attacking = (
        ninety
        * (rates.goals_per_90 * _GOAL_POINTS[position] + rates.assists_per_90 * _ASSIST_POINTS)
        * adjustment.attacking
    )
    supporting = supporting_breakdown(rows, position, minutes, league, prior_nineties, adjustment)
    return PointsBreakdown(
        appearance=appearance,
        attacking=attacking,
        clean_sheet=supporting.clean_sheet,
        bonus=supporting.bonus,
        saves=supporting.saves,
        conceding=supporting.conceding,
        discipline=supporting.discipline,
        defensive_contribution=supporting.defensive_contribution,
    )


def supporting_breakdown(
    rows: Sequence[ElementRow],
    position: int,
    minutes: MinutesProjection,
    league: LeagueRates,
    prior_nineties: float,
    adjustment: RouteAdjustment,
) -> PointsBreakdown:
    """Every scoring route other than appearance, goals and assists.

    Priced from the player's own observed rate, shrunk toward the league rate for
    the position. These routes are position-specific, so omitting them shifts
    whole positions against each other rather than simply adding noise.
    """
    empty = PointsBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    appearances = [row for row in rows if row.minutes > 0]
    if not appearances:
        return empty

    played = len(appearances)
    ninety = minutes.expected_minutes / _MINUTES_PER_90
    nineties_played = sum(row.minutes for row in appearances) / _MINUTES_PER_90

    def rate(events: float, prior: float) -> float:
        return shrunk_rate(events, nineties_played, prior, prior_nineties)

    def per_appearance(events: float, prior: float) -> float:
        """Shrink a per-match rate. Clean sheets and bonus are awarded per match,
        not per ninety, so the denominator is appearances rather than 90s."""
        return shrunk_rate(events, played, prior, prior_nineties)

    # Shrunk like every other route. Left raw, a defender with three matches and
    # two clean sheets was priced at a 67% rate for the rest of the season, and
    # a single early three-bonus became one bonus a match forever. Between them
    # these two routes are a fifth of every point awarded.
    clean_sheet_rate = per_appearance(
        sum(row.clean_sheets for row in appearances),
        league.clean_sheets.get(position, 0.0),
    )
    # The fixture multiplier reaches 2.2, and the best defenders keep a clean
    # sheet in over half their matches, so the product can exceed one. A
    # probability cannot, and paying more than four points for one clean sheet
    # would flatter exactly the premium defenders in the softest fixtures.
    adjusted_clean_sheet = min(1.0, clean_sheet_rate * adjustment.clean_sheet)
    clean_sheet = (
        minutes.probability_sixty_minutes
        * adjusted_clean_sheet
        * _CLEAN_SHEET_POINTS.get(position, 0)
    )
    bonus = ninety * per_appearance(
        sum(row.bonus for row in appearances),
        league.bonus.get(position, 0.0),
    )

    saves = 0.0
    if position == _GOALKEEPER:
        # Saves pay one point per three, so the division happens per match and
        # is averaged after. Dividing the mean instead over-estimates by 0.34
        # points a start, about thirteen points across a keeper's season.
        # Shrunk like every other route: a keeper with two appearances was
        # otherwise priced on two appearances, and the thin bucket ranges from
        # zero to 1.50 save points a match against a league rate near 0.65.
        saves += (
            ninety
            * rate(
                sum(row.saves // _SAVES_PER_POINT for row in appearances),
                league.save_points.get(position, 0.0),
            )
            * adjustment.saves
        )
        saves += (
            ninety
            * rate(
                sum(row.penalties_saved for row in appearances),
                league.penalties_saved.get(position, 0.0),
            )
            * _PENALTY_SAVE_POINTS
        )

    conceding = 0.0
    conceded_points = _CONCEDED_POINTS.get(position, 0)
    if conceded_points:
        deductions = sum(row.goals_conceded // _CONCEDED_PER_POINT for row in appearances)
        conceding = (
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
    discipline = sum(
        ninety * rate(events, league_rate.get(position, 0.0)) * points
        for events, league_rate, points in routes
    )

    return PointsBreakdown(
        appearance=0.0,
        attacking=0.0,
        clean_sheet=clean_sheet,
        bonus=bonus,
        saves=saves,
        conceding=conceding,
        discipline=discipline,
        defensive_contribution=defensive_contribution_points(
            appearances,
            position,
            ninety,
            league,
            prior_nineties,
            adjustment.defensive_contribution,
        ),
    )


def defensive_contribution_points(
    appearances: Sequence[ElementRow],
    position: int,
    ninety: float,
    league: LeagueRates,
    prior_nineties: float,
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
    # `seen` is the evidence that exists, and `shrunk_rate` already pulls a thin
    # sample toward the league rate in proportion to how thin it is. A coverage
    # term on top charged the same missing data twice: a defender with five
    # hundred of his three thousand minutes in 2025/26 was shrunk for having
    # five hundred, then scaled by a sixth for not having the other twenty-five
    # hundred -- hardest against the established defenders whose defcon record
    # is best evidenced.
    rate = shrunk_rate(hits, seen, league.defcon_hits.get(position, 0.0), prior_nineties)
    # A hit rate is a share of matches, so the fixture multiplier cannot lift it
    # past one however much pressure the opponent applies.
    adjusted = min(1.0, rate * adjustment)
    return ninety * adjusted * _DEFCON_POINTS[position]


__all__ = [
    "defensive_contribution_points",
    "fixture_points",
    "supporting_breakdown",
]
