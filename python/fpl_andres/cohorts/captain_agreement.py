"""Which captaincy thesis best *describes* what the elite cohort did.

This is a different question from the one `backtesting/captain_significance.py`
answers, and the two must not be run together into a single verdict.

- The backtest asks: which rule **scores** best over four seasons of history.
- This asks: which rule **predicts** what the top managers actually captained.

## Why the second question is worth asking at all

The backtest can only compare rules that were written down first. If the cohort
is doing something none of the ten theses encode, the backtest will never
surface it, because it was never a candidate. Agreement is a way of noticing
that: a week where every thesis picks A and eighty percent of the cohort
captained B is evidence that the shortlist of ideas is short, and the residual
names the player to go and look at.

## Why agreement is not a score, and this module refuses to pretend it is

The cohort is selected on final rank. Selecting on the outcome and then
measuring the outcome is the trap `data/cohort/fpl500.json` already records: a
population filtered for having done well will look good at anything you measure
it on afterwards. So a high agreement rate says a thesis *resembles* elite
behaviour. It does not say the thesis scores well, and it does not say the
cohort's captaincy is what made them elite — they may be elite despite it.

Agreement therefore reports alongside the backtest, never instead of it. A
thesis that agrees often and scores badly is a description of a habit, not a
recommendation.

## The armband is the wrong place to look for edge, and that is the finding

Captaincy in a top-500 cohort is close to unanimous most weeks. When ninety
percent of the cohort captains the same player, agreement discriminates nothing
between theses and the `unanimity` field says so, so those weeks can be dropped
rather than being allowed to inflate everything equally. What is left — the
genuinely split weeks — is the only part of the series that carries information,
and it is small. `split_weeks` is reported so a reader can see how small.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "MINIMUM_CONTESTED_WEEKS",
    "SPLIT_THRESHOLD",
    "CohortAgreementSignal",
    "CohortWeek",
    "PolicyAgreement",
    "score_agreement",
    "weight_agreement_signal",
]

# Above this share the cohort is effectively unanimous and the week separates
# no two theses. Set at the point where a thesis picking the modal captain is
# more likely than not to be right by construction rather than by insight.
SPLIT_THRESHOLD = 0.5


@dataclass(frozen=True)
class CohortWeek:
    """One gameweek of the cohort's armbands, as captured before the deadline."""

    event: int
    counted: int
    """Managers whose picks were reconciled. The denominator of every share."""
    share_by_element: Mapping[int, float]

    @property
    def modal_captain(self) -> int | None:
        """The player the most managers captained, or None when it is a tie.

        A tie is returned as None rather than broken by element id: an arbitrary
        winner would be scored as if the cohort had agreed on it.
        """
        if not self.share_by_element:
            return None
        best = max(self.share_by_element.values())
        leaders = [element for element, share in self.share_by_element.items() if share == best]
        return leaders[0] if len(leaders) == 1 else None

    @property
    def unanimity(self) -> float:
        """The modal captain's share. High means the week decides nothing."""
        if not self.share_by_element:
            return 0.0
        return max(self.share_by_element.values())

    @property
    def is_split(self) -> bool:
        return self.unanimity <= SPLIT_THRESHOLD


@dataclass(frozen=True)
class PolicyAgreement:
    label: str
    weeks: int
    """Weeks where both the cohort and the policy named a captain."""
    modal_hits: int
    modal_rate: float
    """How often the policy named the same player as the cohort's plurality."""
    mean_share: float
    """The share of the cohort that agreed, averaged. Rewards a near miss."""
    split_weeks: int
    """Of `weeks`, how many were genuinely contested. The rest decide nothing."""
    split_modal_rate: float | None
    """`modal_rate` over the contested weeks only. None when there are none."""


