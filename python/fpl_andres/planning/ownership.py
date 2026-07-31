"""Rank-relative value: what a player is worth against a specific field.

Expected points and expected *rank gain* are different objectives. Against a
field that all owns the same striker, owning him is not an edge, it is a hedge:
you gain nothing when he scores and lose heavily when you do not own him. The
quantity that moves you up a league is the gap between your ownership of a
player and the field's, multiplied by what he returns.

Effective ownership counts captaincy, because a captained player is owned twice
over for scoring purposes. A player on fifty percent ownership with twenty
percent captaincy has an effective ownership of seventy percent.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "EffectiveOwnership",
    "PlayerSwing",
    "effective_ownership",
    "mandatory_players",
    "swing",
]


@dataclass(frozen=True)
class EffectiveOwnership:
    element_id: int
    owned_share: float
    captained_share: float

    @property
    def effective(self) -> float:
        """Captaincy counts a second time: a captain scores twice."""
        return self.owned_share + self.captained_share


@dataclass(frozen=True)
class PlayerSwing:
    """What owning, or not owning, a player does to your position."""

    element_id: int
    expected_points: float
    effective_ownership: float
    owned: bool

    @property
    def swing(self) -> float:
        """Expected points gained on the average rival.

        Owning a player everyone owns is worth nothing. Not owning him costs you
        his full return times how many rivals have him.
        """
        mine = 1.0 if self.owned else 0.0
        return (mine - self.effective_ownership) * self.expected_points

    @property
    def is_hedge(self) -> bool:
        """True when the holding protects position rather than improving it."""
        return self.owned and self.effective_ownership >= 0.5


def effective_ownership(
    squads: Sequence[Sequence[int]],
    captains: Sequence[int | None],
) -> dict[int, EffectiveOwnership]:
    """Measure ownership and captaincy across a known set of rival squads.

    Used for a mini-league, where every rival's picks are known after the
    deadline. For the global game the same shape is filled from the published
    aggregate instead.
    """
    if len(squads) != len(captains):
        raise ValueError("every squad must have a captain entry, even if it is None")
    if not squads:
        return {}

    owned: dict[int, int] = {}
    captained: dict[int, int] = {}
    for squad, captain in zip(squads, captains, strict=True):
        for element_id in set(squad):
            owned[element_id] = owned.get(element_id, 0) + 1
        if captain is not None:
            captained[captain] = captained.get(captain, 0) + 1

    managers = len(squads)
    return {
        element_id: EffectiveOwnership(
            element_id=element_id,
            owned_share=count / managers,
            captained_share=captained.get(element_id, 0) / managers,
        )
        for element_id, count in owned.items()
    }


def swing(
    projected: Mapping[int, float],
    ownership: Mapping[int, EffectiveOwnership],
    held: Sequence[int],
) -> list[PlayerSwing]:
    """Rank every player by what they do to your position, not their points."""
    mine = set(held)
    candidates = set(projected) | mine
    swings = [
        PlayerSwing(
            element_id=element_id,
            expected_points=projected.get(element_id, 0.0),
            effective_ownership=(
                ownership[element_id].effective if element_id in ownership else 0.0
            ),
            owned=element_id in mine,
        )
        for element_id in candidates
    ]
    return sorted(swings, key=lambda entry: -entry.swing)


def mandatory_players(
    projected: Mapping[int, float],
    ownership: Mapping[int, EffectiveOwnership],
    *,
    threshold: float,
) -> list[int]:
    """Players it costs too much to leave out, regardless of value for money.

    A player is mandatory when the points you expect to drop by not owning him
    exceed ``threshold``. This is the arithmetic behind 'you have to have him':
    it is a statement about the field, not about the player.
    """
    return sorted(
        (
            element_id
            for element_id, points in projected.items()
            if element_id in ownership and ownership[element_id].effective * points >= threshold
        ),
        key=lambda element_id: -ownership[element_id].effective * projected[element_id],
    )
