"""Tune and hold out the current-plus-carried xStart candidate."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpl_andres.backtesting.corpus import SeasonCorpus, load_season
from fpl_andres.experiments.xstart import Gw2XStartScore, score_gw2_xstart
from fpl_andres.model_version import MODEL_VERSION
from fpl_andres.models.promotion import TripletPrediction, evaluate_promotion
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient

TRAIN_SEASONS = ("2022-23", "2023-24")
HOLDOUT_SEASONS = ("2024-25", "2025-26")
HALF_LIVES = (2.0, 4.0, 8.0)
PRIOR_STRENGTHS = (1.0, 2.0, 4.0)
DEFAULT_OUTPUT = Path("data/experiments/xstart-current-season.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="experiment-xstart")
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _previous_season(season: str) -> str:
    start, _, end = season.partition("-")
    if len(start) != 4 or len(end) != 2:
        raise ValueError(f"invalid season label: {season}")
    year = int(start)
    return f"{year - 1}-{str(year)[-2:]}"


def _brier(
    predicted: Sequence[float],
    observed: Sequence[float],
) -> float:
    if not predicted or len(predicted) != len(observed):
        raise ValueError("Brier inputs must be non-empty and aligned")
    return sum(
        (forecast - actual) ** 2 for forecast, actual in zip(predicted, observed, strict=True)
    ) / len(predicted)


def _summarise(scores: list[Gw2XStartScore]) -> dict[str, Any]:
    triplets = tuple(row for score in scores for row in score.triplets)
    shipped = tuple(value for score in scores for value in score.shipped_p60)
    observed = tuple(row.observed for row in triplets)
    by_code = _aggregate_by_code(scores)
    return {
        "sampleSize": len(triplets),
        "uniquePlayers": len(by_code),
        "shippedP60Brier": _brier(shipped, observed),
        "baselineBrier": _brier(
            tuple(row.baseline for row in triplets),
            tuple(row.observed for row in triplets),
        ),
        "candidateBrier": _brier(
            tuple(row.candidate for row in triplets),
            tuple(row.observed for row in triplets),
        ),
        "seasons": [
            {
                "season": score.season,
                "sampleSize": len(score.triplets),
                "shippedP60Brier": score.shipped_p60_brier,
                "baselineBrier": score.baseline_brier,
                "candidateBrier": score.candidate_brier,
            }
            for score in scores
        ],
    }


def _aggregate_by_code(scores: list[Gw2XStartScore]) -> tuple[TripletPrediction, ...]:
    grouped: dict[int, list[TripletPrediction]] = {}
    for score in scores:
        for code, triplet in zip(score.element_codes, score.triplets, strict=True):
            grouped.setdefault(code, []).append(triplet)
    return tuple(
        TripletPrediction(
            baseline=sum(row.baseline for row in rows) / len(rows),
            candidate=sum(row.candidate for row in rows) / len(rows),
            observed=sum(row.observed for row in rows) / len(rows),
        )
        for _, rows in sorted(grouped.items())
    )


def _load_corpora(client: SupabaseRestClient) -> dict[str, SeasonCorpus]:
    labels = {
        *TRAIN_SEASONS,
        *HOLDOUT_SEASONS,
        *(_previous_season(season) for season in (*TRAIN_SEASONS, *HOLDOUT_SEASONS)),
    }
    return {season: load_season(client, season) for season in sorted(labels)}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    credentials = SupabaseCredentials.from_env(os.environ)
    with SupabaseRestClient(credentials) as client:
        corpora = _load_corpora(client)

    grid: list[dict[str, Any]] = []
    for half_life in HALF_LIVES:
        for prior_strength in PRIOR_STRENGTHS:
            scores = [
                score_gw2_xstart(
                    corpora[_previous_season(season)],
                    corpora[season],
                    half_life_events=half_life,
                    prior_strength_events=prior_strength,
                )
                for season in TRAIN_SEASONS
            ]
            grid.append(
                {
                    "halfLifeEvents": half_life,
                    "priorStrengthEvents": prior_strength,
                    **_summarise(scores),
                    "selectionBrier": _brier(
                        tuple(row.candidate for row in _aggregate_by_code(scores)),
                        tuple(row.observed for row in _aggregate_by_code(scores)),
                    ),
                }
            )
    selected = min(
        grid,
        key=lambda row: (
            float(row["selectionBrier"]),
            float(row["halfLifeEvents"]),
            float(row["priorStrengthEvents"]),
        ),
    )
    holdout_scores = [
        score_gw2_xstart(
            corpora[_previous_season(season)],
            corpora[season],
            half_life_events=float(selected["halfLifeEvents"]),
            prior_strength_events=float(selected["priorStrengthEvents"]),
        )
        for season in HOLDOUT_SEASONS
    ]
    holdout_triplets = _aggregate_by_code(holdout_scores)
    decision = evaluate_promotion(
        holdout_triplets,
        metric_name="brier",
        metric=_brier,
        metric_direction="lower_is_better",
        resamples=2_000,
        seed=17,
        confidence=0.95,
        minimum_sample_size=200,
        seed_replicates=3,
    )
    payload = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "modelVersion": MODEL_VERSION,
        "codeRevision": args.code_revision,
        "trainSeasons": list(TRAIN_SEASONS),
        "holdoutSeasons": list(HOLDOUT_SEASONS),
        "grid": grid,
        "selected": {
            "halfLifeEvents": selected["halfLifeEvents"],
            "priorStrengthEvents": selected["priorStrengthEvents"],
        },
        "holdout": _summarise(holdout_scores),
        "comparison": {
            "shippedReference": "reconstructed historical-only P(60+) reference",
            "baseline": "historical-only true P(start) under model 8.8 defaults",
            "candidate": "true P(start) with current-plus-carried minutes evidence",
            "bootstrapUnit": "stable player code averaged across holdout seasons",
        },
        "promotion": asdict(decision),
        "corpusFingerprints": {
            season: corpus.fingerprint for season, corpus in sorted(corpora.items())
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {args.output} — selected half-life {selected['halfLifeEvents']}, "
        f"prior {selected['priorStrengthEvents']}; promoted={decision.promoted}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
