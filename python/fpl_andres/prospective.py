"""Freeze a model and its inputs before the outcomes it will be judged on."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from fpl_andres.model_version import MODEL_VERSION

__all__ = [
    "CORRECTION_SCHEMA_VERSION",
    "FROZEN_PLANNING_ARTIFACTS",
    "PROSPECTIVE_SCHEMA_VERSION",
    "build_correction_manifest",
    "build_prospective_manifest",
]

CORRECTION_SCHEMA_VERSION = 1
PROSPECTIVE_SCHEMA_VERSION = 1
FROZEN_PLANNING_ARTIFACTS = (
    "apps/web/src/data/projections.json",
    "apps/web/src/data/projections-meta.json",
    "apps/web/src/data/season-inputs.json",
    "apps/web/src/data/opening-squad.json",
    "apps/web/src/data/season-plan.json",
)
PARAMETERS_PATH = "docs/PARAMETERS.md"


def build_correction_manifest(
    canonical: Mapping[str, Any],
    *,
    manifest_revision: str,
) -> dict[str, object]:
    """Point at the original pre-deadline manifest without rewriting history."""
    if not re.fullmatch(r"[0-9a-f]{40}", manifest_revision):
        raise ValueError("manifest revision must be a forty-character lowercase Git SHA")
    artifact_revision = canonical.get("codeRevision")
    if not isinstance(artifact_revision, str) or not re.fullmatch(
        r"[0-9a-f]{40}", artifact_revision
    ):
        raise ValueError("canonical manifest must name a forty-character artifact revision")
    if canonical.get("season") != "2026-27" or canonical.get("event") != 1:
        raise ValueError("the correction source must describe 2026-27 gameweek 1")
    if canonical.get("outcomesObserved") is not False:
        raise ValueError("the correction source must be prospective evidence")
    artifacts = canonical.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(FROZEN_PLANNING_ARTIFACTS):
        raise ValueError("canonical manifest must hash every frozen planning artifact")
    if not all(
        isinstance(digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
        for digest in artifacts.values()
    ):
        raise ValueError("canonical artifact hashes must be SHA-256 digests")

    return {
        "schemaVersion": CORRECTION_SCHEMA_VERSION,
        "season": "2026-27",
        "event": 1,
        "supersedes": "data/prospective/gw1-2026-27.json",
        "correctionReason": (
            "The original path was later rewritten with a post-deadline freeze and the "
            "gameweek 2 deadline. This companion preserves the original pre-deadline record."
        ),
        "canonicalManifestRevision": manifest_revision,
        "canonicalArtifactRevision": manifest_revision,
        "recordedCodeRevision": artifact_revision,
        "canonicalModelVersion": canonical.get("modelVersion"),
        "canonicalDeadline": canonical.get("deadline"),
        "canonicalFrozenAt": canonical.get("frozenAt"),
        "outcomesObserved": False,
        "evidenceLevel": canonical.get("evidenceLevel"),
        "parameters": canonical.get("parameters"),
        "artifacts": dict(artifacts),
    }


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
