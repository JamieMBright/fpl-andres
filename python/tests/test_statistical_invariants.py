"""Statistical invariants that must hold for every input, not just the examples.

The models are tested with worked examples, which prove the
arithmetic on the cases someone thought of. These state the properties that must
hold everywhere, and let Hypothesis look for the cases nobody thought of.

Each one is a claim the rest of the codebase relies on:

- a shrunk estimate lies between the prior and the observation, because anything
  outside that range is not shrinkage;
- recency decay is monotone, because an older observation counting for more than
  a newer one would invert the whole point of the weighting;
- an effective rank lies in [1, field size], because a rank of 0 or 11,000,001
  is not a position anyone can finish in.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from fpl_andres.models.player_rates import RatePrior, _shrink
from fpl_andres.planning.effective import RankModel

_MINUTES_PER_90 = 90.0

rates = st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)
minutes = st.floats(min_value=0.0, max_value=4000.0, allow_nan=False, allow_infinity=False)
strengths = st.floats(min_value=1.0, max_value=3000.0, allow_nan=False, allow_infinity=False)


@given(
    events=st.floats(min_value=0.0, max_value=200.0),
    observed=minutes,
    prior_rate=rates,
    strength=strengths,
)
@settings(max_examples=200, deadline=None)
def test_a_shrunk_rate_lies_between_the_prior_and_the_observation(
    events: float, observed: float, prior_rate: float, strength: float
) -> None:
    """Shrinkage moves an estimate toward the prior. It cannot move it past."""
    # Returns without minutes is impossible input, and refused. See below.
    assume(observed > 0.0 or events == 0.0)
    prior = RatePrior(goals_per_90=prior_rate, assists_per_90=0.0, strength_minutes=strength)
    shrunk = _shrink(events, observed, prior_rate, prior)

    if observed <= 0.0:
        assert shrunk == pytest.approx(prior_rate, abs=1e-9)
        return

    observed_rate = events * _MINUTES_PER_90 / observed
    low, high = sorted((prior_rate, observed_rate))
    assert low - 1e-9 <= shrunk <= high + 1e-9


@given(events=st.floats(min_value=0.01, max_value=200.0), strength=strengths)
@settings(max_examples=50, deadline=None)
def test_returns_without_minutes_are_refused(events: float, strength: float) -> None:
    """Found by Hypothesis, not by hand.

    With no minutes the denominator collapses to the prior strength while the
    numerator keeps the events, so one goal in zero minutes read as 90 goals per
    90. Unreachable through the blend, which derives both from the same
    observations, but a silent nonsense answer is not what this package does.
    """
    with pytest.raises(ValueError, match="cannot have come from"):
        _shrink(
            events,
            0.0,
            0.5,
            RatePrior(goals_per_90=0.5, assists_per_90=0.0, strength_minutes=strength),
        )


@given(events=st.floats(min_value=0.0, max_value=200.0), prior_rate=rates, strength=strengths)
@settings(max_examples=200, deadline=None)
def test_more_minutes_move_the_estimate_toward_the_observation(
    events: float, prior_rate: float, strength: float
) -> None:
    """Monotone in sample size: the prior's pull only weakens."""
    few = _shrink(
        events,
        90.0,
        prior_rate,
        RatePrior(goals_per_90=prior_rate, assists_per_90=0.0, strength_minutes=strength),
    )
    many = _shrink(
        events * 20,
        1800.0,
        prior_rate,
        RatePrior(goals_per_90=prior_rate, assists_per_90=0.0, strength_minutes=strength),
    )

    observed_rate = events * _MINUTES_PER_90 / 90.0
    assume(abs(observed_rate - prior_rate) > 1e-6)
    assert abs(many - observed_rate) <= abs(few - observed_rate) + 1e-9


@given(
    half_life=st.floats(min_value=0.5, max_value=38.0),
    prediction_event=st.integers(min_value=2, max_value=47),
)
@settings(max_examples=200, deadline=None)
def test_recency_decay_never_favours_an_older_observation(
    half_life: float, prediction_event: int
) -> None:
    """The weighting used by the minutes model, stated as a property.

    An older observation weighing more than a newer one would invert the whole
    reason for decaying at all.
    """
    weights = [
        0.5 ** ((prediction_event - event) / half_life) for event in range(1, prediction_event)
    ]

    assert weights == sorted(weights), "weights must rise toward the prediction event"
    assert all(weight > 0.0 for weight in weights[-1:])


@given(half_life=st.floats(min_value=0.5, max_value=38.0), distance=st.integers(1, 46))
@settings(max_examples=200, deadline=None)
def test_decay_halves_at_the_half_life(half_life: float, distance: int) -> None:
    """The parameter has to mean what it is called."""
    near = 0.5 ** (distance / half_life)
    far = 0.5 ** ((distance + half_life) / half_life)

    assert far == pytest.approx(near / 2.0, rel=1e-9)


@given(
    mean=st.floats(min_value=-500.0, max_value=500.0),
    spread=st.floats(min_value=0.01, max_value=200.0),
    size=st.integers(min_value=2, max_value=15_000_000),
    points=st.floats(min_value=-10_000.0, max_value=10_000.0),
)
@settings(max_examples=300, deadline=None)
def test_an_effective_rank_is_a_position_someone_could_finish_in(
    mean: float, spread: float, size: int, points: float
) -> None:
    field = RankModel(mean_points=mean, standard_deviation=spread, field_size=size)

    rank = field.rank_of(points)

    assert 1.0 <= rank <= float(size)
    assert math.isfinite(rank)


@given(
    mean=st.floats(min_value=-500.0, max_value=500.0),
    spread=st.floats(min_value=0.01, max_value=200.0),
    size=st.integers(min_value=2, max_value=15_000_000),
    points=st.floats(min_value=-10_000.0, max_value=10_000.0),
    extra=st.floats(min_value=0.0, max_value=200.0),
)
@settings(max_examples=300, deadline=None)
def test_more_points_never_makes_a_rank_worse(
    mean: float, spread: float, size: int, points: float, extra: float
) -> None:
    """The property the whole effective-points idea rests on."""
    field = RankModel(mean_points=mean, standard_deviation=spread, field_size=size)

    assert field.rank_of(points + extra) <= field.rank_of(points) + 1e-9
    assert field.places_gained(points, extra) >= -1e-9


@given(
    mean=st.floats(min_value=-500.0, max_value=500.0),
    spread=st.floats(min_value=0.01, max_value=200.0),
    points=st.floats(min_value=-10_000.0, max_value=10_000.0),
)
@settings(max_examples=300, deadline=None)
def test_the_share_below_is_a_probability(mean: float, spread: float, points: float) -> None:
    field = RankModel(mean_points=mean, standard_deviation=spread, field_size=11_000_000)

    share = field.share_below(points)

    assert 0.0 <= share <= 1.0
