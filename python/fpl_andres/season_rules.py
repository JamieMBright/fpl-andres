"""Which scoring routes existed in which season.

The corpus spans seven seasons and the rules moved twice inside it. Defensive
contribution arrived for 2025/26, so a null in that column before then is the
absence of a rule and not a missing measurement -- crediting zero is right, and
would be wrong the day the column is merely unpopulated. Assistant Manager was
`element_type` 5 in 2024/25 alone, and is a chip rather than a footballer.

Treating all seven seasons under one rulebook is how a model comes to explain a
route that did not exist. This is the rulebook, per season, and
`test_season_rules.py` checks the corpus against it rather than trusting it.

## What is deliberately not here

Chip inventories. FPL publishes them in the bootstrap and `RulesSnapshot` reads
them from there, which is a source contract; writing 2021/22's chips down from
memory would be exactly the defaulting this project refuses elsewhere. A season
whose chips were never captured says so.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

__all__ = ["SEASON_RULES", "SeasonRules", "rules_for"]


@dataclass(frozen=True)
class SeasonRules:
    """The routes and squad shape in force for one season."""

    season: str
    #: Two points for clearing the CBIT/CBIRT bar. New for 2025/26.
    defensive_contribution: bool
    #: `element_type` 5, which is a chip and scores no football points.
    assistant_manager: bool
    #: Whether the chip inventory for this season was captured from a bootstrap.
    chips_recorded: bool

    @property
    def scoring_routes(self) -> int:
        """Fourteen with defensive contribution, thirteen before it."""
        return 14 if self.defensive_contribution else 13


def _rules(
    season: str,
    *,
    defensive_contribution: bool = False,
    assistant_manager: bool = False,
    chips_recorded: bool = False,
) -> SeasonRules:
    return SeasonRules(
        season=season,
        defensive_contribution=defensive_contribution,
        assistant_manager=assistant_manager,
        chips_recorded=chips_recorded,
    )


#: Keyed by season. Every entry states what changed, not what stayed the same.
SEASON_RULES: Mapping[str, SeasonRules] = {
    "2019-20": _rules("2019-20"),
    "2020-21": _rules("2020-21"),
    "2021-22": _rules("2021-22"),
    "2022-23": _rules("2022-23"),
    "2023-24": _rules("2023-24"),
    # Assistant Manager ran for one season and was withdrawn.
    "2024-25": _rules("2024-25", assistant_manager=True),
    "2025-26": _rules("2025-26", defensive_contribution=True, chips_recorded=True),
    # Identical to 2025/26 on every route. Verified against the live bootstrap
    # on 2026-08-05: four element types, zero of type 5.
    "2026-27": _rules("2026-27", defensive_contribution=True, chips_recorded=True),
}


class UnknownSeason(KeyError):
    """Raised for a season with no recorded rulebook."""


def rules_for(season: str) -> SeasonRules:
    """The rulebook for a season, or a refusal.

    Refuses rather than assuming the current rules. A season this package has
    never seen is one whose routes nobody has checked, and guessing produces a
    model that prices a route the season did not have.
    """
    try:
        return SEASON_RULES[season]
    except KeyError as error:
        raise UnknownSeason(
            f"no rulebook recorded for {season}; add it to SEASON_RULES rather "
            "than assuming the current rules applied"
        ) from error
