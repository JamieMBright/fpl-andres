from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from fpl_andres.models.player_rates import (
    FutureRateEvidenceError,
    PlayerRateEvidence,
    RateObservation,
    RatePrior,
    project_player_rates,
)

SEASON = "2025-26"
PRIOR_SEASON = "2024-25"
HASH = "sha256:" + "c" * 64
CUTOFF = datetime(2025, 8, 15, 11, 0, tzinfo=UTC)

PRIOR = RatePrior(goals_per_90=0.30, assists_per_90=0.20, strength_minutes=450.0)


def _observation(
    season: str,
    event_id: int,
    *,
    minutes: int = 90,
    goals: int = 0,
    assists: int = 0,
    expected_goals: float | None = None,
    expected_assists: float | None = None,
    kickoff: datetime | None = None,
) -> RateObservation:
    return RateObservation(
        season=season,
        event_id=event_id,
        minutes=minutes,
        goals=goals,
        assists=assists,
        expected_goals=expected_goals,
        expected_assists=expected_assists,
        kickoff_time=kickoff or datetime(2024, 8, 1, tzinfo=UTC) + timedelta(days=7 * event_id),
    )


def _evidence(
    *,
    current: tuple[RateObservation, ...] = (),
    carried: tuple[RateObservation, ...] = (),
    prediction_event: int = 1,
    minimum_minutes: float = 180.0,
    blend_full_weight_minutes: float = 900.0,
    carried_context_weight: float = 1.0,
    decay_half_life_events: float = 8.0,
) -> PlayerRateEvidence:
    return PlayerRateEvidence(
        element_code=118748,
        season=SEASON,
        prediction_event=prediction_event,
        current_season_observations=current,
        prior_season_observations=carried,
        prior=PRIOR,
        minimum_minutes=minimum_minutes,
        blend_full_weight_minutes=blend_full_weight_minutes,
        carried_context_weight=carried_context_weight,
        decay_half_life_events=decay_half_life_events,
        prediction_cutoff=CUTOFF,
        data_available_at=CUTOFF - timedelta(hours=3),
        source_hashes=(HASH,),
    )


def _full_prior_season(goals: int = 20, assists: int = 10) -> tuple[RateObservation, ...]:
    """Thirty-eight full appearances carrying the given season return."""
    return tuple(
        _observation(
            PRIOR_SEASON,
            event,
            minutes=90,
            goals=1 if event <= goals else 0,
            assists=1 if event <= assists else 0,
        )
        for event in range(1, 39)
    )


def test_gameweek_one_carries_the_prior_season_entirely() -> None:
    projection = project_player_rates(_evidence(carried=_full_prior_season()))

    assert projection.carried_weight == 1.0
    assert projection.carried_season == PRIOR_SEASON
    assert projection.current_season_minutes == 0.0
    assert projection.goals_per_90 > 0.35
    assert f"carried_forward_from={PRIOR_SEASON}" in projection.reason_codes


def test_a_carried_projection_is_inferred_not_observed() -> None:
    projection = project_player_rates(_evidence(carried=_full_prior_season()))

    # It is evidence about a different season, so it must not read as observed.
    assert projection.evidence_level == "inferred"


def test_a_promoted_club_debutant_is_unavailable_rather_than_estimated() -> None:
    projection = project_player_rates(_evidence(current=(), carried=()))

    assert projection.evidence_level == "unavailable"
    assert projection.goals_per_90 == 0.0
    assert projection.assists_per_90 == 0.0
    assert projection.carried_season is None
    assert "below_minutes_floor=180" in projection.reason_codes


def test_a_player_below_the_minutes_floor_is_unavailable() -> None:
    thin = (_observation(PRIOR_SEASON, 1, minutes=45), _observation(PRIOR_SEASON, 2, minutes=30))

    projection = project_player_rates(_evidence(carried=thin, minimum_minutes=180.0))

    assert projection.evidence_level == "unavailable"


def test_current_season_minutes_progressively_displace_the_carried_season() -> None:
    carried = _full_prior_season()
    weights: list[float] = []
    for played in (0, 2, 5, 10):
        current = tuple(_observation(SEASON, event, minutes=90) for event in range(1, played + 1))
        projection = project_player_rates(
            _evidence(
                current=current,
                carried=carried,
                prediction_event=played + 1,
                blend_full_weight_minutes=900.0,
                carried_context_weight=1.0,
            )
        )
        weights.append(projection.carried_weight)

    assert weights == sorted(weights, reverse=True)
    assert weights[0] == 1.0


