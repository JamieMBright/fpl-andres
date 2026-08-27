from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from fpl_andres.models.minutes import (
    AppearanceObservation,
    AvailabilityEvidence,
    FutureMinutesEvidenceError,
    MinutesEvidence,
    project_minutes,
)

SEASON = "2024-25"
HASH = "sha256:" + "b" * 64
CUTOFF = datetime(2025, 1, 10, 11, 0, tzinfo=UTC)


def _observation(event_id: int, minutes: int, *, started: bool) -> AppearanceObservation:
    return AppearanceObservation(
        event_id=event_id,
        minutes=minutes,
        started=started,
        kickoff_time=datetime(2024, 8, 1, tzinfo=UTC) + timedelta(days=7 * event_id),
    )


def _evidence(
    observations: tuple[AppearanceObservation, ...],
    *,
    availability: AvailabilityEvidence | None = None,
    prediction_event: int = 20,
    minimum_observations: int = 3,
    prior_start_rate: float = 0.5,
    prior_strength_events: float = 2.0,
    current_season_weight: float = 1.0,
) -> MinutesEvidence:
    return MinutesEvidence(
        element_code=118748,
        season=SEASON,
        prediction_event=prediction_event,
        observations=observations,
        availability=availability,
        decay_half_life_events=4.0,
        minimum_observations=minimum_observations,
        prior_start_rate=prior_start_rate,
        prior_strength_events=prior_strength_events,
        current_season_weight=current_season_weight,
        prediction_cutoff=CUTOFF,
        data_available_at=CUTOFF - timedelta(hours=2),
        source_hashes=(HASH,),
    )


def _nailed_starter(count: int = 10) -> tuple[AppearanceObservation, ...]:
    return tuple(_observation(event, 90, started=True) for event in range(20 - count, 20))


def test_a_nailed_starter_projects_near_certain_start_and_full_minutes() -> None:
    projection = project_minutes(_evidence(_nailed_starter()))

    assert projection.probability_start > 0.88
    assert projection.probability_sixty_minutes > 0.88
    assert projection.expected_minutes > 78
    assert projection.evidence_level == "observed"


def test_a_permanent_bench_player_projects_near_zero() -> None:
    observations = tuple(_observation(event, 0, started=False) for event in range(10, 20))

    # A bench player's prior is not a coin flip; the caller sources it.
    projection = project_minutes(_evidence(observations, prior_start_rate=0.05))

    assert projection.probability_start < 0.05
    assert projection.probability_appear < 0.05
    assert projection.expected_minutes < 5


def test_expected_minutes_stay_coherent_with_the_start_probability() -> None:
    # Never started, so there is no observed minutes-given-start to lean on.
    # Whatever start probability the prior leaves must still price a full match.
    observations = tuple(_observation(event, 0, started=False) for event in range(10, 20))

    projection = project_minutes(_evidence(observations, prior_start_rate=0.5))

    assert projection.expected_minutes == pytest.approx(projection.probability_start * 90)


def test_recency_dominates_a_stale_run_of_starts() -> None:
    # Started every early game, dropped for the last five.
    observations = tuple(_observation(event, 90, started=True) for event in range(5, 15)) + tuple(
        _observation(event, 0, started=False) for event in range(15, 20)
    )

    projection = project_minutes(_evidence(observations))

    assert projection.probability_start < 0.45


def test_a_recent_return_to_the_side_outweighs_an_older_benching() -> None:
    observations = tuple(_observation(event, 0, started=False) for event in range(5, 15)) + tuple(
        _observation(event, 90, started=True) for event in range(15, 20)
    )

    projection = project_minutes(_evidence(observations))

    assert projection.probability_start > 0.55


def test_the_same_record_in_reverse_order_flips_the_projection() -> None:
    # Identical counts, opposite recency. The recent run must decide.
    stale_starts = tuple(_observation(event, 90, started=True) for event in range(5, 15)) + tuple(
        _observation(event, 0, started=False) for event in range(15, 20)
    )
    recent_starts = tuple(_observation(event, 0, started=False) for event in range(5, 15)) + tuple(
        _observation(event, 90, started=True) for event in range(15, 20)
    )

    dropped = project_minutes(_evidence(stale_starts))
    restored = project_minutes(_evidence(recent_starts))

    assert restored.probability_start > dropped.probability_start + 0.15


