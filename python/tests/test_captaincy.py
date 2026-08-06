"""The captain is the decision that gets multiplied, so it is scored on its own.

Every case here is about the population, not the arithmetic. A captaincy
backtest that lets a method pick from the whole league is grading hindsight;
these tests pin the shortlist to the crowd's own holdings and check that every
method faces the same choice.
"""

from __future__ import annotations

from fpl_andres.backtesting.captaincy import CaptaincyScore, score_captaincy


def _scores(*labels: str) -> dict[str, CaptaincyScore]:
    return {label: CaptaincyScore(label=label) for label in labels}


def test_each_method_picks_its_own_best_from_the_shared_shortlist() -> None:
    ownership = {1: 60.0, 2: 40.0, 3: 20.0}
    actual = {1: 2, 2: 9, 3: 14}
    scores = _scores("model", "crowd")

    score_captaincy(
        {"model": {1: 3.0, 2: 6.0, 3: 5.0}, "crowd": ownership},
        ownership,
        actual,
        scores,
        gameweek=1,
        shortlist_size=3,
    )

    # The model rates element 2 highest and banks its 9; the crowd captains the
    # most-owned and banks 2. The ceiling is element 3 for both.
    assert scores["model"].captain_points == 9
    assert scores["crowd"].captain_points == 2
    assert scores["model"].best_points == 14
    assert scores["crowd"].best_points == 14


def test_the_shortlist_is_the_most_owned_and_nothing_else() -> None:
    # Element 4 is the highest scorer in the corpus and nobody owned him, so
    # captaining him was not a decision anyone faced.
    ownership = {1: 60.0, 2: 40.0, 3: 20.0, 4: 0.4}
    actual = {1: 2, 2: 9, 3: 5, 4: 24}
    scores = _scores("model")

    score_captaincy(
        {"model": {1: 1.0, 2: 2.0, 3: 3.0, 4: 99.0}},
        ownership,
        actual,
        scores,
        gameweek=1,
        shortlist_size=3,
    )

    assert scores["model"].captain_points == 5
    assert scores["model"].best_points == 9


def test_a_player_with_no_realised_row_is_not_captainable() -> None:
    # Owned, but the gameweek holds no row for him: blank gameweek or no
    # fixture. Scoring him as zero would invent a decision and its outcome.
    ownership = {1: 60.0, 2: 40.0}
    actual = {2: 7}
    scores = _scores("model")

    score_captaincy({"model": {1: 9.0, 2: 1.0}}, ownership, actual, scores, gameweek=1)

    assert scores["model"].gameweeks == 1
    assert scores["model"].captain_points == 7


def test_regret_and_ceiling_share_are_measured_against_the_shortlist() -> None:
    ownership = {1: 50.0, 2: 30.0}
    actual = {1: 4, 2: 12}
    scores = _scores("model")

    score_captaincy({"model": {1: 8.0, 2: 2.0}}, ownership, actual, scores, gameweek=1)

    assert scores["model"].regret == 8.0
    assert scores["model"].share_of_ceiling == 4 / 12
    assert scores["model"].perfect_weeks == 0


def test_a_perfect_week_is_counted_and_leaves_no_regret() -> None:
    ownership = {1: 50.0, 2: 30.0}
    actual = {1: 13, 2: 3}
    scores = _scores("model")

    score_captaincy({"model": {1: 8.0, 2: 2.0}}, ownership, actual, scores, gameweek=1)

    assert scores["model"].perfect_weeks == 1
    assert scores["model"].regret == 0.0
    assert scores["model"].blank_weeks == 0


def test_an_appearance_and_nothing_else_counts_as_a_blank() -> None:
    ownership = {1: 50.0, 2: 30.0}
    actual = {1: 2, 2: 11}
    scores = _scores("model")

    score_captaincy({"model": {1: 8.0, 2: 2.0}}, ownership, actual, scores, gameweek=1)

    assert scores["model"].blank_weeks == 1
    assert scores["model"].blank_rate == 1.0


def test_a_gameweek_nobody_can_be_captained_in_is_skipped_not_zeroed() -> None:
    scores = _scores("model")

    score_captaincy({"model": {1: 8.0}}, {}, {1: 9}, scores, gameweek=1)

    assert scores["model"].gameweeks == 0
    assert scores["model"].mean_points is None
    assert scores["model"].regret is None


def test_a_method_that_rates_nobody_on_the_shortlist_is_not_scored() -> None:
    # Rating nobody in the pool is not a captaincy of zero, it is an absence of
    # a recommendation, and averaging it in would flatter the others.
    ownership = {1: 50.0, 2: 30.0}
    actual = {1: 4, 2: 12}
    scores = _scores("model", "silent")

    score_captaincy(
        {"model": {1: 8.0, 2: 2.0}, "silent": {99: 1.0}},
        ownership,
        actual,
        scores,
        gameweek=1,
    )

    assert scores["model"].gameweeks == 1
    assert scores["silent"].gameweeks == 0


def test_ties_in_a_ranking_resolve_the_same_way_every_run() -> None:
    ownership = {7: 50.0, 3: 40.0}
    actual = {7: 5, 3: 5}
    first = _scores("model")
    second = _scores("model")

    score_captaincy({"model": {7: 6.0, 3: 6.0}}, ownership, actual, first, gameweek=1)
    score_captaincy({"model": {3: 6.0, 7: 6.0}}, ownership, actual, second, gameweek=1)

    assert first["model"].weekly == second["model"].weekly
