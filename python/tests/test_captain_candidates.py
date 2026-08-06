"""The boundary between the corpus and a captaincy policy.

A policy is only as honest as what it is handed. `_captain_candidates` is that
boundary: it decides which pre-deadline facts reach a thesis, and it is the one
place a realised outcome could leak into the comparison without any individual
policy looking wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

from fpl_andres.backtesting.score import _captain_candidates


@dataclass(frozen=True)
class _Minutes:
    probability_start: float


@dataclass(frozen=True)
class _Projection:
    element_id: int
    expected_points: float
    component_points: float
    minutes: _Minutes
    ceiling_ratio: float
    attacking_multiplier: float


def _projection(
    element_id: int,
    expected: float = 6.0,
    *,
    ceiling_ratio: float = 2.0,
    attacking_multiplier: float = 1.0,
) -> _Projection:
    return _Projection(
        element_id=element_id,
        expected_points=expected,
        component_points=expected - 0.5,
        minutes=_Minutes(probability_start=0.9),
        ceiling_ratio=ceiling_ratio,
        attacking_multiplier=attacking_multiplier,
    )


def test_ownership_reaches_the_policy_on_a_nought_to_a_hundred_scale() -> None:
    # The corpus stores `selected` as a count of managers, of the order of a
    # million. The rank policies price ownership in points per percentage
    # point, so handed the raw count they stop being theses and become
    # arithmetic: one always takes the most owned, the other always the least.
    candidates = _captain_candidates(
        [_projection(1), _projection(2), _projection(3)],
        {},
        {},
        {1: 4_000_000.0, 2: 1_000_000.0, 3: 200_000.0},
    )

    owned = {candidate.element_id: candidate.ownership for candidate in candidates}
    assert owned[1] == 100.0
    assert owned[2] == 25.0
    assert owned[3] == 5.0


def test_a_week_nobody_owns_anybody_does_not_divide_by_zero() -> None:
    candidates = _captain_candidates([_projection(1)], {}, {}, {1: 0.0})

    assert candidates[0].ownership == 0.0


def test_every_pre_deadline_fact_reaches_the_policy() -> None:
    candidates = _captain_candidates(
        [_projection(7, expected=8.0)],
        {7: 5.5},
        {7: 2.25},
        {7: 41.0},
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.element_id == 7
    assert candidate.expected_points == 8.0
    assert candidate.component_points == 7.5
    assert candidate.recent_points == 5.5
    assert candidate.recent_deviation == 2.25
    assert candidate.probability_start == 0.9
    assert candidate.ownership == 100.0


def test_the_ceiling_and_the_fixture_reach_the_policy_that_needs_them() -> None:
    candidates = _captain_candidates(
        [_projection(1, expected=6.0, ceiling_ratio=2.5, attacking_multiplier=1.4)],
        {},
        {},
        {1: 500.0},
    )

    # The ceiling is the projection times the shape, not a separate forecast.
    assert candidates[0].ceiling_points == 15.0
    assert candidates[0].fixture_ease == 1.4


def test_a_player_the_crowd_never_held_is_not_a_candidate() -> None:
    # Ownership defines the shortlist, so a player with no ownership row cannot
    # be ranked against one who has it.
    candidates = _captain_candidates([_projection(1), _projection(2)], {}, {}, {2: 10.0})

    assert [candidate.element_id for candidate in candidates] == [2]


def test_a_player_with_no_recent_rows_keeps_a_null_form_not_a_zero() -> None:
    # Zero form and unknown form are different claims. The form policy refuses
    # the first and has nothing to say about the second.
    candidates = _captain_candidates([_projection(3)], {}, {}, {3: 12.0})

    assert candidates[0].recent_points is None
    assert candidates[0].recent_deviation == 0.0
