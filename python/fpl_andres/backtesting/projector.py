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

from fpl_andres.backtesting.corpus import CorpusLoadError, ElementRow, SeasonCorpus
from fpl_andres.backtesting.fixtures import (
    RouteAdjustment,
    TeamStrength,
    estimate_strength,
    route_adjustment,
)
from fpl_andres.backtesting.rates import (
    _GOAL_PRIOR,
    _MINUTES_PER_90,
    league_rates,
    project_element_minutes,
    project_element_rates,
)
from fpl_andres.backtesting.reliability import PointsShape, describe_shape
from fpl_andres.backtesting.scoring import _NEUTRAL_ADJUSTMENT, fixture_points
from fpl_andres.models.minutes import (
    MAX_EVENT,
    MinutesProjection,
)
from fpl_andres.models.player_rates import (
    PlayerRateProjection,
)

__all__ = [
    "ElementProjection",
    "HorizonProjection",
    "ProjectionSettings",
    "project_gameweek",
    "project_horizon",
]

_SOURCE_HASH = "sha256:" + "0" * 64


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
    # Weight on the player's own recent points, against the component
    # reconstruction. Realised points are a direct, unbiased reading of the
    # target; the component model is indirect and accumulates error across
    # fourteen routes. Blending beats either alone. Measured at 0.7-0.8 in all
    # seven seasons of the corpus independently, so 0.2 is not fitted to the
    # seasons it is reported against.
    recent_form_weight: float = 0.2
    recent_form_window: int = 5


@dataclass(frozen=True)
class ElementProjection:
    element_id: int
    position: int
    expected_minutes: float
    expected_points: float
    minutes: MinutesProjection
    rates: PlayerRateProjection
    fixture_count: int = 1
    # The pure component reconstruction, before recent points are blended in.
    component_points: float = 0.0
    recent_points: float | None = None


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
    league = league_rates(history, corpus.position_by_element)
    prior_nineties = config.prior_strength_minutes / _MINUTES_PER_90
    strength = estimate_strength(corpus.fixtures_before(gameweek))
    form = baseline_recent_mean(corpus, gameweek, window=config.recent_form_window)
    longest = max(horizons)
    projections: list[HorizonProjection] = []

    for element_id, rows in by_element.items():
        position = corpus.position_by_element.get(element_id)
        if position is None or position not in _GOAL_PRIOR:
            continue

        minutes = project_element_minutes(element_id, corpus.season, gameweek, rows, cutoff, config)
        if minutes.evidence_level == "unavailable":
            continue
        rates = project_element_rates(
            element_id, corpus.season, gameweek, rows, cutoff, config, position
        )
        if rates.evidence_level == "unavailable":
            continue

        running = 0.0
        fixtures_seen = 0
        points_by_horizon: dict[int, float] = {}
        fixtures_by_horizon: dict[int, int] = {}
        recent = form.get(element_id)
        for offset in range(longest):
            event = gameweek + offset
            for adjustment in _adjustments_for(corpus, element_id, event, strength):
                component = fixture_points(
                    rows, position, minutes, rates, league, prior_nineties, adjustment
                )
                running += _blend(component, recent, 1, config)
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


@dataclass(frozen=True)
class MatchProjection:
    """One player's expected points in a single match against an average side.

    Between seasons there is no fixture list to lean on and no current-season
    form to measure, so the only honest projection is a per-match rate against a
    neutral opponent. It answers "what did this footballer return, per match, on
    the evidence of the season just finished" and nothing more. It is not a
    gameweek forecast and must never be presented as one.
    """

    code: int
    element_id: int
    position: int
    web_name: str
    price_tenths: int | None
    expected_minutes: float
    expected_points: float
    shape: PointsShape
    minutes: MinutesProjection
    rates: PlayerRateProjection
    # The closing stretch of the season, which is the best guide to a player's
    # current role. A January signing who started every remaining match reads
    # nothing like a squad player with the same season total.
    recent_minutes: int = 0
    recent_starts: int = 0
    recent_matches: int = 0


