"""Shared test doubles and builders.

Measured before building: fifteen helper names are defined in
more than one test file, and `FakeClient` in three. Two of those three were the
same idea with different bodies — one honoured `returning` and gave each row an
id, the other ignored it — so a persistence test's behaviour depended on which
file it happened to live in. The third, in `test_rivals.py`, is a different thing
that shares a name and is deliberately left alone.

Only genuinely shared pieces belong here. A builder that every caller has to
override defeats the point, and the per-model helpers in the model test files
differ enough that merging them would produce exactly that.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from fpl_andres.persistence.supabase import SupabaseCredentials

__all__ = ["RecordingClient", "credentials"]

# Not a real key. Long enough to prove a redaction test is redacting something.
TEST_SECRET = "sb_secret_" + "0" * 32


class RecordingClient:
    """A Supabase client that records writes instead of making them.

    Named for what it does rather than what it is not: the tests using it are
    asserting on the rows a publisher builds, and that is the thing worth
    naming.
    """

    def __init__(self) -> None:
        self.writes: list[tuple[str, list[Mapping[str, Any]]]] = []

    def insert(
        self,
        table: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        returning: bool = False,
        **_: Any,
    ) -> list[dict[str, Any]]:
        self.writes.append((table, list(rows)))
        if not returning:
            return []
        return [{"id": f"{table}-{index}"} for index, _ in enumerate(rows)]

    def upsert(
        self,
        table: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        on_conflict: str | None = None,
        **_: Any,
    ) -> list[dict[str, Any]]:
        self.writes.append((table, list(rows)))
        return []

    @property
    def tables(self) -> list[str]:
        return [table for table, _ in self.writes]

    def rows_for(self, table: str) -> list[Mapping[str, Any]]:
        return [row for written, rows in self.writes if written == table for row in rows]


def credentials(url: str = "https://project.supabase.invalid") -> SupabaseCredentials:
    """Credentials that are obviously not real, for tests that need a client."""
    return SupabaseCredentials(url=url, secret_key=TEST_SECRET)