def score_agreement(
    picks: Mapping[str, Mapping[int, int]],
    cohort: Sequence[CohortWeek],
) -> list[PolicyAgreement]:
    """Score each thesis against what the cohort actually captained.

    `picks` maps a policy label to the element it captained in each event. An
    event a policy has no pick for is skipped rather than counted as a miss:
    the shortlist can be empty in a blank gameweek, and scoring that as a wrong
    answer would punish a thesis for a fixture list.

    Ordered by agreement over the contested weeks, falling back to the overall
    rate, because the contested weeks are the only ones that separate anything.
    """
    weeks_by_event = {week.event: week for week in cohort}
    results: list[PolicyAgreement] = []

    for label in sorted(picks):
        scored = 0
        hits = 0
        shares: list[float] = []
        split_scored = 0
        split_hits = 0
        for event, element in picks[label].items():
            week = weeks_by_event.get(event)
            if week is None or not week.share_by_element:
                continue
            scored += 1
            shares.append(week.share_by_element.get(element, 0.0))
            hit = week.modal_captain is not None and element == week.modal_captain
            hits += int(hit)
            if week.is_split:
                split_scored += 1
                split_hits += int(hit)
        if scored == 0:
            continue
        results.append(
            PolicyAgreement(
                label=label,
                weeks=scored,
                modal_hits=hits,
                modal_rate=hits / scored,
                mean_share=sum(shares) / len(shares),
                split_weeks=split_scored,
                split_modal_rate=(split_hits / split_scored) if split_scored else None,
            )
        )

    return sorted(
        results,
        key=lambda entry: (
            -(entry.split_modal_rate if entry.split_modal_rate is not None else -1.0),
            -entry.modal_rate,
            entry.label,
        ),
    )


# ---------------------------------------------------------------------------
# Agreement signal — a secondary input to thesis selection, not a score
# ---------------------------------------------------------------------------

#: How many contested weeks are needed before the signal carries enough evidence
#: to influence thesis tiebreaking. Below this the signal weight is fractional.
MINIMUM_CONTESTED_WEEKS = 10


@dataclass(frozen=True)
class CohortAgreementSignal:
    """One thesis's cohort agreement, weighted by how much evidence exists.

    The weight is proportional to the number of contested weeks observed,
    capped at 1.0 once `MINIMUM_CONTESTED_WEEKS` is reached. A fresh season
    with two contested weeks carries 0.2 of full weight: the signal is present
    but modest, and it grows as the series does.

    This is a secondary signal. It belongs alongside the backtest result, never
    in place of it. A thesis that agrees with the cohort on split weeks is
    describing a habit that has no demonstrated scoring value; the backtest
    result is the thing that has demonstrated value, and it takes precedence.
    """

    label: str
    split_weeks: int
    """Number of contested weeks the signal is based on."""
    weight: float
    """Confidence in the signal: `split_weeks / MINIMUM_CONTESTED_WEEKS`, capped at 1.0."""
    split_modal_rate: float | None
    """How often this thesis named the cohort's plurality captain on contested weeks."""
    mean_share: float
    """Mean share of the cohort that captained this thesis's pick."""

    @property
    def is_mature(self) -> bool:
        """True once the series has enough contested weeks to be informative."""
        return self.split_weeks >= MINIMUM_CONTESTED_WEEKS

    @property
    def weighted_rate(self) -> float | None:
        """The signal value: `split_modal_rate * weight`, or None when unavailable."""
        if self.split_modal_rate is None:
            return None
        return self.split_modal_rate * self.weight


def weight_agreement_signal(
    agreements: Sequence[PolicyAgreement],
) -> tuple[CohortAgreementSignal, ...]:
    """Convert scored policy agreements into weighted signals.

    The signal is ordered by weighted_rate, descending. A thesis with no split
    weeks at all is included with `split_modal_rate=None` and `weighted_rate=None`
    so it is visible in a report but sorts last.

    The weight grows with `split_weeks` up to `MINIMUM_CONTESTED_WEEKS`, then
    stays at 1.0. Weeks beyond the minimum do not shrink the weight back down:
    once a signal is mature it remains mature.
    """

    def _weight(split_weeks: int) -> float:
        return min(1.0, split_weeks / MINIMUM_CONTESTED_WEEKS)

    signals = tuple(
        CohortAgreementSignal(
            label=entry.label,
            split_weeks=entry.split_weeks,
            weight=_weight(entry.split_weeks),
            split_modal_rate=entry.split_modal_rate,
            mean_share=entry.mean_share,
        )
        for entry in agreements
    )

    return tuple(
        sorted(
            signals,
            key=lambda s: (
                -(s.weighted_rate if s.weighted_rate is not None else -1.0),
                s.label,
            ),
        )
    )
