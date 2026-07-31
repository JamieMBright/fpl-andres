"""Separating a bad recommendation from an unlucky one."""

from __future__ import annotations

from fpl_andres.backtesting.regret import (
    Foresight,
    evaluate_gameweek,
    summarise,
)

CANDIDATES = [1, 2, 3, 4, 5]


def week(
    *,
    projected: dict[int, float],
    actual: dict[int, float],
    chosen: int | None,
    shortlist_size: int = 3,
):
    return evaluate_gameweek(
        7,
        projected=projected,
        actual=actual,
        candidates=CANDIDATES,
        chosen=chosen,
        shortlist_size=shortlist_size,
    )


def test_following_our_own_best_option_carries_no_decision_regret() -> None:
    outcome = week(
        projected={1: 9.0, 2: 5.0, 3: 4.0, 4: 3.0, 5: 2.0},
        actual={1: 2.0, 2: 2.0, 3: 2.0, 4: 2.0, 5: 14.0},
        chosen=1,
    )

    assert outcome.followed_own_model
    assert outcome.decision_regret == 0.0


def test_a_freak_return_is_charged_to_luck_not_to_the_model() -> None:
    outcome = week(
        projected={1: 9.0, 2: 5.0, 3: 4.0, 4: 3.0, 5: 2.0},
        actual={1: 2.0, 2: 2.0, 3: 2.0, 4: 2.0, 5: 14.0},
        chosen=1,
    )

    # Element 5 was our lowest projection and hauled. Nothing to learn from it.
    assert outcome.hindsight_best_element == 5
    assert outcome.foresight is Foresight.UNFORESEEABLE
    assert outcome.luck_regret == 12.0
    assert outcome.decision_regret == 0.0


def test_ignoring_our_own_ranking_is_charged_to_the_model() -> None:
    outcome = week(
        projected={1: 9.0, 2: 5.0, 3: 4.0, 4: 3.0, 5: 2.0},
        actual={1: 8.0, 2: 2.0, 3: 2.0, 4: 2.0, 5: 2.0},
        chosen=4,
    )

    assert not outcome.followed_own_model
    assert outcome.decision_regret == 6.0
    assert outcome.luck_regret == 0.0


def test_a_haul_we_had_shortlisted_is_distinguished_from_one_we_missed() -> None:
    shortlisted = week(
        projected={1: 9.0, 2: 8.0, 3: 7.0, 4: 3.0, 5: 2.0},
        actual={1: 2.0, 2: 2.0, 3: 13.0, 4: 2.0, 5: 2.0},
        chosen=1,
    )
    missed = week(
        projected={1: 9.0, 2: 8.0, 3: 7.0, 4: 3.0, 5: 2.0},
        actual={1: 2.0, 2: 2.0, 3: 2.0, 4: 2.0, 5: 13.0},
        chosen=1,
    )

    assert shortlisted.foresight is Foresight.SHORTLISTED
    assert missed.foresight is Foresight.UNFORESEEABLE


def test_getting_it_exactly_right_is_recorded_as_recommended() -> None:
    outcome = week(
        projected={1: 9.0, 2: 5.0, 3: 4.0, 4: 3.0, 5: 2.0},
        actual={1: 11.0, 2: 2.0, 3: 2.0, 4: 2.0, 5: 2.0},
        chosen=1,
    )

    assert outcome.foresight is Foresight.RECOMMENDED
    assert outcome.realised_regret == 0.0


def test_no_legal_move_scores_nothing_rather_than_inventing_a_penalty() -> None:
    outcome = evaluate_gameweek(
        7,
        projected={},
        actual={},
        candidates=[],
        chosen=None,
    )

    assert outcome.decision_regret == 0.0
    assert outcome.model_best_element is None


def test_the_avoidable_share_separates_skill_from_variance() -> None:
    disciplined = summarise(
        "2024-25",
        [
            week(
                projected={1: 9.0, 2: 5.0, 3: 4.0, 4: 3.0, 5: 2.0},
                actual={1: 2.0, 2: 2.0, 3: 2.0, 4: 2.0, 5: 14.0},
                chosen=1,
            )
        ],
        shortlist_size=3,
    )
    careless = summarise(
        "2024-25",
        [
            week(
                projected={1: 9.0, 2: 5.0, 3: 4.0, 4: 3.0, 5: 2.0},
                actual={1: 8.0, 2: 2.0, 3: 2.0, 4: 2.0, 5: 2.0},
                chosen=4,
            )
        ],
        shortlist_size=3,
    )

    assert disciplined.avoidable_share == 0.0
    assert careless.avoidable_share == 1.0


def test_foresight_shares_sum_to_one_across_a_season() -> None:
    weeks = [
        week(
            projected={1: 9.0, 2: 5.0, 3: 4.0, 4: 3.0, 5: 2.0},
            actual={1: 11.0, 2: 2.0, 3: 2.0, 4: 2.0, 5: 2.0},
            chosen=1,
        ),
        week(
            projected={1: 9.0, 2: 5.0, 3: 4.0, 4: 3.0, 5: 2.0},
            actual={1: 2.0, 2: 2.0, 3: 2.0, 4: 2.0, 5: 14.0},
            chosen=1,
        ),
    ]
    season = summarise("2024-25", weeks, shortlist_size=3)

    assert sum(season.foresight_shares.values()) == 1.0
    assert season.foresight_shares[Foresight.RECOMMENDED.value] == 0.5
