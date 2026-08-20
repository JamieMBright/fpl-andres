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

#: A push is a push wherever it sits on the line. The odds jobs retry inside
#: `if git push; then`, and an anchored pattern silently stopped seeing them —
#: which is the coverage loss the guard below exists to catch. The leading
#: `[^#\n]*` keeps a mention inside a comment from counting.
_PUSH = re.compile(r"^[^#\n]*\bgit push\b", re.MULTILINE)
_REBASE = re.compile(r"^\s*git pull --rebase --autostash\b", re.MULTILINE)
#: `git diff` without `--cached` compares the working tree to the index and
#: ignores untracked files entirely.
_UNSTAGED_DIFF = re.compile(r"^\s*(?:if\s+)?git diff(?!\s+--cached)\b", re.MULTILINE)


def _workflows() -> list[Path]:
    return sorted(WORKFLOWS.glob("*.yml"))


def _pushes(text: str) -> bool:
    return bool(_PUSH.search(text))


@pytest.mark.parametrize("path", _workflows(), ids=lambda path: path.name)
def test_a_workflow_that_commits_asks_the_index_whether_anything_changed(
    path: Path,
) -> None:
    """`git diff` cannot see a file git has never seen.

    Every committing workflow here guards its commit with "has anything
    changed", and every one of them asked the working tree. A file that does
    not yet exist in git is untracked, `git diff` ignores untracked files, and
    the guard therefore reports "unchanged" and exits clean -- so the first run
    to produce an artifact silently throws it away.

    That is not hypothetical. `Survey Player Markets` passed weekly for months
    and `docs/PLAYER_MARKET_CATALOGUE.md` never landed once, which is also why
    nobody could answer which sources price which scoring route.
    """
    text = path.read_text(encoding="utf-8")
    if not _pushes(text):
        return

    assert not _UNSTAGED_DIFF.search(text), (
        f"{path.name} decides whether to commit with `git diff`, which ignores "
        "untracked files, so the run that first creates its artifact will "
        "report no change and discard it. Stage it, then `git diff --cached`."
    )


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
        "calibrate-points-to-rank.yml",
        "ingest-odds.yml",
        "ingest-player-odds.yml",
        "survey-player-props.yml",
        "sweep-managers.yml",
        "validate-model.yml",
    ):
        assert name in pushing, f"{name} no longer looks like it pushes"


@pytest.mark.parametrize(
    "name,source",
    (
        ("ingest-player-odds.yml", "player-odds.json"),
        ("ingest-odds.yml", "fixture-odds.json"),
    ),
)
def test_live_odds_producers_republish_the_plan_the_browser_reads(name: str, source: str) -> None:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")

    assert source in text
    season_inputs = text.index("python -m fpl_andres.cli.publish_season_inputs")
    canonical = text.index(
        "pnpm --filter @fpl-andres/web publish:canonical-opening",
        season_inputs,
    )
    season_plan = text.index("python -m fpl_andres.cli.publish_season_plan", canonical)
    assert season_inputs < canonical < season_plan
    assert "pnpm install --frozen-lockfile" in text
    assert "opening_before" in text
    assert "opening_after" in text
    for path in (
        "apps/web/src/data/season-inputs.json",
        "apps/web/src/data/opening-squad.json",
        "apps/web/src/data/season-plan.json",
    ):
        assert path in text
    if name == "ingest-odds.yml":
        # This workflow iterates the declared paths and formats/stages `$path`.
        assert 'prettier@3 --write "$path"' in text
        assert 'git add -A -- "$path"' in text
    else:
        # The player workflow names both artifacts explicitly.
        publish = text.index("python -m fpl_andres.cli.publish_season_inputs")
        formatting = text.index("prettier@3 --write", publish)
        staging = text.index("git add", formatting)
        assert publish < formatting < staging
        assert staging < text.rindex("apps/web/src/data/season-inputs.json")


def test_rank_sampler_keeps_raw_progress_out_of_model_validation() -> None:
    validation = (WORKFLOWS / "validate-model.yml").read_text(encoding="utf-8")
    calibration = (WORKFLOWS / "calibrate-points-to-rank.yml").read_text(encoding="utf-8")

    assert "data/cohort/points-to-rank.json" in validation
    assert "points-to-rank-sample.jsonl" not in validation
    assert "points-to-rank-sample-checkpoint.json" not in validation
    for path in (
        "data/cohort/points-to-rank-sample.jsonl",
        "data/cohort/points-to-rank-sample-checkpoint.json",
        "data/cohort/points-to-rank.json",
    ):
        assert path in calibration
    assert 'git add -- "$path"' in calibration


def test_model_validation_republishes_the_complete_planning_chain() -> None:
    text = (WORKFLOWS / "validate-model.yml").read_text(encoding="utf-8")

    projection = text.index("python -m fpl_andres.cli.publish_projections")
    opening_seed = text.index("python -m fpl_andres.cli.publish_opening_squad", projection)
    season_inputs = text.index("python -m fpl_andres.cli.publish_season_inputs", opening_seed)
    canonical = text.index("pnpm --filter @fpl-andres/web publish:canonical-opening", season_inputs)
    season_plan = text.index("python -m fpl_andres.cli.publish_season_plan", canonical)
    assert projection < opening_seed < season_inputs < canonical < season_plan

    for path in (
        "apps/web/src/data/opening-squad.json",
        "apps/web/src/data/season-plan.json",
    ):
        assert text.count(path) >= 3, f"{path} must be watched, formatted and committed"


def test_model_artifact_proof_changes_trigger_hosted_validation() -> None:
    text = (WORKFLOWS / "validate-model.yml").read_text(encoding="utf-8")

    assert "python/tests/test_measured_performance.py" in text.split("workflow_dispatch:", 1)[0]


def test_model_backtest_allows_the_measured_slow_runner_duration() -> None:
    text = (WORKFLOWS / "validate-model.yml").read_text(encoding="utf-8")
    backtest = text.index("- name: Run the backtest")
    following_step = text.index("- name:", backtest + 1)

    assert "timeout-minutes: 60" in text[backtest:following_step]


def test_model_republication_allows_the_measured_slow_runner_duration() -> None:
    text = (WORKFLOWS / "validate-model.yml").read_text(encoding="utf-8")
    republish = text.index("- name: Republish the projection the site reads")
    following_step = text.index("- name:", republish + 1)
    job = text.index("jobs:")
    first_step = text.index("steps:", job)

    assert "timeout-minutes: 60" in text[republish:following_step]
    assert "timeout-minutes: 150" in text[job:first_step]


def test_fpl500_capture_republishes_the_prospective_event_ledger() -> None:
    text = (WORKFLOWS / "capture-fpl500.yml").read_text(encoding="utf-8")

    capture = text.index("python -m fpl_andres.cli.capture_cohort_picks")
    publish = text.index("python -m fpl_andres.cli.publish_fpl500", capture)
    web_artifact = "apps/web/src/data/fpl500.json"
    assert publish > capture
    assert text.count(web_artifact) >= 2


def test_deadlines_are_shipped_data_not_cohort_evidence() -> None:
    publisher = (
        Path(__file__).resolve().parents[1] / "fpl_andres" / "cli" / "publish_deadlines.py"
    ).read_text(encoding="utf-8")
    workflow = (WORKFLOWS / "publish-deadlines.yml").read_text(encoding="utf-8")

    for text in (publisher, workflow):
        assert "apps/web/src/data/deadlines.json" in text
        assert "data/cohort/deadlines.json" not in text
    assert "apps/web/public/fpl-global.json" in workflow
