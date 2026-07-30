from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from fpl_andres.models.deployment import (
    DeploymentRoleEvidence,
    DeploymentRoleObservation,
    FutureRoleEvidenceError,
    classify_deployment,
)

CUTOFF = datetime(2026, 9, 12, 9, tzinfo=UTC)


def evidence(**updates: object) -> DeploymentRoleEvidence:
    values: dict[str, object] = {
        "season": "2026-27",
        "element_id": 101,
        "listed_position": "DEF",
        "observed_role": "central_midfield",
        "window_start_event": 1,
        "window_end_event": 5,
        "starts_observed": 4,
        "source": "licensed",
        "evidence_method": "declared_lineup",
        "role_confidence": None,
        "method_version": None,
        "source_reference": "licensed:role-feed:2026-27:101",
        "source_hash": f"sha256:{'a' * 64}",
        "data_available_at": CUTOFF,
        "evidence_level": "observed",
    }
    values.update(updates)
    return DeploymentRoleEvidence.model_validate(values)


def test_defender_in_midfield_is_attacking_oop_with_defender_scoring_retained() -> None:
    signal = classify_deployment(
        evidence(),
        prediction_event=6,
        prediction_cutoff=CUTOFF,
        minimum_starts=3,
    )

    assert signal.classification == "attacking_oop"
    assert signal.effect_name == "lord_lundstram_effect"
    assert signal.watchlist_eligible
    assert signal.fpl_scoring_position == "DEF"
    assert signal.observed_role == "central_midfield"
    assert signal.evidence_level == "observed"
    assert signal.reason_codes == (
        "lord_lundstram_effect",
        "attacking_oop",
        "defender_scoring_position_retained",
        "role_starts=4",
    )


def test_midfielder_as_forward_is_oop_but_midfielder_as_fullback_is_reverse_oop() -> None:
    forward = classify_deployment(
        evidence(listed_position="MID", observed_role="striker"),
        prediction_event=6,
        prediction_cutoff=CUTOFF,
        minimum_starts=3,
    )
    fullback = classify_deployment(
        evidence(listed_position="MID", observed_role="full_back"),
        prediction_event=6,
        prediction_cutoff=CUTOFF,
        minimum_starts=3,
    )

    assert forward.classification == "attacking_oop"
    assert forward.effect_name is None
    assert forward.watchlist_eligible
    assert forward.fpl_scoring_position == "MID"
    assert fullback.classification == "reverse_oop"
    assert not fullback.watchlist_eligible


def test_small_role_sample_is_unavailable_not_assumed() -> None:
    signal = classify_deployment(
        evidence(starts_observed=2),
        prediction_event=6,
        prediction_cutoff=CUTOFF,
        minimum_starts=3,
    )

    assert signal.classification == "unavailable"
    assert signal.evidence_level == "unavailable"
    assert not signal.watchlist_eligible
    assert signal.reason_codes == ("insufficient_role_sample", "role_starts=2")


def test_heatmap_cluster_can_empirically_surface_lord_lundstram_effect() -> None:
    signal = classify_deployment(
        evidence(
            evidence_method="heatmap_cluster",
            role_confidence=0.84,
            method_version="heatmap-role/1",
            evidence_level="experimental",
        ),
        prediction_event=6,
        prediction_cutoff=CUTOFF,
        minimum_starts=3,
    )

    assert signal.effect_name == "lord_lundstram_effect"
    assert signal.classification == "attacking_oop"
    assert signal.evidence_level == "experimental"
    assert "role_method=heatmap_cluster" in signal.reason_codes
    assert "role_confidence=0.840" in signal.reason_codes


def test_role_evidence_after_cutoff_or_from_current_event_is_rejected() -> None:
    with pytest.raises(FutureRoleEvidenceError, match="prediction cutoff"):
        classify_deployment(
            evidence(data_available_at=CUTOFF + timedelta(seconds=1)),
            prediction_event=6,
            prediction_cutoff=CUTOFF,
            minimum_starts=3,
        )

    with pytest.raises(FutureRoleEvidenceError, match="before prediction event"):
        classify_deployment(
            evidence(window_end_event=6),
            prediction_event=6,
            prediction_cutoff=CUTOFF,
            minimum_starts=3,
        )


def test_manager_role_claim_cannot_be_labelled_observed() -> None:
    with pytest.raises(ValidationError, match="manager role evidence must be inferred"):
        evidence(
            source="manager",
            evidence_method="manager_observation",
            evidence_level="observed",
        )


