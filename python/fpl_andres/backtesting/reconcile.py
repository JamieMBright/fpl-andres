"""Rebuild realised points from the component columns, and name every mismatch.

The card has claimed for months that 2025-26 reconstructs to 34,383 against an
actual 34,382. That is a *total*, and a total is the weakest form of the claim:
thousands of rows can be individually wrong in cancelling directions and still
sum to within a point. The 2024/25 statement -- 27,353 of 27,605 rows exact --
is the strong one, and it existed only as a sentence somebody typed once.

So the reconciliation is code now, and it reports where it fails rather than
that it mostly does not. For every player-gameweek it prices the fourteen
routes from the columns FPL published, subtracts what FPL awarded, and keeps
the residual. A route that is systematically short shows up as a signed total
against that route rather than as a rounding error in the season sum.

## What this is not

It is not the projection. Nothing here forecasts anything: every input is a
realised column from a completed gameweek. It measures whether the scoring
table this project prices *with* agrees with the scoring FPL actually applied.
If it does not, every projected point built on that table is wrong by the same
amount, and no amount of modelling upstream will find it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from fpl_andres.backtesting.corpus import ElementRow
from fpl_andres.backtesting.scoring import (
    ASSIST_POINTS,
    CLEAN_SHEET_POINTS,
    CONCEDED_PER_POINT,
    CONCEDED_POINTS,
    DEFCON_POINTS,
    DEFCON_THRESHOLD,
    GOAL_POINTS,
    OWN_GOAL_POINTS,
    PENALTY_MISS_POINTS,
    PENALTY_SAVE_POINTS,
    RED_CARD_POINTS,
    SAVES_PER_POINT,
    YELLOW_CARD_POINTS,
)
from fpl_andres.season_rules import SeasonRules, rules_for

__all__ = [
    "ROUTES",
    "Reconciliation",
    "RowResidual",
    "reconcile_row",
    "reconcile_season",
]

#: An appearance is one point, and a full hour is two.
_APPEARANCE_POINTS = 1
_SIXTY_MINUTE_POINTS = 2
_SIXTY = 60

#: Every route priced, in the order a reader should read them. Appearance is
#: two rows in FPL's own table -- up to an hour, and an hour or more -- which is
#: why the count is fourteen and not thirteen.
ROUTES = (
    "appearance",
    "sixty_minutes",
    "goals",
    "assists",
    "clean_sheet",
    "conceding",
    "saves",
    "penalties_saved",
    "penalties_missed",
    "own_goals",
    "yellow_cards",
    "red_cards",
    "bonus",
    "defensive_contribution",
)


@dataclass(frozen=True)
class RowResidual:
    """One player-gameweek that did not reconcile."""

    gameweek: int
    element_id: int
    name: str
    position: int
    awarded: int
    rebuilt: int
    #: What each route contributed to the rebuild, so a gap can be attributed.
    routes: Mapping[str, int]

    @property
    def residual(self) -> int:
        """Rebuilt minus awarded. Positive means this project over-credits."""
        return self.rebuilt - self.awarded


@dataclass
class Reconciliation:
    """How a season's realised points rebuild from their own component columns."""

    season: str
    rows: int = 0
    exact: int = 0
    awarded: int = 0
    rebuilt: int = 0
    #: Signed residual totalled by position, because a route that is wrong is
    #: usually wrong for one position only.
    by_position: dict[int, int] = field(default_factory=dict)
    #: Total disagreement ignoring sign, over every row rather than the kept
    #: ones. The number a season total hides: a season summing to within a
    #: point can still be built from thousands of offsetting errors.
    absolute: int = 0
    #: The rows that disagreed, worst first, capped so a report stays readable.
    worst: list[RowResidual] = field(default_factory=list)

    @property
    def residual(self) -> int:
        return self.rebuilt - self.awarded

    @property
    def exact_share(self) -> float | None:
        return self.exact / self.rows if self.rows else None


def reconcile_row(
    row: ElementRow, position: int, rules: SeasonRules | None = None
) -> Mapping[str, int]:
    """Price one realised gameweek from its own columns, route by route."""
    played = row.minutes > 0
    full = row.minutes >= _SIXTY
    routes = {
        "appearance": _APPEARANCE_POINTS if played else 0,
        "sixty_minutes": _SIXTY_MINUTE_POINTS - _APPEARANCE_POINTS if full else 0,
        "goals": row.goals * GOAL_POINTS.get(position, 0),
        "assists": row.assists * ASSIST_POINTS,
        "clean_sheet": (row.clean_sheets * CLEAN_SHEET_POINTS.get(position, 0) if full else 0),
        "conceding": (row.goals_conceded // CONCEDED_PER_POINT) * CONCEDED_POINTS.get(position, 0),
        "saves": (row.saves // SAVES_PER_POINT),
        "penalties_saved": row.penalties_saved * PENALTY_SAVE_POINTS,
        "penalties_missed": row.penalties_missed * PENALTY_MISS_POINTS,
        "own_goals": row.own_goals * OWN_GOAL_POINTS,
        "yellow_cards": row.yellow_cards * YELLOW_CARD_POINTS,
        "red_cards": row.red_cards * RED_CARD_POINTS,
        "bonus": row.bonus,
        "defensive_contribution": _defensive_contribution(row, position, rules),
    }
    return routes


def _defensive_contribution(row: ElementRow, position: int, rules: SeasonRules | None) -> int:
    """Two points for clearing the bar, and nothing at all before 2025/26.

    The rulebook decides, not the column. A null before the route existed and a
    null because nobody populated the column are the same byte and different
    facts, and only the first should be priced at zero without complaint.
    """
    if rules is not None and not rules.defensive_contribution:
        return 0
    if row.defensive_contribution is None:
        return 0
    threshold = DEFCON_THRESHOLD.get(position)
    if threshold is None:
        return 0
    return DEFCON_POINTS.get(position, 0) if row.defensive_contribution >= threshold else 0


def reconcile_season(
    rows_by_gameweek: Mapping[int, Sequence[ElementRow]],
    positions: Mapping[int, int],
    names: Mapping[int, str],
    *,
    season: str,
    keep_worst: int = 40,
) -> Reconciliation:
    """Reconcile every row in a season and keep the ones that disagreed."""
    outcome = Reconciliation(season=season)
    rules = rules_for(season)
    residuals: list[RowResidual] = []

    for gameweek in sorted(rows_by_gameweek):
        for row in rows_by_gameweek[gameweek]:
            position = positions.get(row.element_id, 0)
            routes = reconcile_row(row, position, rules)
            rebuilt = sum(routes.values())
            outcome.rows += 1
            outcome.awarded += row.total_points
            outcome.rebuilt += rebuilt
            if rebuilt == row.total_points:
                outcome.exact += 1
                continue
            gap = rebuilt - row.total_points
            outcome.by_position[position] = outcome.by_position.get(position, 0) + gap
            residuals.append(
                RowResidual(
                    gameweek=gameweek,
                    element_id=row.element_id,
                    name=names.get(row.element_id, f"#{row.element_id}"),
                    position=position,
                    awarded=row.total_points,
                    rebuilt=rebuilt,
                    routes=routes,
                )
            )

    # Kept in full for the absolute residual, then trimmed for the report: the
    # count of disagreeing rows is the finding, the identity of the fortieth
    # worst is not.
    residuals.sort(key=lambda entry: (-abs(entry.residual), entry.gameweek, entry.element_id))
    outcome.absolute = sum(abs(entry.residual) for entry in residuals)
    outcome.worst = residuals[:keep_worst]
    return outcome
