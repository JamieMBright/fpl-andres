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
    route_adjustment,
    season_strength,
)
from fpl_andres.backtesting.rates import (
    _GOAL_PRIOR,
    _MINUTES_PER_90,
    league_rates,
    project_element_minutes,
    project_element_rates,
)
from fpl_andres.backtesting.reliability import PointsShape, describe_shape
from fpl_andres.backtesting.scoring import (
    _NEUTRAL_ADJUSTMENT,
    PointsBreakdown,
    fixture_points,
    fixture_points_breakdown,
)
from fpl_andres.models.minutes import (
    MAX_EVENT,
    AvailabilityEvidence,
    MinutesProjection,
)
from fpl_andres.models.player_rates import (
    PlayerRateProjection,
)
from fpl_andres.models.suspension_risk import SEASON_MATCHES, suspension_risk

__all__ = [
    "ElementProjection",
    "HorizonProjection",
    "ProjectionSettings",
    "project_gameweek",
    "project_horizon",
]

_SOURCE_HASH = "sha256:" + "0" * 64

# How many league-average matches a player's own card record is weighed against.
# Assumed, not measured: half a season is enough that a full campaign dominates
# its own rate, while a handful of appearances cannot claim a discipline record.
_BOOKING_PRIOR_MATCHES = 19.0


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
    # How much of a carried season survives a change of club or role.
    #
    # Assumed, not measured: nothing in the corpus has been
    # used to fit it, and it is recorded as assumed in docs/PARAMETERS.md
    # rather than dressed up. 0.6 says a move costs roughly a third of what the
    # previous season told us -- the service, the set pieces and the penalty
    # order all change, but the player does not become a different player.
    #
    # Applied only when club or role is known to have changed. An unknown
    # context is left alone and reported, because discounting on a suspicion is
    # as wrong as ignoring one.
    carried_context_weight: float = 0.6


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
    # How many times his ordinary afternoon his best one is. One where there is
    # nothing measured, which claims no upside rather than inventing some.
    ceiling_ratio: float = 1.0
    # Mean attacking multiplier across his fixtures this gameweek. Venue is
    # already inside it, so nothing downstream should add a home term.
    attacking_multiplier: float = 1.0


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
    strength = season_strength(corpus.season, corpus.fixtures_before(gameweek))
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
    # What the same match looks like on his best afternoon. Not a separate
    # forecast: the projection scaled by the shape of his own scoring, so a
    # defender who plays ninety and does nothing keeps a modest ceiling and a
    # striker who either scores or vanishes keeps a wide one.
    expected_ceiling: float
    shape: PointsShape
    minutes: MinutesProjection
    rates: PlayerRateProjection
    # What `expected_points` is made of, before the suspension derate. A scalar
    # cannot be checked; these can, and a fixture moves each of them differently.
    breakdown: PointsBreakdown
    # The closing stretch of the season, which is the best guide to a player's
    # current role. A January signing who started every remaining match reads
    # nothing like a squad player with the same season total.
    recent_minutes: int = 0
    recent_starts: int = 0
    recent_matches: int = 0
    # How much an accumulation ban is expected to cost him. One means no risk.
    suspension_multiplier: float = 1.0
    yellow_cards: int = 0


