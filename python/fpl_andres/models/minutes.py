"""Expected minutes.

Every other projection multiplies by minutes, so a good points model paired with
a bad minutes model is worthless. This module produces the appearance
distribution a player faces in an upcoming event.

The model is deliberately parameter-light and every parameter is sourced rather
than defaulted: the recency half-life, the sample floor and the shrinkage prior
all arrive on the evidence object. A caller that cannot source them cannot get a
projection, which is the intended failure mode.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fpl_andres.models.contracts import EvidenceLevel

# FPL publishes availability as a single status character.
AvailabilityStatus = Literal["a", "d", "i", "s", "u", "n"]

# Statuses that mean the player cannot feature at all.
_RULED_OUT: frozenset[str] = frozenset({"i", "s", "u", "n"})

_FULL_MATCH_MINUTES = 90
_APPEARANCE_POINT_THRESHOLD = 60


class FutureMinutesEvidenceError(ValueError):
    """Raised when minutes evidence postdates the decision cutoff."""


class AppearanceObservation(BaseModel):
    """One observed appearance, or non-appearance, in a completed event."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    event_id: Annotated[int, Field(ge=1, le=38)]
    minutes: Annotated[int, Field(ge=0, le=120)]
    started: bool
    kickoff_time: datetime

    @model_validator(mode="after")
    def validate_observation(self) -> AppearanceObservation:
        _require_utc(self.kickoff_time, "kickoff_time")
        if self.started and self.minutes == 0:
            raise ValueError("a recorded start cannot have zero minutes")
        return self


class AvailabilityEvidence(BaseModel):
    """FPL's published availability for the upcoming event."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    status: AvailabilityStatus
    chance_of_playing: Annotated[int, Field(ge=0, le=100)] | None = None
    news_added_at: datetime | None = None

    @model_validator(mode="after")
    def validate_availability(self) -> AvailabilityEvidence:
        if self.news_added_at is not None:
            _require_utc(self.news_added_at, "news_added_at")
        if self.status == "d" and self.chance_of_playing is None:
            raise ValueError("a doubtful status requires a published chance_of_playing")
        return self


class MinutesEvidence(BaseModel):
    """Everything the minutes model is allowed to see for one player."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    element_code: Annotated[int, Field(gt=0)]
    season: Annotated[str, Field(pattern=r"^20[0-9]{2}-[0-9]{2}$")]
    prediction_event: Annotated[int, Field(ge=1, le=38)]
    observations: tuple[AppearanceObservation, ...]
    availability: AvailabilityEvidence | None = None

    # Sourced parameters. None of these may be invented by the engine.
    decay_half_life_events: Annotated[float, Field(gt=0, le=38)]
    minimum_observations: Annotated[int, Field(ge=1, le=38)]
    prior_start_rate: Annotated[float, Field(ge=0.0, le=1.0)]
    prior_strength_events: Annotated[float, Field(ge=0.0, le=38.0)]

    prediction_cutoff: datetime
    data_available_at: datetime
    source_hashes: tuple[str, ...]

    @model_validator(mode="after")
    def validate_evidence(self) -> MinutesEvidence:
        _require_utc(self.prediction_cutoff, "prediction_cutoff")
        _require_utc(self.data_available_at, "data_available_at")
        if not self.source_hashes:
            raise ValueError("minutes evidence must cite at least one source hash")

        event_ids = [observation.event_id for observation in self.observations]
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("observations must not repeat an event")
        return self


