"""Score the captain choice, which is the decision with the most leverage.

A transfer moves one squad slot by the difference between two players. The
captain doubles whoever is already in the eleven, so the same gameweek's
captain decision swings two to three times what a routine transfer does. The
model was never measured on it: `score_season` graded the whole pool's ranking
and said nothing about the one pick that gets multiplied.

## The population is the honest part

A manager captains from the fifteen he owns, and a backtest has no squad. Given
the whole pool, every method would be graded on a decision nobody faces --
"captain the best player in the league" is not a choice, it is hindsight with
extra steps.

So every method picks from the same realistic shortlist: the players the crowd
actually owned going into the gameweek, taken from ownership at the previous
gameweek. That is public before the deadline, it is the same set for every
method, and it is roughly the pool a template squad draws from.

## What is reported

The realised points of the chosen player, not the doubled figure. Doubling is a
constant on every method and on the ceiling, so it changes no ordering; leaving
it out keeps the number something that can be checked against a scoresheet.
Over a season the gap between two methods is worth twice what it reads.

The ceiling is the best captain available *in the same shortlist*, so the regret
is a decision a manager could have made, not a fantasy.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from fpl_andres.backtesting.captain_policies import CAPTAIN_POLICIES, CaptainCandidate

__all__ = [
    "SHORTLIST_SIZE",
    "CaptaincyScore",
    "score_captaincy",
    "score_policies",
]

# How many of the most-owned players a captain is picked from. Twenty-five is
# roughly the set a template squad plus the week's obvious punts spans; smaller
# and the model is denied any differential, larger and the shortlist stops
# resembling anyone's fifteen.
SHORTLIST_SIZE = 25


@dataclass
class CaptaincyScore:
    """One captaincy method's record across a season."""

    label: str
    gameweeks: int = 0
    captain_points: int = 0
    best_points: int = 0
    #: Times the pick was the highest scorer available in the shortlist.
    perfect_weeks: int = 0
    #: Times the pick returned nothing at all. The cost a reader feels.
    blank_weeks: int = 0
    weekly: list[int] = field(default_factory=list)

    @property
    def mean_points(self) -> float | None:
        return self.captain_points / self.gameweeks if self.gameweeks else None

    @property
    def mean_best_points(self) -> float | None:
        return self.best_points / self.gameweeks if self.gameweeks else None

    @property
    def regret(self) -> float | None:
        """Points per gameweek left on the table against the shortlist ceiling."""
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
    shortlist_size: int = SHORTLIST_SIZE,
) -> None:
    """Score every competing captaincy thesis on the same gameweek.

    The shortlist is the most-owned players who have a realised score, exactly
    as for the ranking methods, so a policy that likes differentials is still
    choosing from a squad somebody could plausibly have owned. Left to the whole
    pool it would captain the week's cheapest hat-trick and report skill.
    """
    ranked = sorted(candidates, key=lambda entry: (-entry.ownership, entry.element_id))
    shortlist = [entry for entry in ranked if entry.element_id in actual][:shortlist_size]
    if not shortlist:
        return

    best = max(actual[entry.element_id] for entry in shortlist)
    for label, policy in CAPTAIN_POLICIES.items():
        score = scores.get(label)
        if score is None:
            continue
        pick = policy(shortlist)
        if pick is None or pick not in actual:
            continue
        _record(score, actual[pick], best)


def score_captaincy(
    methods: Mapping[str, Mapping[int, float]],
    ownership: Mapping[int, float],
    actual: Mapping[int, int],
    scores: Mapping[str, CaptaincyScore],
    *,
    shortlist_size: int = SHORTLIST_SIZE,
) -> None:
    """Add one gameweek's captaincy result to each method's running score.

    ``methods`` maps a label to that method's ranking over element ids.
    ``ownership`` is the crowd's holding going into the gameweek and defines the
    shortlist. ``actual`` is what everybody went on to score.

    Mutates ``scores`` rather than returning, because a season is accumulated
    one gameweek at a time and rebuilding the record each week would make the
    caller responsible for merging it.
    """
    shortlist = _shortlist(ownership, actual, shortlist_size)
    if not shortlist:
        return

    best = max(actual[element] for element in shortlist)
    for label, ranking in methods.items():
        score = scores.get(label)
        if score is None:
            continue
        pick = _pick(shortlist, ranking)
        if pick is None:
            continue
        _record(score, actual[pick], best)


def _record(score: CaptaincyScore, returned: int, best: int) -> None:
    score.gameweeks += 1
    score.captain_points += returned
    score.best_points += best
    score.weekly.append(returned)
    if returned == best:
        score.perfect_weeks += 1
    if returned <= 2:
        # Two points is an appearance and nothing else. Doubling it is the week
        # a captaincy call is remembered for.
        score.blank_weeks += 1


def _shortlist(
    ownership: Mapping[int, float],
    actual: Mapping[int, int],
    size: int,
) -> list[int]:
    """The most-owned players who also have a realised score this gameweek.

    A player with no row did not feature in a scored fixture, so captaining him
    is not a decision the corpus can grade either way.
    """
    owned = [element for element in ownership if element in actual]
    owned.sort(key=lambda element: (-ownership[element], element))
    return owned[:size]


def _pick(shortlist: Sequence[int], ranking: Mapping[int, float]) -> int | None:
    """The method's highest-ranked player in the shortlist, ties by element id."""
    rated = [element for element in shortlist if element in ranking]
    if not rated:
        return None
    return max(rated, key=lambda element: (ranking[element], -element))
