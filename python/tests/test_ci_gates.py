"""The named CI gates exist and are wired to the things they claim to check.

Audit items #78, #79, #142, #143 and #144.

A workflow file is configuration, so nothing type-checks it and nothing runs it
locally. A step deleted in a rebase, a job renamed out of a required-checks
list, or a script whose name drifted from its `run:` line all fail the same
way: silently, by no longer running.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def workflow() -> dict[str, object]:
    document: dict[str, object] = yaml.safe_load(CI.read_text(encoding="utf-8"))
    return document


def _jobs(workflow: dict[str, object]) -> dict[str, dict[str, object]]:
    jobs: dict[str, dict[str, object]] = workflow["jobs"]  # type: ignore[assignment]
    return jobs


def _steps(workflow: dict[str, object], job: str) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = _jobs(workflow)[job]["steps"]  # type: ignore[index,assignment]
    return steps


def _run_lines(workflow: dict[str, object], job: str) -> str:
    return "\n".join(str(step.get("run", "")) for step in _steps(workflow, job))


def _triggers(workflow: dict[str, object]) -> object:
    # YAML 1.1 reads a bare ``on`` as the boolean true, so PyYAML keys this
    # section under ``True`` and not ``"on"``. Every GitHub workflow hits this
    # and the resulting KeyError names neither the cause nor the fix.
    return workflow.get("on", workflow.get(True))  # type: ignore[call-overload]


class TestSecretScanning:
    """#78: a real secret committed by accident is only undone by rotation."""

    def test_a_secret_scan_runs_on_every_pull_request(self, workflow: dict[str, object]) -> None:
        assert "pull_request" in _triggers(workflow)  # type: ignore[operator]
        uses = [str(step.get("uses", "")) for step in _steps(workflow, "secrets-and-contracts")]
        assert any("gitleaks" in entry for entry in uses)

    def test_the_scanner_action_is_pinned_to_a_commit(self, workflow: dict[str, object]) -> None:
        # A moving tag on a security tool is a supply chain hole in the thing
        # meant to close one.
        for step in _steps(workflow, "secrets-and-contracts"):
            uses = str(step.get("uses", ""))
            if not uses:
                continue
            _, _, reference = uses.partition("@")
            assert len(reference) == 40, f"{uses} is not pinned to a full commit SHA"
            assert all(character in "0123456789abcdef" for character in reference)

    def test_the_scan_sees_the_whole_history(self, workflow: dict[str, object]) -> None:
        # A secret is still a secret in the commit that added it, even when a
        # later commit removes the line. A shallow clone would not see it.
        checkout = next(
            step
            for step in _steps(workflow, "secrets-and-contracts")
            if "checkout" in str(step.get("uses", ""))
        )
        assert checkout["with"]["fetch-depth"] == 0  # type: ignore[index]

    def test_every_allowlist_names_a_path_and_a_shape(self) -> None:
        # Gitleaks defaults an allowlist carrying both `paths` and `regexes` to
        # OR, which exempts the shape everywhere instead of in the one file.
        # Verified against a planted service-role key: without the explicit
        # AND, it was not reported.
        config = (REPO_ROOT / ".gitleaks.toml").read_text(encoding="utf-8")
        blocks = config.split("[[allowlists]]")[1:]
        assert blocks, "no allowlists declared"
        for block in blocks:
            assert 'condition = "AND"' in block
            assert "paths = " in block
            assert "regexes = " in block
            assert "description = " in block

    def test_the_default_rules_are_kept(self) -> None:
        config = (REPO_ROOT / ".gitleaks.toml").read_text(encoding="utf-8")
        assert "useDefault = true" in config

    def test_the_action_is_pointed_at_the_config(self, workflow: dict[str, object]) -> None:
        # Without this the action uses its own defaults and the two documented
        # false positives fail every run, which is how a gate gets removed.
        step = next(
            step
            for step in _steps(workflow, "secrets-and-contracts")
            if "gitleaks" in str(step.get("uses", ""))
        )
        assert step["env"]["GITLEAKS_CONFIG"] == ".gitleaks.toml"  # type: ignore[index]


class TestSchemaDriftGate:
    """#143: drift was one step inside a job that reports four other things."""

    def test_drift_is_its_own_named_job(self, workflow: dict[str, object]) -> None:
        job = _jobs(workflow)["secrets-and-contracts"]
        assert "contracts:check" in _run_lines(workflow, "secrets-and-contracts")
        assert "drift" in str(job["name"]).lower()

    def test_the_gate_is_cheap_enough_to_fail_first(self, workflow: dict[str, object]) -> None:
        # The point of splitting it out is a fast, unambiguous answer. A job
        # that waits on a database container and a browser download would not
        # give one.
        job = _jobs(workflow)["secrets-and-contracts"]
        assert int(job["timeout-minutes"]) <= 10  # type: ignore[arg-type]
        assert "supabase" not in _run_lines(workflow, "secrets-and-contracts")
        assert "playwright" not in _run_lines(workflow, "secrets-and-contracts").lower()


class TestContractsVersionGate:
    """#142: a schema change must come with a version bump."""

    def test_the_gate_runs_in_ci(self, workflow: dict[str, object]) -> None:
        assert "contracts:version-gate" in _run_lines(workflow, "secrets-and-contracts")

    def test_the_script_the_gate_names_exists(self) -> None:
        manifest = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
        command = manifest["scripts"]["contracts:version-gate"]
        script = command.split()[-1]
        assert (REPO_ROOT / script).is_file(), f"{script} is referenced but missing"

    def test_the_gate_compares_against_the_merge_base(self) -> None:
        # Comparing against the tip of the base branch would fire on any change
        # someone else merged in the meantime.
        source = (REPO_ROOT / "scripts" / "contracts-version-gate.mjs").read_text(encoding="utf-8")
        assert "merge-base" in source

    def test_the_gate_does_not_block_a_developer_without_the_base_branch(self) -> None:
        source = (REPO_ROOT / "scripts" / "contracts-version-gate.mjs").read_text(encoding="utf-8")
        assert "process.exit(0)" in source


class TestBoundaryTypes:
    """#144: an inferred return type at a boundary is a contract nobody wrote."""

    def test_the_rule_is_enabled_for_the_api_surface(self) -> None:
        config = (REPO_ROOT / "eslint.config.js").read_text(encoding="utf-8")
        assert "explicit-module-boundary-types" in config
        assert '"api/**/*.ts"' in config

    def test_every_handler_declares_its_return_type(self) -> None:
        # The rule enforces this, but the rule lives in a config file that a
        # future edit could narrow without anyone noticing.
        for path in (REPO_ROOT / "api").rglob("*.ts"):
            source = path.read_text(encoding="utf-8")
            if "export default" not in source:
                continue
            assert "): Promise<void> {" in source or "): void {" in source, (
                f"{path.relative_to(REPO_ROOT)} has an untyped default export"
            )
