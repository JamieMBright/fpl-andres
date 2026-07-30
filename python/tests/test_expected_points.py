from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fpl_andres.models.expected_points import (
    TeamMatchContext,
    project_expected_points,
)
from fpl_andres.models.minutes import MinutesProjection
from fpl_andres.models.player_rates import PlayerRateProjection
from fpl_andres.rules import RulesSnapshot, ScoringRules

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fpl" / "bootstrap_rules_2026_27.json"
SEASON = "2025-26"
HASH = "sha256:" + "d" * 64
AVAILABLE_AT = datetime(2025, 8, 15, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def scoring() -> ScoringRules:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    snapshot = RulesSnapshot.from_bootstrap(
        document["payload"],
        season=SEASON,
        source_hash=HASH,
        weekly_free_transfers=1,
    )
    return snapshot.scoring


def _minutes(
    *,
    probability_start: float = 1.0,
    probability_appear: float = 1.0,
    probability_sixty: float = 1.0,
    expected_minutes: float = 90.0,
    evidence_level: str = "observed",
) -> MinutesProjection:
    return MinutesProjection(
        element_code=118748,
        season=SEASON,
        event=5,
        probability_start=probability_start,
        probability_appear=probability_appear,
        probability_sixty_minutes=probability_sixty,
        expected_minutes=expected_minutes,
        evidence_level=evidence_level,  # type: ignore[arg-type]
        reason_codes=("test",),
        data_available_at=AVAILABLE_AT,
        source_hashes=(HASH,),
    )


def _rates(
    *,
    goals_per_90: float = 0.5,
    assists_per_90: float = 0.3,
    evidence_level: str = "observed",
) -> PlayerRateProjection:
    return PlayerRateProjection(
        element_code=118748,
        season=SEASON,
        event=5,
        goals_per_90=goals_per_90,
        assists_per_90=assists_per_90,
        current_season_minutes=900.0,
        carried_season=None,
        carried_weight=0.0,
        evidence_level=evidence_level,  # type: ignore[arg-type]
        reason_codes=("test",),
        data_available_at=AVAILABLE_AT,
        source_hashes=(HASH,),
    )


def _context(expected_goals_conceded: float = 1.2, level: str = "observed") -> TeamMatchContext:
    return TeamMatchContext(
        expected_goals_conceded=expected_goals_conceded,
        evidence_level=level,  # type: ignore[arg-type]
    )


def test_components_sum_exactly_to_the_total(scoring: ScoringRules) -> None:
    projection = project_expected_points(
        minutes=_minutes(),
        rates=_rates(),
        position_code="MID",
        team_context=_context(),
        scoring=scoring,
    )

    assert projection.expected_points == pytest.approx(projection.breakdown.total)


def test_a_midfielder_scores_appearance_goals_assists_and_clean_sheet(
    scoring: ScoringRules,
) -> None:
    projection = project_expected_points(
        minutes=_minutes(),
        rates=_rates(goals_per_90=0.5, assists_per_90=0.3),
        position_code="MID",
        team_context=_context(1.2),
        scoring=scoring,
    )

    breakdown = projection.breakdown
    # Fixture rules: long_play 2, MID goal 5, assist 3, MID clean sheet 1.
    assert breakdown.appearance == pytest.approx(2.0)
    assert breakdown.goals == pytest.approx(0.5 * 5)
    assert breakdown.assists == pytest.approx(0.3 * 3)
    assert breakdown.clean_sheet > 0.0
    # A midfielder is not penalised for goals conceded.
    assert breakdown.goals_conceded == pytest.approx(0.0)


def test_a_defender_is_penalised_for_goals_conceded(scoring: ScoringRules) -> None:
    defender = project_expected_points(
        minutes=_minutes(),
        rates=_rates(),
        position_code="DEF",
        team_context=_context(2.5),
        scoring=scoring,
    )

    assert defender.breakdown.goals_conceded < 0.0


def test_a_stronger_defence_raises_expected_points_for_a_defender(
    scoring: ScoringRules,
) -> None:
    mean = project_expected_points(
        minutes=_minutes(),
        rates=_rates(),
        position_code="DEF",
        team_context=_context(2.0),
        scoring=scoring,
    )
    stingy = project_expected_points(
        minutes=_minutes(),
        rates=_rates(),
        position_code="DEF",
        team_context=_context(0.6),
        scoring=scoring,
    )

    assert stingy.expected_points > mean.expected_points


def test_a_clean_sheet_requires_reaching_the_long_play_threshold(
    scoring: ScoringRules,
) -> None:
    cameo = project_expected_points(
        minutes=_minutes(probability_appear=1.0, probability_sixty=0.0, expected_minutes=30.0),
        rates=_rates(),
        position_code="DEF",
        team_context=_context(0.5),
        scoring=scoring,
    )

    assert cameo.breakdown.clean_sheet == pytest.approx(0.0)
    assert cameo.breakdown.goals_conceded == pytest.approx(0.0)
    # A short appearance still scores the short-play point.
    assert cameo.breakdown.appearance == pytest.approx(1.0)


def test_expected_minutes_scale_the_attacking_components(scoring: ScoringRules) -> None:
    full = project_expected_points(
        minutes=_minutes(expected_minutes=90.0),
        rates=_rates(goals_per_90=1.0),
        position_code="FWD",
        team_context=_context(),
        scoring=scoring,
    )
    half = project_expected_points(
        minutes=_minutes(expected_minutes=45.0),
        rates=_rates(goals_per_90=1.0),
        position_code="FWD",
        team_context=_context(),
        scoring=scoring,
    )

    assert half.breakdown.goals == pytest.approx(full.breakdown.goals / 2)


def test_unsourced_components_are_reported_missing_rather_than_assumed_zero(
    scoring: ScoringRules,
) -> None:
    projection = project_expected_points(
        minutes=_minutes(),
        rates=_rates(),
        position_code="MID",
        team_context=_context(),
        scoring=scoring,
    )

    assert set(projection.missing_components) == {
        "saves",
        "bonus",
        "defensive_contribution",
        "cards",
    }
    assert any(reason.startswith("missing=") for reason in projection.reason_codes)


def test_supplied_components_are_included_and_leave_the_missing_list(
    scoring: ScoringRules,
) -> None:
    projection = project_expected_points(
        minutes=_minutes(),
        rates=_rates(),
        position_code="DEF",
        team_context=_context(0.8),
        scoring=scoring,
        expected_bonus=0.4,
        defensive_contribution_probability=0.35,
        expected_card_points=-0.15,
    )

    assert projection.breakdown.bonus == pytest.approx(0.4)
    assert projection.breakdown.defensive_contribution > 0.0
    assert projection.breakdown.cards == pytest.approx(-0.15)
    assert "bonus" not in projection.missing_components
    assert "saves" in projection.missing_components


def test_a_goalkeeper_scores_saves_when_a_save_rate_is_supplied(
    scoring: ScoringRules,
) -> None:
    keeper = project_expected_points(
        minutes=_minutes(),
        rates=_rates(goals_per_90=0.0, assists_per_90=0.0),
        position_code="GKP",
        team_context=_context(1.1),
        scoring=scoring,
        expected_saves_per_90=3.4,
    )

    assert keeper.breakdown.saves > 0.0
    assert "saves" not in keeper.missing_components


def test_an_unavailable_component_makes_the_whole_projection_unavailable(
    scoring: ScoringRules,
) -> None:
    projection = project_expected_points(
        minutes=_minutes(
            probability_start=0.0,
            probability_appear=0.0,
            probability_sixty=0.0,
            expected_minutes=0.0,
            evidence_level="unavailable",
        ),
        rates=_rates(),
        position_code="MID",
        team_context=_context(),
        scoring=scoring,
    )

    assert projection.evidence_level == "unavailable"
    assert projection.expected_points == 0.0
    assert projection.breakdown.total == 0.0


def test_evidence_level_degrades_to_the_worst_input(scoring: ScoringRules) -> None:
    projection = project_expected_points(
        minutes=_minutes(evidence_level="observed"),
        rates=_rates(evidence_level="inferred"),
        position_code="MID",
        team_context=_context(level="observed"),
        scoring=scoring,
    )

    # A carried-forward rate must not be laundered into an observed projection.
    assert projection.evidence_level == "inferred"


def test_a_position_absent_from_the_rules_fails_rather_than_defaulting(
    scoring: ScoringRules,
) -> None:
    with pytest.raises(KeyError, match="must fail rather than default"):
        project_expected_points(
            minutes=_minutes(),
            rates=_rates(),
            position_code="SWEEPER",
            team_context=_context(),
            scoring=scoring,
        )


def test_mismatched_projections_are_rejected(scoring: ScoringRules) -> None:
    other_player = _rates()
    mismatched = other_player.model_copy(update={"element_code": 999})

    with pytest.raises(ValueError, match="same player"):
        project_expected_points(
            minutes=_minutes(),
            rates=mismatched,
            position_code="MID",
            team_context=_context(),
            scoring=scoring,
        )


def test_clean_sheet_probability_follows_the_poisson_zero(scoring: ScoringRules) -> None:
    context = _context(0.0)

    # A side expected to concede nothing keeps a clean sheet with certainty.
    assert context.clean_sheet_probability == pytest.approx(1.0)
    assert _context(2.0).clean_sheet_probability == pytest.approx(0.1353, abs=1e-4)
