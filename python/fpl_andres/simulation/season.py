"""Play a squad through a completed season.

Answers "what would this squad actually have scored?" using only observed
per-gameweek results, so it needs no manager history — which is fortunate,
because FPL does not retain any across a rollover.

The scoring rules are not re-implemented here. Realised `total_points` per
player per gameweek is an observation in the corpus; this module only decides
who was on the pitch, applies auto-substitutions and doubles the captain.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from fpl_andres.positions import is_captain_eligible
from fpl_andres.simulation.squad import Candidate

__all__ = [
    "GameweekResult",
    "LineupRules",
    "SeasonResult",
    "SquadGameweek",
    "simulate_season",
]

_GOALKEEPER = 1


@dataclass(frozen=True)
class LineupRules:
    """Formation bounds. Supplied by the caller, never inferred."""

    starting_size: int
    minimum_by_position: Mapping[int, int]
    maximum_by_position: Mapping[int, int]

    def __post_init__(self) -> None:
        if self.starting_size <= 0:
            raise ValueError("starting size must be positive")
        if sum(self.minimum_by_position.values()) > self.starting_size:
            raise ValueError("minimum formation exceeds the starting size")
        if sum(self.maximum_by_position.values()) < self.starting_size:
            raise ValueError("maximum formation cannot reach the starting size")


@dataclass(frozen=True)
class SquadGameweek:
    """One player's observed outcome in one gameweek."""

    element_id: int
    minutes: int
    points: int


@dataclass(frozen=True)
class GameweekResult:
    event: int
    points: int
    captain_id: int | None
    captain_points: int
    autosubs: tuple[int, ...]
    benched_points: int


@dataclass
class SeasonResult:
    season: str
    label: str
    gameweeks: list[GameweekResult] = field(default_factory=list)

    @property
    def total_points(self) -> int:
        return sum(week.points for week in self.gameweeks)

    @property
    def points_left_on_bench(self) -> int:
        return sum(week.benched_points for week in self.gameweeks)


CaptainPolicy = Callable[[Sequence[Candidate], Mapping[int, SquadGameweek], int], int | None]


def highest_scorer_so_far(
    history: Mapping[int, int],
) -> CaptainPolicy:
    """Captain the squad member with the most points before this gameweek.

    Deliberately naive and strictly backward-looking: it is a control to beat,
    not a recommendation, and it must never see the current gameweek.
    """

    def policy(
        squad: Sequence[Candidate],
        _outcomes: Mapping[int, SquadGameweek],
        _event: int,
    ) -> int | None:
        eligible = [player for player in squad if is_captain_eligible(player.position)]
        if not eligible:
            return None
        return max(eligible, key=lambda player: history.get(player.element_id, 0)).element_id

    return policy


def simulate_season(
    *,
    season: str,
    label: str,
    squad: Sequence[Candidate],
    results_by_event: Mapping[int, Mapping[int, SquadGameweek]],
    lineup_rules: LineupRules,
    captain_policy: CaptainPolicy | None = None,
    lineup_rank: Callable[[Candidate], float] | None = None,
) -> SeasonResult:
    """Play the squad through every supplied gameweek.

    ``lineup_rank`` scores a player for selection using pre-gameweek information
    only. It defaults to price, a crude but honest proxy; a promoted projection
    replaces it once one exists. ``captain_policy`` receives only the eligible
    midfielders and forwards in that gameweek's starting XI. An invalid policy
    result falls back to the highest pre-gameweek lineup rank in that pool.
    """
    positions = {player.element_id: player.position for player in squad}
    by_element = {player.element_id: player for player in squad}
    running_points: dict[int, int] = {player.element_id: 0 for player in squad}
    outcome = SeasonResult(season=season, label=label)
    policy = captain_policy or highest_scorer_so_far(running_points)
    rank = lineup_rank or (lambda player: float(player.price_tenths))

    for event in sorted(results_by_event):
        outcomes = results_by_event[event]
        available = {
            player.element_id: outcomes.get(
                player.element_id, SquadGameweek(player.element_id, 0, 0)
            )
            for player in squad
        }

        starters = _pick_starters(squad, rank, lineup_rules)
        starters, autosubs = _apply_autosubs(squad, starters, available, positions, lineup_rules)
        eligible_starters = [
            element_id for element_id in starters if is_captain_eligible(positions[element_id])
        ]
        if len(eligible_starters) < 2:
            raise ValueError("lineup has fewer than two captain-eligible starters")

        captain_pool = [by_element[element_id] for element_id in eligible_starters]
        captain_id = policy(captain_pool, available, event)
        if captain_id not in eligible_starters:
            captain_id = max(eligible_starters, key=lambda pid: rank(by_element[pid]))

        points = sum(available[pid].points for pid in starters)
        captain_points = available[captain_id].points if captain_id else 0
        points += captain_points

        benched = [pid for pid in available if pid not in starters]
        outcome.gameweeks.append(
            GameweekResult(
                event=event,
                points=points,
                captain_id=captain_id,
                captain_points=captain_points,
                autosubs=tuple(sorted(autosubs)),
                benched_points=sum(available[pid].points for pid in benched),
            )
        )

        for element_id, result in available.items():
            running_points[element_id] = running_points.get(element_id, 0) + result.points

    return outcome


