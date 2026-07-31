"""Was a recommendation wrong, or just unlucky?

There is always a hindsight-optimal transfer, but scoring against it punishes a
model for things nobody could forecast. A defender heading in twice from corners
is not a miss, it is variance. Scoring against it would teach the model to chase
noise.

So the gap between what we did and the perfect answer is split in two:

- **decision regret** is the expected points we left on the table relative to
  our own best available option. This is entirely our fault and is the only
  part worth optimising.
- **luck regret** is the gap between the best option by expectation and the
  best option in hindsight. Nobody could have claimed it, and a model that
  appears to capture it is overfitting.

Each hindsight-best move is also classified by whether we *could* have found it:
inside our shortlist, ranked first, or invisible to the model entirely.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "Foresight",
    "GameweekRegret",
    "SeasonRegret",
    "evaluate_gameweek",
    "summarise",
]


class Foresight(StrEnum):
    """Whether the hindsight-best move was reachable from what we knew."""

    RECOMMENDED = "recommended"
    SHORTLISTED = "shortlisted"
    UNFORESEEABLE = "unforeseeable"


@dataclass(frozen=True)
class GameweekRegret:
    gameweek: int
    chosen_element: int | None
    model_best_element: int | None
    hindsight_best_element: int | None
    decision_regret: float
    luck_regret: float
    realised_regret: float
    foresight: Foresight

    @property
    def followed_own_model(self) -> bool:
        return self.decision_regret <= 1e-9


@dataclass
class SeasonRegret:
    season: str
    shortlist_size: int
    gameweeks: list[GameweekRegret] = field(default_factory=list)

    @property
    def mean_decision_regret(self) -> float | None:
        values = [week.decision_regret for week in self.gameweeks]
        return statistics.mean(values) if values else None

    @property
    def mean_luck_regret(self) -> float | None:
        values = [week.luck_regret for week in self.gameweeks]
        return statistics.mean(values) if values else None

    @property
    def foresight_shares(self) -> dict[str, float]:
        if not self.gameweeks:
            return {}
        counts: dict[str, int] = {}
        for week in self.gameweeks:
            counts[week.foresight.value] = counts.get(week.foresight.value, 0) + 1
        return {key: value / len(self.gameweeks) for key, value in counts.items()}

    @property
    def avoidable_share(self) -> float | None:
        """How much of the total shortfall we could actually have prevented.

        The complement is variance. A model near zero here is already taking the
        best option available to it, and further gains must come from better
        projections rather than better decisions.
        """
        total = sum(abs(week.realised_regret) for week in self.gameweeks)
        if total <= 0:
            return None
        return sum(abs(week.decision_regret) for week in self.gameweeks) / total


def evaluate_gameweek(
    gameweek: int,
    *,
    projected: Mapping[int, float],
    actual: Mapping[int, float],
    candidates: Sequence[int],
    chosen: int | None,
    shortlist_size: int = 10,
) -> GameweekRegret:
    """Score one decision against both the best forecast and the best outcome.

    ``candidates`` is the set of moves that were legally available: budget, club
    limit and position already applied. Scoring against players who could not
    have been bought would measure the rules, not the model.
    """
    available = [element for element in candidates if element in projected and element in actual]
    if not available:
        return GameweekRegret(
            gameweek=gameweek,
            chosen_element=chosen,
            model_best_element=None,
            hindsight_best_element=None,
            decision_regret=0.0,
            luck_regret=0.0,
            realised_regret=0.0,
            foresight=Foresight.UNFORESEEABLE,
        )

    model_best = max(available, key=lambda element: projected[element])
    hindsight_best = max(available, key=lambda element: actual[element])
    shortlist = sorted(available, key=lambda element: -projected[element])[:shortlist_size]

    chosen_projected = projected.get(chosen, 0.0) if chosen is not None else 0.0
    chosen_actual = actual.get(chosen, 0.0) if chosen is not None else 0.0

    if hindsight_best == model_best:
        foresight = Foresight.RECOMMENDED
    elif hindsight_best in shortlist:
        foresight = Foresight.SHORTLISTED
    else:
        foresight = Foresight.UNFORESEEABLE

    return GameweekRegret(
        gameweek=gameweek,
        chosen_element=chosen,
        model_best_element=model_best,
        hindsight_best_element=hindsight_best,
        # Measured in expected points: this is the part we controlled.
        decision_regret=max(0.0, projected[model_best] - chosen_projected),
        # Measured in realised points: this is the part we did not.
        luck_regret=max(0.0, actual[hindsight_best] - actual[model_best]),
        realised_regret=max(0.0, actual[hindsight_best] - chosen_actual),
        foresight=foresight,
    )


def summarise(season: str, weeks: Sequence[GameweekRegret], *, shortlist_size: int) -> SeasonRegret:
    outcome = SeasonRegret(season=season, shortlist_size=shortlist_size)
    outcome.gameweeks.extend(weeks)
    return outcome
