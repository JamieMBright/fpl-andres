"""Suspension risk from yellow card accumulation.

The thresholds are sourced Premier League rules, so they are asserted directly
rather than inferred: 5 yellows inside 19 matches, 10 by matchweek 32, 15 across
the season, banning one, two and three matches.
"""

from __future__ import annotations

import pytest

from fpl_andres.models.suspension_risk import (
    THRESHOLDS,
    next_threshold,
    suspension_risk,
)


def test_the_published_thresholds_are_what_is_modelled() -> None:
    assert [(t.yellows, t.by_match, t.matches_banned) for t in THRESHOLDS] == [
        (5, 19, 1),
        (10, 32, 2),
        (15, None, 3),
    ]


def test_a_clean_player_carries_no_risk() -> None:
    risk = suspension_risk(yellows=0, matches_played=10, match=11)

    assert risk.probability == 0.0
    assert risk.multiplier == 1.0


def test_a_player_one_booking_short_is_priced_hardest() -> None:
    # Four yellows in ten matches: 0.4 a match, one card needed, five to get it.
    risk = suspension_risk(yellows=4, matches_played=10, match=11, horizon=5)

    assert risk.threshold is not None
    assert risk.cards_needed == 1
    assert risk.probability == pytest.approx(1.0)
    assert risk.expected_matches_missed == pytest.approx(1.0)
    assert risk.multiplier == pytest.approx(0.8)


def test_risk_falls_as_the_player_needs_more_cards() -> None:
    close = suspension_risk(yellows=4, matches_played=20, match=21, horizon=5)
    far = suspension_risk(yellows=1, matches_played=20, match=21, horizon=5)

    assert close.probability > far.probability
    assert close.multiplier < far.multiplier


def test_a_threshold_that_has_expired_is_skipped() -> None:
    # Past match 19, the five-yellow rule can no longer be reached.
    risk = suspension_risk(yellows=4, matches_played=20, match=25)

    assert risk.threshold is not None
    assert risk.threshold.yellows == 10


def test_the_last_threshold_runs_to_the_end_of_the_season() -> None:
    assert next_threshold(14, 37) is not None
    assert next_threshold(14, 37).yellows == 15  # type: ignore[union-attr]


def test_a_player_past_every_threshold_carries_no_further_risk() -> None:
    risk = suspension_risk(yellows=15, matches_played=30, match=31)

    assert risk.threshold is None
    assert risk.multiplier == 1.0


def test_a_window_that_closes_before_the_threshold_prices_nothing() -> None:
    # One match left before the rule expires, and four cards needed in it.
    risk = suspension_risk(yellows=1, matches_played=18, match=19, horizon=5)

    assert risk.threshold is not None
    assert risk.probability < 0.2


def test_the_multiplier_never_leaves_its_bounds() -> None:
    for yellows in range(0, 16):
        for match in (1, 10, 19, 20, 32, 33, 38):
            risk = suspension_risk(yellows=yellows, matches_played=max(1, match - 1), match=match)
            assert 0.0 <= risk.multiplier <= 1.0
            assert 0.0 <= risk.probability <= 1.0


def test_a_nonsense_record_is_refused() -> None:
    with pytest.raises(ValueError, match="non-negative record"):
        suspension_risk(yellows=-1, matches_played=10, match=11)
    with pytest.raises(ValueError, match="non-negative record"):
        suspension_risk(yellows=1, matches_played=10, match=0)


def test_a_player_who_has_never_played_carries_no_measured_risk() -> None:
    # No matches means no rate, and a rate invented from nothing is a guess.
    risk = suspension_risk(yellows=0, matches_played=0, match=1)

    assert risk.booking_rate == 0.0
    assert risk.multiplier == 1.0


def test_a_carried_rate_prices_a_fresh_season() -> None:
    """The tally resets in August but the player does not. Twelve yellows in
    thirty-five matches is a booking every three, and that is still true on the
    opening day even though he starts on nothing."""
    risk = suspension_risk(
        yellows=0,
        matches_played=35,
        match=1,
        booking_rate=12 / 35,
    )

    assert risk.booking_rate == pytest.approx(12 / 35)
    assert risk.threshold is not None
    # Five yellows away from the first ban, not one.
    assert risk.cards_needed == 5
    assert risk.multiplier < 1.0


def test_a_carried_rate_of_zero_costs_nothing() -> None:
    risk = suspension_risk(yellows=0, matches_played=38, match=1, booking_rate=0.0)

    assert risk.multiplier == 1.0


def test_a_negative_carried_rate_is_refused() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        suspension_risk(yellows=0, matches_played=10, match=1, booking_rate=-0.1)
