"""Tune and hold out the recent-form xPts blend without changing production."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpl_andres.backtesting.corpus import SeasonCorpus, load_season
from fpl_andres.experiments.recent_form_weight import (
    CANDIDATE_WEIGHTS,
    INCUMBENT_WEIGHT,
    SeasonWeightScore,
    evaluate_weight,
    score_recent_form_weights,
    select_weight,
)
from fpl_andres.model_version import MODEL_VERSION
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient

TRAIN_SEASONS = ("2022-23", "2023-24")
HOLDOUT_SEASONS = ("2024-25", "2025-26")
DEFAULT_OUTPUT = Path("data/experiments/recent-form-weight.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="experiment-recent-form-weight")
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _load_corpora(client: SupabaseRestClient) -> dict[str, SeasonCorpus]:
    return {season: load_season(client, season) for season in (*TRAIN_SEASONS, *HOLDOUT_SEASONS)}


def _weight_summary(scores: list[SeasonWeightScore], weight: float) -> dict[str, Any]:
    weekly = [value for score in scores for value in score.by_weight[weight].weekly_mae]
    if not weekly:
        raise ValueError(f"recent-form weight {weight} has no scored gameweeks")
    return {
        "weight": weight,
        "weeks": len(weekly),
        "meanWeeklyMae": sum(weekly) / len(weekly),
        "seasons": [
            {
                "season": score.season,
                "weeks": len(score.by_weight[weight].weekly_mae),
                "meanWeeklyMae": score.by_weight[weight].mean_mae,
                "meanSpearman": score.by_weight[weight].mean_spearman,
            }
            for score in scores
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    credentials = SupabaseCredentials.from_env(os.environ)
    with SupabaseRestClient(credentials) as client:
        corpora = _load_corpora(client)

    train_scores = [score_recent_form_weights(corpora[season]) for season in TRAIN_SEASONS]
    selected = select_weight(train_scores)
    holdout_scores = [score_recent_form_weights(corpora[season]) for season in HOLDOUT_SEASONS]
    evaluation = evaluate_weight(holdout_scores, candidate_weight=selected)
    payload = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "modelVersion": MODEL_VERSION,
        "codeRevision": args.code_revision,
        "incumbentWeight": INCUMBENT_WEIGHT,
        "candidateWeights": list(CANDIDATE_WEIGHTS),
        "trainSeasons": list(TRAIN_SEASONS),
        "holdoutSeasons": list(HOLDOUT_SEASONS),
        "trainingGrid": [_weight_summary(train_scores, weight) for weight in CANDIDATE_WEIGHTS],
        "selectedWeight": selected,
        "holdout": {
            "incumbent": _weight_summary(holdout_scores, INCUMBENT_WEIGHT),
            "candidate": _weight_summary(holdout_scores, selected),
        },
        "promotion": {
            **asdict(evaluation.decision),
            "familySize": evaluation.family_size,
            "familyCorrectedConfidence": evaluation.confidence,
            "spearmanRegressionLimit": 0.005,
            "spearmanRegressions": evaluation.spearman_regressions,
            "promotedAfterGuardrail": evaluation.promoted,
            "finalReasonCodes": list(evaluation.reason_codes),
        },
        "comparison": {
            "primaryMetric": "paired mean weekly MAE",
            "bootstrapUnit": "scored gameweek on one shared player population",
            "familyCorrection": "Bonferroni across four challengers",
            "guardrail": "no holdout-season mean Spearman regression greater than 0.005",
        },
        "corpusFingerprints": {
            season: corpus.fingerprint for season, corpus in sorted(corpora.items())
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {args.output} — selected {selected:.2f} against "
        f"{INCUMBENT_WEIGHT:.2f}; promoted={evaluation.promoted}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
