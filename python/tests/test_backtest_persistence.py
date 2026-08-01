"""Persisting backtest runs, and refusing to persist an unattributable one."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from fpl_andres.backtesting.score import GameweekScore, MethodScore
from fpl_andres.persistence.backtest import BacktestRecord, persist_backtest

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
REVISION = "a" * 40


class FakeClient:
    def __init__(self) -> None:
        self.writes: list[tuple[str, list[Mapping[str, Any]]]] = []

    def insert(
        self,
        table: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        returning: bool = False,
        **_: Any,
    ) -> list[dict[str, Any]]:
        self.writes.append((table, list(rows)))
        if not returning:
            return []
        return [{"id": f"run-{index}"} for index, _ in enumerate(rows)]


def score(spearman: float | None = 0.5) -> MethodScore:
    outcome = MethodScore(label="model")
    outcome.scored = 100
    outcome.absolute_error = 150.0
    outcome.squared_error = 400.0
    outcome.signed_error = -20.0
    outcome.gameweeks.append(
        GameweekScore(gameweek=7, scored=100, spearman=spearman, top_n_hits=8, top_n=10)
    )
    return outcome


def record(season: str = "2024-25", method: str = "model") -> BacktestRecord:
    return BacktestRecord(
        season=season,
        method=method,
        first_scored_gameweek=7,
        score=score(),
        data_available_at=NOW,
    )


def test_a_run_carries_the_revision_that_produced_it() -> None:
    client = FakeClient()

    persist_backtest(client, [record()], revision=REVISION)  # type: ignore[arg-type]

    table, rows = client.writes[0]
    assert table == "backtest_runs"
    assert rows[0]["code_revision"] == REVISION
    assert rows[0]["season"] == "2024-25"


def test_a_run_carries_the_corpus_it_was_measured_over() -> None:
    """#153. code_revision answered which code ran; nothing answered over which
    data. The corpus is a mutable table, so without this a moved metric is
    indistinguishable from a moved model."""
    client = FakeClient()
    fingerprint = f"sha256:{'a' * 64}"

    persist_backtest(  # type: ignore[arg-type]
        client,
        [
            BacktestRecord(
                season="2024-25",
                method="model",
                first_scored_gameweek=7,
                score=score(),
                data_available_at=NOW,
                corpus_fingerprint=fingerprint,
            )
        ],
        revision=REVISION,
    )

    _, rows = client.writes[0]
    assert rows[0]["corpus_fingerprint"] == fingerprint


def test_a_run_that_cannot_name_its_corpus_says_null_rather_than_guessing() -> None:
    """Rows written before the column existed genuinely do not know their
    corpus, and a plausible wrong hash is worse than an honest gap."""
    client = FakeClient()

    persist_backtest(client, [record()], revision=REVISION)  # type: ignore[arg-type]

    _, rows = client.writes[0]
    assert rows[0]["corpus_fingerprint"] is None


def test_nothing_is_written_for_an_empty_run_list() -> None:
    client = FakeClient()

    assert persist_backtest(client, [], revision=REVISION) == []  # type: ignore[arg-type]
    assert client.writes == []


def test_predictions_are_attached_to_the_run_that_produced_them() -> None:
    client = FakeClient()

    persist_backtest(
        client,  # type: ignore[arg-type]
        [record()],
        revision=REVISION,
        predictions={
            ("2024-25", "model"): [
                {"gameweek": 7, "element_id": 1, "predicted_points": 5.0, "actual_points": 6}
            ]
        },
    )

    table, rows = client.writes[1]
    assert table == "backtest_predictions"
    assert rows[0]["run_id"] == "run-0"
    assert rows[0]["element_id"] == 1


def test_predictions_for_a_method_that_was_not_run_are_ignored() -> None:
    client = FakeClient()

    persist_backtest(
        client,  # type: ignore[arg-type]
        [record(method="model")],
        revision=REVISION,
        predictions={("2024-25", "recent_mean"): [{"gameweek": 7, "element_id": 1}]},
    )

    assert [table for table, _ in client.writes] == ["backtest_runs"]


def test_per_position_correlations_are_persisted_as_their_own_columns() -> None:
    client = FakeClient()
    entry = record()
    entry.score.by_position["DEF"] = [(1.0, 2.0), (2.0, 4.0), (3.0, 6.0)]

    persist_backtest(client, [entry], revision=REVISION)  # type: ignore[arg-type]

    _, rows = client.writes[0]
    assert rows[0]["spearman_def"] == pytest.approx(1.0)
    assert rows[0]["spearman_gkp"] is None
