"""Read this season's elite off the Overall league, rather than off every id.

The sweep in `sweep.py` walks entry ids one at a time. Thirteen million of
them, of which about two in ten thousand ever finish inside the top ten
thousand. At the rate it holds itself to that is the better part of a week for
one pass, and 2.9 million ids in have found 2,270 managers.

The Overall league is the same information from the other end. It is an
ordinary classic league containing every entry, ordered by rank, fifty to a
page -- so the top ten thousand of the current season is two hundred requests.
Fetching a history for each of those is ten thousand more, once per manager
ever. Ten thousand two hundred against thirteen million.

What it cannot do is reach backwards: the Overall league shows the season it is
in and no other, so a manager who finished well in 2022 and has stopped playing
is invisible here and only the id sweep will ever find him. The two are
therefore complements, and this one is the cheap half that should run first.

Nothing here reads a private endpoint. Every entry id, name and rank on the
Overall league is public.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "OVERALL_LEAGUE",
    "PAGE_SIZE",
    "LeaguePage",
    "StandingRow",
    "pages_for",
    "parse_standings",
]

#: FPL's Overall league. Every entry is in it, from the first gameweek.
OVERALL_LEAGUE = 314

#: How many rows a standings page returns. Fixed by FPL, not chosen here.
PAGE_SIZE = 50


@dataclass(frozen=True)
class StandingRow:
    """One manager's current-season standing, as the league publishes it."""

    entry_id: int
    rank: int
    total: int


@dataclass(frozen=True)
class LeaguePage:
    """One page of standings, and whether another follows."""

    rows: tuple[StandingRow, ...]
    page: int
    has_next: bool


def parse_standings(payload: Mapping[str, Any]) -> LeaguePage | None:
    """Read a standings page, or None when the payload is not one.

    Returns an empty page rather than None when the league exists and has no
    rows yet. Between seasons that is the honest answer -- the Overall league
    is real and nobody has played -- and it is different from being handed
    something that is not a league at all.
    """
    standings = payload.get("standings")
    if not isinstance(standings, Mapping):
        return None
    results = standings.get("results")
    if not isinstance(results, list):
        return None

    rows: list[StandingRow] = []
    for row in results:
        if not isinstance(row, Mapping):
            continue
        entry = row.get("entry")
        rank = row.get("rank")
        total = row.get("total")
        if not isinstance(entry, int) or not isinstance(rank, int) or rank <= 0:
            continue
        rows.append(
            StandingRow(
                entry_id=entry,
                rank=rank,
                total=total if isinstance(total, int) else 0,
            )
        )
    page = standings.get("page")
    return LeaguePage(
        rows=tuple(rows),
        page=page if isinstance(page, int) else 1,
        has_next=bool(standings.get("has_next")),
    )


def pages_for(rank_ceiling: int) -> int:
    """How many pages hold the top `rank_ceiling`, rounded up."""
    if rank_ceiling <= 0:
        raise ValueError("rank ceiling must be positive")
    return -(-rank_ceiling // PAGE_SIZE)


def unseen(rows: Sequence[StandingRow], known: frozenset[int]) -> tuple[int, ...]:
    """Entry ids with no history in the catalogue yet.

    A manager's past seasons never change, so a history is fetched once and
    never again. This is what keeps the harvest cheap after the first run: the
    top ten thousand turns over slowly, so most of a week's page is already
    known.
    """
    return tuple(row.entry_id for row in rows if row.entry_id not in known)
