from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import datetime

from fpl_andres.contracts import SourceSnapshot
from fpl_andres.timeguard import require_utc

COMMIT_PATTERN = re.compile(r"^[a-f0-9]{40}$", re.IGNORECASE)
SEASON_PATTERN = re.compile(r"^\d{4}-\d{2}$")


class FutureInformationError(ValueError):
    """Raised when historical evidence was unavailable at decision time."""


@dataclass(frozen=True)
class VaastavRevision:
    commit_sha: str
    season: str

    def __post_init__(self) -> None:
        if not COMMIT_PATTERN.fullmatch(self.commit_sha):
            raise ValueError("vaastav revision must be a 40-character commit SHA")
        if not SEASON_PATTERN.fullmatch(self.season):
            raise ValueError("season must use the YYYY-YY archive format")

    def gameweek_url(self, gameweek: int) -> str:
        # 2019/20 was suspended and resumed, running to gameweek 47.
        if isinstance(gameweek, bool) or not 1 <= gameweek <= 47:
            raise ValueError("gameweek must be between 1 and 47")
        return f"{self._season_root()}/gws/gw{gameweek}.csv"

    def players_url(self) -> str:
        return f"{self._season_root()}/players_raw.csv"

    def teams_url(self) -> str:
        return f"{self._season_root()}/teams.csv"

    def fixtures_url(self) -> str:
        return f"{self._season_root()}/fixtures.csv"

    def _season_root(self) -> str:
        return (
            "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/"
            f"{self.commit_sha}/data/{self.season}"
        )


@dataclass(frozen=True)
class HistoricalBatch:
    rows: tuple[dict[str, str], ...]
    excluded_fields: tuple[str, ...]
    snapshot: SourceSnapshot


def parse_gameweek_csv(
    raw_csv: bytes,
    *,
    revision: VaastavRevision,
    gameweek: int,
    fetched_at: datetime,
    data_available_at: datetime,
    prediction_cutoff: datetime,
) -> HistoricalBatch:
    _require_utc("fetched_at", fetched_at)
    _require_utc("data_available_at", data_available_at)
    _require_utc("prediction_cutoff", prediction_cutoff)
    if data_available_at > prediction_cutoff:
        raise FutureInformationError("historical data became available after the prediction cutoff")
    if data_available_at > fetched_at:
        raise FutureInformationError("historical data availability cannot follow fetch time")

    upstream_reference = revision.gameweek_url(gameweek)
    text = raw_csv.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None:
        raise ValueError("historical CSV must include a header")

    excluded_fields = tuple(field for field in reader.fieldnames if field.casefold() == "xp")
    rows: list[dict[str, str]] = []
    for row_number, row in enumerate(reader, start=2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"historical CSV row {row_number} does not match its header")
        rows.append(
            {
                field: value
                for field, value in row.items()
                if field.casefold() != "xp" and value is not None
            }
        )

    snapshot = SourceSnapshot(
        source="vaastav",
        fetched_at=fetched_at,
        data_available_at=data_available_at,
        content_hash=f"sha256:{hashlib.sha256(raw_csv).hexdigest()}",
        upstream_reference=upstream_reference,
    )
    return HistoricalBatch(
        rows=tuple(rows),
        excluded_fields=excluded_fields,
        snapshot=snapshot,
    )


def _require_utc(label: str, value: datetime) -> None:
    require_utc(value, label)
