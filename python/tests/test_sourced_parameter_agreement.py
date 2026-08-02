"""A hit and an empty allowance both show as paid transfers. They are not the same.

Zero free transfers passes validation, and from there every transfer costs four
points. A reader of the result could not tell a plan that deliberately took a
hit from one that had nothing free to spend, because only the paid count was
recorded. The budget is now on the result and the arithmetic between them is
checked.

Also pins improvement #4: two sourced parameters in the rate model must agree
with each other, not only be individually in range.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from fpl_andres.models.player_rates import PlayerRateEvidence, RatePrior

CUTOFF = datetime(2026, 9, 12, 9, tzinfo=UTC)
HASH = "sha256:" + "c" * 64


def _evidence(**overrides: object) -> PlayerRateEvidence:
    values: dict[str, object] = {
        "element_code": 154561,
        "season": "2026-27",
        "prediction_event": 6,
        "prior": RatePrior(
            goals_per_90=0.1,
            assists_per_90=0.1,
            strength_minutes=900.0,
        ),
        "minimum_minutes": 270.0,
        "blend_full_weight_minutes": 900.0,
        "carried_context_weight": 1.0,
        "prediction_cutoff": CUTOFF,
        "data_available_at": CUTOFF - timedelta(hours=1),
        "source_hashes": (HASH,),
    }
    values.update(overrides)
    return PlayerRateEvidence.model_validate(values)


class BlendParameterTest(unittest.TestCase):
    def test_the_default_pairing_is_accepted(self) -> None:
        self.assertEqual(_evidence().blend_full_weight_minutes, 900.0)

    def test_a_blend_that_saturates_at_the_floor_is_refused(self) -> None:
        """Every player who clears the floor would already be at full weight."""
        with pytest.raises(ValidationError, match="must exceed"):
            _evidence(minimum_minutes=900.0, blend_full_weight_minutes=900.0)

    def test_a_blend_that_saturates_below_the_floor_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="must exceed"):
            _evidence(minimum_minutes=900.0, blend_full_weight_minutes=450.0)

    def test_the_message_names_both_values(self) -> None:
        with pytest.raises(ValidationError) as caught:
            _evidence(minimum_minutes=900.0, blend_full_weight_minutes=450.0)

        message = str(caught.value)
        self.assertIn("450", message)
        self.assertIn("900", message)
        self.assertIn("carried season", message)

    def test_each_parameter_alone_is_still_range_checked(self) -> None:
        with pytest.raises(ValidationError):
            _evidence(blend_full_weight_minutes=0.0)


if __name__ == "__main__":
    unittest.main()
