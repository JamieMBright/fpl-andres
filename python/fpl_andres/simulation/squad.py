"""Squad construction under FPL selection rules.

Used to start a season simulation from a legal opening squad without needing any
manager's real history, which FPL does not retain across a rollover.

Every rule is supplied rather than assumed. Squad size, budget, club limit and
the per-position counts have been stable for years, but assuming them would be
exactly the silent default this product refuses elsewhere.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__ = [
    "Candidate",
    "SquadRules",
    "SquadSelectionError",
    "build_ranked_squad",
    "build_squad",
    "validate_squad",
]


class SquadSelectionError(ValueError):
    """Raised when a legal squad cannot be produced from the supplied pool."""


@dataclass(frozen=True)
class Candidate:
    """One selectable player at a point in time."""

    element_id: int
    element_code: int
    position: int
    team_id: int
    price_tenths: int
    web_name: str = ""

    def __post_init__(self) -> None:
        if self.price_tenths <= 0:
            raise ValueError("price must be positive")
        if self.position not in (1, 2, 3, 4):
            raise ValueError("position must be 1..4 (GKP, DEF, MID, FWD)")


@dataclass(frozen=True)
class SquadRules:
    """Selection rules for a season. Sourced by the caller, never inferred."""

    budget_tenths: int
    club_limit: int
    position_counts: Mapping[int, int]

    @property
    def squad_size(self) -> int:
        return sum(self.position_counts.values())

    def __post_init__(self) -> None:
        if self.budget_tenths <= 0:
            raise ValueError("budget must be positive")
        if self.club_limit <= 0:
            raise ValueError("club limit must be positive")
        if not self.position_counts:
            raise ValueError("position counts must be supplied")


def validate_squad(squad: Sequence[Candidate], rules: SquadRules) -> None:
    """Raise unless the squad satisfies every selection rule."""
    if len(squad) != rules.squad_size:
        raise SquadSelectionError(
            f"squad holds {len(squad)} players, rules require {rules.squad_size}"
        )

    element_ids = [player.element_id for player in squad]
    if len(set(element_ids)) != len(element_ids):
        raise SquadSelectionError("squad repeats a player")

    spend = sum(player.price_tenths for player in squad)
    if spend > rules.budget_tenths:
        raise SquadSelectionError(
            f"squad costs {spend / 10:.1f}m, budget is {rules.budget_tenths / 10:.1f}m"
        )

    for position, required in rules.position_counts.items():
        held = sum(1 for player in squad if player.position == position)
        if held != required:
            raise SquadSelectionError(
                f"position {position} holds {held} players, rules require {required}"
            )

    counts: dict[int, int] = {}
    for player in squad:
        counts[player.team_id] = counts.get(player.team_id, 0) + 1
    over = {team: count for team, count in counts.items() if count > rules.club_limit}
    if over:
        raise SquadSelectionError(f"club limit exceeded: {over}")


def clubs_over_limit(squad: Sequence[Candidate], rules: SquadRules) -> dict[int, int]:
    """Clubs a held squad is over-represented in.

    A squad can legally hold more than the limit without ever having selected
    it: when a player moves between clubs mid-season, FPL leaves the manager
    holding four and requires the next transfer to put it right. Selecting four
    remains impossible, so `validate_squad` stays strict and this reports the
    transitional state instead.
    """
    counts: dict[int, int] = {}
    for player in squad:
        counts[player.team_id] = counts.get(player.team_id, 0) + 1
    return {team: count for team, count in counts.items() if count > rules.club_limit}


def transfer_respects_club_limit(
    squad: Sequence[Candidate],
    outgoing: Candidate,
    incoming: Candidate,
    rules: SquadRules,
) -> bool:
    """Whether one swap is allowed under the club limit.

    A squad already over the limit must come back under it: the correction is
    compulsory, not optional, so a transfer that leaves the breach standing is
    refused even when it changes nothing about that club.
    """
    after = [player for player in squad if player.element_id != outgoing.element_id]
    after.append(incoming)
    breaches_before = clubs_over_limit(squad, rules)
    breaches_after = clubs_over_limit(after, rules)

    if not breaches_before:
        return not breaches_after
    return sum(breaches_after.values()) < sum(breaches_before.values())


def build_ranked_squad(
    pool: Sequence[Candidate],
    rules: SquadRules,
    ranking: Mapping[int, float],
) -> tuple[Candidate, ...]:
    """The best legal squad a greedy pass over ``ranking`` can afford.

    Used to start every policy from the same credible team. A randomly drawn
    squad is mostly players who never appear, so a simulation begun from one
    measures recovery from a bad team rather than skill at playing the game.

    Greedy with a feasibility floor: a player is only taken if the remaining
    budget can still buy the cheapest legal completion of the squad.
    """
    by_position: dict[int, list[Candidate]] = {}
    for player in pool:
        by_position.setdefault(player.position, []).append(player)

    for position, required in rules.position_counts.items():
        available = len(by_position.get(position, []))
        if available < required:
            raise SquadSelectionError(
                f"pool holds {available} players in position {position}, need {required}"
            )

    needed = dict(rules.position_counts)
    squad: list[Candidate] = []
    clubs: dict[int, int] = {}
    taken: set[int] = set()
    spent = 0

    ordered = sorted(
        pool,
        key=lambda player: (-ranking.get(player.element_id, 0.0), player.price_tenths),
    )
    for player in ordered:
        if needed.get(player.position, 0) <= 0 or player.element_id in taken:
            continue
        if clubs.get(player.team_id, 0) >= rules.club_limit:
            continue
        provisional = {**needed, player.position: needed[player.position] - 1}
        floor = _completion_floor(provisional, by_position, taken | {player.element_id})
        if floor is None or spent + player.price_tenths + floor > rules.budget_tenths:
            continue
        squad.append(player)
        taken.add(player.element_id)
        clubs[player.team_id] = clubs.get(player.team_id, 0) + 1
        needed[player.position] -= 1
        spent += player.price_tenths
        if all(count <= 0 for count in needed.values()):
            break

    if any(count > 0 for count in needed.values()):
        raise SquadSelectionError("could not complete a legal squad from the ranking")
    validate_squad(squad, rules)
    return tuple(squad)


def _completion_floor(
    needed: Mapping[int, int],
    by_position: Mapping[int, list[Candidate]],
    taken: set[int],
) -> int | None:
    """Cheapest cost of the slots still open, from players still available.

    Using the pool's global cheapest would understate this as players are taken,
    letting the greedy overspend early and then fail to field a legal squad.
    Returns None when a position can no longer be filled at all.
    """
    total = 0
    for position, count in needed.items():
        if count <= 0:
            continue
        prices = sorted(
            player.price_tenths
            for player in by_position.get(position, [])
            if player.element_id not in taken
        )
        if len(prices) < count:
            return None
        total += sum(prices[:count])
    return total


def build_squad(
    pool: Sequence[Candidate],
    rules: SquadRules,
    *,
    rng: random.Random,
    attempts: int = 400,
) -> tuple[Candidate, ...]:
    """Draw a legal squad that spends as much of the budget as it can.

    Picks randomly within each position, then repairs the budget by swapping the
    most expensive players down. Random selection is the point: it is the
    dartboard baseline any real model has to beat.
    """
    by_position: dict[int, list[Candidate]] = {}
    for player in pool:
        by_position.setdefault(player.position, []).append(player)

    for position, required in rules.position_counts.items():
        available = len(by_position.get(position, []))
        if available < required:
            raise SquadSelectionError(
                f"pool holds {available} players in position {position}, need {required}"
            )

    for _ in range(attempts):
        squad = _draw(by_position, rules, rng)
        if squad is None:
            continue
        repaired = _repair_budget(squad, by_position, rules)
        if repaired is None:
            continue
        try:
            validate_squad(repaired, rules)
        except SquadSelectionError:
            continue
        return tuple(repaired)

    raise SquadSelectionError(
        f"no legal squad found in {attempts} attempts; the pool may be too thin "
        "or too expensive for the supplied budget"
    )


def _draw(
    by_position: Mapping[int, list[Candidate]],
    rules: SquadRules,
    rng: random.Random,
) -> list[Candidate] | None:
    """One random draw honouring the club limit as it goes."""
    squad: list[Candidate] = []
    club_counts: dict[int, int] = {}

    for position, required in sorted(rules.position_counts.items()):
        options = list(by_position[position])
        rng.shuffle(options)
        taken = 0
        for player in options:
            if club_counts.get(player.team_id, 0) >= rules.club_limit:
                continue
            squad.append(player)
            club_counts[player.team_id] = club_counts.get(player.team_id, 0) + 1
            taken += 1
            if taken == required:
                break
        if taken < required:
            return None
    return squad


def _repair_budget(
    squad: list[Candidate],
    by_position: Mapping[int, list[Candidate]],
    rules: SquadRules,
) -> list[Candidate] | None:
    """Swap the priciest players for cheaper same-position ones until affordable."""
    working = list(squad)
    for _ in range(len(working) * 4):
        spend = sum(player.price_tenths for player in working)
        if spend <= rules.budget_tenths:
            return working

        held = {player.element_id for player in working}
        club_counts: dict[int, int] = {}
        for player in working:
            club_counts[player.team_id] = club_counts.get(player.team_id, 0) + 1

        dearest = max(working, key=lambda player: player.price_tenths)
        replacement = _cheapest_swap(dearest, by_position, held, club_counts, rules)
        if replacement is None:
            return None
        working[working.index(dearest)] = replacement
    return None


def _cheapest_swap(
    outgoing: Candidate,
    by_position: Mapping[int, list[Candidate]],
    held: set[int],
    club_counts: Mapping[int, int],
    rules: SquadRules,
) -> Candidate | None:
    best: Candidate | None = None
    for player in by_position[outgoing.position]:
        if player.element_id in held or player.price_tenths >= outgoing.price_tenths:
            continue
        if (
            player.team_id != outgoing.team_id
            and club_counts.get(player.team_id, 0) >= rules.club_limit
        ):
            continue
        if best is None or player.price_tenths < best.price_tenths:
            best = player
    return best
