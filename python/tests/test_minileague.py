"""Transfer economics in the mini-league simulation.

These guard the fairness of the published comparison: a manager carries the same
squad week to week, gets one free transfer per gameweek, banks up to five, and
pays four points for anything beyond the bank.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus
from fpl_andres.simulation.minileague import (
    LeagueSettings,
    _Manager,
    _take_transfers,
    simulate_league,
)
from fpl_andres.simulation.season import LineupRules
from fpl_andres.simulation.squad import Candidate, SquadRules
from fpl_andres.simulation.valuation import Portfolio

SQUAD_RULES = SquadRules(budget_tenths=1000, club_limit=3, position_counts={1: 2, 2: 5, 3: 5, 4: 3})
LINEUP_RULES = LineupRules(
    starting_size=11,
    minimum_by_position={1: 1, 2: 3, 3: 2, 4: 1},
    maximum_by_position={1: 1, 2: 5, 3: 5, 4: 3},
)
KICKOFF = datetime(2024, 8, 17, 14, 0, tzinfo=UTC)


def candidate(element_id: int, position: int, team_id: int, price: int = 40) -> Candidate:
    return Candidate(
        element_id=element_id,
        element_code=element_id,
        position=position,
        team_id=team_id,
        price_tenths=price,
        web_name=f"P{element_id}",
    )


def build_manager(free_transfers: int) -> _Manager:
    from fpl_andres.simulation.minileague import ManagerResult

    squad = [
        candidate(1, 1, 1),
        candidate(2, 1, 2),
        *[candidate(10 + index, 2, 3 + index) for index in range(5)],
        *[candidate(20 + index, 3, 8 + index) for index in range(5)],
        *[candidate(30 + index, 4, 13 + index) for index in range(3)],
    ]
    return _Manager(
        result=ManagerResult(manager_id=0, policy="advised", seed=0),
        squad=squad,
        free_transfers=free_transfers,
        portfolio=Portfolio.opening(
            [player.element_id for player in squad],
            PRICES,
            SQUAD_RULES.budget_tenths,
        ),
    )


# Every squad member and every replacement costs the same, so affordability
# never quietly decides a test that is about transfer economics.
PRICES = {element_id: 40 for element_id in range(1, 200)}


def pool_sorted(upgrades: dict[int, float]) -> dict[int, list[Candidate]]:
    """Every position offers one clearly better, affordable replacement."""
    by_position: dict[int, list[Candidate]] = {}
    for element_id, position in ((100, 1), (110, 2), (120, 3), (130, 4)):
        by_position[position] = [candidate(element_id, position, 20)]
    for entries in by_position.values():
        entries.sort(key=lambda entry: upgrades.get(entry.element_id, 0.0), reverse=True)
    return by_position


def test_a_free_transfer_is_spent_before_any_hit_is_taken() -> None:
    manager = build_manager(free_transfers=0)
    ranking = {player.element_id: 1.0 for player in manager.squad}
    ranking[110] = 10.0

    _take_transfers(
        manager,
        settings=LeagueSettings(squad_rules=SQUAD_RULES, lineup_rules=LINEUP_RULES),
        by_position=pool_sorted(ranking),
        projected=ranking,
        form=ranking,
        minutes={},
        prices=PRICES,
    )

    assert manager.result.transfers_made == 1
    assert manager.result.hit_points == 0


def test_a_marginal_gain_does_not_justify_a_hit() -> None:
    manager = build_manager(free_transfers=0)
    ranking = {player.element_id: 1.0 for player in manager.squad}
    # One free transfer arrives, so two upgrades are on offer but only the first
    # is free. The second gains 3.0, under the four-point cost of a hit.
    ranking[110] = 10.0
    ranking[120] = 4.0

    _take_transfers(
        manager,
        settings=LeagueSettings(squad_rules=SQUAD_RULES, lineup_rules=LINEUP_RULES),
        by_position=pool_sorted(ranking),
        projected=ranking,
        form=ranking,
        minutes={},
        prices=PRICES,
    )

    assert manager.result.transfers_made == 1
    assert manager.result.hit_points == 0


def test_a_large_gain_does_justify_a_hit() -> None:
    manager = build_manager(free_transfers=0)
    ranking = {player.element_id: 1.0 for player in manager.squad}
    ranking[110] = 10.0
    ranking[120] = 9.0

    _take_transfers(
        manager,
        settings=LeagueSettings(squad_rules=SQUAD_RULES, lineup_rules=LINEUP_RULES),
        by_position=pool_sorted(ranking),
        projected=ranking,
        form=ranking,
        minutes={},
        prices=PRICES,
    )

    assert manager.result.transfers_made == 2
    assert manager.result.hit_points == 4


def test_free_transfers_bank_but_never_exceed_the_cap() -> None:
    settings = LeagueSettings(squad_rules=SQUAD_RULES, lineup_rules=LINEUP_RULES)
    manager = build_manager(free_transfers=settings.max_free_transfers)
    flat = {player.element_id: 1.0 for player in manager.squad}

    _take_transfers(
        manager,
        settings=settings,
        by_position={},
        projected=flat,
        form=flat,
        minutes={},
        prices=PRICES,
    )

    assert manager.free_transfers == settings.max_free_transfers
    assert manager.result.transfers_made == 0


def synthetic_corpus() -> SeasonCorpus:
    """Twelve gameweeks, forty players, points fixed by element id."""
    corpus = SeasonCorpus(season="2024-25")
    element_id = 1
    for position, count in ((1, 6), (2, 16), (3, 16), (4, 10)):
        for index in range(count):
            corpus.position_by_element[element_id] = position
            corpus.team_by_element[element_id] = 1 + (index % 12)
            corpus.name_by_element[element_id] = f"P{element_id}"
            element_id += 1

    for gameweek in range(1, 13):
        rows = []
        for player, position in corpus.position_by_element.items():
            rows.append(
                ElementRow(
                    gameweek=gameweek,
                    element_id=player,
                    element_code=player,
                    fixture_id=gameweek * 100 + player,
                    minutes=90,
                    started=True,
                    goals=1 if player % 7 == 0 else 0,
                    assists=0,
                    expected_goals=0.2,
                    expected_assists=0.1,
                    total_points=2 + (player % 5),
                    price_tenths=40 + (position * 5),
                    selected=1000,
                    kickoff_time=KICKOFF + timedelta(days=7 * gameweek),
                )
            )
        corpus.rows_by_gameweek[gameweek] = rows
    return corpus


def test_the_squad_persists_and_only_changes_by_transfer() -> None:
    settings = LeagueSettings(
        squad_rules=SQUAD_RULES,
        lineup_rules=LINEUP_RULES,
        managers=4,
        advised_share=0.5,
        start_gameweek=7,
    )
    result = simulate_league(synthetic_corpus(), settings, seed=1)

    gameweeks_played = 6
    for manager in result.managers:
        assert len(manager.weekly_points) == gameweeks_played
        # One free transfer a week is the ceiling without paying for more.
        free_moves = gameweeks_played
        paid_moves = manager.hit_points // 4
        assert manager.transfers_made <= free_moves + paid_moves
        assert manager.net_points == manager.total_points - manager.hit_points


@pytest.mark.parametrize("policy", ["advised", "zombie"])
def test_every_manager_is_held_to_the_same_transfer_budget(policy: str) -> None:
    settings = LeagueSettings(
        squad_rules=SQUAD_RULES,
        lineup_rules=LINEUP_RULES,
        managers=4,
        advised_share=0.5,
        start_gameweek=7,
    )
    result = simulate_league(synthetic_corpus(), settings, seed=2)

    for manager in result.by_policy(policy):  # type: ignore[arg-type]
        assert manager.transfers_made <= 6 + manager.hit_points // 4


def tilt_ranking(place: int, places: int) -> dict[int, float]:
    """Rank a widely-owned and a rare player for a manager in a given position."""
    from fpl_andres.simulation.minileague import ManagerResult, _tilted_ranking

    managers = []
    for index in range(places):
        entry = _Manager(
            result=ManagerResult(manager_id=index, policy="rank_aware", seed=index),
            squad=[],
            free_transfers=1,
            portfolio=Portfolio(holdings={}, bank_tenths=0),
        )
        # Net points descend with index, so index 0 leads.
        entry.result.total_points = (places - index) * 100
        managers.append(entry)

    return _tilted_ranking(
        managers[place],
        managers,
        projected={1: 5.0, 2: 5.0},
        ownership={1: 0.9, 2: 0.05},
        settings=LeagueSettings(squad_rules=SQUAD_RULES, lineup_rules=LINEUP_RULES),
    )


def test_a_leader_prefers_the_player_the_field_already_owns() -> None:
    ranking = tilt_ranking(place=0, places=10)

    assert ranking[1] > ranking[2]


def test_a_manager_in_last_prefers_the_player_nobody_owns() -> None:
    ranking = tilt_ranking(place=9, places=10)

    assert ranking[2] > ranking[1]


def test_neither_tilt_changes_a_player_ranked_against_himself() -> None:
    # The tilt is a risk setting, so two equally owned players keep their order.
    from fpl_andres.simulation.minileague import ManagerResult, _tilted_ranking

    solo = _Manager(
        result=ManagerResult(manager_id=0, policy="rank_aware", seed=0),
        squad=[],
        free_transfers=1,
        portfolio=Portfolio(holdings={}, bank_tenths=0),
    )
    ranking = _tilted_ranking(
        solo,
        [solo],
        projected={1: 5.0, 2: 9.0},
        ownership={1: 0.9, 2: 0.05},
        settings=LeagueSettings(squad_rules=SQUAD_RULES, lineup_rules=LINEUP_RULES),
    )

    assert ranking[2] > ranking[1]
