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
from fpl_andres.backtesting.fixtures import (
    RouteAdjustment,
    TeamStrength,
    estimate_strength,
    route_adjustment,
)
from fpl_andres.backtesting.reliability import PointsShape, describe_shape
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

__all__ = [
    "ElementProjection",
    "HorizonProjection",
    "ProjectionSettings",
    "project_gameweek",
    "project_horizon",
]

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
_CLEAN_SHEET_POINTS: Mapping[int, int] = {1: 4, 2: 4, 3: 1, 4: 0}
_SAVES_PER_POINT = 3
_GOALKEEPER = 1
_NEUTRAL_ADJUSTMENT = RouteAdjustment(1.0, 1.0, 1.0, 1.0, 1.0)
# Every remaining scoring route. Verified by reconstructing realised points from
# component columns: 2025-26 reconciles to 34,383 against an actual 34,382, and
# 27,353 of 27,605 rows in 2024-25 match exactly, the remainder being managers.
_CONCEDED_POINTS: Mapping[int, int] = {1: -1, 2: -1, 3: 0, 4: 0}
_CONCEDED_PER_POINT = 2
_YELLOW_CARD_POINTS = -1
_RED_CARD_POINTS = -3
_OWN_GOAL_POINTS = -2
_PENALTY_SAVE_POINTS = 5
_PENALTY_MISS_POINTS = -2
# Defensive contribution, new for 2025/26. Threshold is on the raw action count.
_DEFCON_POINTS: Mapping[int, int] = {1: 0, 2: 2, 3: 2, 4: 2}
_DEFCON_THRESHOLD: Mapping[int, int] = {2: 10, 3: 12, 4: 12}


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
    fixture_count: int = 1


@dataclass(frozen=True)
class HorizonProjection:
    """One player's cumulative expected points over several planning horizons.

    A single gameweek is a poor basis for a transfer: a player can be worth
    buying for one fixture and worth selling for the four after it. The ladder
    makes that visible instead of hiding it behind one number.
    """

    element_id: int
    position: int
    price_tenths: int | None
    points_by_horizon: Mapping[int, float]
    fixtures_by_horizon: Mapping[int, int]
    minutes: MinutesProjection
    rates: PlayerRateProjection
    shape: PointsShape

    def points_over(self, horizon: int) -> float:
        return self.points_by_horizon.get(horizon, 0.0)

    def points_per_million(self, horizon: int) -> float | None:
        """Return per pound spent. None when the price is unknown."""
        if not self.price_tenths:
            return None
        return self.points_over(horizon) / (self.price_tenths / 10.0)


def project_horizon(
    corpus: SeasonCorpus,
    gameweek: int,
    *,
    horizons: Sequence[int] = (1, 3, 5, 7),
    settings: ProjectionSettings | None = None,
) -> list[HorizonProjection]:
    """Project each horizon from one fixed read of history.

    Form is measured once, at ``gameweek``, and held across the horizon. Only
    the fixture schedule varies, because that is the only thing genuinely known
    in advance. Projecting future form from future results would be a leak.
    """
    config = settings or ProjectionSettings()
    history = corpus.before(gameweek)
    if not history:
        return []

    by_element: dict[int, list[ElementRow]] = {}
    for row in history:
        by_element.setdefault(row.element_id, []).append(row)

    cutoff = _cutoff_for(corpus, gameweek, history)
    league = _league_rates(history, corpus.position_by_element)
    prior_nineties = config.prior_strength_minutes / _MINUTES_PER_90
    strength = estimate_strength(corpus.fixtures_before(gameweek))
    longest = max(horizons)
    projections: list[HorizonProjection] = []

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

        running = 0.0
        fixtures_seen = 0
        points_by_horizon: dict[int, float] = {}
        fixtures_by_horizon: dict[int, int] = {}
        for offset in range(longest):
            event = gameweek + offset
            for adjustment in _adjustments_for(corpus, element_id, event, strength):
                running += _fixture_points(
                    rows, position, minutes, rates, league, prior_nineties, adjustment
                )
                fixtures_seen += 1
            if offset + 1 in horizons:
                points_by_horizon[offset + 1] = running
                fixtures_by_horizon[offset + 1] = fixtures_seen

        projections.append(
            HorizonProjection(
                element_id=element_id,
                position=position,
                price_tenths=_latest_price(rows),
                points_by_horizon=points_by_horizon,
                fixtures_by_horizon=fixtures_by_horizon,
                minutes=minutes,
                rates=rates,
                shape=describe_shape(rows),
            )
        )

    return projections