def project_next_match(
    corpus: SeasonCorpus,
    *,
    settings: ProjectionSettings | None = None,
    recent_window: int = 6,
) -> list[MatchProjection]:
    """Project every player's next match from a completed season, fixture-free.

    Deliberately excludes fixture difficulty and recent form: neither exists
    before a ball is kicked. A player without enough minutes is left out rather
    than projected from a prior alone.
    """
    config = settings or ProjectionSettings()
    # 2019-20 ran to gameweek 47 after the shutdown, so the season after the
    # last one is not always a legal event. History is unaffected: `before`
    # is inclusive of everything already played.
    gameweek = min(corpus.last_event + 1, MAX_EVENT)
    history = corpus.before(corpus.last_event + 1)
    if not history:
        return []

    by_element: dict[int, list[ElementRow]] = {}
    for row in history:
        by_element.setdefault(row.element_id, []).append(row)

    cutoff = _cutoff_for(corpus, gameweek, history)
    league = league_rates(history, corpus.position_by_element)
    prior_nineties = config.prior_strength_minutes / _MINUTES_PER_90
    projections: list[MatchProjection] = []

    for element_id, rows in by_element.items():
        position = corpus.position_by_element.get(element_id)
        code = corpus.code_by_element.get(element_id)
        if position is None or position not in _GOAL_PRIOR or code is None:
            continue

        minutes = project_element_minutes(element_id, corpus.season, gameweek, rows, cutoff, config)
        if minutes.evidence_level == "unavailable":
            continue
        rates = project_element_rates(
            element_id, corpus.season, gameweek, rows, cutoff, config, position
        )
        if rates.evidence_level == "unavailable":
            continue

        recent = [row for row in rows if row.gameweek > gameweek - 1 - recent_window]
        projections.append(
            MatchProjection(
                code=code,
                element_id=element_id,
                position=position,
                web_name=corpus.name_by_element.get(element_id, ""),
                price_tenths=_latest_price(rows),
                expected_minutes=minutes.expected_minutes,
                expected_points=fixture_points(
                    rows,
                    position,
                    minutes,
                    rates,
                    league,
                    prior_nineties,
                    _NEUTRAL_ADJUSTMENT,
                ),
                shape=describe_shape(rows),
                minutes=minutes,
                rates=rates,
                recent_minutes=sum(row.minutes for row in recent),
                recent_starts=sum(1 for row in recent if row.minutes >= 60),
                recent_matches=len(recent),
            )
        )

    return projections


