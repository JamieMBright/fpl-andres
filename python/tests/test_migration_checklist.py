"""The migration checklist is the production ledger, so it must be complete.

Audit item #192 surfaced this while cataloguing the schema. The repository
instructions state:

    The initial production bootstrap is the ordered SQL Editor checklist in
    `docs/OWNER_SETUP.md`.

That checklist did not exist. `OWNER_SETUP.md` named five migrations in a prose
bullet and eight were unnamed anywhere, including every one added after the
history corpus. There is no CLI migration ledger for the hosted project, so an
unnamed migration is one nobody can tell has been applied.

Also checks `docs/SCHEMA.md`, which is the only readable view of a model defined
across thirteen files.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS = _ROOT / "supabase" / "migrations"
_OWNER_SETUP = _ROOT / "docs" / "OWNER_SETUP.md"
_SCHEMA = _ROOT / "docs" / "SCHEMA.md"


def _migration_names() -> list[str]:
    return sorted(path.name for path in _MIGRATIONS.glob("*.sql"))


def _created_tables() -> set[str]:
    sql = " ".join(
        " ".join(path.read_text(encoding="utf-8").split())
        for path in sorted(_MIGRATIONS.glob("*.sql"))
    )
    return set(re.findall(r"create table (?:if not exists )?public\.(\w+)", sql))


def test_the_checklist_names_every_migration() -> None:
    """An unnamed migration is one nobody can tell has been applied."""
    listed = _OWNER_SETUP.read_text(encoding="utf-8")
    missing = [name for name in _migration_names() if name not in listed]

    assert missing == [], (
        "docs/OWNER_SETUP.md does not name these migrations, so their applied "
        "state cannot be recorded: " + ", ".join(missing)
    )


def test_the_checklist_names_nothing_that_does_not_exist() -> None:
    """A row for a deleted migration would be a line nobody can act on."""
    listed = re.findall(r"`(\d{14}_\w+\.sql)`", _OWNER_SETUP.read_text(encoding="utf-8"))
    stale = sorted(set(listed) - set(_migration_names()))

    assert stale == [], f"the checklist names migrations that no longer exist: {stale}"


def test_the_checklist_is_in_filename_order() -> None:
    """The order is the instruction. A list out of order is worse than none,
    because a migration referencing a later table fails on a clean apply."""
    listed = re.findall(r"`(\d{14}_\w+\.sql)`", _OWNER_SETUP.read_text(encoding="utf-8"))

    assert listed == sorted(listed)


def test_the_checklist_says_migrations_are_not_idempotent() -> None:
    """Whoever is pasting needs to know they cannot simply re-run a failed file."""
    text = _OWNER_SETUP.read_text(encoding="utf-8")

    assert "not idempotent" in text
    assert "rollback/down.sql" in text or "RUNBOOK" in text


def test_unconfirmed_rows_are_marked_rather_than_guessed() -> None:
    """Four migrations predate this checklist and their state was never recorded.

    Marking them for confirmation is the honest answer. Writing "yes" would put a
    guess into the one document that is supposed to be the ledger.
    """
    text = _OWNER_SETUP.read_text(encoding="utf-8")

    assert "owner to confirm" in text
    assert "marked for confirmation rather than guessed" in text


@pytest.mark.parametrize("table", sorted(_created_tables()))
def test_the_schema_reference_describes_every_table(table: str) -> None:
    assert f"`{table}`" in _SCHEMA.read_text(encoding="utf-8"), (
        f"docs/SCHEMA.md does not describe {table}"
    )


def test_the_schema_reference_states_the_organising_rule() -> None:
    """Ten tables immutable and seven not looks arbitrary without it."""
    text = _SCHEMA.read_text(encoding="utf-8")

    assert "immutable" in text.lower()
    assert "FPL revises in-season data" in text


def test_the_schema_reference_explains_the_one_cascade() -> None:
    """`backtest_predictions` is the only cascade in the schema, and an
    unexplained cascade is how data disappears."""
    text = _SCHEMA.read_text(encoding="utf-8")

    assert "on delete cascade" in text.lower()
    assert "backtest_predictions" in text


def test_the_schema_reference_records_the_per_fixture_grain() -> None:
    """The migration that fixed it exists because the original per-gameweek key
    silently discarded one row of a double gameweek."""
    text = _SCHEMA.read_text(encoding="utf-8")

    assert "per fixture, not per gameweek" in text
