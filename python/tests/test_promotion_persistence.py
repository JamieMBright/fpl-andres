"""Writing a promotion decision, with the lineage that makes it reproducible.

The table has existed since the projection-artifacts migration and nothing wrote
to it, so every promotion decision so far lived only in a log line.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from fpl_andres.lineage import Lineage
from fpl_andres.models.promotion import BootstrapResult, PromotionDecision
from fpl_andres.persistence.promotion import persist_promotion_decision

CUTOFF = datetime(2026, 8, 14, 17, 30, tzinfo=UTC)
HASH = "sha256:" + "a" * 64
REVISION = "b" * 40


class FakeClient:
    def __init__(self) -> None:
        self.writes: list[tuple[str, list[dict[str, Any]]]] = []

    def insert(
        self, table: str, rows: list[dict[str, Any]], *, returning: bool = False
    ) -> list[dict[str, Any]]:
        self.writes.append((table, rows))
        return [{"id": "00000000-0000-4000-8000-000000000001"}]


def _result(name: str = "mae", point: float = 1.0, lower: float = 0.1) -> BootstrapResult:
    return BootstrapResult(
        metric_name=name,
        point_estimate=point,
        lower=lower,
        upper=point + 1.0,
        confidence=0.95,
        resamples=2000,
        seed=7,
        sample_size=300,
    )


def _decision(promoted: bool = True, replicates: int = 5) -> PromotionDecision:
    return PromotionDecision(
        baseline=_result("mae", 2.0),
        candidate=_result("mae", 1.6),
        paired_improvement=_result("paired_mae_improvement", 0.4, 0.1),
        minimum_sample_size=30,
        promoted=promoted,
        reason_codes=("beat_baseline",) if promoted else ("ci_includes_zero",),
        seed_replicates=replicates,
        seeds_promoting=replicates if promoted else 0,
    )


def _lineage(corpus: str | None = f"sha256:{'c' * 64}") -> Lineage:
    return Lineage(
        code_revision=REVISION,
        dependency_fingerprint=f"sha256:{'d' * 64}",
        dependency_versions=("scipy==1.14.0", "numpy==2.0.0"),
        corpus_fingerprint=corpus,
    )


def _persist(client: FakeClient, **overrides: Any) -> str:
    arguments: dict[str, Any] = {
        "workflow_run_id": "00000000-0000-4000-8000-00000000000f",
        "season": "2026-27",
        "decision_cutoff": CUTOFF,
        "baseline_model": "recent_mean",
        "baseline_version": "1.0.0",
        "candidate_model": "expected_points",
        "candidate_version": "2.1.0",
        "data_available_at": CUTOFF - timedelta(hours=2),
        "source_hashes": [HASH],
        "lineage": _lineage(),
    }
    arguments.update(overrides)
    return persist_promotion_decision(client, overrides.pop("decision", _decision()), **arguments)  # type: ignore[arg-type]


def test_a_decision_records_which_code_produced_it() -> None:
    client = FakeClient()

    _persist(client)

    _, rows = client.writes[0]
    assert rows[0]["code_revision"] == REVISION


def test_a_decision_records_which_corpus_it_was_measured_over() -> None:
    """The corpus is a mutable table. Without this, a moved metric is
    indistinguishable from a moved model."""
    client = FakeClient()

    _persist(client)

    assert client.writes[0][1][0]["corpus_fingerprint"] == f"sha256:{'c' * 64}"


def test_a_decision_records_the_libraries_that_did_the_arithmetic() -> None:
    """scipy's spearmanr and HiGHS' simplex do not promise bit-identical results
    across versions."""
    client = FakeClient()

    _persist(client)

    row = client.writes[0][1][0]
    assert row["dependency_fingerprint"].startswith("sha256:")
    assert "scipy==1.14.0" in row["dependency_versions"]


def test_a_decision_records_how_many_seeds_agreed() -> None:
    client = FakeClient()

    _persist(client)

    row = client.writes[0][1][0]
    assert row["seed_replicates"] == 5
    assert row["seeds_promoting"] == 5


def test_the_table_and_the_shape_are_what_the_schema_expects() -> None:
    client = FakeClient()

    _persist(client)

    table, rows = client.writes[0]
    assert table == "model_promotion_decisions"
    assert rows[0]["promoted"] is True
    assert rows[0]["reason_codes"] == ["beat_baseline"]


def test_source_hashes_are_sorted_so_two_identical_runs_hash_alike() -> None:
    client = FakeClient()
    second = "sha256:" + "e" * 64

    _persist(client, source_hashes=[second, HASH])

    assert client.writes[0][1][0]["source_hashes"] == [HASH, second]


def test_the_evaluation_hash_ignores_the_workflow_run() -> None:
    """The same evaluation repeated by a re-triggered workflow is the same
    evaluation. Hashing the run id would hide that."""
    first, second = FakeClient(), FakeClient()

    _persist(first)
    _persist(second, workflow_run_id="00000000-0000-4000-8000-0000000000ff")

    assert first.writes[0][1][0]["evaluation_hash"] == second.writes[0][1][0]["evaluation_hash"]


def test_a_different_corpus_changes_the_evaluation_hash() -> None:
    first, second = FakeClient(), FakeClient()

    _persist(first)
    _persist(second, lineage=_lineage(corpus=f"sha256:{'f' * 64}"))

    assert first.writes[0][1][0]["evaluation_hash"] != second.writes[0][1][0]["evaluation_hash"]


def test_evidence_arriving_after_the_cutoff_is_refused() -> None:
    """The leakage rule, at the persistence boundary."""
    client = FakeClient()

    with pytest.raises(ValueError, match="after the decision cutoff"):
        _persist(client, data_available_at=CUTOFF + timedelta(minutes=1))

    assert client.writes == []


def test_a_decision_citing_no_source_is_refused() -> None:
    client = FakeClient()

    with pytest.raises(ValueError, match="at least one source hash"):
        _persist(client, source_hashes=[])


@pytest.mark.parametrize("field", ["decision_cutoff", "data_available_at"])
def test_a_naive_timestamp_is_refused(field: str) -> None:
    client = FakeClient()

    with pytest.raises(ValueError, match=r"UTC|timezone|aware"):
        _persist(client, **{field: datetime(2026, 8, 14, 17, 30)})
