"""Home advantage, and each club's own share of it.

Dixon-Coles fits one home advantage for the whole league. Normalising each venue
against its own league average then divided that straight back out, so every
club came back with identical home and away multipliers and the same tie
projected the same whoever was hosting. These pin the two halves of the fix:
the league's home advantage survives, and each club gets its own measured share
of it rather than the league's.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fpl_andres.backtesting.fixtures import (
    Fixture,
    TeamStrength,
    estimate_strength,
    venue_tilt,
    with_venue_tilt,
)
from fpl_andres.planning.fixture_routes import (
    PROMOTED_STRENGTH,
    fixture_difficulty,
)

KICKOFF = datetime(2026, 8, 15, 14, 0, tzinfo=UTC)


def _fixture(identifier: int, home: int, away: int, home_goals: int, away_goals: int) -> Fixture:
    return Fixture(
        fixture_id=identifier,
        event=1 + identifier // 10,
        team_h=home,
        team_a=away,
        team_h_score=home_goals,
        team_a_score=away_goals,
        kickoff_time=KICKOFF + timedelta(days=identifier),
    )


def _even_league(home_goals: int = 2, away_goals: int = 1) -> list[Fixture]:
    """Four sides of equal quality, where the host always scores more."""
    pairs = [(h, a) for h in (1, 2, 3, 4) for a in (1, 2, 3, 4) if h != a]
    return [
        _fixture(index, home, away, home_goals, away_goals)
        for index, (home, away) in enumerate(pairs)
    ]


def test_playing_at_home_is_worth_something() -> None:
    """Every side scores twice at home and once away, so the tilt is measurable."""
    strength = estimate_strength(_even_league())

    for team in (1, 2, 3, 4):
        assert strength[team].attack_home > strength[team].attack_away


def test_a_home_side_concedes_less_than_it_does_away() -> None:
    strength = estimate_strength(_even_league())

    for team in (1, 2, 3, 4):
        assert strength[team].defence_home < strength[team].defence_away


def test_the_venue_tilt_is_measured_per_club_not_shared() -> None:
    """One side wins at home and loses away; another is the same wherever."""
    fixtures = [
        *[_fixture(index, 1, other, 4, 0) for index, other in enumerate((2, 3, 4))],
        *[_fixture(10 + index, other, 1, 2, 0) for index, other in enumerate((2, 3, 4))],
        *[_fixture(20 + index, 2, other, 2, 1) for index, other in enumerate((3, 4))],
        *[_fixture(30 + index, other, 2, 1, 2) for index, other in enumerate((3, 4))],
        _fixture(40, 3, 4, 2, 1),
        _fixture(41, 4, 3, 2, 1),
    ]
    tilts = venue_tilt(fixtures)

    fortress = tilts[1][0] / tilts[1][1]
    traveller = tilts[2][0] / tilts[2][1]
    assert fortress > traveller


def test_a_shared_advantage_is_replaced_by_each_club_s_own() -> None:
    """`with_venue_tilt` keeps the quality and re-splits it by venue."""
    base = {
        team: TeamStrength(attack_home=1.2, attack_away=1.2, defence_home=0.9, defence_away=0.9)
        for team in (1, 2, 3, 4)
    }

    adjusted = with_venue_tilt(base, _even_league())

    for team in (1, 2, 3, 4):
        assert adjusted[team].attack_home > adjusted[team].attack_away
        # The two-venue average is the quality it was handed.
        average = (adjusted[team].attack_home + adjusted[team].attack_away) / 2
        assert average == pytest.approx(1.2, abs=0.02)


def test_a_club_with_no_fixtures_keeps_the_shape_it_was_given() -> None:
    base = {9: TeamStrength(attack_home=1.0, attack_away=1.0, defence_home=1.0, defence_away=1.0)}

    adjusted = with_venue_tilt(base, _even_league())

    assert adjusted[9].attack_home == pytest.approx(1.0)
    assert adjusted[9].attack_away == pytest.approx(1.0)


def test_difficulty_is_continuous_rather_than_five_buckets() -> None:
    """Five bands threw away most of what the route model had measured."""
    strength = estimate_strength(_even_league())
    ratings = {
        fixture_difficulty([(opponent, home)], 1, strength)
        for opponent in (2, 3, 4)
        for home in (True, False)
    }

    assert all(rating is not None for rating in ratings)
    assert any(rating != round(rating) for rating in ratings if rating is not None)


def test_the_same_tie_is_harder_away_than_at_home() -> None:
    strength = estimate_strength(_even_league())

    at_home = fixture_difficulty([(2, True)], 1, strength)
    away = fixture_difficulty([(2, False)], 1, strength)

    assert at_home is not None and away is not None
    assert away > at_home


def test_difficulty_stays_inside_the_published_scale() -> None:
    lopsided = [
        *[_fixture(index, 1, other, 9, 0) for index, other in enumerate((2, 3, 4))],
        *[_fixture(10 + index, other, 1, 0, 9) for index, other in enumerate((2, 3, 4))],
        _fixture(20, 2, 3, 1, 1),
        _fixture(21, 3, 4, 1, 1),
        _fixture(22, 4, 2, 1, 1),
    ]
    strength = estimate_strength(lopsided)

    for team in (1, 2, 3, 4):
        for opponent in (1, 2, 3, 4):
            if opponent == team:
                continue
            rating = fixture_difficulty([(opponent, True)], team, strength)
            assert rating is not None
            assert 1.0 <= rating <= 5.0


def test_a_promoted_opponent_is_assumed_soft_rather_than_dropped() -> None:
    """The tie is being played, so reporting "no fixture" for it is a lie."""
    strength = estimate_strength(_even_league())
    unknown = max(strength) + 50

    rating = fixture_difficulty([(unknown, True)], 1, strength)
    known = fixture_difficulty([(2, True)], 1, strength)

    assert rating is not None and known is not None
    assert rating < known


def test_the_promoted_prior_is_worse_than_average_in_both_directions() -> None:
    assert PROMOTED_STRENGTH.attack_home < 1.0
    assert PROMOTED_STRENGTH.defence_home > 1.0


def test_a_club_with_no_record_of_its_own_cannot_be_rated() -> None:
    """Assuming the opponent is soft is a prior; inventing the side is not."""
    strength = estimate_strength(_even_league())

    assert fixture_difficulty([(2, True)], 999, strength) is None


def test_a_blank_gameweek_is_not_a_difficulty() -> None:
    strength = estimate_strength(_even_league())

    assert fixture_difficulty([], 1, strength) is None
