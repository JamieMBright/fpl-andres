"""Reading a scoring price as evidence about minutes.

The behaviour worth pinning is what this refuses: to invent a denominator, to
carry a default weight, and to extrapolate past certainty.
"""

from __future__ import annotations

import pytest

from fpl_andres.models.market_minutes import (
    MarketMinutesError,
    MarketMinutesEvidence,
    blend_start_rate,
    market_start_probability,
)


def _evidence(anytime: float, rate: float = 0.25, weight: float = 0.3):
    return MarketMinutesEvidence(
        anytime_goal=anytime,
        positional_scoring_rate=rate,
        weight=weight,
    )


class TestEvidence:
    def test_a_rate_nobody_measured_is_refused(self) -> None:
        with pytest.raises(MarketMinutesError, match="measured and positive"):
            _evidence(0.2, rate=0.0)

    def test_a_price_outside_zero_to_one_is_refused(self) -> None:
        with pytest.raises(MarketMinutesError, match="probability"):
            _evidence(1.4)

    def test_a_weight_outside_zero_to_one_is_refused(self) -> None:
        with pytest.raises(MarketMinutesError, match="0 to 1"):
            _evidence(0.2, weight=2.0)


class TestStartProbability:
    def test_a_player_priced_at_his_positional_rate_reads_as_a_starter(self) -> None:
        assert market_start_probability(_evidence(0.25, rate=0.25)) == 1.0

    def test_half_the_rate_reads_as_a_coin_toss(self) -> None:
        assert market_start_probability(_evidence(0.125, rate=0.25)) == 0.5

    def test_out_pricing_the_position_is_capped_not_extrapolated(self) -> None:
        assert market_start_probability(_evidence(0.9, rate=0.25)) == 1.0


class TestBlend:
    def test_a_thin_price_pulls_the_start_rate_down(self) -> None:
        # Market reads 0.1, record says 0.8, half each.
        blended = blend_start_rate(0.8, _evidence(0.025, rate=0.25, weight=0.5))

        assert blended == pytest.approx(0.45)

    def test_all_the_weight_on_the_market_ignores_the_record(self) -> None:
        assert blend_start_rate(0.2, _evidence(0.25, rate=0.25, weight=1.0)) == 1.0

    def test_no_weight_on_the_market_leaves_the_record_alone(self) -> None:
        assert blend_start_rate(0.2, _evidence(0.9, weight=0.0)) == pytest.approx(0.2)

    def test_a_recorded_rate_that_is_not_a_probability_is_refused(self) -> None:
        with pytest.raises(MarketMinutesError, match="recorded start rate"):
            blend_start_rate(1.5, _evidence(0.2))
