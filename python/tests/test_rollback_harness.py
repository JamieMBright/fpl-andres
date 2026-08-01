"""The teardown script must stay in step with the migrations.

Audit item #100: CI validated `supabase db reset` but never exercised undoing a
migration, so nothing proved the schema could be torn down and rebuilt.

That gap matters more here than in most projects. The production bootstrap is an
ordered SQL Editor checklist rather than `db push`, and the migration set uses
non-idempotent DDL throughout — measured below — so a file re-run after a
partial paste fails on the first object that already exists. `down.sql` is the
escape hatch, and an escape hatch that has quietly stopped covering three tables
is worse than none.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS = _ROOT / "supabase" / "migrations"
_ROLLBACK = _ROOT / "supabase" / "rollback" / "down.sql"


@cache
def _migration_sql() -> str:
    return " ".join(
        " ".join(path.read_text(encoding="utf-8").split())
        for path in sorted(_MIGRATIONS.glob("*.sql"))
    ).lower()


@cache
def _rollback_sql() -> str:
    """Comments stripped: they discuss `cascade` and the drop order, and a test
    that reads prose as SQL asserts nothing about the script."""
    lines = [line.split("--", 1)[0] for line in _ROLLBACK.read_text(encoding="utf-8").splitlines()]
    return " ".join(" ".join(lines).split()).lower()


def _created_tables() -> set[str]:
    return set(re.findall(r"create table (?:if not exists )?public\.(\w+)", _migration_sql()))


def _created_functions() -> set[str]:
    return set(re.findall(r"create (?:or replace )?function (private\.\w+)\(", _migration_sql()))


def test_every_table_the_migrations_create_is_dropped() -> None:
    dropped = set(re.findall(r"drop table if exists public\.(\w+)", _rollback_sql()))
    missing = sorted(_created_tables() - dropped)
    assert missing == [], (
        "supabase/rollback/down.sql does not drop these tables, so a teardown "
        "would leave them behind and the re-apply would fail: " + ", ".join(missing)
    )


def test_every_function_the_migrations_create_is_dropped() -> None:
    dropped = set(re.findall(r"drop function if exists (private\.\w+)\(", _rollback_sql()))
    missing = sorted(_created_functions() - dropped)
    assert missing == [], f"down.sql leaves these functions behind: {missing}"


def test_the_teardown_drops_nothing_the_migrations_never_created() -> None:
    """A stale drop is a drop aimed at something else's object."""
    dropped = set(re.findall(r"drop table if exists public\.(\w+)", _rollback_sql()))
    stale = sorted(dropped - _created_tables())
    assert stale == [], f"down.sql drops tables no migration creates: {stale}"


def test_tables_drop_before_the_functions_their_triggers_use() -> None:
    """Reverse dependency order. A function still referenced by a trigger cannot
    be dropped, so getting this backwards makes the script fail halfway — which
    is precisely the state it exists to recover from."""
    sql = _rollback_sql()
    last_table = sql.rfind("drop table if exists")
    first_function = sql.find("drop function if exists")
    assert last_table < first_function, "functions are dropped before the tables"


def test_the_schema_drops_after_the_functions_inside_it() -> None:
    sql = _rollback_sql()
    assert sql.rfind("drop function if exists") < sql.find("drop schema if exists")


def test_the_teardown_is_a_single_transaction() -> None:
    """Half a teardown is a worse state than the one being recovered from."""
    sql = _rollback_sql().strip()
    assert sql.startswith("begin;")
    assert sql.endswith("commit;")


def test_the_teardown_does_not_use_cascade() -> None:
    """`cascade` would silently remove dependents this file has not been taught
    about, which is how a teardown drifts out of step with the schema and stops
    being reviewable."""
    assert "cascade" not in _rollback_sql()


def test_the_teardown_lives_outside_the_migrations_directory() -> None:
    """`supabase db reset` runs everything in `migrations/` in filename order.
    A teardown in there would drop the schema it had just built."""
    assert _ROLLBACK.parent.name == "rollback"
    assert not list(_MIGRATIONS.glob("*down*.sql"))


def test_the_migration_set_is_not_idempotent_which_is_why_this_exists() -> None:
    """Pins the measurement behind the decision, and the numbers the runbook
    quotes.

    The runbook previously claimed migrations were idempotent. They were not,
    and an operator following that claim mid-incident would have re-pasted a
    file and hit `relation already exists` with no stated recovery path.

    If these reach zero, every migration can simply be re-run and the teardown
    becomes far less load-bearing. Until then it is the only recovery path from
    a partial SQL Editor paste.
    """
    sql = _migration_sql()
    counts = {
        "create table": len(re.findall(r"create table (?!if not exists)\S", sql)),
        "create index": len(re.findall(r"create index (?!if not exists)(?!concurrently)\S", sql)),
        "create trigger": len(re.findall(r"create trigger \S", sql)),
        "create function": len(re.findall(r"create function \S", sql)),
    }
    assert sum(counts.values()) > 0, (
        "every migration is now idempotent; revisit whether down.sql is still "
        f"the primary recovery path. {counts}"
    )

    # Collapsed, because prose wraps and a count can land either side of a break.
    runbook = " ".join((_ROOT / "docs" / "RUNBOOK.md").read_text(encoding="utf-8").split())
    for label, count in counts.items():
        assert f"{count} `{label}`" in runbook, (
            f"the runbook quotes a stale count for {label}; it is now {count}"
        )


def test_the_runbook_documents_the_recovery_path() -> None:
    """An escape hatch nobody can find during an incident is not one."""
    runbook = (_ROOT / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
    assert "supabase/rollback/down.sql" in runbook
    assert "paste failed part-way" in runbook
    assert "teardown, not a" in runbook, "the destructive scope must be stated"