def test_a_ruled_out_player_projects_zero_as_an_observation_not_a_guess() -> None:
    projection = project_minutes(
        _evidence(_nailed_starter(), availability=AvailabilityEvidence(status="i"))
    )

    assert projection.probability_start == 0.0
    assert projection.probability_appear == 0.0
    assert projection.expected_minutes == 0.0
    # We observed the player is out; that is knowledge, not absence of it.
    assert projection.evidence_level == "observed"
    assert "ruled_out" in projection.reason_codes


@pytest.mark.parametrize("status", ["i", "s", "u", "n"])
def test_every_ruled_out_status_produces_zero_minutes(status: str) -> None:
    projection = project_minutes(
        _evidence(
            _nailed_starter(),
            availability=AvailabilityEvidence(status=status),  # type: ignore[arg-type]
        )
    )

    assert projection.expected_minutes == 0.0


def test_a_doubtful_status_scales_the_projection_and_downgrades_evidence() -> None:
    confident = project_minutes(_evidence(_nailed_starter()))
    doubtful = project_minutes(
        _evidence(
            _nailed_starter(),
            availability=AvailabilityEvidence(status="d", chance_of_playing=25),
        )
    )

    assert doubtful.probability_start == pytest.approx(confident.probability_start * 0.25)
    assert doubtful.expected_minutes == pytest.approx(confident.expected_minutes * 0.25)
    assert doubtful.evidence_level == "inferred"
    assert "chance_of_playing=25" in doubtful.reason_codes


def test_a_doubtful_status_without_a_published_chance_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AvailabilityEvidence(status="d")


def test_below_the_sourced_sample_floor_renders_unavailable_not_a_guess() -> None:
    observations = (_observation(18, 90, started=True), _observation(19, 90, started=True))

    projection = project_minutes(_evidence(observations, minimum_observations=5))

    assert projection.evidence_level == "unavailable"
    assert projection.expected_minutes == 0.0
    assert "below_sample_floor=5" in projection.reason_codes


def test_shrinkage_keeps_a_tiny_sample_away_from_certainty() -> None:
    three_starts = tuple(_observation(event, 90, started=True) for event in (17, 18, 19))

    projection = project_minutes(
        _evidence(
            three_starts, minimum_observations=3, prior_start_rate=0.5, prior_strength_events=2.0
        )
    )

    # Three starts is not proof of a nailed starter.
    assert projection.probability_start < 0.95
    assert projection.probability_start > 0.6


def test_a_stronger_prior_pulls_a_small_sample_further_toward_it() -> None:
    three_starts = tuple(_observation(event, 90, started=True) for event in (17, 18, 19))

    weak = project_minutes(_evidence(three_starts, prior_strength_events=1.0))
    strong = project_minutes(_evidence(three_starts, prior_strength_events=10.0))

    assert strong.probability_start < weak.probability_start


def test_current_season_weight_moves_recent_lineups_in_the_observed_direction() -> None:
    current_start = AppearanceObservation(
        event_id=1,
        minutes=90,
        started=True,
        kickoff_time=datetime(2024, 8, 8, tzinfo=UTC),
        fixture_id=1,
        source_season=SEASON,
        events_before_prediction=2,
    )
    current_bench = current_start.model_copy(update={"minutes": 0, "started": False})
    prior = tuple(
        AppearanceObservation(
            event_id=event,
            minutes=0,
            started=False,
            kickoff_time=datetime(2023, 8, 1, tzinfo=UTC) + timedelta(days=7 * event),
            fixture_id=100 + event,
            source_season="2023-24",
            events_before_prediction=40 - event,
            start_probability_only=True,
        )
        for event in range(1, 39)
    )

    ordinary_start = project_minutes(_evidence((current_start, *prior), prediction_event=3))
    weighted_start = project_minutes(
        _evidence(
            (current_start, *prior),
            prediction_event=3,
            current_season_weight=4.0,
        )
    )
    ordinary_bench = project_minutes(_evidence((current_bench, *prior), prediction_event=3))
    weighted_bench = project_minutes(
        _evidence(
            (current_bench, *prior),
            prediction_event=3,
            current_season_weight=4.0,
        )
    )

    assert weighted_start.probability_start > ordinary_start.probability_start
    assert weighted_bench.probability_start < ordinary_bench.probability_start


def test_evidence_from_after_the_cutoff_is_rejected() -> None:
    evidence = MinutesEvidence(
        element_code=1,
        season=SEASON,
        prediction_event=20,
        observations=_nailed_starter(),
        decay_half_life_events=4.0,
        minimum_observations=3,
        prior_start_rate=0.5,
        prior_strength_events=2.0,
        current_season_weight=1.0,
        prediction_cutoff=CUTOFF,
        data_available_at=CUTOFF + timedelta(seconds=1),
        source_hashes=(HASH,),
    )

    with pytest.raises(FutureMinutesEvidenceError, match="prediction cutoff"):
        project_minutes(evidence)


