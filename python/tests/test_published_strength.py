"""Rating a club FPL has published a strength for.

The promoted sides are the reason this exists: they have no Premier League
record, and the alternative was one hand-picked constant standing in for all
of them while FPL's own ratings sat ingested and unread.
"""

from __future__ import annotations

from fpl_andres.planning.fixture_routes import published_strength


def _team(name: str, attack: int, defence: int) -> dict[str, object]:
    return {
        "short_name": name,
        "strength_attack_home": attack,
        "strength_attack_away": attack,
        "strength_defence_home": defence,
        "strength_defence_away": defence,
    }


LEAGUE = [
    _team("STR", 1300, 1300),
    _team("MID", 1100, 1100),
    _team("WEA", 900, 900),
]


def test_the_league_mean_rates_as_exactly_even() -> None:
    rated = published_strength(_team("AVG", 1100, 1100), LEAGUE)

    assert rated is not None
    assert rated.attack_home == 1.0
    assert rated.defence_home == 1.0


def test_a_strong_attack_reads_above_one() -> None:
    rated = published_strength(LEAGUE[0], LEAGUE)

    assert rated is not None
    assert rated.attack_home > 1.0
    # FPL's defence is higher-is-better and this module's is higher-is-leakier,
    # so a strong side must come out as harder to score against, not easier.
    assert rated.defence_home < 1.0


def test_a_weak_side_reads_soft_on_both_counts() -> None:
    rated = published_strength(LEAGUE[2], LEAGUE)

    assert rated is not None
    assert rated.attack_home < 1.0
    assert rated.defence_home > 1.0


def test_a_bootstrap_with_no_strength_is_refused_rather_than_invented() -> None:
    bare = [{"short_name": "ONE"}, {"short_name": "TWO"}]

    assert published_strength(bare[0], bare) is None


def test_a_club_missing_its_own_strength_is_refused() -> None:
    assert published_strength({"short_name": "GAP"}, LEAGUE) is None


def test_a_zero_is_read_as_absent_rather_than_as_infinitely_weak() -> None:
    assert published_strength(_team("ZED", 0, 0), LEAGUE) is None