def _latest_price(rows: Sequence[ElementRow]) -> int | None:
    for row in sorted(rows, key=lambda entry: entry.gameweek, reverse=True):
        if row.price_tenths is not None:
            return row.price_tenths
    return None


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
    league = _league_rates(history, corpus.position_by_element)
    prior_nineties = config.prior_strength_minutes / _MINUTES_PER_90
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

        schedule = _schedule_for(corpus, element_id, gameweek)
        total = 0.0
        for adjustment in schedule:
            total += _fixture_points(
                rows, position, minutes, rates, league, prior_nineties, adjustment
            )

        projections.append(
            ElementProjection(
                element_id=element_id,
                position=position,
                expected_minutes=minutes.expected_minutes * len(schedule),
                expected_points=total,
                minutes=minutes,
                rates=rates,
                fixture_count=len(schedule),
            )
        )

    return projections


def _schedule_for(corpus: SeasonCorpus, element_id: int, gameweek: int) -> list[RouteAdjustment]:
    """One adjustment per fixture: two in a double, none in a blank.

    A corpus with no fixture table falls back to a single neutral fixture, so a
    caller without schedule data keeps the previous behaviour rather than
    silently projecting every player at zero.
    """
    strength = corpus.strength_cache.get(gameweek)
    if strength is None:
        strength = estimate_strength(corpus.fixtures_before(gameweek))
        corpus.strength_cache[gameweek] = strength
    return _adjustments_for(corpus, element_id, gameweek, strength)


def _adjustments_for(
    corpus: SeasonCorpus,
    element_id: int,
    gameweek: int,
    strength: Mapping[int, TeamStrength],
) -> list[RouteAdjustment]:
    if not corpus.fixtures_by_event:
        return [_NEUTRAL_ADJUSTMENT]
    team_id = corpus.team_by_element.get(element_id)
    if team_id is None:
        return [_NEUTRAL_ADJUSTMENT]

    adjustments: list[RouteAdjustment] = []
    for fixture in corpus.fixtures_for(team_id, gameweek):
        opponent = fixture.opponent_of(team_id)
        if opponent is None:
            adjustments.append(_NEUTRAL_ADJUSTMENT)
            continue
        adjustments.append(
            route_adjustment(strength, team_id, opponent, home=fixture.is_home(team_id))
        )
    return adjustments


def _fixture_points(
    rows: Sequence[ElementRow],
    position: int,
    minutes: MinutesProjection,
    rates: PlayerRateProjection,
    league: LeagueRates,
    prior_nineties: float,
    adjustment: RouteAdjustment,
) -> float:
    ninety = minutes.expected_minutes / _MINUTES_PER_90
    appearance = (
        minutes.probability_appear - minutes.probability_sixty_minutes
    ) + minutes.probability_sixty_minutes * 2
    attacking = (
        ninety
        * (rates.goals_per_90 * _GOAL_POINTS[position] + rates.assists_per_90 * _ASSIST_POINTS)
        * adjustment.attacking
    )
    supporting = _supporting_points(rows, position, minutes, league, prior_nineties, adjustment)
    return appearance + attacking + supporting


@dataclass(frozen=True)
class LeagueRates:
    """Per-position, per-90 route rates measured across every player to date.

    Used as the shrinkage target for thin individual histories. Measured rather
    than chosen, so a rarely-seen route cannot be given a flattering prior, and
    computed only from gameweeks earlier than the one being projected.
    """

    conceded_deductions: Mapping[int, float]
    yellow_cards: Mapping[int, float]
    red_cards: Mapping[int, float]
    own_goals: Mapping[int, float]
    penalties_saved: Mapping[int, float]
    penalties_missed: Mapping[int, float]
    defcon_hits: Mapping[int, float]


def _league_rates(
    rows: Sequence[ElementRow], position_by_element: Mapping[int, int]
) -> LeagueRates:
    nineties: dict[int, float] = {}
    totals: dict[str, dict[int, float]] = {
        name: {}
        for name in (
            "conceded",
            "yellow",
            "red",
            "own_goal",
            "pen_saved",
            "pen_missed",
            "defcon",
        )
    }
    defcon_nineties: dict[int, float] = {}

    for row in rows:
        if row.minutes <= 0:
            continue
        position = position_by_element.get(row.element_id)
        if position is None:
            continue
        played = row.minutes / _MINUTES_PER_90
        nineties[position] = nineties.get(position, 0.0) + played
        totals["conceded"][position] = totals["conceded"].get(position, 0.0) + (
            row.goals_conceded // _CONCEDED_PER_POINT
        )
        totals["yellow"][position] = totals["yellow"].get(position, 0.0) + row.yellow_cards
        totals["red"][position] = totals["red"].get(position, 0.0) + row.red_cards
        totals["own_goal"][position] = totals["own_goal"].get(position, 0.0) + row.own_goals
        totals["pen_saved"][position] = totals["pen_saved"].get(position, 0.0) + row.penalties_saved
        totals["pen_missed"][position] = (
            totals["pen_missed"].get(position, 0.0) + row.penalties_missed
        )
        threshold = _DEFCON_THRESHOLD.get(position)
        if threshold is not None and row.defensive_contribution is not None:
            defcon_nineties[position] = defcon_nineties.get(position, 0.0) + played
            if row.defensive_contribution >= threshold:
                totals["defcon"][position] = totals["defcon"].get(position, 0.0) + 1

    def per_ninety(name: str, denominator: Mapping[int, float]) -> dict[int, float]:
        return {
            position: totals[name].get(position, 0.0) / played
            for position, played in denominator.items()
            if played > 0
        }

    return LeagueRates(
        conceded_deductions=per_ninety("conceded", nineties),
        yellow_cards=per_ninety("yellow", nineties),
        red_cards=per_ninety("red", nineties),
        own_goals=per_ninety("own_goal", nineties),
        penalties_saved=per_ninety("pen_saved", nineties),
        penalties_missed=per_ninety("pen_missed", nineties),
        defcon_hits=per_ninety("defcon", defcon_nineties),
    )


