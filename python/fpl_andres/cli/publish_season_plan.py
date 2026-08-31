"""Publish a gameweek 1 to 38 plan from the opening squad.

Before the first deadline every manager owns the same nothing, so this publishes
one plan rather than a plan each. After the season starts the same planner needs
a per-manager squad, which is a different job with a different entry point.

Fixtures and prices come from FPL. Scoring records come from the committed
projection artifact, joined on player code. Per-gameweek expected points are the
player's record scaled by the opponent's measured strength on the route that
matters for his position, home or away, which is the same adjustment the opening
squad uses over its five-week window.

Usage:
    python -m fpl_andres.cli.publish_season_plan
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from fpl_andres import timeouts
from fpl_andres.artifacts import SEASON_PLAN_SCHEMA_VERSION
from fpl_andres.backtesting.fixtures import TeamStrength
from fpl_andres.bootstrap import BootstrapElement, parse_elements
from fpl_andres.jsonio import parse_json, read_json_file
from fpl_andres.model_version import MODEL_VERSION
from fpl_andres.optimization.contracts import (
    CurrentSquadPlayer,
    HorizonPlayerForecast,
    OptimizationRules,
    OptimizationStateEvidence,
    PositionConstraint,
    TransferRulesAddendum,
)
from fpl_andres.optimization.highs import CAPTAIN_CEILING_WEIGHT
from fpl_andres.planning.fixture_routes import fixture_difficulty, fixture_multiplier
from fpl_andres.planning.opening import (
    PLAYABLE_START_RATE,
    OpeningSettings,
    best_eleven,
    choose_opening_squad,
)
from fpl_andres.planning.season_plan import (
    PlannedEvent,
    confidence_for,
    plan_season,
)
from fpl_andres.positions import Position, is_captain_eligible
from fpl_andres.rules import RulesSnapshot
from fpl_andres.season_position import plannable_events
from fpl_andres.simulation.squad import Candidate as SquadCandidate
from fpl_andres.simulation.squad import SquadRules, validate_squad


def _now() -> datetime:
    """Read as one call so a test can pin the season's position."""
    return datetime.now(UTC)


SQUAD_RULES = SquadRules(budget_tenths=1000, club_limit=3, position_counts={1: 2, 2: 5, 3: 5, 4: 3})

BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"
USER_AGENT = "fpl-andres/0.5 (+https://github.com/JamieMBright/fpl-andres)"
PROJECTIONS = Path("apps/web/src/data/projections.json")
OPENING_SQUAD = Path("apps/web/src/data/opening-squad.json")
DEFAULT_OUTPUT = Path("apps/web/src/data/season-plan.json")

POSITION_CODES = {position.value: position.code for position in Position}
SQUAD_SHAPE = {1: 2, 2: 5, 3: 5, 4: 3}
LINEUP_RANGE = {1: (1, 1), 2: (3, 5), 3: (2, 5), 4: (1, 3)}
# The pool the planner may transfer into. Trimmed hard because window solve time
# grows with it and because the four hundredth-best player is not a candidate for
# a plan; the artifact records the size so the trim is visible rather than
# implied.
POOL_PER_POSITION = 14
# Cheapest playable options per position, on top of the best ones.
#
# A pool ranked only by expected points contains no bench fodder, and a squad
# must still field fifteen: the solver was forced to spend a mean of 23.4 of the
# 100 million on players who score nothing, once benching a 12.0 million
# midfielder. The bench scores zero outside a Bench Boost, so every pound parked
# there is a pound not in the eleven, and the fix is to make cheap players
# available rather than to penalise expensive ones.
ENABLERS_PER_POSITION = 6


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-season-plan")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--projections", default=str(PROJECTIONS))
    parser.add_argument("--opening-squad", default=str(OPENING_SQUAD))
    # 30 s was enough for a five-event window and is not enough for eight: the
    # third lexicographic stage timed out proving its tie-break optimum, which
    # fails the publish outright. This is an offline step, so it buys the time.
    parser.add_argument("--time-limit", type=float, default=120.0)
    # FPL publishes neither of these in the bootstrap. `docs/PARAMETERS.md`
    # records them as never inferred, so they are required rather than
    # defaulted: a plan built on a guessed transfer cost is a wrong plan that
    # looks right.
    parser.add_argument("--weekly-free-transfers", type=int, required=True)
    parser.add_argument("--transfer-cost-points", type=int, required=True)
    parser.add_argument(
        "--rules-reference",
        required=True,
        help="where those two numbers were read from, recorded in the artifact",
    )
    return parser


def _get_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeouts.FPL_API) as response:
        raw: bytes = response.read()
    return raw


def _get(url: str) -> object:
    return parse_json(_get_bytes(url).decode("utf-8"), source=url)


def _season_of(first_deadline: datetime) -> str:
    """FPL seasons open in August and close in May, so the year the first
    deadline falls in is the opening year."""
    start = first_deadline.year
    return f"{start}-{str(start + 1)[-2:]}"


@dataclass(frozen=True)
class Candidate:
    element_id: int
    code: int
    name: str
    position: int
    team_id: int
    club: str
    price_tenths: int
    record: float
    # His best single match last season. What a chip is played hoping for.
    best_match: float
    squad_number: int | None
    # What `record` is made of, so a fixture can be applied to each route.
    routes: Mapping[str, float] = field(default_factory=dict)


def _armband_value(mean: float, ceiling: float) -> float:
    """What an extra copy of a player is worth to someone chasing a haul.

    The same blend the optimizer uses for the ordinary armband, imported rather
    than restated so the site cannot hold two opinions about how much of the
    captaincy is read off the ceiling.
    """
    return mean * (1.0 - CAPTAIN_CEILING_WEIGHT) + ceiling * CAPTAIN_CEILING_WEIGHT


def _captain_eligible_elements(
    element_ids: Sequence[int], candidates: Mapping[int, Candidate]
) -> list[int]:
    return [
        element_id
        for element_id in element_ids
        if element_id in candidates and is_captain_eligible(candidates[element_id].position)
    ]


def _lineup_points_with_captain(
    starters: Sequence[int],
    points: Mapping[int, float],
    candidates: Mapping[int, Candidate],
) -> float:
    eligible = _captain_eligible_elements(starters, candidates)
    if len(eligible) < 2:
        raise ValueError("lineup has fewer than two captain-eligible starters")
    return sum(points[element_id] for element_id in starters) + max(
        points[element_id] for element_id in eligible
    )


def _free_hit_squad(
    pool: Sequence[SquadCandidate],
    points: Mapping[int, float],
) -> tuple[list[int], list[int]]:
    """Maximize one-week XI points, then minimize spend on the four reserves."""
    settings = OpeningSettings(rules=SQUAD_RULES, bench_weight=0.0)
    built = choose_opening_squad(
        pool,
        points,
        {candidate.element_id: 1.0 for candidate in pool},
        settings,
    )
    squad = list(built.squad)
    changed = True
    while changed:
        changed = False
        starters, score = best_eleven(squad, points, settings)
        starting = {candidate.element_id for candidate in starters}
        held = {candidate.element_id for candidate in squad}
        for index, outgoing in sorted(
            enumerate(squad),
            key=lambda row: row[1].price_tenths,
            reverse=True,
        ):
            if outgoing.element_id in starting:
                continue
            replacements = sorted(
                (
                    candidate
                    for candidate in pool
                    if candidate.position == outgoing.position
                    and candidate.element_id not in held
                    and candidate.price_tenths < outgoing.price_tenths
                ),
                key=lambda candidate: (candidate.price_tenths, candidate.element_id),
            )
            for incoming in replacements:
                candidate_squad = list(squad)
                candidate_squad[index] = incoming
                try:
                    validate_squad(candidate_squad, SQUAD_RULES)
                except ValueError:
                    continue
                _, candidate_score = best_eleven(candidate_squad, points, settings)
                if candidate_score + 1e-9 < score:
                    continue
                squad = candidate_squad
                changed = True
                break
            if changed:
                break

    starters, _ = best_eleven(squad, points, settings)
    starting = {candidate.element_id for candidate in starters}
    bench = [candidate for candidate in squad if candidate.element_id not in starting]
    return (
        [candidate.element_id for candidate in starters],
        [candidate.element_id for candidate in bench],
    )


