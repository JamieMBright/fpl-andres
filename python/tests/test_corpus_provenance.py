"""Corpus provenance must match what was actually loaded.

Audit item #189. A backtest claim is only reproducible if someone can rebuild the
data it was measured over, and nothing recorded what that data was.

The commit SHA is the part that is genuinely missing: it was a workflow dispatch
input and was never written back to a committed file. `docs/CORPUS.md` leaves it
as a placeholder rather than guessing — a wrong SHA in a provenance document is
worse than a missing one, because the missing one prompts the recovery query and
the wrong one prompts a reproduction that quietly uses different data.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fpl_andres.cli.ingest_historical import SUPPORTED_SEASONS

_ROOT = Path(__file__).resolve().parents[2]
_CORPUS = _ROOT / "docs" / "CORPUS.md"
_VALIDATION = _ROOT / "apps" / "web" / "src" / "data" / "validation.json"


def _corpus() -> str:
    return _CORPUS.read_text(encoding="utf-8")


def _measured() -> dict[str, dict[str, int]]:
    payload = json.loads(_VALIDATION.read_text(encoding="utf-8"))
    return {str(season["season"]): season for season in payload["seasons"]}


@pytest.mark.parametrize("season", SUPPORTED_SEASONS)
def test_every_supported_season_appears_in_the_provenance(season: str) -> None:
    """Including the three with no expected-goals coverage. A season nobody
    documents is a season nobody knows is loaded."""
    assert season in _corpus()


@pytest.mark.parametrize("season", sorted(_measured()))
def test_the_documented_row_counts_are_the_measured_ones(season: str) -> None:
    measured = _measured()[season]
    text = _corpus()

    assert f"{measured['rows']:,}" in text, (
        f"CORPUS.md does not state {season}'s row count of {measured['rows']:,}"
    )
    assert f"{measured['elements']:,}" in text or str(measured["elements"]) in text


def test_the_shortened_season_is_explained_rather_than_left_odd() -> None:
    """2022-23 has 37 gameweeks. Unexplained, that looks like a failed ingest."""
    short = [s for s, m in _measured().items() if m["gameweeks"] < 38]

    assert short == ["2022-23"]
    assert "Queen Elizabeth II" in _corpus()
    assert "37 gameweeks" in _corpus()


def test_the_missing_commit_sha_is_flagged_rather_than_invented() -> None:
    """The one fact that would make the corpus reproducible, and the one nobody
    wrote down. Placeholders, not guesses."""
    text = _corpus()

    assert "_to be recovered_" in text
    assert not re.search(r"\b[0-9a-f]{40}\b", text), (
        "CORPUS.md contains a 40-character hex string; if that is a real SHA it "
        "should replace the placeholders, and if it is not it must not be there"
    )


def test_the_recovery_route_is_a_query_rather_than_an_archaeology_expedition() -> None:
    """The SHA is not lost: every ingested row cites a source_snapshots row, and
    that row's upstream_reference is the archive URL, which contains it."""
    text = _corpus()

    assert "source_snapshots" in text
    assert "upstream_reference" in text
    assert "split_part" in text


def test_the_archive_url_pattern_matches_the_adapter() -> None:
    """A documented URL that the code does not build is a documented URL that
    reproduces nothing."""
    adapter = (_ROOT / "python" / "fpl_andres" / "adapters" / "vaastav.py").read_text(
        encoding="utf-8"
    )
    text = _corpus()

    assert "raw.githubusercontent.com/vaastav/Fantasy-Premier-League" in adapter
    assert "raw.githubusercontent.com/vaastav/Fantasy-Premier-League" in text
    for endpoint in ("teams.csv", "players_raw.csv", "fixtures.csv"):
        assert endpoint in adapter
        assert endpoint in text


def test_the_provenance_says_the_sha_alone_is_not_enough() -> None:
    """The corpus is mutable by design, so a SHA names the archive state and not
    the corpus state. The fingerprint names the corpus state."""
    text = _corpus()

    assert "corpus_fingerprint" in text
    assert "mutable by design" in text


def test_the_row_total_agrees_between_the_two_documents() -> None:
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")

    assert "185,954" in readme
    assert "185,954" in _corpus()
