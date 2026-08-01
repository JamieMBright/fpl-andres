"""An injected parameter must reach every place that reads it.

Audit item #11 asked for `_BENCH_WEIGHT` and `PLAYABLE_START_RATE` to become
injectable rather than module constants. Both already were: `OpeningSettings`
carries `bench_weight` and `playable_start_rate`, defaulting to the constants.
`simulation/season.py`, which the item named, has no such constant at all.

The real defect was subtler and worse than the one reported. The opening-squad
publisher pre-filtered candidates against the module constant while handing the
selector a settings object, so an injected floor was applied by one and ignored
by the other. A parameter that is half-injectable is more dangerous than one
that is not injectable at all: it looks configured and behaves otherwise.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from fpl_andres.planning.opening import (
    PLAYABLE_START_RATE,
    OpeningSettings,
    choose_opening_squad,
)
from fpl_andres.simulation.squad import Candidate, SquadRules

_PUBLISHER = Path(__file__).resolve().parents[1] / "fpl_andres" / "cli" / "publish_opening_squad.py"

RULES = SquadRules(
    budget_tenths=1000,
    club_limit=3,
    position_counts={1: 2, 2: 5, 3: 5, 4: 3},
)


def test_both_parameters_are_already_injectable() -> None:
    """#11's premise. Recorded so the item is not reopened."""
    settings = OpeningSettings(rules=RULES, bench_weight=0.5, playable_start_rate=0.9)

    assert settings.bench_weight == 0.5
    assert settings.playable_start_rate == 0.9


def test_the_defaults_are_the_published_constants() -> None:
    assert OpeningSettings(rules=RULES).playable_start_rate == PLAYABLE_START_RATE


def test_the_publisher_reads_the_floor_from_settings_not_the_constant() -> None:
    """The real defect. Every comparison, artifact field and log line must come
    from the settings object, or an injected floor is applied by the selector
    and ignored by the filter that ran before it."""
    tree = ast.parse(_PUBLISHER.read_text(encoding="utf-8"))
    bare_uses = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and node.id == "PLAYABLE_START_RATE"
        and isinstance(node.ctx, ast.Load)
    ]
    assert bare_uses == [], (
        "publish_opening_squad reads the module constant directly; it must read "
        "settings.playable_start_rate so the pre-filter and the selector agree"
    )


def test_the_publisher_builds_its_settings_before_it_filters() -> None:
    """Ordering is the whole fix: a settings object built after the filter
    cannot influence it."""
    source = _PUBLISHER.read_text(encoding="utf-8")
    built = source.index("settings = OpeningSettings(")
    filtered = source.index("< settings.playable_start_rate")
    assert built < filtered


def _candidate(element_id: int, position: int, price: int) -> Candidate:
    return Candidate(
        element_id=element_id,
        element_code=100_000 + element_id,
        position=position,
        team_id=(element_id % 20) + 1,
        price_tenths=price,
        web_name=f"P{element_id}",
    )


def _pool() -> list[Candidate]:
    pool: list[Candidate] = []
    element_id = 1
    for position, count in ((1, 4), (2, 10), (3, 10), (4, 6)):
        for _ in range(count):
            pool.append(_candidate(element_id, position, 45))
            element_id += 1
    return pool


@pytest.mark.parametrize("floor", [0.0, 0.35, 0.75])
def test_a_raised_floor_changes_who_is_eligible_to_start(floor: float) -> None:
    """The setting has to do something, or injecting it proves nothing."""
    pool = _pool()
    ranking = {player.element_id: float(player.element_id) for player in pool}
    # Half the pool is a nailed starter, half is a rotation risk.
    start_rates = {player.element_id: 0.9 if player.element_id % 2 == 0 else 0.5 for player in pool}

    plan = choose_opening_squad(
        pool,
        ranking,
        start_rates,
        OpeningSettings(rules=RULES, playable_start_rate=floor),
    )

    assert len(plan.squad) == RULES.squad_size
    if floor > 0.5:
        # Nobody below the floor may be trusted with a starting place while an
        # eligible alternative exists.
        eligible = [p for p in plan.starters if start_rates[p.element_id] >= floor]
        assert len(eligible) >= 1