def _shrunk_rate(
    events: float, nineties_played: float, prior: float, prior_nineties: float
) -> float:
    """Observed rate pulled toward the league rate in proportion to how thin it is."""
    return (events + prior * prior_nineties) / (nineties_played + prior_nineties)


def _supporting_points(
    rows: Sequence[ElementRow],
    position: int,
    minutes: MinutesProjection,
    league: LeagueRates,
    prior_nineties: float,
    adjustment: RouteAdjustment,
) -> float:
    """Every scoring route other than appearance, goals and assists.

    Priced from the player's own observed rate, shrunk toward the league rate for
    the position. These routes are position-specific, so omitting them shifts
    whole positions against each other rather than simply adding noise.
    """
    appearances = [row for row in rows if row.minutes > 0]
    if not appearances:
        return 0.0

    played = len(appearances)
    ninety = minutes.expected_minutes / _MINUTES_PER_90
    nineties_played = sum(row.minutes for row in appearances) / _MINUTES_PER_90

    def rate(events: float, prior: float) -> float:
        return _shrunk_rate(events, nineties_played, prior, prior_nineties)

    clean_sheet_rate = sum(row.clean_sheets for row in appearances) / played
    total = (
        minutes.probability_sixty_minutes
        * clean_sheet_rate
        * _CLEAN_SHEET_POINTS.get(position, 0)
        * adjustment.clean_sheet
    )
    total += ninety * (sum(row.bonus for row in appearances) / played)

    if position == _GOALKEEPER:
        total += (
            ninety
            * (sum(row.saves for row in appearances) / played)
            / _SAVES_PER_POINT
            * adjustment.saves
        )
        total += (
            ninety
            * rate(
                sum(row.penalties_saved for row in appearances),
                league.penalties_saved.get(position, 0.0),
            )
            * _PENALTY_SAVE_POINTS
        )

    conceded_points = _CONCEDED_POINTS.get(position, 0)
    if conceded_points:
        deductions = sum(row.goals_conceded // _CONCEDED_PER_POINT for row in appearances)
        total += (
            ninety
            * rate(deductions, league.conceded_deductions.get(position, 0.0))
            * conceded_points
            * adjustment.conceding
        )

    routes = (
        (sum(row.yellow_cards for row in appearances), league.yellow_cards, _YELLOW_CARD_POINTS),
        (sum(row.red_cards for row in appearances), league.red_cards, _RED_CARD_POINTS),
        (sum(row.own_goals for row in appearances), league.own_goals, _OWN_GOAL_POINTS),
        (
            sum(row.penalties_missed for row in appearances),
            league.penalties_missed,
            _PENALTY_MISS_POINTS,
        ),
    )
    for events, league_rate, points in routes:
        total += ninety * rate(events, league_rate.get(position, 0.0)) * points

    total += (
        _defensive_contribution_points(
            appearances, position, ninety, league, prior_nineties, nineties_played
        )
        * adjustment.defensive_contribution
    )

    return total


def _defensive_contribution_points(
    appearances: Sequence[ElementRow],
    position: int,
    ninety: float,
    league: LeagueRates,
    prior_nineties: float,
    nineties_played: float,
) -> float:
    """Zero before 2025/26, where the column is absent because the route did not exist."""
    threshold = _DEFCON_THRESHOLD.get(position)
    if threshold is None:
        return 0.0
    observed = [row for row in appearances if row.defensive_contribution is not None]
    if not observed:
        return 0.0
    hits = sum(1 for row in observed if (row.defensive_contribution or 0) >= threshold)
    seen = sum(row.minutes for row in observed) / _MINUTES_PER_90
    rate = _shrunk_rate(hits, seen, league.defcon_hits.get(position, 0.0), prior_nineties)
    # Scaled by the share of the player's history that even had the column.
    coverage = min(1.0, seen / nineties_played) if nineties_played > 0 else 0.0
    return ninety * rate * _DEFCON_POINTS[position] * coverage


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
