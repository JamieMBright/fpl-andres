from datetime import UTC, datetime, timedelta

import pytest

from fpl_andres.models.baselines import InsufficientHistoryError
from fpl_andres.models.contracts import FixtureResult
from fpl_andres.models.dixon_coles import DixonColesModel

START = datetime(2026, 8, 1, 15, tzinfo=UTC)


def fixture(
    index: int,
    *,
    home: int,
    away: int,
    home_goals: int,
    away_goals: int,
) -> FixtureResult:
    kickoff = START + timedelta(days=7 * index)
    return FixtureResult(
        season="2026-27",
        event=index + 1,
        home_team_id=home,
        away_team_id=away,
        home_goals=home_goals,
        away_goals=away_goals,
        kickoff_time=kickoff,
        data_available_at=kickoff + timedelta(hours=3),
        source_hash=f"sha256:{index + 100:064x}",
    )


OBSERVED = (
    fixture(0, home=1, away=2, home_goals=2, away_goals=0),
    fixture(1, home=2, away=1, home_goals=2, away_goals=1),
    fixture(2, home=1, away=2, home_goals=1, away_goals=0),
    fixture(3, home=2, away=1, home_goals=1, away_goals=1),
    fixture(4, home=1, away=2, home_goals=3, away_goals=1),
    fixture(5, home=2, away=1, home_goals=2, away_goals=0),
)
AS_OF = OBSERVED[-1].data_available_at


def fit_model() -> DixonColesModel:
    return DixonColesModel.fit(
        OBSERVED,
        season="2026-27",
        as_of=AS_OF,
        decay_rate=0.0,
        minimum_matches=3,
        max_iterations=500,
    )


def test_dixon_coles_returns_positive_deterministic_rates() -> None:
    first = fit_model().predict(home_team_id=1, away_team_id=2, event=7)
    second = fit_model().predict(home_team_id=1, away_team_id=2, event=7)

    assert first.home_expected_goals > first.away_expected_goals > 0
    assert first.home_expected_goals == pytest.approx(second.home_expected_goals, abs=1e-9)
    assert first.away_expected_goals == pytest.approx(second.away_expected_goals, abs=1e-9)
    assert first.evidence_level == "experimental"
    assert first.reason_codes[0] == "dixon_coles"
    assert len(first.source_hashes) == len(OBSERVED)


def test_dixon_coles_rejects_evidence_newer_than_fit_cutoff() -> None:
    with pytest.raises(ValueError, match="available after as_of"):
        DixonColesModel.fit(
            OBSERVED,
            season="2026-27",
            as_of=AS_OF - timedelta(seconds=1),
            decay_rate=0.0,
            minimum_matches=3,
            max_iterations=500,
        )


def test_dixon_coles_fails_closed_for_unseen_team() -> None:
    model = fit_model()

    with pytest.raises(InsufficientHistoryError, match="team 99"):
        model.predict(home_team_id=99, away_team_id=2, event=7)
