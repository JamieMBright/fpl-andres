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
REPO = Path(__file__).resolve().parents[2]

#: Extensions prettier owns in this repository. A bot that commits one of
#: these without formatting it hands the failure to the next push.
_PRETTIER_OWNED = re.compile(r"[\w./-]+\.(?:json|md)\b")

#: A push is a push wherever it sits on the line. The odds jobs retry inside
#: `if git push; then`, and an anchored pattern silently stopped seeing them —
#: which is the coverage loss the guard below exists to catch. The leading
#: `[^#\n]*` keeps a mention inside a comment from counting.
_PUSH = re.compile(r"^[^#\n]*\bgit push\b", re.MULTILINE)
_REBASE = re.compile(r"^\s*git pull --rebase --autostash\b", re.MULTILINE)
#: Rebasing is not enough on its own for the two odds jobs. Both regenerate the
#: same derived artifacts, so every one of them conflicts and `--autostash` only
#: relocates the conflict. Rebuilding on the base that arrived is the recovery
#: that actually works, and it counts.
_REBUILD = re.compile(r"^\s*git reset --hard \"origin/\$GITHUB_REF_NAME\"", re.MULTILINE)
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

    assert _REBASE.search(text) or _REBUILD.search(text), (
        f"{path.name} pushes without `git pull --rebase --autostash` or a "
        "rebuild onto the fetched base, so a run whose base moved while it "
        "worked is rejected and its output is lost"
    )


@pytest.mark.parametrize("path", _workflows(), ids=lambda path: path.name)
def test_a_workflow_that_commits_a_prettier_owned_file_formats_it(path: Path) -> None:
    """Scoped to the file, not the staged pathspec: `ingest-odds.yml` stages
    through a loop variable, so the path it commits never appears beside
    `git add`. This catches "never runs prettier at all", which is the shape
    all three observed reds had, and does not claim to check the argument.

    A workflow may format by calling a script rather than inline, so the
    scripts it runs are read too. The question is whether prettier runs
    anywhere on the path the workflow takes, not where the word appears.
    """
    text = path.read_text(encoding="utf-8")
    if not _pushes(text):
        return
    owned = sorted(set(_PRETTIER_OWNED.findall(text)))
    if not owned:
        return

    called = [REPO / script for script in sorted(set(re.findall(r"scripts/[\w./-]+\.sh", text)))]
    formats = "prettier" in text or any(
        script.exists() and "prettier" in script.read_text(encoding="utf-8") for script in called
    )

    assert formats, (
        f"{path.name} commits {owned}, which prettier owns, without running "
        "it -- the red lands on the next human push, not on this run"
    )


def test_the_bot_committing_workflows_are_covered_by_those_rules() -> None:
    """Guards the guards: a renamed step must not empty the set silently."""
    pushing = {path.name for path in _workflows() if _pushes(path.read_text(encoding="utf-8"))}

    for name in (
        "calibrate-points-to-rank.yml",
        "capture-live-gameweek.yml",
        "ingest-odds.yml",
        "ingest-player-odds.yml",
        "probe-api-football-historical.yml",
        "survey-player-props.yml",
        "sweep-managers.yml",
        "validate-model.yml",
    ):
        assert name in pushing, f"{name} no longer looks like it pushes"


def test_solver_input_publication_rebuilds_after_a_push_conflict() -> None:
    """A rebase cannot merge independently regenerated planning artifacts."""
    text = (WORKFLOWS / "publish-solver-input.yml").read_text(encoding="utf-8")

    assert "for attempt in 1 2 3 4 5" in text
    assert 'git reset --hard "origin/$GITHUB_REF_NAME"' in text
    assert "rebuild" in text
    assert "could not push the regenerated solver input after five attempts" in text


