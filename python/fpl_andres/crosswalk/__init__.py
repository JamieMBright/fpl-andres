"""Mapping FPL players onto sources that do not publish Opta ids."""

from fpl_andres.crosswalk.clubs import canonical_club
from fpl_andres.crosswalk.names import normalise, variants
from fpl_andres.crosswalk.resolve import (
    CrosswalkReport,
    ForeignPlayer,
    FplPlayer,
    MatchOutcome,
    PlayerMatch,
    resolve_crosswalk,
)

__all__ = [
    "CrosswalkReport",
    "ForeignPlayer",
    "FplPlayer",
    "MatchOutcome",
    "PlayerMatch",
    "canonical_club",
    "normalise",
    "resolve_crosswalk",
    "variants",
]
