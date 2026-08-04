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
    "venue_tilt",
    "with_venue_tilt",
]

# Shrinkage target. A side with few matches played is treated as average until
# the record says otherwise; ten matches is roughly when the split stabilises.
_PRIOR_MATCHES = 10.0
# A club plays nineteen at home. Half weight at one full season, because a
# fortress and a lucky run look identical over that many matches.
_VENUE_PRIOR_MATCHES = 19.0
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
    # One baseline for both venues, for the reason given in
    # `strength_from_goal_model`: a per-venue baseline divides out the very
    # ratio home advantage lives in.
    league_mean = (home_goals + away_goals) / (2 * len(played))
    home_mean = league_mean
    away_mean = league_mean

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


def venue_tilt(played: Sequence[Fixture]) -> dict[int, tuple[float, float, float, float]]:
    """Each club's own home and away tilt, measured from its own fixtures.

    Dixon-Coles fits one home advantage for the whole league, which says every
    club gains the same from playing at home. Clubs plainly differ: some are a
    fortress and travel badly, some barely notice. So the venue split is
    measured per club rather than assumed, and shrunk toward the league's own
    split because nineteen home matches is a thin sample to argue from.

    Returned as four multipliers against that club's *own* two-venue average:
    attack at home, attack away, goals conceded at home, conceded away. A club
    with no measured tilt comes back all ones, which is the league's shape.
    """
    scored: dict[tuple[int, bool], float] = {}
    conceded: dict[tuple[int, bool], float] = {}
    matches: dict[tuple[int, bool], float] = {}
    for fixture in played:
        if fixture.team_h_score is None or fixture.team_a_score is None:
            continue
        home_goals = float(fixture.team_h_score)
        away_goals = float(fixture.team_a_score)
        for team, home, mine, theirs in (
            (fixture.team_h, True, home_goals, away_goals),
            (fixture.team_a, False, away_goals, home_goals),
        ):
            scored[(team, home)] = scored.get((team, home), 0.0) + mine
            conceded[(team, home)] = conceded.get((team, home), 0.0) + theirs
            matches[(team, home)] = matches.get((team, home), 0.0) + 1

    teams = sorted({team for team, _ in matches})
    if not teams:
        return {}

    def rate(store: dict[tuple[int, bool], float], team: int, home: bool) -> float | None:
        played_here = matches.get((team, home), 0.0)
        return store.get((team, home), 0.0) / played_here if played_here else None

    def league(store: dict[tuple[int, bool], float], home: bool) -> float:
        rates = [value for team in teams if (value := rate(store, team, home)) is not None]
        return sum(rates) / len(rates) if rates else 0.0

    league_rates = {
        ("scored", True): league(scored, True),
        ("scored", False): league(scored, False),
        ("conceded", True): league(conceded, True),
        ("conceded", False): league(conceded, False),
    }
    scored_overall = (league_rates[("scored", True)] + league_rates[("scored", False)]) / 2
    conceded_overall = (league_rates[("conceded", True)] + league_rates[("conceded", False)]) / 2

    def tilt(
        store: dict[tuple[int, bool], float],
        team: int,
        home: bool,
        key: str,
        league_overall: float,
    ) -> float:
        """This club's rate at this venue over its own two-venue average."""
        if league_overall <= 0:
            return _NEUTRAL
        league_tilt = league_rates[(key, home)] / league_overall
        here = rate(store, team, home)
        there = rate(store, team, not home)
        played_here = matches.get((team, home), 0.0)
        if here is None or there is None or here + there <= 0:
            return _bounded(league_tilt)
        own = here / ((here + there) / 2)
        # Shrunk toward the league's split, because a club's own nineteen home
        # matches cannot separate a fortress from a lucky run.
        weight = played_here / (played_here + _VENUE_PRIOR_MATCHES)
        return _bounded(own * weight + league_tilt * (1 - weight))

    return {
        team: (
            tilt(scored, team, True, "scored", scored_overall),
            tilt(scored, team, False, "scored", scored_overall),
            tilt(conceded, team, True, "conceded", conceded_overall),
            tilt(conceded, team, False, "conceded", conceded_overall),
        )
        for team in teams
    }


def with_venue_tilt(
    base: Mapping[int, TeamStrength],
    played: Sequence[Fixture],
) -> dict[int, TeamStrength]:
    """Replace a shared home advantage with each club's measured one.

    `base` carries opponent-adjusted quality, which is what Dixon-Coles is for
    and what a goal average gets wrong. The venue split is the one thing the fit
    deliberately shares across the league, so it is measured separately here and
    multiplied back in around each club's own two-venue average.
    """
    tilts = venue_tilt(played)
    adjusted: dict[int, TeamStrength] = {}
    for team, strength in base.items():
        attack = (strength.attack_home + strength.attack_away) / 2
        defence = (strength.defence_home + strength.defence_away) / 2
        attack_tilt_home, attack_tilt_away, defence_tilt_home, defence_tilt_away = tilts.get(
            team, (_NEUTRAL, _NEUTRAL, _NEUTRAL, _NEUTRAL)
        )
        adjusted[team] = TeamStrength(
            attack_home=_bounded(attack * attack_tilt_home),
            attack_away=_bounded(attack * attack_tilt_away),
            defence_home=_bounded(defence * defence_tilt_home),
            defence_away=_bounded(defence * defence_tilt_away),
        )
    return adjusted


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

    Both venues are normalised against **one** league baseline, the goals a side
    scores in an average match at either venue. Dividing each venue by its own
    baseline instead is arithmetically the same as deleting home advantage: the
    ratio it lives in is exactly the ratio being divided out. That is what this
    function used to do, and it left every club with identical home and away
    multipliers, so `route_adjustment` graded a fixture on the opponent alone
    and the same tie projected identically home and away.
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

    # One baseline for both venues. By symmetry the average goals scored and the
    # average goals conceded across the league are the same number, so attack
    # and defence share it.
    league = mean(
        value for team in known for value in (scored[(team, True)], scored[(team, False)])
    )
    if league <= 0:
        return {}

    return {
        team: TeamStrength(
            attack_home=_bounded(scored[(team, True)] / league),
            attack_away=_bounded(scored[(team, False)] / league),
            defence_home=_bounded(conceded[(team, True)] / league),
            defence_away=_bounded(conceded[(team, False)] / league),
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
