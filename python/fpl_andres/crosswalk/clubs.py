"""Club names, which every source spells differently.

An explicit list rather than fuzzy matching, because the failure mode of fuzzy
club matching is "Manchester City" resolving to "Manchester United" and taking a
whole squad's history with it. Twenty clubs a season is small enough to be
right rather than clever.
"""

from __future__ import annotations

__all__ = ["canonical_club"]

# Keyed by the normalised spelling, valued by the canonical one. Every alias any
# source in use has actually produced, not every alias imaginable.
_ALIASES = {
    "arsenal": "Arsenal",
    "aston villa": "Aston Villa",
    "villa": "Aston Villa",
    "bournemouth": "Bournemouth",
    "afc bournemouth": "Bournemouth",
    "brentford": "Brentford",
    "brighton": "Brighton",
    "brighton hove albion": "Brighton",
    "brighton and hove albion": "Brighton",
    "burnley": "Burnley",
    "chelsea": "Chelsea",
    "crystal palace": "Crystal Palace",
    "everton": "Everton",
    "fulham": "Fulham",
    "ipswich": "Ipswich",
    "ipswich town": "Ipswich",
    "leeds": "Leeds",
    "leeds united": "Leeds",
    "leicester": "Leicester",
    "leicester city": "Leicester",
    "liverpool": "Liverpool",
    "luton": "Luton",
    "luton town": "Luton",
    "man city": "Man City",
    "manchester city": "Man City",
    "man utd": "Man Utd",
    "man united": "Man Utd",
    "manchester united": "Man Utd",
    "newcastle": "Newcastle",
    "newcastle united": "Newcastle",
    "norwich": "Norwich",
    "norwich city": "Norwich",
    "nottm forest": "Nott'm Forest",
    "nottingham forest": "Nott'm Forest",
    "sheffield utd": "Sheffield Utd",
    "sheffield united": "Sheffield Utd",
    "southampton": "Southampton",
    "sunderland": "Sunderland",
    "spurs": "Spurs",
    "tottenham": "Spurs",
    "tottenham hotspur": "Spurs",
    "watford": "Watford",
    "west brom": "West Brom",
    "west bromwich albion": "West Brom",
    "west ham": "West Ham",
    "west ham united": "West Ham",
    "wolves": "Wolves",
    "wolverhampton wanderers": "Wolves",
}


def canonical_club(name: str) -> str | None:
    """One spelling per club, or None when the club is not recognised.

    None rather than the input, so an unrecognised club is a visible gap
    instead of a silent one-club island nothing can ever join to.
    """
    from fpl_andres.crosswalk.names import normalise

    return _ALIASES.get(normalise(name))
