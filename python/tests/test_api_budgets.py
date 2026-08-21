"""Every scheduled run has to fit inside the free tier it spends.

None of these hosts warns before an allowance runs out; the request that
crosses the line simply fails, and the failure looks exactly like a market
that is not open. Nobody notices until a deadline. The numbers below are
therefore held here, against the schedules that spend them, so raising a cron
or adding a market has to be argued for rather than merged.

The Odds API bills per market per region, not per request. That is the fact
this file exists to keep in front of whoever changes a cron next: the same
schedule costs four times as much with four markets as with one.

Nothing here emits or implies a betting recommendation. A price is read as a
probability and used as evidence about a footballer.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from fpl_andres.adapters.player_props import (
    _THE_ODDS_API_IMPLICIT_MARKETS,
    _THE_ODDS_API_MARKETS,
)
from fpl_andres.adapters.the_odds_api import PLAYER_MARKETS
from fpl_andres.cli.ingest_odds import (
    TEAM_FALLBACK_BILLED_MARKETS,
    TEAM_FALLBACK_MARKETS,
    TEAM_FALLBACK_WEEKLY_BUDGET,
)
from fpl_andres.cli.ingest_player_odds import (
    DEFAULT_BUDGET,
    billed_request_cost,
    can_request_fixture,
)

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"

#: The Odds API free tier. Shared by the ingest and the weekly survey.
ODDS_API_MONTHLY = 500

#: Days in a month, for turning a weekly cron into a monthly bill.
WEEKS_PER_MONTH = 4.4


def _triggers(name: str) -> dict[str, object]:
    document = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    # PyYAML reads a bare `on` as the boolean True, this being YAML 1.1.
    section = document.get("on", document.get(True))
    assert isinstance(section, dict), f"{name} declares no triggers"
    return section


def _weekly_runs(name: str) -> float:
    """How many times a month the schedule fires, from its crons alone."""
    schedule = _triggers(name).get("schedule", [])
    assert isinstance(schedule, list)
    total = 0.0
    for entry in schedule:
        cron = str(entry["cron"])
        days = cron.split()[4]
        if days == "*":
            total += 30.0
            continue
        total += len(re.split(r"[,-]", days)) * WEEKS_PER_MONTH
    return total


def test_the_ingest_and_the_survey_fit_inside_one_free_tier() -> None:
    """They share a key, and the survey is the one nobody watches.

    A run costs its budget in requests; the survey costs its market list once
    a week. If the two together exceed the allowance the ingest is what fails,
    silently, in the week before a deadline.
    """
    ingest = _weekly_runs("ingest-player-odds.yml") * DEFAULT_BUDGET
    survey = _weekly_runs("survey-player-props.yml") * (
        len(_THE_ODDS_API_MARKETS) + len(_THE_ODDS_API_IMPLICIT_MARKETS)
    )
    team = WEEKS_PER_MONTH * TEAM_FALLBACK_WEEKLY_BUDGET

    assert ingest + survey + team <= ODDS_API_MONTHLY, (
        f"the schedules spend {ingest + survey + team:.0f} of "
        f"{ODDS_API_MONTHLY} requests a month ({ingest:.0f} player, "
        f"{team:.0f} team, {survey:.0f} surveying). Cut a cron, the budget, "
        "or the market list."
    )


def test_the_ingest_asks_for_no_market_it_does_not_read() -> None:
    """Each one is billed per region, every run, whether or not anybody reads it."""
    from fpl_andres.adapters.the_odds_api import MARKET_FIELDS

    assert set(PLAYER_MARKETS) == set(MARKET_FIELDS)


def test_team_fallback_requests_every_live_number_moving_market() -> None:
    assert TEAM_FALLBACK_MARKETS == ("h2h", "totals", "alternate_totals")
    assert _THE_ODDS_API_IMPLICIT_MARKETS == ("h2h_lay",)
    assert len(TEAM_FALLBACK_MARKETS) + 1 == TEAM_FALLBACK_BILLED_MARKETS


def test_a_player_run_reserves_the_maximum_cost_before_another_fixture() -> None:
    assert len(PLAYER_MARKETS) == DEFAULT_BUDGET
    last_safe = DEFAULT_BUDGET - len(PLAYER_MARKETS)
    assert can_request_fixture(spent=last_safe, budget=DEFAULT_BUDGET) is True
    assert can_request_fixture(spent=last_safe + 1, budget=DEFAULT_BUDGET) is False


def test_an_explicitly_free_response_does_not_consume_the_run_cap() -> None:
    from fpl_andres.adapters.the_odds_api import Quota

    assert billed_request_cost(Quota(cost=0, used=123, remaining=377)) == 0
    assert billed_request_cost(Quota(cost=None, used=None, remaining=None)) == 1


def test_the_odds_ingest_runs_daily() -> None:
    """No provider publishes an opening hour, so only a daily probe sees the first one."""
    schedule = _triggers("ingest-player-odds.yml")["schedule"]  # type: ignore[index]
    assert len(schedule) == 1
    assert str(schedule[0]["cron"]).split()[4] == "*"


def test_a_paid_workflow_does_not_spend_the_allowance_on_every_push() -> None:
    """A `push` trigger on a source path is an unbounded, uncounted spender.

    The monthly sum above counts crons. A workflow that also fires on pushes
    to the modules it runs costs its full budget again for each one, and a day
    of ordinary work on those modules is several pushes. That is not a
    rounding error against a 500-request tier: it is how an allowance sized for
    a season is gone in a week, and the failure arrives as a market that looks
    shut rather than as an error.

    Free-tier workflows are therefore asked for by hand.
    """
    for name in ("ingest-player-odds.yml", "survey-player-props.yml", "ingest-odds.yml"):
        triggers = _triggers(name)
        assert "workflow_dispatch" in triggers, f"{name} must stay manually runnable"
        paths = (triggers.get("push") or {}).get("paths", [])  # type: ignore[union-attr]
        assert all(str(path).startswith(".github/workflows/") for path in paths), (
            f"{name} re-runs on a push to {paths}, spending its whole budget "
            "again outside the monthly sum above. Trigger it by hand instead."
        )


def test_the_daily_odds_trigger_bails_before_the_provider_outside_deadline_week() -> None:
    text = (WORKFLOWS / "ingest-player-odds.yml").read_text(encoding="utf-8")

    assert "--within-days 7" in text
    assert "apps/web/src/data/deadlines.json" in (
        Path(__file__).resolve().parents[1] / "fpl_andres" / "cli" / "ingest_player_odds.py"
    ).read_text(encoding="utf-8")
