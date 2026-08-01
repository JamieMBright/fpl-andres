"""Persist backtest results so runs can be compared over time.

The calibration page ships a committed JSON artifact and keeps doing so: a claim
about a commit belongs in the commit. This serves the other need, which is
answering whether a change actually improved anything, and that needs the runs
side by side rather than one at a time.

Every run carries the git revision that produced it. Two runs of the same season
from different code are different experiments, and the unique constraint says so.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from fpl_andres.backtesting.score import MethodScore
from fpl_andres.persistence.supabase import SupabaseRestClient
from fpl_andres.positions import Position

__all__ = ["BacktestRecord", "current_revision", "persist_backtest"]


class RevisionUnavailable(RuntimeError):
    """Raised when the code revision cannot be determined."""


@dataclass(frozen=True)
class BacktestRecord:
    season: str
    method: str
    first_scored_gameweek: int
    score: MethodScore
    data_available_at: datetime


def current_revision() -> str:
    """The commit that is about to produce a run.

    Fails rather than defaulting. A metric attributed to an unknown revision
    cannot be compared to anything, so an unlabelled run is worse than none.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RevisionUnavailable("could not read the current git revision") from error

    revision = result.stdout.strip()
    if not revision:
        raise RevisionUnavailable("git reported an empty revision")
    return revision


def _positions(score: MethodScore) -> dict[str, float | None]:
    by_position = score.position_spearman()
    return {
        f"spearman_{position.code.lower()}": by_position.get(position.code) for position in Position
    }


def persist_backtest(
    client: SupabaseRestClient,
    records: Sequence[BacktestRecord],
    *,
    revision: str,
    predictions: Mapping[tuple[str, str], Sequence[Mapping[str, object]]] | None = None,
) -> list[str]:
    """Write runs and, where supplied, the predictions behind them.

    Returns the run ids in the order the records were given. Predictions are
    keyed by ``(season, method)`` so a caller can persist detail for one method
    without holding every prediction in memory at once.
    """
    if not records:
        return []

    rows = [
        {
            "season": record.season,
            "method": record.method,
            "first_scored_gameweek": record.first_scored_gameweek,
            "scored_observations": record.score.scored,
            "mean_absolute_error": record.score.mean_absolute_error,
            "root_mean_squared_error": record.score.root_mean_squared_error,
            "bias": record.score.bias,
            "spearman": record.score.mean_spearman,
            "top_n_hit_rate": record.score.top_n_hit_rate,
            **_positions(record.score),
            "code_revision": revision,
            "data_available_at": record.data_available_at.isoformat(),
        }
        for record in records
    ]

    written = client.insert("backtest_runs", rows, returning=True)
    run_ids = [str(row["id"]) for row in written]

    if predictions:
        detail: list[dict[str, object]] = []
        for record, run_id in zip(records, run_ids, strict=True):
            for entry in predictions.get((record.season, record.method), ()):
                detail.append({**entry, "run_id": run_id})
        if detail:
            client.insert("backtest_predictions", detail)

    return run_ids
