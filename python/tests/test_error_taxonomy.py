"""`docs/ERRORS.md` must describe every exception the package can raise.

It was asked for a public error taxonomy, prompted by
`FutureMinutesEvidenceError` being undocumented. A document alone would rot on
the first new exception, so this pins it: adding a raisable type without
classifying it fails the suite.

The test cannot check that a given exception landed in the *right* table. That
is the one part requiring judgement, and pretending otherwise would make the
taxonomy look more load-bearing than it is.
"""

from __future__ import annotations

import ast
import re
from functools import cache
from pathlib import Path

import pytest

_PACKAGE = Path(__file__).resolve().parents[1] / "fpl_andres"
_TAXONOMY = Path(__file__).resolve().parents[2] / "docs" / "ERRORS.md"
_EXCEPTION_BASES = {"ValueError", "RuntimeError", "LookupError", "Exception", "TypeError"}
_SECTIONS = ("## Refuse", "## Degrade", "## Retry")


@cache
def _parsed() -> tuple[tuple[str, ast.Module], ...]:
    return tuple(
        (path.relative_to(_PACKAGE).as_posix(), ast.parse(path.read_text(encoding="utf-8")))
        for path in sorted(_PACKAGE.rglob("*.py"))
    )


@cache
def _declared_exceptions() -> dict[str, str]:
    """Every class in the package that is, or descends from, an exception."""
    found: dict[str, str] = {}
    local_bases: set[str] = set()
    for _ in range(3):  # resolve chains such as ArchiveFileNotPublished
        for relative, tree in _parsed():
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                bases = {base.id for base in node.bases if isinstance(base, ast.Name)}
                if bases & (_EXCEPTION_BASES | local_bases):
                    found[node.name] = relative
                    local_bases.add(node.name)
    return found


@cache
def _taxonomy_rows() -> dict[str, str]:
    """Tolerates the column padding prettier adds when it reformats the tables.

    The first version anchored on single spaces and silently matched nothing
    after `pnpm format` ran, which turned the coverage assertion into a test
    that every exception was missing. Padding-tolerant since.
    """
    text = _TAXONOMY.read_text(encoding="utf-8")
    return {
        match.group(1): match.group(2)
        for match in re.finditer(r"^\|\s*`(\w+)`\s*\|\s*`([^`]+)`\s*\|", text, re.MULTILINE)
    }


def test_every_exception_is_classified() -> None:
    missing = sorted(set(_declared_exceptions()) - set(_taxonomy_rows()))
    assert missing == [], (
        "these exceptions are not in docs/ERRORS.md. Decide whether each one "
        "means refuse, degrade or retry, then add a row: " + ", ".join(missing)
    )


def test_the_taxonomy_lists_no_exception_that_no_longer_exists() -> None:
    stale = sorted(set(_taxonomy_rows()) - set(_declared_exceptions()))
    assert stale == [], f"docs/ERRORS.md describes exceptions that were deleted: {stale}"


def test_the_taxonomy_records_the_right_module() -> None:
    declared = _declared_exceptions()
    wrong = {
        name: (documented, declared[name])
        for name, documented in _taxonomy_rows().items()
        if name in declared and documented != declared[name]
    }
    assert wrong == {}, f"module moved without updating docs/ERRORS.md: {wrong}"


def test_every_exception_explains_itself() -> None:
    """A bare `pass` body tells a caller nothing about which class it is in."""
    declared = _declared_exceptions()
    undocumented = [
        f"{relative}::{node.name}"
        for relative, tree in _parsed()
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and node.name in declared
        and not (ast.get_docstring(node) or "").startswith("Raised when")
    ]
    assert undocumented == [], "exception docstrings must start with 'Raised when': " + ", ".join(
        undocumented
    )


@pytest.mark.parametrize("section", _SECTIONS)
def test_all_three_classes_are_present_and_populated(section: str) -> None:
    text = _TAXONOMY.read_text(encoding="utf-8")
    assert section in text
    body = text.split(section, 1)[1].split("\n## ", 1)[0]
    assert body.count("\n| `") >= 5, f"{section} has too few entries to be a real class"


def test_the_taxonomy_refuses_a_single_package_wide_base_class() -> None:
    """Recorded as a decision, not an accident: one root exception would invite
    catching a refusal and a degradation in the same clause."""
    assert "FplAndresError" in _TAXONOMY.read_text(encoding="utf-8")
    assert "FplAndresError" not in _declared_exceptions()
