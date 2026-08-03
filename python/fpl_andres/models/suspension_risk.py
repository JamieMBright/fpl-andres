"""Suspension risk from yellow card accumulation.

## The rules, sourced

Premier League accumulation thresholds, which reset each season and count only
Premier League matches:

- **5 yellows** inside the first 19 matches — one match banned
- **10 yellows** by matchweek 32 — two matches banned
- **15 yellows** across the season — three matches banned

A second yellow in one match is a red, and is treated as a straight red for
suspension purposes rather than adding to the tally. Cards do not carry into the
FA Cup or EFL Cup, and bans are served in Premier League matches only.

Twenty or more yellows triggers a disciplinary hearing rather than an automatic
ban, so it is not modelled: the outcome is a judgement, not a threshold.

## What this does with them

A player on four yellows at gameweek 10 is one booking from missing a match, and
that is a real cost to his expected points that a season-average projection
cannot see. This prices it:

1. Estimate his booking rate per match from the season so far.
2. Ask how likely he is to cross the next threshold in the coming matches.
3. Turn that into the share of the next few gameweeks he is expected to miss.

The estimate is deliberately linear in his own rate. A player's booking rate is
noisy and the thresholds are far apart; a more elaborate model would be more
precise about a number that is mostly determined by whether a referee has a bad
afternoon.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "SEASON_MATCHES",
    "THRESHOLDS",
    "SuspensionRisk",
    "SuspensionThreshold",
    "next_threshold",
    "suspension_risk",
]

# Matches in a Premier League season, which is what the thresholds count. Not
# `MAX_EVENT`, which is 47 because 2019-20 restarted after a shutdown; a card
# tally has never had forty-seven matches to accumulate over.
SEASON_MATCHES = 38


@dataclass(frozen=True)
class SuspensionThreshold:
    """One accumulation rule."""

    yellows: int
    """Bookings that trigger it."""
    by_match: int | None
    """Last match it can be reached in. None means the whole season."""
    matches_banned: int


# Ordered by how soon they bite.
THRESHOLDS: tuple[SuspensionThreshold, ...] = (
    SuspensionThreshold(yellows=5, by_match=19, matches_banned=1),
    SuspensionThreshold(yellows=10, by_match=32, matches_banned=2),
    SuspensionThreshold(yellows=15, by_match=None, matches_banned=3),
)


@dataclass(frozen=True)
class SuspensionRisk:
    yellows: int
    matches_played: int
    booking_rate: float
    """Yellows per match so far."""
    threshold: SuspensionThreshold | None
    """The next one he could reach, or None when none remain."""
    cards_needed: int
    probability: float
    """Chance of reaching that threshold inside the horizon."""
    expected_matches_missed: float
    multiplier: float
    """What to scale his expected points by across the horizon."""


def next_threshold(yellows: int, match: int) -> SuspensionThreshold | None:
    """The first threshold still reachable at this point in the season."""
    for threshold in THRESHOLDS:
        if yellows >= threshold.yellows:
            continue
        if threshold.by_match is not None and match > threshold.by_match:
            continue
        return threshold
    return None


def suspension_risk(
    *,
    yellows: int,
    matches_played: int,
    match: int,
    horizon: int = 5,
    booking_rate: float | None = None,
) -> SuspensionRisk:
    """Price the chance of a ban across the next `horizon` matches.

    `match` is the player's next Premier League match number, which is what the
    thresholds are counted against; `matches_played` is his own, which may be
    fewer if he has been out.

    `booking_rate` overrides the rate implied by `yellows / matches_played`. It
    exists because the tally resets each season but the player does not: before
    a ball is kicked he is on zero yellows, and the only thing worth carrying
    across is how often he gets booked.
    """
    if yellows < 0 or matches_played < 0 or match < 1 or horizon < 1:
        raise ValueError("suspension risk needs a non-negative record and a real horizon")
    if booking_rate is not None and booking_rate < 0.0:
        raise ValueError("a booking rate cannot be negative")

    if booking_rate is not None:
        rate = booking_rate
    else:
        rate = yellows / matches_played if matches_played > 0 else 0.0
    threshold = next_threshold(yellows, match)
    if threshold is None or rate <= 0.0:
        return SuspensionRisk(
            yellows=yellows,
            matches_played=matches_played,
            booking_rate=rate,
            threshold=threshold,
            cards_needed=0 if threshold is None else threshold.yellows - yellows,
            probability=0.0,
            expected_matches_missed=0.0,
            multiplier=1.0,
        )

    needed = threshold.yellows - yellows
    # How many matches the threshold is still open for, which caps the horizon:
    # a five-yellow ban cannot be earned in match 20.
    open_for = (
        horizon if threshold.by_match is None else min(horizon, threshold.by_match - match + 1)
    )
    if open_for <= 0:
        return SuspensionRisk(
            yellows=yellows,
            matches_played=matches_played,
            booking_rate=rate,
            threshold=threshold,
            cards_needed=needed,
            probability=0.0,
            expected_matches_missed=0.0,
            multiplier=1.0,
        )

    # Expected bookings over the window, against how many he still needs. One
    # card short of a ban with one card expected is an even chance; two short is
    # half of it. Linear, and clamped, because the alternative is a precision
    # this evidence does not support.
    expected_cards = rate * open_for
    probability = max(0.0, min(1.0, expected_cards / needed))
    missed = probability * threshold.matches_banned
    multiplier = max(0.0, 1.0 - missed / horizon)

    return SuspensionRisk(
        yellows=yellows,
        matches_played=matches_played,
        booking_rate=rate,
        threshold=threshold,
        cards_needed=needed,
        probability=probability,
        expected_matches_missed=missed,
        multiplier=multiplier,
    )