def test_heatmap_role_requires_model_version_and_confidence() -> None:
    with pytest.raises(ValidationError, match="heatmap role evidence"):
        evidence(evidence_method="heatmap_cluster", evidence_level="experimental")


LISTED_POSITIONS = ("GKP", "DEF", "MID", "FWD")
OBSERVED_ROLES = (
    "goalkeeper",
    "centre_back",
    "full_back",
    "wing_back",
    "defensive_midfield",
    "central_midfield",
    "attacking_midfield",
    "wide_forward",
    "striker",
)
DEPLOYMENT_TRUTH_TABLE: dict[tuple[str, str], str] = {
    # GKP row: keeper aligned; anything else is attacking_oop (fielder-out-of-net).
    ("GKP", "goalkeeper"): "aligned",
    ("GKP", "centre_back"): "attacking_oop",
    ("GKP", "full_back"): "attacking_oop",
    ("GKP", "wing_back"): "attacking_oop",
    ("GKP", "defensive_midfield"): "attacking_oop",
    ("GKP", "central_midfield"): "attacking_oop",
    ("GKP", "attacking_midfield"): "attacking_oop",
    ("GKP", "wide_forward"): "attacking_oop",
    ("GKP", "striker"): "attacking_oop",
    # DEF row: DEF-tier aligned; wing_back and midfield tiers attacking_oop;
    # forward-tier attacking_oop; goalkeeper reverse_oop.
    ("DEF", "goalkeeper"): "reverse_oop",
    ("DEF", "centre_back"): "aligned",
    ("DEF", "full_back"): "aligned",
    ("DEF", "wing_back"): "attacking_oop",
    ("DEF", "defensive_midfield"): "attacking_oop",
    ("DEF", "central_midfield"): "attacking_oop",
    ("DEF", "attacking_midfield"): "attacking_oop",
    ("DEF", "wide_forward"): "attacking_oop",
    ("DEF", "striker"): "attacking_oop",
    # MID row: mid tiers aligned; defender tiers reverse_oop; forward tiers attacking_oop.
    ("MID", "goalkeeper"): "reverse_oop",
    ("MID", "centre_back"): "reverse_oop",
    ("MID", "full_back"): "reverse_oop",
    ("MID", "wing_back"): "aligned",
    ("MID", "defensive_midfield"): "aligned",
    ("MID", "central_midfield"): "aligned",
    ("MID", "attacking_midfield"): "aligned",
    ("MID", "wide_forward"): "attacking_oop",
    ("MID", "striker"): "attacking_oop",
    # FWD row: forward tier aligned; everything below reverse_oop.
    ("FWD", "goalkeeper"): "reverse_oop",
    ("FWD", "centre_back"): "reverse_oop",
    ("FWD", "full_back"): "reverse_oop",
    ("FWD", "wing_back"): "reverse_oop",
    ("FWD", "defensive_midfield"): "reverse_oop",
    ("FWD", "central_midfield"): "reverse_oop",
    ("FWD", "attacking_midfield"): "reverse_oop",
    ("FWD", "wide_forward"): "aligned",
    ("FWD", "striker"): "aligned",
}


@pytest.mark.parametrize(
    ("listed_position", "observed_role", "expected_classification"),
    [
        (listed, observed, DEPLOYMENT_TRUTH_TABLE[(listed, observed)])
        for listed in LISTED_POSITIONS
        for observed in OBSERVED_ROLES
    ],
)
def test_deployment_classification_matches_explicit_truth_table(
    listed_position: str,
    observed_role: str,
    expected_classification: str,
) -> None:
    signal = classify_deployment(
        evidence(listed_position=listed_position, observed_role=observed_role),
        prediction_event=6,
        prediction_cutoff=CUTOFF,
        minimum_starts=3,
    )

    assert signal.classification == expected_classification, (
        f"({listed_position}, {observed_role}) should be {expected_classification} "
        f"but classifier returned {signal.classification}"
    )


def _observation(
    event_id: int,
    observed_role: str,
    *,
    minutes: int = 90,
    days_before_cutoff: int | None = None,
) -> DeploymentRoleObservation:
    kickoff = CUTOFF - timedelta(days=days_before_cutoff if days_before_cutoff is not None else 1)
    return DeploymentRoleObservation(
        event_id=event_id,
        observed_role=observed_role,  # type: ignore[arg-type]
        minutes_played=minutes,
        kickoff_time=kickoff,
        role_probability=None,
    )


