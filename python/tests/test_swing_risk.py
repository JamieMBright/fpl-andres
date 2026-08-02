"""The spread of a squad's swing, with correlation in it.

Audit item #28. The module docstring already said that what ownership changes is
the *spread* of outcomes, and then reported only expected values. Swing, cover
and upside are three views of one player's expectation; there was no variance
anywhere, so nothing could be said about risk at all.

The failure this closes is specific. Two Arsenal defenders do not return
independently: a clean sheet pays both, a defeat pays neither. Treating them as
independent understates the variance of a squad built around one defence --
which is the exact shape of squad this game rewards and punishes -- and would
report a narrow spread for the riskiest thing a manager can do.

Nothing here invents a covariance. It is supplied, and a missing pair is a
refusal rather than a zero, on the same rule that governs every other input in
this repository.
"""

from __future__ import annotations

import math

import pytest

from fpl_andres.planning.effective import (
    CovarianceUnavailable,
    EffectivePoints,
    RankModel,
    effective_points,
    swing_risk,
)


class Measured:
    """A covariance the caller measured. Same club correlates; nothing else."""

    def __init__(
        self,
        variance: float = 4.0,
        same_club_covariance: float = 2.0,
        clubs: dict[int, int] | None = None,
        unmeasured: set[tuple[int, int]] | None = None,
    ) -> None:
        self._variance = variance
        self._same_club = same_club_covariance
        self._clubs = clubs or {}
        self._unmeasured = unmeasured or set()

    def between(self, first: int, second: int) -> float | None:
        if (first, second) in self._unmeasured or (second, first) in self._unmeasured:
            return None
        if first == second:
            return self._variance
        if self._clubs.get(first) is not None and self._clubs.get(first) == self._clubs.get(second):
            return self._same_club
        return 0.0


def entry(element_id: int, points: float, ownership: float, owned: bool) -> EffectivePoints:
    return EffectivePoints(
        element_id=element_id,
        expected_points=points,
        effective_ownership=ownership,
        owned=owned,
    )


class TestExpectedSwing:
    def test_it_agrees_with_the_per_player_swings(self) -> None:
        entries = [
            entry(1, 6.0, 0.5, owned=True),
            entry(2, 4.0, 0.2, owned=False),
        ]
        risk = swing_risk(entries, Measured())
        assert risk.expected_swing == pytest.approx(sum(one.swing for one in entries))

    def test_a_player_the_whole_field_owns_contributes_nothing(self) -> None:
        # The arithmetic the module exists for: owning a player everyone owns
        # is worth nothing to rank, because every rival banks the same score.
        entries = [entry(1, 10.0, 1.0, owned=True)]
        risk = swing_risk(entries, Measured())
        assert risk.expected_swing == pytest.approx(0.0)
        assert risk.variance == pytest.approx(0.0)

    def test_not_owning_a_widely_owned_player_is_a_negative_swing(self) -> None:
        entries = [entry(1, 8.0, 0.8, owned=False)]
        risk = swing_risk(entries, Measured())
        assert risk.expected_swing == pytest.approx(-6.4)


class TestCorrelation:
    def test_two_players_from_one_club_are_riskier_than_two_from_different_clubs(
        self,
    ) -> None:
        # The whole point. Same expectation, same weights, more variance.
        together = [
            entry(1, 5.0, 0.1, owned=True),
            entry(2, 5.0, 0.1, owned=True),
        ]
        same_club = swing_risk(together, Measured(clubs={1: 10, 2: 10}))
        apart = swing_risk(together, Measured(clubs={1: 10, 2: 11}))

        assert same_club.expected_swing == pytest.approx(apart.expected_swing)
        assert same_club.variance > apart.variance

    def test_dropping_the_off_diagonal_terms_understates_the_spread(self) -> None:
        # Treating players as independent means exactly this: keeping the
        # diagonal and discarding the rest. The gap is the effect the item is
        # about, so it is measured rather than described.
        entries = [
            entry(1, 5.0, 0.1, owned=True),
            entry(2, 5.0, 0.1, owned=True),
            entry(3, 5.0, 0.1, owned=True),
        ]
        clubs = {1: 10, 2: 10, 3: 10}
        correlated = swing_risk(entries, Measured(clubs=clubs))

        weights = [(1.0 - one.effective_ownership) for one in entries]
        independent = sum(weight**2 * 4.0 for weight in weights)

        assert correlated.variance > independent
        # Three players, three diagonal terms and six off-diagonal ones.
        assert correlated.variance == pytest.approx(independent + 6 * 0.81 * 2.0)

    def test_a_negative_covariance_narrows_the_spread(self) -> None:
        # Hedging is real: a player and the opponent's keeper move opposite ways.
        entries = [
            entry(1, 5.0, 0.1, owned=True),
            entry(2, 5.0, 0.1, owned=True),
        ]
        hedged = swing_risk(entries, Measured(same_club_covariance=-2.0, clubs={1: 10, 2: 10}))
        uncorrelated = swing_risk(entries, Measured(clubs={1: 10, 2: 11}))
        assert hedged.variance < uncorrelated.variance

    def test_covariance_is_counted_both_ways_round(self) -> None:
        # The double sum runs over ordered pairs, so cov(i, j) and cov(j, i)
        # both appear. Counting one would halve every off-diagonal term.
        entries = [
            entry(1, 5.0, 0.0, owned=True),
            entry(2, 5.0, 0.0, owned=True),
        ]
        risk = swing_risk(entries, Measured(clubs={1: 10, 2: 10}))
        assert risk.variance == pytest.approx(4.0 + 4.0 + 2.0 + 2.0)


