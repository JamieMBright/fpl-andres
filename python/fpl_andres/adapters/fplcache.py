"""Retroactive ownership and price history from the fplcache archive.

`crowd_snapshots` can only collect forwards from the day it was switched on.
fplcache (github.com/Randdalf/fplcache) has been storing the bootstrap payload
four times a day since well before that, LZMA-compressed, so the same series can
be recovered backwards.

Nothing here defaults a missing field. A snapshot that does not carry a price or
an ownership figure is refused, because a silently-zeroed ownership would look
exactly like a genuinely unowned player.
"""

from __future__ import annotations

import hashlib
import io
import json
import lzma
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

__all__ = [
    "CachedSnapshot",
    "FplCacheUnavailable",
    "OwnershipRow",
    "parse_snapshot",
    "snapshot_directory",
    "snapshot_url",
]

_ARCHIVE = "https://raw.githubusercontent.com/Randdalf/fplcache/main/cache"
# The archive names files HHMM, and the capture times drift by a few minutes.
_TIME_FORMAT = "%H%M"


class FplCacheUnavailable(RuntimeError):
    """Raised when an archived snapshot cannot be read or trusted."""


@dataclass(frozen=True)
class OwnershipRow:
    """One player at one instant."""

    element_code: int
    element_id: int
    now_cost_tenths: int
    selected_by_percent: float
    transfers_in_event: int
    transfers_out_event: int


@dataclass(frozen=True)
class CachedSnapshot:
    """Provenance for one archived bootstrap payload."""

    captured_at: datetime
    source_url: str
    content_hash: str
    element_count: int


def snapshot_directory(day: datetime) -> str:
    """The archive lays out cache/{year}/{month}/{day} with no zero padding."""
    return f"{day.year}/{day.month}/{day.day}"


def snapshot_url(day: datetime, file_name: str) -> str:
    return f"{_ARCHIVE}/{snapshot_directory(day)}/{file_name}"


def parse_snapshot(
    payload: bytes, *, source_url: str, day: datetime, file_name: str
) -> tuple[CachedSnapshot, tuple[OwnershipRow, ...]]:
    """Decompress one archived bootstrap and pull out the ownership series."""
    try:
        with lzma.open(io.BytesIO(payload)) as stream:
            document = json.loads(stream.read())
    except (lzma.LZMAError, EOFError, json.JSONDecodeError) as error:
        raise FplCacheUnavailable(f"{source_url} is not readable LZMA JSON") from error

    elements = document.get("elements")
    if not isinstance(elements, list) or not elements:
        raise FplCacheUnavailable(f"{source_url} carries no elements")

    captured_at = _captured_at(day, file_name, source_url)
    rows = tuple(_row(element, source_url) for element in elements)
    return (
        CachedSnapshot(
            captured_at=captured_at,
            source_url=source_url,
            content_hash="sha256:" + hashlib.sha256(payload).hexdigest(),
            element_count=len(rows),
        ),
        rows,
    )


def _captured_at(day: datetime, file_name: str, source_url: str) -> datetime:
    stamp = file_name.split(".", 1)[0]
    try:
        clock = datetime.strptime(stamp, _TIME_FORMAT)
    except ValueError as error:
        raise FplCacheUnavailable(f"{source_url} has no readable capture time") from error
    return datetime(day.year, day.month, day.day, clock.hour, clock.minute, tzinfo=UTC)


def _row(element: Any, source_url: str) -> OwnershipRow:
    try:
        # selected_by_percent arrives as a string like "30.4".
        ownership = float(element["selected_by_percent"])
        return OwnershipRow(
            element_code=int(element["code"]),
            element_id=int(element["id"]),
            now_cost_tenths=int(element["now_cost"]),
            selected_by_percent=ownership,
            transfers_in_event=int(element["transfers_in_event"]),
            transfers_out_event=int(element["transfers_out_event"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise FplCacheUnavailable(
            f"{source_url} has an element missing a price or ownership: {error}"
        ) from error
