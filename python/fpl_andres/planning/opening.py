"""Pick fifteen for a season, not for one Saturday.

You score eleven, so the objective is the best legal eleven, not the sum of the
squad. But a bench of non-players is worth nothing when a starter is dropped,
injured or rested, and with one free transfer a week you cannot repair that
every time it happens. So the bench earns its place too, at a discount: it pays
when a starter fails, and it lets you take the better of two fixtures without
spending a transfer.

That is why two playing four-and-a-half-million goalkeepers beat one premium and
one who never appears. Each week you start whichever has the better fixture, and
the pair costs less than the premium alone.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from fpl_andres.simulation.squad import Candidate, SquadRules, validate_squad

__all__ = ["OpeningSettings", "SquadPlan", "choose_opening_squad"]

# How much a bench place is worth against a starting one. A bench player scores
# when a starter records no minutes, and lets you switch fixture without a
# transfer. Assumed, not measured: it is the one number here that wants a
# season of squad data behind it.
_BENCH_WEIGHT = 0.25
# A substitute who never starts cannot cover anything. Below this he is a body.
_PLAYABLE_START_RATE = 0.35
# Rotating this pair is the point of a cheap goalkeeper pairing.
_GOALKEEPER = 1


@dataclass(frozen=True)
class OpeningSettings:
    rules: SquadRules
    lineup_size: int = 11
    minimum_by_position: Mapping[int, int] | None = None
    maximum_by_position: Mapping[int, int] | None = None
    bench_weight: float = _BENCH_WEIGHT
    playable_start_rate: float = _PLAYABLE_START_RATE

    def minimums(self) -> Mapping[int, int]:
        return self.minimum_by_position or {1: 1, 2: 3, 3: 2, 4: 1}

    def maximums(self) -> Mapping[int, int]:
        return self.maximum_by_position or {1: 1, 2: 5, 3: 5, 4: 3}


@dataclass(frozen=True)
class SquadPlan:
    squad: tuple[Candidate, ...]
    starters: tuple[Candidate, ...]
    bench: tuple[Candidate, ...]
    expected_points: float
    spent_tenths: int


def best_eleven(
    squad: Sequence[Candidate],
    points: Mapping[int, float],
    settings: OpeningSettings,
) -> tuple[list[Candidate], float]:
    """The highest-scoring legal lineup, and what it is worth."""
    minimums = settings.minimums()
    maximums = settings.maximums()
    by_position: dict[int, list[Candidate]] = {}
    for player in squad:
        by_position.setdefault(player.position, []).append(player)
    for players in by_position.values():
        players.sort(key=lambda player: points.get(player.element_id, 0.0), reverse=True)

    chosen: list[Candidate] = []
    for position, minimum in minimums.items():
        chosen.extend(by_position.get(position, [])[:minimum])

    remaining = [player for player in squad if player not in chosen]
    counts = {position: len(by_position.get(position, ())) for position in by_position}
    taken = {position: minimums.get(position, 0) for position in counts}
    remaining.sort(key=lambda player: points.get(player.element_id, 0.0), reverse=True)
    for player in remaining:
        if len(chosen) == settings.lineup_size:
            break
        if taken.get(player.position, 0) >= maximums.get(player.position, 0):
            continue
        chosen.append(player)
        taken[player.position] = taken.get(player.position, 0) + 1

    if len(chosen) < settings.lineup_size:
        return [], 0.0
    return chosen, sum(points.get(player.element_id, 0.0) for player in chosen)


def _value(
    squad: Sequence[Candidate],
    points: Mapping[int, float],
    settings: OpeningSettings,
) -> float:
    starters, total = best_eleven(squad, points, settings)
    if not starters:
        return float("-inf")
    starting = {player.element_id for player in starters}
    bench = sum(
        points.get(player.element_id, 0.0) for player in squad if player.element_id not in starting
    )
    return total + settings.bench_weight * bench


def _legal(squad: Sequence[Candidate], settings: OpeningSettings) -> bool:
    try:
        validate_squad(squad, settings.rules)
    except ValueError:
        return False
    return best_eleven(squad, {player.element_id: 1.0 for player in squad}, settings)[0] != []


def choose_opening_squad(
    pool: Sequence[Candidate],
    points: Mapping[int, float],
    start_rate: Mapping[int, float],
    settings: OpeningSettings,
) -> SquadPlan:
    """Greedy on value per pound, then improved by swaps until nothing helps.

    Every player must clear the playable floor, bench included: a squad that
    cannot field a substitute has spent four of its fifteen places on nothing.
    """
    playable = [
        player
        for player in pool
        if start_rate.get(player.element_id, 0.0) >= settings.playable_start_rate
    ]
    counts = settings.rules.position_counts
    squad = _seed(playable, points, settings)
    if squad is None:
        raise ValueError("no legal squad of playable footballers fits the budget")

    improved = True
    while improved:
        improved = False
        current = _value(squad, points, settings)
        spent = sum(player.price_tenths for player in squad)
        for index, outgoing in enumerate(squad):
            for incoming in playable:
                if incoming.position != outgoing.position:
                    continue
                if any(player.element_id == incoming.element_id for player in squad):
                    continue
                budget = spent - outgoing.price_tenths + incoming.price_tenths
                if budget > settings.rules.budget_tenths:
                    continue
                candidate = list(squad)
                candidate[index] = incoming
                if not _legal(candidate, settings):
                    continue
                if _value(candidate, points, settings) > current + 1e-9:
                    squad = candidate
                    improved = True
                    break
            if improved:
                break

    starters, total = best_eleven(squad, points, settings)
    starting = {player.element_id for player in starters}
    assert len(squad) == sum(counts.values())
    return SquadPlan(
        squad=tuple(squad),
        starters=tuple(starters),
        bench=tuple(player for player in squad if player.element_id not in starting),
        expected_points=total,
        spent_tenths=sum(player.price_tenths for player in squad),
    )


def _seed(
    pool: Sequence[Candidate],
    points: Mapping[int, float],
    settings: OpeningSettings,
) -> list[Candidate] | None:
    """A legal starting point: cheapest playable squad, best first per position."""
    squad: list[Candidate] = []
    per_club: dict[int, int] = {}
    for position, needed in settings.rules.position_counts.items():
        ranked = sorted(
            (player for player in pool if player.position == position),
            key=lambda player: player.price_tenths,
        )
        taken = 0
        for player in ranked:
            if taken == needed:
                break
            if per_club.get(player.team_id, 0) >= settings.rules.club_limit:
                continue
            squad.append(player)
            per_club[player.team_id] = per_club.get(player.team_id, 0) + 1
            taken += 1
        if taken < needed:
            return None
    return squad if _legal(squad, settings) else None
