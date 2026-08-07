"""A plan for every remaining gameweek, solved in overlapping windows.

## Why not one solve

The horizon MILP is exact but superlinear in events. Measured on this machine
with a 100-player pool: 3 events in 0.16s, 12 in 9.13s, 16 in 147.44s. A single
38-event solve over a real candidate pool is not going to return. That is the
reason the season plan was previously declared out of scope.

Solving it in overlapping windows does return. Each window is optimised exactly,
the first `stride` gameweeks of its answer are committed, and the resulting
squad, bank and free-transfer balance become the opening state of the next
window. The overlap is what stops the planner from playing each window as if the
season ended at its edge — a squad assembled for gameweeks 7 to 11 is chosen
knowing 12 and 13 exist.

This is a receding-horizon plan, not a globally optimal one. A single optimal
38-event solution exists and is unreachable; nothing here pretends otherwise.

## Why confidence has to travel with it

Every gameweek after the next one assumes no injury, no price change, no
transfer the manager makes on a whim, and a squad list that in reality turns
over every January. The plan is still worth having — knowing you are two
transfers away from a good gameweek 9 changes what you do in gameweek 6 — but a
row for gameweek 34 is worth less than a row for gameweek 2, and the artifact
says so rather than leaving a reader to infer it from a number's precision.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from fpl_andres.optimization.contracts import (
    CurrentSquadPlayer,
    HorizonEvent,
    HorizonEventPlan,
    HorizonOptimizationRequest,
    HorizonPlayerForecast,
    OptimizationRules,
    OptimizationStateEvidence,
)
from fpl_andres.optimization.horizon import HighsHorizonOptimizer

__all__ = [
    "COMMIT_EVENTS",
    "SEASON_OPENER",
    "WINDOW_EVENTS",
    "Confidence",
    "PlannedEvent",
    "SeasonPlan",
    "confidence_for",
    "plan_season",
]

# Eight events per solve, committing three, so five weeks of lookahead sit past
# the commit boundary.
#
# It was five and three, which is two weeks of sight past the weeks a window
# actually acts on. That is too short for the shape transfers exist to exploit:
# a club with five soft fixtures and then five hard ones looks uniformly good
# for the whole of a five-week window, so the planner buys into the run and only
# discovers the turn while standing in it. Eight covers the good half and the
# start of the bad one, which is what makes selling before a cliff a decision
# rather than a reaction.
#
# Measured on the full-season test, same machine: 6.4 s at five, 23.1 s at
# eight. The solve is superlinear in the window and that is the trade being
# made knowingly -- a publish step has minutes, and a planner that cannot see a
# fixture swing before it arrives is the more expensive problem.
WINDOW_EVENTS = 8
COMMIT_EVENTS = 3

# Before the first deadline a manager may change the whole squad at no cost, so
# the opening gameweek is not a transfer window and nothing is "rolled" into it.
SEASON_OPENER = 1

Confidence = Literal["firm", "projected", "provisional"]

# Where the bands come from, so they are not three words chosen to sound careful:
#
# "firm"        the next deadline. Prices, availability and fixtures are all
#               observed. Only the points are projected.
# "projected"   inside the horizon the repository has measured. Rank correlation
#               at a multi-week horizon is 0.48-0.51 against 0.24-0.32 at one
#               week, because weekly noise averages out. The squad is still
#               approximately today's squad.
# "provisional" beyond it. Fixtures are known; almost nothing else is. Treat the
#               shape as information and the specific transfer as an
#               illustration of it.
FIRM_THROUGH = 1
PROJECTED_THROUGH = 8


def confidence_for(event: int, first_event: int) -> Confidence:
    ahead = event - first_event
    if ahead < FIRM_THROUGH:
        return "firm"
    if ahead < PROJECTED_THROUGH:
        return "projected"
    return "provisional"


@dataclass(frozen=True)
class PlannedEvent:
    event: int
    plan: HorizonEventPlan
    confidence: Confidence


@dataclass(frozen=True)
class SeasonPlan:
    events: tuple[PlannedEvent, ...]
    windows_solved: int
    pool_size: int

    @property
    def net_expected_points(self) -> float:
        return sum(planned.plan.net_expected_points for planned in self.events)


def _windows(events: Sequence[int]) -> list[tuple[int, int]]:
    """Start and stop offsets for each solve, as half-open ranges."""
    spans: list[tuple[int, int]] = []
    start = 0
    while start < len(events):
        stop = min(start + WINDOW_EVENTS, len(events))
        # A horizon request needs two events. A trailing single gameweek is
        # folded back into the previous window rather than solved alone.
        if stop - start < 2:
            if spans:
                spans[-1] = (spans[-1][0], stop)
                break
            return [(start, stop)]
        spans.append((start, stop))
        if stop == len(events):
            break
        start += COMMIT_EVENTS
    return spans


def plan_season(
    *,
    events: Sequence[int],
    cutoffs: Mapping[int, datetime],
    forecasts: Sequence[HorizonPlayerForecast],
    opening_squad: Sequence[CurrentSquadPlayer],
    bank_tenths: int,
    free_transfers: int,
    rules: OptimizationRules,
    state_evidence: OptimizationStateEvidence,
    time_limit_seconds: float = 30.0,
) -> SeasonPlan:
    """Chain window solves across the season, carrying squad state forward."""
    if len(events) < 2:
        raise ValueError("a season plan needs at least two gameweeks")

    ordered = sorted(events)
    by_event: dict[int, list[HorizonPlayerForecast]] = {}
    for forecast in forecasts:
        by_event.setdefault(forecast.event, []).append(forecast)

    missing = [event for event in ordered if not by_event.get(event)]
    if missing:
        raise ValueError(f"no forecasts for gameweeks {missing}")

    optimizer = HighsHorizonOptimizer(time_limit_seconds=time_limit_seconds)
    squad = list(opening_squad)
    bank = bank_tenths
    weekly_free_transfers = rules.transfer_rules.weekly_free_transfers
    # The opening gameweek is squad selection, not a transfer window. There is
    # nothing to spend and nothing to roll, and the first award lands for
    # gameweek 2 — so a plan that starts at gameweek 1 must not reach gameweek 2
    # holding two.
    available = 0 if ordered[0] == SEASON_OPENER else free_transfers
    committed: list[PlannedEvent] = []
    windows = _windows(ordered)

    for index, (start, stop) in enumerate(windows):
        span = ordered[start:stop]
        request = HorizonOptimizationRequest(
            events=tuple(
                HorizonEvent(
                    event=event,
                    prediction_cutoff=cutoffs[event],
                    # Later gameweeks in a window are lookahead, not the answer.
                    # Weighting them below the committed ones keeps the solve
                    # from trading a certain gameweek for a speculative one.
                    objective_weight=1.0 if offset < COMMIT_EVENTS else 0.5,
                )
                for offset, event in enumerate(span)
            ),
            forecasts=tuple(forecast for event in span for forecast in by_event[event]),
            current_squad=tuple(squad),
            bank_tenths=bank,
            available_free_transfers=available,
            state_evidence=state_evidence,
            price_scenario="provided_event_prices",
            objective="expected_value",
            chip_scenario="none",
            rules=rules,
        )

        result = optimizer.solve(request)
        is_last = index == len(windows) - 1
        keep = len(span) if is_last else min(COMMIT_EVENTS, len(span))

        for offset, event_plan in enumerate(result.events[:keep]):
            committed.append(
                PlannedEvent(
                    event=event_plan.event,
                    plan=event_plan,
                    confidence=confidence_for(event_plan.event, ordered[0]),
                )
            )
            if offset == keep - 1:
                price_at = {
                    forecast.element_id: forecast.sell_price_tenths
                    for forecast in by_event[event_plan.event]
                }
                squad = [
                    CurrentSquadPlayer(
                        element_id=element_id,
                        selling_price_tenths=price_at[element_id],
                    )
                    for element_id in event_plan.squad_element_ids
                ]
                bank = event_plan.bank_after_tenths
                # Gameweek 1 is squad selection, not a transfer window: FPL
                # charges nothing for it and awards the first free transfer for
                # gameweek 2. Carrying the opening allowance forward would hand
                # the plan a dozen free transfers it never earned.
                available = (
                    weekly_free_transfers
                    if event_plan.event == SEASON_OPENER
                    else event_plan.free_transfers_next_event
                )

    return SeasonPlan(
        events=tuple(committed),
        windows_solved=len(windows),
        pool_size=len({forecast.element_id for forecast in forecasts}),
    )