def test_the_prior_season_stops_contributing_once_the_sample_floor_is_met() -> None:
    carried = _full_prior_season()
    current = tuple(_observation(SEASON, event, minutes=90) for event in range(1, 11))

    projection = project_player_rates(
        _evidence(
            current=current,
            carried=carried,
            prediction_event=11,
            blend_full_weight_minutes=900.0,
            carried_context_weight=1.0,
        )
    )

    assert projection.carried_weight == 0.0
    assert projection.evidence_level == "observed"
    assert "carried_forward_from" not in " ".join(projection.reason_codes)


def test_shrinkage_pulls_a_thin_hot_streak_toward_the_prior() -> None:
    # Three goals in three games is not a 1.0 goals-per-90 player.
    hot = tuple(_observation(SEASON, event, minutes=90, goals=1) for event in (1, 2, 3))

    projection = project_player_rates(
        _evidence(current=hot, prediction_event=4, minimum_minutes=180.0)
    )

    assert projection.goals_per_90 < 0.6
    assert projection.goals_per_90 > PRIOR.goals_per_90


def test_a_large_sample_overwhelms_the_prior() -> None:
    prolific = tuple(_observation(SEASON, event, minutes=90, goals=1) for event in range(1, 31))

    projection = project_player_rates(
        _evidence(current=prolific, prediction_event=31, minimum_minutes=180.0)
    )

    assert projection.goals_per_90 > 0.75


def test_expected_values_are_preferred_when_every_observation_carries_them() -> None:
    with_expected = tuple(
        _observation(SEASON, event, minutes=90, goals=0, expected_goals=0.5, expected_assists=0.25)
        for event in range(1, 11)
    )

    projection = project_player_rates(
        _evidence(current=with_expected, prediction_event=11, minimum_minutes=180.0)
    )

    assert "basis=expected" in projection.reason_codes
    # Zero actual goals but strong underlying numbers must not read as a drought.
    assert projection.goals_per_90 > 0.3


def test_a_partially_populated_expected_column_falls_back_to_actuals() -> None:
    mixed = (
        _observation(SEASON, 1, minutes=90, goals=1, expected_goals=0.5, expected_assists=0.1),
        _observation(SEASON, 2, minutes=90, goals=1),
        _observation(SEASON, 3, minutes=90, goals=1),
    )

    projection = project_player_rates(
        _evidence(current=mixed, prediction_event=4, minimum_minutes=180.0)
    )

    # Mixing xG with goals would blend two different measurements.
    assert "basis=actual" in projection.reason_codes


def test_carried_observations_must_not_come_from_the_current_season() -> None:
    with pytest.raises(ValidationError, match="must not come from the current season"):
        _evidence(carried=(_observation(SEASON, 1),))


def test_carried_observations_must_come_from_a_single_season() -> None:
    with pytest.raises(ValidationError, match="single prior season"):
        _evidence(carried=(_observation("2023-24", 1), _observation(PRIOR_SEASON, 1)))


def test_current_observations_must_match_the_evidence_season() -> None:
    with pytest.raises(ValidationError, match="must match the evidence season"):
        _evidence(current=(_observation(PRIOR_SEASON, 1),))


def test_evidence_from_after_the_cutoff_is_rejected() -> None:
    evidence = PlayerRateEvidence(
        element_code=1,
        season=SEASON,
        prediction_event=1,
        prior_season_observations=_full_prior_season(),
        prior=PRIOR,
        minimum_minutes=180.0,
        blend_full_weight_minutes=900.0,
        carried_context_weight=1.0,
        decay_half_life_events=8.0,
        prediction_cutoff=CUTOFF,
        data_available_at=CUTOFF + timedelta(seconds=1),
        source_hashes=(HASH,),
    )

    with pytest.raises(FutureRateEvidenceError, match="prediction cutoff"):
        project_player_rates(evidence)


def test_an_observation_from_the_event_being_predicted_is_rejected() -> None:
    evidence = _evidence(
        current=(_observation(SEASON, 5, minutes=90),),
        prediction_event=5,
        minimum_minutes=0.0,
    )

    with pytest.raises(FutureRateEvidenceError, match="precede the event being predicted"):
        project_player_rates(evidence)


def test_an_observation_kicking_off_after_the_cutoff_is_rejected() -> None:
    evidence = _evidence(
        carried=(_observation(PRIOR_SEASON, 1, kickoff=CUTOFF + timedelta(days=1)),),
        minimum_minutes=0.0,
    )

    with pytest.raises(FutureRateEvidenceError, match="kickoff must precede"):
        project_player_rates(evidence)


def test_evidence_must_cite_a_source() -> None:
    with pytest.raises(ValidationError):
        PlayerRateEvidence(
            element_code=1,
            season=SEASON,
            prediction_event=1,
            prior=PRIOR,
            minimum_minutes=180.0,
            blend_full_weight_minutes=900.0,
            carried_context_weight=1.0,
            prediction_cutoff=CUTOFF,
            data_available_at=CUTOFF,
            source_hashes=(),
        )
