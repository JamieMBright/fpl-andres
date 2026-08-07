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

__all__ = [
    "PLAYABLE_START_RATE",
    "OpeningSettings",
    "SquadPlan",
    "bench_weights",
    "choose_opening_squad",
]

# How much a bench place is worth against a starting one, where the squad's own
# appearance chances are not known. Assumed, not measured; `bench_weights`
# derives it properly and is what the publishers use.
_BENCH_WEIGHT = 0.25

# How many candidates per position a paired swap considers, from each end: the
# best few because that is what an upgrade buys, and the cheapest few because
# that is what pays for it. Fifteen slots make 105 pairs, so the search is a
# few tens of thousands of squads rather than the millions an exhaustive pass
# over a five-hundred-player pool would be.
_PAIR_CANDIDATES = 8
# A substitute who never starts cannot cover anything. Below this he is a body.
# Measured on the decay-weighted chance of an hour, not a season total: Isidor
# made 32 appearances and started none of the last six, Kinsky made 7 and
# started all of them.
PLAYABLE_START_RATE = 0.35
_PLAYABLE_START_RATE = PLAYABLE_START_RATE
# Rotating this pair is the point of a cheap goalkeeper pairing.
_GOALKEEPER = 1


def _blank_tail(blanks: Sequence[float]) -> list[float]:
    """P(at least one blank), P(at least two), ... from independent chances.

    A Poisson binomial, built up one starter at a time. Ten starters is small
    enough that the exact distribution is cheaper than reasoning about which
    approximation would have been close enough.
    """
    # distribution[k] is P(exactly k blanks) among the starters seen so far.
    distribution = [1.0]
    for blank in blanks:
        updated = [0.0] * (len(distribution) + 1)
        for count, probability in enumerate(distribution):
            updated[count] += probability * (1.0 - blank)
            updated[count + 1] += probability * blank
        distribution = updated
    tail: list[float] = []
    running = 1.0
    for count in range(len(distribution) - 1):
        running -= distribution[count]
        tail.append(max(0.0, min(1.0, running)))
    return tail


def bench_weights(
    starters: Sequence[Candidate],
    bench: Sequence[Candidate],
    appear: Mapping[int, float],
) -> list[float]:
    """What each bench place is worth, in the order the subs would come on.

    A substitute scores only when a starter records no minutes and the auto-sub
    fires, so his worth is the chance he is needed: the first outfield sub comes
    on if at least one outfield starter blanks, the second if at least two, and
    so on.

    This replaces a flat 0.25 applied to every bench place, which was assumed
    rather than measured and valued the fourth substitute exactly as highly as
    the first.

    The reserve goalkeeper is the chance the one who started records nothing,
    because no outfield substitute can replace him.

    He was briefly valued at zero, on the argument that a manager transfers a
    ruled-out keeper rather than carrying insurance. That was reasoning, not
    measurement, and it was wrong: it forecloses rotating two cheap keepers to
    take the softer fixture every week, and it makes a Bench Boost bench a man
    short. Neither is a strategy this function may rule out by assumption.
    """
    outfield_blanks = [
        1.0 - appear.get(player.element_id, 0.0)
        for player in starters
        if player.position != _GOALKEEPER
    ]
    tail = _blank_tail(outfield_blanks)
    keeper_blank = next(
        (
            1.0 - appear.get(player.element_id, 0.0)
            for player in starters
            if player.position == _GOALKEEPER
        ),
        0.0,
    )

    weights: list[float] = []
    used = 0
    for player in bench:
        if player.position == _GOALKEEPER:
            weights.append(keeper_blank)
            continue
        weights.append(tail[used] if used < len(tail) else 0.0)
        used += 1
    return weights


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
    appear: Mapping[int, float] | None = None,
) -> float:
    starters, total = best_eleven(squad, points, settings)
    if not starters:
        return float("-inf")
    starting = {player.element_id for player in starters}
    benched = [player for player in squad if player.element_id not in starting]
    if appear is None:
        return total + settings.bench_weight * sum(
            points.get(player.element_id, 0.0) for player in benched
        )
    # Ordered by points, because that is the order the auto-subs are tried in.
    benched.sort(key=lambda player: points.get(player.element_id, 0.0), reverse=True)
    weights = bench_weights(starters, benched, appear)
    return total + sum(
        weight * points.get(player.element_id, 0.0)
        for player, weight in zip(benched, weights, strict=True)
    )


