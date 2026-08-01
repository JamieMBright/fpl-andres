"""Fifteen copies of the UTC guard, one definition, and a claim that was wrong.

Every leakage guard in this package depends on timestamps being aware and in
UTC. The check was written out fifteen times. These tests pin the behaviour of
the one definition that replaced them, at the boundary where it matters.

Also records the outcome of improvement #5, which asked for a None guard before
the chronology comparison in SourceSnapshot. Pydantic rejects a None on a
non-optional datetime field before any validator runs, so the TypeError it
predicted cannot happen. Asserted rather than argued.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from fpl_andres.contracts import SourceSnapshot
from fpl_andres.timeguard import is_utc, require_utc

AWARE = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
HASH = "sha256:" + "a" * 64


class IsUtcTest(unittest.TestCase):
    def test_an_aware_utc_timestamp_passes(self) -> None:
        self.assertTrue(is_utc(AWARE))

    def test_a_naive_timestamp_fails(self) -> None:
        self.assertFalse(is_utc(datetime(2026, 8, 1, 12, 0)))

    def test_a_non_zero_offset_fails(self) -> None:
        self.assertFalse(is_utc(AWARE.astimezone(timezone(timedelta(hours=1)))))

    def test_a_fixed_zero_offset_zone_passes(self) -> None:
        """Not every zero-offset zone is the UTC singleton, and that is fine."""
        self.assertTrue(is_utc(AWARE.astimezone(timezone(timedelta(0)))))


class RequireUtcTest(unittest.TestCase):
    def test_it_returns_the_value_so_it_can_be_used_inline(self) -> None:
        self.assertIs(require_utc(AWARE, "kickoff"), AWARE)

    def test_the_message_names_the_offending_field(self) -> None:
        with self.assertRaises(ValueError) as caught:
            require_utc(datetime(2026, 8, 1), "kickoffTime")

        self.assertIn("kickoffTime", str(caught.exception))
        self.assertIn("aware UTC timestamp", str(caught.exception))


def _snapshot(**overrides: object) -> SourceSnapshot:
    values: dict[str, object] = {
        "source": "fpl",
        "fetched_at": AWARE,
        "data_available_at": AWARE,
        "content_hash": HASH,
        "upstream_reference": "bootstrap-static",
    }
    values.update(overrides)
    return SourceSnapshot.model_validate(values)


class SourceSnapshotTest(unittest.TestCase):
    def test_a_naive_timestamp_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="aware UTC timestamp"):
            _snapshot(fetched_at=datetime(2026, 8, 1))

    def test_data_cannot_be_available_after_it_was_fetched(self) -> None:
        with pytest.raises(ValidationError, match="cannot be later than"):
            _snapshot(data_available_at=AWARE + timedelta(seconds=1))

    def test_a_none_timestamp_is_a_validation_error_not_a_type_error(self) -> None:
        """Improvement #5 predicted a TypeError here. Pydantic gets there first."""
        with pytest.raises(ValidationError):
            _snapshot(fetched_at=None)

    def test_a_missing_timestamp_is_a_validation_error(self) -> None:
        values = {
            "source": "fpl",
            "data_available_at": AWARE,
            "content_hash": HASH,
            "upstream_reference": "bootstrap-static",
        }
        with pytest.raises(ValidationError):
            SourceSnapshot.model_validate(values)


if __name__ == "__main__":
    unittest.main()
