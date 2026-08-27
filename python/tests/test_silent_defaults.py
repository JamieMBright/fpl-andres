"""Four places a missing value was read as a confident one.

Each is the same shape: something absent was substituted with a number, the
number was plausible, and nothing downstream could tell it apart from a
measurement. Collected here because the fix is the same idea in four places --
say what is not known rather than picking a value for it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fpl_andres.models.minutes import (
    AppearanceObservation,
    AvailabilityEvidence,
    MinutesEvidence,
    project_minutes,
)

KICKOFF = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)
CUTOFF = datetime(2030, 1, 1, tzinfo=UTC)


def _evidence(
    observations: tuple[AppearanceObservation, ...],
    availability: AvailabilityEvidence | None = None,
) -> MinutesEvidence:
    return MinutesEvidence(
        element_code=1,
        season="2025-26",
        prediction_event=10,
        observations=observations,
        availability=availability,
        decay_half_life_events=4.0,
        minimum_observations=3,
        prior_start_rate=0.35,
        prior_strength_events=2.0,
        current_season_weight=1.0,
        prediction_cutoff=CUTOFF,
        data_available_at=CUTOFF,
        source_hashes=("hash",),
    )


def _appearance(event: int, minutes: int, *, started: bool) -> AppearanceObservation:
    return AppearanceObservation(
        event_id=event,
        minutes=minutes,
        started=started,
        kickoff_time=KICKOFF + timedelta(days=7 * event),
        fixture_id=event,
    )


class TestARuledOutPlayerIsNotMerelyDoubtful:
    def test_a_published_zero_chance_is_unavailable(self) -> None:
        # Left as "inferred" he passed the unavailable filter in the projector
        # and reached the ranking and the captaincy shortlist, carrying an
        # evidence chip that claimed an opinion about a ruled-out player.
        projection = project_minutes(
            _evidence(
                tuple(_appearance(event, 90, started=True) for event in range(1, 6)),
                AvailabilityEvidence(status="d", chance_of_playing=0),
            )
        )

        assert projection.evidence_level == "unavailable"
        assert projection.expected_minutes == 0.0

    def test_a_genuine_doubt_is_still_inferred_rather_than_dropped(self) -> None:
        projection = project_minutes(
            _evidence(
                tuple(_appearance(event, 90, started=True) for event in range(1, 6)),
                AvailabilityEvidence(status="d", chance_of_playing=25),
            )
        )

        assert projection.evidence_level == "inferred"
        assert projection.expected_minutes > 0.0


class TestAnAssumedConditionalSaysSo:
    def test_a_player_who_has_never_started_is_flagged(self) -> None:
        # P(60 given start) defaults to certainty when there is no start to read
        # from, and multiplies a marginal that was carefully shrunk.
        projection = project_minutes(
            _evidence(tuple(_appearance(event, 15, started=False) for event in range(1, 6)))
        )

        assert any(
            code.startswith("assumed_conditional=") and "sixty_given_start" in code
            for code in projection.reason_codes
        )

    def test_a_player_who_has_never_been_benched_is_flagged(self) -> None:
        projection = project_minutes(
            _evidence(tuple(_appearance(event, 90, started=True) for event in range(1, 6)))
        )

        assert any(
            code.startswith("assumed_conditional=") and "cameo_given_benched" in code
            for code in projection.reason_codes
        )

    def test_a_player_with_both_kinds_of_week_assumes_nothing(self) -> None:
        projection = project_minutes(
            _evidence(
                (
                    _appearance(1, 90, started=True),
                    _appearance(2, 90, started=True),
                    _appearance(3, 20, started=False),
                    _appearance(4, 0, started=False),
                    _appearance(5, 90, started=True),
                )
            )
        )

        assert not any(code.startswith("assumed_conditional=") for code in projection.reason_codes)
