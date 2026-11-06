"""Every suppressed advisory has a live, checkable justification.

``package.json`` carries ``pnpm.auditConfig.ignoreGhsas``. An
entry there silences a real finding, and a silence with no reason attached
becomes permanent by inertia.

The document is not the point; the checking is. A justification that cannot
become false is not a justification, and one that can become false silently is
worse than none. These tests hold the document and the suppression list to each
other and refuse an expired review.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_JSON = REPO_ROOT / "package.json"
DOCUMENT = REPO_ROOT / "SECURITY.md"


def suppressed_ghsas() -> list[str]:
    manifest = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    audit_config = manifest.get("pnpm", {}).get("auditConfig", {})
    ids: list[str] = audit_config.get("ignoreGhsas", [])
    return ids


def documented_ghsas() -> list[str]:
    text = DOCUMENT.read_text(encoding="utf-8")
    return re.findall(r"^### (GHSA-[0-9a-z-]+)$", text, flags=re.MULTILINE)


def _section(ghsa: str) -> str:
    text = DOCUMENT.read_text(encoding="utf-8")
    match = re.search(rf"^### {re.escape(ghsa)}$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert match is not None, f"{ghsa} has no section"
    return match.group(1)


def _field(ghsa: str, label: str) -> str:
    match = re.search(rf"\|\s*{label}\s*\|\s*([^|]+?)\s*\|", _section(ghsa))
    assert match is not None, f"{ghsa} does not record '{label}'"
    return match.group(1)


def test_every_suppression_is_documented() -> None:
    assert sorted(suppressed_ghsas()) == sorted(documented_ghsas())


def test_the_document_lists_nothing_that_is_no_longer_suppressed() -> None:
    # A stale section reads as a live suppression and would be trusted as one.
    assert set(documented_ghsas()) <= set(suppressed_ghsas())


@pytest.mark.parametrize("ghsa", suppressed_ghsas())
def test_each_suppression_records_when_it_was_assessed(ghsa: str) -> None:
    assessed = datetime.strptime(_field(ghsa, "Assessed"), "%Y-%m-%d").replace(tzinfo=UTC)
    assert assessed.date() <= datetime.now(UTC).date()


@pytest.mark.parametrize("ghsa", suppressed_ghsas())
def test_no_suppression_is_past_its_review_date(ghsa: str) -> None:
    # The whole failure mode is a suppression nobody revisits. This is the only
    # part of the document that can fail on its own, with no code change at all.
    review_by = datetime.strptime(_field(ghsa, "Review by"), "%Y-%m-%d").replace(tzinfo=UTC).date()
    assert review_by > date(2026, 1, 1), "a review date in the past is not a review date"
    assert review_by >= datetime.now(UTC).date(), (
        f"{ghsa} is past its review date; reassess it or take the upgrade"
    )


@pytest.mark.parametrize("ghsa", suppressed_ghsas())
def test_each_suppression_says_what_would_make_it_false(ghsa: str) -> None:
    assert "What would make this false" in _section(ghsa)
