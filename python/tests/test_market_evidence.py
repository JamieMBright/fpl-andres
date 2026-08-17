"""Market evidence as route-level expectations with explicit provenance."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from fpl_andres.models.market_evidence import (
    BonusCandidate,
    BpsInputs,
    BpsObservation,
    RouteEvidence,
    bonus_expectations,
    expected_bps,
    infer_participation,
    pressure_adjusted_defcon,
    pressure_adjusted_saves,
    project_bps_from_history,
)

SOURCE_HASH = "sha256:" + "a" * 64
OBSERVED_AT = datetime(2026, 8, 17, 9, 50, tzinfo=UTC)


class TestRouteEvidence:
    def test_an_observed_signal_carries_its_source_and_time(self) -> None:
        evidence = RouteEvidence(
            route="goals",
            metric="expected_events",
            value=0.42,
            evidence_level="inferred",
            source="the-odds-api",
            observed_at=OBSERVED_AT,
            source_hashes=(SOURCE_HASH,),
            reason_codes=("anytime_probability_poisson_inversion",),
            books=3,
        )

        assert evidence.value == 0.42
        assert evidence.observed_at == OBSERVED_AT

    def test_unavailable_evidence_has_no_made_up_value(self) -> None:
        evidence = RouteEvidence(
            route="own_goals",
            metric="expected_events",
            value=None,
            evidence_level="unavailable",
            source="none",
            observed_at=OBSERVED_AT,
            source_hashes=(SOURCE_HASH,),
            reason_codes=("no_named_player_market",),
        )

        assert evidence.value is None

    def test_a_value_labelled_unavailable_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="unavailable"):
            RouteEvidence(
                route="own_goals",
                metric="expected_events",
                value=0.01,
                evidence_level="unavailable",
                source="none",
                observed_at=OBSERVED_AT,
                source_hashes=(SOURCE_HASH,),
                reason_codes=("no_named_player_market",),
            )


class TestParticipationInference:
    def test_a_stronger_market_than_the_record_raises_expected_minutes(self) -> None:
        estimate = infer_participation(
            recorded_minutes=45.0,
            recorded_start_probability=0.5,
            recorded_events=0.2,
            market_events=0.32,
            weight=0.35,
        )

        assert estimate is not None
        assert 45.0 < estimate.expected_minutes <= 90.0
        assert 0.5 < estimate.start_probability <= 1.0

    def test_no_recorded_scoring_rate_makes_minutes_unidentifiable(self) -> None:
        assert (
            infer_participation(
                recorded_minutes=45.0,
                recorded_start_probability=0.5,
                recorded_events=0.0,
                market_events=0.3,
                weight=0.35,
            )
            is None
        )


class TestPressureRoutes:
    def test_more_opponent_threat_raises_expected_save_points(self) -> None:
        assert pressure_adjusted_saves(0.7, 1.5) > pressure_adjusted_saves(0.7, 0.8)

    def test_defcon_pressure_is_monotonic_but_cannot_pay_more_than_the_route(self) -> None:
        soft = pressure_adjusted_defcon(0.8, 0.7)
        hard = pressure_adjusted_defcon(0.8, 1.8)

        assert 0.0 <= soft < hard < 2.0


class TestBpsReconstruction:
    def test_known_actions_use_the_official_bps_coefficients(self) -> None:
        estimate = expected_bps(
            BpsInputs(
                probability_appear=1.0,
                probability_sixty=1.0,
                goals=1.0,
                assists=1.0,
                shots_on_target=1.0,
                yellow_cards=1.0,
            ),
            position=3,
        )

        # 6 for 60+, 18 for a midfielder goal, 9 for an assist,
        # 2 for a shot on target, and -3 for a yellow card.
        assert estimate.score == pytest.approx(32.0)
        assert "goals" in estimate.covered
        assert "key_passes" in estimate.missing

    def test_defensive_actions_are_counted_separately(self) -> None:
        estimate = expected_bps(
            BpsInputs(
                clearances_blocks_interceptions=4.0,
                recoveries=6.0,
                tackles=2.0,
            ),
            position=2,
        )

        # 1 per two CBI, 1 per three recoveries, 2 per tackle.
        assert estimate.score == pytest.approx(8.0)

    def test_unavailable_opta_actions_carry_as_a_historical_residual(self) -> None:
        observations = [
            BpsObservation(
                inputs=BpsInputs(
                    probability_appear=1.0,
                    probability_sixty=1.0,
                    goals=1.0,
                ),
                observed_bps=30.0,
            ),
            BpsObservation(
                inputs=BpsInputs(
                    probability_appear=1.0,
                    probability_sixty=1.0,
                    goals=0.0,
                ),
                observed_bps=12.0,
            ),
        ]
        projected = BpsInputs(
            probability_appear=0.8,
            probability_sixty=0.7,
            goals=0.2,
        )

        result = project_bps_from_history(observations, projected, position=3)

        assert result is not None
        # Residuals are 6 and 6 BPS. The projection carries 80% of their mean.
        assert result.expected_bps == pytest.approx(expected_bps(projected, position=3).score + 4.8)
        assert result.residual_per_appearance == pytest.approx(6.0)

    def test_no_observed_bps_returns_no_projection(self) -> None:
        assert project_bps_from_history([], BpsInputs(goals=0.2), position=3) is None


class TestBonusPlacement:
    def test_a_higher_bps_distribution_has_more_expected_bonus(self) -> None:
        results = bonus_expectations(
            [
                BonusCandidate(element_id=1, expected_bps=30.0, bps_deviation=4.0),
                BonusCandidate(element_id=2, expected_bps=22.0, bps_deviation=4.0),
                BonusCandidate(element_id=3, expected_bps=18.0, bps_deviation=4.0),
                BonusCandidate(element_id=4, expected_bps=12.0, bps_deviation=4.0),
            ]
        )

        assert results[1].first > results[2].first
        assert results[1].expected_points > results[2].expected_points

    def test_equal_candidates_receive_equal_probabilities(self) -> None:
        results = bonus_expectations(
            [
                BonusCandidate(element_id=1, expected_bps=20.0, bps_deviation=5.0),
                BonusCandidate(element_id=2, expected_bps=20.0, bps_deviation=5.0),
                BonusCandidate(element_id=3, expected_bps=20.0, bps_deviation=5.0),
                BonusCandidate(element_id=4, expected_bps=20.0, bps_deviation=5.0),
            ]
        )

        assert results[1] == results[2] == results[3] == results[4]
