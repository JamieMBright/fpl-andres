"""Persist a promotion decision with everything needed to reproduce it.

The table has existed since the projection-artifacts migration
and nothing wrote to it, so every promotion decision so far has lived only in a
log line.

A decision records the seed, the resample count and the sample size, which is
enough to re-run the bootstrap and not enough to reproduce the answer. It also
needs which code ran, over which corpus, and with which numerical libraries —
scipy's `spearmanr` and HiGHS' simplex are the parts doing the arithmetic, and
neither promises bit-identical results across versions.

A promotion that cannot be reproduced is not evidence. It is a number someone
wrote down.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime

from fpl_andres.lineage import Lineage
from fpl_andres.models.promotion import PromotionDecision
from fpl_andres.persistence.supabase import SupabaseRestClient
from fpl_andres.timeguard import require_utc

__all__ = ["persist_promotion_decision"]


def persist_promotion_decision(
    client: SupabaseRestClient,
    decision: PromotionDecision,
    *,
    workflow_run_id: str,
    season: str,
    decision_cutoff: datetime,
    baseline_model: str,
    baseline_version: str,
    candidate_model: str,
    candidate_version: str,
    data_available_at: datetime,
    source_hashes: Sequence[str],
    lineage: Lineage,
) -> str:
    """Write one decision and return its id.

    Every argument is required. A promotion attributed to an unknown model,
    revision or cutoff cannot be compared to the next one, which is the only
    thing the table is for.
    """
    require_utc(decision_cutoff, "decision_cutoff")
    require_utc(data_available_at, "data_available_at")
    if not source_hashes:
        raise ValueError("a promotion decision must cite at least one source hash")
    if data_available_at > decision_cutoff:
        raise ValueError("evidence became available after the decision cutoff")

    row = {
        "workflow_run_id": workflow_run_id,
        "season": season,
        "decision_cutoff": decision_cutoff.isoformat(),
        "baseline_model": baseline_model,
        "baseline_version": baseline_version,
        "candidate_model": candidate_model,
        "candidate_version": candidate_version,
        "metric_name": decision.paired_improvement.metric_name,
        "baseline_point": decision.baseline.point_estimate,
        "candidate_point": decision.candidate.point_estimate,
        "paired_improvement": decision.paired_improvement.point_estimate,
        "paired_improvement_lower": decision.paired_improvement.lower,
        "paired_improvement_upper": decision.paired_improvement.upper,
        "confidence": decision.paired_improvement.confidence,
        "resamples": decision.paired_improvement.resamples,
        "seed": decision.paired_improvement.seed,
        "sample_size": decision.paired_improvement.sample_size,
        "minimum_sample_size": decision.minimum_sample_size,
        "promoted": decision.promoted,
        "reason_codes": list(decision.reason_codes),
        "data_available_at": data_available_at.isoformat(),
        "source_hashes": sorted(source_hashes),
        "seed_replicates": decision.seed_replicates,
        "seeds_promoting": decision.seeds_promoting,
        "code_revision": lineage.code_revision,
        "corpus_fingerprint": lineage.corpus_fingerprint,
        "dependency_fingerprint": lineage.dependency_fingerprint,
        "dependency_versions": list(lineage.dependency_versions),
    }
    row["evaluation_hash"] = _evaluation_hash(row)

    written = client.insert("model_promotion_decisions", [row], returning=True)
    return str(written[0]["id"])


def _evaluation_hash(row: dict[str, object]) -> str:
    """Identity of the evaluation, not of the row.

    Excludes the workflow run: the same evaluation repeated by a re-triggered
    workflow is the same evaluation, and hashing the run id would hide that.
    """
    identifying = {key: value for key, value in row.items() if key != "workflow_run_id"}
    canonical = json.dumps(identifying, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
