"""Every fixture records where it came from and what it is for.

Audit item #160. A fixture is a claim about what upstream sends. Nothing
recorded where these came from, when, or what they are supposed to prove, so a
fixture that had drifted away from reality looked exactly like one that had
not -- and a test passing against a stale fixture is worse than no test,
because it reports confidence it has not earned.

The manifest is only worth having if it cannot drift from the data. The digest
is what enforces that: editing a fixture fails this file until its provenance
is updated too.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MANIFEST_PATH = FIXTURES / "MANIFEST.json"


def _manifest() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entries: dict[str, Any] = document["fixtures"]
    return entries


def _fixture_files() -> list[Path]:
    return sorted(path for path in FIXTURES.rglob("*.json") if path != MANIFEST_PATH)


def _relative(path: Path) -> str:
    return path.relative_to(FIXTURES).as_posix()


def _canonical_digest(path: Path) -> str:
    # Over the canonical JSON, not the file bytes. Line endings differ between
    # a Windows working tree and a Linux runner, and a formatter may reflow the
    # file; neither changes what the fixture asserts. A byte hash would fail
    # for both and teach people to regenerate it without reading why.
    document = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


NAMES = [_relative(path) for path in _fixture_files()]


def test_there_is_at_least_one_fixture_to_check() -> None:
    # Otherwise every parametrised test below passes by describing nothing.
    assert NAMES


def test_every_fixture_is_declared() -> None:
    assert sorted(NAMES) == sorted(_manifest())


def test_the_manifest_declares_nothing_that_is_missing() -> None:
    # A declared fixture that no longer exists reads as coverage that is not
    # there, and the entry would survive the file being deleted.
    for name in _manifest():
        assert (FIXTURES / name).is_file(), f"{name} is declared but absent"


@pytest.mark.parametrize("name", NAMES)
def test_the_digest_matches_the_data(name: str) -> None:
    assert _canonical_digest(FIXTURES / name) == _manifest()[name]["digest"], (
        f"{name} changed. Update its entry in MANIFEST.json, including why."
    )


@pytest.mark.parametrize("name", NAMES)
def test_each_fixture_records_its_source_and_capture(name: str) -> None:
    entry = _manifest()[name]
    assert entry["source"]
    captured = datetime.fromisoformat(entry["captured_at"].replace("Z", "+00:00"))
    assert captured.tzinfo is not None, "a capture time without a zone is not a time"
    assert captured <= datetime.now(UTC)


@pytest.mark.parametrize("name", NAMES)
def test_each_fixture_says_what_it_proves(name: str) -> None:
    # The field that stops a fixture outliving its reason. A fixture nobody can
    # say the purpose of is one nobody will delete when it stops having one.
    proves = _manifest()[name]["proves"]
    assert proves and all(line.strip() for line in proves)


@pytest.mark.parametrize("name", NAMES)
def test_each_fixture_declares_a_schema_version(name: str) -> None:
    version = _manifest()[name]["schema_version"]
    assert isinstance(version, int)
    assert not isinstance(version, bool)
    assert version >= 1


@pytest.mark.parametrize("name", NAMES)
def test_staleness_is_either_pinned_with_a_reason_or_dated(name: str) -> None:
    entry = _manifest()[name]
    staleness = entry["staleness"]
    if staleness == "pinned":
        reason = entry["pinned_because"]
        assert reason and all(line.strip() for line in reason), (
            f"{name} is pinned with no reason, which is the same as unexamined"
        )
        return
    review_by = datetime.fromisoformat(f"{staleness}T00:00:00+00:00")
    assert review_by >= datetime.now(UTC), (
        f"{name} is past its revalidation date; recapture it or pin it with a reason"
    )


def test_the_live_bootstrap_is_checked_against_upstream_rather_than_a_date() -> None:
    # The bootstrap fixture is pinned on the grounds that drift is caught by
    # asking FPL rather than by asking a calendar. That claim is only true
    # while the workflow exists and runs on a schedule.
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "live-contracts.yml"
    assert workflow.is_file()
    text = workflow.read_text(encoding="utf-8")
    assert "schedule:" in text
    assert "cron:" in text


def test_the_entry_fixture_still_describes_the_pre_season_state() -> None:
    # Its whole reason for existing: current_event is null and there is no
    # picks endpoint yet, so the engine must answer "no processed event"
    # rather than treat the manager as having an empty squad. A fixture
    # edited to carry a current event would silently stop testing that.
    entry = json.loads((FIXTURES / "fpl" / "entry_preseason.json").read_text(encoding="utf-8"))
    assert entry["current_event"] is None
    assert entry["last_deadline_bank"] is None
    assert entry["last_deadline_value"] is None


def test_the_entry_fixture_names_nobody_real() -> None:
    # Capturing this endpoint means capturing somebody. The manifest claims the
    # identifying fields were replaced; this is that claim, checked.
    entry = json.loads((FIXTURES / "fpl" / "entry_preseason.json").read_text(encoding="utf-8"))
    assert entry["player_first_name"] == "Private"
    assert entry["player_last_name"] == "Manager"
