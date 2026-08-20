"""How each rival policy spends its transfers.

Split out of `minileague.py` for These are the decisions that
distinguish an advised manager from a form chaser, and they are the part of the
simulation most likely to change.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from fpl_andres.simulation.minileague_state import (
    _CHASERS,
    _PASSIVE,
    _TRANSFER_HIT_POINTS,
    LeagueSettings,
    _Manager,
)
from fpl_andres.simulation.squad import (
    Candidate,
    transfer_respects_club_limit,
)


def _take_transfers(
    manager: _Manager,
    *,
    settings: LeagueSettings,
    by_position: Mapping[int, Sequence[Candidate]],
    projected: Mapping[int, float],
    form: Mapping[int, float],
    minutes: Mapping[int, int],
    prices: Mapping[int, int],
) -> None:
    # The week's free transfer arrives before any decision is taken.
    manager.free_transfers = min(
        manager.free_transfers + settings.free_transfers_per_event,
        settings.max_free_transfers,
    )
    policy = manager.result.policy
    if policy in _PASSIVE:
        return

    ranking = projected
    if not ranking:
        return

    if policy == "zombie":
        _zombie_transfer(manager, settings, by_position, ranking, form, minutes, prices)
        return

    if policy in _CHASERS:
        # Spends its free transfer whenever there is any upgrade at all, and
        # never pays for a second. This is how the conventional player behaves,
        # and the point of the baseline is realism rather than optimality.
        if manager.free_transfers <= 0:
            return
        swap = _best_swap(manager, settings, by_position, ranking, prices)
        if swap is None:
            return
        outgoing, incoming, _ = swap
        _settle(manager, outgoing, incoming, prices)
        manager.free_transfers -= 1
        return

    # Keep swapping while the gain clears what the move costs. A free transfer
    # is close to free, so the bar is a hit's worth of points once the bank is
    # empty; that is the decision the -4 rule actually poses.
    while True:
        swap = _best_swap(manager, settings, by_position, ranking, prices)
        if swap is None:
            return
        outgoing, incoming, gain = swap
        takes_hit = manager.free_transfers <= 0
        if gain <= (_TRANSFER_HIT_POINTS if takes_hit else 0.0):
            return
        _settle(manager, outgoing, incoming, prices)
        if takes_hit:
            manager.result.hit_points += _TRANSFER_HIT_POINTS
        else:
            manager.free_transfers -= 1


def _settle(
    manager: _Manager,
    outgoing: Candidate,
    incoming: Candidate,
    prices: Mapping[int, int],
) -> None:
    """Make the swap and move the money, keeping squad and portfolio in step."""
    manager.portfolio.transfer(outgoing.element_id, incoming.element_id, prices)
    manager.squad[manager.squad.index(outgoing)] = incoming
    manager.result.transfers_made += 1
    manager.pending_transfers.append((outgoing.element_id, incoming.element_id))


def _zombie_transfer(
    manager: _Manager,
    settings: LeagueSettings,
    by_position: Mapping[int, Sequence[Candidate]],
    ranking: Mapping[int, float],
    form: Mapping[int, float],
    minutes: Mapping[int, int],
    prices: Mapping[int, int],
) -> None:
    """Acts only when a player has stopped featuring, and never takes a hit."""
    # Absent from the window and playing nothing in it are different facts. A
    # new signing has no rows yet, and reading that as zero minutes sold him.
    outgoing = [
        player
        for player in manager.squad
        if player.element_id in minutes and minutes[player.element_id] == 0
    ]
    if not outgoing or manager.free_transfers <= 0:
        return
    worst = min(outgoing, key=lambda player: form.get(player.element_id, 0.0))
    replacement = _best_replacement(worst, manager, settings, by_position, ranking, prices)
    if replacement is None:
        return
    _settle(manager, worst, replacement, prices)
    manager.free_transfers -= 1


def _best_swap(
    manager: _Manager,
    settings: LeagueSettings,
    by_position: Mapping[int, Sequence[Candidate]],
    ranking: Mapping[int, float],
    prices: Mapping[int, int],
) -> tuple[Candidate, Candidate, float] | None:
    best: tuple[Candidate, Candidate, float] | None = None
    for player in manager.squad:
        replacement = _best_replacement(player, manager, settings, by_position, ranking, prices)
        if replacement is None:
            continue
        gain = ranking.get(replacement.element_id, 0.0) - ranking.get(player.element_id, 0.0)
        if best is None or gain > best[2]:
            best = (player, replacement, gain)
    return best


def _best_replacement(
    outgoing: Candidate,
    manager: _Manager,
    settings: LeagueSettings,
    by_position: Mapping[int, Sequence[Candidate]],
    ranking: Mapping[int, float],
    prices: Mapping[int, int],
) -> Candidate | None:
    """First affordable, eligible upgrade in a list already sorted by ranking."""
    held = {player.element_id for player in manager.squad}
    budget = manager.portfolio.affordable(outgoing.element_id, prices)
    # An unranked outgoing player used to default to zero, which made every
    # ranked candidate an "upgrade" and bought a full-price replacement for no
    # measured gain. Nothing is known about him, so nothing is claimed.
    current = ranking.get(outgoing.element_id)
    if current is None:
        return None

    for candidate in by_position.get(outgoing.position, ()):
        score = ranking.get(candidate.element_id)
        if score is None or score <= current:
            return None
        cost = prices.get(candidate.element_id, candidate.price_tenths)
        if candidate.element_id in held or cost > budget:
            continue
        if not transfer_respects_club_limit(
            manager.squad, outgoing, candidate, settings.squad_rules
        ):
            continue
        return candidate
    return None


def _squad_cost(squad: Sequence[Candidate]) -> int:
    return sum(player.price_tenths for player in squad)
