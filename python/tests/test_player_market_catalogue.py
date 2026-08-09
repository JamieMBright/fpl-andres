"""The generated market catalogue.

The point of the page is that a reader can answer one question from it: can
this project price a player's chance to score, and if not, why not. These pin
that the page answers it in both directions.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fpl_andres.adapters.player_market_catalogue import render_catalogue
from fpl_andres.adapters.player_props import ProbeResult, PropSource

SURVEYED_AT = datetime(2026, 8, 9, 12, 30, tzinfo=UTC)


def _source(
    key: str,
    *,
    covers: tuple[str, ...],
    credential_env: tuple[str, ...] = (),
    market: bool = True,
) -> PropSource:
    return PropSource(
        key=key,
        name=key.replace("-", " ").title(),
        homepage=f"https://{key}.example",
        credential_env=credential_env,
        covers=covers,
        terms="Test source.",
        probe=lambda _client, _env: ProbeResult(key=key, status="ok", note="ok"),
        market=market,
    )


def test_it_names_who_can_price_a_goal() -> None:
    sources = [
        _source("priced", covers=("goal", "assist")),
        _source("match-only", covers=("clean_sheet",)),
        _source("rates", covers=("goal",), market=False),
    ]
    results = [
        ProbeResult(
            key="priced",
            status="ok",
            note="answered",
            markets=("player_goal_scorer_anytime",),
        ),
        ProbeResult(key="match-only", status="ok", note="answered"),
        ProbeResult(key="rates", status="ok", note="answered"),
    ]

    page = render_catalogue(sources, results, SURVEYED_AT)

    assert "## Can we price a player's chance to score?" in page
    assert "**Priced**" in page
    assert "player_goal_scorer_anytime" in page
    # Neither of these has money on the outcome, so neither answers the
    # question this section asks.
    assert "**Match Only**" not in page
    assert "**Rates**" not in page


def test_it_says_plainly_when_nothing_can() -> None:
    sources = [_source("blocked", covers=("goal",), credential_env=("KEY",))]
    results = [
        ProbeResult(key="blocked", status="no_credential", note="KEY is not set"),
    ]

    page = render_catalogue(sources, results, SURVEYED_AT)

    assert "Not from anything that answered this run" in page
    assert "`KEY`" in page
    # No credential is a finding, not a crash, and the table must show it.
    assert "no key" in page


def test_the_coverage_table_has_a_row_for_every_source() -> None:
    sources = [_source("a", covers=("goal",)), _source("b", covers=("save",))]
    results = [
        ProbeResult(key="a", status="ok", note="ok", http_status=200),
        ProbeResult(key="b", status="unreachable", note="ConnectError"),
    ]

    page = render_catalogue(sources, results, SURVEYED_AT)
    rows = [
        line for line in page.splitlines() if line.startswith("| A ") or line.startswith("| B ")
    ]

    assert len(rows) == 2
    assert "answered (200)" in rows[0]
    assert "blocked" in rows[1]


def test_it_refuses_to_render_a_mismatch() -> None:
    try:
        render_catalogue([_source("a", covers=())], [], SURVEYED_AT)
    except ValueError as error:
        assert "exactly one result" in str(error)
    else:  # pragma: no cover - the assertion above is the test
        raise AssertionError("a missing result must not render")
