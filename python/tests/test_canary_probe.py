"""The canary's stated policy has to be the policy it can actually execute.

It said a degraded response was "worth knowing but not this deployment
failing. Reported, not alarmed." It could not do that. The degraded envelope is
served with HTTP 503 and the probe checked the status code first, so the branch
that tolerated a degraded body was unreachable and every FPL blip opened an
incident. Seven of the first thirty-eight scheduled runs failed that way, which
is how an alert becomes one nobody reads.

The distinction that has to survive: `fpl_unreachable` and `fpl_source_failed`
are upstream and are reported; `source_contract_failed` means FPL answered in a
shape this deployment does not understand, every dossier degrades until the
contract is updated, and that one is alarmed.

A workflow file is configuration. Nothing type-checks it and nothing runs it
locally, so a rewrite that quietly drops a branch fails the same way the
original did: silently, in production, at three in the morning.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CANARY = REPO_ROOT / ".github" / "workflows" / "canary.yml"
RESPONSE = REPO_ROOT / "api" / "_lib" / "team-public-state-response.ts"


@pytest.fixture(scope="module")
def probe_script() -> str:
    document: dict[str, object] = yaml.safe_load(CANARY.read_text(encoding="utf-8"))
    jobs: dict[str, dict[str, object]] = document["jobs"]  # type: ignore[assignment]
    steps: list[dict[str, object]] = jobs["probe"]["steps"]  # type: ignore[index,assignment]
    return "\n".join(str(step.get("run", "")) for step in steps)


class TestTheProbeMatchesWhatTheApiActuallyReturns:
    def test_the_degraded_envelope_is_still_served_with_503(self) -> None:
        # The whole bug rests on this. If the API ever serves degraded with a
        # 200, the probe's ordering stops mattering and this test should be the
        # thing that says so.
        source = RESPONSE.read_text(encoding="utf-8")
        assert 'jsonResponse({ status: "degraded", reason }, 503)' in source

    def test_the_body_is_read_before_the_status_code(self, probe_script: str) -> None:
        body_check = probe_script.index('grep -q \'"status":"degraded"\'')
        code_check = probe_script.index('"$team_code" != "200"')
        assert body_check < code_check

    def test_an_upstream_failure_is_reported_and_not_alarmed(self, probe_script: str) -> None:
        # Neither upstream reason may appear in a line that records a failure.
        for line in probe_script.splitlines():
            if "fpl_unreachable" in line or "fpl_source_failed" in line:
                assert "failures=" not in line

    def test_a_broken_contract_is_alarmed(self, probe_script: str) -> None:
        assert "source_contract_failed" in probe_script
        alarmed = [
            line for line in probe_script.splitlines() if "failures=" in line and "contract" in line
        ]
        assert alarmed

    def test_every_degraded_reason_the_api_emits_is_accounted_for(self) -> None:
        # A new reason added to the API and not to the canary would be silently
        # sorted into "upstream", which is the safe-looking wrong answer.
        source = RESPONSE.read_text(encoding="utf-8")
        emitted = {
            reason
            for reason in ("fpl_unreachable", "fpl_source_failed", "source_contract_failed")
            if f'"{reason}"' in source
        }
        assert emitted == {"fpl_unreachable", "fpl_source_failed", "source_contract_failed"}

    def test_a_non_degraded_error_still_fails(self, probe_script: str) -> None:
        # A 500 with no envelope is the site being broken, and must still alarm.
        assert '"$team_code" != "200"' in probe_script
        assert "/api/team returned ${team_code}" in probe_script

    def test_health_is_still_checked_strictly(self, probe_script: str) -> None:
        # Health has no degraded mode; anything but ok is this deployment.
        assert '"$health_code" != "200"' in probe_script
        assert '"status":"ok"' in probe_script
