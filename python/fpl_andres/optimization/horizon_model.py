"""The variable layout and constraint blocks of the horizon MILP.

`HighsHorizonOptimizer.solve` was around two hundred lines of
nested indexing with no names on any of it: a reader had to work out from
`variable(free_used_offset, event_index, index)` which of eleven rules was being
written, and there was no way to test one block without solving the whole
problem.

The rules of Fantasy Premier League are the specification here, and each one is
now a function named after it. `squad_composition` is "fifteen players, eleven
of them start, one of those is captain". `free_transfer_ledger` is the
accounting that decides whether a transfer costs four points. Reading the
solver should be reading the rules.

Nothing about the model changed. This is the same matrix, written down where it
can be seen.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from fpl_andres.optimization.contracts import (
        HorizonEvent,
        HorizonOptimizationRequest,
        HorizonPlayerForecast,
    )


@dataclass
class HorizonModel:
    """Variable layout, and the constraints written into it so far.

    One decision variable per (block, event, player), laid out as six contiguous
    blocks so a variable's index is arithmetic rather than a lookup. The
    per-event scalars follow.

    Constraints are held as (row, column, value) triples rather than as dense
    rows. Every constraint names a handful of variables out
    of thousands, so a dense row is almost entirely zeros and the matrix grew as
    players squared.
    """

    request: HorizonOptimizationRequest
    player_ids: tuple[int, ...]
    forecasts: dict[tuple[int, int], HorizonPlayerForecast]

    rows: list[int] = field(default_factory=list)
    columns: list[int] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    lower_bounds: list[float] = field(default_factory=list)
    upper_bounds: list[float] = field(default_factory=list)
    constraint_count: int = 0

    def __post_init__(self) -> None:
        self.events = self.request.events
        self.event_count = len(self.events)
        self.player_count = len(self.player_ids)
        self.player_index = {element_id: index for index, element_id in enumerate(self.player_ids)}
        self.current = {player.element_id: player for player in self.request.current_squad}

        block = self.event_count * self.player_count
        self.block_size = block
        self.squad_offset = 0
        self.lineup_offset = block
        self.captain_offset = 2 * block
        self.transfer_in_offset = 3 * block
        self.transfer_out_offset = 4 * block
        self.paid_offset = 5 * block
        self.free_offset = self.paid_offset + self.event_count
        self.free_used_offset = self.free_offset + self.event_count + 1
        self.free_compare_offset = self.free_used_offset + self.event_count
        self.cap_compare_offset = self.free_compare_offset + self.event_count
        self.bank_offset = self.cap_compare_offset + self.event_count
        self.variable_count = self.bank_offset + self.event_count + 1

    def variable(self, offset: int, event_index: int, player: int) -> int:
        return offset + event_index * self.player_count + player

    def add(
        self,
        coefficients: dict[int, float],
        *,
        lower: float = -np.inf,
        upper: float = np.inf,
    ) -> None:
        for index, coefficient in coefficients.items():
            self.rows.append(self.constraint_count)
            self.columns.append(index)
            self.values.append(coefficient)
        self.constraint_count += 1
        self.lower_bounds.append(lower)
        self.upper_bounds.append(upper)

    def forecast(self, event: HorizonEvent, element_id: int) -> HorizonPlayerForecast:
        return self.forecasts[(event.event, element_id)]

    def all_players(self, offset: int, event_index: int) -> dict[int, float]:
        """Every player's variable in one block, coefficient 1."""
        return {
            self.variable(offset, event_index, index): 1.0 for index in range(self.player_count)
        }


def negated(coefficients: dict[int, float]) -> dict[int, float]:
    return {index: -value for index, value in coefficients.items()}


# --------------------------------------------------------------- composition


def squad_composition(model: HorizonModel, event_index: int) -> None:
    """Fifteen in the squad, eleven of them start, one of those is captain.

    The counts come from the published rules rather than from constants: FPL has
    changed the squad size before, and a number written here would be a second
    source of truth for something the game already states.
    """
    rules = model.request.rules
    model.add(
        model.all_players(model.squad_offset, event_index),
        lower=rules.squad_size,
        upper=rules.squad_size,
    )
    model.add(
        model.all_players(model.lineup_offset, event_index),
        lower=rules.lineup_size,
        upper=rules.lineup_size,
    )
    model.add(
        model.all_players(model.captain_offset, event_index),
        lower=1.0,
        upper=1.0,
    )


