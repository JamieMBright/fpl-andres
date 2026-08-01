"""The deny-all RLS posture is a decision, and must stay one.

Audit item #97. Every table is `enable row level security` plus `force row level
security` with no policy attached, which means: no anon or authenticated role can
read or write anything, and even the table owner is subject to RLS. Only
`service_role`, which bypasses RLS entirely, reaches the data. That is correct
while nothing is browser-readable — the web app reads published JSON artifacts,
not the database.

It was correct by accident, though, in the sense that nothing enforced it. A new
table without RLS would have been readable by `anon` the moment a Supabase
anon key reached the browser. These tests make the posture an invariant:
- a new table must be protected,
- and a first policy cannot be added without deliberately editing this file,
  which is where the guidance for doing it properly lives.

See `docs/adr/0001-forced-rls-with-no-policies.md` for the reasoning.
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"

_CREATE_TABLE = re.compile(r"create table (?:if not exists )?public\.(\w+)")
_ENABLE_RLS = re.compile(r"alter table public\.(\w+) enable row level security")
_FORCE_RLS = re.compile(r"alter table public\.(\w+) force row level security")
_CREATE_POLICY = re.compile(r"create policy", re.IGNORECASE)
_GRANT = re.compile(r"^\s*grant\s+", re.IGNORECASE | re.MULTILINE)


def _all_sql() -> str:
    return " ".join(
        " ".join(path.read_text(encoding="utf-8").lower().split())
        for path in sorted(MIGRATIONS_DIR.glob("*.sql"))
    )


def test_every_public_table_enables_and_forces_row_level_security() -> None:
    """`enable` alone leaves the owner exempt, so both are required.

    Postgres exempts a table's owner from RLS unless `force` is set. Supabase
    migrations run as the owner, so `enable` on its own protects against the
    anon key but not against a query run through the SQL editor or any tooling
    connected as that role.
    """
    sql = _all_sql()
    created = set(_CREATE_TABLE.findall(sql))
    enabled = set(_ENABLE_RLS.findall(sql))
    forced = set(_FORCE_RLS.findall(sql))

    assert created, "no tables found; the regexes have drifted from the SQL"
    assert sorted(created - enabled) == [], (
        "these tables never enable row level security: " + ", ".join(sorted(created - enabled))
    )
    assert sorted(created - forced) == [], (
        "these tables enable but never force row level security, so the owner "
        "role is still exempt: " + ", ".join(sorted(created - forced))
    )


def test_no_migration_creates_a_policy() -> None:
    """The first policy is the moment the database stops being private.

    If you are here because you added one, the checklist is:

    1. Say which role it grants to. `anon` means the open internet; the browser
       ships that key. `authenticated` means anyone who can sign up.
    2. Name it after what it permits, not the table it sits on, so the grant is
       legible in `pg_policies` without reading the migration.
    3. Restrict it to `select` unless a write path genuinely exists. This
       project's writes all come from CI as `service_role`.
    4. Confirm the table holds nothing derived from a subscriber email, a
       manager's private team state, or an unpublished projection.
    5. Add the table to the assertion below so the exemption is explicit rather
       than implied by a deleted test.

    `force row level security` still applies. A policy narrows a deny-all
    default; it does not replace it.
    """
    tables_with_policies: set[str] = set()
    assert tables_with_policies == set(), (
        "a policy was added; update this test's allowlist and the ADR together"
    )
    assert not _CREATE_POLICY.search(_all_sql()), (
        "a migration creates a policy. Read this test's docstring before "
        "allowlisting it, then record the decision in "
        "docs/adr/0001-forced-rls-with-no-policies.md"
    )


def test_no_migration_grants_table_access_to_a_client_role() -> None:
    """A `grant` would route around RLS-by-absence-of-policy entirely.

    RLS denies by default only because no policy exists. A `grant select on ...
    to anon` does not create a policy, so this stays denied — but the pairing is
    subtle enough that the grant is worth refusing outright rather than
    reasoning about each time.
    """
    grants = [
        line.strip()
        for path in sorted(MIGRATIONS_DIR.glob("*.sql"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if _GRANT.match(line)
    ]
    assert grants == [], f"migrations grant table access: {grants}"


def test_the_posture_is_documented_where_someone_would_look() -> None:
    adr = MIGRATIONS_DIR.parents[1] / "docs" / "adr" / "0001-forced-rls-with-no-policies.md"
    assert adr.exists(), "the RLS decision must have an ADR"
    text = adr.read_text(encoding="utf-8").lower()
    for phrase in ("service_role", "force row level security", "anon"):
        assert phrase in text, f"ADR 0001 should explain {phrase}"


def test_rls_covers_every_table_the_history_corpus_added() -> None:
    """The corpus migration adds six tables at once, which is the shape of change
    most likely to leave one unprotected."""
    sql = _all_sql()
    forced = set(_FORCE_RLS.findall(sql))
    corpus = {
        "seasons",
        "teams",
        "elements",
        "fixtures",
        "element_gameweek_stats",
        "element_price_observations",
    }
    assert corpus <= forced, f"unprotected corpus tables: {sorted(corpus - forced)}"
