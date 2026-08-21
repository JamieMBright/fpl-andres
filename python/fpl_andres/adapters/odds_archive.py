"""Keep every quote a run was billed for, not just the median it published.

The published artifact carries one number per player per market: the median
across the books that priced it. That is the right input for a projection and
the wrong record to keep, because it throws away the twenty other prices that
formed it and it is overwritten on the next fetch. A season of odds is
trainable data and this pipeline was destroying it four times a week.

So every fetch also writes what it actually received, flattened to one row per
bookmaker per market per selection, with the time it was observed. Files are
named for the fetch and never rewritten: the archive is append-only by
directory, which is the same rule the published artifacts follow, and it means
two fetches of the same fixture an hour apart are both kept rather than one
replacing the other.

Keeping the observation time is the point. How much a price moves between a
Tuesday and the Saturday deadline is only answerable from a series, and so is
the question of how early a projection can be trusted.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

__all__ = [
    "ARCHIVE_ROOT",
    "archive_path",
    "flatten_event",
    "write_archive",
]

#: One directory per season, one file per fetch.
ARCHIVE_ROOT = Path("data/odds/player-raw")


def flatten_event(
    payload: Mapping[str, Any],
    *,
    fetched_at: datetime,
) -> Iterator[dict[str, object]]:
    """One row per bookmaker, per market, per selection.

    Flat rather than nested so the archive can be read straight into a frame
    without knowing the provider's shape, and so a market this repository does
    not model yet is still kept against the day it does.
    """
    home = payload.get("home_team")
    away = payload.get("away_team")
    commence = payload.get("commence_time")
    event_id = payload.get("id")
    for book in payload.get("bookmakers", ()):
        if not isinstance(book, Mapping):
            continue
        book_key = book.get("key")
        book_update = book.get("last_update")
        for market in book.get("markets", ()):
            if not isinstance(market, Mapping):
                continue
            market_key = market.get("key")
            market_update = market.get("last_update")
            for outcome in market.get("outcomes", ()):
                if not isinstance(outcome, Mapping):
                    continue
                yield {
                    "fetchedAt": fetched_at.isoformat(),
                    "eventId": event_id,
                    "commenceTime": commence,
                    "home": home,
                    "away": away,
                    "bookmaker": book_key,
                    "bookmakerUpdated": book_update,
                    "market": market_key,
                    "marketUpdated": market_update,
                    # The provider keys player markets by `description` and puts
                    # the side in `name`; team markets use `name` for the side.
                    "selection": outcome.get("name"),
                    "player": outcome.get("description"),
                    "price": outcome.get("price"),
                    "point": outcome.get("point"),
                }


def archive_path(season: str, fetched_at: datetime, *, root: Path = ARCHIVE_ROOT) -> Path:
    """Where a fetch's rows belong. Named for the fetch, so never rewritten."""
    stamp = fetched_at.strftime("%Y%m%dT%H%M%SZ")
    return root / season / f"{stamp}.jsonl.gz"


def write_archive(
    rows: Iterable[Mapping[str, object]],
    *,
    season: str,
    fetched_at: datetime,
    root: Path = ARCHIVE_ROOT,
) -> Path | None:
    """Write one fetch's rows, or nothing when the fetch returned nothing."""
    materialised = list(rows)
    if not materialised:
        return None
    path = archive_path(season, fetched_at, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Gzipped because a round of twenty-one books is tens of thousands of rows
    # and a season of them belongs in the repository rather than in a bucket
    # nobody can read without a credential.
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as handle:
        for row in materialised:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
    return path