class MinutesProjection(BaseModel):
    """The appearance distribution for one player in one event."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    element_code: Annotated[int, Field(gt=0)]
    season: Annotated[str, Field(pattern=r"^20[0-9]{2}-[0-9]{2}$")]
    event: Annotated[int, Field(ge=1, le=38)]
    probability_start: Annotated[float, Field(ge=0.0, le=1.0)]
    probability_appear: Annotated[float, Field(ge=0.0, le=1.0)]
    probability_sixty_minutes: Annotated[float, Field(ge=0.0, le=1.0)]
    expected_minutes: Annotated[float, Field(ge=0.0, le=120.0)]
    evidence_level: EvidenceLevel
    reason_codes: tuple[str, ...]
    data_available_at: datetime
    source_hashes: tuple[str, ...]

    @model_validator(mode="after")
    def validate_projection(self) -> MinutesProjection:
        _require_utc(self.data_available_at, "data_available_at")
        if self.probability_sixty_minutes > self.probability_appear:
            raise ValueError("P(60+) cannot exceed P(appear)")
        if self.probability_start > self.probability_appear:
            raise ValueError("P(start) cannot exceed P(appear)")
        if self.evidence_level == "unavailable" and self.expected_minutes != 0.0:
            raise ValueError("an unavailable projection must not carry expected minutes")
        return self


def project_minutes(evidence: MinutesEvidence) -> MinutesProjection:
    """Project the appearance distribution for the upcoming event."""
    _reject_future_evidence(evidence)

    reasons: list[str] = [
        f"half_life={evidence.decay_half_life_events}",
        f"observations={len(evidence.observations)}",
    ]

    ruled_out = evidence.availability is not None and evidence.availability.status in _RULED_OUT
    if ruled_out:
        assert evidence.availability is not None
        reasons.append(f"status={evidence.availability.status}")
        reasons.append("ruled_out")
        return _projection(
            evidence,
            probability_start=0.0,
            probability_appear=0.0,
            probability_sixty=0.0,
            expected_minutes=0.0,
            evidence_level="observed",
            reasons=reasons,
        )

    if len(evidence.observations) < evidence.minimum_observations:
        reasons.append(f"below_sample_floor={evidence.minimum_observations}")
        return _unavailable(evidence, reasons)

    weights = {
        observation.event_id: 0.5
        ** ((evidence.prediction_event - observation.event_id) / evidence.decay_half_life_events)
        for observation in evidence.observations
    }
    total_weight = sum(weights.values())
    if total_weight <= 0.0:
        reasons.append("recency_weights_vanished")
        return _unavailable(evidence, reasons)

    start_weight = sum(
        weights[observation.event_id]
        for observation in evidence.observations
        if observation.started
    )
    weighted_start_rate = start_weight / total_weight

    # Kish effective sample size. Recency decay decides how much each observation
    # informs the estimate; it must not pretend the observations never happened,
    # which is what shrinking against the raw weight sum would do.
    squared_weight = sum(weight * weight for weight in weights.values())
    effective_sample = (total_weight * total_weight) / squared_weight
    reasons.append(f"effective_sample={effective_sample:.2f}")

    # Beta-Binomial shrinkage toward the sourced prior keeps a three-appearance
    # sample from reading as a certainty.
    prior_strength = evidence.prior_strength_events
    probability_start = (
        weighted_start_rate * effective_sample + evidence.prior_start_rate * prior_strength
    ) / (effective_sample + prior_strength)

    starts = [observation for observation in evidence.observations if observation.started]
    benched = [observation for observation in evidence.observations if not observation.started]

    probability_sixty_given_start = _weighted_share(
        starts, weights, lambda o: o.minutes >= _APPEARANCE_POINT_THRESHOLD, default=1.0
    )
    mean_minutes_given_start = _weighted_mean(
        starts, weights, lambda o: float(o.minutes), default=float(_FULL_MATCH_MINUTES)
    )
    probability_cameo_given_benched = _weighted_share(
        benched, weights, lambda o: o.minutes > 0, default=0.0
    )
    mean_minutes_given_cameo = _weighted_mean(
        [o for o in benched if o.minutes > 0], weights, lambda o: float(o.minutes), default=0.0
    )

    probability_appear = (
        probability_start + (1.0 - probability_start) * probability_cameo_given_benched
    )
    probability_sixty = probability_start * probability_sixty_given_start
    expected_minutes = (
        probability_start * mean_minutes_given_start
        + (1.0 - probability_start) * probability_cameo_given_benched * mean_minutes_given_cameo
    )

    evidence_level: EvidenceLevel = "observed"
    if evidence.availability is not None and evidence.availability.status == "d":
        chance = evidence.availability.chance_of_playing
        assert chance is not None
        scale = chance / 100.0
        probability_start *= scale
        probability_appear *= scale
        probability_sixty *= scale
        expected_minutes *= scale
        evidence_level = "inferred"
        reasons.append(f"chance_of_playing={chance}")

    return _projection(
        evidence,
        probability_start=probability_start,
        probability_appear=probability_appear,
        probability_sixty=probability_sixty,
        expected_minutes=expected_minutes,
        evidence_level=evidence_level,
        reasons=reasons,
    )


def _weighted_share(
    observations: list[AppearanceObservation],
    weights: dict[int, float],
    predicate: Callable[[AppearanceObservation], bool],
    *,
    default: float,
) -> float:
    total = sum(weights[o.event_id] for o in observations)
    if total <= 0.0:
        return default
    hit = sum(weights[o.event_id] for o in observations if predicate(o))
    return hit / total


def _weighted_mean(
    observations: list[AppearanceObservation],
    weights: dict[int, float],
    value: Callable[[AppearanceObservation], float],
    *,
    default: float,
) -> float:
    total = sum(weights[o.event_id] for o in observations)
    if total <= 0.0:
        return default
    return sum(weights[o.event_id] * value(o) for o in observations) / total


def _projection(
    evidence: MinutesEvidence,
    *,
    probability_start: float,
    probability_appear: float,
    probability_sixty: float,
    expected_minutes: float,
    evidence_level: EvidenceLevel,
    reasons: list[str],
) -> MinutesProjection:
    return MinutesProjection(
        element_code=evidence.element_code,
        season=evidence.season,
        event=evidence.prediction_event,
        probability_start=_clamp(probability_start),
        probability_appear=_clamp(probability_appear),
        probability_sixty_minutes=_clamp(probability_sixty),
        expected_minutes=min(max(expected_minutes, 0.0), 120.0),
        evidence_level=evidence_level,
        reason_codes=tuple(reasons),
        data_available_at=evidence.data_available_at,
        source_hashes=evidence.source_hashes,
    )


def _unavailable(evidence: MinutesEvidence, reasons: list[str]) -> MinutesProjection:
    return _projection(
        evidence,
        probability_start=0.0,
        probability_appear=0.0,
        probability_sixty=0.0,
        expected_minutes=0.0,
        evidence_level="unavailable",
        reasons=reasons,
    )


def _reject_future_evidence(evidence: MinutesEvidence) -> None:
    """Refuse anything that was not knowable at the decision cutoff."""
    if evidence.data_available_at > evidence.prediction_cutoff:
        raise FutureMinutesEvidenceError(
            "minutes evidence became available after the prediction cutoff"
        )
    for observation in evidence.observations:
        if observation.event_id >= evidence.prediction_event:
            raise FutureMinutesEvidenceError("observations must precede the event being predicted")
        if observation.kickoff_time > evidence.prediction_cutoff:
            raise FutureMinutesEvidenceError(
                "observation kickoff must precede the prediction cutoff"
            )
    availability = evidence.availability
    if (
        availability is not None
        and availability.news_added_at is not None
        and availability.news_added_at > evidence.prediction_cutoff
    ):
        raise FutureMinutesEvidenceError("availability news must precede the prediction cutoff")


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def _require_utc(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be an aware UTC timestamp")


__all__ = [
    "AppearanceObservation",
    "AvailabilityEvidence",
    "AvailabilityStatus",
    "FutureMinutesEvidenceError",
    "MinutesEvidence",
    "MinutesProjection",
    "project_minutes",
]