def _legal(squad: Sequence[Candidate], settings: OpeningSettings) -> bool:
    try:
        validate_squad(squad, settings.rules)
    except ValueError:
        return False
    return best_eleven(squad, {player.element_id: 1.0 for player in squad}, settings)[0] != []


def _best_paired_swap(
    squad: Sequence[Candidate],
    playable: Sequence[Candidate],
    points: Mapping[int, float],
    settings: OpeningSettings,
    appear: Mapping[int, float] | None,
    current: float,
) -> list[Candidate] | None:
    """Two out, two in, when neither move is worth making alone.

    Bounded rather than exhaustive. Every position keeps its best
    `_PAIR_CANDIDATES` by points, which is where an upgrade comes from, plus
    its cheapest few, which is where the money comes from. Anything outside
    both is neither the player you want nor the one you sell to afford him.
    """
    held = {player.element_id for player in squad}
    by_position: dict[int, list[Candidate]] = {}
    for player in playable:
        if player.element_id in held:
            continue
        by_position.setdefault(player.position, []).append(player)

    shortlists: dict[int, list[Candidate]] = {}
    for position, options in by_position.items():
        best = sorted(options, key=lambda p: -points.get(p.element_id, 0.0))
        cheap = sorted(options, key=lambda p: p.price_tenths)
        seen: dict[int, Candidate] = {}
        for player in [*best[:_PAIR_CANDIDATES], *cheap[:_PAIR_CANDIDATES]]:
            seen[player.element_id] = player
        shortlists[position] = list(seen.values())

    spent = sum(player.price_tenths for player in squad)
    budget = settings.rules.budget_tenths
    best_squad: list[Candidate] | None = None
    best_value = current

    for first in range(len(squad)):
        for second in range(first + 1, len(squad)):
            out_one, out_two = squad[first], squad[second]
            freed = spent - out_one.price_tenths - out_two.price_tenths
            for in_one in shortlists.get(out_one.position, ()):
                if freed + in_one.price_tenths > budget:
                    continue
                for in_two in shortlists.get(out_two.position, ()):
                    if in_two.element_id == in_one.element_id:
                        continue
                    if freed + in_one.price_tenths + in_two.price_tenths > budget:
                        continue
                    candidate = list(squad)
                    candidate[first] = in_one
                    candidate[second] = in_two
                    if not _legal(candidate, settings):
                        continue
                    value = _value(candidate, points, settings, appear)
                    if value > best_value + 1e-9:
                        best_value = value
                        best_squad = candidate

    return best_squad


def choose_opening_squad(
    pool: Sequence[Candidate],
    points: Mapping[int, float],
    start_rate: Mapping[int, float],
    settings: OpeningSettings,
    appear: Mapping[int, float] | None = None,
) -> SquadPlan:
    """Greedy on value per pound, then improved by swaps until nothing helps.

    Every player must clear the playable floor, bench included: a squad that
    cannot field a substitute has spent four of its fifteen places on nothing.

    `appear` is each player's chance of recording any minutes. Given it, the
    bench is valued by how often its cover is actually needed rather than by a
    flat weight.
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
        current = _value(squad, points, settings, appear)
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
                if _value(candidate, points, settings, appear) > current + 1e-9:
                    squad = candidate
                    improved = True
                    break
            if improved:
                break

        if improved:
            continue
        # Nothing single helps, which is not the same as nothing helping. An
        # upgrade you cannot afford on its own is bought by selling somewhere
        # else, and one swap at a time can never express that: the downgrade
        # loses points immediately and is rejected before the upgrade it pays
        # for is ever considered. That is what left a premium goalkeeper on the
        # bench, and what made a Wildcard rebuild score worse than the exact
        # solve it is compared against.
        paired = _best_paired_swap(squad, playable, points, settings, appear, current)
        if paired is not None:
            squad = paired
            improved = True

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
