"""Score the projection method against completed seasons.

Walks each gameweek, projects from earlier gameweeks only, then reveals the
realised points. Baselines are scored on exactly the same rows so the
comparison is like for like.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from scipy.stats import spearmanr

from fpl_andres.backtesting.corpus import SeasonCorpus
from fpl_andres.backtesting.projector import (
    ProjectionSettings,
    baseline_ownership,
    baseline_recent_mean,
    project_gameweek,
)

__all__ = [
    "GameweekScore",
    "MethodScore",
    "SeasonScore",
    "score_season",
]

_POSITION_NAMES = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


@dataclass
class GameweekScore:
    gameweek: int
    scored: int
    spearman: float | None
    top_n_hits: int
    top_n: int


@dataclass
class MethodScore:
    """How one ranking method performed across a season."""

    label: str
    scored: int = 0
    absolute_error: float = 0.0
    squared_error: float = 0.0
    signed_error: float = 0.0
    gameweeks: list[GameweekScore] = field(default_factory=list)
    by_position: dict[str, list[tuple[float, float]]] = field(default_factory=dict)

    @property
    def mean_absolute_error(self) -> float | None:
        return self.absolute_error / self.scored if self.scored else None

    @property
    def root_mean_squared_error(self) -> float | None:
        return (self.squared_error / self.scored) ** 0.5 if self.scored else None

    @property
    def bias(self) -> float | None:
        return self.signed_error / self.scored if self.scored else None

    @property
    def mean_spearman(self) -> float | None:
        values = [week.spearman for week in self.gameweeks if week.spearman is not None]
        return sum(values) / len(values) if values else None

    @property
    def top_n_hit_rate(self) -> float | None:
        weeks = [week for week in self.gameweeks if week.top_n]
        if not weeks:
            return None
        return sum(week.top_n_hits for week in weeks) / sum(week.top_n for week in weeks)

    def position_spearman(self) -> dict[str, float | None]:
        out: dict[str, float | None] = {}
        for position, pairs in sorted(self.by_position.items()):
            out[position] = _spearman(
                [predicted for predicted, _ in pairs], [actual for _, actual in pairs]
            )
        return out


@dataclass
class SeasonScore:
    season: str
    first_scored_gameweek: int
    methods: dict[str, MethodScore] = field(default_factory=dict)


def score_season(
    corpus: SeasonCorpus,
    *,
    settings: ProjectionSettings | None = None,
    top_n: int = 20,
    minimum_history: int = 6,
) -> SeasonScore:
    """Score the model and its baselines over every scorable gameweek.

    ``minimum_history`` skips the opening gameweeks, where nobody has enough
    current-season evidence to project from. Scoring them would measure the
    cold-start problem rather than the method.
    """
    config = settings or ProjectionSettings()
    outcome = SeasonScore(season=corpus.season, first_scored_gameweek=minimum_history + 1)
    for label in ("model", "recent_mean", "ownership"):
        outcome.methods[label] = MethodScore(label=label)

    for gameweek in corpus.gameweeks:
        if gameweek <= minimum_history:
            continue
        actual = corpus.actual_points(gameweek)
        if not actual:
            continue

        projections = project_gameweek(corpus, gameweek, settings=config)
        model_ranking = {
            projection.element_id: projection.expected_points for projection in projections
        }
        positions = {
            projection.element_id: _POSITION_NAMES.get(projection.position, "UNK")
            for projection in projections
        }

        _score(
            outcome.methods["model"],
            gameweek,
            model_ranking,
            actual,
            top_n,
            positions,
            calibrated=True,
        )
        _score(
            outcome.methods["recent_mean"],
            gameweek,
            baseline_recent_mean(corpus, gameweek),
            actual,
            top_n,
            positions,
            calibrated=True,
        )
        _score(
            outcome.methods["ownership"],
            gameweek,
            baseline_ownership(corpus, gameweek),
            actual,
            top_n,
            positions,
            # Ownership counts are not points, so only its ranking is scored.
            calibrated=False,
        )

    return outcome


def _score(
    method: MethodScore,
    gameweek: int,
    ranking: Mapping[int, float],
    actual: Mapping[int, int],
    top_n: int,
    positions: Mapping[int, str],
    *,
    calibrated: bool,
) -> None:
    shared = [element for element in ranking if element in actual]
    if len(shared) < top_n:
        return

    predicted = [ranking[element] for element in shared]
    realised = [float(actual[element]) for element in shared]

    if calibrated:
        method.scored += len(shared)
        for value, truth in zip(predicted, realised, strict=True):
            error = value - truth
            method.absolute_error += abs(error)
            method.squared_error += error * error
            method.signed_error += error

    for element, value, truth in zip(shared, predicted, realised, strict=True):
        position = positions.get(element)
        if position:
            method.by_position.setdefault(position, []).append((value, truth))

    ordered = sorted(shared, key=lambda element: ranking[element], reverse=True)
    best = sorted(shared, key=lambda element: actual[element], reverse=True)
    hits = len(set(ordered[:top_n]) & set(best[:top_n]))

    method.gameweeks.append(
        GameweekScore(
            gameweek=gameweek,
            scored=len(shared),
            spearman=_spearman(predicted, realised),
            top_n_hits=hits,
            top_n=top_n,
        )
    )


def _spearman(predicted: Sequence[float], actual: Sequence[float]) -> float | None:
    if len(predicted) < 3:
        return None
    if len(set(predicted)) < 2 or len(set(actual)) < 2:
        return None
    value = float(spearmanr(predicted, actual).statistic)
    return None if value != value else value
