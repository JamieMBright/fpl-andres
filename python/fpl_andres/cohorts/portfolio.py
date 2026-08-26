"""Reconcile a cohort's picks into one portfolio — the ETF.

The catalogue knows *who* the good managers are. It does not know what they own:
the sweep stores season ranks, not squads. This is the part that turns 2,207
entry ids into a single holding, once a gameweek.

## What has to be reconciled, and why each one is a trap

**Partial capture.** Two thousand requests will not all succeed. If ownership is
divided by "however many answered", the denominator moves every week and a
player looks to be drifting when the sample drifted instead. Coverage is
therefore measured, reported, and floored: below the floor the snapshot is
refused rather than published with a quiet asterisk.

**Chips.** A Free Hit squad is a one-week rental and says nothing about what the
manager holds, so it is excluded from holdings and counted separately. Triple
Captain multiplies the armband by three rather than two. Bench Boost makes all
fifteen count, so "started" cannot be inferred from position alone.

**Captaincy is not ownership.** Sixty percent owned and forty percent captained
is a different exposure from sixty and two. Effective ownership adds the armband
on top of the holding, which is what makes it the number that decides a
transfer.

**Deadline intent, not outcome.** Picks are read after the deadline but before
the results settle, and are never reconciled against what happened. Auto-subs
and non-starters change what scored; they do not change what the cohort chose,
and what it chose is the signal.

**Cohort drift.** Membership changes whenever the catalogue is re-swept. A
series whose population silently changes is not a series, so every snapshot pins
the cohort revision it was taken over. Exact ranked-500 captures carry a hashed,
event-specific membership and publish separately from the full catalogue.

**Equal weight.** Each manager counts once. Weighting by rank would encode a
claim that this season's league table predicts next week, which is exactly the
claim `cohort.json` already records as unmeasurable on a cohort selected for
past success.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

__all__ = [
    "MINIMUM_COVERAGE",
    "CoverageTooLow",
    "Holding",
    "ManagerPicks",
    "Pick",
    "Portfolio",
    "PortfolioBasis",
    "reconcile",
]

# Below this share of the cohort the snapshot is refused. Set where a missing
# tail can still move a mid-ownership player by less than a percentage point.
MINIMUM_COVERAGE = 0.9

# Chips that change what a squad means, rather than what it scores.
FREE_HIT = "freehit"
TRIPLE_CAPTAIN = "3xc"
BENCH_BOOST = "bboost"
PortfolioBasis = Literal["catalogue-at-deadline", "ranked-500"]


class CoverageTooLow(RuntimeError):
    """Raised when too little of the cohort answered to publish a portfolio."""


@dataclass(frozen=True)
class Pick:
    element_id: int
    """1-15. Twelve and above is the bench unless Bench Boost is active."""
    position: int
    multiplier: int
    is_captain: bool
    is_vice_captain: bool

    @property
    def started(self) -> bool:
        # The published multiplier is zero for an unused bench player, which is
        # the only thing that distinguishes a bench slot under Bench Boost.
        return self.multiplier > 0


@dataclass(frozen=True)
class ManagerPicks:
    entry_id: int
    event: int
    picks: tuple[Pick, ...]
    active_chip: str | None = None

    @property
    def captain(self) -> int | None:
        for pick in self.picks:
            if pick.is_captain:
                return pick.element_id
        return None

    @property
    def vice_captain(self) -> int | None:
        for pick in self.picks:
            if pick.is_vice_captain:
                return pick.element_id
        return None


@dataclass(frozen=True)
class Holding:
    element_id: int
    owned: int
    started: int
    captained: int
    vice_captained: int
    owned_share: float
    started_share: float
    captained_share: float
    effective_ownership: float
    """Started share plus the armband on top, counting a triple captain twice."""


@dataclass(frozen=True)
class Portfolio:
    event: int
    cohort_revision: str
    attempted: int
    responded: int
    counted: int
    """Responded minus the Free Hit squads, which are excluded from holdings."""
    free_hit: int
    holdings: tuple[Holding, ...]
    basis: PortfolioBasis = "catalogue-at-deadline"

    @property
    def coverage(self) -> float:
        return self.responded / self.attempted if self.attempted else 0.0


def reconcile(
    captured: Sequence[ManagerPicks],
    *,
    event: int,
    attempted: int,
    cohort_revision: str,
    minimum_coverage: float = MINIMUM_COVERAGE,
    basis: PortfolioBasis = "catalogue-at-deadline",
) -> Portfolio:
    """Fold a gameweek of captured picks into one portfolio.

    `attempted` is the size of the cohort asked, not the number that answered.
    Passing the latter is how a shrinking sample turns into a moving ownership
    number that looks like managers changing their minds.
    """
    if attempted <= 0:
        raise ValueError("a portfolio needs a cohort to be taken over")
    if basis not in ("catalogue-at-deadline", "ranked-500"):
        raise ValueError(f"unsupported portfolio basis: {basis}")

    wrong_event = [row.entry_id for row in captured if row.event != event]
    if wrong_event:
        raise ValueError(f"picks from another gameweek for entries {wrong_event}")

    duplicates = len(captured) - len({row.entry_id for row in captured})
    if duplicates:
        raise ValueError(f"{duplicates} entries captured more than once")

    responded = len(captured)
    if responded > attempted:
        raise ValueError("more managers answered than were asked")

    coverage = responded / attempted
    if coverage < minimum_coverage:
        raise CoverageTooLow(
            f"only {responded} of {attempted} managers answered "
            f"({coverage:.1%}); below the {minimum_coverage:.0%} floor, so this "
            f"gameweek has no portfolio rather than a misleading one"
        )

    counting = [row for row in captured if row.active_chip != FREE_HIT]
    free_hit = responded - len(counting)
    if not counting:
        raise CoverageTooLow("every captured squad was a Free Hit; nothing to hold")

    owned: dict[int, int] = {}
    started: dict[int, int] = {}
    captained: dict[int, int] = {}
    vice: dict[int, int] = {}
    armband: dict[int, float] = {}

    for row in counting:
        triple = row.active_chip == TRIPLE_CAPTAIN
        for element_id in {pick.element_id for pick in row.picks}:
            owned[element_id] = owned.get(element_id, 0) + 1
        for pick in row.picks:
            if pick.started:
                started[pick.element_id] = started.get(pick.element_id, 0) + 1
            if pick.is_captain:
                captained[pick.element_id] = captained.get(pick.element_id, 0) + 1
                # A captain contributes one extra share, a triple captain two.
                armband[pick.element_id] = armband.get(pick.element_id, 0.0) + (
                    2.0 if triple else 1.0
                )
            if pick.is_vice_captain:
                vice[pick.element_id] = vice.get(pick.element_id, 0) + 1

    total = len(counting)
    holdings = tuple(
        sorted(
            (
                Holding(
                    element_id=element_id,
                    owned=count,
                    started=started.get(element_id, 0),
                    captained=captained.get(element_id, 0),
                    vice_captained=vice.get(element_id, 0),
                    owned_share=count / total,
                    started_share=started.get(element_id, 0) / total,
                    captained_share=captained.get(element_id, 0) / total,
                    effective_ownership=(started.get(element_id, 0) + armband.get(element_id, 0.0))
                    / total,
                )
                for element_id, count in owned.items()
            ),
            key=lambda holding: (-holding.effective_ownership, holding.element_id),
        )
    )

    return Portfolio(
        event=event,
        cohort_revision=cohort_revision,
        attempted=attempted,
        responded=responded,
        counted=total,
        free_hit=free_hit,
        holdings=holdings,
        basis=basis,
    )