def test_model_validation_refires_only_when_a_new_gameweek_settles() -> None:
    """Bot capture commits cannot activate another workflow's push filter."""
    text = (WORKFLOWS / "validate-model.yml").read_text(encoding="utf-8")
    header = text.split("jobs:", 1)[0]

    assert "workflow_run:" in header
    assert 'workflows: ["Capture settled gameweeks"]' in header
    assert "github.event.workflow_run.conclusion == 'success'" in text
    assert 'output_file.write(f"run={str(settled > published).lower()}\\n")' in text
    assert "needs.refresh.outputs.run == 'true'" in text


def test_portfolio_annotation_backfills_legacy_season_standings() -> None:
    text = (WORKFLOWS / "annotate-portfolio.yml").read_text(encoding="utf-8")

    assert "capture_cohort_aggregate" in text
    assert '"$portfolio_dir/gw${event}-standing.json"' in text
    assert '--standing-supersedes "gw${event}-aggregates.json"' in text
    assert "adds-season-standing" in text
    assert "scripts/republish-fpl500.sh" in text


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
    # The chain is one script both odds jobs call, because each has to be able
    # to run it a second time when its push is rejected and it rebuilds on the
    # base that arrived. The ordering guarantee therefore lives with the script.
    assert "scripts/republish-plan.sh" in text
    assert "pnpm install --frozen-lockfile" in text

    chain = (REPO / "scripts" / "republish-plan.sh").read_text(encoding="utf-8")
    season_inputs = chain.index("python -m fpl_andres.cli.publish_season_inputs")
    canonical = chain.index(
        "pnpm --filter @fpl-andres/web publish:canonical-opening",
        season_inputs,
    )
    season_plan = chain.index("python -m fpl_andres.cli.publish_season_plan", canonical)
    assert season_inputs < canonical < season_plan
    # Fixture and player odds move the whole season plan even when the opening
    # fifteen happens to stay unchanged.
    assert "canonical fifteen unchanged" not in chain
    for path in (
        "apps/web/src/data/season-inputs.json",
        "apps/web/src/data/opening-squad.json",
        "apps/web/src/data/season-plan.json",
    ):
        assert path in chain
        assert path in text

    # Whatever else changed, the artifact this job fetched is formatted and
    # staged, and the derived chain is republished before anything is staged.
    if name == "ingest-odds.yml":
        # This workflow iterates the declared paths and formats/stages `$path`.
        assert 'prettier@3 --write "$path"' in text
        assert 'git add -A -- "$path"' in text
    else:
        # The player workflow names its own artifact explicitly.
        formatting = text.index("prettier@3 --write apps/web/src/data/player-odds.json")
        staging = text.index("git add apps/web/src/data/player-odds.json", formatting)
        assert formatting < staging


def test_prospective_freeze_uses_the_event_deadline_ledger() -> None:
    chain = (REPO / "scripts" / "republish-plan.sh").read_text(encoding="utf-8")
    validation = (WORKFLOWS / "validate-model.yml").read_text(encoding="utf-8")

    for text in (chain, validation):
        assert "season-inputs.json'); process.stdout.write(p.deadlines[0])" not in text
        assert "python -m fpl_andres.cli.freeze_prospective" in text
        assert "data/prospective/*.json" in text


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
    assert "--time-limit 120" in text[season_plan : season_plan + 400]

    for path in (
        "apps/web/src/data/opening-squad.json",
        "apps/web/src/data/season-plan.json",
    ):
        assert text.count(path) >= 3, f"{path} must be watched, formatted and committed"


def test_model_validation_publishes_the_held_out_xstart_experiment() -> None:
    text = (WORKFLOWS / "validate-model.yml").read_text(encoding="utf-8")
    experiment = "python -m fpl_andres.cli.experiment_xstart"
    artifact = "data/experiments/xstart-current-season.json"

    assert experiment in text
    assert '--code-revision "$GITHUB_SHA"' in text
    assert text.count(artifact) >= 3


