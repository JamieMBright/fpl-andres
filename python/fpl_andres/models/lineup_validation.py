"""Compare a dated probable XI with model probabilities and the actual team."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime

from fpl_andres.timeguard import require_utc


def _fold_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


@dataclass(frozen=True)
class LineupPrior:
    club: str
    fixture_id: int
    cutoff: str
    source: str
    expected_names: tuple[str, ...]
    least_confident: tuple[str, ...] = ()


@dataclass(frozen=True)
class LineupCandidate:
    element_id: int
    name: str
    start_probability: float


@dataclass(frozen=True)
class LineupValidation:
    prior_names: tuple[str, ...]
    model_names: tuple[str, ...]
    overlap: int
    actual_names: tuple[str, ...] | None
    actual_overlap: int | None
    model_actual_overlap: int | None
    brier_score: float | None


def evaluate_lineup_prior(
    prior: LineupPrior,
    candidates: list[LineupCandidate],
    *,
    lineup_size: int = 11,
    actual_element_ids: set[int] | None = None,
) -> LineupValidation:
    """Evaluate without promoting the external prior into model evidence."""
    cutoff = datetime.fromisoformat(prior.cutoff.replace("Z", "+00:00"))
    require_utc(cutoff, "cutoff")
    if lineup_size <= 0:
        raise ValueError("lineup_size must be positive")
    if len({candidate.element_id for candidate in candidates}) != len(candidates):
        raise ValueError("lineup candidates must have unique element ids")
    for candidate in candidates:
        if not 0.0 <= candidate.start_probability <= 1.0:
            raise ValueError("start_probability must be between zero and one")

    ranked = sorted(
        candidates,
        key=lambda candidate: (-candidate.start_probability, candidate.element_id),
    )
    selected = ranked[:lineup_size]
    prior_names = tuple(prior.expected_names)
    model_names = tuple(candidate.name for candidate in selected)
    prior_keys = {_fold_name(name) for name in prior_names}
    model_keys = {_fold_name(name) for name in model_names}
    overlap = len(prior_keys & model_keys)
    if actual_element_ids is None:
        return LineupValidation(
            prior_names=prior_names,
            model_names=model_names,
            overlap=overlap,
            actual_names=None,
            actual_overlap=None,
            model_actual_overlap=None,
            brier_score=None,
        )

    actual = [candidate for candidate in candidates if candidate.element_id in actual_element_ids]
    actual_names = tuple(sorted(candidate.name for candidate in actual))
    actual_name_set = {_fold_name(name) for name in actual_names}
    brier = sum(
        (candidate.start_probability - (1.0 if candidate.element_id in actual_element_ids else 0.0))
        ** 2
        for candidate in candidates
    ) / len(candidates)
    return LineupValidation(
        prior_names=prior_names,
        model_names=model_names,
        overlap=overlap,
        actual_names=actual_names,
        actual_overlap=len(prior_keys & actual_name_set),
        model_actual_overlap=len(model_keys & actual_name_set),
        brier_score=brier,
    )


__all__ = [
    "LineupCandidate",
    "LineupPrior",
    "LineupValidation",
    "evaluate_lineup_prior",
]
