"""Retrospective seasons are named honestly; prospective evidence is frozen."""

from __future__ import annotations

import hashlib
import inspect
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fpl_andres.cli import validate
from fpl_andres.holdout import SCORED_SEASONS
from fpl_andres.jsonio import read_json_file
from fpl_andres.model_version import MODEL_VERSION
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


def test_the_pre_gw1_prospective_manifest_freezes_the_live_model() -> None:
    payload = read_json_file(MANIFEST)

    assert payload["schemaVersion"] == PROSPECTIVE_SCHEMA_VERSION
    assert payload["season"] == "2026-27"
    assert payload["event"] == 1
    assert payload["modelVersion"] == MODEL_VERSION
    assert re.fullmatch(r"[0-9a-f]{40}", payload["codeRevision"])
    assert datetime.fromisoformat(payload["frozenAt"]) < datetime.fromisoformat(payload["deadline"])
    assert payload["outcomesObserved"] is False


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
