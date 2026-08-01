"""Timeouts in one place, and an ingest that says what it skipped.

- **#46** Six timeouts across six modules — 20s, 60s, 60s, 20s, 10s, 30s — with
  no way to see them together and no reason attached to any. They remain
  different, because one number would be wrong for every caller: a bootstrap
  fetch that has not answered in twenty seconds is not coming, while a season
  archive is tens of megabytes. What was missing was one place to compare them.

- **#52 / #53** A gameweek the archive does not publish was skipped with
  `continue` and no record. A season legitimately shorter than the request then
  looked identical to an archive that had stopped publishing halfway through,
  and `ArchiveFileNotPublished` carried only a url, leaving the reader to derive
  which gameweek of which season had gone missing from a path.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import httpx
import pytest

from fpl_andres import timeouts
from fpl_andres.ingest.historical import (
    ArchiveFetcher,
    ArchiveFileNotPublished,
    FetchedFile,
)

_PACKAGE = Path(__file__).resolve().parents[1] / "fpl_andres"


def test_every_timeout_has_a_stated_reason() -> None:
    """A number with no comment is a number nobody can safely change."""
    source = (_PACKAGE / "timeouts.py").read_text(encoding="utf-8")
    for name in ("CONNECT", "FPL_API", "SUPABASE_REST", "ARCHIVE_DOWNLOAD", "SUBPROCESS"):
        before = source.split(f"{name} =")[0]
        assert before.rstrip().endswith((".", '"""')), f"{name} has no explanation above it"


def test_the_budgets_are_ordered_by_the_work_they_cover() -> None:
    """Connect is the shortest; an archive download is the longest. If this
    inverts, one of them was changed without thinking about the others, which is
    exactly what having six scattered constants allowed."""
    assert timeouts.CONNECT < timeouts.SUBPROCESS < timeouts.FPL_API
    assert timeouts.FPL_API < timeouts.SUPABASE_REST < timeouts.ARCHIVE_DOWNLOAD


def test_no_module_hardcodes_a_network_timeout() -> None:
    """Fails if a seventh scattered constant appears.

    Matches a module-level name as well as a literal: the first version required
    a digit after `timeout=`, and `cli/ingest_ownership.py` kept its own
    `_TIMEOUT = 60.0` behind that gap for a whole commit.
    """
    literal = re.compile(r"timeout\s*=\s*(?:httpx\.Timeout\()?\d")
    named = re.compile(r"^_?TIMEOUT\w*\s*[:=]", re.MULTILINE)
    offenders = sorted(
        path.relative_to(_PACKAGE).as_posix()
        for path in _PACKAGE.rglob("*.py")
        if path.name != "timeouts.py"
        and (literal.search(text := path.read_text(encoding="utf-8")) or named.search(text))
    )
    assert offenders == [], "these set a timeout outside fpl_andres.timeouts: " + ", ".join(
        offenders
    )


def test_the_client_helper_carries_the_shared_connect_budget() -> None:
    """Failing to open a socket is a different failure from a slow response, so
    waiting a minute to discover DNS is broken helps nobody."""
    timeout = timeouts.client_timeout(timeouts.FPL_API)

    assert timeout.connect == timeouts.CONNECT
    assert timeout.read == timeouts.FPL_API


class _NotFound(httpx.Client):
    def get(self, url: object, **kwargs: object) -> httpx.Response:  # type: ignore[override]
        return httpx.Response(404, request=httpx.Request("GET", str(url)))


def test_a_missing_archive_file_names_the_season_and_gameweek() -> None:
    """#53. The url alone left the reader parsing a path to work out what had
    failed, which is exactly the work a log line should have done."""
    fetcher = ArchiveFetcher(_NotFound())

    with pytest.raises(ArchiveFileNotPublished) as caught:
        fetcher.fetch("https://example.invalid/gw31.csv", season="2019-20", gameweek=31)

    error = caught.value
    assert error.season == "2019-20"
    assert error.gameweek == 31
    assert error.url == "https://example.invalid/gw31.csv"
    assert "2019-20 gameweek 31" in str(error)


def test_a_missing_file_without_a_gameweek_still_reads_sensibly() -> None:
    """The teams and fixtures files have no gameweek, and a missing one there is
    fatal rather than expected."""
    fetcher = ArchiveFetcher(_NotFound())

    with pytest.raises(ArchiveFileNotPublished, match="2019-20: "):
        fetcher.fetch("https://example.invalid/teams.csv", season="2019-20")


def test_the_ingest_result_reports_gameweeks_the_archive_does_not_publish() -> None:
    """#52. A season shorter than the request and an archive that stopped
    publishing halfway are the same silence without this."""
    from fpl_andres.ingest.historical import SeasonIngestResult

    result = SeasonIngestResult(
        season="2019-20",
        teams=20,
        elements=700,
        fixtures=380,
        gameweeks={1: 500, 2: 500},
        unavailable_gameweeks=(39, 40),
    )

    assert result.unavailable_gameweeks == (39, 40)
    assert result.total_stat_rows == 1000


def test_an_ingest_with_nothing_missing_reports_nothing_missing() -> None:
    from fpl_andres.ingest.historical import SeasonIngestResult

    result = SeasonIngestResult(
        season="2024-25", teams=20, elements=800, fixtures=380, gameweeks={1: 500}
    )

    assert result.unavailable_gameweeks == ()


def test_the_cli_prints_the_skipped_gameweeks() -> None:
    """An unreported skip is only useful if it reaches a log."""
    source = (_PACKAGE / "cli" / "ingest_historical.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert "unavailable_gameweeks" in source
    assert "not published" in source
    assert any(isinstance(node, ast.JoinedStr) for node in ast.walk(tree))


def test_a_fetched_file_still_hashes_its_content() -> None:
    """The context added to the exception must not have disturbed the happy
    path, which is what provenance depends on."""
    file = FetchedFile(
        url="https://example.invalid/gw1.csv",
        content=b"a,b\n1,2\n",
        fetched_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )

    assert file.content_hash.startswith("sha256:")
    assert len(file.content_hash) == len("sha256:") + 64
