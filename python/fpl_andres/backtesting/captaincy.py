"""Score captain rules inside the legal eleven a model-managed squad fielded.

A transfer moves one squad slot by the difference between two players. The
captain doubles whoever is already in the eleven, so the same gameweek's
captain decision swings two to three times what a routine transfer does. The
model was never measured on it: `score_season` graded the whole pool's ranking
and said nothing about the one pick that gets multiplied.

The caller owns the population boundary: validation passes the eleven retained
by a legal season simulation. This module never expands it from ownership or
realised outcomes, so every scored option was reachable by that manager.

## What is reported

The realised points of the chosen player, not the doubled figure. Doubling is a
constant on every method and on the ceiling, so it changes no ordering; leaving
it out keeps the number something that can be checked against a scoresheet.
Over a season the gap between two methods is worth twice what it reads.

The ceiling is the best captain available *in the same eleven*, so the regret
is a decision a manager could have made, not a fantasy.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from fpl_andres.backtesting.captain_policies import (
    CaptainCandidate,
    CaptainPolicy,
    build_captain_policies,
)

__all__ = [
    "CaptainPick",
    "CaptaincyScore",
    "score_policies",
]


@dataclass(frozen=True)
class CaptainPick:
    """One method's armband in one gameweek, kept so it can be inspected.

    A season mean says a method is worth 6.97 a week and gives a reader no way
    to disagree with it. The disagreement is the point: two methods differing
    by a tenth of a point over four seasons still differ on which player, in
    which week, and that is a claim somebody can check against a scoresheet.
    """

    gameweek: int
    element_id: int
    points: int
    #: The best return available on the same fielded eleven, for the regret.
    best_points: int


@dataclass
class CaptaincyScore:
    """One captaincy method's record across a season."""

    label: str
    gameweeks: int = 0
    captain_points: int = 0
    best_points: int = 0
    #: Times the pick was the highest scorer available in the eleven.
    perfect_weeks: int = 0
    #: Times the pick returned nothing at all. The cost a reader feels.
    blank_weeks: int = 0
    weekly: list[int] = field(default_factory=list)
    picks: list[CaptainPick] = field(default_factory=list)

    @property
    def mean_points(self) -> float | None:
        return self.captain_points / self.gameweeks if self.gameweeks else None

    @property
    def mean_best_points(self) -> float | None:
        return self.best_points / self.gameweeks if self.gameweeks else None

    @property
    def regret(self) -> float | None:
        """Points per gameweek left on the table against the owned-XI ceiling."""
        if not self.gameweeks:
            return None
        return (self.best_points - self.captain_points) / self.gameweeks

    @property
    def share_of_ceiling(self) -> float | None:
        return self.captain_points / self.best_points if self.best_points else None

    @property
    def blank_rate(self) -> float | None:
        return self.blank_weeks / self.gameweeks if self.gameweeks else None


def score_policies(
    candidates: Sequence[CaptainCandidate],
    actual: Mapping[int, int],
    scores: Mapping[str, CaptaincyScore],
    *,
    gameweek: int,
    policies: Mapping[str, CaptainPolicy] | None = None,
) -> None:
    """Score every thesis on exactly the candidates the caller supplied.

    ``policies`` must be one set held across a whole season: `set_and_forget`
    remembers who it committed to, and rebuilding it each gameweek would let it
    change its mind, which is the one thing it is defined not to do.
    """
    active = build_captain_policies() if policies is None else policies
    available = [entry for entry in candidates if entry.element_id in actual]
    if not available:
        return

    best = max(actual[entry.element_id] for entry in available)
    for label, policy in active.items():
        score = scores.get(label)
        if score is None:
            continue
        pick = policy(available)
        if pick is None or pick not in actual:
            continue
        _record(score, gameweek, pick, actual[pick], best)


def _record(
    score: CaptaincyScore,
    gameweek: int,
    element_id: int,
    returned: int,
    best: int,
) -> None:
    score.gameweeks += 1
    score.captain_points += returned
    score.best_points += best
    score.weekly.append(returned)
    score.picks.append(
        CaptainPick(gameweek=gameweek, element_id=element_id, points=returned, best_points=best)
    )
    if returned == best:
        score.perfect_weeks += 1
    if returned <= 2:
        # Two points is an appearance and nothing else. Doubling it is the week
        # a captaincy call is remembered for.
        score.blank_weeks += 1
