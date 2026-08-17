"""Route-level evidence derived from football markets and match context.

Direct prices, historical rates and modelled consequences do not carry the
same evidential weight. This module keeps those distinctions attached to the
number and contains only transformations whose inputs name their units.

Bonus is reconstructed in two stages. First, the official BPS coefficients are
applied to every component the caller can source. Inputs that are unavailable
stay missing; a historical residual may account for them at a higher layer.
Second, expected BPS distributions are compared within a fixture to estimate
the probability of finishing first, second or third.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from datetime import datetime
from statistics import NormalDist, fmean, pstdev
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fpl_andres.models.contracts import EvidenceLevel
from fpl_andres.timeguard import require_utc

MarketRoute = Literal[
    "appearance",
    "goals",
    "assists",
    "clean_sheet",
    "goals_conceded",
    "saves",
    "penalty_saves",
    "bonus",
    "yellow_cards",
    "red_cards",
    "own_goals",
    "penalties_missed",
    "defensive_contribution",
]
EvidenceMetric = Literal[
    "probability",
    "expected_events",
    "expected_minutes",
    "expected_bps",
    "expected_points",
]


class RouteEvidence(BaseModel):
    """One route signal with enough provenance to audit or refuse it."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    route: MarketRoute
    metric: EvidenceMetric
    value: float | None
    evidence_level: EvidenceLevel
    source: Annotated[str, Field(min_length=1)]
    observed_at: datetime
    source_hashes: tuple[Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")], ...]
    reason_codes: tuple[Annotated[str, Field(min_length=1)], ...]
    books: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def validate_evidence(self) -> RouteEvidence:
        require_utc(self.observed_at, "observed_at")
        if not self.source_hashes:
            raise ValueError("market evidence must cite at least one source hash")
        if not self.reason_codes:
            raise ValueError("market evidence must carry at least one reason code")
        if self.evidence_level == "unavailable":
            if self.value is not None:
                raise ValueError("unavailable evidence must not carry a value")
        elif self.value is None or not math.isfinite(self.value):
            raise ValueError("available evidence must carry a finite value")
        return self


@dataclass(frozen=True)
class ParticipationEstimate:
    """Minutes and start probability implied by one unconditional event price."""

    expected_minutes: float
    start_probability: float
    market_minutes: float


def infer_participation(
    *,
    recorded_minutes: float,
    recorded_start_probability: float,
    recorded_events: float,
    market_events: float,
    weight: float,
) -> ParticipationEstimate | None:
    """Infer participation without spending the same price twice on attack.

    The record supplies an unconditional event expectation at its recorded
    minutes. Holding the per-minute event rate fixed, the market expectation
    names the minutes it implies. The result is bounded to one regulation match
    and blended because a price also contains a view of ability and role.

    Callers must use the market event expectation directly for the attacking
    route. Multiplying it by these inferred minutes again would double-count the
    same evidence.
    """
    if not 0.0 <= weight <= 1.0:
        raise ValueError("weight must be between zero and one")
    if not 0.0 <= recorded_start_probability <= 1.0:
        raise ValueError("recorded_start_probability must be between zero and one")
    if recorded_minutes < 0.0 or market_events < 0.0:
        raise ValueError("minutes and event expectations cannot be negative")
    if recorded_events <= 0.0:
        return None

    market_minutes = min(90.0, recorded_minutes * market_events / recorded_events)
    expected_minutes = (1.0 - weight) * recorded_minutes + weight * market_minutes
    market_start = market_minutes / 90.0
    start_probability = (1.0 - weight) * recorded_start_probability + weight * market_start
    return ParticipationEstimate(
        expected_minutes=expected_minutes,
        start_probability=min(1.0, max(0.0, start_probability)),
        market_minutes=market_minutes,
    )


def pressure_adjusted_saves(recorded_points: float, pressure_multiplier: float) -> float:
    """Blend goalkeeper history with opponent xG-derived shot pressure.

    A direct shots-on-target or goalkeeper-saves market can replace this
    bounded approximation at the caller. In its absence, the team market says
    how much scoring pressure the opponent applies and the keeper's own record
    says how often that pressure became saves.
    """
    if recorded_points < 0.0 or pressure_multiplier < 0.0:
        raise ValueError("save points and pressure cannot be negative")
    return recorded_points * pressure_multiplier


def pressure_adjusted_defcon(
    recorded_points: float,
    pressure_multiplier: float,
    *,
    maximum_points: float = 2.0,
) -> float:
    """Move a historical DefCon hit probability with opponent pressure.

    Multiplying points directly can exceed the two-point route. Odds scaling is
    monotonic while preserving the probability bounds: pressure multiplies the
    odds of clearing the threshold, then the result is converted back.
    """
    if maximum_points <= 0.0:
        raise ValueError("maximum_points must be positive")
    if not 0.0 <= recorded_points <= maximum_points:
        raise ValueError("recorded DefCon points must fit inside the route")
    if pressure_multiplier < 0.0:
        raise ValueError("pressure cannot be negative")
    probability = recorded_points / maximum_points
    if probability in (0.0, 1.0):
        return recorded_points
    adjusted = (
        probability * pressure_multiplier / (1.0 - probability + probability * pressure_multiplier)
    )
    return adjusted * maximum_points


@dataclass(frozen=True)
class BpsInputs:
    """Expected match actions used by the official Bonus Points System.

    None means unavailable, not zero. `goals` means goals whose penalty status
    is unknown and therefore uses the player's positional goal coefficient;
    callers with the split should put penalty goals in `penalty_goals` and only
    non-penalty goals in `goals`.
    """

    probability_appear: float | None = None
    probability_sixty: float | None = None
    goals: float | None = None
    penalty_goals: float | None = None
    assists: float | None = None
    clean_sheets: float | None = None
    penalties_saved: float | None = None
    saves_inside_box: float | None = None
    saves_outside_box: float | None = None
    open_play_crosses: float | None = None
    big_chances_created: float | None = None
    clearances_blocks_interceptions: float | None = None
    recoveries: float | None = None
    key_passes: float | None = None
    tackles: float | None = None
    dribbles: float | None = None
    winning_goals: float | None = None
    goalline_clearances: float | None = None
    fouls_won: float | None = None
    shots_on_target: float | None = None
    pass_completion_bps: float | None = None
    goals_conceded: float | None = None
    penalties_conceded: float | None = None
    penalties_missed: float | None = None
    yellow_cards: float | None = None
    red_cards: float | None = None
    own_goals: float | None = None
    big_chances_missed: float | None = None
    errors_leading_to_goal: float | None = None
    errors_leading_to_attempt: float | None = None
    times_tackled: float | None = None
    fouls_conceded: float | None = None
    offsides: float | None = None
    shots_off_target: float | None = None


@dataclass(frozen=True)
class BpsEstimate:
    score: float
    covered: tuple[str, ...]
    missing: tuple[str, ...]


@dataclass(frozen=True)
class BpsObservation:
    """Observed BPS beside the components the source can reconstruct."""

    inputs: BpsInputs
    observed_bps: float


@dataclass(frozen=True)
class BpsProjection:
    expected_bps: float
    bps_deviation: float
    residual_per_appearance: float
    covered: tuple[str, ...]
    missing: tuple[str, ...]


_GOAL_BPS = {1: 12.0, 2: 12.0, 3: 18.0, 4: 24.0}
_BPS_WEIGHTS = {
    "penalty_goals": 12.0,
    "assists": 9.0,
    "penalties_saved": 8.0,
    "saves_inside_box": 3.0,
    "saves_outside_box": 2.0,
    "open_play_crosses": 1.0,
    "big_chances_created": 3.0,
    "recoveries": 1.0 / 3.0,
    "key_passes": 1.0,
    "tackles": 2.0,
    "dribbles": 1.0,
    "winning_goals": 3.0,
    "goalline_clearances": 9.0,
    "fouls_won": 1.0,
    "shots_on_target": 2.0,
    "pass_completion_bps": 1.0,
    "goals_conceded": -4.0,
    "penalties_conceded": -3.0,
    "penalties_missed": -6.0,
    "yellow_cards": -3.0,
    "red_cards": -9.0,
    "own_goals": -6.0,
    "big_chances_missed": -3.0,
    "errors_leading_to_goal": -3.0,
    "errors_leading_to_attempt": -1.0,
    "times_tackled": -1.0,
    "fouls_conceded": -1.0,
    "offsides": -1.0,
    "shots_off_target": -1.0,
}


def expected_bps(inputs: BpsInputs, *, position: int) -> BpsEstimate:
    """Apply every official coefficient for which the caller has evidence."""
    if position not in _GOAL_BPS:
        raise ValueError(f"unknown FPL position {position}")

    score = 0.0
    covered: set[str] = set()
    if inputs.probability_appear is not None and inputs.probability_sixty is not None:
        if not 0.0 <= inputs.probability_sixty <= inputs.probability_appear <= 1.0:
            raise ValueError("appearance probabilities must satisfy P(60) <= P(appear)")
        score += 3.0 * (inputs.probability_appear - inputs.probability_sixty)
        score += 6.0 * inputs.probability_sixty
        covered.update(("probability_appear", "probability_sixty"))

    if inputs.goals is not None:
        score += _non_negative(inputs.goals, "goals") * _GOAL_BPS[position]
        covered.add("goals")
    if inputs.clean_sheets is not None:
        clean_sheets = _non_negative(inputs.clean_sheets, "clean_sheets")
        score += clean_sheets * (12.0 if position in (1, 2) else 0.0)
        covered.add("clean_sheets")
    if inputs.clearances_blocks_interceptions is not None:
        score += (
            _non_negative(
                inputs.clearances_blocks_interceptions,
                "clearances_blocks_interceptions",
            )
            / 2.0
        )
        covered.add("clearances_blocks_interceptions")

    for name, weight in _BPS_WEIGHTS.items():
        value = getattr(inputs, name)
        if value is None:
            continue
        score += _non_negative(value, name) * weight
        covered.add(name)

    names = {field.name for field in fields(inputs)}
    missing = tuple(sorted(names - covered))
    return BpsEstimate(
        score=score,
        covered=tuple(sorted(covered)),
        missing=missing,
    )


def project_bps_from_history(
    observations: list[BpsObservation],
    projected: BpsInputs,
    *,
    position: int,
) -> BpsProjection | None:
    """Project official components plus the player's unobserved BPS residual.

    Passing, errors, shot location and several Opta events are not present in
    the history corpus. Setting them to zero would systematically erase a
    player's style. Instead, each historical BPS score is reduced by the
    components that can be reconstructed, leaving a per-appearance residual.
    The projected match carries that residual only by P(appear).
    """
    if not observations or projected.probability_appear is None:
        return None
    if not 0.0 <= projected.probability_appear <= 1.0:
        raise ValueError("probability_appear must be between zero and one")

    residuals: list[float] = []
    observed_scores: list[float] = []
    for observation in observations:
        if not math.isfinite(observation.observed_bps):
            raise ValueError("observed BPS must be finite")
        reconstructed = expected_bps(observation.inputs, position=position)
        residuals.append(observation.observed_bps - reconstructed.score)
        observed_scores.append(observation.observed_bps)

    residual = fmean(residuals)
    estimate = expected_bps(projected, position=position)
    return BpsProjection(
        expected_bps=estimate.score + residual * projected.probability_appear,
        bps_deviation=pstdev(observed_scores),
        residual_per_appearance=residual,
        covered=estimate.covered,
        missing=estimate.missing,
    )


def _non_negative(value: float, name: str) -> float:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return value


@dataclass(frozen=True)
class BonusCandidate:
    element_id: int
    expected_bps: float
    bps_deviation: float


@dataclass(frozen=True)
class BonusExpectation:
    first: float
    second: float
    third: float
    expected_points: float


def bonus_expectations(candidates: list[BonusCandidate]) -> dict[int, BonusExpectation]:
    """Estimate top-three placement from independent BPS distributions.

    Each pairwise comparison is the difference between two normal BPS
    distributions. A small dynamic program then finds the probability that
    exactly zero, one or two competitors finish ahead. This is deterministic
    and preserves uncertainty; integer BPS tie rules remain a documented
    approximation until event-level component distributions are retained.
    """
    if len({candidate.element_id for candidate in candidates}) != len(candidates):
        raise ValueError("bonus candidates must have unique element ids")
    for candidate in candidates:
        if not math.isfinite(candidate.expected_bps) or candidate.bps_deviation < 0.0:
            raise ValueError("bonus candidate distributions must be finite")

    results: dict[int, BonusExpectation] = {}
    for candidate in candidates:
        # Probability of exactly zero, one and two competitors finishing ahead.
        ranks = [1.0, 0.0, 0.0]
        for other in candidates:
            if other.element_id == candidate.element_id:
                continue
            ahead = _probability_ahead(other, candidate)
            ranks = [
                ranks[0] * (1.0 - ahead),
                ranks[1] * (1.0 - ahead) + ranks[0] * ahead,
                ranks[2] * (1.0 - ahead) + ranks[1] * ahead,
            ]
        first, second, third = ranks
        results[candidate.element_id] = BonusExpectation(
            first=first,
            second=second,
            third=third,
            expected_points=3.0 * first + 2.0 * second + third,
        )
    return results


def _probability_ahead(other: BonusCandidate, candidate: BonusCandidate) -> float:
    deviation = math.hypot(other.bps_deviation, candidate.bps_deviation)
    difference = other.expected_bps - candidate.expected_bps
    if deviation == 0.0:
        if difference > 0.0:
            return 1.0
        if difference < 0.0:
            return 0.0
        return 0.5
    return NormalDist().cdf(difference / deviation)


__all__ = [
    "BonusCandidate",
    "BonusExpectation",
    "BpsEstimate",
    "BpsInputs",
    "BpsObservation",
    "BpsProjection",
    "EvidenceMetric",
    "MarketRoute",
    "ParticipationEstimate",
    "RouteEvidence",
    "bonus_expectations",
    "expected_bps",
    "infer_participation",
    "pressure_adjusted_defcon",
    "pressure_adjusted_saves",
    "project_bps_from_history",
]
