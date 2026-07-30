from __future__ import annotations

import random

import pytest

from fpl_andres.simulation.season import (
    LineupRules,
    SquadGameweek,
    simulate_season,
)
from fpl_andres.simulation.squad import (
    Candidate,
    SquadRules,
    SquadSelectionError,
    build_squad,
    validate_squad,
)

# The 2024-25 selection rules, supplied explicitly rather than assumed.
RULES = SquadRules(
    budget_tenths=1000,
    club_limit=3,
    position_counts={1: 2, 2: 5, 3: 5, 4: 3},
)

LINEUP = LineupRules(
    starting_size=11,
    minimum_by_position={1: 1, 2: 3, 3: 2, 4: 1},
    maximum_by_position={1: 1, 2: 5, 3: 5, 4: 3},
)


def _pool(price_tenths: int = 50, teams: int = 20) -> list[Candidate]:
    """A deep, uniformly priced pool across many clubs."""
    pool: list[Candidate] = []
    element_id = 1
    for team in range(1, teams + 1):
        for position, count in ((1, 2), (2, 5), (3, 5), (4, 3)):
            for _ in range(count):
                pool.append(
                    Candidate(
                        element_id=element_id,
                        element_code=100_000 + element_id,
                        position=position,
                        team_id=team,
                        price_tenths=price_tenths,
                    )
                )
                element_id += 1
    return pool


def test_a_built_squad_satisfies_every_selection_rule() -> None:
    squad = build_squad(_pool(), RULES, rng=random.Random(7))

    validate_squad(squad, RULES)
    assert len(squad) == 15


def test_a_built_squad_respects_the_club_limit() -> None:
    squad = build_squad(_pool(), RULES, rng=random.Random(11))

    counts: dict[int, int] = {}
    for player in squad:
        counts[player.team_id] = counts.get(player.team_id, 0) + 1
    assert max(counts.values()) <= RULES.club_limit


def test_a_built_squad_stays_inside_the_budget() -> None:
    # 6.0m uniform would cost 90.0m for 15, comfortably inside 100.0m.
    squad = build_squad(_pool(price_tenths=60), RULES, rng=random.Random(3))

    assert sum(player.price_tenths for player in squad) <= RULES.budget_tenths


def test_an_unaffordable_pool_raises_rather_than_overspending() -> None:
    with pytest.raises(SquadSelectionError):
        build_squad(_pool(price_tenths=200), RULES, rng=random.Random(5), attempts=20)


def test_a_pool_too_thin_for_a_position_is_rejected() -> None:
    pool = [player for player in _pool() if player.position != 1]

    with pytest.raises(SquadSelectionError, match="position 1"):
        build_squad(pool, RULES, rng=random.Random(5))


def test_validation_rejects_a_repeated_player() -> None:
    squad = list(build_squad(_pool(), RULES, rng=random.Random(2)))
    squad[1] = squad[0]

    with pytest.raises(SquadSelectionError, match="repeats a player"):
        validate_squad(squad, RULES)


def test_validation_rejects_an_overspent_squad() -> None:
    squad = build_squad(_pool(price_tenths=60), RULES, rng=random.Random(2))
    tight = SquadRules(budget_tenths=500, club_limit=3, position_counts=RULES.position_counts)

    with pytest.raises(SquadSelectionError, match="budget"):
        validate_squad(squad, tight)


def _squad_of(*positions: int) -> list[Candidate]:
    return [
        Candidate(
            element_id=index + 1,
            element_code=200_000 + index,
            position=position,
            team_id=(index % 5) + 1,
            price_tenths=50,
        )
        for index, position in enumerate(positions)
    ]


FIFTEEN = _squad_of(1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4)


def _all_played(points: dict[int, int]) -> dict[int, SquadGameweek]:
    return {
        pid: SquadGameweek(element_id=pid, minutes=90, points=score)
        for pid, score in points.items()
    }