def _evidence_with_observations(
    observations: tuple[DeploymentRoleObservation, ...],
    **updates: object,
) -> DeploymentRoleEvidence:
    defaults: dict[str, object] = {
        "window_start_event": min(obs.event_id for obs in observations),
        "window_end_event": max(obs.event_id for obs in observations),
        "starts_observed": len(observations),
        "role_observations": observations,
        "decay_half_life_events": 2.0,
        "regime_change_threshold_events": 3,
    }
    defaults.update(updates)
    return evidence(**defaults)


def test_recency_weighted_regime_change_emits_unavailable() -> None:
    observations = (
        _observation(1, "attacking_midfield"),
        _observation(2, "attacking_midfield"),
        _observation(3, "attacking_midfield"),
        _observation(4, "attacking_midfield"),
        _observation(5, "attacking_midfield"),
        _observation(6, "full_back"),
        _observation(7, "full_back"),
        _observation(8, "full_back"),
    )
    ev = _evidence_with_observations(observations)

    signal = classify_deployment(
        ev,
        prediction_event=10,
        prediction_cutoff=CUTOFF,
        minimum_starts=1,
    )

    assert signal.classification == "unavailable"
    assert signal.evidence_level == "unavailable"
    assert "regime_change" in signal.reason_codes
    assert "recent_role=full_back" in signal.reason_codes
    assert "prior_role=attacking_midfield" in signal.reason_codes


def test_recency_weighted_consistent_recent_run_fires_attacking_oop() -> None:
    observations = tuple(_observation(event_id, "attacking_midfield") for event_id in range(1, 9))
    ev = _evidence_with_observations(observations)

    signal = classify_deployment(
        ev,
        prediction_event=10,
        prediction_cutoff=CUTOFF,
        minimum_starts=1,
    )

    assert signal.classification == "attacking_oop"
    assert signal.effect_name == "lord_lundstram_effect"
    assert "regime_change" not in signal.reason_codes
    assert signal.observed_role == "attacking_midfield"


def test_short_recent_reversion_below_threshold_does_not_trigger_regime_change() -> None:
    observations = (
        _observation(1, "attacking_midfield"),
        _observation(2, "attacking_midfield"),
        _observation(3, "attacking_midfield"),
        _observation(4, "attacking_midfield"),
        _observation(5, "attacking_midfield"),
        _observation(6, "full_back"),
        _observation(7, "full_back"),
    )
    ev = _evidence_with_observations(observations)

    signal = classify_deployment(
        ev,
        prediction_event=9,
        prediction_cutoff=CUTOFF,
        minimum_starts=1,
    )

    # Recent-run window has 3 events (5=att_mid, 6=full_back, 7=full_back); prior has 4 att_mid.
    # Recent dominant is full_back → reverse_oop for a DEF; prior dominant att_mid → attacking_oop.
    # This IS a regime change, so must be unavailable.
    assert signal.classification == "unavailable"
    assert "regime_change" in signal.reason_codes


def test_recency_weighted_starts_below_minimum_emits_unavailable() -> None:
    observations = tuple(_observation(event_id, "attacking_midfield") for event_id in range(1, 11))
    ev = _evidence_with_observations(observations)

    signal = classify_deployment(
        ev,
        prediction_event=38,
        prediction_cutoff=CUTOFF,
        minimum_starts=3,
    )

    # With half-life 2 events, weight at event 10 predicting event 38 = 0.5^14 ≈ 6e-5.
    # Sum across 10 observations stays far below 3.
    assert signal.classification == "unavailable"
    assert "insufficient_weighted_starts" in signal.reason_codes


def test_recency_bundle_requires_all_or_none_of_the_three_fields() -> None:
    observations = (_observation(1, "attacking_midfield"),)
    with pytest.raises(ValidationError, match="all be supplied together"):
        evidence(
            role_observations=observations,
            starts_observed=1,
            window_start_event=1,
            window_end_event=1,
            decay_half_life_events=2.0,
        )


def test_observations_must_lie_inside_declared_window() -> None:
    observations = (
        _observation(1, "attacking_midfield"),
        _observation(2, "attacking_midfield"),
    )
    with pytest.raises(ValidationError, match="window_end_event"):
        _evidence_with_observations(observations, window_end_event=1)
