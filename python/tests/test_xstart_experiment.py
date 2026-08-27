from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus
from fpl_andres.backtesting.fixtures import Fixture
from fpl_andres.backtesting.projector import ProjectionSettings, project_gameweek
from fpl_andres.cli.experiment_xstart import _aggregate_by_code
from fpl_andres.experiments.xstart import ChronologicalAppearance, score_gw2_xstart

KICKOFF = datetime(2024, 8, 17, 14, tzinfo=UTC)
CODE = 101


def _row(
    season_start: datetime,
    gameweek: int,
    element_id: int,
    *,
    started: bool,
) -> ElementRow:
    return ElementRow(
        gameweek=gameweek,
        element_id=element_id,
        element_code=CODE,
        fixture_id=gameweek * 100 + element_id,
        minutes=90 if started else 20,
        started=started,
        goals=0,
        assists=0,
        expected_goals=0.1,
        expected_assists=0.1,
        total_points=2 if started else 0,
        price_tenths=80,
        selected=100_000,
        kickoff_time=season_start + timedelta(days=7 * gameweek),
    )


def _previous() -> SeasonCorpus:
    corpus = SeasonCorpus(season="2024-25")
    corpus.position_by_element[1] = 4
    corpus.team_by_element[1] = 1
    corpus.name_by_element[1] = "Returning"
    corpus.code_by_element[1] = CODE
    for gameweek in range(1, 39):
        corpus.rows_by_gameweek[gameweek] = [_row(KICKOFF, gameweek, 1, started=False)]
    return corpus


def _previous_with_short_starts() -> SeasonCorpus:
    corpus = _previous()
    for rows in corpus.rows_by_gameweek.values():
        rows[0] = replace(
            rows[0],
            minutes=45,
            started=True,
            total_points=1,
        )
    return corpus


def _current() -> SeasonCorpus:
    start = KICKOFF + timedelta(days=365)
    corpus = SeasonCorpus(season="2025-26")
    corpus.position_by_element[7] = 4
    corpus.team_by_element[7] = 1
    corpus.name_by_element[7] = "Returning"
    corpus.code_by_element[7] = CODE
    corpus.rows_by_gameweek[1] = [_row(start, 1, 7, started=True)]
    corpus.rows_by_gameweek[2] = [_row(start, 2, 7, started=True)]
    corpus.fixtures_by_event[2] = [
        Fixture(
            fixture_id=2,
            event=2,
            team_h=1,
            team_a=2,
            kickoff_time=start + timedelta(days=14),
        )
    ]
    return corpus


def test_gw2_experiment_pairs_forecasts_before_revealing_the_start() -> None:
    score = score_gw2_xstart(
        _previous(),
        _current(),
        half_life_events=4.0,
        prior_strength_events=2.0,
    )

    assert score.season == "2025-26"
    assert score.event == 2
    assert score.element_ids == (7,)
    assert score.element_codes == (CODE,)
    [triplet] = score.triplets
    assert triplet.observed == 1.0
    assert triplet.baseline < triplet.candidate < 0.8
    assert score.shipped_p60 == (triplet.baseline,)
    assert score.candidate_brier < score.baseline_brier


def test_candidate_parameters_never_move_the_fixed_baseline() -> None:
    weak = score_gw2_xstart(
        _previous(),
        _current(),
        half_life_events=4.0,
        prior_strength_events=1.0,
    )
    strong = score_gw2_xstart(
        _previous(),
        _current(),
        half_life_events=4.0,
        prior_strength_events=4.0,
    )

    assert weak.triplets[0].baseline == strong.triplets[0].baseline
    assert weak.triplets[0].candidate != strong.triplets[0].candidate


def test_more_current_lineup_weight_moves_a_gw1_starter_up() -> None:
    ordinary = score_gw2_xstart(
        _previous(),
        _current(),
        half_life_events=2.0,
        prior_strength_events=4.0,
        current_season_weight=1.0,
    )
    stronger = score_gw2_xstart(
        _previous(),
        _current(),
        half_life_events=2.0,
        prior_strength_events=4.0,
        current_season_weight=4.0,
    )

    assert stronger.triplets[0].baseline == ordinary.triplets[0].baseline
    assert stronger.triplets[0].candidate > ordinary.triplets[0].candidate


def test_more_current_lineup_weight_moves_a_gw1_benching_down() -> None:
    current = _current()
    current.rows_by_gameweek[1][0] = replace(
        current.rows_by_gameweek[1][0], minutes=20, started=False
    )
    ordinary = score_gw2_xstart(
        _previous(),
        current,
        half_life_events=2.0,
        prior_strength_events=4.0,
        current_season_weight=1.0,
    )
    stronger = score_gw2_xstart(
        _previous(),
        current,
        half_life_events=2.0,
        prior_strength_events=4.0,
        current_season_weight=4.0,
    )

    assert stronger.triplets[0].candidate < ordinary.triplets[0].candidate


def test_promoted_production_posterior_matches_the_held_out_candidate() -> None:
    previous = _previous()
    current = _current()
    experiment = score_gw2_xstart(
        previous,
        current,
        half_life_events=2.0,
        prior_strength_events=4.0,
    )
    production = project_gameweek(
        current,
        2,
        previous=previous,
        settings=ProjectionSettings(
            decay_half_life_events=2.0,
            prior_strength_events=4.0,
        ),
    )

    assert len(production) == 1
    assert production[0].minutes.probability_start == pytest.approx(
        experiment.triplets[0].candidate
    )


def test_candidate_distinguishes_the_same_event_and_fixture_across_seasons() -> None:
    current = _current()
    current.rows_by_gameweek[1][0] = replace(
        current.rows_by_gameweek[1][0],
        fixture_id=_previous().rows_by_gameweek[1][0].fixture_id,
    )

    score = score_gw2_xstart(
        _previous(),
        current,
        half_life_events=4.0,
        prior_strength_events=2.0,
    )

    assert len(score.triplets) == 1


def test_chronological_appearance_requires_a_positive_distance() -> None:
    with pytest.raises(ValueError, match="chronological distance"):
        ChronologicalAppearance(
            source_season="2025-26",
            event=1,
            fixture_id=101,
            events_before_prediction=0,
            started=True,
        )


def test_shipped_p60_reference_is_distinct_from_true_start_probability() -> None:
    score = score_gw2_xstart(
        _previous_with_short_starts(),
        _current(),
        half_life_events=4.0,
        prior_strength_events=2.0,
    )

    assert score.shipped_p60[0] < score.triplets[0].baseline


def test_gw2_double_gameweek_is_not_collapsed_to_started_either_match() -> None:
    current = _current()
    current.rows_by_gameweek[2].append(
        replace(
            current.rows_by_gameweek[2][0],
            fixture_id=999,
            minutes=0,
            started=False,
        )
    )

    with pytest.raises(ValueError, match="one fixture per player"):
        score_gw2_xstart(
            _previous(),
            current,
            half_life_events=4.0,
            prior_strength_events=2.0,
        )


def test_holdout_bootstrap_averages_repeat_players_by_stable_code() -> None:
    first = score_gw2_xstart(
        _previous(),
        _current(),
        half_life_events=4.0,
        prior_strength_events=2.0,
    )
    repeated = _aggregate_by_code([first, first])

    assert len(repeated) == 1
    assert repeated[0] == first.triplets[0]
