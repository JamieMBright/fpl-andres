"""Schema conventions, enforced rather than described.

- **#106** asked for referential integrity or a reconciliation job for
  `source_snapshots.storage_path`, so deleted objects do not leave orphan rows.
  Investigating found something else: nothing in this repository uploads to
  Supabase Storage. There are no objects to delete and therefore no orphans of
  the kind described. The column is a content address derived from
  `content_hash`, and the integrity that actually applies is internal.

- **#107** asked for an ERD. It lives in `docs/SCHEMA.md`, and these tests
  assert it names every table and every foreign key, so a new relation cannot
  be added without appearing in the picture.

- **#108** asked for naming conventions. Every migration already follows them;
  this makes that a rule rather than a coincidence.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS = _ROOT / "supabase" / "migrations"
_SCHEMA_DOC = _ROOT / "docs" / "SCHEMA.md"


@cache
def _sql() -> str:
    """Comments stripped: one explains the lock `CREATE INDEX takes`, and a
    convention check that reads prose finds an index called `takes`."""
    statements: list[str] = []
    for path in sorted(_MIGRATIONS.glob("*.sql")):
        for line in path.read_text(encoding="utf-8").splitlines():
            statements.append(line.split("--", 1)[0])
    return " ".join(" ".join(statements).split()).lower()


@cache
def _tables() -> set[str]:
    return set(re.findall(r"create table (?:if not exists )?public\.(\w+)", _sql()))


def test_every_index_is_named_for_its_table_and_ends_in_idx() -> None:
    offenders = [
        name
        for name in re.findall(r"create index (?:if not exists )?(\w+)", _sql())
        if not name.endswith("_idx") or not any(name.startswith(t) for t in _tables())
    ]
    assert offenders == [], f"indexes not named <table>_<columns>_idx: {offenders}"


def test_every_named_constraint_starts_with_its_table() -> None:
    """Constraint names are read in error messages by whoever is holding the
    failing insert, so they have to say which table refused."""
    offenders = [
        name
        for name in re.findall(r"constraint (\w+) (?:check|unique)", _sql())
        if not any(name.startswith(table) for table in _tables())
    ]
    assert offenders == [], f"constraints not prefixed with their table: {offenders}"


def test_every_trigger_is_named_for_its_table() -> None:
    offenders = [
        name
        for name in re.findall(r"create trigger (\w+)", _sql())
        if not any(name.startswith(table) for table in _tables())
    ]
    assert offenders == [], f"triggers not prefixed with their table: {offenders}"


def test_helper_functions_live_in_private() -> None:
    """`public` is the schema PostgREST exposes. A helper there is an endpoint."""
    public_functions = re.findall(r"create (?:or replace )?function public\.(\w+)", _sql())
    assert public_functions == [], (
        f"these helpers are reachable through PostgREST: {public_functions}"
    )


def test_the_erd_names_every_table() -> None:
    """#107. A table missing from the diagram is a table nobody reviewing the
    model will know exists."""
    diagram = _SCHEMA_DOC.read_text(encoding="utf-8").split("```mermaid", 1)[1]
    diagram = diagram.split("```", 1)[0]
    missing = sorted(table for table in _tables() if table not in diagram)
    assert missing == [], f"absent from the ERD in docs/SCHEMA.md: {missing}"


def test_the_erd_shows_every_foreign_key_target() -> None:
    diagram = _SCHEMA_DOC.read_text(encoding="utf-8").split("```mermaid", 1)[1]
    diagram = diagram.split("```", 1)[0]
    targets = set(re.findall(r"references public\.(\w+)", _sql()))
    missing = sorted(target for target in targets if target not in diagram)
    assert missing == [], f"foreign key targets absent from the ERD: {missing}"


def test_the_storage_path_is_tied_to_the_content_hash() -> None:
    """#106. The integrity that applies to a column nothing uploads to."""
    assert "source_snapshots_path_matches_hash" in _sql()
    assert "storage_path = source || '/' || substring(content_hash from 8)" in _sql()


def test_the_ingest_derives_the_path_the_constraint_expects() -> None:
    """An injectable prefix could only ever break the constraint, so it is gone.

    Nothing passed a non-default value, and a value that disagreed with
    `source` would have produced rows the database now refuses.
    """
    source = (_ROOT / "python" / "fpl_andres" / "ingest" / "historical.py").read_text(
        encoding="utf-8"
    )

    assert "storage_prefix" not in source
    assert '"storage_path": f"{_SOURCE}/' in source


def test_nothing_claims_to_upload_to_object_storage() -> None:
    """The premise behind #106's answer. If an upload appears, the column stops
    being a content address and the reconciliation job it asked for is back on
    the table."""
    package = _ROOT / "python" / "fpl_andres"
    offenders = sorted(
        path.relative_to(package).as_posix()
        for path in package.rglob("*.py")
        if "storage/v1" in path.read_text(encoding="utf-8")
    )
    assert offenders == [], f"these upload to object storage: {offenders}"
