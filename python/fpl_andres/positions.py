"""The four FPL positions, in one place.

The same mapping between element type and position code was written in
`backtesting/score.py` and `models/deployment.py`, which is two copies of an FPL
rule and therefore two chances for them to disagree. An enum rather than a bare
dict so the set can be iterated exhaustively and a missing branch is a type
error rather than a KeyError at runtime.

Assistant Manager was `element_type` 5 in 2024/25 and was removed for 2026/27,
which is why the mapping refuses an unknown type instead of guessing.
"""

from __future__ import annotations

from enum import IntEnum

__all__ = ["Position", "PositionUnknown", "is_captain_eligible", "position_code"]


class PositionUnknown(ValueError):
    """Raised when an element type or code is not one of the four positions."""


class Position(IntEnum):
    """FPL element types. The integer value is FPL's own."""

    GOALKEEPER = 1
    DEFENDER = 2
    MIDFIELDER = 3
    FORWARD = 4

    @property
    def code(self) -> str:
        return _CODES[self]


_CODES: dict[Position, str] = {
    Position.GOALKEEPER: "GKP",
    Position.DEFENDER: "DEF",
    Position.MIDFIELDER: "MID",
    Position.FORWARD: "FWD",
}

_CAPTAIN_ELIGIBLE = frozenset({Position.MIDFIELDER, Position.FORWARD})


def _position(element_type: int) -> Position:
    try:
        return Position(element_type)
    except ValueError as error:
        raise PositionUnknown(
            f"element_type {element_type} is not one of the four FPL positions"
        ) from error


def position_code(element_type: int) -> str:
    """FPL's three-letter code for an element type.

    Refuses an unknown type rather than returning a placeholder: an element type
    this package does not know about is a rule change, and a silent 'UNK' would
    let it reach a projection.
    """
    return _CODES[_position(element_type)]


def is_captain_eligible(element_type: int) -> bool:
    """Whether an advisory captain or vice-captain may use this position."""
    return _position(element_type) in _CAPTAIN_ELIGIBLE
