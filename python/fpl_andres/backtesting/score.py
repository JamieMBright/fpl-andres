"""Score the projection method against completed seasons.

Walks each gameweek, projects from earlier gameweeks only, then reveals the
realised points. Baselines are scored on exactly the same rows so the
comparison is like for like.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from fpl_andres.backtesting.captain_policies import CaptainCandidate
from fpl_andres.backtesting.corpus import SeasonCorpus
from fpl_andres.backtesting.projector import (
    ProjectionSettings,
    baseline_ownership,
    baseline_recent_deviation,
    baseline_recent_mean,
    project_gameweek,
)
from fpl_andres.models.backtest import CALIBRATION_BAND_EDGES, CalibrationBand
from fpl_andres.models.metrics import rank_correlation
from fpl_andres.positions import PositionUnknown, position_code

__all__ = [
    "METHOD_LABELS",
    "GameweekScore",
    "MethodScore",
    "SeasonScore",
    "score_season",
]

#: Every ranking scored, in the order a reader should read them. ``components``
#: is the model with the recent-form blend removed, so the two together say how
#: much of the model's lead is its own pricing and how much is the naive term it
#: carries. Publishing only ``model`` hid that.
METHOD_LABELS = ("model", "components", "recent_mean", "ownership")


def _position_label(element_type: int) -> str:
    """A backtest spans seasons whose element types this package may not know.

    Assistant Manager was element_type 5 in 2024/25 and was removed for 2026/27,
    so a historical corpus legitimately contains one. Scoring labels it rather
    than refusing the whole season, which is the one place a placeholder is
    correct: it groups the rows instead of pricing them.
    """
    try:
        return position_code(element_type)
    except PositionUnknown:
        return "UNK"


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
    #: Band index -> [rows, summed projection, summed outcome]. Kept as running
    #: totals rather than retained rows because a season is ~11k predictions and
    #: nothing needs them individually.
    band_totals: dict[int, list[float]] = field(default_factory=dict)

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

    def calibration(self) -> tuple[CalibrationBand, ...]:
        """Mean projection against mean outcome, banded by what was projected."""
        bands: list[CalibrationBand] = []
        for index, (low, high) in enumerate(_band_bounds()):
            totals = self.band_totals.get(index)
            if not totals or totals[0] == 0:
                continue
            rows = int(totals[0])
            bands.append(
                CalibrationBand(
                    label=f"{low:g}+" if high is None else f"{low:g}-{high:g}",
                    lower=low,
                    upper=high,
                    count=rows,
                    mean_predicted=totals[1] / rows,
                    mean_actual=totals[2] / rows,
                )
            )
        return tuple(bands)


@dataclass
class SeasonScore:
    season: str
    first_scored_gameweek: int
    methods: dict[str, MethodScore] = field(default_factory=dict)
    #: Full pre-deadline candidates, retained so simulated legal XIs can be
    #: scored after their season has been played.
    captain_candidates: dict[int, tuple[CaptainCandidate, ...]] = field(default_factory=dict)


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
    for label in METHOD_LABELS:
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
        component_ranking = {
            projection.element_id: projection.component_points for projection in projections
        }
        positions = {
            projection.element_id: _position_label(projection.position)
            for projection in projections
        }
        recent = baseline_recent_mean(corpus, gameweek)
        deviation = baseline_recent_deviation(corpus, gameweek)
        ownership = baseline_ownership(corpus, gameweek)

        # Every method is scored on the same players. Left to their own
        # populations, the naive baseline is handed several hundred fringe
        # players who never appear and trivially score zero, which inflates a
        # rank correlation without demonstrating any skill.
        population = [
            element
            for element in model_ranking
            if element in actual and element in recent and element in ownership
        ]

        for label, ranking, calibrated in (
            ("model", model_ranking, True),
            ("components", component_ranking, True),
            ("recent_mean", recent, True),
            # Ownership counts are not points, so only its ranking is scored.
            ("ownership", ownership, False),
        ):
            _score(
                outcome.methods[label],
                gameweek,
                ranking,
                actual,
                top_n,
                positions,
                population,
                calibrated=calibrated,
            )

        # Retained until the legal season simulation has named the model-owned
        # XI. Scoring against any larger set would invent reachable captains.
        candidates = _captain_candidates(projections, recent, deviation, ownership)
        outcome.captain_candidates[gameweek] = tuple(candidates)

    return outcome


def _captain_candidates(
    projections: Sequence[object],
    recent: Mapping[int, float],
    deviation: Mapping[int, float],
    ownership: Mapping[int, float],
) -> list[CaptainCandidate]:
    """Everything a policy is allowed to read, and nothing it is not.

    Built here rather than inside the policies so no policy can reach past this
    boundary into the corpus and see the gameweek it is deciding.

    Ownership is rescaled to 0-100 against the most-owned player of the week.
    The corpus stores `selected` as a count of managers, which is of the order
    of a million, and the two rank policies price ownership in points per
    percentage point. Handed the raw count they were arithmetic rather than
    theses: the template term swamped every projection and reduced to "captain
    the most owned", and the differential term to "captain the least owned",
    which is how a policy that nobody proposed scored 3.3 points a week.
    """
    most_owned = max(ownership.values(), default=0.0)
    candidates: list[CaptainCandidate] = []
    for projection in projections:
        element = projection.element_id  # type: ignore[attr-defined]
        if element not in ownership:
            continue
        candidates.append(
            CaptainCandidate(
                element_id=element,
                expected_points=projection.expected_points,  # type: ignore[attr-defined]
                component_points=projection.component_points,  # type: ignore[attr-defined]
                recent_points=recent.get(element),
                recent_deviation=deviation.get(element, 0.0),
                probability_start=projection.minutes.probability_start,  # type: ignore[attr-defined]
                ownership=100.0 * ownership[element] / most_owned if most_owned else 0.0,
                ceiling_points=projection.expected_points  # type: ignore[attr-defined]
                * projection.ceiling_ratio,  # type: ignore[attr-defined]
                fixture_ease=projection.attacking_multiplier,  # type: ignore[attr-defined]
            )
        )
    return candidates


def _score(
    method: MethodScore,
    gameweek: int,
    ranking: Mapping[int, float],
    actual: Mapping[int, int],
    top_n: int,
    positions: Mapping[int, str],
    population: Sequence[int],
    *,
    calibrated: bool,
) -> None:
    shared = [element for element in population if element in ranking]
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
            totals = method.band_totals.setdefault(_band_index(value), [0.0, 0.0, 0.0])
            totals[0] += 1.0
            totals[1] += value
            totals[2] += truth

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


def _band_bounds() -> list[tuple[float, float | None]]:
    bounds: list[tuple[float, float | None]] = []
    lower = 0.0
    for edge in CALIBRATION_BAND_EDGES:
        bounds.append((lower, edge))
        lower = edge
    bounds.append((lower, None))
    return bounds


def _band_index(value: float) -> int:
    """Which band a projection falls in. Anything below zero joins the first."""
    for index, edge in enumerate(CALIBRATION_BAND_EDGES):
        if value < edge:
            return index
    return len(CALIBRATION_BAND_EDGES)


def _spearman(predicted: Sequence[float], actual: Sequence[float]) -> float | None:
    return rank_correlation(predicted, actual)
