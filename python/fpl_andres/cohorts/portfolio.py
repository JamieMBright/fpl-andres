"""Reconcile a cohort's picks into one portfolio — the ETF.

The catalogue knows *who* the good managers are. It does not know what they own:
the sweep stores season ranks, not squads. This is the part that turns 2,207
entry ids into a single holding, once a gameweek.

## What has to be reconciled, and why each one is a trap

**Partial capture.** Two thousand requests will not all succeed. If ownership is
divided by "however many answered", the denominator moves every week and a
player looks to be drifting when the sample drifted instead. Coverage is
therefore measured, reported, and floored: below the floor the snapshot is
refused rather than published with a quiet asterisk.

**Chips.** A Free Hit squad is a one-week rental and says nothing about what the
manager holds, so it is excluded from holdings and counted separately. Triple
Captain multiplies the armband by three rather than two. Bench Boost makes all
fifteen count, so "started" cannot be inferred from position alone.

**Captaincy is not ownership.** Sixty percent owned and forty percent captained
is a different exposure from sixty and two. Effective ownership adds the armband
on top of the holding, which is what makes it the number that decides a
transfer.

**Deadline intent, not outcome.** Picks are read after the deadline but before
the results settle, and are never reconciled against what happened. Auto-subs
and non-starters change what scored; they do not change what the cohort chose,
and what it chose is the signal.

**Cohort drift.** Membership changes whenever the catalogue is re-swept. A
series whose population silently changes is not a series, so every snapshot pins
the cohort revision it was taken over. Exact ranked-500 captures carry a hashed,
event-specific membership and publish separately from the full catalogue.

**Equal weight.** Each manager counts once. Weighting by rank would encode a
claim that this season's league table predicts next week, which is exactly the
claim `cohort.json` already records as unmeasurable on a cohort selected for
past success.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from statistics import median
from typing import Literal

from fpl_andres.planning.opening import OpeningSettings, SquadPlan, choose_opening_squad
from fpl_andres.simulation.squad import Candidate, SquadRules

__all__ = [
    "MINIMUM_COVERAGE",
    "CoverageTooLow",
    "DistributionSummary",
    "EntryHistory",
    "Holding",
    "KeeperPairing",
    "ManagerPicks",
    "OutfieldTrio",
    "Pick",
    "PopularitySquad",
    "Portfolio",
    "PortfolioAggregate",
    "PortfolioBasis",
    "PortfolioStructure",
    "SeasonStanding",
    "aggregate_manager_history",
    "reconcile",
    "summarize_structure",
]

# Below this share of the cohort the snapshot is refused. Set where a missing
# tail can still move a mid-ownership player by less than a percentage point.
MINIMUM_COVERAGE = 0.9

# Chips that change what a squad means, rather than what it scores.
FREE_HIT = "freehit"
TRIPLE_CAPTAIN = "3xc"
BENCH_BOOST = "bboost"
PortfolioBasis = Literal["catalogue-at-deadline", "ranked-500"]


class CoverageTooLow(RuntimeError):
    """Raised when too little of the cohort answered to publish a portfolio."""


@dataclass(frozen=True)
class Pick:
    element_id: int
    """1-15. Twelve and above is the bench unless Bench Boost is active."""
    position: int
    multiplier: int
    is_captain: bool
    is_vice_captain: bool

    @property
    def started(self) -> bool:
        # The published multiplier is zero for an unused bench player, which is
        # the only thing that distinguishes a bench slot under Bench Boost.
        return self.multiplier > 0


@dataclass(frozen=True)
class ManagerPicks:
    entry_id: int
    event: int
    picks: tuple[Pick, ...]
    active_chip: str | None = None
    history: EntryHistory | None = None

    @property
    def captain(self) -> int | None:
        for pick in self.picks:
            if pick.is_captain:
                return pick.element_id
        return None

    @property
    def vice_captain(self) -> int | None:
        for pick in self.picks:
            if pick.is_vice_captain:
                return pick.element_id
        return None


@dataclass(frozen=True)
class Holding:
    element_id: int
    owned: int
    started: int
    captained: int
    vice_captained: int
    owned_share: float
    started_share: float
    captained_share: float
    effective_ownership: float
    """Started share plus the armband on top, counting a triple captain twice."""


@dataclass(frozen=True)
class EntryHistory:
    points: int
    points_on_bench: int
    value_tenths: int
    bank_tenths: int
    event_transfers: int
    event_transfers_cost: int
    # Cumulative season figures, not this gameweek's alone. FPL omits
    # `overall_rank` for an entry it has not ranked yet, so it is the one
    # optional field here; `total_points` is set the moment a history exists.
    total_points: int | None = None
    overall_rank: int | None = None


@dataclass(frozen=True)
class SeasonStanding:
    """One entry's live season position, published with no entry id attached.

    The point of the whole reconciler is that a manager's identity never
    survives past this module. A bag of (rank, points) pairs says how the
    cohort is doing this season without saying who; the pairs are sorted by
    the caller before publishing, which discards even the order they were
    read in.
    """

    overall_rank: int | None
    total_points: int


@dataclass(frozen=True)
class DistributionSummary:
    mean: float
    median: float
    p10: float
    p90: float
    minimum: int
    maximum: int


@dataclass(frozen=True)
class PortfolioAggregate:
    event: int
    cohort_revision: str
    attempted: int
    responded: int
    chips: dict[str, int]
    total_points: DistributionSummary
    bench_points: DistributionSummary
    squad_value_tenths: DistributionSummary
    bank_tenths: DistributionSummary
    event_transfers: DistributionSummary
    transfer_cost: DistributionSummary
    transfers_available: bool
    season_standing: tuple[SeasonStanding, ...] = ()

    @property
    def coverage(self) -> float:
        return self.responded / self.attempted if self.attempted else 0.0


@dataclass(frozen=True)
class Portfolio:
    event: int
    cohort_revision: str
    attempted: int
    responded: int
    counted: int
    """Responded minus the Free Hit squads, which are excluded from holdings."""
    free_hit: int
    holdings: tuple[Holding, ...]
    basis: PortfolioBasis = "catalogue-at-deadline"

    @property
    def coverage(self) -> float:
        return self.responded / self.attempted if self.attempted else 0.0


@dataclass(frozen=True)
class KeeperPairing:
    starter_element_id: int
    bench_element_id: int
    count: int
    share: float


@dataclass(frozen=True)
class OutfieldTrio:
    """Three outfield players held together, the most common combination FPL's
    five-a-position squad rule allows within that position.

    The keeper pair is unambiguous because a squad owns exactly two. A squad
    owns five defenders and five midfielders, so a trio is one combination
    among ten, chosen because it is the one held together most often. Where a
    position holds fewer than three, no trio is published rather than one
    invented from a pair.
    """

    position: int
    element_ids: tuple[int, int, int]
    count: int
    share: float


@dataclass(frozen=True)
class PopularitySquad:
    squad: tuple[int, ...]
    starters: tuple[int, ...]
    bench: tuple[int, ...]
    formation: tuple[int, int, int]
    spent_tenths: int
    xi_spent_tenths: int
    mean_ownership: float
    mean_started_share: float


@dataclass(frozen=True)
class PortfolioStructure:
    event: int
    cohort_revision: str
    attempted: int
    responded: int
    keeper_pairings: tuple[KeeperPairing, ...]
    common_starting_xi: tuple[int, ...]
    formation: tuple[int, int, int]
    positional_spend: dict[int, DistributionSummary]
    outfield_trios: tuple[OutfieldTrio, ...] = ()
    popularity_squad: PopularitySquad | None = None

    @property
    def coverage(self) -> float:
        return self.responded / self.attempted if self.attempted else 0.0


def reconcile(
    captured: Sequence[ManagerPicks],
    *,
    event: int,
    attempted: int,
    cohort_revision: str,
    minimum_coverage: float = MINIMUM_COVERAGE,
    basis: PortfolioBasis = "catalogue-at-deadline",
) -> Portfolio:
    """Fold a gameweek of captured picks into one portfolio.

    `attempted` is the size of the cohort asked, not the number that answered.
    Passing the latter is how a shrinking sample turns into a moving ownership
    number that looks like managers changing their minds.
    """
    if attempted <= 0:
        raise ValueError("a portfolio needs a cohort to be taken over")
    if basis not in ("catalogue-at-deadline", "ranked-500"):
        raise ValueError(f"unsupported portfolio basis: {basis}")

    wrong_event = [row.entry_id for row in captured if row.event != event]
    if wrong_event:
        raise ValueError(f"picks from another gameweek for entries {wrong_event}")

    duplicates = len(captured) - len({row.entry_id for row in captured})
    if duplicates:
        raise ValueError(f"{duplicates} entries captured more than once")

    responded = len(captured)
    if responded > attempted:
        raise ValueError("more managers answered than were asked")

    coverage = responded / attempted
    if coverage < minimum_coverage:
        raise CoverageTooLow(
            f"only {responded} of {attempted} managers answered "
            f"({coverage:.1%}); below the {minimum_coverage:.0%} floor, so this "
            f"gameweek has no portfolio rather than a misleading one"
        )

    counting = [row for row in captured if row.active_chip != FREE_HIT]
    free_hit = responded - len(counting)
    if not counting:
        raise CoverageTooLow("every captured squad was a Free Hit; nothing to hold")

    owned: dict[int, int] = {}
    started: dict[int, int] = {}
    captained: dict[int, int] = {}
    vice: dict[int, int] = {}
    armband: dict[int, float] = {}

    for row in counting:
        triple = row.active_chip == TRIPLE_CAPTAIN
        for element_id in {pick.element_id for pick in row.picks}:
            owned[element_id] = owned.get(element_id, 0) + 1
        for pick in row.picks:
            if pick.started:
                started[pick.element_id] = started.get(pick.element_id, 0) + 1
            if pick.is_captain:
                captained[pick.element_id] = captained.get(pick.element_id, 0) + 1
                # A captain contributes one extra share, a triple captain two.
                armband[pick.element_id] = armband.get(pick.element_id, 0.0) + (
                    2.0 if triple else 1.0
                )
            if pick.is_vice_captain:
                vice[pick.element_id] = vice.get(pick.element_id, 0) + 1

    total = len(counting)
    holdings = tuple(
        sorted(
            (
                Holding(
                    element_id=element_id,
                    owned=count,
                    started=started.get(element_id, 0),
                    captained=captained.get(element_id, 0),
                    vice_captained=vice.get(element_id, 0),
                    owned_share=count / total,
                    started_share=started.get(element_id, 0) / total,
                    captained_share=captained.get(element_id, 0) / total,
                    effective_ownership=(started.get(element_id, 0) + armband.get(element_id, 0.0))
                    / total,
                )
                for element_id, count in owned.items()
            ),
            key=lambda holding: (-holding.effective_ownership, holding.element_id),
        )
    )

    return Portfolio(
        event=event,
        cohort_revision=cohort_revision,
        attempted=attempted,
        responded=responded,
        counted=total,
        free_hit=free_hit,
        holdings=holdings,
        basis=basis,
    )


def summarize_structure(
    captured: Sequence[ManagerPicks],
    *,
    event: int,
    attempted: int,
    cohort_revision: str,
    element_types: Mapping[int, int],
    team_ids: Mapping[int, int],
    prices: Mapping[int, int],
    minimum_coverage: float = MINIMUM_COVERAGE,
) -> PortfolioStructure:
    """Publish joint squad choices without retaining manager identity."""
    if attempted <= 0:
        raise ValueError("a portfolio structure needs a cohort")
    rows = [row for row in captured if row.active_chip != FREE_HIT]
    if any(row.event != event for row in rows):
        raise ValueError("portfolio structure contains another gameweek")
    if len({row.entry_id for row in rows}) != len(rows):
        raise ValueError("portfolio structure contains duplicate managers")
    if len(captured) / attempted < minimum_coverage:
        raise CoverageTooLow(
            f"only {len(captured)} of {attempted} structures answered; "
            f"below the {minimum_coverage:.0%} floor"
        )
    if not rows:
        raise CoverageTooLow("every captured squad was a Free Hit; no structure remains")

    pair_counts: dict[tuple[int, int], int] = {}
    trio_counts: dict[tuple[int, tuple[int, int, int]], int] = {}
    formation_counts: dict[tuple[int, int, int], int] = {}
    owned_counts: dict[int, int] = {}
    started_counts: dict[int, int] = {}
    spend: dict[int, list[int]] = {position: [] for position in range(1, 5)}
    for row in rows:
        squad_ids = {pick.element_id for pick in row.picks}
        for element_id in squad_ids:
            owned_counts[element_id] = owned_counts.get(element_id, 0) + 1
        for position in (2, 3, 4):
            held = sorted(
                element_id for element_id in squad_ids if element_types.get(element_id) == position
            )
            for combo in combinations(held, 3):
                key = (position, combo)
                trio_counts[key] = trio_counts.get(key, 0) + 1
        keepers = [pick for pick in row.picks if element_types.get(pick.element_id) == 1]
        starters = [pick for pick in row.picks if pick.position <= 11]
        starting_keeper = next((pick for pick in keepers if pick.position <= 11), None)
        bench_keeper = next((pick for pick in keepers if pick.position > 11), None)
        if starting_keeper is not None and bench_keeper is not None:
            starter, bench = sorted((starting_keeper.element_id, bench_keeper.element_id))
            pair = (starter, bench)
            pair_counts[pair] = pair_counts.get(pair, 0) + 1
        formation = (
            sum(1 for pick in starters if element_types.get(pick.element_id) == 2),
            sum(1 for pick in starters if element_types.get(pick.element_id) == 3),
            sum(1 for pick in starters if element_types.get(pick.element_id) == 4),
        )
        if len(starters) == 11 and sum(formation) == 10:
            formation_counts[formation] = formation_counts.get(formation, 0) + 1
        for pick in starters:
            started_counts[pick.element_id] = started_counts.get(pick.element_id, 0) + 1
        for position in range(1, 5):
            position_spend = sum(
                prices[pick.element_id]
                for pick in row.picks
                if element_types.get(pick.element_id) == position and pick.element_id in prices
            )
            spend[position].append(position_spend)

    formation = max(formation_counts, key=lambda value: (formation_counts[value], value))
    required = {1: 1, 2: formation[0], 3: formation[1], 4: formation[2]}
    common: list[int] = []
    for position in range(1, 5):
        candidates = sorted(
            (
                (count, element_id)
                for element_id, count in started_counts.items()
                if element_types.get(element_id) == position
            ),
            key=lambda row: (-row[0], row[1]),
        )
        common.extend(element_id for _, element_id in candidates[: required[position]])

    total = len(rows)
    pairings = tuple(
        KeeperPairing(
            starter_element_id=starter,
            bench_element_id=bench,
            count=count,
            share=count / total,
        )
        for (starter, bench), count in sorted(
            pair_counts.items(), key=lambda row: (-row[1], row[0])
        )
    )
    outfield_trios: list[OutfieldTrio] = []
    for position in (2, 3, 4):
        trio_candidates = sorted(
            (
                (count, combo)
                for (candidate_position, combo), count in trio_counts.items()
                if candidate_position == position
            ),
            key=lambda row: (-row[0], row[1]),
        )
        if not trio_candidates:
            continue
        count, combo = trio_candidates[0]
        outfield_trios.append(
            OutfieldTrio(position=position, element_ids=combo, count=count, share=count / total)
        )
    popularity = _popularity_squad(
        pairings,
        owned_counts,
        started_counts,
        element_types,
        team_ids,
        prices,
        total,
    )
    return PortfolioStructure(
        event=event,
        cohort_revision=cohort_revision,
        attempted=attempted,
        responded=len(captured),
        keeper_pairings=pairings,
        common_starting_xi=tuple(common),
        formation=formation,
        positional_spend={position: _summary(values) for position, values in spend.items()},
        outfield_trios=tuple(outfield_trios),
        popularity_squad=popularity,
    )


def _popularity_squad(
    pairings: Sequence[KeeperPairing],
    owned_counts: Mapping[int, int],
    started_counts: Mapping[int, int],
    element_types: Mapping[int, int],
    team_ids: Mapping[int, int],
    prices: Mapping[int, int],
    total: int,
) -> PopularitySquad | None:
    candidates = tuple(
        Candidate(
            element_id=element_id,
            element_code=element_id,
            position=element_types[element_id],
            team_id=team_ids[element_id],
            price_tenths=prices[element_id],
        )
        for element_id in sorted(owned_counts)
        if element_id in element_types and element_id in team_ids and element_id in prices
    )
    rules = SquadRules(
        budget_tenths=1000,
        club_limit=3,
        position_counts={1: 2, 2: 5, 3: 5, 4: 3},
    )
    settings = OpeningSettings(rules=rules, playable_start_rate=0.0)
    owned_share = {element_id: count / total for element_id, count in owned_counts.items()}
    started_share = {
        element_id: started_counts.get(element_id, 0) / total for element_id in owned_counts
    }
    plans: list[SquadPlan] = []
    keeper_pairs = [{pair.starter_element_id, pair.bench_element_id} for pair in pairings] or [
        set()
    ]
    for keeper_pair in keeper_pairs:
        pool = [
            player
            for player in candidates
            if player.position != 1 or not keeper_pair or player.element_id in keeper_pair
        ]
        try:
            plans.append(
                choose_opening_squad(
                    pool,
                    started_share,
                    owned_share,
                    settings,
                    appear=started_share,
                )
            )
            break
        except ValueError:
            continue
    if not plans:
        return None
    plan = plans[0]
    assert plan is not None
    starters = tuple(player.element_id for player in plan.starters)
    squad = tuple(player.element_id for player in plan.squad)
    formation = tuple(
        sum(1 for player in plan.starters if player.position == position) for position in (2, 3, 4)
    )
    return PopularitySquad(
        squad=squad,
        starters=starters,
        bench=tuple(player.element_id for player in plan.bench),
        formation=(formation[0], formation[1], formation[2]),
        spent_tenths=plan.spent_tenths,
        xi_spent_tenths=sum(player.price_tenths for player in plan.starters),
        mean_ownership=sum(owned_share[element_id] for element_id in squad) / len(squad),
        mean_started_share=sum(started_share[element_id] for element_id in starters)
        / len(starters),
    )


def _percentile(values: Sequence[int], share: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("a distribution requires observations")
    position = (len(ordered) - 1) * share
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _summary(values: Sequence[int]) -> DistributionSummary:
    if not values:
        raise ValueError("a distribution requires observations")
    return DistributionSummary(
        mean=sum(values) / len(values),
        median=float(median(values)),
        p10=_percentile(values, 0.1),
        p90=_percentile(values, 0.9),
        minimum=min(values),
        maximum=max(values),
    )


def aggregate_manager_history(
    captured: Sequence[ManagerPicks],
    *,
    event: int,
    attempted: int,
    cohort_revision: str,
    minimum_coverage: float = MINIMUM_COVERAGE,
) -> PortfolioAggregate:
    """Aggregate entry history without retaining any manager identity."""
    if attempted <= 0:
        raise ValueError("a portfolio aggregate needs a cohort")
    rows = [row for row in captured if row.history is not None]
    wrong_event = [row.entry_id for row in rows if row.event != event]
    if wrong_event:
        raise ValueError(f"history from another gameweek for entries {wrong_event}")
    if len({row.entry_id for row in rows}) != len(rows):
        raise ValueError("aggregate history contains duplicate managers")
    if len(rows) > attempted:
        raise ValueError("more manager histories answered than were asked")
    coverage = len(rows) / attempted
    if coverage < minimum_coverage:
        raise CoverageTooLow(
            f"only {len(rows)} of {attempted} manager histories answered "
            f"({coverage:.1%}); below the {minimum_coverage:.0%} floor"
        )
    histories = [row.history for row in rows if row.history is not None]
    chips: dict[str, int] = {}
    for row in rows:
        key = row.active_chip or "none"
        chips[key] = chips.get(key, 0) + 1
    standing = tuple(
        sorted(
            (
                SeasonStanding(overall_rank=history.overall_rank, total_points=history.total_points)
                for history in histories
                if history.total_points is not None
            ),
            key=lambda row: (-row.total_points, row.overall_rank or 0),
        )
    )
    return PortfolioAggregate(
        event=event,
        cohort_revision=cohort_revision,
        attempted=attempted,
        responded=len(histories),
        chips={key: chips[key] for key in sorted(chips)},
        total_points=_summary([row.points for row in histories]),
        bench_points=_summary([row.points_on_bench for row in histories]),
        squad_value_tenths=_summary([row.value_tenths for row in histories]),
        bank_tenths=_summary([row.bank_tenths for row in histories]),
        event_transfers=_summary([row.event_transfers for row in histories]),
        transfer_cost=_summary([row.event_transfers_cost for row in histories]),
        transfers_available=event > 1,
        season_standing=standing,
    )