def project_gameweek(
    corpus: SeasonCorpus,
    gameweek: int,
    *,
    settings: ProjectionSettings | None = None,
    previous: SeasonCorpus | None = None,
) -> list[ElementProjection]:
    """Project every element with enough history, using only earlier gameweeks.

    ``previous`` supplies last season's record so an opening gameweek can be
    projected at all. A footballer with no Premier League history under either
    season is skipped rather than guessed at: promoted-club debutants and
    arrivals from other leagues have no evidence, and inventing some would be
    the silent default this product refuses. Players who have left simply do not
    appear in the current season's element list.
    """
    config = settings or ProjectionSettings()
    history = corpus.before(gameweek)
    carried = _carried_history(corpus, previous)
    if not history and not carried:
        return []

    by_element: dict[int, list[ElementRow]] = {}
    for row in history:
        by_element.setdefault(row.element_id, []).append(row)
    # Every current-season player gets an entry, even with no rows yet, so an
    # opening gameweek can still be projected from what they did last year.
    for element_id in corpus.position_by_element:
        if element_id in carried:
            by_element.setdefault(element_id, [])

    cutoff = _cutoff_for(corpus, gameweek, history, previous)
    if history:
        league = league_rates(history, corpus.position_by_element)
    elif previous is not None:
        # Element ids are reassigned each season, so last season's rows must be
        # read against last season's position map.
        league = league_rates(
            previous.before(previous.last_event + 1), previous.position_by_element
        )
    else:
        league = league_rates((), {})
    prior_nineties = config.prior_strength_minutes / _MINUTES_PER_90
    form = baseline_recent_mean(corpus, gameweek, window=config.recent_form_window)
    projections: list[ElementProjection] = []

    for element_id, rows in by_element.items():
        position = corpus.position_by_element.get(element_id)
        if position is None or position not in _GOAL_PRIOR:
            continue
        prior_rows = carried.get(element_id, ())

        minutes = project_element_minutes(
            element_id, corpus.season, gameweek, rows, cutoff, config, prior_rows
        )
        if minutes.evidence_level == "unavailable":
            continue

        rates = project_element_rates(
            element_id,
            corpus.season,
            gameweek,
            rows,
            cutoff,
            config,
            position,
            prior_rows,
            previous.season if previous else None,
        )
        if rates.evidence_level == "unavailable":
            continue

        # Scoring rates come from whichever season supplied the evidence.
        scoring_rows = rows or list(prior_rows)
        schedule = _schedule_for(corpus, element_id, gameweek)
        total = 0.0
        for adjustment in schedule:
            total += fixture_points(
                scoring_rows, position, minutes, rates, league, prior_nineties, adjustment
            )

        recent = form.get(element_id)
        projections.append(
            ElementProjection(
                element_id=element_id,
                position=position,
                expected_minutes=minutes.expected_minutes * len(schedule),
                expected_points=_blend(total, recent, len(schedule), config),
                minutes=minutes,
                rates=rates,
                fixture_count=len(schedule),
                component_points=total,
                recent_points=recent,
            )
        )

    return projections


def _carried_history(
    corpus: SeasonCorpus, previous: SeasonCorpus | None
) -> dict[int, tuple[ElementRow, ...]]:
    """Last season's rows, re-keyed onto this season's element ids."""
    if previous is None:
        return {}
    by_code = previous.rows_by_element_code()
    carried: dict[int, tuple[ElementRow, ...]] = {}
    for element_id, code in corpus.code_by_element.items():
        rows = by_code.get(code)
        if rows:
            carried[element_id] = tuple(rows)
    return carried


def _all_carried(carried: Mapping[int, tuple[ElementRow, ...]]) -> list[ElementRow]:
    return [row for rows in carried.values() for row in rows]


def _blend(
    component_points: float,
    recent_points: float | None,
    fixture_count: int,
    config: ProjectionSettings,
) -> float:
    """Weight the component reconstruction against the player's recent scoring.

    Recent points are a per-gameweek figure, so they scale with the number of
    fixtures. A player with no recent rows keeps the component estimate rather
    than being pulled toward a form value that does not exist.
    """
    if recent_points is None or config.recent_form_weight <= 0:
        return component_points
    weight = config.recent_form_weight
    return (1 - weight) * component_points + weight * recent_points * fixture_count


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


def _cutoff_for(
    corpus: SeasonCorpus,
    gameweek: int,
    history: Sequence[ElementRow],
    previous: SeasonCorpus | None = None,
) -> datetime:
    """The moment a decision for this gameweek had to be made."""
    upcoming = corpus.rows_by_gameweek.get(gameweek, ())
    if upcoming:
        return min(row.kickoff_time for row in upcoming)
    scheduled = [
        fixture.kickoff_time
        for fixture in corpus.fixtures_by_event.get(gameweek, ())
        if fixture.kickoff_time
    ]
    if scheduled:
        return min(scheduled)
    if history:
        return max(row.kickoff_time for row in history) + timedelta(days=1)
    if previous is not None:
        latest = [row.kickoff_time for rows in previous.rows_by_gameweek.values() for row in rows]
        if latest:
            return max(latest) + timedelta(days=1)
    raise CorpusLoadError(f"{corpus.season} GW{gameweek} has no schedule to date a decision from")


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