def _opponent_multiplier(
    *,
    candidate: Candidate,
    opponent: int,
    home: bool,
    strength: Mapping[int, TeamStrength],
) -> float:
    """How much this fixture is worth to this player, against an average one.

    Each published scoring route is bent by what the fixture does to *it*, then
    the lot is expressed as a ratio against the neutral projection. One blended
    difficulty number cannot do this: the same hard away tie suppresses clean
    sheets and raises saves, so it is good for the keeper and bad for the
    defender in front of him.
    """
    if opponent not in strength or candidate.team_id not in strength:
        return 1.0
    return fixture_multiplier(
        candidate.routes,
        neutral_points=candidate.record,
        team_id=candidate.team_id,
        opponent_id=opponent,
        home=home,
        strength=strength,
    )


def _data_gaps(
    pool: Sequence[Candidate],
    clubs: Mapping[int, Mapping[str, Any]],
) -> dict[str, object]:
    """Which clubs the previous season cannot say anything about.

    The record season is the last Premier League season, so the three promoted
    clubs have almost no players in it and no measured strength at all. Their
    fixtures are therefore rated as exactly average, which is a guess wearing
    the same clothes as a measurement. Counting it here means the page can say
    how big the hole is rather than implying there is not one.
    """
    represented = {candidate.club for candidate in pool}
    absent = sorted(
        str(team["short_name"])
        for team in clubs.values()
        if str(team["short_name"]) not in represented
    )
    return {
        "clubsWithoutRecord": absent,
        "clubsInPool": len(represented),
        "clubsInLeague": len(clubs),
    }


def _validate_published_armbands(
    gameweeks: Sequence[Mapping[str, Any]], named: Mapping[int, Candidate]
) -> None:
    for week in gameweeks:
        for armband in ("captain", "viceCaptain"):
            code = int(week[armband])
            candidate = named.get(code)
            if candidate is None or not is_captain_eligible(candidate.position):
                raise ValueError(
                    f"gameweek {week['event']} publishes an ineligible {armband}: {code}"
                )


# Every chip is available twice: once in the first half of the season, once in
# the second. FPL resets the set at the halfway point, so a chip unplayed by
# gameweek nineteen is simply lost.
FIRST_HALF_LAST_EVENT = 19
# What a chip wants to be worth on the afternoon it pays off. Expected points
# are the average; a chip is played for the upside, so the bar is the ceiling.
CHIP_TARGET_POINTS = 20.0
# Below this the number is noise from the squad chooser rather than a finding,
# and presenting it as a plan would be dressing up a rounding error.
NEGLIGIBLE_CHIP_POINTS = 2.0

# A wildcard rebuilds a squad. Before a ball is kicked the squad was chosen
# freely, and one transfer later it has barely moved, so there is nothing to
# rebuild. Playing one here throws the chip away.
WILDCARD_EARLIEST_EVENT = 4
# A free hit swaps the squad for one week and hands it back. In gameweek one
# there is no squad to escape: the eleven on the pitch is the eleven that was
# picked for it.
FREE_HIT_EARLIEST_EVENT = 2
# How long one free transfer a week takes to close a gap a wildcard closes at
# once. A squad is usually three to five moves from optimal, so beyond this the
# wildcard has bought nothing that patience would not.
FREE_TRANSFER_CATCHUP = 5
# A Wildcard is a horizon pivot, not a fixed five-week rebuild. The legal squad
# is rebuilt at each of these horizons and the change between adjacent squads
# names the cliff; the longest squad is what persists after the chip.
WILDCARD_HORIZONS = (3, 5, 7, 9)
# How many of the fifteen a rebuild has to move before the chip is worth
# spending. Below this the free transfer makes the same moves over a few weeks
# and the chip is still in hand; a Wildcard offered against one swap is a chip
# thrown away, however well that swap scores.
MINIMUM_WILDCARD_CHANGES = 5
MINIMUM_FREE_HIT_CHANGES = 10

# How many rebuild weeks per half are solved exactly rather than trusted to the
# cheap screen. The screen already scores every legal week; taking only its
# best meant a week it ranked second was never verified and could never win.
# Each candidate is a whole season re-plan, so this is the number that decides
# how long a publish takes.
WILDCARD_CANDIDATES = 2
# The window a free hit's week is judged against. A gap that persists is a
# wildcard's job; a free hit is for the week that collapses on its own.
FREE_HIT_CONTEXT = 4


