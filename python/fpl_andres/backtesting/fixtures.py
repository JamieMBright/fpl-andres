"""Team attack and defence strength, and the fixture schedule that applies them.

Estimated from results to date rather than taken from FPL's published difficulty
rating, which is a subjective 1-5 and is null for older seasons.

Strength is expressed as a multiplier on the league's average goals per side, so
1.0 is average and 1.3 means a side that scores thirty percent more than typical.
Home and away are separate because the split is large and stable.

A single difficulty number is wrong for this game. A hard fixture suppresses
clean sheets while *raising* saves and defensive contributions, because a side
under pressure defends more. Callers therefore ask for the multiplier that
applies to a given scoring route, not for one blended figure.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from fpl_andres.models.dixon_coles import DixonColesModel

__all__ = [
    "Fixture",
    "RouteAdjustment",
    "TeamStrength",
    "estimate_strength",
    "route_adjustment",
]

# Shrinkage target. A side with few matches played is treated as average until
# the record says otherwise; ten matches is roughly when the split stabilises.
_PRIOR_MATCHES = 10.0
_NEUTRAL = 1.0
# Bounds keep an early-season freak run from producing absurd multipliers.
_MIN_MULTIPLIER = 0.4
_MAX_MULTIPLIER = 2.2


@dataclass(frozen=True)
class Fixture:
    """One scheduled match. Scores are absent until it has been played."""

    fixture_id: int
    event: int | None
    team_h: int
    team_a: int
    kickoff_time: datetime | None
    team_h_score: int | None = None
    team_a_score: int | None = None
    finished: bool = False

    def opponent_of(self, team_id: int) -> int | None:
        if team_id == self.team_h:
            return self.team_a
        if team_id == self.team_a:
            return self.team_h
        return None

    def is_home(self, team_id: int) -> bool:
        return team_id == self.team_h


@dataclass(frozen=True)
class TeamStrength:
    """Multipliers against the league average, by venue."""

    attack_home: float
    attack_away: float
    defence_home: float
    defence_away: float

    def attack(self, *, home: bool) -> float:
        return self.attack_home if home else self.attack_away

    def defence(self, *, home: bool) -> float:
        """Above one means this side concedes more than average."""
        return self.defence_home if home else self.defence_away


@dataclass(frozen=True)
class RouteAdjustment:
    """Per-route multipliers for one player in one fixture."""

    attacking: float
    clean_sheet: float
    conceding: float
    saves: float
    defensive_contribution: float


def _bounded(value: float) -> float:
    return max(_MIN_MULTIPLIER, min(_MAX_MULTIPLIER, value))


def _shrink(scored: float, matches: float, league_mean: float) -> float:
    """Goals per match relative to the league, pulled toward average when thin."""
    if league_mean <= 0:
        return _NEUTRAL
    total = scored + league_mean * _PRIOR_MATCHES
    played = matches + _PRIOR_MATCHES
    return _bounded((total / played) / league_mean)


def estimate_strength(fixtures: Sequence[Fixture]) -> dict[int, TeamStrength]:
    """Attack and defence multipliers per team, from played fixtures only."""
    played = [
        fixture
        for fixture in fixtures
        if fixture.team_h_score is not None and fixture.team_a_score is not None
    ]
    if not played:
        return {}

    home_goals = sum(fixture.team_h_score or 0 for fixture in played)
    away_goals = sum(fixture.team_a_score or 0 for fixture in played)
    home_mean = home_goals / len(played)
    away_mean = away_goals / len(played)

    scored_home: dict[int, float] = {}
    scored_away: dict[int, float] = {}
    conceded_home: dict[int, float] = {}
    conceded_away: dict[int, float] = {}
    matches_home: dict[int, float] = {}
    matches_away: dict[int, float] = {}

    for fixture in played:
        for_home = float(fixture.team_h_score or 0)
        for_away = float(fixture.team_a_score or 0)
        scored_home[fixture.team_h] = scored_home.get(fixture.team_h, 0.0) + for_home
        conceded_home[fixture.team_h] = conceded_home.get(fixture.team_h, 0.0) + for_away
        matches_home[fixture.team_h] = matches_home.get(fixture.team_h, 0.0) + 1
        scored_away[fixture.team_a] = scored_away.get(fixture.team_a, 0.0) + for_away
        conceded_away[fixture.team_a] = conceded_away.get(fixture.team_a, 0.0) + for_home
        matches_away[fixture.team_a] = matches_away.get(fixture.team_a, 0.0) + 1

    teams = set(matches_home) | set(matches_away)
    return {
        team_id: TeamStrength(
            attack_home=_shrink(
                scored_home.get(team_id, 0.0), matches_home.get(team_id, 0.0), home_mean
            ),
            attack_away=_shrink(
                scored_away.get(team_id, 0.0), matches_away.get(team_id, 0.0), away_mean
            ),
            # A home side concedes the away-goal average, so it is judged
            # against that baseline rather than its own.
            defence_home=_shrink(
                conceded_home.get(team_id, 0.0), matches_home.get(team_id, 0.0), away_mean
            ),
            defence_away=_shrink(
                conceded_away.get(team_id, 0.0), matches_away.get(team_id, 0.0), home_mean
            ),
        )
        for team_id in teams
    }


def strength_from_goal_model(
    model: DixonColesModel,
    teams: Sequence[int],
) -> dict[int, TeamStrength]:
    """Turn a fitted Dixon-Coles model into venue strength multipliers.

    `estimate_strength` averages goals for and against and shrinks toward the
    league. That charges a side for the fixtures it happened to draw: a team who
    played the top four early looks leakier than it is. Dixon-Coles separates
    attack, defence and home advantage by fitting them jointly, so the strength
    is against an average opponent rather than against the ones already faced.

    Each multiplier is the model's expected goals for that team at that venue,
    averaged over every possible opponent, divided by the same average across
    the league. `defence` stays a leakiness multiplier, as the rest of this
    module expects: above one means that side concedes more than average.

    Normalising within a venue matches `estimate_strength`, so the two are
    interchangeable. One consequence is visible in the output: Dixon-Coles fits
    a single home advantage shared by every club, so a club's home and away
    multipliers come out equal. That is the model's claim, not a defect — it
    says clubs differ in how good they are, not in how much a home crowd is
    worth, and nineteen home matches is too thin to argue otherwise.
    """
    known = [team for team in teams if team in model.teams]
    if len(known) < 2:
        return {}

    scored: dict[tuple[int, bool], float] = {}
    conceded: dict[tuple[int, bool], float] = {}
    for team in known:
        opponents = [other for other in known if other != team]
        for home in (True, False):
            predictions = [
                model.predict(
                    home_team_id=team if home else other,
                    away_team_id=other if home else team,
                    event=1,
                )
                for other in opponents
            ]
            mine = [p.home_expected_goals if home else p.away_expected_goals for p in predictions]
            theirs = [p.away_expected_goals if home else p.home_expected_goals for p in predictions]
            scored[(team, home)] = sum(mine) / len(mine)
            conceded[(team, home)] = sum(theirs) / len(theirs)

    def mean(values: Iterable[float]) -> float:
        collected = list(values)
        return sum(collected) / len(collected) if collected else 1.0

    scored_home = mean(scored[(team, True)] for team in known)
    scored_away = mean(scored[(team, False)] for team in known)
    conceded_home = mean(conceded[(team, True)] for team in known)
    conceded_away = mean(conceded[(team, False)] for team in known)

    return {
        team: TeamStrength(
            attack_home=_bounded(scored[(team, True)] / scored_home),
            attack_away=_bounded(scored[(team, False)] / scored_away),
            defence_home=_bounded(conceded[(team, True)] / conceded_home),
            defence_away=_bounded(conceded[(team, False)] / conceded_away),
        )
        for team in known
    }


def route_adjustment(
    strength: Mapping[int, TeamStrength],
    team_id: int,
    opponent_id: int,
    *,
    home: bool,
) -> RouteAdjustment:
    """How one fixture bends each scoring route for a player of ``team_id``.

    Returns neutral multipliers when either side is unmeasured, so a missing
    opponent softens the projection toward average rather than dropping it.
    """
    mine = strength.get(team_id)
    theirs = strength.get(opponent_id)
    if mine is None or theirs is None:
        return RouteAdjustment(_NEUTRAL, _NEUTRAL, _NEUTRAL, _NEUTRAL, _NEUTRAL)

    # Goals flow from my attack meeting their defensive leakiness.
    attacking = _bounded(mine.attack(home=home) * theirs.defence(home=not home))
    # Goals against flow from their attack meeting my leakiness.
    conceding = _bounded(theirs.attack(home=not home) * mine.defence(home=home))
    # A clean sheet is the chance they fail to score at all. Poisson at the
    # adjusted rate would need a goals baseline the caller has not supplied, so
    # the multiplier is the inverse of the pressure they apply.
    clean_sheet = _bounded(1.0 / conceding) if conceding > 0 else _MAX_MULTIPLIER
    # Under pressure a side makes more saves and more defensive actions. This is
    # why one difficulty number cannot serve every route.
    saves = conceding
    defensive_contribution = _bounded(1.0 + (conceding - 1.0) * 0.5)

    return RouteAdjustment(
        attacking=attacking,
        clean_sheet=clean_sheet,
        conceding=conceding,
        saves=saves,
        defensive_contribution=defensive_contribution,
    )
