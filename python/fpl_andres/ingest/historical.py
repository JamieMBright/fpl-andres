"""Historical season ingest from the pinned vaastav archive.

The archive is fetched at an exact commit SHA, the raw bytes are hashed and
recorded as an immutable ``source_snapshots`` row, and only then are normalised
rows written. Every persisted row points back at the snapshot it came from, so
any table state is reconstructible from raw evidence.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from fpl_andres.adapters.vaastav import VaastavRevision
from fpl_andres.ingest.normalise import (
    normalise_fixtures,
    normalise_gameweek_stats,
    normalise_players,
    normalise_teams,
)
from fpl_andres.persistence.supabase import SupabaseRestClient

_SOURCE = "vaastav"


class ArchiveFetchError(RuntimeError):
    """Raised when the pinned archive cannot be retrieved."""


class ArchiveFileNotPublished(ArchiveFetchError):
    """Raised when the archive simply does not carry a file.

    Distinct from a transport failure: seasons differ in length, so a missing
    gameweek file is expected, whereas a missing teams file is fatal.

    Carries the season, gameweek and url so a partial ingest is diagnosable from
    the log alone. The url on its own left the reader deriving which gameweek of
    which season had gone missing from a path.
    """

    def __init__(self, url: str, *, season: str | None = None, gameweek: int | None = None) -> None:
        where = f"{season or 'unknown season'}"
        if gameweek is not None:
            where += f" gameweek {gameweek}"
        super().__init__(f"archive file not published for {where}: {url}")
        self.url = url
        self.season = season
        self.gameweek = gameweek


@dataclass(frozen=True)
class FetchedFile:
    url: str
    content: bytes
    fetched_at: datetime

    @property
    def content_hash(self) -> str:
        return f"sha256:{hashlib.sha256(self.content).hexdigest()}"


@dataclass(frozen=True)
class SeasonIngestResult:
    season: str
    teams: int
    elements: int
    fixtures: int
    gameweeks: dict[int, int]
    # Requested gameweeks the archive does not publish. Reported rather than
    # skipped in silence: a season legitimately shorter than the request looks
    # identical to an archive that has stopped publishing halfway.
    unavailable_gameweeks: tuple[int, ...] = ()

    @property
    def total_stat_rows(self) -> int:
        return sum(self.gameweeks.values())


class ArchiveFetcher:
    """Fetches pinned archive files over HTTPS."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def fetch(
        self, url: str, *, season: str | None = None, gameweek: int | None = None
    ) -> FetchedFile:
        response = self._client.get(url)
        if response.status_code == 404:
            raise ArchiveFileNotPublished(url, season=season, gameweek=gameweek)
        if response.status_code >= 400:
            raise ArchiveFetchError(f"archive fetch failed with {response.status_code}: {url}")
        return FetchedFile(url=url, content=response.content, fetched_at=datetime.now(UTC))


