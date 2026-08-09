"""A workflow that reads a secret has to say which environment holds it.

GitHub scopes a secret to an environment, and a job that does not name that
environment simply cannot see it. There is no error: the expression expands to
an empty string and the step fails somewhere further down for a reason that
looks unrelated. `Ingest Player Odds` run 1 failed exactly this way -- the key
was configured, the job could not read it, and the failure surfaced as "key is
not set".

Nothing type-checks a workflow file and nothing runs it locally, so this is the
only place the mistake can be caught before a scheduled run makes it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"

#: Secrets held in the `production` environment rather than on the repository.
#: `GITHUB_TOKEN` is issued per job and is deliberately not here.
ENVIRONMENT_SECRETS = frozenset(
    {
        "API_FOOTBALL_API_KEY",
        "BETFAIR_APP_KEY",
        "BETFAIR_SESSION_TOKEN",
        "SUPABASE_SECRET_KEY",
        "SUPABASE_URL",
        "THE_ODDS_API_KEY",
    }
)

_REFERENCE = re.compile(r"secrets\.([A-Z0-9_]+)")


def _workflows() -> list[Path]:
    return sorted(WORKFLOWS.glob("*.yml"))


def _secrets_used(text: str) -> set[str]:
    return {name for name in _REFERENCE.findall(text) if name in ENVIRONMENT_SECRETS}


@pytest.mark.parametrize("path", _workflows(), ids=lambda path: path.name)
def test_a_workflow_reading_an_environment_secret_names_the_environment(
    path: Path,
) -> None:
    text = path.read_text(encoding="utf-8")
    wanted = _secrets_used(text)
    if not wanted:
        return

    document = yaml.safe_load(text)
    jobs: dict[str, dict[str, object]] = document["jobs"]
    for name, job in jobs.items():
        if not _secrets_used(yaml.safe_dump(job)):
            continue
        assert job.get("environment") == "production", (
            f"{path.name} job '{name}' reads {sorted(wanted)} but declares no "
            "environment, so the secret expands to an empty string"
        )


def test_the_odds_workflows_are_covered_by_that_rule() -> None:
    """Guards the guard: a renamed secret must not silently empty the set."""
    named = {path.name for path in _workflows() if _secrets_used(path.read_text(encoding="utf-8"))}

    assert "ingest-player-odds.yml" in named
    assert "ingest-odds.yml" in named
    assert "survey-player-props.yml" in named


def test_the_ingest_tells_a_missing_key_apart_from_one_held_as_a_variable() -> None:
    """`secrets` and `vars` are separate namespaces and the UI puts them a tab
    apart, so "not set" is the wrong diagnosis half the time. The owner hit
    exactly that: the key was configured, as an environment variable, and the
    step told them to add a secret they believed they already had.

    No bash runs locally, so this asserts against the workflow text.
    """
    text = (WORKFLOWS / "ingest-player-odds.yml").read_text(encoding="utf-8")

    assert "vars.THE_ODDS_API_KEY" in text, (
        "the guard cannot tell an unset key from one held in `vars` without reading `vars`"
    )
    assert "environment VARIABLE, not a secret" in text


def test_no_credential_is_supplied_to_a_step_from_the_variables_namespace() -> None:
    """A `vars` entry is stored and logged in plain text. `SUPABASE_SECRET_KEY`
    is the service-role key, so sourcing one from there discloses it."""
    for path in _workflows():
        text = path.read_text(encoding="utf-8")
        for name in sorted(ENVIRONMENT_SECRETS):
            assert f"{name}: ${{{{ vars.{name} }}}}" not in text, (
                f"{path.name} takes {name} from `vars`, which is not masked in the log"
            )


def test_no_workflow_still_reads_a_retired_credential_name() -> None:
    """The owner holds `THE_ODDS_API_KEY`; the old names buy nothing but a 401."""
    retired = ("ODDS_API_KEY", "API_FOOTBALL_KEY", "SPORTMONKS_TOKEN")
    for path in _workflows():
        text = path.read_text(encoding="utf-8")
        for name in retired:
            # `THE_ODDS_API_KEY` legitimately ends in `ODDS_API_KEY`.
            assert not re.search(rf"(?<![A-Z_]){name}\b", text), (
                f"{path.name} still references {name}"
            )