def selection_hierarchy(model: HorizonModel, event_index: int) -> None:
    """A starter must be in the squad; a captain must be a starter.

    Without these the solver would happily start a player it never bought.
    """
    for index in range(model.player_count):
        model.add(
            {
                model.variable(model.lineup_offset, event_index, index): 1.0,
                model.variable(model.squad_offset, event_index, index): -1.0,
            },
            upper=0.0,
        )
        model.add(
            {
                model.variable(model.captain_offset, event_index, index): 1.0,
                model.variable(model.lineup_offset, event_index, index): -1.0,
            },
            upper=0.0,
        )


def squad_continuity(model: HorizonModel, event_index: int) -> None:
    """A player is in this week's squad if he was in last week's, plus or minus
    a transfer.

    The first event is pinned to the squad the manager actually holds, which is
    what stops the horizon from inventing a starting point it prefers.
    """
    for element_id, index in model.player_index.items():
        incoming = model.variable(model.transfer_in_offset, event_index, index)
        outgoing = model.variable(model.transfer_out_offset, event_index, index)
        flow = {
            model.variable(model.squad_offset, event_index, index): 1.0,
            incoming: -1.0,
            outgoing: 1.0,
        }
        if event_index == 0:
            held = 1.0 if element_id in model.current else 0.0
            model.add(flow, lower=held, upper=held)
        else:
            flow[model.variable(model.squad_offset, event_index - 1, index)] = -1.0
            model.add(flow, lower=0.0, upper=0.0)
        # Buying and selling the same player in the same week is a way to spend
        # a transfer on nothing, and the solver will do it to satisfy a count.
        model.add({incoming: 1.0, outgoing: 1.0}, upper=1.0)


def position_quotas(model: HorizonModel, event_index: int) -> None:
    """Exactly two keepers, five defenders and so on, and a legal formation."""
    event = model.events[event_index]
    for position in model.request.rules.positions:
        indices = [
            index
            for element_id, index in model.player_index.items()
            if model.forecast(event, element_id).position_id == position.position_id
        ]
        model.add(
            {model.variable(model.squad_offset, event_index, index): 1.0 for index in indices},
            lower=position.squad_count,
            upper=position.squad_count,
        )
        model.add(
            {model.variable(model.lineup_offset, event_index, index): 1.0 for index in indices},
            lower=position.lineup_minimum,
            upper=position.lineup_maximum,
        )


def club_limit(model: HorizonModel, event_index: int) -> None:
    """At most three from any one club.

    Grouped by the club id in the forecast rather than by a stored squad club,
    because a player who moves mid-season belongs to whoever the forecast says
    -- and a wrong club id here splits one club into two groups and lets six
    players through as three plus three."""
    event = model.events[event_index]
    by_club: defaultdict[int, list[int]] = defaultdict(list)
    for element_id, index in model.player_index.items():
        by_club[model.forecast(event, element_id).team_id].append(index)
    for indices in by_club.values():
        model.add(
            {model.variable(model.squad_offset, event_index, index): 1.0 for index in indices},
            upper=model.request.rules.club_limit,
        )


# ----------------------------------------------------------------- transfers


def transfer_balance(model: HorizonModel, event_index: int) -> None:
    """Every player in is a player out, and no more than the cap either way.

    The squad size is already fixed per event, so this is implied -- but stating
    it directly gives the solver a much tighter relaxation to work from.
    """
    incoming = model.all_players(model.transfer_in_offset, event_index)
    outgoing = model.all_players(model.transfer_out_offset, event_index)
    model.add(incoming, upper=model.request.rules.transfer_cap)
    model.add({**incoming, **negated(outgoing)}, lower=0.0, upper=0.0)


def bank_flow(model: HorizonModel, event_index: int) -> None:
    """Money in the bank after transfers is money before, plus sales, less buys.

    Selling and buying prices are separate because FPL's selling price is not
    the market price: a player bought before a rise sells for less than he now
    costs, and treating the two as one is the classic way to produce a plan the
    manager cannot afford.
    """
    event = model.events[event_index]
    flow = {
        model.bank_offset + event_index + 1: 1.0,
        model.bank_offset + event_index: -1.0,
    }
    for element_id, index in model.player_index.items():
        forecast = model.forecast(event, element_id)
        flow[
            model.variable(model.transfer_out_offset, event_index, index)
        ] = -forecast.sell_price_tenths
        flow[model.variable(model.transfer_in_offset, event_index, index)] = (
            forecast.buy_price_tenths
        )
    model.add(flow, lower=0.0, upper=0.0)


