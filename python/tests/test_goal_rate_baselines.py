from datetime import UTC, datetime, timedelta

import pytest

from fpl_andres.models.baselines import (
    InsufficientHistoryError,
    LeagueVenueGoalBaseline,
    TeamVenueGoalRateModel,
)
from fpl_andres.models.contracts import FixtureResult

KICKOFF = datetime(2026, 8, 15, 15, tzinfo=UTC)


def result(
    *,
    event: int,
    home: int,
    away: int,
    home_goals: int,
    away_goals: int,
) -> FixtureResult:
    kickoff = KICKOFF + timedelta(days=7 * (event - 1))
    return FixtureResult(
        season="2026-27",
        event=event,
        home_team_id=home,
        away_team_id=away,
        home_goals=home_goals,
        away_goals=away_goals,
        kickoff_time=kickoff,
        data_available_at=kickoff + timedelta(hours=3),
        source_hash=f"sha256:{event:064x}",
    )


OBSERVED = (
    result(event=1, home=1, away=2, home_goals=2, away_goals=1),
    result(event=2, home=2, away=1, home_goals=0, away_goals=1),
    result(event=3, home=1, away=2, home_goals=0, away_goals=0),
    result(event=4, home=2, away=1, home_goals=2, away_goals=1),
)


def test_league_baseline_uses_only_observed_home_and_away_means() -> None:
    model = LeagueVenueGoalBaseline.fit(OBSERVED, season="2026-27")

    prediction = model.predict(home_team_id=99, away_team_id=100, event=5)

    assert prediction.home_expected_goals == pytest.approx(1.0)
    assert prediction.away_expected_goals == pytest.approx(0.75)
    assert prediction.evidence_level == "inferred"
    assert prediction.reason_codes == ("league_venue_mean", "matches_used=4")


def test_team_rate_candidate_combines_attack_and_opponent_concession_rates() -> None:
    model = TeamVenueGoalRateModel.fit(
        OBSERVED,
        season="2026-27",
        minimum_matches=2,
    )

    prediction = model.predict(home_team_id=1, away_team_id=2, event=5)

    # Team 1 home attack: (2 + 0) / 2 = 1.0.
    # Team 2 away concession: (2 + 0) / 2 = 1.0.
    # Team 2 away attack: (1 + 0) / 2 = 0.5.
    # Team 1 home concession: (1 + 0) / 2 = 0.5.
    assert prediction.home_expected_goals == pytest.approx(1.0)
    assert prediction.away_expected_goals == pytest.approx(0.5)
    assert prediction.evidence_level == "experimental"
    assert prediction.reason_codes == ("team_venue_rates", "matches_used=8")


def test_team_rate_candidate_fails_closed_for_unseen_team() -> None:
    model = TeamVenueGoalRateModel.fit(
        OBSERVED,
        season="2026-27",
        minimum_matches=2,
    )

    with pytest.raises(InsufficientHistoryError, match="team 99"):
        model.predict(home_team_id=99, away_team_id=2, event=5)


def test_models_reject_cross_season_rows() -> None:
    other_season = result(event=5, home=1, away=2, home_goals=9, away_goals=9).model_copy(
        update={"season": "2025-26"}
    )

    with pytest.raises(ValueError, match="season"):
        LeagueVenueGoalBaseline.fit((*OBSERVED, other_season), season="2026-27")
