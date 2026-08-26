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

import math
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fpl_andres.models.contracts import EvidenceLevel
from fpl_andres.timeguard import require_utc

# A season can exceed 38 events when it is disrupted: 2019/20 was suspended
# and resumed, running to 47. The history schema already allows this.
MAX_EVENT = 47

# FPL publishes availability as a single status character.
AvailabilityStatus = Literal["a", "d", "i", "s", "u", "n"]

# Statuses that mean the player cannot feature at all.
_RULED_OUT: frozenset[str] = frozenset({"i", "s", "u", "n"})

_FULL_MATCH_MINUTES = 90
_APPEARANCE_POINT_THRESHOLD = 60


class FutureMinutesEvidenceError(ValueError):
    """Raised when minutes evidence postdates the decision cutoff."""


class OutOfWindowObservationError(ValueError):
    """Raised when recency decay has driven an observation's weight to zero."""


class AppearanceObservation(BaseModel):
    """One observed appearance, or non-appearance, in a completed event."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    event_id: Annotated[int, Field(ge=1, le=MAX_EVENT)]
    minutes: Annotated[int, Field(ge=0, le=120)]
    started: bool
    kickoff_time: datetime
    #: Which match this was. Optional because not every caller has one, but it
    #: is what makes two fixtures in one event distinguishable when the source
    #: published no kickoff and the corpus had to synthesise one per gameweek.
    fixture_id: int | None = None
    source_season: Annotated[str, Field(pattern=r"^20[0-9]{2}-[0-9]{2}$")] | None = None
    events_before_prediction: Annotated[int, Field(ge=1, le=76)] | None = None
    start_probability_only: bool = False

    @model_validator(mode="after")
    def validate_observation(self) -> AppearanceObservation:
        _require_utc(self.kickoff_time, "kickoff_time")
        if self.started and self.minutes == 0:
            raise ValueError("a recorded start cannot have zero minutes")
        if (self.source_season is None) != (self.events_before_prediction is None):
            raise ValueError("source_season and events_before_prediction must be supplied together")
        if self.start_probability_only and self.events_before_prediction is None:
            raise ValueError("start_probability_only evidence requires events_before_prediction")
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
    prediction_event: Annotated[int, Field(ge=1, le=MAX_EVENT)]
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

        # A match, not a gameweek: a double gameweek is two real appearances in
        # one event, and rejecting it would throw away half of what he played.
        # Keyed on the fixture where one is known, because a synthesised kickoff
        # is per gameweek and would make a double look like a repeat.
        matches = [
            (
                observation.source_season or self.season,
                observation.event_id,
                observation.fixture_id
                if observation.fixture_id is not None
                else observation.kickoff_time,
            )
            for observation in self.observations
        ]
        if len(set(matches)) != len(matches):
            raise ValueError("observations must not repeat a match")
        for observation in self.observations:
            if observation.source_season == self.season:
                expected_distance = self.prediction_event - observation.event_id
                if observation.events_before_prediction != expected_distance:
                    raise ValueError(
                        "current-season events_before_prediction must match the event ledger"
                    )
            if observation.start_probability_only and observation.source_season == self.season:
                raise ValueError("current-season observations cannot be start_probability_only")
        return self


class MinutesProjection(BaseModel):
    """The appearance distribution for one player in one event."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    element_code: Annotated[int, Field(gt=0)]
    season: Annotated[str, Field(pattern=r"^20[0-9]{2}-[0-9]{2}$")]
    event: Annotated[int, Field(ge=1, le=MAX_EVENT)]
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
    if any(observation.start_probability_only for observation in evidence.observations):
        reasons.append("current_plus_carried_start")

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

    weighted = [
        (
            observation,
            math.pow(
                0.5,
                (
                    observation.events_before_prediction
                    if observation.events_before_prediction is not None
                    else evidence.prediction_event - observation.event_id
                )
                / evidence.decay_half_life_events,
            ),
        )
        for observation in evidence.observations
    ]
    # A weight that underflows to zero is an observation the model is pretending
    # to use. It does not move the estimate, but it does count towards the
    # sample floor, so the caller believes the projection rests on more evidence
    # than it does. Named rather than dropped quietly.
    vanished = sorted(
        (
            observation.source_season or evidence.season,
            observation.event_id,
        )
        for observation, weight in weighted
        if weight <= 0.0
    )
    if vanished:
        raise OutOfWindowObservationError(
            f"observations from season/event(s) {vanished} are too far from "
            f"event {evidence.prediction_event} to carry any weight at a "
            f"{evidence.decay_half_life_events}-event half-life; "
            "drop them rather than counting them towards the sample floor"
        )

    # One weight per appearance, not per event. Recency decays by event, so two
    # fixtures in a double gameweek share a factor -- but each is a match that
    # happened and each has to count. Summing the event map put a double into
    # the denominator once and into the numerator twice, which let a player who
    # started both halves of one carry a start rate above 1.
    total_weight = sum(weight for _, weight in weighted)
    if total_weight <= 0.0:
        reasons.append("recency_weights_vanished")
        return _unavailable(evidence, reasons)

    start_weight = sum(weight for observation, weight in weighted if observation.started)
    weighted_start_rate = start_weight / total_weight

    # Kish effective sample size. Recency decay decides how much each observation
    # informs the estimate; it must not pretend the observations never happened,
    # which is what shrinking against the raw weight sum would do.
    squared_weight = sum(weight * weight for _, weight in weighted)
    effective_sample = (total_weight * total_weight) / squared_weight
    reasons.append(f"effective_sample={effective_sample:.2f}")

    # Beta-Binomial shrinkage toward the sourced prior keeps a three-appearance
    # sample from reading as a certainty.
    prior_strength = evidence.prior_strength_events
    probability_start = (
        weighted_start_rate * effective_sample + evidence.prior_start_rate * prior_strength
    ) / (effective_sample + prior_strength)
    # How much of the answer is the prior rather than the player. Bounding
    # prior_strength was never the difficulty: a legal value can still supply
    # most of the posterior, and without this the projection cannot say so.
    reasons.append(f"prior_share={prior_strength / (effective_sample + prior_strength):.3f}")

    conditional = [
        (observation, weight)
        for observation, weight in weighted
        if not observation.start_probability_only
    ]
    starts = [(observation, weight) for observation, weight in conditional if observation.started]
    benched = [
        (observation, weight) for observation, weight in conditional if not observation.started
    ]

    # Both conditionals fall back to a certainty when there is nothing to read:
    # a player with no observed start is assumed to complete the hour, and one
    # with no observed benching never to come off it. Those are assumptions, not
    # measurements, and they multiply a marginal that was carefully shrunk. No
    # sourced prior exists to shrink them toward, and inventing one here would be
    # worse than the assumption, so the projection names which it leaned on.
    assumed = [
        name
        for name, empty in (("sixty_given_start", not starts), ("cameo_given_benched", not benched))
        if empty
    ]
    if assumed:
        reasons.append(f"assumed_conditional={'+'.join(assumed)}")

    probability_sixty_given_start = _weighted_share(
        starts, lambda o: o.minutes >= _APPEARANCE_POINT_THRESHOLD, default=1.0
    )
    mean_minutes_given_start = _weighted_mean(
        starts, lambda o: float(o.minutes), default=float(_FULL_MATCH_MINUTES)
    )
    probability_cameo_given_benched = _weighted_share(benched, lambda o: o.minutes > 0, default=0.0)
    mean_minutes_given_cameo = _weighted_mean(
        [(o, weight) for o, weight in benched if o.minutes > 0],
        lambda o: float(o.minutes),
        default=0.0,
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
        # A published zero is a ruled-out player, not a doubtful one. Left as
        # "inferred" he passed the unavailable filter and reached the ranking
        # and the captaincy shortlist carrying an evidence chip that claimed an
        # opinion about somebody the source had already excluded.
        evidence_level = "unavailable" if chance == 0 else "inferred"
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
    observations: list[tuple[AppearanceObservation, float]],
    predicate: Callable[[AppearanceObservation], bool],
    *,
    default: float,
) -> float:
    total = sum(weight for _, weight in observations)
    if total <= 0.0:
        return default
    hit = sum(weight for observation, weight in observations if predicate(observation))
    return hit / total


def _weighted_mean(
    observations: list[tuple[AppearanceObservation, float]],
    value: Callable[[AppearanceObservation], float],
    *,
    default: float,
) -> float:
    total = sum(weight for _, weight in observations)
    if total <= 0.0:
        return default
    return sum(weight * value(observation) for observation, weight in observations) / total


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
        if (
            observation.events_before_prediction is None
            and observation.event_id >= evidence.prediction_event
        ):
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
    require_utc(value, label)


__all__ = [
    "AppearanceObservation",
    "AvailabilityEvidence",
    "AvailabilityStatus",
    "FutureMinutesEvidenceError",
    "MinutesEvidence",
    "MinutesProjection",
    "OutOfWindowObservationError",
    "project_minutes",
]
