"""Plan the next few transfers over a horizon rather than one gameweek.

The unit of value is expected points gained across the planning window, net of
what the move costs. A swap that wins next Saturday and loses the following
month is a bad swap, and only a horizon can tell the difference.

Budget is treated as an allocation problem: a premium is worth its price only if
no combination of cheaper players returns more over the same window. That test
is applied explicitly rather than assumed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from fpl_andres.backtesting.projector import HorizonProjection

__all__ = [
    "PlannedTransfer",
    "TransferPlan",
    "TransferPlanSettings",
    "plan_transfers",
    "premium_is_justified",
]

_HIT_POINTS = 4.0


@dataclass(frozen=True)
class TransferPlanSettings:
    horizon: int = 5
    club_limit: int = 3
    free_transfers: int = 1
    max_moves: int = 6
    # A move must clear this much on top of its cost before it is worth doing.
    # Churn has a real cost the model cannot see: price changes, and being wrong.
    margin: float = 0.5


@dataclass(frozen=True)
class PlannedTransfer:
    out_element_id: int
    in_element_id: int
    gain: float
    cost: float
    spends_free_transfer: bool

    @property
    def net_gain(self) -> float:
        return self.gain - self.cost


@dataclass(frozen=True)
class TransferPlan:
    horizon: int
    moves: tuple[PlannedTransfer, ...]
    squad_points_before: float
    squad_points_after: float

    @property
    def net_gain(self) -> float:
        return sum(move.net_gain for move in self.moves)


def _squad_points(
    squad: Sequence[int], projections: Mapping[int, HorizonProjection], horizon: int
) -> float:
    return sum(
        projections[element_id].points_over(horizon)
        for element_id in squad
        if element_id in projections
    )


def plan_transfers(
    squad: Sequence[int],
    projections: Sequence[HorizonProjection],
    *,
    bank_tenths: int,
    team_by_element: Mapping[int, int],
    settings: TransferPlanSettings | None = None,
) -> TransferPlan:
    """Greedily take the best swap while it clears its cost, up to ``max_moves``.

    Greedy rather than exhaustive: the full problem is a knapsack over hundreds
    of players and several weeks, and a solver that cannot explain its answer is
    worse than a simple rule that can.
    """
    config = settings or TransferPlanSettings()
    by_id = {projection.element_id: projection for projection in projections}
    held = list(squad)
    before = _squad_points(held, by_id, config.horizon)

    bank = bank_tenths
    free = config.free_transfers
    moves: list[PlannedTransfer] = []

    while len(moves) < config.max_moves:
        best: tuple[PlannedTransfer, int] | None = None
        clubs: dict[int, int] = {}
        for element_id in held:
            club = team_by_element.get(element_id)
            if club is not None:
                clubs[club] = clubs.get(club, 0) + 1

        for outgoing_id in held:
            outgoing = by_id.get(outgoing_id)
            if outgoing is None or outgoing.price_tenths is None:
                continue
            affordable = bank + outgoing.price_tenths
            outgoing_club = team_by_element.get(outgoing_id)

            for incoming in projections:
                if incoming.element_id in held or incoming.position != outgoing.position:
                    continue
                if incoming.price_tenths is None or incoming.price_tenths > affordable:
                    continue
                club = team_by_element.get(incoming.element_id)
                if (
                    club is not None
                    and club != outgoing_club
                    and clubs.get(club, 0) >= config.club_limit
                ):
                    continue

                gain = incoming.points_over(config.horizon) - outgoing.points_over(config.horizon)
                cost = 0.0 if free > 0 else _HIT_POINTS
                if gain - cost <= config.margin:
                    continue
                move = PlannedTransfer(
                    out_element_id=outgoing_id,
                    in_element_id=incoming.element_id,
                    gain=gain,
                    cost=cost,
                    spends_free_transfer=free > 0,
                )
                if best is None or move.net_gain > best[0].net_gain:
                    best = (move, affordable - incoming.price_tenths)

        if best is None:
            break
        move, remaining_bank = best
        moves.append(move)
        held[held.index(move.out_element_id)] = move.in_element_id
        bank = remaining_bank
        if move.spends_free_transfer:
            free -= 1

    return TransferPlan(
        horizon=config.horizon,
        moves=tuple(moves),
        squad_points_before=before,
        squad_points_after=_squad_points(held, by_id, config.horizon),
    )


def premium_is_justified(
    premium: HorizonProjection,
    alternatives: Sequence[HorizonProjection],
    *,
    horizon: int,
    spare_tenths: int,
    replacements: int = 2,
) -> bool:
    """Does one expensive player beat spreading the same money over several?

    Compares the premium against the best combination of ``replacements`` players
    affordable with the premium's price plus whatever is spare. Answers the
    'fifteen million on one striker' question directly rather than by feel.
    """
    if premium.price_tenths is None or replacements < 1:
        return True

    budget = premium.price_tenths + spare_tenths
    priced = sorted(
        (
            entry
            for entry in alternatives
            if entry.price_tenths is not None and entry.element_id != premium.element_id
        ),
        key=lambda entry: -entry.points_over(horizon),
    )

    chosen: list[HorizonProjection] = []
    spent = 0
    for entry in priced:
        price = entry.price_tenths or 0
        remaining = replacements - len(chosen) - 1
        # Leave enough for the cheapest possible remainder.
        floor = remaining * min((item.price_tenths or 0) for item in priced)
        if spent + price + floor > budget:
            continue
        chosen.append(entry)
        spent += price
        if len(chosen) == replacements:
            break

    if len(chosen) < replacements:
        return True
    spread = sum(entry.points_over(horizon) for entry in chosen)
    return premium.points_over(horizon) >= spread
