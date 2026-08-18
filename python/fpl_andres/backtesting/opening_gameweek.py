"""Measure the production cold-start path from one season into the next."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from fpl_andres.backtesting.corpus import SeasonCorpus
from fpl_andres.backtesting.projector import ProjectionSettings, project_gameweek
from fpl_andres.models.metrics import rank_correlation

__all__ = ["OpeningGameweekScore", "score_opening_gameweek"]


@dataclass(frozen=True)
class OpeningGameweekScore:
    previous_season: str
    season: str
    predictions: Mapping[int, float]
    actual_points: Mapping[int, int]
    scored: int
    mean_absolute_error: float | None
    root_mean_squared_error: float | None
    bias: float | None
    spearman: float | None


def score_opening_gameweek(
    previous: SeasonCorpus,
    current: SeasonCorpus,
    *,
    settings: ProjectionSettings | None = None,
) -> OpeningGameweekScore:
    """Project GW1 from the prior season, then reveal current outcomes.

    The projection call receives the current corpus because it owns this
    season's player ids, roles and fixtures. Its event-one cutoff structurally
    removes every current-season result before the previous corpus is joined.
    """
    if _next_season(previous.season) != current.season:
        raise ValueError(
            f"opening validation requires adjacent seasons, got "
            f"{previous.season} and {current.season}"
        )

    predictions = {
        projection.element_id: projection.expected_points
        for projection in project_gameweek(current, 1, settings=settings, previous=previous)
    }
    realised = current.actual_points(1)
    shared = sorted(set(predictions) & set(realised))
    actual = {element: realised[element] for element in shared}
    if not shared:
        return OpeningGameweekScore(
            previous_season=previous.season,
            season=current.season,
            predictions=predictions,
            actual_points=actual,
            scored=0,
            mean_absolute_error=None,
            root_mean_squared_error=None,
            bias=None,
            spearman=None,
        )

    errors = [predictions[element] - actual[element] for element in shared]
    return OpeningGameweekScore(
        previous_season=previous.season,
        season=current.season,
        predictions=predictions,
        actual_points=actual,
        scored=len(shared),
        mean_absolute_error=sum(abs(error) for error in errors) / len(errors),
        root_mean_squared_error=(sum(error * error for error in errors) / len(errors)) ** 0.5,
        bias=sum(errors) / len(errors),
        spearman=rank_correlation(
            [predictions[element] for element in shared],
            [float(actual[element]) for element in shared],
        ),
    )


def _next_season(season: str) -> str:
    start_text, _, end_text = season.partition("-")
    if len(start_text) != 4 or len(end_text) != 2:
        raise ValueError(f"invalid season label: {season}")
    start = int(start_text)
    return f"{start + 1}-{str(start + 2)[-2:]}"
