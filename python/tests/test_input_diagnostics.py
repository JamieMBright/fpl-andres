"""Malformed input must say what was malformed.

- **#55** Only `cli/sweep_managers.py` guarded `ValueError` from a JSON parse.
  The other six sites produced a raw `JSONDecodeError` naming a character offset
  — "Expecting value: line 1 column 1 (char 0)" — and nothing about which file
  or endpoint had failed. The offset is the least useful part of that message;
  the path is the useful part, and it was the part missing.

- **#54** `_require` checked column *presence*. `csv.DictReader` keys by name,
  so a repeated column silently keeps only the last occurrence: an archive that
  published `total_points` twice would have ingested one of them with nothing to
  say which. Column *order* is deliberately still unchecked, because reading by
  name makes a reordered header harmless.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpl_andres.ingest.normalise import ColumnMappingError, normalise_gameweek_stats
from fpl_andres.jsonio import (
    MalformedJsonError,
    parse_json,
    read_json_file,
    read_json_lines,
)

SNAPSHOT = "00000000-0000-4000-8000-000000000000"


def test_a_malformed_payload_names_its_endpoint() -> None:
    with pytest.raises(MalformedJsonError, match=r"https://fantasy\.example/api"):
        parse_json("<html>502 Bad Gateway</html>", source="https://fantasy.example/api")


def test_a_malformed_file_names_its_path(tmp_path: Path) -> None:
    """A truncated checkpoint is the realistic case: the process died mid-write
    and the resume path is the one that has to explain it."""
    checkpoint = tmp_path / "sweep-progress.json"
    checkpoint.write_text('{"next_id": 12345, "with_his', encoding="utf-8")

    with pytest.raises(MalformedJsonError, match=r"sweep-progress\.json"):
        read_json_file(checkpoint)


def test_a_well_formed_file_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps({"season": "2025-26", "rows": 3}), encoding="utf-8")

    assert read_json_file(path) == {"season": "2025-26", "rows": 3}


def test_an_unreadable_path_is_reported_as_such(tmp_path: Path) -> None:
    with pytest.raises(MalformedJsonError, match="could not be read"):
        read_json_file(tmp_path / "does-not-exist.json")


def test_one_bad_line_in_a_sweep_output_names_its_line_number(tmp_path: Path) -> None:
    """Otherwise a single bad line in 2,000 is found by bisection."""
    path = tmp_path / "sweep.jsonl"
    path.write_text('{"entry": 1}\n{"entry": 2}\n{"entry": 3\n{"entry": 4}\n', encoding="utf-8")

    with pytest.raises(MalformedJsonError, match="line 3"):
        read_json_lines(path)


def test_blank_lines_in_newline_delimited_json_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "sweep.jsonl"
    path.write_text('{"entry": 1}\n\n   \n{"entry": 2}\n', encoding="utf-8")

    assert read_json_lines(path) == [{"entry": 1}, {"entry": 2}]


def test_no_cli_module_parses_json_without_naming_its_source() -> None:
    """Fails if an eighth unguarded parse site appears."""
    cli = Path(__file__).resolve().parents[1] / "fpl_andres" / "cli"
    offenders = sorted(
        path.name for path in cli.glob("*.py") if "json.loads(" in path.read_text(encoding="utf-8")
    )
    assert offenders == [], (
        "these call json.loads directly; use fpl_andres.jsonio so the failure "
        f"names its source: {offenders}"
    )


_HEADER = (
    "element,fixture,round,minutes,total_points,goals_scored,assists,clean_sheets,"
    "goals_conceded,own_goals,penalties_saved,penalties_missed,yellow_cards,"
    "red_cards,saves,bonus,bps,value,was_home"
)
_ROW = "1,10,1,90,8,1,0,1,0,0,0,0,0,0,0,2,30,75,True"


def test_a_well_formed_gameweek_file_still_parses() -> None:
    rows = normalise_gameweek_stats(
        f"{_HEADER}\n{_ROW}\n".encode(),
        season="2025-26",
        gameweek=1,
        source_snapshot_id=SNAPSHOT,
        element_codes={1: 100_001},
    )

    assert len(rows) == 1
    assert rows[0]["total_points"] == 8


def test_a_repeated_column_is_refused_rather_than_silently_halved() -> None:
    """#54's real danger. DictReader keeps the last occurrence, so the corpus
    would be wrong in a way no later check could detect."""
    doubled = f"{_HEADER},total_points\n{_ROW},999\n".encode()

    with pytest.raises(ColumnMappingError, match="repeats column"):
        normalise_gameweek_stats(
            doubled,
            season="2025-26",
            gameweek=1,
            source_snapshot_id=SNAPSHOT,
            element_codes={1: 100_001},
        )


def test_an_unnamed_column_is_refused() -> None:
    with pytest.raises(ColumnMappingError, match="unnamed column"):
        normalise_gameweek_stats(
            f"{_HEADER},\n{_ROW},x\n".encode(),
            season="2025-26",
            gameweek=1,
            source_snapshot_id=SNAPSHOT,
            element_codes={1: 100_001},
        )


def test_a_reordered_header_is_deliberately_accepted() -> None:
    """Reading by name makes order irrelevant, so refusing a reorder would break
    ingestion for a change that cannot affect the data."""
    columns = _HEADER.split(",")
    values = _ROW.split(",")
    order = list(reversed(range(len(columns))))
    reordered_header = ",".join(columns[i] for i in order)
    reordered_row = ",".join(values[i] for i in order)

    rows = normalise_gameweek_stats(
        f"{reordered_header}\n{reordered_row}\n".encode(),
        season="2025-26",
        gameweek=1,
        source_snapshot_id=SNAPSHOT,
        element_codes={1: 100_001},
    )

    assert rows[0]["total_points"] == 8
    assert rows[0]["minutes"] == 90
