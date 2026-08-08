"""Shared state for the mini-league simulation.

It was asked for `minileague.py` to be split so the season loop, the
rival policies and the scoring are independently reviewable. All three need the
same handful of types, so they live here rather than in any one of them: without
this module the split would be a three-way import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from fpl_andres.simulation.chips import (
    ChipName,
    ChipState,
)
from fpl_andres.simulation.season import LineupRules
from fpl_andres.simulation.squad import (
    Candidate,
    SquadRules,
)
from fpl_andres.simulation.valuation import Portfolio

__all__ = [
    "LeagueResult",
    "LeagueSettings",
    "ManagerResult",
    "Policy",
]

Policy = Literal["advised", "rank_aware", "zombie", "hold", "form_chaser", "crowd"]

# Policies that never spend a transfer, so their ranking is only used for team
# selection and captaincy.
_PASSIVE: frozenset[str] = frozenset({"hold"})
# Policies that buy the best available every week they can afford to.
_CHASERS: frozenset[str] = frozenset({"form_chaser", "crowd"})

_TRANSFER_HIT_POINTS = 4
_FORM_WINDOW = 4
_DROPPED_THRESHOLD = 3


@dataclass(frozen=True)
class LeagueSettings:
    """Sourced league rules and policy mix."""

    squad_rules: SquadRules
    lineup_rules: LineupRules
    managers: int = 20
    advised_share: float = 0.25
    rank_aware_share: float = 0.0
    hold_share: float = 0.0
    form_chaser_share: float = 0.0
    crowd_share: float = 0.0
    free_transfers_per_event: int = 1
    max_free_transfers: int = 5
    start_gameweek: int = 7
    # How hard a rank-aware manager leans on ownership. Effective ownership
    # cancels out of the expected gain from a transfer, so it can only ever be a
    # risk setting: cover the field when ahead, take differentials when behind.
    risk_weight: float = 0.3
    chips_enabled: bool = True
    # Floors below which a chip is not worth burning. Expressed in projected
    # points, so they are comparable to everything else the model produces.
    triple_captain_floor: float = 7.0
    bench_boost_floor: float = 12.0
    wildcard_floor: float = 12.0
    free_hit_floor: float = 12.0

    def advised_count(self) -> int:
        return max(1, round(self.managers * self.advised_share))

    def rank_aware_count(self) -> int:
        return round(self.managers * self.rank_aware_share)

    def policy_roster(self) -> list[Policy]:
        """One policy per seat, filling any remainder with zombies.

        Zombie is the filler rather than a share of its own: it is the crowd of
        ordinary managers the named policies are measured against.
        """
        seats: list[Policy] = []
        # Annotated, so the literals are checked against
        # `Policy` here rather than silenced at the `extend` below. A share
        # added for a policy that does not exist is now a type error instead of
        # a seat nobody fills.
        shares: tuple[tuple[Policy, float], ...] = (
            ("advised", self.advised_share),
            ("rank_aware", self.rank_aware_share),
            ("hold", self.hold_share),
            ("form_chaser", self.form_chaser_share),
            ("crowd", self.crowd_share),
        )
        for name, share in shares:
            count = round(self.managers * share)
            if name == "advised":
                count = max(1, count)
            seats.extend([name] * count)
        if len(seats) > self.managers:
            raise ValueError("policy shares exceed the number of managers")
        seats.extend(["zombie"] * (self.managers - len(seats)))
        return seats


@dataclass
class ManagerResult:
    manager_id: int
    policy: Policy
    seed: int
    total_points: int = 0
    transfers_made: int = 0
    hit_points: int = 0
    weekly_points: list[int] = field(default_factory=list)
    chips_played: dict[str, int] = field(default_factory=dict)
    final_team_value_tenths: int = 0

    @property
    def net_points(self) -> int:
        return self.total_points - self.hit_points


@dataclass
class LeagueResult:
    season: str
    settings: LeagueSettings
    managers: list[ManagerResult] = field(default_factory=list)
    # One representative finishing squad per policy, for inspection.
    squad_snapshots: list[tuple[str, list[tuple[int, int]]]] = field(default_factory=list)

    def standings(self) -> list[ManagerResult]:
        return sorted(self.managers, key=lambda manager: -manager.net_points)

    def by_policy(self, policy: Policy) -> list[ManagerResult]:
        return [manager for manager in self.managers if manager.policy == policy]

    def mean_net(self, policy: Policy) -> float:
        cohort = self.by_policy(policy)
        return sum(manager.net_points for manager in cohort) / len(cohort) if cohort else 0.0


@dataclass
class _Manager:
    result: ManagerResult
    squad: list[Candidate]
    free_transfers: int
    portfolio: Portfolio
    chips: ChipState = field(default_factory=ChipState)
    chip_plan: dict[int, ChipName] = field(default_factory=dict)
