"""Competing theses about who to captain, so the backtest can settle it.

The captain doubles, so this one call carries two to three times the expected
value of a routine transfer. Until now this project made it one way -- take the
highest projected scorer -- and had no evidence that was the right way. The
practitioner literature is unanimous that it is not, and unanimous about very
little else, so the honest response is to write the competing claims down as
policies and score them all on the same weeks.

## What the sources actually claim

FPL Oracle builds a shortlist on expected points, then separates candidates on
*effective ownership* and on whether the manager is protecting a rank or
chasing one; it also derates by rotation risk, `xPts x P(start)`. FPL360 leads
on form with a hard floor, and frames the whole thing as loss aversion: the
template pick is chosen out of fear rather than belief. Ramezani and Dinh treat
captaincy as a decision variable inside the optimiser rather than a heuristic
bolted on afterwards, and report that penalising a score by its own uncertainty
trims upside without buying protection -- for averaging methods, though it
helped for ICT.

Those disagree. One says take the mean, one says take the form, one says take
the crowd's pick, one says take the differential, one says shrink for variance.
They cannot all be right, and each is stated without a measurement.

## Why these seven and not seventy

Every policy here is a different *family*: a different quantity is being
maximised. Tuning a coefficient inside one of them and calling the result a new
thesis would be fitting the seasons, and with four seasons and about 127 scored
gameweeks there is not enough evidence to separate near-neighbours. Where a
coefficient is unavoidable it is set from the source that proposed it, once,
and never swept.

The crowd policy is deliberately included rather than treated as a foil. It is
what most managers do, it is what the template says, and Bhatt found crowd
captaincy beat expert analysts. If the premium every rival owns is the right
answer, the measurement should say so -- nothing here excludes a Haaland, and a
policy that could never pick him would be answering a different question.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "CAPTAIN_POLICIES",
    "STATEFUL_POLICIES",
    "CaptainCandidate",
    "CaptainPolicy",
    "SetAndForget",
    "build_captain_policies",
    "policy_names",
]

#: Anything that can name a captain from a shortlist. Stateless functions and
#: stateful objects both qualify; the scorer does not care which it holds.
CaptainPolicy = Callable[[Sequence["CaptainCandidate"]], int | None]


@dataclass(frozen=True)
class CaptainCandidate:
    """One captaincy option, with everything any policy is allowed to read.

    Every field is knowable before the deadline. Realised points for the
    gameweek being decided are deliberately absent: a policy that could see
    them would score perfectly and mean nothing.
    """

    element_id: int
    #: The shipped projection: components blended with recent scoring.
    expected_points: float
    #: The same projection with the recent-form blend removed.
    component_points: float
    #: Mean points over the last five gameweeks. `None` where he has no rows.
    recent_points: float | None
    #: Standard deviation of those same gameweeks. Zero where he has one row.
    recent_deviation: float
    #: Chance he starts, from the minutes model.
    probability_start: float
    #: Share of managers holding him, rescaled to 0-100 against the most owned.
    ownership: float
    #: His ninetieth-percentile afternoon, not his ordinary one.
    ceiling_points: float = 0.0
    #: Attacking multiplier for this gameweek's fixtures. Venue is inside it.
    fixture_ease: float = 1.0


#: Oracle's rule of thumb: a differential is worth taking when the projections
#: are within about 1.5 points, and not when the favourite is clearly ahead.
#: Used as the price of a point of effective ownership, once, unswept.
EFFECTIVE_OWNERSHIP_PRICE = 1.5 / 100.0

#: Ramezani and Dinh penalise a score by its own uncertainty at one deviation.
UNCERTAINTY_WEIGHT = 1.0

#: FPL360 refuses any captain under this recent average. Stated as form, which
#: on their scale is points per game over the last four.
FORM_FLOOR = 2.0


def _highest(
    candidates: Sequence[CaptainCandidate],
    score: Callable[[CaptainCandidate], float],
) -> int | None:
    """The best candidate by `score`, ties broken on element id.

    Deterministic on purpose: a tie resolved by dictionary order would make the
    whole backtest depend on the hash seed.
    """
    if not candidates:
        return None
    best = max(candidates, key=lambda entry: (score(entry), -entry.element_id))
    return best.element_id


def _expected_points(candidates: Sequence[CaptainCandidate]) -> int | None:
    """Take the highest projected scorer. What this project already did."""
    return _highest(candidates, lambda entry: entry.expected_points)


def _components(candidates: Sequence[CaptainCandidate]) -> int | None:
    """The same, with the recent-form blend removed from the projection."""
    return _highest(candidates, lambda entry: entry.component_points)


def _available(candidates: Sequence[CaptainCandidate]) -> int | None:
    """Oracle step five: derate the projection by the chance he starts.

    A model that assumes the player plays is the systemic weakness in every
    expected-points captaincy pick. Seven and a half points behind an
    eighty-five per cent chance of starting is worth less than six and a half
    behind a certainty, and only this policy prices that.
    """
    return _highest(candidates, lambda entry: entry.expected_points * entry.probability_start)


def _upside(candidates: Sequence[CaptainCandidate]) -> int | None:
    """Captain the ceiling, not the mean.

    Doubling an average return is worth much less than doubling a haul, and the
    decision is a right-tail bet rather than a point estimate. Nobody in the
    sources says this outright; it is the obvious consequence of the multiplier
    and it belongs in the comparison.
    """
    return _highest(
        candidates,
        lambda entry: entry.expected_points + entry.recent_deviation,
    )


def _robust(candidates: Sequence[CaptainCandidate]) -> int | None:
    """The opposite bet: shrink a projection by its own uncertainty.

    Ramezani and Dinh report this trims upside without buying protection for
    averaging methods. It is included precisely because it is expected to lose:
    a comparison of only the ideas somebody believes in cannot tell you whether
    the winner won on merit.
    """
    return _highest(
        candidates,
        lambda entry: entry.expected_points - UNCERTAINTY_WEIGHT * entry.recent_deviation,
    )


def _form(candidates: Sequence[CaptainCandidate]) -> int | None:
    """FPL360: rank by recent scoring, and never captain below the floor.

    Their claim is that form compounds fixture quality, so an in-form player
    against a hard fixture beats an out-of-form player against an easy one. If
    everybody is under the floor the rule has nothing to say, so it falls back
    to the projection rather than refusing to captain.
    """
    eligible = [
        entry
        for entry in candidates
        if entry.recent_points is not None and entry.recent_points >= FORM_FLOOR
    ]
    if not eligible:
        return _expected_points(candidates)
    return _highest(eligible, lambda entry: entry.recent_points or 0.0)


def _crowd(candidates: Sequence[CaptainCandidate]) -> int | None:
    """Captain whoever the field owns. The template, and the loss-averse pick."""
    return _highest(candidates, lambda entry: entry.ownership)


def _differential(candidates: Sequence[CaptainCandidate]) -> int | None:
    """Chasing: pay a point and a half of projection for a hundred of ownership.

    The rank-climbing half of Oracle step three. A haul from a player the field
    already owns moves nobody, so the projection is charged for the ownership
    that comes with it. The price is Oracle's own indifference band and is not
    tuned here.
    """
    return _highest(
        candidates,
        lambda entry: entry.expected_points - EFFECTIVE_OWNERSHIP_PRICE * entry.ownership,
    )


def _template(candidates: Sequence[CaptainCandidate]) -> int | None:
    """Protecting: the same trade with the sign flipped.

    Both halves of the rank rule are scored because the backtest has no rank to
    condition on, and a policy that is right only for managers in one position
    should not be reported as right in general.
    """
    return _highest(
        candidates,
        lambda entry: entry.expected_points + EFFECTIVE_OWNERSHIP_PRICE * entry.ownership,
    )


def _ceiling_and_fixture(candidates: Sequence[CaptainCandidate]) -> int | None:
    """The owner's own rule: the biggest ceiling against the kindest fixture.

    Stated as "xCeil against the easiest fixture, at home, or away if the
    fixture is easy enough" -- which is a product, not a filter: a huge ceiling
    tolerates a harder fixture and an ordinary one needs a kind draw.

    No separate home term is applied. Venue is already inside the attacking
    multiplier, which is measured per club and per side, so a home bonus on top
    would price the same fact twice and quietly outrank the ceiling it is
    supposed to modify.
    """
    return _highest(candidates, lambda entry: entry.ceiling_points * entry.fixture_ease)


class SetAndForget:
    """Captain one player all season. Choose him once, never think again.

    The "just captain Haaland" baseline, written without his name in it. Naming
    him would be hindsight: you only know he was the right anchor because the
    seasons already happened. So the anchor is whoever the field owns most at
    the first scored gameweek, which is information a manager had at the time
    and is, in practice, how that decision is actually made.

    This is the baseline that matters. It requires no projection, no form, no
    fixture, and no decision after the opening week. A model that cannot beat
    it is not earning its complexity.

    When the anchor has no realised row -- injured, benched, or his club blanked
    -- the armband passes to the next most owned. That is not a fudge to keep
    the series length equal: it is the vice-captain, which is a real rule of the
    game and exactly what happens to a real set-and-forget manager.

    Stateful, so one instance belongs to one season. `build_captain_policies`
    returns a fresh set for exactly that reason.
    """

    def __init__(self) -> None:
        self._anchor: int | None = None

    @property
    def anchor(self) -> int | None:
        """Who this season was committed to, or None before the first week."""
        return self._anchor

    def __call__(self, candidates: Sequence[CaptainCandidate]) -> int | None:
        if not candidates:
            return None
        if self._anchor is None:
            self._anchor = _crowd(candidates)
        if any(entry.element_id == self._anchor for entry in candidates):
            return self._anchor
        return _crowd(candidates)


#: Keyed by the label that reaches the artifact and the calibration page.
#: Stateless policies only -- see `build_captain_policies` for the full set.
CAPTAIN_POLICIES: Mapping[str, Callable[[Sequence[CaptainCandidate]], int | None]] = {
    "expected_points": _expected_points,
    "components": _components,
    "availability_adjusted": _available,
    "upside": _upside,
    "robust": _robust,
    "form": _form,
    "crowd": _crowd,
    "differential": _differential,
    "template": _template,
    "ceiling_and_fixture": _ceiling_and_fixture,
}


def policy_names() -> tuple[str, ...]:
    """Every policy, in a fixed order, so two runs produce the same columns."""
    return (*CAPTAIN_POLICIES, *STATEFUL_POLICIES)


#: Policies that carry season state and therefore cannot be module-level.
STATEFUL_POLICIES: tuple[str, ...] = ("set_and_forget",)


def build_captain_policies() -> dict[str, CaptainPolicy]:
    """A fresh policy set for one season.

    Fresh because `SetAndForget` remembers its anchor. A module-level instance
    would carry 2022-23's anchor into 2023-24 and score a player who had left
    the league, which would look like a modelling result rather than a leak.
    """
    return {**CAPTAIN_POLICIES, "set_and_forget": SetAndForget()}