class HistoricalIngest:
    """Ingests one season of the archive into the history corpus."""

    def __init__(
        self,
        *,
        client: SupabaseRestClient,
        fetcher: ArchiveFetcher,
        storage_prefix: str = "vaastav",
    ) -> None:
        self._client = client
        self._fetcher = fetcher
        self._storage_prefix = storage_prefix

    def ingest_season(
        self,
        revision: VaastavRevision,
        *,
        gameweeks: Sequence[int],
        data_available_at: datetime,
    ) -> SeasonIngestResult:
        season = revision.season

        # Every fetch happens before every write. PostgREST has no transaction
        # spanning requests, so a season cannot be written atomically — but the
        # failure that actually happens is a dropped connection partway through
        # thirty-eight downloads, and that used to leave teams and elements
        # written with no stats. Now it writes nothing.
        #
        # Fetching first also makes a re-run cheap rather than merely possible:
        # every write below is an upsert, so a partial write is repaired by
        # running the same command again.
        teams_file = self._fetcher.fetch(revision.teams_url(), season=season)
        players_file = self._fetcher.fetch(revision.players_url(), season=season)
        fixtures_file = self._fetcher.fetch(revision.fixtures_url(), season=season)

        stats_files: list[tuple[int, FetchedFile]] = []
        unavailable: list[int] = []
        for gameweek in gameweeks:
            try:
                stats_files.append(
                    (
                        gameweek,
                        self._fetcher.fetch(
                            revision.gameweek_url(gameweek),
                            season=season,
                            gameweek=gameweek,
                        ),
                    )
                )
            except ArchiveFileNotPublished:
                # Seasons differ in length; 2019/20 ran to 47, most run to 38.
                unavailable.append(gameweek)

        self._client.insert_ignoring_duplicates(
            "seasons", [{"season": season}], on_conflict="season"
        )

        teams_snapshot = self._record_snapshot(teams_file, data_available_at)
        teams = normalise_teams(
            teams_file.content, season=season, source_snapshot_id=teams_snapshot
        )
        self._client.upsert("teams", teams, on_conflict="season,team_id")

        players_snapshot = self._record_snapshot(players_file, data_available_at)
        elements = normalise_players(
            players_file.content, season=season, source_snapshot_id=players_snapshot
        )
        self._client.upsert("elements", elements, on_conflict="season,element_id")

        fixtures_snapshot = self._record_snapshot(fixtures_file, data_available_at)
        fixtures = normalise_fixtures(
            fixtures_file.content, season=season, source_snapshot_id=fixtures_snapshot
        )
        self._client.upsert("fixtures", fixtures, on_conflict="season,fixture_id")

        element_codes = {row["element_id"]: row["code"] for row in elements}

        written: dict[int, int] = {}
        for gameweek, stats_file in stats_files:
            stats_snapshot = self._record_snapshot(stats_file, data_available_at)
            stats = normalise_gameweek_stats(
                stats_file.content,
                season=season,
                gameweek=gameweek,
                element_codes=element_codes,
                source_snapshot_id=stats_snapshot,
            )
            self._client.upsert(
                "element_gameweek_stats",
                stats,
                on_conflict="season,gameweek,element_id,fixture_id",
            )
            written[gameweek] = len(stats)

        return SeasonIngestResult(
            season=season,
            teams=len(teams),
            elements=len(elements),
            fixtures=len(fixtures),
            gameweeks=written,
            unavailable_gameweeks=tuple(unavailable),
        )

    def _record_snapshot(self, file: FetchedFile, data_available_at: datetime) -> str:
        """Insert the provenance row and return its id, reusing an existing hash."""
        payload: dict[str, Any] = {
            "source": _SOURCE,
            "upstream_reference": file.url,
            "fetched_at": file.fetched_at.isoformat(),
            "data_available_at": data_available_at.isoformat(),
            "content_hash": file.content_hash,
            "storage_path": f"{self._storage_prefix}/{file.content_hash.removeprefix('sha256:')}",
            "compressed_bytes": max(len(file.content), 1),
            "metadata": {"bytes": len(file.content)},
        }
        created = self._client.insert(
            "source_snapshots",
            [payload],
            resolution="ignore-duplicates",
            on_conflict="source,content_hash",
            returning=True,
        )
        if created:
            return str(created[0]["id"])

        existing = self._client.select(
            "source_snapshots",
            columns="id",
            filters={
                "source": f"eq.{_SOURCE}",
                "content_hash": f"eq.{file.content_hash}",
            },
            limit=1,
        )
        if not existing:
            raise ArchiveFetchError(f"snapshot for {file.url} was neither created nor retrievable")
        return str(existing[0]["id"])


__all__ = [
    "ArchiveFetchError",
    "ArchiveFetcher",
    "ArchiveFileNotPublished",
    "FetchedFile",
    "HistoricalIngest",
    "SeasonIngestResult",
]