def test_model_validation_publishes_the_held_out_recent_form_experiment() -> None:
    text = (WORKFLOWS / "validate-model.yml").read_text(encoding="utf-8")
    experiment = "python -m fpl_andres.cli.experiment_recent_form_weight"
    artifact = "data/experiments/recent-form-weight.json"

    assert experiment in text
    assert '--code-revision "$GITHUB_SHA"' in text
    assert text.count(artifact) >= 4


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
    job = text.index("  validate:\n")
    first_step = text.index("steps:", job)

    assert "timeout-minutes: 60" in text[republish:following_step]
    assert "timeout-minutes: 150" in text[job:first_step]


def test_fpl500_capture_republishes_the_prospective_event_ledger() -> None:
    text = (WORKFLOWS / "capture-fpl500.yml").read_text(encoding="utf-8")

    pin = text.index("python -m fpl_andres.cli.pin_fpl500_membership")
    catalogue_capture = text.index("python -m fpl_andres.cli.capture_cohort_picks", pin)
    exact_capture = text.index(
        "python -m fpl_andres.cli.capture_cohort_picks", catalogue_capture + 1
    )
    aggregate = text.index("python -m fpl_andres.cli.capture_cohort_aggregate", exact_capture)
    publish = text.index("scripts/republish-fpl500.sh", aggregate)
    web_artifact = "apps/web/src/data/fpl500.json"
    assert pin < catalogue_capture < exact_capture < aggregate < publish
    assert "--membership" in text[catalogue_capture:publish]
    assert "data/cohort/portfolio/fpl500" in text
    assert web_artifact in text
    chain = (REPO / "scripts" / "republish-fpl500.sh").read_text(encoding="utf-8")
    assert web_artifact in chain


@pytest.mark.parametrize(
    "name",
    ("capture-fpl500.yml", "sweep-managers.yml", "annotate-portfolio.yml"),
)
def test_fpl500_artifact_producers_rebuild_on_the_base_that_arrived(name: str) -> None:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")

    assert "scripts/republish-fpl500.sh" in text
    assert _REBUILD.search(text), (
        f"{name} regenerates the shared FPL500 artifacts, so rebasing two "
        "independent JSON generations cannot recover a rejected push"
    )


def test_portfolio_annotation_sweeps_catalogue_and_exact_fpl500() -> None:
    text = (WORKFLOWS / "annotate-portfolio.yml").read_text(encoding="utf-8")

    assert text.count("python -m fpl_andres.cli.annotate_portfolio") >= 2
    assert "--portfolio-dir data/cohort/portfolio/fpl500" in text


def test_live_capture_builds_the_review_after_the_settled_snapshot() -> None:
    text = (WORKFLOWS / "capture-live-gameweek.yml").read_text(encoding="utf-8")

    capture = text.index("python -m fpl_andres.cli.capture_live_gameweek")
    xstart = text.index("python -m fpl_andres.cli.build_xstart_validation", capture)
    review = text.index("python -m fpl_andres.cli.build_gw1_review", xstart)
    xstart_step = text.rindex("- name:", 0, xstart)
    review_step = text.rindex("- name:", 0, review)
    staging = text.index("git add $paths", review)
    comparison = text.index("git diff --cached --quiet", staging)
    assert capture < xstart < review < staging < comparison
    assert "set -o pipefail" in text[xstart_step:xstart]
    assert "set -o pipefail" in text[review_step:review]
    assert "fetch-depth: 0" in text
    assert text.count("apps/web/src/data/xstart-validation.json") >= 2


def test_deadlines_are_shipped_data_not_cohort_evidence() -> None:
    publisher = (
        Path(__file__).resolve().parents[1] / "fpl_andres" / "cli" / "publish_deadlines.py"
    ).read_text(encoding="utf-8")
    workflow = (WORKFLOWS / "publish-deadlines.yml").read_text(encoding="utf-8")

    for text in (publisher, workflow):
        assert "apps/web/src/data/deadlines.json" in text
        assert "data/cohort/deadlines.json" not in text
    assert "apps/web/public/fpl-global.json" in workflow