class TestRefusal:
    def test_an_unmeasured_pair_refuses_rather_than_assuming_zero(self) -> None:
        # Assuming zero is assuming independence, which is the error being
        # fixed. A silent zero would report a narrow spread for the riskiest
        # squad a manager can build.
        entries = [
            entry(1, 5.0, 0.1, owned=True),
            entry(2, 5.0, 0.1, owned=True),
        ]
        with pytest.raises(CovarianceUnavailable):
            swing_risk(entries, Measured(unmeasured={(1, 2)}))

    def test_the_refusal_names_the_pairs_to_go_and_measure(self) -> None:
        entries = [
            entry(1, 5.0, 0.1, owned=True),
            entry(2, 5.0, 0.1, owned=True),
        ]
        with pytest.raises(CovarianceUnavailable, match=r"1/2|2/1"):
            swing_risk(entries, Measured(unmeasured={(1, 2)}))

    def test_a_missing_variance_is_refused_too(self) -> None:
        entries = [entry(1, 5.0, 0.1, owned=True)]
        with pytest.raises(CovarianceUnavailable):
            swing_risk(entries, Measured(unmeasured={(1, 1)}))

    def test_an_inconsistent_covariance_is_not_rounded_up_to_zero(self) -> None:
        # Only reachable from a covariance that is not positive semi-definite,
        # which is a fault in the measurement. Clamping would hide it.
        entries = [
            entry(1, 5.0, 0.0, owned=True),
            entry(2, 5.0, 0.0, owned=True),
        ]
        with pytest.raises(ValueError, match="inconsistent"):
            swing_risk(
                entries, Measured(variance=1.0, same_club_covariance=-5.0, clubs={1: 1, 2: 1})
            )


class TestInterval:
    def test_it_reads_best_rank_first(self) -> None:
        model = RankModel(mean_points=50.0, standard_deviation=15.0, field_size=10_000_000)
        entries = [entry(1, 6.0, 0.2, owned=True)]
        risk = swing_risk(entries, Measured())
        low, high = risk.interval(model, 50.0)
        assert low <= high

    def test_the_range_widens_with_the_variance(self) -> None:
        model = RankModel(mean_points=50.0, standard_deviation=15.0, field_size=10_000_000)
        entries = [
            entry(1, 5.0, 0.1, owned=True),
            entry(2, 5.0, 0.1, owned=True),
        ]
        tight = swing_risk(entries, Measured(clubs={1: 10, 2: 11}))
        loose = swing_risk(entries, Measured(clubs={1: 10, 2: 10}))

        tight_low, tight_high = tight.interval(model, 50.0)
        loose_low, loose_high = loose.interval(model, 50.0)
        assert (loose_high - loose_low) > (tight_high - tight_low)

    def test_the_asymmetry_is_real_and_not_a_bug(self) -> None:
        # The rank curve is steepest in the middle of the field, so equal points
        # either way are not equal places. A test asserting symmetry would be
        # asserting the wrong thing.
        model = RankModel(mean_points=50.0, standard_deviation=15.0, field_size=10_000_000)
        entries = [entry(1, 20.0, 0.0, owned=True)]
        risk = swing_risk(entries, Measured(variance=9.0))
        centre = model.rank_of(50.0 + risk.expected_swing)
        low, high = risk.interval(model, 50.0)
        assert not math.isclose(centre - low, high - centre, rel_tol=1e-6)


class TestStandardDeviation:
    def test_it_is_the_root_of_the_variance(self) -> None:
        entries = [entry(1, 5.0, 0.0, owned=True)]
        risk = swing_risk(entries, Measured(variance=9.0))
        assert risk.variance == pytest.approx(9.0)
        assert risk.standard_deviation == pytest.approx(3.0)

    def test_an_empty_squad_has_no_swing_and_no_spread(self) -> None:
        risk = swing_risk([], Measured())
        assert risk.expected_swing == 0.0
        assert risk.standard_deviation == 0.0


class TestUnchangedBehaviour:
    def test_effective_points_still_ranks_by_swing(self) -> None:
        ranked = effective_points(
            projected={1: 6.0, 2: 4.0, 3: 8.0},
            ownership={1: 0.9, 2: 0.05, 3: 0.5},
            held=[1, 2, 3],
        )
        swings = [one.swing for one in ranked]
        assert swings == sorted(swings, reverse=True)
