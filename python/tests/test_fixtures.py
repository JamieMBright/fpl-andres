"""Team strength and route-specific fixture adjustment.

The central claim under test is that one difficulty number cannot serve every
scoring route: a hard fixture suppresses clean sheets while raising saves.
"""

from __future__ import annotations

from fpl_andres.backtesting.fixtures import (
    Fixture,
    estimate_strength,
    route_adjustment,
)

STRONG = 1
WEAK = 2
MIDDLING = 3


def played(fixture_id: int, home: int, away: int, home_goals: int, away_goals: int) -> Fixture:
    return Fixture(
        fixture_id=fixture_id,
        event=1 + fixture_id // 10,
        team_h=home,
        team_a=away,
        kickoff_time=None,
        team_h_score=home_goals,
        team_a_score=away_goals,
        finished=True,
    )


def league() -> list[Fixture]:
    """A strong side thrashes a weak one repeatedly; a middling side draws."""
    fixtures: list[Fixture] = []
    fixture_id = 1
    for _ in range(15):
        fixtures.append(played(fixture_id, STRONG, WEAK, 4, 0))
        fixtures.append(played(fixture_id + 1, WEAK, STRONG, 0, 4))
        fixtures.append(played(fixture_id + 2, MIDDLING, WEAK, 1, 1))
        fixtures.append(played(fixture_id + 3, WEAK, MIDDLING, 1, 1))
        fixture_id += 4
    return fixtures


def test_a_prolific_side_earns_an_attack_multiplier_above_one() -> None:
    strength = estimate_strength(league())

    assert strength[STRONG].attack_home > 1.0
    assert strength[WEAK].attack_home < 1.0


def test_a_leaky_side_earns_a_defence_multiplier_above_one() -> None:
    strength = estimate_strength(league())

    # Above one means "concedes more than average".
    assert strength[WEAK].defence_home > 1.0
    assert strength[STRONG].defence_away < 1.0


def test_a_hard_fixture_suppresses_clean_sheets_but_raises_saves() -> None:
    strength = estimate_strength(league())

    facing_the_best = route_adjustment(strength, WEAK, STRONG, home=True)

    assert facing_the_best.clean_sheet < 1.0
    assert facing_the_best.saves > 1.0
    assert facing_the_best.defensive_contribution > 1.0


def test_an_easy_fixture_does_the_opposite() -> None:
    strength = estimate_strength(league())

    facing_the_worst = route_adjustment(strength, STRONG, WEAK, home=True)

    assert facing_the_worst.clean_sheet > 1.0
    assert facing_the_worst.saves < 1.0
    assert facing_the_worst.attacking > 1.0


def test_an_unmeasured_opponent_falls_back_to_neutral_rather_than_zero() -> None:
    strength = estimate_strength(league())

    unknown = route_adjustment(strength, STRONG, 99, home=True)

    assert unknown.attacking == 1.0
    assert unknown.clean_sheet == 1.0
    assert unknown.saves == 1.0


def test_no_results_yet_produces_no_strength_rather_than_a_guess() -> None:
    unplayed = [
        Fixture(
            fixture_id=1,
            event=1,
            team_h=STRONG,
            team_a=WEAK,
            kickoff_time=None,
        )
    ]

    assert estimate_strength(unplayed) == {}


def test_a_single_freak_result_is_shrunk_toward_average() -> None:
    thrashing = [played(1, STRONG, WEAK, 9, 0)]

    strength = estimate_strength(thrashing)

    # Nine goals in one match must not read as a nine-times-average attack.
    assert strength[STRONG].attack_home < 2.0


def test_fixture_reports_opponent_and_venue_from_either_side() -> None:
    fixture = played(1, STRONG, WEAK, 2, 1)

    assert fixture.opponent_of(STRONG) == WEAK
    assert fixture.opponent_of(WEAK) == STRONG
    assert fixture.opponent_of(99) is None
    assert fixture.is_home(STRONG)
    assert not fixture.is_home(WEAK)
