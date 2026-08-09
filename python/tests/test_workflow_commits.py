"""A workflow that commits has to leave main both formatted and pushable.

Two failures with one shape. `Ingest Bookmaker Odds` run 16 checked out
`0934248`, spent 35 seconds fetching, and pushed into a main that had moved to
`476fc2a` in the meantime -- rejected, work discarded. And CI 224 went red on
`data/cohort/sweep-checkpoint.json`, a file the push never touched: a bot had
committed it unformatted, so the next human push inherited the failure.

Neither is visible in the workflow that causes it. The rejected push fails the
run that deserved it, but the unformatted commit fails somebody else's, which
is why it took three CI reds to find. There is no bash locally, so both are
asserted against the workflow text.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"

#: Extensions prettier owns in this repository. A bot that commits one of
#: these without formatting it hands the failure to the next push.
_PRETTIER_OWNED = re.compile(r"[\w./-]+\.(?:json|md)\b")

_PUSH = re.compile(r"^\s*git push\b", re.MULTILINE)
_REBASE = re.compile(r"^\s*git pull --rebase --autostash\b", re.MULTILINE)


def _workflows() -> list[Path]:
    return sorted(WORKFLOWS.glob("*.yml"))


def _pushes(text: str) -> bool:
    return bool(_PUSH.search(text))


@pytest.mark.parametrize("path", _workflows(), ids=lambda path: path.name)
def test_a_workflow_that_pushes_rebases_onto_whatever_arrived_first(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if not _pushes(text):
        return

    assert _REBASE.search(text), (
        f"{path.name} pushes without `git pull --rebase --autostash`, so a run "
        "whose base moved while it worked is rejected and its output is lost"
    )


@pytest.mark.parametrize("path", _workflows(), ids=lambda path: path.name)
def test_a_workflow_that_commits_a_prettier_owned_file_formats_it(path: Path) -> None:
    """Scoped to the file, not the staged pathspec: `ingest-odds.yml` stages
    through a loop variable, so the path it commits never appears beside
    `git add`. This catches "never runs prettier at all", which is the shape
    all three observed reds had, and does not claim to check the argument.
    """
    text = path.read_text(encoding="utf-8")
    if not _pushes(text):
        return
    owned = sorted(set(_PRETTIER_OWNED.findall(text)))
    if not owned:
        return

    assert "prettier" in text, (
        f"{path.name} commits {owned}, which prettier owns, without running "
        "it -- the red lands on the next human push, not on this run"
    )


def test_the_bot_committing_workflows_are_covered_by_those_rules() -> None:
    """Guards the guards: a renamed step must not empty the set silently."""
    pushing = {path.name for path in _workflows() if _pushes(path.read_text(encoding="utf-8"))}

    for name in (
        "ingest-odds.yml",
        "ingest-player-odds.yml",
        "survey-player-props.yml",
        "sweep-managers.yml",
        "validate-model.yml",
    ):
        assert name in pushing, f"{name} no longer looks like it pushes"
