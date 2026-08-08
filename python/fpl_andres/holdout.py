"""Which season is held out, and the rule for spending it.

The corpus enforces a cutoff *within* a season, `walk_forward`
exists as a leak guard, and `test_leakage_guards.py` polices both. All of that
stops the model seeing the future of a gameweek. None of it stops the modeller
seeing the future of a season.

Every tuning constant in this project was chosen by a person who had already
seen all four scored seasons: the recency half-lives, the prior strengths, the
multiplier clamps, the blend weight, the captaincy shortlist size, the
ownership coefficient. That is researcher degrees of freedom, and it is the
larger of the two effects when the constants are chosen by hand and the
reported edges are tenths of a point.

The evidence that it matters is already in this repository's history: the
captaincy ordering inverted completely when one arithmetic error was fixed. A
result that fragile cannot survive having its constants tuned on the same data
it is scored on.

## The rule

`HOLDOUT_SEASON` is scored but never tuned against. Fit, choose constants and
argue on the development seasons; report the holdout once, at the end, and do
not go back and adjust after seeing it. Spending it is a one-way door: the
moment a constant moves because of what the holdout said, it is a development
season and something else has to be held out.

A sourced parameter is exempt. The point is to separate constants chosen by
hand from constants taken from a paper or a practitioner, which this project
already believes it does.
"""

from __future__ import annotations

__all__ = ["DEVELOPMENT_SEASONS", "HOLDOUT_SEASON", "SCORED_SEASONS"]

#: Every season the backtest reports on. Expected-goals coverage is zero before
#: 2022-23, so earlier seasons describe a different model rather than a longer
#: history of this one.
SCORED_SEASONS: tuple[str, ...] = ("2022-23", "2023-24", "2024-25", "2025-26")

#: The most recent season, because a holdout is only worth having if it is the
#: one most like the season being played next.
HOLDOUT_SEASON = "2025-26"

DEVELOPMENT_SEASONS: tuple[str, ...] = tuple(
    season for season in SCORED_SEASONS if season != HOLDOUT_SEASON
)
