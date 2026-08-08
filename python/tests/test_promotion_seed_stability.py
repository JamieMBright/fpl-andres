"""A promotion must not depend on which seed was passed in.

The bootstrap ran once, under one seed. Measured across 40 seeds
on synthetic data with a small true edge and a 60-row sample, the candidate
promoted on 3 of them — a 7.5% chance of shipping a model on the strength of a
random number generator rather than evidence.

`seed_replicates` runs the interval again under further seeds and requires
unanimity. A split vote resolves to "not promoted" with a `seed_disagreement`
reason, because a decision that half the seeds disagree with is not a decision
about the model. Majority voting was rejected for the same reason: it would
convert a coin-flip into a confident answer.
"""

from __future__ import annotations

import random

import pytest

from fpl_andres.models.metrics import mean_absolute_error
from fpl_andres.models.promotion import TripletPrediction, evaluate_promotion

# Every test here runs hundreds of bootstrap resamples, several of them twenty
# times over to compare seeds. Genuinely slow rather than accidentally slow.
pytestmark = pytest.mark.slow


def _triplets(count: int, edge: float, noise_seed: int = 99) -> tuple[TripletPrediction, ...]:
    """Synthetic paired predictions where the candidate is `edge` less noisy."""
    rng = random.Random(noise_seed)
    rows = []
    for _ in range(count):
        observed = max(0.0, rng.gauss(6.0, 3.0))
        rows.append(
            TripletPrediction(
                baseline=max(0.0, observed + rng.gauss(0.0, 2.0)),
                candidate=max(0.0, observed + rng.gauss(0.0, 2.0 - edge)),
                observed=observed,
            )
        )
    return tuple(rows)


def _decide(triplets: tuple[TripletPrediction, ...], seed: int, replicates: int = 1) -> object:
    return evaluate_promotion(
        triplets,
        metric_name="mae",
        metric=mean_absolute_error,
        metric_direction="lower_is_better",
        resamples=400,
        seed=seed,
        confidence=0.95,
        minimum_sample_size=30,
        seed_replicates=replicates,
    )


def test_a_clear_winner_promotes_under_every_seed() -> None:
    """Replication must not block a candidate that genuinely wins."""
    data = _triplets(300, edge=0.60)
    assert all(_decide(data, seed).promoted for seed in range(6))  # type: ignore[attr-defined]


def test_a_clear_winner_still_promotes_with_replication() -> None:
    decision = _decide(_triplets(300, edge=0.60), seed=0, replicates=5)

    assert decision.promoted is True  # type: ignore[attr-defined]
    assert decision.seeds_promoting == 5  # type: ignore[attr-defined]
    assert decision.reason_codes == ("beat_baseline",)  # type: ignore[attr-defined]


def test_a_candidate_with_no_edge_never_promotes() -> None:
    decision = _decide(_triplets(200, edge=0.0), seed=0, replicates=5)

    assert decision.promoted is False  # type: ignore[attr-defined]


def test_replication_suppresses_a_seed_dependent_promotion() -> None:
    """The bug this identified, reproduced and closed.

    Forty rows and a modest edge put the interval bound close enough to zero
    that Monte Carlo error decides the outcome. Under a single seed this sample
    promotes on 7 of 20 seeds. Under eight-way unanimity it promotes on none:
    the disagreement is the finding, and shipping on a 35% coin-flip is what the
    replication exists to stop.

    Re-measured when the gate stopped reading a one-sided decision off a
    two-sided bound. The old test was twice as strict as it said it was, so the
    edge that sat on the knife-edge moved with it: 0.5 then, 0.4 now.
    """
    data = _triplets(40, edge=0.4, noise_seed=1)

    single = [_decide(data, seed).promoted for seed in range(20)]  # type: ignore[attr-defined]
    replicated = [_decide(data, seed, replicates=8).promoted for seed in range(20)]  # type: ignore[attr-defined]

    assert sum(single) == 7, "the marginal fixture drifted; re-measure before adjusting"
    assert sum(replicated) == 0


def test_a_split_vote_is_reported_rather_than_resolved_by_majority() -> None:
    """A decision that promotes on its own seed but not on every replicate must
    come back refused, and say why."""
    data = _triplets(40, edge=0.4, noise_seed=1)

    for seed in range(20):
        decision = _decide(data, seed, replicates=8)
        if decision.reason_codes == ("seed_disagreement",):  # type: ignore[attr-defined]
            assert decision.promoted is False  # type: ignore[attr-defined]
            assert 0 < decision.seeds_promoting < 8  # type: ignore[attr-defined]
            return
    raise AssertionError("the marginal fixture no longer produces a split vote")


def test_the_replicate_count_is_reported_so_a_decision_can_be_audited() -> None:
    decision = _decide(_triplets(200, edge=0.60), seed=3, replicates=4)

    assert decision.seed_replicates == 4  # type: ignore[attr-defined]
    assert decision.seeds_promoting <= 4  # type: ignore[attr-defined]


def test_one_replicate_is_the_default_and_changes_nothing() -> None:
    """Existing callers keep their behaviour exactly."""
    data = _triplets(200, edge=0.60)

    assert _decide(data, 7).promoted == _decide(data, 7, replicates=1).promoted  # type: ignore[attr-defined]


@pytest.mark.parametrize("replicates", [0, -1, True])
def test_an_invalid_replicate_count_is_refused(replicates: object) -> None:
    with pytest.raises(ValueError, match="seed_replicates must be a positive integer"):
        _decide(_triplets(60, 0.3), seed=0, replicates=replicates)  # type: ignore[arg-type]