def free_transfer_ledger(model: HorizonModel, event_index: int) -> None:
    """How many transfers were free, how many were paid, and how many carry.

    This is the block worth naming. Free transfers used is the minimum of the
    transfers made and the free transfers held, and a minimum is not linear --
    it needs two inequalities plus a binary saying which one is tight. The same
    shape appears again for the carry, which is capped rather than unbounded.

    `big_m` is deliberately derived rather than picked. A constant large enough
    "to be safe" makes the relaxation weaker and the solve slower; too small
    silently forbids legal plans. This is the largest the two sides can differ
    by, and no larger.
    """
    rules = model.request.rules
    transfers = model.all_players(model.transfer_in_offset, event_index)
    free_before = model.free_offset + event_index
    free_after = model.free_offset + event_index + 1
    free_used = model.free_used_offset + event_index
    free_compare = model.free_compare_offset + event_index
    cap_compare = model.cap_compare_offset + event_index
    paid = model.paid_offset + event_index
    big_m = float(
        rules.transfer_cap
        + rules.transfer_rules.maximum_free_transfers
        + rules.transfer_rules.weekly_free_transfers
    )

    # free_used <= transfers, and free_used <= free_before.
    model.add({free_used: 1.0, **negated(transfers)}, upper=0.0)
    model.add({free_used: 1.0, free_before: -1.0}, upper=0.0)
    # One of the two is tight, chosen by free_compare.
    model.add(
        {free_used: 1.0, **negated(transfers), free_compare: big_m},
        lower=0.0,
    )
    model.add(
        {free_used: 1.0, free_before: -1.0, free_compare: -big_m},
        lower=-big_m,
    )
    # Everything not free is paid for, at four points each.
    model.add(
        {paid: 1.0, free_used: 1.0, **negated(transfers)},
        lower=0.0,
        upper=0.0,
    )

    # Carry: free_after = min(free_before - free_used + weekly, maximum).
    weekly = rules.transfer_rules.weekly_free_transfers
    maximum = rules.transfer_rules.maximum_free_transfers
    model.add(
        {free_after: 1.0, free_before: -1.0, free_used: 1.0},
        upper=weekly,
    )
    model.add(
        {free_after: 1.0, free_before: -1.0, free_used: 1.0, cap_compare: big_m},
        lower=weekly,
    )
    model.add({free_after: 1.0, cap_compare: -big_m}, lower=maximum - big_m)


# ----------------------------------------------------- horizon-wide and start


def sell_each_player_once(model: HorizonModel) -> None:
    """A player can be sold once across the whole horizon, and only if held.

    Without this the solver can sell a player it does not own in a later week to
    balance a transfer count, and the plan reads as though a free player were
    turned into money.
    """
    for element_id, index in model.player_index.items():
        model.add(
            {
                model.variable(model.transfer_out_offset, event_index, index): 1.0
                for event_index in range(model.event_count)
            },
            upper=1.0 if element_id in model.current else 0.0,
        )


def opening_position(model: HorizonModel) -> None:
    """Free transfers and bank at the start are facts, not decisions."""
    model.add(
        {model.free_offset: 1.0},
        lower=model.request.available_free_transfers,
        upper=model.request.available_free_transfers,
    )
    model.add(
        {model.bank_offset: 1.0},
        lower=model.request.bank_tenths,
        upper=model.request.bank_tenths,
    )


PER_EVENT_BLOCKS = (
    squad_composition,
    selection_hierarchy,
    squad_continuity,
    position_quotas,
    club_limit,
    transfer_balance,
    bank_flow,
    free_transfer_ledger,
)

HORIZON_BLOCKS = (sell_each_player_once, opening_position)


def build_constraints(model: HorizonModel) -> None:
    """Every rule, in an order chosen for reading rather than for the solver."""
    for event_index in range(model.event_count):
        for block in PER_EVENT_BLOCKS:
            block(model, event_index)
    for horizon_block in HORIZON_BLOCKS:
        horizon_block(model)


__all__ = [
    "HORIZON_BLOCKS",
    "PER_EVENT_BLOCKS",
    "HorizonModel",
    "bank_flow",
    "build_constraints",
    "club_limit",
    "free_transfer_ledger",
    "negated",
    "opening_position",
    "position_quotas",
    "selection_hierarchy",
    "sell_each_player_once",
    "squad_composition",
    "squad_continuity",
    "transfer_balance",
]
