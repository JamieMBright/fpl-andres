"""Turning a squad and a gameweek into points.

Split out of `minileague.py` for Starting eleven, captaincy and
automatic substitutions, none of which depend on how the squad was chosen.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from fpl_andres.simulation.chips import ChipName
from fpl_andres.simulation.minileague_state import LeagueSettings, _Manager
from fpl_andres.simulation.season import LineupRules, SquadGameweek
from fpl_andres.simulation.squad import Candidate, build_ranked_squad

__all__ = ["Played"]


@dataclass(frozen=True)
class Played:
    """A scored gameweek, and the eleven that scored it.

    The eleven is returned rather than discarded because the questions worth
    asking of a season are about what was on the field, and the total alone
    cannot answer any of them.
    """

    points: int
    squad: tuple[int, ...]
    starters: tuple[int, ...]
    captain: int | None
    #: The captain's own score before his multiplier, so a ledger can show what
    #: the armband was worth rather than only what the week totalled.
    captain_points: int = 0
    #: What the unused substitutes scored. Zero under a bench boost, where they
    #: were not substitutes.
    bench_points: int = 0


def _play(
    manager: _Manager,
    settings: LeagueSettings,
    outcomes: Mapping[int, SquadGameweek],
    projected: Mapping[int, float],
    form: Mapping[int, float],
    chip: ChipName | None = None,
    pool: Sequence[Candidate] = (),
) -> Played:
    squad = manager.squad
    if chip == "free_hit" and pool:
        # One week only: the squad played is not the squad kept.
        squad = list(build_ranked_squad(pool, settings.squad_rules, projected))

    available = {
        player.element_id: outcomes.get(player.element_id, SquadGameweek(player.element_id, 0, 0))
        for player in squad
    }
    ranking = projected if manager.result.policy == "advised" else form

    starters = _starting_eleven(squad, ranking, settings.lineup_rules)
    starters = _autosub(squad, starters, available, settings.lineup_rules)
    if chip == "bench_boost":
        # Every one of the fifteen scores, so there is nothing to substitute.
        starters = [player.element_id for player in squad]

    captain = max(starters, key=lambda pid: ranking.get(pid, 0.0), default=None)
    points = sum(available[pid].points for pid in starters)
    if captain is not None:
        # Captain doubles; the triple captain chip adds a further multiple.
        points += available[captain].points
        if chip == "triple_captain":
            points += available[captain].points
    fielded = set(starters)
    return Played(
        points=points,
        squad=tuple(player.element_id for player in squad),
        starters=tuple(starters),
        captain=captain,
        captain_points=available[captain].points if captain is not None else 0,
        bench_points=sum(
            outcome.points for element, outcome in available.items() if element not in fielded
        ),
    )


def _starting_eleven(
    squad: Sequence[Candidate], ranking: Mapping[int, float], rules: LineupRules
) -> list[int]:
    ordered = sorted(squad, key=lambda player: ranking.get(player.element_id, 0.0), reverse=True)
    chosen: list[int] = []
    counts: dict[int, int] = {}

    for position, minimum in rules.minimum_by_position.items():
        for player in ordered:
            if counts.get(position, 0) >= minimum:
                break
            if player.position == position and player.element_id not in chosen:
                chosen.append(player.element_id)
                counts[position] = counts.get(position, 0) + 1

    for player in ordered:
        if len(chosen) >= rules.starting_size:
            break
        if player.element_id in chosen:
            continue
        if counts.get(player.position, 0) >= rules.maximum_by_position.get(
            player.position, rules.starting_size
        ):
            continue
        chosen.append(player.element_id)
        counts[player.position] = counts.get(player.position, 0) + 1
    return chosen


def _autosub(
    squad: Sequence[Candidate],
    starters: list[int],
    outcomes: Mapping[int, SquadGameweek],
    rules: LineupRules,
) -> list[int]:
    positions = {player.element_id: player.position for player in squad}
    bench = [
        player.element_id
        for player in squad
        if player.element_id not in starters and outcomes[player.element_id].minutes > 0
    ]
    final = list(starters)
    used: set[int] = set()

    for blank in [pid for pid in starters if outcomes[pid].minutes == 0]:
        for candidate in bench:
            if candidate in used:
                continue
            if (positions[blank] == 1) != (positions[candidate] == 1):
                continue
            counts: dict[int, int] = {}
            for pid in final:
                position = positions[pid] if pid != blank else positions[candidate]
                counts[position] = counts.get(position, 0) + 1
            if any(
                counts.get(position, 0) < minimum
                for position, minimum in rules.minimum_by_position.items()
            ):
                continue
            final[final.index(blank)] = candidate
            used.add(candidate)
            break
    return final