def _pick_starters(
    squad: Sequence[Candidate],
    rank: Callable[[Candidate], float],
    rules: LineupRules,
) -> list[int]:
    """Choose a legal starting lineup from pre-gameweek information only.

    Deliberately blind to this gameweek's outcomes. Ranking on whether a player
    actually featured would silently never field a blank, inflating every
    simulated score and making auto-substitution dead code.
    """
    ranked = sorted(squad, key=rank, reverse=True)

    chosen: list[int] = []
    counts: dict[int, int] = {}

    for position, minimum in rules.minimum_by_position.items():
        for player in ranked:
            if counts.get(position, 0) >= minimum:
                break
            if player.position == position and player.element_id not in chosen:
                chosen.append(player.element_id)
                counts[position] = counts.get(position, 0) + 1

    for player in ranked:
        if len(chosen) >= rules.starting_size:
            break
        if player.element_id in chosen:
            continue
        maximum = rules.maximum_by_position.get(player.position, rules.starting_size)
        if counts.get(player.position, 0) >= maximum:
            continue
        chosen.append(player.element_id)
        counts[player.position] = counts.get(player.position, 0) + 1

    return chosen


def _apply_autosubs(
    squad: Sequence[Candidate],
    starters: list[int],
    outcomes: Mapping[int, SquadGameweek],
    positions: Mapping[int, int],
    rules: LineupRules,
) -> tuple[list[int], list[int]]:
    """Replace starters who did not play, keeping the formation legal."""
    bench = [
        player.element_id
        for player in squad
        if player.element_id not in starters and outcomes[player.element_id].minutes > 0
    ]
    blanks = [pid for pid in starters if outcomes[pid].minutes == 0]

    final = list(starters)
    used: list[int] = []

    for blank in blanks:
        for candidate in bench:
            if candidate in used:
                continue
            # A keeper may only be replaced by a keeper, and vice versa.
            if (positions[blank] == _GOALKEEPER) != (positions[candidate] == _GOALKEEPER):
                continue
            if not _formation_holds(final, blank, candidate, positions, rules):
                continue
            final[final.index(blank)] = candidate
            used.append(candidate)
            break

    return final, used


def _formation_holds(
    starters: Sequence[int],
    outgoing: int,
    incoming: int,
    positions: Mapping[int, int],
    rules: LineupRules,
) -> bool:
    counts: dict[int, int] = {}
    for pid in starters:
        position = positions[pid] if pid != outgoing else positions[incoming]
        counts[position] = counts.get(position, 0) + 1

    for position, minimum in rules.minimum_by_position.items():
        if counts.get(position, 0) < minimum:
            return False
    for position, maximum in rules.maximum_by_position.items():
        if counts.get(position, 0) > maximum:
            return False
    return True
