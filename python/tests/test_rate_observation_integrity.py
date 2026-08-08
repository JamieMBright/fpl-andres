"""A repeated gameweek must not be able to inflate a player's rate.

This said neither `player_rates.py` nor `minutes.py` rejected repeated
or unsorted event ids. Half true. `MinutesEvidence` has rejected repeats since it
was written ("observations must not repeat an event"). `PlayerRateEvidence` did
not, and rates are summed over observations, so one duplicated gameweek
double-counts that gameweek's minutes and goals into a per-90 figure the
optimiser then trusts.

Sort order is deliberately NOT enforced. Rates weight by event distance, not by
position in the list, so an unsorted list produces an identical projection.
Proved below rather than asserted, so the decision stays checkable.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from fpl_andres.models.minutes import AppearanceObservation, MinutesEvidence
from fpl_andres.models.player_rates import (
    PlayerRateEvidence,
    RateObservation,
    RatePrior,
    project_player_rates,
)

SEASON = "2025-26"
PRIOR_SEASON = "2024-25"
HASH = "sha256:" + "d" * 64
CUTOFF = datetime(2025, 8, 15, 11, 0, tzinfo=UTC)
PRIOR = RatePrior(goals_per_90=0.30, assists_per_90=0.20, strength_minutes=450.0)


def _observation(
    season: str,
    event_id: int,
    *,
    minutes: int = 90,
    goals: int = 0,
) -> RateObservation:
    return RateObservation(
        season=season,
        event_id=event_id,
        minutes=minutes,
        goals=goals,
        assists=0,
        kickoff_time=datetime(2024, 8, 1, tzinfo=UTC) + timedelta(days=7 * event_id),
    )


def _evidence(
    *,
    current: tuple[RateObservation, ...] = (),
    carried: tuple[RateObservation, ...] = (),
) -> PlayerRateEvidence:
    return PlayerRateEvidence(
        element_code=118748,
        season=SEASON,
        prediction_event=20,
        current_season_observations=current,
        prior_season_observations=carried,
        prior=PRIOR,
        minimum_minutes=180.0,
        blend_full_weight_minutes=900.0,
        carried_context_weight=1.0,
        decay_half_life_events=8.0,
        prediction_cutoff=CUTOFF,
        data_available_at=CUTOFF - timedelta(hours=3),
        source_hashes=(HASH,),
    )


def _current(events: tuple[int, ...], *, goals_on: int) -> tuple[RateObservation, ...]:
    return tuple(
        _observation(SEASON, event, goals=1 if event == goals_on else 0) for event in events
    )


def test_current_season_observations_reject_a_repeated_match() -> None:
    honest = _current(tuple(range(1, 11)), goals_on=3)
    with pytest.raises(ValidationError, match="must not repeat a match"):
        _evidence(current=(*honest, _observation(SEASON, 3, goals=1)))


def test_a_double_gameweek_is_two_matches_not_a_repeat() -> None:
    """Two fixtures in one event is a real thing the Premier League does after a
    postponement, and both of them earned him minutes. Rejecting the second
    would throw away half of what he played that week."""
    honest = _current(tuple(range(1, 11)), goals_on=3)
    second = RateObservation(
        season=SEASON,
        event_id=3,
        minutes=90,
        goals=1,
        assists=0,
        # Same event, midweek instead of the weekend.
        kickoff_time=datetime(2024, 8, 1, tzinfo=UTC) + timedelta(days=24),
    )
    evidence = _evidence(current=(*honest, second))

    assert len(evidence.current_season_observations) == 11


def test_carried_season_observations_reject_a_repeated_match() -> None:
    """The carried season is summed the same way, so it needs the same guard."""
    carried = tuple(_observation(PRIOR_SEASON, event) for event in range(1, 11))
    with pytest.raises(ValidationError, match="must not repeat a match"):
        _evidence(carried=(*carried, _observation(PRIOR_SEASON, 4)))


def test_the_two_seasons_may_share_an_event_number() -> None:
    """Gameweek 5 of 2024-25 and gameweek 5 of 2025-26 are different matches,
    so the guard must be per-season and not across the pair."""
    evidence = _evidence(
        current=_current(tuple(range(1, 11)), goals_on=3),
        carried=tuple(_observation(PRIOR_SEASON, event) for event in range(1, 11)),
    )
    assert len(evidence.current_season_observations) == 10
    assert len(evidence.prior_season_observations) == 10


def test_order_does_not_change_the_projection() -> None:
    """Why #6's sort-order half is not implemented: weighting is by event
    distance from the prediction event, not by position in the list."""
    ascending = _current(tuple(range(1, 11)), goals_on=3)
    forward = project_player_rates(_evidence(current=ascending))
    backward = project_player_rates(_evidence(current=tuple(reversed(ascending))))
    assert forward.goals_per_90 == pytest.approx(backward.goals_per_90)
    assert forward.assists_per_90 == pytest.approx(backward.assists_per_90)
    assert forward.current_season_minutes == backward.current_season_minutes
    assert forward.evidence_level == backward.evidence_level


def test_minutes_evidence_also_rejects_a_repeated_match() -> None:
    """#6 claimed this was missing in minutes.py as well. It was not."""
    observations = tuple(
        AppearanceObservation(
            event_id=event,
            minutes=90,
            started=True,
            kickoff_time=datetime(2024, 8, 1, tzinfo=UTC) + timedelta(days=7 * event),
        )
        for event in range(1, 6)
    )
    with pytest.raises(ValidationError, match="must not repeat a match"):
        MinutesEvidence(
            element_code=118748,
            season=SEASON,
            prediction_event=6,
            observations=(*observations, observations[1]),
            decay_half_life_events=6.0,
            minimum_observations=3,
            prior_start_rate=0.5,
            prior_strength_events=4.0,
            prediction_cutoff=CUTOFF,
            data_available_at=CUTOFF - timedelta(hours=3),
            source_hashes=(HASH,),
        )
