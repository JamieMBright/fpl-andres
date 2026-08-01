"""The runbook must cover the failures that actually happen.

Audit items #194 and #198. The runbook had deploy, secrets, release, supply
chain and one API incident. It had nothing for the three failures most likely to
need it — a bad ingest, a promotion that looks wrong, and stale public state —
and no local development guide at all.

These check the procedures reference things that exist. A playbook naming a
column that was renamed is worse than no playbook, because it is followed under
pressure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RUNBOOK = _ROOT / "docs" / "RUNBOOK.md"
_DEVELOPMENT = _ROOT / "docs" / "DEVELOPMENT.md"


def _runbook() -> str:
    return _RUNBOOK.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "incident",
    [
        "returning HTTP 500 with an empty body",
        "a migration paste failed part-way through",
        "the corpus has ingested wrong data",
        "a promotion decision looks wrong",
        "the site is showing stale public state",
    ],
)
def test_the_runbook_covers_the_incident(incident: str) -> None:
    assert incident in _runbook(), f"no playbook for: {incident}"


def test_the_corpus_playbook_names_the_real_recovery_path() -> None:
    """Deleting the season first turns a recoverable overwrite into a gap. The
    upsert key is what makes re-ingesting the correct move."""
    text = _runbook()

    assert "Do not delete the season" in text
    assert "season, gameweek, element_id, fixture_id" in text
    assert "corpusFingerprint" in text


def test_the_promotion_playbook_names_the_lineage_columns_that_exist() -> None:
    """A playbook naming a column that was renamed is followed under pressure."""
    text = _runbook()

    for column in (
        "code_revision",
        "corpus_fingerprint",
        "dependency_fingerprint",
        "dependency_versions",
        "seeds_promoting",
        "seed_replicates",
    ):
        assert column in text, f"the promotion playbook does not mention {column}"


def test_the_promotion_playbook_says_a_split_vote_promoted_nothing() -> None:
    """The first thing to check, and the one most likely to be misread as a
    failed promotion rather than a refused one."""
    text = _runbook()

    assert "seed_disagreement" in text
    assert "Nothing was promoted" in text


def test_the_stale_state_playbook_separates_the_two_causes() -> None:
    """A failing refresh and a stale committed artifact look identical on the
    page and need opposite responses."""
    text = _runbook()

    assert "The refresh is failing" in text
    assert "The artifacts are stale" in text
    assert "generatedAt" in text


def test_the_stale_state_playbook_names_the_degraded_reasons_the_contract_defines() -> None:
    text = _runbook()

    for reason in ("fpl_unreachable", "fpl_source_failed", "source_contract_failed"):
        assert reason in text


def test_the_development_guide_covers_what_the_readme_does_not() -> None:
    text = _DEVELOPMENT.read_text(encoding="utf-8")

    for topic in ("supabase status", "psql", "maxDuration", "PYTHONHASHSEED"):
        assert topic in text, f"the development guide does not cover {topic}"


def test_the_development_guide_repeats_the_production_prohibition() -> None:
    """The one place a reader is being told how to inspect a database is the
    place to say which database."""
    text = _DEVELOPMENT.read_text(encoding="utf-8")

    assert "local database only" in text
    assert "prohibited" in text
    assert "db push" in text


def test_the_development_guide_explains_why_failures_are_opaque() -> None:
    """Otherwise the first reaction to a bare request id is to add the message
    back, which is the leak the design prevents."""
    text = _DEVELOPMENT.read_text(encoding="utf-8")

    assert "request id" in text
    assert "connection string" in text


def test_every_command_the_guides_quote_is_a_real_script() -> None:
    """A runbook that quotes a command which no longer exists sends whoever is
    following it to a dead end."""
    import json

    scripts = set(json.loads((_ROOT / "package.json").read_text(encoding="utf-8"))["scripts"])
    text = _DEVELOPMENT.read_text(encoding="utf-8") + _runbook()

    for script in ("fast", "check", "test:e2e", "dev"):
        assert script in scripts, f"package.json has no {script} script"
        assert f"pnpm {script}" in text
