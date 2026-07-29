from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from fpl_andres.models.deployment import (
    DeploymentRoleEvidence,
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