def _chip_plan(
    gameweeks: Sequence[dict[str, Any]],
    named: Mapping[int, Candidate],
    ceiling: Mapping[int, float] | None = None,
    peak: Mapping[tuple[int, int], float] | None = None,
    code_of: Mapping[int, int] | None = None,
) -> list[dict[str, object]]:
    """When to play all eight chips, from what each one actually buys.

    The four are not variations on "a good week". Each removes a different
    constraint, and the statistic that finds it has to be the one that measures
    that constraint biting.

    - **Triple Captain** removes the cap on one player: he scores three times
      instead of twice. It wants the week where one player's *best* afternoon is
      worth the most, because trebling a man who returns his average has spent a
      chip to gain his average.
    - **Bench Boost** removes the eleven-player limit: all fifteen score. It
      wants the week the bench is worth most, and it is the one chip that can be
      built toward, because the bench is chosen weeks in advance.
    - **Free Hit** removes the transfer limit for one week and then *takes the
      squad back*. That last part is what makes it different: it buys one week
      and nothing after it. So it is worth playing only where a single week is
      unusually bad for the squad being held -- a blank, or a fixture pile-up --
      and not where the squad is simply behind, which is a wildcard's problem.
    - **Wildcard** removes the transfer limit and *keeps* the new squad. Its
      value is not the gap it closes but the gap it closes **sooner than one
      free transfer a week would have closed it anyway**. Charging it the full
      gap credits it for points patience would have collected for nothing.

    That reading also rules some weeks out entirely. A wildcard in gameweek one
    rebuilds a squad that was chosen freely days earlier; a free hit in gameweek
    one escapes an eleven picked for that very week. Adjacent Free Hit and
    Wildcard weeks remain legal: the rental may cover a lull immediately before
    a meaningful permanent pivot.

    Wildcards are solved first as permanent season pivots. A Free Hit then
    re-solves from the restored squad until the next Wildcard, so its one-week
    gain includes the lost transfer bank without erasing the permanent rebuild.
    """
    if not gameweeks:
        return []

    peak_by = peak or {}
    code_for = code_of or {}
    element_for_code = {code: element_id for element_id, code in code_for.items()}
    chips: list[dict[str, object]] = []
    taken: set[int] = set()

    shortfall: dict[int, float] = {
        int(week["event"]): max(
            0.0, (ceiling or {}).get(week["event"], 0.0) - week["projectedPoints"]
        )
        for week in gameweeks
    }
    index_of = {int(week["event"]): index for index, week in enumerate(gameweeks)}

    def free(weeks: Sequence[dict[str, Any]], earliest: int = 0) -> list[dict[str, Any]]:
        return [week for week in weeks if week["event"] not in taken and week["event"] >= earliest]

    def verdict(best: float) -> str:
        if best < NEGLIGIBLE_CHIP_POINTS:
            # Worth saying plainly: this is a statement about the model, not
            # about the chip. Squads drift because of injuries, form, price
            # moves and blank gameweeks, and none of those exist in a projection
            # built from a completed season's per-match rates.
            return (
                "worth almost nothing here, because this projection has no injuries, "
                "no form and no blank gameweeks, so the squad never drifts far enough "
                "from optimal for unlimited transfers to rescue it. Play it against "
                "real news rather than against this number"
            )
        return (
            f"clears the {CHIP_TARGET_POINTS:.0f} points a chip wants to return"
            if best >= CHIP_TARGET_POINTS
            else (
                f"under the {CHIP_TARGET_POINTS:.0f} points that makes a chip worth "
                f"building around, but an unplayed chip expires at nothing"
            )
        )

    def peak_of(event: int, element_id: int) -> float:
        return float(peak_by.get((event, element_id), 0.0))

    def bench_points(week: dict[str, Any]) -> tuple[float, float]:
        mean = sum(week["expected"].get(str(code), 0.0) for code in week["bench"])
        best = sum(peak_of(week["event"], element) for element in week["benchElementIds"])
        return float(mean), float(best)

    def treble(week: dict[str, Any]) -> tuple[float, float, int]:
        """What a third copy of the week's published captain is worth.

        Triple Captain changes the multiplier, not who wears the armband. An
        independent selector here could describe trebling one starter while the
        gameweek card captained another, which is not a playable plan.
        """
        code = int(week["captain"])
        candidate = named.get(code)
        element = element_for_code.get(code)
        if (
            candidate is None
            or element is None
            or not is_captain_eligible(candidate.position)
            or code not in week["starters"]
        ):
            raise ValueError(f"gameweek {week['event']} cannot treble captain {code}")
        mean = week["expected"].get(str(code), 0.0)
        best = peak_of(week["event"], element)
        return float(mean), float(best), element

    def spike(week: dict[str, Any]) -> float:
        """How much worse this week is than the weeks either side of it.

        A free hit buys one week. A squad that is behind every week is not a
        free-hit problem, so only the excess over its own neighbourhood counts.
        """
        centre = index_of[week["event"]]
        low = max(0, centre - FREE_HIT_CONTEXT)
        high = min(len(gameweeks), centre + FREE_HIT_CONTEXT + 1)
        around = [
            shortfall[each["event"]]
            for position, each in enumerate(gameweeks[low:high], start=low)
            if position != centre
        ]
        if not around:
            return float(shortfall[week["event"]])
        typical = sorted(around)[len(around) // 2]
        return max(0.0, float(shortfall[week["event"]]) - typical)

    def persisting(week: dict[str, Any]) -> float:
        """The gap a rebuild closes sooner than free transfers would have.

        Full credit in the week it is played, none by the time one transfer a
        week would have caught up. Without that taper a wildcard is credited for
        points that were arriving anyway.
        """
        start = index_of[week["event"]]
        total = 0.0
        for offset, each in enumerate(gameweeks[start : start + max(WILDCARD_HORIZONS)]):
            earned = max(0.0, 1.0 - offset / FREE_TRANSFER_CATCHUP)
            total += shortfall[each["event"]] * earned
        return total

    halves = (
        ("first", [week for week in gameweeks if week["event"] <= FIRST_HALF_LAST_EVENT]),
        ("second", [week for week in gameweeks if week["event"] > FIRST_HALF_LAST_EVENT]),
    )

    for half, weeks in halves:
        if not weeks:
            continue

        candidates = free(weeks)
        if candidates:

            def treble_value(week: dict[str, Any]) -> float:
                mean, best, _ = treble(week)
                return _armband_value(mean, best)

            chosen = max(candidates, key=treble_value)
            mean, best, element = treble(chosen)
            taken.add(chosen["event"])
            code = code_for.get(element, 0)
            name = named[code].name if code in named else "the captain"
            chips.append(
                {
                    "event": chosen["event"],
                    "chip": "Triple Captain",
                    "half": half,
                    "gain": round(mean, 2),
                    "ceiling": round(best, 2),
                    "note": (
                        f"a third copy of {name}: {mean:.1f} if he returns his average, "
                        f"{best:.1f} on the sort of afternoon the chip is played for, which "
                        f"{verdict(best)}"
                    ),
                }
            )

        candidates = free(weeks)
        if candidates:
            chosen = max(candidates, key=lambda week: bench_points(week)[1])
            mean, best = bench_points(chosen)
            taken.add(chosen["event"])
            chips.append(
                {
                    "event": chosen["event"],
                    "chip": "Bench Boost",
                    "half": half,
                    "gain": round(mean, 2),
                    "ceiling": round(best, 2),
                    "note": (
                        f"the bench averages {mean:.1f} and reaches {best:.1f} if all four "
                        f"have the sort of week they are capable of, the best bench of the "
                        f"{half} half, which {verdict(best)}"
                    ),
                }
            )

        # The free hit picks first. It is the sharper instrument -- it only ever
        # scores a week that collapses on its own -- so letting the wildcard go
        # first would let a rebuild swallow the one week a rebuild cannot fix.
        candidates = free(weeks, FREE_HIT_EARLIEST_EVENT)
        if candidates:
            chosen = max(candidates, key=spike)
            gain = spike(chosen)
            taken.add(chosen["event"])
            chips.append(
                {
                    "event": chosen["event"],
                    "chip": "Free Hit",
                    "half": half,
                    "gain": round(gain, 2),
                    "ceiling": round(gain, 2),
                    "note": (
                        f"this week is {gain:.1f} worse for the held squad than the weeks "
                        f"around it, the sharpest one-week drop of the {half} half, which "
                        f"{verdict(gain)}"
                    ),
                }
            )

        candidates = free(weeks, WILDCARD_EARLIEST_EVENT)
        if candidates:
            ranked = sorted(candidates, key=persisting, reverse=True)
            chosen = ranked[0]
            gain = persisting(chosen)
            taken.add(chosen["event"])
            chips.append(
                {
                    "event": chosen["event"],
                    "chip": "Wildcard",
                    "half": half,
                    "gain": round(gain, 2),
                    "ceiling": round(gain, 2),
                    # Every legal week is already scored by the cheap screen and
                    # all but the best was being thrown away, so a rebuild that
                    # the screen ranked second was never solved exactly and
                    # never got the chance to win. Carried through to
                    # `_place_wildcards`, which verifies each properly, and
                    # popped there before the chip is published.
                    "_alternatives": [int(week["event"]) for week in ranked[1:WILDCARD_CANDIDATES]],
                    "note": (
                        f"rebuilding here is worth {gain:.1f} over the next "
                        f"{max(WILDCARD_HORIZONS)} gameweeks once the points one free transfer a "
                        f"week would have recovered anyway are taken off, which {verdict(gain)}"
                    ),
                }
            )

    return sorted(chips, key=lambda chip: (chip["event"] is None, chip["event"] or 0))


@dataclass(frozen=True)
class _ChipRun:
    """Everything playing a chip needs, so the callers stay one line each."""

    by_event: dict[int, dict[str, Any]]
    ordered_events: list[int]
    event_points: dict[int, dict[int, float]]
    pool: list[Candidate]
    candidate_for: dict[int, SquadCandidate]
    free_squads: dict[int, tuple[list[int], list[int]]]
    detail: dict[int, Candidate]
    cutoffs: Mapping[int, datetime]
    forecasts: Sequence[Any]
    rules: OptimizationRules
    now: datetime
    time_limit: float
    schedule: Mapping[tuple[int, int], Sequence[tuple[int, bool]]]
    clubs: Mapping[int, Any]
    strength: Mapping[int, Any]
    budget_tenths: int
    opening_squad: Sequence[int]
    opening_bank_tenths: int
    opening_free_transfers: int
    week_dict: Callable[[PlannedEvent], dict[str, Any]]
    ref: Callable[[int], int]
    wildcard_squads: dict[tuple[int, int], tuple[list[int], list[int]]] = field(
        default_factory=dict
    )


def _turnover(
    week: dict[str, Any],
    starters: list[int],
    bench: list[int],
    run: _ChipRun,
    replacing: set[int] | None = None,
) -> None:
    """Rewrite a week as the fifteen a chip bought, and price it.

    `replacing` is the squad the chip tore up. A Free Hit tears up the week's
    own fifteen, so it defaults to that. A Wildcard cannot: the segmented solve
    has already installed the rebuild as this week's squad, so diffing against
    it reports no transfers at all and the card shows a chip that did nothing.
    """
    event = int(week["event"])
    points = run.event_points[event]
    held = set(week["squadElementIds"]) if replacing is None else replacing
    fresh = set(starters) | set(bench)
    eligible = _captain_eligible_elements(starters, run.detail)
    if len(eligible) < 2:
        raise ValueError("chip squad has fewer than two captain-eligible starters")
    captain = max(eligible, key=lambda element_id: points[element_id])
    vice = max(
        (element_id for element_id in eligible if element_id != captain),
        key=lambda element_id: points[element_id],
    )

    opponents: dict[str, list[str]] = {}
    week_difficulty: dict[str, float | None] = {}
    for element_id in fresh:
        candidate = run.detail[element_id]
        if candidate.club in opponents:
            continue
        games = run.schedule.get((event, candidate.team_id), ())
        opponents[candidate.club] = [
            f"{run.clubs[opponent]['short_name']} ({'H' if home else 'A'})"
            for opponent, home in games
        ]
        week_difficulty[candidate.club] = fixture_difficulty(games, candidate.team_id, run.strength)

    peak_at = {
        element_id: run.detail[element_id].best_match
        * sum(
            _opponent_multiplier(
                candidate=run.detail[element_id],
                opponent=opponent,
                home=home,
                strength=run.strength,
            )
            for opponent, home in run.schedule.get((event, run.detail[element_id].team_id), ())
        )
        for element_id in fresh
    }

    week["starters"] = [run.ref(element_id) for element_id in starters]
    week["bench"] = [run.ref(element_id) for element_id in bench]
    week["captain"] = run.ref(captain)
    week["viceCaptain"] = run.ref(vice)
    # Out and in are the whole turnover, up to all fifteen, and none of it is
    # charged. That is the chip.
    week["transfersOut"] = [run.ref(element_id) for element_id in sorted(held - fresh)]
    week["transfersIn"] = [run.ref(element_id) for element_id in sorted(fresh - held)]
    week["opponents"] = opponents
    week["difficulty"] = week_difficulty
    week["squadElementIds"] = sorted(fresh)
    week["benchElementIds"] = list(bench)
    week["expected"] = {
        str(run.detail[element_id].code): round(points[element_id], 2) for element_id in fresh
    }
    week["ceiling"] = {
        str(run.detail[element_id].code): round(peak_at[element_id], 2) for element_id in fresh
    }
    week["paidTransfers"] = 0
    week["transferCostPoints"] = 0
    total = sum(points[element_id] for element_id in starters) + points[captain]
    week["projectedPoints"] = round(total, 2)
    week["netExpectedPoints"] = round(total, 2)
    week["bankAfterTenths"] = run.budget_tenths - sum(
        run.detail[element_id].price_tenths for element_id in fresh
    )


def _wildcard_turnover(event: int, run: _ChipRun) -> int:
    """How many of the fifteen a rebuild in this week would actually move.

    Measured against the squad the baseline plan holds going into the week, so
    it is the turnover a reader would see on the card. A chip that moves one or
    two players is a chip thrown away: the free transfer could have made those
    moves, and the wildcard cannot be played twice.
    """
    picked = _wildcard_squad(event, run)
    if picked is None:
        return 0
    index = run.ordered_events.index(event)
    previous = run.ordered_events[index - 1] if index > 0 else None
    if previous is None or previous not in run.by_event:
        held = set(run.opening_squad)
    else:
        held = set(run.by_event[previous]["squadElementIds"])
    return len((set(picked[0]) | set(picked[1])) - held)


def _solved_wildcard_turnover(
    event: int,
    weeks: Mapping[int, Mapping[str, Any]],
    ordered_events: Sequence[int],
    opening_squad: Sequence[int],
) -> int:
    """Turnover in the exact solved season, after earlier chips changed it."""
    index = ordered_events.index(event)
    previous = ordered_events[index - 1] if index > 0 else None
    held = (
        set(weeks[previous]["squadElementIds"])
        if previous is not None and previous in weeks
        else set(opening_squad)
    )
    return len(set(weeks[event]["squadElementIds"]) - held)


def _wildcard_squad_for_horizon(
    event: int,
    horizon_length: int,
    run: _ChipRun,
) -> tuple[list[int], list[int]] | None:
    """The legal fifteen a Wildcard buys over one measured horizon.

    Shopped from the planning pool rather than the whole game, because the
    segment solved from it has forecasts for no one else.
    """
    cached = run.wildcard_squads.get((event, horizon_length))
    if cached is not None:
        return cached
    horizon = [
        candidate for candidate in run.ordered_events if event <= candidate < event + horizon_length
    ]
    over_horizon = {
        candidate.element_id: sum(
            run.event_points[week_event].get(candidate.element_id, 0.0)
            for week_event in horizon
            if week_event in run.event_points
        )
        for candidate in run.pool
    }
    shoppable = [
        run.candidate_for[candidate.element_id]
        for candidate in run.pool
        if candidate.element_id in run.candidate_for
    ]
    if len(shoppable) < sum(SQUAD_RULES.position_counts.values()):
        return None
    try:
        rules = SquadRules(
            budget_tenths=run.budget_tenths,
            club_limit=SQUAD_RULES.club_limit,
            position_counts=SQUAD_RULES.position_counts,
        )
        built = choose_opening_squad(
            shoppable,
            over_horizon,
            {candidate.element_id: 1.0 for candidate in run.pool},
            OpeningSettings(rules=rules, bench_weight=0.0),
            weekly=[run.event_points[week] for week in horizon if week in run.event_points],
        )
    except ValueError:
        return None
    selected = (
        [player.element_id for player in built.starters],
        [player.element_id for player in built.bench],
    )
    run.wildcard_squads[(event, horizon_length)] = selected
    return selected


def _wildcard_squad(event: int, run: _ChipRun) -> tuple[list[int], list[int]] | None:
    """The longest-horizon legal squad, which persists after the Wildcard."""
    return _wildcard_squad_for_horizon(event, max(WILDCARD_HORIZONS), run)


def _wildcard_horizon_cliff(event: int, run: _ChipRun) -> tuple[int, tuple[int, int] | None]:
    """Largest squad change between adjacent 3/5/7/9-gameweek optima."""
    built = [
        (horizon, _wildcard_squad_for_horizon(event, horizon, run)) for horizon in WILDCARD_HORIZONS
    ]
    changes: list[tuple[int, tuple[int, int]]] = []
    for (short, short_squad), (long, long_squad) in pairwise(built):
        if short_squad is None or long_squad is None:
            continue
        short_ids = set(short_squad[0]) | set(short_squad[1])
        long_ids = set(long_squad[0]) | set(long_squad[1])
        changes.append((len(long_ids - short_ids), (short, long)))
    if not changes:
        return 0, None
    return max(changes, key=lambda row: (row[0], row[1]))


def _solve_segment(
    events: list[int],
    squad: Sequence[int],
    bank_tenths: int,
    free_transfers: int,
    run: _ChipRun,
) -> dict[int, dict[str, Any]]:
    """One stretch of season, solved with nothing beyond its own last gameweek.

    This is what makes a Wildcard worth playing. The chained window solve is
    long-termist by construction: every squad has to still be viable five weeks
    out, so it never spends down. A segment that ends at the Wildcard has no
    week after it to protect, so it can chase points and let the rebuild clear
    up. Solving the whole season long-termist and then swapping in a rebuild
    pays the cost of the chip and collects none of the licence it buys.
    """
    if not events:
        return {}
    solved = plan_season(
        events=events,
        cutoffs=run.cutoffs,
        forecasts=run.forecasts,
        opening_squad=tuple(
            CurrentSquadPlayer(
                element_id=element_id,
                selling_price_tenths=run.detail[element_id].price_tenths,
            )
            for element_id in sorted(squad)
        ),
        bank_tenths=bank_tenths,
        free_transfers=free_transfers,
        rules=run.rules,
        state_evidence=OptimizationStateEvidence(
            public_state_as_of=run.now,
            public_data_available_at=run.now,
            overrides_updated_at=run.now,
            public_source_hashes=(f"sha256:{2:064x}",),
            manager_overrides_hash=f"sha256:{3:064x}",
        ),
        time_limit_seconds=run.time_limit,
    )
    return {planned.event: run.week_dict(planned) for planned in solved.events}


def _season_with_wildcards(
    wildcards: Sequence[int], run: _ChipRun
) -> tuple[dict[int, dict[str, Any]], float] | None:
    """The whole season split at each Wildcard, and what it is worth."""
    boundaries = sorted(wildcards)
    weeks: dict[int, dict[str, Any]] = {}
    squad: Sequence[int] = run.opening_squad
    bank = run.opening_bank_tenths
    free_transfers = run.opening_free_transfers

    starts = [run.ordered_events[0], *boundaries]
    for index, start in enumerate(starts):
        stop = boundaries[index] if index < len(boundaries) else None
        segment = [
            event
            for event in run.ordered_events
            if event >= start and (stop is None or event < stop)
        ]
        solved = _solve_segment(segment, squad, bank, free_transfers, run)
        if not solved and len(segment) >= 2:
            return None
        # Each segment is solved as if the season started there, so it labels
        # its own opening week "firm" -- a gameweek thirteen weeks out claiming
        # observed prices. Confidence belongs to the distance from the real
        # first deadline, not from a Wildcard.
        opening = run.ordered_events[0]
        for event, week in solved.items():
            week["confidence"] = confidence_for(event, opening)
        weeks.update(solved)
        if stop is None:
            break
        picked = _wildcard_squad(stop, run)
        if picked is None:
            return None
        # The rebuild lands on the chip's own gameweek, which the next segment
        # then starts from.
        squad = sorted(set(picked[0]) | set(picked[1]))
        bank = run.budget_tenths - sum(run.detail[element_id].price_tenths for element_id in squad)
        if bank < 0:
            return None
        free_transfers = run.rules.transfer_rules.weekly_free_transfers

    missing = [event for event in run.ordered_events if event not in weeks]
    if missing:
        return None
    return weeks, sum(float(week["netExpectedPoints"]) for week in weeks.values())


def _place_wildcards(chips: list[dict[str, Any]], run: _ChipRun) -> None:
    """Keep only the Wildcards that beat carrying on with one transfer a week.

    Each candidate set is a whole re-plan, not a patch: the weeks before a
    Wildcard are solved again knowing the squad is about to be torn up.
    """
    proposed = sorted(
        (chip for chip in chips if chip["chip"] == "Wildcard" and chip.get("event") is not None),
        key=lambda chip: int(chip["event"]),
    )
    if not proposed:
        return

    baseline = sum(float(run.by_event[event]["netExpectedPoints"]) for event in run.ordered_events)
    # Each half offers its best few weeks by the cheap screen, not just its
    # best one. A week the screen ranked second can still win the exact solve,
    # and until now it was never given the chance.
    by_half: list[list[int]] = []
    cliff_by_event: dict[int, tuple[int, tuple[int, int] | None]] = {}
    for chip in proposed:
        alternatives = [int(event) for event in chip.pop("_alternatives", [])]
        offered = [int(chip["event"]), *alternatives]
        # Screened before the expensive solve: a week whose rebuild moves fewer
        # than this is not a wildcard week however well the season scores
        # around it.
        viable = [
            week
            for week in offered
            if week < run.ordered_events[-1]
            and _wildcard_turnover(week, run) >= MINIMUM_WILDCARD_CHANGES
        ]
        for week in viable:
            cliff_by_event[week] = _wildcard_horizon_cliff(week, run)
        viable.sort(
            key=lambda week: (
                cliff_by_event[week][0],
                -offered.index(week),
            ),
            reverse=True,
        )
        by_half.append(viable[:WILDCARD_CANDIDATES])

    if not any(by_half):
        for chip in proposed:
            chip["event"] = None
            chip["gain"] = 0.0
            chip["note"] = (
                f"No week in this half rebuilds {MINIMUM_WILDCARD_CHANGES} or more of the "
                "fifteen. A rebuild smaller than that is a transfer, and the free transfer "
                "makes it without spending the chip."
            )
        return

    options: list[list[int]] = []
    for weeks_for_half in by_half:
        options.extend([week] for week in weeks_for_half)
    if len(by_half) == 2:
        options.extend(
            [first, second] for first in by_half[0] for second in by_half[1] if first < second
        )

    best: tuple[list[int], dict[int, dict[str, Any]], float] | None = None
    for option in options:
        outcome = _season_with_wildcards(option, run)
        if outcome is None:
            continue
        weeks, total = outcome
        if any(
            _solved_wildcard_turnover(
                event,
                weeks,
                run.ordered_events,
                run.opening_squad,
            )
            < MINIMUM_WILDCARD_CHANGES
            for event in option
        ):
            continue
        if total > baseline and (best is None or total > best[2]):
            best = (option, weeks, total)

    if best is None:
        for chip in proposed:
            chip["event"] = None
            chip["gain"] = 0.0
            chip["note"] = (
                "Re-planning the season around a rebuild here, with the weeks before it "
                "freed from having to stay viable afterwards, still scored no more than "
                "one transfer a week. Nothing in this projection breaks, so there is "
                "nothing for a Wildcard to repair."
            )
        return

    kept, weeks, total = best
    run.by_event.update(weeks)
    # The winning week may be one the screen ranked below the chip's proposal,
    # so each half takes back whichever of its own candidates was kept.
    element_by_code = {candidate.code: element_id for element_id, candidate in run.detail.items()}
    for chip, offered in zip(proposed, by_half, strict=True):
        won = [candidate_event for candidate_event in kept if candidate_event in offered]
        if not won:
            chip["event"] = None
            chip["gain"] = 0.0
            chip["note"] = (
                "Every rebuild week offered for this half was worth less than carrying on "
                "with one transfer a week, so this copy of the chip is left unplayed."
            )
            continue
        event = won[0]
        chip["event"] = event
        week_data = run.by_event[event]
        starters = [element_by_code[int(code)] for code in week_data["starters"]]
        bench = [element_by_code[int(code)] for code in week_data["bench"]]
        # Against the week before, because the segmented solve has already
        # installed its exact rebuild here. Replacing it with the screening
        # squad would leave the following week's transfer ledger on a
        # different starting fifteen.
        index = run.ordered_events.index(event)
        previous = run.ordered_events[index - 1] if index > 0 else None
        replaced = (
            set(run.by_event[previous]["squadElementIds"])
            if previous is not None and previous in run.by_event
            else set(run.opening_squad)
        )
        _turnover(week_data, starters, bench, run, replaced)
        run.by_event[event]["chip"] = "Wildcard"
        chip["gain"] = round(total - baseline, 2)
        gained = total - baseline
        cliff, horizon_pair = cliff_by_event.get(event, (0, None))
        horizon_note = (
            f"the legal fifteen changes {cliff} players between xPts{horizon_pair[0]} "
            f"and xPts{horizon_pair[1]}"
            if horizon_pair is not None
            else "the xPts3/5/7/9 legal squads do not expose a sharper pivot"
        )
        chip["note"] = (
            f"Rebuilding in gameweek {event} is worth {gained:.1f} over the season, because "
            "the weeks before it no longer have to leave a squad that still works "
            f"afterwards; {horizon_note}, which "
            + (
                f"clears the {CHIP_TARGET_POINTS:.0f} points a chip wants to return"
                if gained >= CHIP_TARGET_POINTS
                else f"is under the {CHIP_TARGET_POINTS:.0f} a chip wants, "
                "but an unplayed chip expires at nothing"
            )
        )


def _play_free_hit(chip: dict[str, Any], run: _ChipRun) -> None:
    """Field the best fifteen in the game for one week and hand them back."""
    event = int(chip["event"])
    week = run.by_event.get(event)
    picked = run.free_squads.get(event)
    if week is None or picked is None:
        return

    index = run.ordered_events.index(event)
    previous = run.ordered_events[index - 1] if index > 0 else None
    if previous is None or previous not in run.by_event:
        held = list(run.opening_squad)
        held_bank = run.opening_bank_tenths
    else:
        held = list(run.by_event[previous]["squadElementIds"])
        held_bank = int(run.by_event[previous]["bankAfterTenths"])

    changes = len(set(picked[0] + picked[1]) - set(held))
    if changes < MINIMUM_FREE_HIT_CHANGES:
        chip["event"] = None
        chip["gain"] = 0.0
        chip["note"] = (
            f"The best temporary squad moves only {changes} of the fifteen; "
            f"a Free Hit needs {MINIMUM_FREE_HIT_CHANGES} or more changes."
        )
        return

    before = float(week["netExpectedPoints"])
    rental = deepcopy(week)
    _turnover(rental, picked[0], picked[1], run, replacing=set(held))
    after = float(rental["netExpectedPoints"])
    if after <= before:
        chip["event"] = None
        chip["gain"] = 0.0
        chip["note"] = (
            f"The best fifteen in the game for gameweek {event} scored no more than "
            "the squad the plan was already holding, so there is nothing to buy."
        )
        return

    future_wildcards = [
        candidate
        for candidate in run.ordered_events[index + 1 :]
        if run.by_event.get(candidate, {}).get("chip") == "Wildcard"
    ]
    next_wildcard = future_wildcards[0] if future_wildcards else None
    resume_events = [
        candidate
        for candidate in run.ordered_events[index + 1 :]
        if next_wildcard is None or candidate < next_wildcard
    ]
    baseline_total = sum(
        float(run.by_event[candidate]["netExpectedPoints"]) for candidate in [event, *resume_events]
    )
    resumed = _solve_segment(
        resume_events,
        held,
        held_bank,
        run.rules.transfer_rules.weekly_free_transfers,
        run,
    )
    if any(candidate not in resumed for candidate in resume_events):
        chip["event"] = None
        chip["gain"] = 0.0
        chip["note"] = (
            f"The temporary squad for gameweek {event} could not restore and re-plan "
            "every later week, so the Free Hit is left unplayed."
        )
        return

    resumed_total = after + sum(
        float(resumed[candidate]["netExpectedPoints"]) for candidate in resume_events
    )
    if resumed_total <= baseline_total:
        chip["event"] = None
        chip["gain"] = 0.0
        chip["note"] = (
            f"The gameweek {event} rental gains {after - before:.1f}, but restoring the "
            "old squad and resetting to one free transfer leaves the affected run worth "
            f"{baseline_total - resumed_total:.1f} less overall, so the Free Hit is unplayed."
        )
        return

    opening = run.ordered_events[0]
    for candidate, resumed_week in resumed.items():
        resumed_week["confidence"] = confidence_for(candidate, opening)
        run.by_event[candidate] = resumed_week

    if next_wildcard is not None:
        wildcard_week = run.by_event[next_wildcard]
        wildcard_squad = set(wildcard_week["squadElementIds"])
        wildcard_bench = list(wildcard_week["benchElementIds"])
        wildcard_starters = sorted(wildcard_squad - set(wildcard_bench))
        predecessor = run.ordered_events[run.ordered_events.index(next_wildcard) - 1]
        replacing = (
            set(held) if predecessor == event else set(run.by_event[predecessor]["squadElementIds"])
        )
        _turnover(
            wildcard_week,
            wildcard_starters,
            wildcard_bench,
            run,
            replacing=replacing,
        )
        wildcard_week["chip"] = "Wildcard"

    chip["gain"] = round(resumed_total - baseline_total, 2)
    rental["chip"] = "Free Hit"
    # The squad reverts on the whistle. The plan underneath is untouched, so the
    # fifteen it resumes from is published rather than inferred.
    rental["revertsAfter"] = True
    rental["revertsTo"] = sorted(run.ref(element_id) for element_id in held)
    run.by_event[event] = rental


def _play_chips(chips: list[dict[str, Any]], run: _ChipRun) -> None:
    """Wildcards first, because each one re-plans the season around itself."""
    _place_wildcards(chips, run)
    for chip in chips:
        if chip["chip"] == "Free Hit" and chip.get("event") is not None:
            _play_free_hit(chip, run)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    artifact = read_json_file(Path(args.projections))
    record_by_code = {int(row["code"]): row for row in artifact["players"]}
    strength_by_code = {
        int(row["code"]): TeamStrength(
            attack_home=row["attackHome"],
            attack_away=row["attackAway"],
            defence_home=row["defenceHome"],
            defence_away=row["defenceAway"],
        )
        for row in artifact.get("clubs", ())
    }

    bootstrap_raw = _get_bytes(BOOTSTRAP)
    bootstrap = parse_json(bootstrap_raw.decode("utf-8"), source=BOOTSTRAP)
    bootstrap_hash = f"sha256:{hashlib.sha256(bootstrap_raw).hexdigest()}"
    assert isinstance(bootstrap, dict)
    clubs = {int(team["id"]): team for team in bootstrap["teams"]}
    strength = {
        team_id: strength_by_code[int(team["code"])]
        for team_id, team in clubs.items()
        if int(team["code"]) in strength_by_code
    }

    events = plannable_events(bootstrap["events"], _now())
    if not events:
        print("every gameweek deadline has passed; nothing to plan", file=sys.stderr)
        return 1

    raw_fixtures = _get(FIXTURES)
    assert isinstance(raw_fixtures, list)
    # (event, team) -> list of (opponent, home)
    schedule: dict[tuple[int, int], list[tuple[int, bool]]] = {}
    for row in raw_fixtures:
        event = row["event"]
        if event is None:
            continue
        home_id, away_id = int(row["team_h"]), int(row["team_a"])
        schedule.setdefault((int(event), home_id), []).append((away_id, True))
        schedule.setdefault((int(event), away_id), []).append((home_id, False))

    candidates: list[Candidate] = []
    for element in parse_elements(bootstrap["elements"], model=BootstrapElement):
        if element.element_type not in POSITION_CODES or not element.is_available:
            continue
        record = record_by_code.get(element.code)
        if record is None:
            continue
        # The same floor the opening squad applies. Without it the plan happily
        # transferred in a fringe forward who has not started a match: his
        # per-match record looks fine because it is measured over the handful of
        # matches he did play.
        if float(record["probabilityStart"]) < PLAYABLE_START_RATE:
            continue
        candidates.append(
            Candidate(
                element_id=element.id,
                code=element.code,
                name=element.web_name,
                position=element.element_type,
                team_id=element.team,
                club=str(clubs[element.team]["short_name"]),
                price_tenths=element.now_cost,
                record=float(record["expectedPoints"]),
                best_match=float(record.get("expectedCeiling") or record["expectedPoints"]),
                routes=record.get("routes", {}),
                squad_number=element.squad_number,
            )
        )

    opening = read_json_file(Path(args.opening_squad))
    squad_codes = [int(pick["code"]) for pick in opening["picks"]]
    by_code = {candidate.code: candidate for candidate in candidates}
    missing = [code for code in squad_codes if code not in by_code]
    if missing:
        print(
            f"opening squad references {len(missing)} players who are no longer "
            f"selectable: {missing}. Republish the opening squad first.",
            file=sys.stderr,
        )
        return 1

    # Keep the squad, the strongest of everyone else, and the cheapest players
    # worth a bench place, position by position.
    held = {by_code[code].element_id for code in squad_codes}
    pool: list[Candidate] = [by_code[code] for code in squad_codes]
    for position in SQUAD_SHAPE:
        available = [c for c in candidates if c.position == position and c.element_id not in held]
        best = sorted(available, key=lambda c: -c.record)[:POOL_PER_POSITION]
        chosen = {c.element_id for c in best}
        cheapest = sorted(
            (c for c in available if c.element_id not in chosen),
            key=lambda c: (c.price_tenths, -c.record),
        )[:ENABLERS_PER_POSITION]
        pool.extend(best)
        pool.extend(cheapest)

    ordered_events = sorted(events)
    cutoffs = {
        event: datetime.fromisoformat(events[event]["deadline_time"].replace("Z", "+00:00"))
        for event in ordered_events
    }
    season = _season_of(cutoffs[ordered_events[0]])
    snapshot = RulesSnapshot.from_bootstrap(
        bootstrap,
        season=season,
        source_hash=bootstrap_hash,
        weekly_free_transfers=args.weekly_free_transfers,
    )

    forecasts: list[HorizonPlayerForecast] = []
    difficulty: dict[int, float] = {}
    # (event, element id) -> points, so a card can show what the shirt is worth
    # that week rather than only the squad total.
    expected_by: dict[tuple[int, int], float] = {}
    # The same week priced at each player's best match rather than his average.
    # A chip is played for the upside, so this is what it is judged on.
    ceiling_by: dict[tuple[int, int], float] = {}
    # Every event planned here still has its deadline ahead, so publishing time
    # is genuinely before every cutoff the validation compares it against.
    now = _now()
    for event in ordered_events:
        weights: list[float] = []
        for candidate in pool:
            games = schedule.get((event, candidate.team_id), ())
            if not games:
                # A blank gameweek is zero, not an average week. Nothing is a
                # more honest projection for a player who is not playing.
                expected = 0.0
                peak = 0.0
            else:
                multiplier = sum(
                    _opponent_multiplier(
                        candidate=candidate,
                        opponent=opponent,
                        home=home,
                        strength=strength,
                    )
                    for opponent, home in games
                )
                expected = candidate.record * multiplier
                peak = candidate.best_match * multiplier
            expected_by[(event, candidate.element_id)] = round(expected, 2)
            ceiling_by[(event, candidate.element_id)] = round(peak, 2)
            forecasts.append(
                HorizonPlayerForecast(
                    season=season,
                    event=event,
                    element_id=candidate.element_id,
                    team_id=candidate.team_id,
                    position_id=candidate.position,
                    buy_price_tenths=candidate.price_tenths,
                    sell_price_tenths=candidate.price_tenths,
                    expected_points=round(expected, 3),
                    expected_ceiling=round(max(expected, peak), 3),
                    evidence_level="inferred",
                    model_name="season-plan",
                    model_version=MODEL_VERSION,
                    data_available_at=cutoffs[event],
                    source_hashes=(f"sha256:{candidate.code:064x}",),
                )
            )
        for candidate in pool:
            for opponent, home in schedule.get((event, candidate.team_id), ()):
                weights.append(
                    _opponent_multiplier(
                        candidate=candidate, opponent=opponent, home=home, strength=strength
                    )
                )
        # Higher multiplier means an easier opponent, so invert it to read as
        # difficulty everywhere it is used.
        difficulty[event] = -(sum(weights) / len(weights)) if weights else 0.0

    rules = OptimizationRules(
        season=season,
        squad_size=snapshot.squad_size,
        lineup_size=snapshot.starting_size,
        club_limit=snapshot.club_limit,
        transfer_cap=snapshot.transfer_cap,
        positions=tuple(
            PositionConstraint(
                position_id=position,
                squad_count=count,
                lineup_minimum=LINEUP_RANGE[position][0],
                lineup_maximum=LINEUP_RANGE[position][1],
            )
            for position, count in SQUAD_SHAPE.items()
        ),
        transfer_rules=TransferRulesAddendum(
            season=season,
            weekly_free_transfers=snapshot.weekly_free_transfers,
            maximum_free_transfers=snapshot.max_free_transfers,
            transfer_cost_points=args.transfer_cost_points,
            source_reference=args.rules_reference,
            source_hash=bootstrap_hash,
            data_available_at=now,
        ),
        published_rules_hash=bootstrap_hash,
        data_available_at=now,
    )

    plan = plan_season(
        events=ordered_events,
        cutoffs=cutoffs,
        forecasts=forecasts,
        opening_squad=tuple(
            CurrentSquadPlayer(
                element_id=by_code[code].element_id,
                selling_price_tenths=by_code[code].price_tenths,
            )
            for code in squad_codes
        ),
        bank_tenths=int(opening["budgetTenths"]) - int(opening["spentTenths"]),
        free_transfers=1,
        rules=rules,
        state_evidence=OptimizationStateEvidence(
            public_state_as_of=now,
            public_data_available_at=now,
            overrides_updated_at=now,
            public_source_hashes=(f"sha256:{2:064x}",),
            manager_overrides_hash=f"sha256:{3:064x}",
        ),
        time_limit_seconds=args.time_limit,
    )

    # Every candidate, not just the planning pool: a Free Hit week is filled
    # from the whole game, and those shirts still have to be named.
    detail = {candidate.element_id: candidate for candidate in candidates}
    # Fifteen full player objects per gameweek repeated thirty-eight times is
    # most of the file. The plan references codes and carries one table.
    named: dict[int, Candidate] = {}

    def ref(element_id: int) -> int:
        candidate = detail[element_id]
        named[candidate.code] = candidate
        return candidate.code

    def week_dict(planned: PlannedEvent) -> dict[str, Any]:
        event_plan = planned.plan
        squad = set(event_plan.squad_element_ids)
        # "HUL (A)" per club, so a card can name the opponent rather than repeat
        # the club whose shirt is already drawn beside the player. A double
        # gameweek gets both.
        opponents: dict[str, list[str]] = {}
        # One to five for the same tie, so a card can show how hard the week is
        # without the reader working it out from club names.
        week_difficulty: dict[str, float | None] = {}
        for element_id in squad:
            candidate = detail[element_id]
            if candidate.club in opponents:
                continue
            games = schedule.get((planned.event, candidate.team_id), ())
            opponents[candidate.club] = [
                f"{clubs[opponent]['short_name']} ({'H' if home else 'A'})"
                for opponent, home in games
            ]
            week_difficulty[candidate.club] = fixture_difficulty(games, candidate.team_id, strength)

        return {
            "event": planned.event,
            "deadline": cutoffs[planned.event].astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "confidence": planned.confidence,
            "starters": [ref(pid) for pid in event_plan.starter_element_ids],
            "bench": [ref(pid) for pid in event_plan.bench_element_ids],
            "captain": ref(event_plan.captain_element_id),
            "viceCaptain": ref(event_plan.vice_captain_element_id),
            "transfersIn": [ref(pid) for pid in event_plan.transfers_in],
            "transfersOut": [ref(pid) for pid in event_plan.transfers_out],
            "opponents": opponents,
            "difficulty": week_difficulty,
            # Element ids alongside the published codes, so the chip planner
            # can price a week without re-deriving the mapping.
            "squadElementIds": sorted(squad),
            "benchElementIds": list(event_plan.bench_element_ids),
            "expected": {
                str(detail[element_id].code): expected_by[(planned.event, element_id)]
                for element_id in squad
            },
            # The same week on his best afternoon, so a card can show what
            # it is hoping for as well as what it is expecting.
            "ceiling": {
                str(detail[element_id].code): ceiling_by[(planned.event, element_id)]
                for element_id in squad
            },
            "freeTransfersBefore": event_plan.free_transfers_before,
            "paidTransfers": event_plan.paid_transfers,
            "transferCostPoints": event_plan.transfer_cost_points,
            "projectedPoints": round(event_plan.projected_points_before_cost, 2),
            "netExpectedPoints": round(event_plan.net_expected_points, 2),
            "bankAfterTenths": event_plan.bank_after_tenths,
        }

    gameweeks = [week_dict(planned) for planned in plan.events]

    # The best eleven the whole budget could buy that week, ignoring transfers.
    # A chip is only worth playing to the extent the plan falls short of it.
    #
    # Drawn from every candidate rather than the trimmed planning pool: a Free
    # Hit can buy anyone in the game for a week, so measuring it against the
    # eighty-five players the plan already shops from said it was worth nothing.
    ceiling: dict[int, float] = {}
    # The fifteen that made up that ceiling, so a Free Hit can actually be played
    # rather than described.
    free_squads: dict[int, tuple[list[int], list[int]]] = {}
    event_points: dict[int, dict[int, float]] = {}
    candidate_for = {
        candidate.element_id: SquadCandidate(
            element_id=candidate.element_id,
            element_code=candidate.code,
            position=candidate.position,
            team_id=candidate.team_id,
            price_tenths=candidate.price_tenths,
            web_name=candidate.name,
        )
        for candidate in candidates
    }
    for event in ordered_events:
        points = {
            candidate.element_id: sum(
                candidate.record
                * _opponent_multiplier(
                    candidate=candidate,
                    opponent=opponent,
                    home=home,
                    strength=strength,
                )
                for opponent, home in schedule.get((event, candidate.team_id), ())
            )
            for candidate in candidates
        }
        try:
            free_starters, free_bench = _free_hit_squad(
                list(candidate_for.values()),
                points,
            )
        except ValueError:
            continue
        # The armband too, because the plan's own `projectedPoints` counts it.
        # Comparing an eleven against an eleven-plus-captain made the ceiling
        # look lower than the plan every week, so the shortfall was always zero
        # and the Free Hit and Wildcard were never played.
        ceiling[event] = _lineup_points_with_captain(free_starters, points, detail)
        free_squads[event] = (free_starters, free_bench)
        event_points[event] = points

    chips = _chip_plan(
        gameweeks,
        named,
        ceiling,
        ceiling_by,
        {candidate.element_id: candidate.code for candidate in pool},
    )

    budget_tenths = int(opening["budgetTenths"])

    # Neither chip is modelled by the optimizer, so the weeks they were chosen
    # for still hold the squad the plan was carrying. Play them here.
    by_event = {int(week["event"]): week for week in gameweeks}

    _play_chips(
        chips,
        _ChipRun(
            by_event=by_event,
            ordered_events=list(ordered_events),
            event_points=event_points,
            pool=list(pool),
            candidate_for=candidate_for,
            free_squads=free_squads,
            detail=detail,
            cutoffs=cutoffs,
            forecasts=forecasts,
            rules=rules,
            now=now,
            time_limit=args.time_limit,
            schedule=schedule,
            clubs=clubs,
            strength=strength,
            budget_tenths=budget_tenths,
            opening_squad=[by_code[code].element_id for code in squad_codes],
            opening_bank_tenths=budget_tenths - int(opening["spentTenths"]),
            opening_free_transfers=1,
            week_dict=week_dict,
            ref=ref,
        ),
    )

    gameweeks = [by_event[candidate] for candidate in ordered_events]

    payload = {
        "schemaVersion": SEASON_PLAN_SCHEMA_VERSION,
        "modelVersion": MODEL_VERSION,
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "season": season,
        "recordSeason": str(artifact["season"]),
        "basis": (
            "opening squad, fixture-adjusted projections, solved in overlapping "
            f"windows and committed {len(plan.events)} gameweeks deep"
        ),
        "rulesReference": args.rules_reference,
        "weeklyFreeTransfers": snapshot.weekly_free_transfers,
        "maximumFreeTransfers": snapshot.max_free_transfers,
        "transferCostPoints": args.transfer_cost_points,
        "firstEvent": plan.events[0].event,
        "lastEvent": plan.events[-1].event,
        "windowsSolved": plan.windows_solved,
        "poolSize": plan.pool_size,
        # Summed over the published weeks rather than taken from the first
        # solve, because the chips rewrote some of them.
        "netExpectedPoints": round(
            sum(float(week["netExpectedPoints"]) for week in gameweeks),
            2,
        ),
        "chips": chips,
        "dataGaps": _data_gaps(pool, clubs),
        "players": {
            str(code): {
                "name": candidate.name,
                "position": POSITION_CODES[candidate.position],
                "club": candidate.club,
                "priceTenths": candidate.price_tenths,
                "squadNumber": candidate.squad_number,
            }
            for code, candidate in sorted(named.items())
        },
        "gameweeks": gameweeks,
    }

    _validate_published_armbands(gameweeks, named)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {output} — gameweeks {payload['firstEvent']} to {payload['lastEvent']}, "
        f"{plan.windows_solved} windows, pool {plan.pool_size}, "
        f"{payload['netExpectedPoints']} net points"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
