"""A promotion decision must be reproducible, not just recorded.

`model_promotion_decisions` stored the seed, the resample count
and the sample size — enough to re-run the bootstrap, and not enough to reproduce
the answer. Three things were missing: which code ran, over which corpus, and
with which numerical libraries.

The third is the one most easily dismissed. scipy's `spearmanr` and HiGHS'
simplex are the parts doing the arithmetic, and neither promises bit-identical
results across versions. A promotion that cannot be reproduced is not evidence,
it is a number someone wrote down.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fpl_andres.lineage import (
    NUMERICAL_DEPENDENCIES,
    Lineage,
    capture_lineage,
    dependency_fingerprint,
)

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260801190000_promotion_lineage.sql"
)


def _sql() -> str:
    return " ".join(_MIGRATION.read_text(encoding="utf-8").lower().split())


def test_the_dependency_fingerprint_is_stable_within_one_environment() -> None:
    assert dependency_fingerprint() == dependency_fingerprint()


def test_the_fingerprint_covers_the_libraries_that_do_the_arithmetic() -> None:
    """Not every dependency. httpx moving cannot alter a rank correlation, and a
    fingerprint that changes for reasons it cannot be guarding gets ignored."""
    _, versions = dependency_fingerprint()

    assert len(versions) == len(NUMERICAL_DEPENDENCIES)
    for name in ("scipy", "numpy", "highspy", "pydantic"):
        assert any(entry.startswith(f"{name}==") for entry in versions)


def test_a_missing_library_is_recorded_rather_than_skipped() -> None:
    """Absent is a fact about the environment. Skipping it would make two
    different environments fingerprint alike."""
    _, versions = dependency_fingerprint()

    assert all("==" in entry for entry in versions)


def test_the_version_list_is_kept_alongside_the_hash() -> None:
    """A hash says two runs differed. The list says how."""
    fingerprint, versions = dependency_fingerprint()

    assert fingerprint.startswith("sha256:")
    assert len(fingerprint) == len("sha256:") + 64
    assert versions


def test_capture_reads_the_revision_that_is_about_to_run() -> None:
    lineage = capture_lineage()

    assert re.fullmatch(r"[0-9a-f]{40}", lineage.code_revision)
    assert lineage.dependency_fingerprint.startswith("sha256:")


def test_a_corpus_fingerprint_is_carried_through_when_supplied() -> None:
    corpus = f"sha256:{'a' * 64}"

    lineage = capture_lineage(corpus_fingerprint=corpus)

    assert lineage.corpus_fingerprint == corpus


def test_a_decision_without_a_corpus_says_none_rather_than_guessing() -> None:
    assert capture_lineage().corpus_fingerprint is None


def test_lineage_is_frozen() -> None:
    """It describes a run that already happened."""
    lineage = Lineage(
        code_revision="a" * 40,
        dependency_fingerprint=f"sha256:{'b' * 64}",
        dependency_versions=("scipy==1.0.0",),
    )

    with pytest.raises(Exception, match=r"frozen|immutable|cannot assign"):
        lineage.code_revision = "c" * 40  # type: ignore[misc]


@pytest.mark.parametrize(
    "column",
    [
        "code_revision",
        "corpus_fingerprint",
        "dependency_fingerprint",
        "dependency_versions",
        "seed_replicates",
        "seeds_promoting",
    ],
)
def test_the_migration_adds_every_lineage_column(column: str) -> None:
    assert f"add column if not exists {column}" in _sql()


def test_the_lineage_columns_are_nullable() -> None:
    """Rows written before these existed genuinely do not know their lineage,
    and backfilling a guess would be worse than an honest gap."""
    sql = _sql()

    for column in ("code_revision", "corpus_fingerprint", "dependency_fingerprint"):
        assert f"{column} text not null" not in sql


def test_a_malformed_fingerprint_is_refused_by_the_schema() -> None:
    """A truncated hash must not be able to pass as provenance."""
    sql = _sql()

    assert "corpus_fingerprint ~ '^sha256:[0-9a-f]{64}$'" in sql
    assert "dependency_fingerprint ~ '^sha256:[0-9a-f]{64}$'" in sql
    assert "code_revision ~ '^[0-9a-f]{7,40}$'" in sql


def test_the_schema_refuses_a_promotion_that_bypassed_unanimity() -> None:
    """A split vote resolves to not-promoted. A row that promoted on fewer seeds
    than it replicated would mean that rule had been gone around."""
    sql = _sql()

    assert "seeds_promoting between 0 and seed_replicates" in sql
    assert "not promoted or seeds_promoting = seed_replicates" in sql


def test_the_migration_keeps_the_deny_all_posture() -> None:
    sql = _sql()

    assert "create policy" not in sql
    assert "grant " not in sql
