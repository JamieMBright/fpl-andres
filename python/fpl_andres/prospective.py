"""Freeze a model and its inputs before the outcomes it will be judged on."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

from fpl_andres.model_version import MODEL_VERSION

__all__ = [
    "FROZEN_PLANNING_ARTIFACTS",
    "PROSPECTIVE_SCHEMA_VERSION",
    "build_prospective_manifest",
]

PROSPECTIVE_SCHEMA_VERSION = 1
FROZEN_PLANNING_ARTIFACTS = (
    "apps/web/src/data/projections.json",
    "apps/web/src/data/projections-meta.json",
    "apps/web/src/data/season-inputs.json",
    "apps/web/src/data/opening-squad.json",
    "apps/web/src/data/season-plan.json",
)
PARAMETERS_PATH = "docs/PARAMETERS.md"


def build_prospective_manifest(
    root: Path,
    *,
    season: str,
    event: int,
    deadline: datetime,
    frozen_at: datetime,
    code_revision: str,
) -> dict[str, object]:
    if not re.fullmatch(r"[0-9a-f]{40}", code_revision):
        raise ValueError("code revision must be a forty-character lowercase Git SHA")
    if deadline.tzinfo is None or frozen_at.tzinfo is None:
        raise ValueError("deadline and freeze time must carry a timezone")
    if frozen_at >= deadline:
        raise ValueError("prospective evidence must be frozen before the deadline")
    if not 1 <= event <= 38:
        raise ValueError("event must be in the FPL gameweek range")

    parameter_path = root / PARAMETERS_PATH
    artifact_paths = {path: root / path for path in FROZEN_PLANNING_ARTIFACTS}
    missing = [
        str(path) for path in (parameter_path, *artifact_paths.values()) if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(f"prospective inputs are missing: {missing}")

    return {
        "schemaVersion": PROSPECTIVE_SCHEMA_VERSION,
        "season": season,
        "event": event,
        "deadline": deadline.isoformat(),
        "frozenAt": frozen_at.isoformat(),
        "modelVersion": MODEL_VERSION,
        "codeRevision": code_revision,
        "outcomesObserved": False,
        "evidenceLevel": "observed",
        "parameters": {
            "path": PARAMETERS_PATH,
            "sha256": _sha256(parameter_path),
        },
        "artifacts": {path: _sha256(file) for path, file in artifact_paths.items()},
    }


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
