"""The decision not to partition must keep checking itself.

Audit item #98 asked for a partitioning strategy for `element_gameweek_stats`.
The growth is real; the rate was never measured. Measured, it is 28,396 rows and
6.6 MB per season, reaching a million rows in 2061. Partitioning that would be
premature optimisation with real costs, so ADR 0005 declines and sets thresholds
instead.

A threshold in a document is a threshold nobody checks. These read the published
validation artifact — the same file the site serves, so it cannot disagree with
what was actually ingested — and fail when either threshold is crossed. The
decision then gets revisited because the suite went red, not because someone
remembered.

Production is never queried here; repository policy forbids inspecting
application rows through tooling. The artifact is the sanctioned view.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = _ROOT / "apps" / "web" / "src" / "data" / "validation.json"
_ADR = _ROOT / "docs" / "adr" / "0005-no-partitioning-for-the-history-corpus.md"

# ADR 0005. Crossing either sends the decision back for review.
MAX_TOTAL_ROWS = 2_000_000
MAX_ROWS_PER_SEASON = 100_000

# 24B tuple header, 16 int4, 4 int8, 8 numeric, timestamptz, bool, season, uuid.
ESTIMATED_ROW_BYTES = 244


def _seasons() -> list[dict[str, Any]]:
    report = json.loads(_VALIDATION.read_text(encoding="utf-8"))
    seasons = report["seasons"]
    assert seasons, "the validation artifact reports no seasons"
    return list(seasons)


def test_the_corpus_is_still_far_below_the_partitioning_threshold() -> None:
    total = sum(int(season["rows"]) for season in _seasons())
    assert total < MAX_TOTAL_ROWS, (
        f"element_gameweek_stats now holds {total:,} rows, past the "
        f"{MAX_TOTAL_ROWS:,} that ADR 0005 set as the point to reconsider "
        "partitioning. Re-measure and update the ADR."
    )


def test_no_single_season_grew_beyond_what_the_projection_assumed() -> None:
    """A rule change — squad size, or a fifth element type — would show up here
    long before the total did."""
    oversized = {
        str(season["season"]): int(season["rows"])
        for season in _seasons()
        if int(season["rows"]) > MAX_ROWS_PER_SEASON
    }
    assert oversized == {}, (
        f"these seasons exceed the {MAX_ROWS_PER_SEASON:,} rows ADR 0005 "
        f"projected from: {oversized}. The growth rate changed shape."
    )


def test_the_growth_rate_is_linear_not_compounding() -> None:
    """ADR 0005's projection assumes a constant. A season fixed at 380 matches
    and ~800 players cannot compound, and this fails if that stops being true."""
    counts = [int(season["rows"]) for season in _seasons()]
    if len(counts) < 2:
        pytest.skip("need at least two seasons to compare")
    largest, smallest = max(counts), min(counts)
    assert largest <= smallest * 1.5, (
        f"season sizes range {smallest:,} to {largest:,}, wider than the "
        "constant-growth assumption behind ADR 0005"
    )


def test_the_projected_table_size_stays_trivial() -> None:
    total = sum(int(season["rows"]) for season in _seasons())
    megabytes = total * ESTIMATED_ROW_BYTES / 1024 / 1024
    assert megabytes < 500, (
        f"the corpus is now roughly {megabytes:.0f} MB; ADR 0005 projected it "
        "would not reach 500 MB until 2101"
    )


def test_the_decision_is_written_down_with_its_numbers() -> None:
    """An ADR that declines to act is only useful if it shows the arithmetic."""
    text = _ADR.read_text(encoding="utf-8")
    assert "2,000,000" in text or "2 million" in text
    assert "28,396" in text, "the measured per-season rate should be stated"
    assert "113,582" in text, "the measured total should be stated"


def test_a_season_remains_individually_removable_without_partitions() -> None:
    """The operation partitioning would make cheap. `season` leads the primary
    key, so a single-season delete already uses an index."""
    sql = " ".join(
        (_ROOT / "supabase" / "migrations" / "20260801120000_history_corpus.sql")
        .read_text(encoding="utf-8")
        .lower()
        .split()
    )
    assert "primary key (season, gameweek, element_id" in sql


def test_the_access_paths_the_adr_relies_on_exist() -> None:
    """ADR 0005 argues a 113k-row table needs indexes, not partitions. It is
    only right if the indexes are actually there."""
    sql = " ".join(
        (_ROOT / "supabase" / "migrations" / "20260801170000_access_path_indexes.sql")
        .read_text(encoding="utf-8")
        .lower()
        .split()
    )
    assert "(season, gameweek, element_id)" in sql
    assert "(season, element_id, gameweek)" in sql
