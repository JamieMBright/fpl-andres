"""Published artifacts carry a schema version, and both readers agree on it.

The artifacts are written by two Python CLIs and imported by the
web app at build time. Nothing recorded which shape they were in, so a change to
a writer would have been picked up silently by the reader: a field quietly
absent, ``undefined`` where a number was expected, and a page that renders
wrongly rather than refusing.

The version constant is declared twice, once per language, because neither side
can import the other's. Two constants meant to agree and never compared will
eventually not, so they are compared here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fpl_andres.artifacts import (
    GW1_REVIEW_SCHEMA_VERSION,
    OPENING_SQUAD_SCHEMA_VERSION,
    PROJECTIONS_META_SCHEMA_VERSION,
    PROJECTIONS_SCHEMA_VERSION,
    SEASON_INPUTS_SCHEMA_VERSION,
    SEASON_PLAN_SCHEMA_VERSION,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "apps" / "web" / "src" / "data"
TS_VERSIONS = REPO_ROOT / "apps" / "web" / "src" / "state" / "artifact-version.ts"

ARTIFACTS = (
    ("projections.json", PROJECTIONS_SCHEMA_VERSION, "PROJECTIONS_SCHEMA_VERSION"),
    (
        "season-inputs.json",
        SEASON_INPUTS_SCHEMA_VERSION,
        "SEASON_INPUTS_SCHEMA_VERSION",
    ),
    (
        "projections-meta.json",
        PROJECTIONS_META_SCHEMA_VERSION,
        "PROJECTIONS_META_SCHEMA_VERSION",
    ),
    ("opening-squad.json", OPENING_SQUAD_SCHEMA_VERSION, "OPENING_SQUAD_SCHEMA_VERSION"),
    ("season-plan.json", SEASON_PLAN_SCHEMA_VERSION, "SEASON_PLAN_SCHEMA_VERSION"),
    ("gw1-review.json", GW1_REVIEW_SCHEMA_VERSION, "GW1_REVIEW_SCHEMA_VERSION"),
)


def _typescript_version(name: str) -> int:
    source = TS_VERSIONS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = (\d+);", source)
    assert match is not None, f"{name} is not declared in artifact-version.ts"
    return int(match.group(1))


@pytest.mark.parametrize(("filename", "version", "_constant"), ARTIFACTS)
def test_the_committed_artifact_declares_its_schema_version(
    filename: str, version: int, _constant: str
) -> None:
    document = json.loads((DATA / filename).read_text(encoding="utf-8"))
    assert document["schemaVersion"] == version


@pytest.mark.parametrize(("_filename", "version", "constant"), ARTIFACTS)
def test_python_and_typescript_agree_on_the_version(
    _filename: str, version: int, constant: str
) -> None:
    assert _typescript_version(constant) == version


@pytest.mark.parametrize(("filename", "_version", "_constant"), ARTIFACTS)
def test_the_version_is_the_first_key_so_it_is_visible_in_a_diff(
    filename: str, _version: int, _constant: str
) -> None:
    # A version buried after two hundred kilobytes of players is a version
    # nobody reads. First key means a stale artifact is visible at a glance.
    document = json.loads((DATA / filename).read_text(encoding="utf-8"))
    assert next(iter(document)) == "schemaVersion"


@pytest.mark.parametrize(("filename", "_version", "_constant"), ARTIFACTS)
def test_the_version_is_a_positive_integer_not_a_string(
    filename: str, _version: int, _constant: str
) -> None:
    # A string version compares wrongly against a number and the reader's
    # strict equality would reject a correct artifact.
    document = json.loads((DATA / filename).read_text(encoding="utf-8"))
    version = document["schemaVersion"]
    assert isinstance(version, int)
    assert not isinstance(version, bool)
    assert version >= 1


def test_every_publisher_stamps_the_artifact_it_writes() -> None:
    # A publisher that forgot the stamp would write an artifact the reader
    # refuses, which is the right failure but a late one. This catches it
    # without running either CLI.
    for module in (
        "publish_projections.py",
        "publish_opening_squad.py",
        "publish_season_inputs.py",
    ):
        source = (REPO_ROOT / "python" / "fpl_andres" / "cli" / module).read_text(encoding="utf-8")
        assert "schemaVersion" in source, f"{module} does not stamp its artifact"
        assert "SCHEMA_VERSION" in source, f"{module} hardcodes a version"


def test_the_readers_refuse_rather_than_degrade() -> None:
    # Degrading would mean rendering a squad from a document whose fields no
    # longer mean what the reader thinks, and every value on the page would
    # look plausible.
    source = TS_VERSIONS.read_text(encoding="utf-8")
    assert "throw new ArtifactVersionError" in source
