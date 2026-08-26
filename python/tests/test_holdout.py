"""Retrospective seasons are named honestly; prospective evidence is frozen."""

from __future__ import annotations

import hashlib
import inspect
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fpl_andres.cli import freeze_prospective, validate
from fpl_andres.holdout import SCORED_SEASONS
from fpl_andres.jsonio import read_json_file
from fpl_andres.prospective import (
    FROZEN_PLANNING_ARTIFACTS,
    PROSPECTIVE_SCHEMA_VERSION,
    build_prospective_manifest,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "prospective" / "gw1-2026-27.json"


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def test_every_scored_season_is_retrospective() -> None:
    assert SCORED_SEASONS == ("2022-23", "2023-24", "2024-25", "2025-26")
    assert '"holdout"' not in inspect.getsource(validate.main)


def test_the_pre_gw1_prospective_manifest_keeps_its_recorded_model() -> None:
    payload = read_json_file(MANIFEST)

    assert payload["schemaVersion"] == PROSPECTIVE_SCHEMA_VERSION
    assert payload["season"] == "2026-27"
    assert payload["event"] == 1
    assert re.fullmatch(r"[0-9a-f]{40}", payload["codeRevision"])
    source = subprocess.run(
        [
            "git",
            "show",
            f"{payload['codeRevision']}:python/fpl_andres/model_version.py",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    recorded = re.search(r'^MODEL_VERSION\s*=\s*"([^"]+)"', source, re.MULTILINE)
    assert recorded is not None
    assert payload["modelVersion"] == recorded.group(1)
    assert datetime.fromisoformat(payload["frozenAt"]) < datetime.fromisoformat(payload["deadline"])
    assert payload["outcomesObserved"] is False


def test_automatic_freeze_selects_the_first_unfinished_event(tmp_path: Path) -> None:
    deadlines = tmp_path / "deadlines.json"
    deadlines.write_text(
        '{"deadlines":['
        '{"event":1,"deadline":"2026-08-21T17:30:00Z","finished":true},'
        '{"event":2,"deadline":"2026-08-28T17:30:00Z","finished":false}'
        "]}",
        encoding="utf-8",
    )

    event, deadline = freeze_prospective._event_and_deadline(deadlines, None, None)

    assert event == 2
    assert deadline == datetime(2026, 8, 28, 17, 30, tzinfo=UTC)


def test_explicit_freeze_refuses_a_finished_event(tmp_path: Path) -> None:
    deadlines = tmp_path / "deadlines.json"
    deadlines.write_text(
        '{"deadlines":[{"event":1,"deadline":"2026-08-21T17:30:00Z","finished":true}]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="already finished"):
        freeze_prospective._event_and_deadline(deadlines, 1, None)


def test_an_existing_prospective_manifest_is_never_rewritten(tmp_path: Path) -> None:
    deadlines = tmp_path / "deadlines.json"
    deadlines.write_text(
        '{"deadlines":[{"event":2,"deadline":"2026-08-28T17:30:00Z","finished":false}]}',
        encoding="utf-8",
    )
    output = tmp_path / "gw2-2026-27.json"
    output.write_text("frozen bytes", encoding="utf-8")

    assert (
        freeze_prospective.main(
            [
                "--deadlines",
                str(deadlines),
                "--frozen-at",
                "2026-08-26T12:00:00Z",
                "--code-revision",
                "a" * 40,
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert output.read_text(encoding="utf-8") == "frozen bytes"


def test_the_manifest_hashes_every_input_that_can_move_the_gw1_plan() -> None:
    payload = read_json_file(MANIFEST)

    assert payload["parameters"]["path"] == "docs/PARAMETERS.md"
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", payload["parameters"]["sha256"])
    assert set(payload["artifacts"]) == set(FROZEN_PLANNING_ARTIFACTS)
    assert all(
        re.fullmatch(r"sha256:[0-9a-f]{64}", digest) for digest in payload["artifacts"].values()
    )


def test_the_manifest_builder_hashes_the_files_it_was_given(tmp_path: Path) -> None:
    parameters = tmp_path / "docs" / "PARAMETERS.md"
    parameters.parent.mkdir(parents=True)
    parameters.write_text("parameters", encoding="utf-8")
    for index, relative in enumerate(FROZEN_PLANNING_ARTIFACTS):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"artifact {index}", encoding="utf-8")
    frozen_at = datetime(2026, 8, 18, tzinfo=UTC)

    payload = build_prospective_manifest(
        tmp_path,
        season="2026-27",
        event=1,
        deadline=frozen_at + timedelta(days=3),
        frozen_at=frozen_at,
        code_revision="a" * 40,
    )

    assert payload["parameters"]["sha256"] == _sha256(parameters)
    assert payload["artifacts"] == {
        relative: _sha256(tmp_path / relative) for relative in FROZEN_PLANNING_ARTIFACTS
    }
