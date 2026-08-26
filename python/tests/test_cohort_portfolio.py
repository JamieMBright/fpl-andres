"""Reconciling a cohort's picks into one portfolio.

Each test here is a way the number could be wrong while looking fine, which is
the only failure mode that matters for a signal nobody can eyeball.
"""

from __future__ import annotations

import pytest

from fpl_andres.cohorts.portfolio import (
    CoverageTooLow,
    ManagerPicks,
    Pick,
    reconcile,
)


def squad(
    entry_id: int,
    element_ids: list[int],
    *,
    captain: int,
    vice: int,
    event: int = 1,
    chip: str | None = None,
    benched: tuple[int, ...] = (),
) -> ManagerPicks:
    return ManagerPicks(
        entry_id=entry_id,
        event=event,
        active_chip=chip,
        picks=tuple(
            Pick(
                element_id=element_id,
                position=index + 1,
                multiplier=0 if element_id in benched else (2 if element_id == captain else 1),
                is_captain=element_id == captain,
                is_vice_captain=element_id == vice,
            )
            for index, element_id in enumerate(element_ids)
        ),
    )


def test_ownership_is_measured_against_the_cohort_asked_not_the_one_that_answered() -> None:
    captured = [squad(i, [1, 2, 3], captain=1, vice=2) for i in range(95)]

    portfolio = reconcile(
        captured, event=1, attempted=100, cohort_revision="r1", minimum_coverage=0.9
    )

    assert portfolio.responded == 95
    assert portfolio.attempted == 100
    assert portfolio.coverage == pytest.approx(0.95)
    # Shares are over who was counted, and coverage is published beside them so
    # the missing five are visible rather than absorbed.
    assert portfolio.holdings[0].owned_share == pytest.approx(1.0)


def test_a_thin_sample_is_refused_rather_than_published() -> None:
    captured = [squad(i, [1, 2, 3], captain=1, vice=2) for i in range(40)]

    with pytest.raises(CoverageTooLow, match="below the 90% floor"):
        reconcile(captured, event=1, attempted=100, cohort_revision="r1")


def test_effective_ownership_puts_the_armband_on_top_of_the_holding() -> None:
    # Ten managers, all own player 1, six captain it.
    captured = [squad(i, [1, 2, 3], captain=1 if i < 6 else 2, vice=3) for i in range(10)]

    portfolio = reconcile(captured, event=1, attempted=10, cohort_revision="r1")
    one = next(h for h in portfolio.holdings if h.element_id == 1)

    assert one.owned_share == pytest.approx(1.0)
    assert one.captained_share == pytest.approx(0.6)
    # Started once each, captained by six: 10 + 6 over 10.
    assert one.effective_ownership == pytest.approx(1.6)


def test_a_triple_captain_counts_for_two_extra_not_one() -> None:
    plain = [squad(i, [1, 2], captain=1, vice=2) for i in range(9)]
    tripled = [squad(9, [1, 2], captain=1, vice=2, chip="3xc")]

    portfolio = reconcile(plain + tripled, event=1, attempted=10, cohort_revision="r1")
    one = next(h for h in portfolio.holdings if h.element_id == 1)

    # Ten starts, nine ordinary armbands, one triple worth two: 10 + 9 + 2.
    assert one.effective_ownership == pytest.approx(2.1)


def test_free_hit_squads_are_excluded_from_holdings_and_counted() -> None:
    real = [squad(i, [1, 2], captain=1, vice=2) for i in range(8)]
    rented = [squad(8 + i, [7, 8], captain=7, vice=8, chip="freehit") for i in range(2)]

    portfolio = reconcile(real + rented, event=1, attempted=10, cohort_revision="r1")

    assert portfolio.free_hit == 2
    assert portfolio.counted == 8
    assert {h.element_id for h in portfolio.holdings} == {1, 2}
    # A one-week rental must not read as the cohort buying a player.
    assert all(h.element_id not in (7, 8) for h in portfolio.holdings)


def test_a_benched_player_is_owned_but_not_started() -> None:
    captured = [squad(i, [1, 2, 3], captain=1, vice=2, benched=(3,)) for i in range(10)]

    portfolio = reconcile(captured, event=1, attempted=10, cohort_revision="r1")
    three = next(h for h in portfolio.holdings if h.element_id == 3)

    assert three.owned_share == pytest.approx(1.0)
    assert three.started_share == pytest.approx(0.0)
    assert three.effective_ownership == pytest.approx(0.0)


def test_holdings_come_back_ordered_by_exposure() -> None:
    captured = [squad(i, [1, 2, 3], captain=1 if i < 7 else 2, vice=3) for i in range(10)]

    portfolio = reconcile(captured, event=1, attempted=10, cohort_revision="r1")
    exposures = [h.effective_ownership for h in portfolio.holdings]

    assert exposures == sorted(exposures, reverse=True)


def test_the_cohort_revision_travels_with_the_snapshot() -> None:
    captured = [squad(i, [1, 2], captain=1, vice=2, event=4) for i in range(10)]

    portfolio = reconcile(captured, event=4, attempted=10, cohort_revision="sweep-2026-08-03")

    # Without this a series whose population changed looks like managers moving.
    assert portfolio.cohort_revision == "sweep-2026-08-03"
    assert portfolio.event == 4


def test_ranked_500_basis_travels_with_its_separate_snapshot() -> None:
    captured = [squad(i, [1, 2], captain=1, vice=2) for i in range(10)]

    portfolio = reconcile(
        captured,
        event=1,
        attempted=10,
        cohort_revision="sha256:pinned",
        basis="ranked-500",
    )

    assert portfolio.basis == "ranked-500"


def test_picks_from_the_wrong_gameweek_are_named_not_folded_in() -> None:
    captured = [squad(i, [1, 2], captain=1, vice=2) for i in range(9)]
    captured.append(squad(99, [1, 2], captain=1, vice=2, event=2))

    with pytest.raises(ValueError, match="99"):
        reconcile(captured, event=1, attempted=10, cohort_revision="r1")


def test_a_manager_captured_twice_is_refused() -> None:
    captured = [squad(1, [1, 2], captain=1, vice=2) for _ in range(2)]
    captured.extend(squad(i + 10, [1, 2], captain=1, vice=2) for i in range(8))

    with pytest.raises(ValueError, match="captured more than once"):
        reconcile(captured, event=1, attempted=10, cohort_revision="r1")


def test_more_answers_than_managers_asked_is_a_bug_not_a_bonus() -> None:
    captured = [squad(i, [1], captain=1, vice=1) for i in range(11)]

    with pytest.raises(ValueError, match="more managers answered"):
        reconcile(captured, event=1, attempted=10, cohort_revision="r1")


def test_an_empty_cohort_is_refused() -> None:
    with pytest.raises(ValueError, match="needs a cohort"):
        reconcile([], event=1, attempted=0, cohort_revision="r1")


def test_an_all_free_hit_gameweek_yields_no_portfolio() -> None:
    captured = [squad(i, [1, 2], captain=1, vice=2, chip="freehit") for i in range(10)]

    with pytest.raises(CoverageTooLow, match="every captured squad was a Free Hit"):
        reconcile(captured, event=1, attempted=10, cohort_revision="r1")


def test_vice_captains_are_recorded_because_the_armband_can_move() -> None:
    captured = [squad(i, [1, 2], captain=1, vice=2) for i in range(10)]

    portfolio = reconcile(captured, event=1, attempted=10, cohort_revision="r1")
    two = next(h for h in portfolio.holdings if h.element_id == 2)

    assert two.vice_captained == 10
