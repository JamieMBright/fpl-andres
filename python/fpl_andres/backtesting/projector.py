"""Turn corpus history into projections for one gameweek.

Deliberately drives the promoted model code rather than reimplementing its
maths. A backtest that scores a copy of the models proves nothing about what
actually ships.

The leak guard is structural: this module only ever receives rows from
``SeasonCorpus.before(gameweek)``, so future observations are not merely
ignored, they are absent.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus
from fpl_andres.models.minutes import (
    AppearanceObservation,
    MinutesEvidence,
    MinutesProjection,
    project_minutes,
)
from fpl_andres.models.player_rates import (
    PlayerRateEvidence,
    PlayerRateProjection,
    RateObservation,
    RatePrior,
    project_player_rates,
)

__all__ = ["ElementProjection", "ProjectionSettings", "project_gameweek"]

_SOURCE_HASH = "sha256:" + "0" * 64
_MINUTES_PER_90 = 90.0

# Position priors, expressed per 90. Sourced from league-wide long-run rates
# rather than tuned, so the backtest cannot flatter itself by fitting them.
_GOAL_PRIOR: Mapping[int, float] = {1: 0.00, 2: 0.05, 3: 0.12, 4: 0.28}
_ASSIST_PRIOR: Mapping[int, float] = {1: 0.00, 2: 0.06, 3: 0.13, 4: 0.12}
# Appearance points only; the full scoring composition arrives with a promoted
# team-goal model. Stated here so the number is never mistaken for full xPTS.
_GOAL_POINTS: Mapping[int, int] = {1: 10, 2: 6, 3: 5, 4: 4}
_ASSIST_POINTS = 3


@dataclass(frozen=True)
class ProjectionSettings:
    """Sourced parameters. None are inferred from the data being scored."""

    decay_half_life_events: float = 4.0
    minimum_observations: int = 3
    minimum_minutes: float = 180.0
    prior_strength_events: float = 2.0
    prior_strength_minutes: float = 450.0
    blend_full_weight_minutes: float = 900.0
    prior_start_rate: float = 0.35


@dataclass(frozen=True)
class ElementProjection:
    element_id: int
    position: int
    expected_minutes: float
    expected_points: float
    minutes: MinutesProjection
    rates: PlayerRateProjection


def project_gameweek(
    corpus: SeasonCorpus,
    gameweek: int,
    *,
    settings: ProjectionSettings | None = None,
) -> list[ElementProjection]:
    """Project every element with enough history, using only earlier gameweeks."""
    config = settings or ProjectionSettings()
    history = corpus.before(gameweek)
    if not history:
        return []

    by_element: dict[int, list[ElementRow]] = {}
    for row in history:
        by_element.setdefault(row.element_id, []).append(row)

    cutoff = _cutoff_for(corpus, gameweek, history)
    projections: list[ElementProjection] = []

    for element_id, rows in by_element.items():
        position = corpus.position_by_element.get(element_id)
        if position is None or position not in _GOAL_PRIOR:
            continue

        minutes = _project_minutes(element_id, corpus.season, gameweek, rows, cutoff, config)
        if minutes.evidence_level == "unavailable":
            continue

        rates = _project_rates(element_id, corpus.season, gameweek, rows, cutoff, config, position)
        if rates.evidence_level == "unavailable":
            continue

        ninety = minutes.expected_minutes / _MINUTES_PER_90
        appearance = (
            minutes.probability_appear - minutes.probability_sixty_minutes
        ) + minutes.probability_sixty_minutes * 2
        attacking = ninety * (
            rates.goals_per_90 * _GOAL_POINTS[position] + rates.assists_per_90 * _ASSIST_POINTS
        )

        projections.append(
            ElementProjection(
                element_id=element_id,
                position=position,
                expected_minutes=minutes.expected_minutes,
                expected_points=appearance + attacking,
                minutes=minutes,
                rates=rates,
            )
        )

    return projections


def _cutoff_for(corpus: SeasonCorpus, gameweek: int, history: Sequence[ElementRow]) -> datetime:
    """The moment a decision for this gameweek had to be made."""
    upcoming = corpus.rows_by_gameweek.get(gameweek, ())
    if upcoming:
        return min(row.kickoff_time for row in upcoming)
    return max(row.kickoff_time for row in history) + timedelta(days=1)


def _project_minutes(
    element_id: int,
    season: str,
    gameweek: int,
    rows: Sequence[ElementRow],
    cutoff: datetime,
    config: ProjectionSettings,
) -> MinutesProjection:
    # One appearance per gameweek: a double gameweek's fixtures are combined,
    # because the models reason about events, not matches.
    combined: dict[int, tuple[int, bool, datetime]] = {}
    for row in rows:
        minutes, started, kickoff = combined.get(row.gameweek, (0, False, row.kickoff_time))
        combined[row.gameweek] = (
            min(minutes + row.minutes, 120),
            started or row.started or row.minutes >= 60,
            min(kickoff, row.kickoff_time),
        )

    observations = tuple(
        AppearanceObservation(
            event_id=event,
            minutes=minutes,
            started=started and minutes > 0,
            kickoff_time=min(kickoff, cutoff),
        )
        for event, (minutes, started, kickoff) in sorted(combined.items())
        if event < gameweek
    )

    evidence = MinutesEvidence(
        element_code=element_id,
        season=season,
        prediction_event=gameweek,
        observations=observations,
        decay_half_life_events=config.decay_half_life_events,
        minimum_observations=config.minimum_observations,
        prior_start_rate=config.prior_start_rate,
        prior_strength_events=config.prior_strength_events,
        prediction_cutoff=cutoff,
        data_available_at=cutoff,
        source_hashes=(_SOURCE_HASH,),
    )
    return project_minutes(evidence)


def _project_rates(
    element_id: int,
    season: str,
    gameweek: int,
    rows: Sequence[ElementRow],
    cutoff: datetime,
    config: ProjectionSettings,
    position: int,
) -> PlayerRateProjection:
    observations = tuple(
        RateObservation(
            season=season,
            event_id=row.gameweek,
            minutes=min(row.minutes, 120),
            goals=row.goals,
            assists=row.assists,
            expected_goals=row.expected_goals,
            expected_assists=row.expected_assists,
            kickoff_time=min(row.kickoff_time, cutoff),
        )
        for row in rows
        if row.gameweek < gameweek
    )

    evidence = PlayerRateEvidence(
        element_code=element_id,
        season=season,
        prediction_event=gameweek,
        current_season_observations=observations,
        prior=RatePrior(
            goals_per_90=_GOAL_PRIOR[position],
            assists_per_90=_ASSIST_PRIOR[position],
            strength_minutes=config.prior_strength_minutes,
        ),
        minimum_minutes=config.minimum_minutes,
        blend_full_weight_minutes=config.blend_full_weight_minutes,
        prediction_cutoff=cutoff,
        data_available_at=cutoff,
        source_hashes=(_SOURCE_HASH,),
    )
    return project_player_rates(evidence)


def baseline_recent_mean(
    corpus: SeasonCorpus, gameweek: int, *, window: int = 5
) -> dict[int, float]:
    """Mean points over the last ``window`` gameweeks. The naive control."""
    totals: dict[int, list[int]] = {}
    for event in range(max(1, gameweek - window), gameweek):
        for element_id, points in corpus.actual_points(event).items():
            totals.setdefault(element_id, []).append(points)
    return {
        element_id: sum(points) / len(points) for element_id, points in totals.items() if points
    }


def baseline_ownership(corpus: SeasonCorpus, gameweek: int) -> dict[int, float]:
    """Ownership at the previous gameweek. The crowd's own answer."""
    previous = gameweek - 1
    while previous >= 1:
        rows = corpus.rows_by_gameweek.get(previous, ())
        owned = {row.element_id: float(row.selected) for row in rows if row.selected is not None}
        if owned:
            return owned
        previous -= 1
    return {}
