"""Where the estimate stops being about the player.

Both models shrink toward a sourced prior. Neither said how much of a given
answer came from the prior rather than the evidence, so a projection built
almost entirely from an assumption was indistinguishable from one built from
observation.

- **#26** asked for the shrinkage boundary in `player_rates` to be documented
  and tested: zero observed minutes collapses the estimate to the prior exactly.
  It does, and the arithmetic is exact rather than approximate, which is worth
  pinning because it is the one input where the model returns something it did
  not measure.

- **#27** asked for bounds on the beta-binomial prior strength so an extreme
  value "fails its contract instead of quietly dominating every posterior".
  The field is already bounded 0..38 — a whole season. Bounding it was never the
  difficulty: a perfectly legal 38 against three appearances supplies 93% of the
  posterior. The fix is to make the share visible, not to narrow a range whose
  legal values still dominate.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fpl_andres.models.minutes import (
    AppearanceObservation,
    MinutesEvidence,
    project_minutes,
)
from fpl_andres.models.player_rates import (
    PlayerRateEvidence,
    RateObservation,
    RatePrior,
    project_player_rates,
)

SEASON = "2025-26"
PRIOR_SEASON = "2024-25"
HASH = "sha256:" + "e" * 64
CUTOFF = datetime(2025, 12, 1, 11, 0, tzinfo=UTC)
PRIOR = RatePrior(goals_per_90=0.30, assists_per_90=0.20, strength_minutes=450.0)


def _rate_observation(season: str, event: int, minutes: int, goals: int = 0) -> RateObservation:
    return RateObservation(
        season=season,
        event_id=event,
        minutes=minutes,
        goals=goals,
        assists=0,
        kickoff_time=datetime(2024, 8, 1, tzinfo=UTC) + timedelta(days=7 * event),
    )


def _rate_evidence(
    *,
    current: tuple[RateObservation, ...] = (),
    carried: tuple[RateObservation, ...] = (),
    minimum_minutes: float = 180.0,
) -> PlayerRateEvidence:
    return PlayerRateEvidence(
        element_code=118748,
        season=SEASON,
        prediction_event=20,
        current_season_observations=current,
        prior_season_observations=carried,
        prior=PRIOR,
        minimum_minutes=minimum_minutes,
        blend_full_weight_minutes=900.0,
        prediction_cutoff=CUTOFF,
        data_available_at=CUTOFF - timedelta(hours=3),
        source_hashes=(HASH,),
    )


def test_zero_observed_minutes_collapses_to_the_prior_exactly() -> None:
    """#26's boundary. Not approximately the prior: the shrinkage algebra
    cancels to it, and a drift here would be a silent change to what an
    unobserved player is assumed to be.

    Reaching this boundary is also what exposed an ordering bug. The blend set
    `current_weight = 1.0` when there were no carried observations, then
    unconditionally reset it to 0.0 when current minutes were zero — so a player
    with neither produced `carried_weight = 1.0` with nothing to carry, and
    `PlayerRateProjection` refused it with "a carried weight requires the season
    it was carried from". The two overrides now run in the order that leaves the
    no-carried-season case intact.
    """
    projection = project_player_rates(_rate_evidence(minimum_minutes=0.0))

    assert projection.goals_per_90 == pytest.approx(PRIOR.goals_per_90, abs=1e-12)
    assert projection.assists_per_90 == pytest.approx(PRIOR.assists_per_90, abs=1e-12)
    assert projection.carried_weight == pytest.approx(0.0)
    assert projection.carried_season is None


def test_the_floor_normally_prevents_that_boundary_being_reached() -> None:
    """It is only reachable when the sourced minimum is itself zero. At any
    real floor the model refuses instead of answering from the prior."""
    projection = project_player_rates(_rate_evidence())

    assert projection.evidence_level == "unavailable"
    assert any("below_minutes_floor" in reason for reason in projection.reason_codes)


def test_more_minutes_move_the_estimate_away_from_the_prior() -> None:
    """The direction of the shrinkage, measured rather than asserted."""
    prolific = tuple(_rate_observation(SEASON, event, 90, goals=1) for event in range(1, 11))
    sparse = prolific[:3]

    near = project_player_rates(_rate_evidence(current=sparse)).goals_per_90
    far = project_player_rates(_rate_evidence(current=prolific)).goals_per_90

    assert PRIOR.goals_per_90 < near < far
    assert far - PRIOR.goals_per_90 > near - PRIOR.goals_per_90


def test_a_player_with_no_current_minutes_reads_entirely_from_the_carried_season() -> None:
    carried = tuple(_rate_observation(PRIOR_SEASON, event, 90, goals=1) for event in range(1, 11))

    projection = project_player_rates(_rate_evidence(carried=carried))

    assert projection.carried_weight == pytest.approx(1.0)
    assert projection.evidence_level == "inferred"
    assert any("carried_forward_from" in reason for reason in projection.reason_codes)


def _appearance(event: int, started: bool = True) -> AppearanceObservation:
    return AppearanceObservation(
        event_id=event,
        minutes=90 if started else 0,
        started=started,
        kickoff_time=datetime(2025, 8, 1, tzinfo=UTC) + timedelta(days=7 * event),
    )


def _minutes_evidence(count: int, prior_strength: float) -> MinutesEvidence:
    return MinutesEvidence(
        element_code=118748,
        season=SEASON,
        prediction_event=count + 1,
        observations=tuple(_appearance(event) for event in range(1, count + 1)),
        decay_half_life_events=6.0,
        minimum_observations=1,
        prior_start_rate=0.2,
        prior_strength_events=prior_strength,
        prediction_cutoff=CUTOFF,
        data_available_at=CUTOFF - timedelta(hours=3),
        source_hashes=(HASH,),
    )


def _prior_share(projection: object) -> float:
    for reason in projection.reason_codes:  # type: ignore[attr-defined]
        if reason.startswith("prior_share="):
            return float(reason.split("=", 1)[1])
    raise AssertionError("the projection did not report a prior share")


def test_a_projection_states_how_much_of_it_is_the_prior() -> None:
    """#27. The number the item was really worried about, now visible."""
    projection = project_minutes(_minutes_evidence(3, prior_strength=38.0))

    assert _prior_share(projection) > 0.9


def test_a_legal_prior_strength_can_still_supply_most_of_the_answer() -> None:
    """Why bounding the field was not the fix: 38 is within the contract and
    still leaves three appearances contributing under a tenth."""
    dominated = project_minutes(_minutes_evidence(3, prior_strength=38.0))
    evidenced = project_minutes(_minutes_evidence(3, prior_strength=1.0))

    assert _prior_share(dominated) > _prior_share(evidenced)
    assert abs(dominated.probability_start - 0.2) < abs(evidenced.probability_start - 0.2)


def test_the_prior_share_falls_as_appearances_accumulate() -> None:
    shares = [_prior_share(project_minutes(_minutes_evidence(n, 8.0))) for n in (2, 6, 12)]

    assert shares == sorted(shares, reverse=True)
    assert shares[0] > shares[-1]


def test_a_zero_strength_prior_reports_no_share_of_the_answer() -> None:
    projection = project_minutes(_minutes_evidence(5, prior_strength=0.0))

    assert _prior_share(projection) == pytest.approx(0.0)


@pytest.mark.parametrize("strength", [-0.1, 38.1, 100.0])
def test_a_prior_strength_outside_the_contract_is_refused(strength: float) -> None:
    """The bound #27 asked for already existed. Pinned so it stays."""
    with pytest.raises(Exception, match=r"less than or equal to 38|greater than or equal to 0"):
        _minutes_evidence(5, prior_strength=strength)