def project_next_match(
    corpus: SeasonCorpus,
    *,
    settings: ProjectionSettings | None = None,
    recent_window: int = 6,
    availability: Mapping[int, AvailabilityEvidence] | None = None,
    previous: SeasonCorpus | None = None,
) -> list[MatchProjection]:
    """Project every player's next match from a completed season, fixture-free.

    Deliberately excludes fixture difficulty and recent form: neither exists
    before a ball is kicked. A player without enough minutes is left out rather
    than projected from a prior alone.

    `availability` is FPL's own published status, keyed by element code. Without
    it the projection reads an injured player's history and reports the minutes
    he used to play, which is how a ruled-out player kept a full projection.

    `previous` is read for the defensive-contribution route only, where a
    season played under a different arrangement is a prior rather than a record.
    Everything else stays on the season named, which is what "the record" means
    on the site.
    """
    config = settings or ProjectionSettings()
    # 2019-20 ran to gameweek 47 after the shutdown, so the season after the
    # last one is not always a legal event. History is unaffected: `before`
    # is inclusive of everything already played.
    gameweek = min(corpus.last_event + 1, MAX_EVENT)
    # When the next event runs past the end of a season, the next match a player
    # actually plays is match one of the next one, with a clean card record.
    season_over = corpus.last_event + 1 > SEASON_MATCHES
    history = corpus.before(corpus.last_event + 1)
    if not history:
        return []

    by_element: dict[int, list[ElementRow]] = {}
    for row in history:
        by_element.setdefault(row.element_id, []).append(row)

    cutoff = _cutoff_for(corpus, gameweek, history)
    league = league_rates(history, corpus.position_by_element)
    # The league's own booking rate, to shrink thin records toward. Two yellows
    # in five matches is not a rate of 0.4 a match; it is five matches.
    #
    # Per position, because defenders are booked several times as often as
    # forwards and the prior carries half a season of weight. Pooled, it lifted
    # every forward's clean record toward a defender's risk and pulled every
    # defender's toward a forward's. Every other route in `league_rates` is
    # already split this way.
    league_booking_rate = _booking_rates(history, corpus.position_by_element)
    prior_nineties = config.prior_strength_minutes / _MINUTES_PER_90
    carried = _carried_history(corpus, previous)
    projections: list[MatchProjection] = []

    for element_id, rows in by_element.items():
        position = corpus.position_by_element.get(element_id)
        code = corpus.code_by_element.get(element_id)
        if position is None or position not in _GOAL_PRIOR or code is None:
            continue

        minutes = project_element_minutes(
            element_id,
            corpus.season,
            gameweek,
            rows,
            cutoff,
            config,
            availability=(availability or {}).get(code),
        )
        if minutes.evidence_level == "unavailable":
            continue
        rates = project_element_rates(
            element_id, corpus.season, gameweek, rows, cutoff, config, position
        )
        if rates.evidence_level == "unavailable":
            continue

        recent = [row for row in rows if row.gameweek > gameweek - 1 - recent_window]
        # A player one booking from a ban is worth less than his rate says, and
        # the accumulation thresholds are published rules rather than a guess.
        # The tally resets each season, so what carries across is the rate he
        # gets booked at, not the count he ended on.
        played = len({row.gameweek for row in rows if row.minutes > 0})
        yellows = sum(row.yellow_cards for row in rows)
        first_match = 1 if season_over else gameweek
        booking_rate = (
            yellows + league_booking_rate.get(position, 0.0) * _BOOKING_PRIOR_MATCHES
        ) / (played + _BOOKING_PRIOR_MATCHES)
        ban = suspension_risk(
            yellows=0 if first_match == 1 else yellows,
            matches_played=played,
            match=first_match,
            booking_rate=booking_rate,
        )
        breakdown = fixture_points_breakdown(
            rows,
            position,
            minutes,
            rates,
            league,
            prior_nineties,
            _NEUTRAL_ADJUSTMENT,
            list(carried.get(element_id, ())),
        )
        shape = describe_shape(rows)
        expected = breakdown.total * ban.multiplier
        projections.append(
            MatchProjection(
                code=code,
                element_id=element_id,
                position=position,
                web_name=corpus.name_by_element.get(element_id, ""),
                price_tenths=_latest_price(rows),
                expected_minutes=minutes.expected_minutes,
                expected_points=expected,
                expected_ceiling=expected * shape.ceiling_ratio,
                breakdown=breakdown,
                suspension_multiplier=ban.multiplier,
                yellow_cards=yellows,
                shape=shape,
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
        prior_team, prior_position = _prior_context(previous, prior_rows)

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
            team_id=corpus.team_by_element.get(element_id),
            prior_team_id=prior_team,
            prior_position=prior_position,
        )
        if rates.evidence_level == "unavailable":
            continue

        # Scoring rates come from whichever season supplied the evidence.
        scoring_rows = rows or list(prior_rows)
        # Last season is handed over separately only when this season has
        # something of its own to weigh it against. Where it does not,
        # `scoring_rows` already is last season and passing it twice would
        # shrink it toward itself. Only the defensive-contribution route reads
        # it: a defender's action count is a property of the system around him,
        # so a completed gameweek of the current arrangement has to outweigh a
        # campaign played under a different one.
        carried_defcon = list(prior_rows) if rows else []
        schedule = _schedule_for(corpus, element_id, gameweek)
        total = 0.0
        for adjustment in schedule:
            total += fixture_points(
                scoring_rows,
                position,
                minutes,
                rates,
                league,
                prior_nineties,
                adjustment,
                carried_defcon,
            )

        recent = form.get(element_id)
        shape = describe_shape(scoring_rows)
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
                ceiling_ratio=shape.ceiling_ratio,
                attacking_multiplier=(
                    sum(adjustment.attacking for adjustment in schedule) / len(schedule)
                    if schedule
                    else 1.0
                ),
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


def _booking_rates(
    history: Sequence[ElementRow], position_by_element: Mapping[int, int]
) -> dict[int, float]:
    """Yellow cards per match played, per position."""
    cards: dict[int, int] = {}
    matches: dict[int, int] = {}
    for row in history:
        if row.minutes <= 0:
            continue
        position = position_by_element.get(row.element_id)
        if position is None:
            continue
        matches[position] = matches.get(position, 0) + 1
        cards[position] = cards.get(position, 0) + row.yellow_cards
    return {
        position: cards.get(position, 0) / count for position, count in matches.items() if count
    }


def _prior_context(
    previous: SeasonCorpus | None, prior_rows: Sequence[ElementRow]
) -> tuple[int | None, int | None]:
    """Which club and role last season's rows were produced in.

    Carried rows keep last season's element id, and ids are reassigned every
    summer, so the lookup has to go through the previous corpus rather than the
    current one. Without this the carried-context check saw `None` on every
    projection and the club-change discount never fired.
    """
    if previous is None or not prior_rows:
        return None, None
    prior_id = prior_rows[0].element_id
    return (
        previous.team_by_element.get(prior_id),
        previous.position_by_element.get(prior_id),
    )


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
        strength = season_strength(corpus.season, corpus.fixtures_before(gameweek))
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
    """Mean points per fixture over the last ``window`` gameweeks.

    Per fixture, not per gameweek. `actual_points` sums a double gameweek's
    rows into one event total, so averaging events gave a per-gameweek figure
    that `_blend` then multiplied by the upcoming fixture count -- applying the
    double twice for anyone whose recent window already contained one.
    """
    scored: dict[int, list[int]] = {}
    fixtures: dict[int, int] = {}
    for event in range(max(1, gameweek - window), gameweek):
        for element_id, points in corpus.actual_points(event).items():
            scored.setdefault(element_id, []).append(points)
        for row in corpus.rows_by_gameweek.get(event, ()):
            fixtures[row.element_id] = fixtures.get(row.element_id, 0) + 1
    return {
        element_id: sum(points) / max(1, fixtures.get(element_id, len(points)))
        for element_id, points in scored.items()
        if points
    }


def baseline_recent_deviation(
    corpus: SeasonCorpus, gameweek: int, *, window: int = 5
) -> dict[int, float]:
    """Spread of the same window the recent mean averages.

    Two captaincy theses pull in opposite directions on it -- one wants the
    ceiling, one wants the certainty -- so both read the same number rather
    than each computing its own and disagreeing about what it measured.
    """
    totals: dict[int, list[int]] = {}
    for event in range(max(1, gameweek - window), gameweek):
        for element_id, points in corpus.actual_points(event).items():
            totals.setdefault(element_id, []).append(points)
    spread: dict[int, float] = {}
    for element_id, scored in totals.items():
        if len(scored) < 2:
            # One observation has no spread. Zero says "unknown", which both
            # policies then treat as "no adjustment".
            spread[element_id] = 0.0
            continue
        mean = sum(scored) / len(scored)
        spread[element_id] = (sum((value - mean) ** 2 for value in scored) / len(scored)) ** 0.5
    return spread


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
