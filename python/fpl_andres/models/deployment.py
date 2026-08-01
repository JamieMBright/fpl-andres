from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic.alias_generators import to_camel

from fpl_andres.models.contracts import EvidenceLevel
from fpl_andres.timeguard import require_utc

ListedPosition = Literal["GKP", "DEF", "MID", "FWD"]
ObservedRole = Literal[
    "goalkeeper",
    "centre_back",
    "full_back",
    "wing_back",
    "defensive_midfield",
    "central_midfield",
    "attacking_midfield",
    "wide_forward",
    "striker",
]
DeploymentClassification = Literal[
    "attacking_oop",
    "aligned",
    "reverse_oop",
    "unavailable",
]

_POSITION_GROUP: dict[ListedPosition, int] = {
    "GKP": 0,
    "DEF": 1,
    "MID": 2,
    "FWD": 3,
}
_ROLE_GROUP: dict[ObservedRole, int] = {
    "goalkeeper": 0,
    "centre_back": 1,
    "full_back": 1,
    "wing_back": 2,
    "defensive_midfield": 2,
    "central_midfield": 2,
    "attacking_midfield": 2,
    "wide_forward": 3,
    "striker": 3,
}
_DEPLOYMENT_CLASSIFICATION: dict[tuple[ListedPosition, ObservedRole], DeploymentClassification] = {
    (listed, observed): (
        "attacking_oop"
        if _ROLE_GROUP[observed] > _POSITION_GROUP[listed]
        else "reverse_oop"
        if _ROLE_GROUP[observed] < _POSITION_GROUP[listed]
        else "aligned"
    )
    for listed in _POSITION_GROUP
    for observed in _ROLE_GROUP
}


class FutureRoleEvidenceError(ValueError):
    """Raised when role evidence was unavailable for the requested decision."""


class DeploymentRoleObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    event_id: Annotated[int, Field(ge=1, le=38)]
    observed_role: ObservedRole
    minutes_played: Annotated[int, Field(ge=1, le=130)]
    kickoff_time: datetime
    role_probability: Annotated[float, Field(ge=0, le=1)] | None

    @model_validator(mode="after")
    def validate_observation(self) -> DeploymentRoleObservation:
        _require_utc(self.kickoff_time, "kickoff_time")
        return self


class DeploymentRoleEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    season: Annotated[str, Field(pattern=r"^20[0-9]{2}-[0-9]{2}$")]
    element_id: Annotated[int, Field(gt=0)]
    listed_position: ListedPosition
    observed_role: ObservedRole
    window_start_event: Annotated[int, Field(ge=1, le=38)]
    window_end_event: Annotated[int, Field(ge=1, le=38)]
    starts_observed: Annotated[int, Field(ge=1)]
    source: Literal["official_club", "licensed", "manager"]
    evidence_method: Literal["declared_lineup", "heatmap_cluster", "manager_observation"]
    role_confidence: Annotated[float, Field(ge=0, le=1)] | None
    method_version: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
        ]
        | None
    )
    source_reference: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2048),
    ]
    source_hash: Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
    data_available_at: datetime
    evidence_level: Literal["observed", "inferred", "experimental"]
    role_observations: tuple[DeploymentRoleObservation, ...] | None = None
    decay_half_life_events: Annotated[float, Field(gt=0, le=38)] | None = None
    regime_change_threshold_events: Annotated[int, Field(ge=2, le=10)] | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> DeploymentRoleEvidence:
        _require_utc(self.data_available_at, "data_available_at")
        if self.window_start_event > self.window_end_event:
            raise ValueError("role evidence window cannot be inverted")
        if self.source == "manager":
            if self.evidence_method != "manager_observation":
                raise ValueError("manager role evidence requires manager_observation")
            if self.evidence_level != "inferred":
                raise ValueError("manager role evidence must be inferred")
        elif self.evidence_method == "manager_observation":
            raise ValueError("manager_observation requires manager role evidence")
        if self.evidence_method == "heatmap_cluster":
            if (
                self.source == "manager"
                or self.role_confidence is None
                or self.method_version is None
                or self.evidence_level == "observed"
            ):
                raise ValueError(
                    "heatmap role evidence requires source, model version and confidence"
                )
        elif self.role_confidence is not None or self.method_version is not None:
            raise ValueError("role confidence and method version require heatmap_cluster")
        self._validate_recency_bundle()
        return self

    def _validate_recency_bundle(self) -> None:
        recency_fields = (
            self.role_observations,
            self.decay_half_life_events,
            self.regime_change_threshold_events,
        )
        supplied = [field is not None for field in recency_fields]
        if any(supplied) and not all(supplied):
            raise ValueError(
                "role_observations, decay_half_life_events and "
                "regime_change_threshold_events must all be supplied together"
            )
        if self.role_observations is None:
            return
        if len(self.role_observations) != self.starts_observed:
            raise ValueError("role_observations count must equal starts_observed")
        event_ids = [obs.event_id for obs in self.role_observations]
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("role_observations must not repeat an event")
        if min(event_ids) < self.window_start_event:
            raise ValueError("role_observations extend before window_start_event")
        if max(event_ids) > self.window_end_event:
            raise ValueError("role_observations extend after window_end_event")
        for obs in self.role_observations:
            if obs.kickoff_time > self.data_available_at:
                raise ValueError("observation kickoff must precede data_available_at")


