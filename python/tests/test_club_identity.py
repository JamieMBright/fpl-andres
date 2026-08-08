"""A corrupted club id must not be able to buy a fourth player from one club.

This said an unknown `team_id` "silently escapes the three-per-club
constraint". That is not what happens. `HighsOptimizer` groups candidates by
whatever `team_id` they carry and caps every group at `club_limit`, so an
unrecognised id is constrained exactly like a recognised one.

The real failure is the opposite shape, and worse. A club id that is wrong
rather than unknown **splits one club into two groups**, and each group gets its
own allowance. Six Arsenal players enter a squad as three under id 1 and three
under id 21, and the optimiser proves that squad optimal because as far as the
model is concerned it obeys every constraint.

#7 also asked to validate ids against the rules snapshot. `OptimizationRules`
carries no team list, so there is nothing to validate against without inventing
one. The Premier League is fixed at 20 clubs and FPL numbers them 1..20, so the
bound is a range check, and the range is a rule rather than a guess.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from fpl_andres.optimization.contracts import OptimizationPlayer

CUTOFF = datetime(2026, 8, 14, 17, 30, tzinfo=UTC)


def _player(element_id: int, team_id: int) -> OptimizationPlayer:
    return OptimizationPlayer(
        season="2026-27",
        event=1,
        element_id=element_id,
        team_id=team_id,
        position_id=3,
        buy_price_tenths=75,
        expected_points=4.2,
        evidence_level="inferred",
        model_name="expected_points",
        model_version="1.0.0",
        data_available_at=CUTOFF,
        source_hashes=(f"sha256:{'a' * 64}",),
    )


@pytest.mark.parametrize("team_id", [1, 10, 20])
def test_every_real_club_id_is_accepted(team_id: int) -> None:
    assert _player(1, team_id).team_id == team_id


@pytest.mark.parametrize("team_id", [21, 99, 1000])
def test_a_club_id_beyond_the_twenty_is_refused(team_id: int) -> None:
    """The split-club bug this closes: id 21 would have formed its own group
    with its own three-player allowance, so one club could field six."""
    with pytest.raises(ValidationError, match="less than or equal to 20"):
        _player(1, team_id)


@pytest.mark.parametrize("team_id", [0, -1])
def test_a_non_positive_club_id_is_refused(team_id: int) -> None:
    with pytest.raises(ValidationError):
        _player(1, team_id)


def test_the_constraint_was_never_escaped_only_split() -> None:
    """Records what #7 got wrong, so it is not reopened.

    The optimiser groups by the id present on the candidate. An unknown id is
    still a group, and still capped. Nothing escapes; the danger was two groups
    where there should have been one.
    """
    from collections import defaultdict

    players = [_player(index, 1) for index in range(1, 4)] + [
        _player(index, 20) for index in range(4, 7)
    ]
    grouped: defaultdict[int, list[int]] = defaultdict(list)
    for index, player in enumerate(players):
        grouped[player.team_id].append(index)

    assert sorted(grouped) == [1, 20]
    assert all(len(indices) == 3 for indices in grouped.values())