def test_an_observation_from_the_event_being_predicted_is_rejected() -> None:
    evidence = _evidence((_observation(20, 90, started=True), *_nailed_starter()))

    with pytest.raises(FutureMinutesEvidenceError, match="precede the event being predicted"):
        project_minutes(evidence)


def test_an_observation_kicking_off_after_the_cutoff_is_rejected() -> None:
    late = AppearanceObservation(
        event_id=14,
        minutes=90,
        started=True,
        kickoff_time=CUTOFF + timedelta(days=1),
    )
    evidence = _evidence((late, *_nailed_starter(count=5)))

    with pytest.raises(FutureMinutesEvidenceError, match="kickoff must precede"):
        project_minutes(evidence)


def test_availability_news_from_after_the_cutoff_is_rejected() -> None:
    evidence = _evidence(
        _nailed_starter(),
        availability=AvailabilityEvidence(
            status="d",
            chance_of_playing=50,
            news_added_at=CUTOFF + timedelta(hours=1),
        ),
    )

    with pytest.raises(FutureMinutesEvidenceError, match="news must precede"):
        project_minutes(evidence)


def test_evidence_must_cite_a_source() -> None:
    with pytest.raises(ValidationError):
        MinutesEvidence(
            element_code=1,
            season=SEASON,
            prediction_event=20,
            observations=_nailed_starter(),
            decay_half_life_events=4.0,
            minimum_observations=3,
            prior_start_rate=0.5,
            prior_strength_events=2.0,
            prediction_cutoff=CUTOFF,
            data_available_at=CUTOFF,
            source_hashes=(),
        )


def test_a_repeated_event_is_rejected() -> None:
    duplicated = (_observation(19, 90, started=True), _observation(19, 45, started=False))

    with pytest.raises(ValidationError):
        _evidence(duplicated, minimum_observations=1)


def test_the_same_event_and_fixture_are_distinct_across_seasons() -> None:
    previous = AppearanceObservation(
        event_id=1,
        minutes=90,
        started=True,
        kickoff_time=datetime(2023, 8, 1, tzinfo=UTC),
        fixture_id=101,
        source_season="2023-24",
        events_before_prediction=39,
        start_probability_only=True,
    )
    current = AppearanceObservation(
        event_id=1,
        minutes=20,
        started=False,
        kickoff_time=datetime(2024, 8, 1, tzinfo=UTC),
        fixture_id=101,
        source_season=SEASON,
        events_before_prediction=1,
    )

    projection = project_minutes(
        _evidence((previous, current), prediction_event=2, minimum_observations=1)
    )

    assert projection.evidence_level == "observed"
    assert projection.probability_start < 0.5


def test_carried_start_evidence_requires_its_chronological_distance() -> None:
    with pytest.raises(ValidationError, match="events_before_prediction"):
        AppearanceObservation(
            event_id=38,
            minutes=90,
            started=True,
            kickoff_time=datetime(2024, 5, 19, tzinfo=UTC),
            fixture_id=3801,
            source_season="2023-24",
            start_probability_only=True,
        )


def test_a_start_recorded_with_zero_minutes_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AppearanceObservation(
            event_id=5,
            minutes=0,
            started=True,
            kickoff_time=datetime(2024, 9, 1, tzinfo=UTC),
        )


@given(
    minutes=st.lists(
        st.tuples(st.integers(min_value=0, max_value=90), st.booleans()),
        min_size=5,
        max_size=15,
    )
)
def test_probabilities_stay_coherent_for_any_appearance_history(
    minutes: list[tuple[int, bool]],
) -> None:
    observations = tuple(
        _observation(event, 0 if (started and value == 0) else value, started=started and value > 0)
        for event, (value, started) in enumerate(minutes, start=1)
    )

    projection = project_minutes(_evidence(observations, prediction_event=len(minutes) + 1))

    assert 0.0 <= projection.probability_start <= 1.0
    assert 0.0 <= projection.probability_appear <= 1.0
    assert 0.0 <= projection.probability_sixty_minutes <= 1.0
    assert projection.probability_start <= projection.probability_appear
    assert projection.probability_sixty_minutes <= projection.probability_appear
    assert 0.0 <= projection.expected_minutes <= 120.0