class DeploymentSignal(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )

    season: Annotated[str, Field(pattern=r"^20[0-9]{2}-[0-9]{2}$")]
    prediction_event: Annotated[int, Field(ge=1, le=38)]
    element_id: Annotated[int, Field(gt=0)]
    fpl_scoring_position: ListedPosition
    observed_role: ObservedRole
    classification: DeploymentClassification
    effect_name: Literal["lord_lundstram_effect"] | None
    watchlist_eligible: bool
    evidence_level: EvidenceLevel
    reason_codes: tuple[str, ...]
    data_available_at: datetime
    source_hashes: tuple[Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")], ...]

    @model_validator(mode="after")
    def validate_signal(self) -> DeploymentSignal:
        _require_utc(self.data_available_at, "data_available_at")
        if self.watchlist_eligible != (self.classification == "attacking_oop"):
            raise ValueError("watchlist eligibility must match attacking OOP classification")
        expected_lundstram = (
            self.fpl_scoring_position == "DEF" and self.classification == "attacking_oop"
        )
        if (self.effect_name is not None) != expected_lundstram:
            raise ValueError("Lord Lundstram effect must identify every attacking OOP defender")
        if self.classification == "unavailable" and self.evidence_level != "unavailable":
            raise ValueError("unavailable deployment must have unavailable evidence")
        if not self.reason_codes:
            raise ValueError("deployment signal requires reason codes")
        if self.source_hashes != tuple(sorted(set(self.source_hashes))):
            raise ValueError("source hashes must be sorted and unique")
        return self


def classify_deployment(
    evidence: DeploymentRoleEvidence,
    *,
    prediction_event: int,
    prediction_cutoff: datetime,
    minimum_starts: int,
) -> DeploymentSignal:
    if isinstance(prediction_event, bool) or not 1 <= prediction_event <= 38:
        raise ValueError("prediction_event must be between 1 and 38")
    _require_utc(prediction_cutoff, "prediction_cutoff")
    if (
        isinstance(minimum_starts, bool)
        or not isinstance(minimum_starts, int)
        or minimum_starts < 1
    ):
        raise ValueError("minimum_starts must be a positive integer")
    if evidence.data_available_at > prediction_cutoff:
        raise FutureRoleEvidenceError("role evidence arrived after the prediction cutoff")
    if evidence.window_end_event >= prediction_event:
        raise FutureRoleEvidenceError("role evidence window must end before prediction event")

    if evidence.role_observations is not None:
        return _classify_recency_weighted(
            evidence,
            prediction_event=prediction_event,
            minimum_starts=minimum_starts,
        )

    if evidence.starts_observed < minimum_starts:
        return _signal(
            evidence,
            prediction_event=prediction_event,
            classification="unavailable",
            effect_name=None,
            evidence_level="unavailable",
            reason_codes=(
                "insufficient_role_sample",
                f"role_starts={evidence.starts_observed}",
            ),
        )

    classification: DeploymentClassification = _DEPLOYMENT_CLASSIFICATION[
        (evidence.listed_position, evidence.observed_role)
    ]

    effect_name: Literal["lord_lundstram_effect"] | None = None
    reasons: list[str] = []
    if classification == "attacking_oop" and evidence.listed_position == "DEF":
        effect_name = "lord_lundstram_effect"
        reasons.extend(
            (
                "lord_lundstram_effect",
                "attacking_oop",
                "defender_scoring_position_retained",
            )
        )
    elif classification == "attacking_oop":
        reasons.extend(
            (
                "attacking_oop",
                f"{evidence.listed_position.lower()}_scoring_position_retained",
            )
        )
    else:
        reasons.append(classification)
    reasons.append(f"role_starts={evidence.starts_observed}")
    if evidence.evidence_method == "heatmap_cluster":
        confidence = evidence.role_confidence
        if confidence is None:
            raise AssertionError("heatmap confidence must be contract-validated")
        reasons.extend(
            (
                "role_method=heatmap_cluster",
                f"role_confidence={confidence:.3f}",
            )
        )

    return _signal(
        evidence,
        prediction_event=prediction_event,
        classification=classification,
        effect_name=effect_name,
        evidence_level=evidence.evidence_level,
        reason_codes=tuple(reasons),
    )


def _signal(
    evidence: DeploymentRoleEvidence,
    *,
    prediction_event: int,
    classification: DeploymentClassification,
    effect_name: Literal["lord_lundstram_effect"] | None,
    evidence_level: EvidenceLevel,
    reason_codes: tuple[str, ...],
    observed_role: ObservedRole | None = None,
) -> DeploymentSignal:
    return DeploymentSignal(
        season=evidence.season,
        prediction_event=prediction_event,
        element_id=evidence.element_id,
        fpl_scoring_position=evidence.listed_position,
        observed_role=observed_role or evidence.observed_role,
        classification=classification,
        effect_name=effect_name,
        watchlist_eligible=classification == "attacking_oop",
        evidence_level=evidence_level,
        reason_codes=reason_codes,
        data_available_at=evidence.data_available_at,
        source_hashes=(evidence.source_hash,),
    )


def _classify_recency_weighted(
    evidence: DeploymentRoleEvidence,
    *,
    prediction_event: int,
    minimum_starts: int,
) -> DeploymentSignal:
    observations = evidence.role_observations
    half_life = evidence.decay_half_life_events
    threshold = evidence.regime_change_threshold_events
    if observations is None or half_life is None or threshold is None:
        raise AssertionError("recency bundle must be validated before classification")

    weighted_total = 0.0
    role_weights: dict[ObservedRole, float] = {}
    for obs in observations:
        weight = 0.5 ** ((prediction_event - obs.event_id) / half_life)
        weighted_total += weight
        role_weights[obs.observed_role] = role_weights.get(obs.observed_role, 0.0) + weight

    if weighted_total < minimum_starts:
        return _signal(
            evidence,
            prediction_event=prediction_event,
            classification="unavailable",
            effect_name=None,
            evidence_level="unavailable",
            reason_codes=(
                "insufficient_weighted_starts",
                f"weighted_starts={weighted_total:.3f}",
                f"decay_half_life={half_life}",
            ),
        )

    sorted_obs = sorted(observations, key=lambda obs: obs.event_id)
    recent = sorted_obs[-threshold:]
    prior = sorted_obs[:-threshold]
    if len(recent) >= threshold and len(prior) >= threshold:
        recent_role = _dominant_role(recent)
        prior_role = _dominant_role(prior)
        recent_class = _DEPLOYMENT_CLASSIFICATION[(evidence.listed_position, recent_role)]
        prior_class = _DEPLOYMENT_CLASSIFICATION[(evidence.listed_position, prior_role)]
        if recent_class != prior_class:
            return _signal(
                evidence,
                prediction_event=prediction_event,
                classification="unavailable",
                effect_name=None,
                evidence_level="unavailable",
                reason_codes=(
                    "regime_change",
                    f"recent_role={recent_role}",
                    f"prior_role={prior_role}",
                ),
                observed_role=recent_role,
            )

    effective_role = max(
        role_weights.items(),
        key=lambda item: (item[1], -_role_ordinal(item[0])),
    )[0]
    classification = _DEPLOYMENT_CLASSIFICATION[(evidence.listed_position, effective_role)]

    effect_name: Literal["lord_lundstram_effect"] | None = None
    reasons: list[str] = []
    if classification == "attacking_oop" and evidence.listed_position == "DEF":
        effect_name = "lord_lundstram_effect"
        reasons.extend(
            (
                "lord_lundstram_effect",
                "attacking_oop",
                "defender_scoring_position_retained",
            )
        )
    elif classification == "attacking_oop":
        reasons.extend(
            (
                "attacking_oop",
                f"{evidence.listed_position.lower()}_scoring_position_retained",
            )
        )
    else:
        reasons.append(classification)
    reasons.append(f"weighted_starts={weighted_total:.3f}")
    reasons.append(f"effective_role={effective_role}")
    reasons.append(f"decay_half_life={half_life}")
    if evidence.evidence_method == "heatmap_cluster" and evidence.role_confidence is not None:
        reasons.extend(
            (
                "role_method=heatmap_cluster",
                f"role_confidence={evidence.role_confidence:.3f}",
            )
        )

    return _signal(
        evidence,
        prediction_event=prediction_event,
        classification=classification,
        effect_name=effect_name,
        evidence_level=evidence.evidence_level,
        reason_codes=tuple(reasons),
        observed_role=effective_role,
    )


def _dominant_role(
    observations: tuple[DeploymentRoleObservation, ...] | list[DeploymentRoleObservation],
) -> ObservedRole:
    counts: dict[ObservedRole, int] = {}
    for obs in observations:
        counts[obs.observed_role] = counts.get(obs.observed_role, 0) + 1
    return max(counts.items(), key=lambda item: (item[1], -_role_ordinal(item[0])))[0]


def _role_ordinal(role: ObservedRole) -> int:
    return list(_ROLE_GROUP.keys()).index(role)


def _require_utc(value: datetime, label: str) -> None:
    require_utc(value, label)