def test_a_season_totals_the_starting_eleven_plus_the_captain() -> None:
    outcomes = _all_played({player.element_id: 2 for player in FIFTEEN})

    result = simulate_season(
        season="2024-25",
        label="control",
        squad=FIFTEEN,
        results_by_event={1: outcomes},
        lineup_rules=LINEUP,
    )

    # Eleven starters at two points, plus the captain counted twice.
    assert result.total_points == 11 * 2 + 2
    assert len(result.gameweeks) == 1


def test_bench_points_are_reported_but_not_scored() -> None:
    outcomes = _all_played({player.element_id: 3 for player in FIFTEEN})

    result = simulate_season(
        season="2024-25",
        label="control",
        squad=FIFTEEN,
        results_by_event={1: outcomes},
        lineup_rules=LINEUP,
    )

    week = result.gameweeks[0]
    assert week.benched_points == 4 * 3
    assert result.points_left_on_bench == 12


def test_a_starter_who_did_not_play_is_auto_subbed() -> None:
    outcomes = {player.element_id: SquadGameweek(player.element_id, 90, 2) for player in FIFTEEN}
    # Blank an outfield starter; a bench outfielder must come on.
    outcomes[3] = SquadGameweek(3, 0, 0)

    result = simulate_season(
        season="2024-25",
        label="control",
        squad=FIFTEEN,
        results_by_event={1: outcomes},
        lineup_rules=LINEUP,
        # Force a deterministic lineup so element 3 is certain to start.
        lineup_rank=lambda player: -player.element_id,
    )

    assert result.gameweeks[0].autosubs


def test_lineup_selection_cannot_see_the_gameweek_it_is_picking_for() -> None:
    """Hindsight would silently never field a blank and inflate every score."""
    played = {player.element_id: SquadGameweek(player.element_id, 90, 2) for player in FIFTEEN}
    blanked = dict(played)
    blanked[3] = SquadGameweek(3, 0, 0)

    def run(outcomes: dict[int, SquadGameweek]) -> list[int]:
        result = simulate_season(
            season="2024-25",
            label="control",
            squad=FIFTEEN,
            results_by_event={1: outcomes},
            lineup_rules=LINEUP,
            lineup_rank=lambda player: -player.element_id,
        )
        return list(result.gameweeks[0].autosubs)

    # The only difference is the realised outcome, which selection must ignore.
    assert run(played) == []
    assert run(blanked) != []


def test_a_goalkeeper_is_only_replaced_by_a_goalkeeper() -> None:
    outcomes = {player.element_id: SquadGameweek(player.element_id, 90, 2) for player in FIFTEEN}
    outcomes[1] = SquadGameweek(1, 0, 0)

    result = simulate_season(
        season="2024-25",
        label="control",
        squad=FIFTEEN,
        results_by_event={1: outcomes},
        lineup_rules=LINEUP,
    )

    subs = result.gameweeks[0].autosubs
    keeper_ids = {player.element_id for player in FIFTEEN if player.position == 1}
    assert set(subs) <= keeper_ids


def test_the_captain_is_chosen_only_from_prior_gameweeks() -> None:
    flat = _all_played({player.element_id: 1 for player in FIFTEEN})
    # Player 8 explodes in gameweek 1, so may only be captained from gameweek 2.
    gw1 = dict(flat)
    gw1[8] = SquadGameweek(8, 90, 20)

    result = simulate_season(
        season="2024-25",
        label="control",
        squad=FIFTEEN,
        results_by_event={1: gw1, 2: dict(flat)},
        lineup_rules=LINEUP,
    )

    assert result.gameweeks[0].captain_id != 8
    assert result.gameweeks[1].captain_id == 8


def test_every_supplied_gameweek_is_played() -> None:
    flat = _all_played({player.element_id: 1 for player in FIFTEEN})

    result = simulate_season(
        season="2024-25",
        label="control",
        squad=FIFTEEN,
        results_by_event=dict.fromkeys(range(1, 39), flat),
        lineup_rules=LINEUP,
    )

    assert len(result.gameweeks) == 38
    assert [week.event for week in result.gameweeks] == list(range(1, 39))


def test_a_formation_that_cannot_reach_the_starting_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot reach"):
        LineupRules(
            starting_size=11,
            minimum_by_position={1: 1},
            maximum_by_position={1: 1, 2: 3},
        )
