"""The catalogue is append-only, so reading it has to survive a repeated row.

`sweep_managers` opens `managers.jsonl` in append mode and advances its
checkpoint one block at a time. A run killed after a block was written but
before its checkpoint was saved re-sweeps that block on resume and appends the
same managers a second time. That has happened: the shipped catalogue holds
16,426 rows for 15,959 managers.

Nothing downstream notices, which is the danger. A duplicated row is ranked
twice, so one manager takes two of the five hundred places and the five
hundredth is pushed out — a cohort that quietly holds 497 people while
reporting 500.
"""

from __future__ import annotations

import json
from pathlib import Path

from fpl_andres.cli.publish_fpl500 import read_catalogue


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _manager(entry_id: int, points: int = 2600) -> dict[str, object]:
    return {
        "entryId": entry_id,
        "seasons": [
            {"season": "2023/24", "points": points, "rank": 500},
            {"season": "2024/25", "points": points, "rank": 400},
        ],
    }


def test_a_manager_appended_twice_is_read_once(tmp_path: Path) -> None:
    catalogue = tmp_path / "managers.jsonl"
    _write(catalogue, [_manager(11), _manager(22), _manager(11)])

    managers = read_catalogue(catalogue)

    assert [row.entry_id for row in managers] == [11, 22]


def test_the_first_copy_of_a_repeated_row_is_the_one_kept(tmp_path: Path) -> None:
    """Order is the sweep order, and it is what the ranking's tie-breaks see."""
    catalogue = tmp_path / "managers.jsonl"
    _write(catalogue, [_manager(11, points=2600), _manager(22), _manager(11, points=1)])

    managers = read_catalogue(catalogue)

    assert len(managers) == 2
    held = next(row for row in managers if row.entry_id == 11)
    assert [season.points for season in held.seasons] == [2600, 2600]


def test_distinct_managers_are_all_kept(tmp_path: Path) -> None:
    catalogue = tmp_path / "managers.jsonl"
    _write(catalogue, [_manager(11), _manager(22), _manager(33)])

    assert [row.entry_id for row in read_catalogue(catalogue)] == [11, 22, 33]
