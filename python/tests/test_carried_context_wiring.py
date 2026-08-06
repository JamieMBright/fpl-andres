"""The club-change discount has to fire from the projector, not just the model.

`_carried_context` discounts a carried season produced at a different club or
in a different role. It was reachable only in unit tests: every projector call
site stopped at `position`, so `team_id` was `None` on every observation, the
context resolved to "unknown", and the discount never applied. A striker who
moved from a title challenger to a relegation candidate carried his old rate at
full weight.

Tests that construct `RateObservation` directly cannot catch that, because the
gap is between the projector and the model rather than inside either. These go
through `project_gameweek`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus
from fpl_andres.backtesting.fixtures import Fixture
from fpl_andres.backtesting.projector import ElementProjection, project_gameweek

KICKOFF = datetime(2024, 8, 17, 14, 0, tzinfo=UTC)
FORWARD = 4
MOVER_CODE = 7
FILLER_CODE = 99
OPPONENT = 15


def _row(gameweek: int, element_id: int, *, goals: int, code: int, start: datetime) -> ElementRow:
    return ElementRow(
        gameweek=gameweek,
        element_id=element_id,
        element_code=code,
        fixture_id=gameweek * 100 + element_id,
        minutes=90,
        started=True,
        goals=goals,
        assists=0,
        expected_goals=float(goals),
        expected_assists=0.0,
        total_points=2 + 4 * goals,
        price_tenths=90,
        selected=500_000,
        kickoff_time=start + timedelta(days=7 * gameweek),
        clean_sheets=0,
        saves=0,
        bonus=0,
        goals_conceded=0,
    )


def _season(
    season: str,
    *,
    element_id: int,
    team_id: int,
    goals: int,
    played: int,
    fixtures: int,
    start: datetime,
) -> SeasonCorpus:
    """A season with one mover and one filler, and a fixture list beyond it.

    ``fixtures`` runs past ``played`` so the gameweek being projected has a
    match to price, which is what the projector needs to produce a number.
    """
    corpus = SeasonCorpus(season=season)
    for week in range(1, played + 1):
        corpus.rows_by_gameweek.setdefault(week, []).extend(
            (
                _row(week, element_id, goals=goals, code=MOVER_CODE, start=start),
                _row(week, 999, goals=0, code=FILLER_CODE, start=start),
            )
        )
    for week in range(1, fixtures + 1):
        corpus.fixtures_by_event.setdefault(week, []).append(
            Fixture(
                fixture_id=week,
                event=week,
                team_h=team_id,
                team_a=OPPONENT,
                kickoff_time=start + timedelta(days=7 * week),
            )
        )
    for identifier, team, code in ((element_id, team_id, MOVER_CODE), (999, OPPONENT, FILLER_CODE)):
        corpus.position_by_element[identifier] = FORWARD
        corpus.team_by_element[identifier] = team
        corpus.name_by_element[identifier] = f"player-{identifier}"
        corpus.code_by_element[identifier] = code
    for team in (team_id, OPPONENT):
        corpus.short_name_by_team[team] = f"T{team}"
        corpus.code_by_team[team] = team
    return corpus


def _mover(
    previous_team: int, current_team: int, *, previous_position: int = FORWARD
) -> ElementProjection:
    # Element ids are reassigned each summer, so the mover carries a different
    # id between seasons. That indirection is what the lookup has to survive.
    previous = _season(
        "2023-24",
        element_id=1,
        team_id=previous_team,
        goals=1,
        played=20,
        fixtures=20,
        start=KICKOFF,
    )
    previous.position_by_element[1] = previous_position
    current = _season(
        "2024-25",
        element_id=2,
        team_id=current_team,
        goals=0,
        played=3,
        fixtures=6,
        start=KICKOFF + timedelta(days=365),
    )
    projections = project_gameweek(current, 4, previous=previous)
    return next(entry for entry in projections if entry.element_id == 2)


class TestTheDiscountReachesTheProjector:
    def test_the_context_is_read_rather_than_left_unknown(self) -> None:
        # "unknown" is exactly what the bug produced on every projection.
        stayed = _mover(previous_team=3, current_team=3)
        moved = _mover(previous_team=3, current_team=8)

        assert any("carried_context=same" in code for code in stayed.rates.reason_codes)
        assert any("carried_context=changed" in code for code in moved.rates.reason_codes)

    def test_a_player_who_changed_club_is_projected_below_one_who_did_not(self) -> None:
        # Same carried record, same current record, same fixture. The only
        # difference between them is that one moved, and that has to cost him.
        stayed = _mover(previous_team=3, current_team=3)
        moved = _mover(previous_team=3, current_team=8)

        assert moved.component_points < stayed.component_points

    def test_a_player_who_changed_role_is_discounted_too(self) -> None:
        # Position is half the context: a defender converted to a forward keeps
        # his minutes and loses the meaning of his scoring rate.
        moved = _mover(previous_team=3, current_team=3, previous_position=2)

        assert any("carried_context=changed" in code for code in moved.rates.reason_codes)
