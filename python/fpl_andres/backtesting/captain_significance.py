"""Is a captaincy thesis actually better, or did it get four lucky seasons?

Ten policies over roughly 127 scored gameweeks is ten chances to top a table by
accident. The first run made that concrete: `template` finished bottom, and
after one arithmetic fix it finished top. A ranking that can invert on a
rescaling is a ranking that needs an interval, not a sort.

So each thesis is tested against the incumbent -- take the highest projected
scorer -- with the paired bootstrap already used for model promotion. Paired
because every policy captains in the same weeks: a week where the whole
shortlist blanked is a bad week for all of them, and comparing unpaired means
would charge that to whichever policy happened to be sampled into it.

The gate is the one the rest of the project uses: the strict lower bound of the
paired-improvement interval must clear zero, and every seed replicate must
agree. A thesis that promotes under one seed and not the next is not a finding.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from fpl_andres.models.promotion import TripletPrediction, evaluate_promotion

__all__ = [
    "BASELINE_POLICY",
    "CONFIDENCE",
    "MINIMUM_WEEKS",
    "RESAMPLES",
    "PolicyVerdict",
    "compare_policies",
]

#: The incumbent every thesis is measured against: take the highest projection.
BASELINE_POLICY = "expected_points"
#: Enough to place a percentile bound without pretending to more precision.
RESAMPLES = 2000
CONFIDENCE = 0.95
#: A season is 32 scored weeks. Below one season there is nothing to conclude.
MINIMUM_WEEKS = 32
#: Independent seeds that must all agree before a result is called.
SEED_REPLICATES = 3
_SEED = 1


@dataclass(frozen=True)
class PolicyVerdict:
    """One thesis measured against the incumbent."""

    label: str
    weeks: int
    mean: float
    baseline_mean: float
    improvement: float
    lower: float
    upper: float
    #: True only when the whole interval clears zero, under every seed.
    better: bool
    reason_codes: tuple[str, ...]


def _mean(values: Sequence[float], _observed: Sequence[float]) -> float:
    """Mean captain return. The observed series is unused and required by the
    promotion metric signature, which exists for error metrics."""
    return sum(values) / len(values) if values else 0.0


def _offset(weekly: Mapping[str, Sequence[int]]) -> float:
    """How far the worst week has to be lifted to clear zero.

    A captain can lose points: a red card is -3, an own goal -2, and goals
    conceded take more off a defender. `TripletPrediction` refuses a negative
    row because the metrics it was built for are error magnitudes, which cannot
    be. Captain return is not one of those.

    Adding one constant to every series is exact rather than a workaround. The
    verdict is built from the paired difference of two means, and a shift
    common to both cancels out of it entirely -- point estimate, bootstrap
    samples and interval alike. Only the two reported means move, by exactly
    the offset, and they are moved back.
    """
    lowest = min((value for series in weekly.values() for value in series), default=0)
    return float(-lowest) if lowest < 0 else 0.0


def compare_policies(
    weekly: Mapping[str, Sequence[int]],
    *,
    baseline: str = BASELINE_POLICY,
    resamples: int = RESAMPLES,
    minimum_weeks: int = MINIMUM_WEEKS,
) -> list[PolicyVerdict]:
    """Rank every thesis against the incumbent, with an interval on each gap.

    ``weekly`` maps a policy to its captain return in each scored gameweek, in
    the same order for every policy. A policy scored on a different number of
    weeks cannot be paired and is refused rather than truncated: silently
    trimming would compare two different populations and call it a comparison.
    """
    reference = weekly.get(baseline)
    if reference is None:
        raise KeyError(f"{baseline} is not among the scored policies")

    verdicts: list[PolicyVerdict] = []
    offset = _offset(weekly)
    for label, series in weekly.items():
        if label == baseline:
            continue
        if len(series) != len(reference):
            raise ValueError(
                f"{label} was scored on {len(series)} weeks and {baseline} on "
                f"{len(reference)}; they cannot be paired"
            )
        triplets = [
            # `observed` is unused by a mean, and is the realised return so the
            # record stays interpretable if the metric is ever changed.
            TripletPrediction(
                baseline=float(base) + offset,
                candidate=float(value) + offset,
                observed=float(value) + offset,
            )
            for base, value in zip(reference, series, strict=True)
        ]
        decision = evaluate_promotion(
            triplets,
            metric_name="captain_points",
            metric=_mean,
            metric_direction="higher_is_better",
            resamples=resamples,
            seed=_SEED,
            confidence=CONFIDENCE,
            minimum_sample_size=minimum_weeks,
            seed_replicates=SEED_REPLICATES,
        )
        verdicts.append(
            PolicyVerdict(
                label=label,
                weeks=len(series),
                mean=decision.candidate.point_estimate - offset,
                baseline_mean=decision.baseline.point_estimate - offset,
                improvement=decision.paired_improvement.point_estimate,
                lower=decision.paired_improvement.lower,
                upper=decision.paired_improvement.upper,
                better=decision.promoted,
                reason_codes=decision.reason_codes,
            )
        )

    verdicts.sort(key=lambda entry: -entry.improvement)
    return verdicts
