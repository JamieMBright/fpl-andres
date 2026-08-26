"""Schema versions for the published JSON artifacts.

The artifacts are written by the publication CLIs and read by the web app or
API, which imports them at build time. Nothing recorded which shape they were
in, so a change to the
writer would have been picked up silently by the reader: fields quietly absent,
`undefined` where a number was expected, and a page that renders wrongly rather
than refusing.

A version is cheap and it moves the failure to the earliest place it can
happen. Because the web app imports these files rather than fetching them, the
check runs at build time and fails CI, not a visitor's browser.

Bump a version when a field is removed or its meaning changes. Adding an
optional field does not need one: a reader that ignores it is still correct.
"""

from __future__ import annotations

from typing import Final

#: Player-level projections plus club rows. Version 2 replaced `routes.discipline`
#: with the four events it bundled, so a card price has something to price.
PROJECTIONS_SCHEMA_VERSION: Final = 2

#: Browser season-solver inputs. Version 6 removes copied per-player quote
#: disclosure; the authoritative player-odds artifact owns it, while this
#: artifact retains only fields the solver consumes and aggregate reach counts.
SEASON_INPUTS_SCHEMA_VERSION: Final = 6

#: The header of the projections artifact, published separately so a component
#: needing only the season label does not pull the whole player list.
PROJECTIONS_META_SCHEMA_VERSION: Final = 1

#: The opening-squad plan.
OPENING_SQUAD_SCHEMA_VERSION: Final = 1

#: Full-season recommendation plan. Version 2 adds the model version that
#: generated every captain, transfer and chip call.
SEASON_PLAN_SCHEMA_VERSION: Final = 2

#: Immutable event-1 scorecard against the pre-deadline projection.
GW1_REVIEW_SCHEMA_VERSION: Final = 1

#: Population, reliability and club xStart scoring for one settled event.
XSTART_VALIDATION_SCHEMA_VERSION: Final = 1

#: Understat shot quality and penalty exposure, keyed by FPL code.
UNDERSTAT_SCHEMA_VERSION: Final = 1

# Season aggregates for the analysis scatter, one entry per season held.
ANALYSIS_SEASONS_SCHEMA_VERSION: Final = 1

__all__ = [
    "ANALYSIS_SEASONS_SCHEMA_VERSION",
    "GW1_REVIEW_SCHEMA_VERSION",
    "OPENING_SQUAD_SCHEMA_VERSION",
    "PROJECTIONS_META_SCHEMA_VERSION",
    "PROJECTIONS_SCHEMA_VERSION",
    "SEASON_INPUTS_SCHEMA_VERSION",
    "SEASON_PLAN_SCHEMA_VERSION",
    "UNDERSTAT_SCHEMA_VERSION",
    "XSTART_VALIDATION_SCHEMA_VERSION",
]
