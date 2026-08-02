"""Mini-league simulation.

Plays a league of managers through a completed season from different random
opening squads, so the spread of outcomes is visible rather than a single lucky
or unlucky run.

Two policies:

- **advised** follows the projection: transfers toward the highest projected
  points, captains the highest projection.
- **zombie** is the realistic majority. It leaves the squad alone unless a
  player stops featuring, then replaces them with the best recent form
  available, and captains whoever has scored most lately.

Every decision uses information from before the gameweek being played. The
corpus slice enforces that structurally.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

from fpl_andres.backtesting.corpus import SeasonCorpus
from fpl_andres.backtesting.fixtures import estimate_strength
from fpl_andres.backtesting.projector import ProjectionSettings, project_gameweek
from fpl_andres.simulation.baselines import crowd_ranking
from fpl_andres.simulation.chips import (
    ChipName,
    ChipState,
    plan_chips,
)
from fpl_andres.simulation.season import LineupRules, SquadGameweek
from fpl_andres.simulation.squad import (
    Candidate,
    SquadRules,
    SquadSelectionError,
    build_ranked_squad,
    build_squad,
    transfer_respects_club_limit,
)
from fpl_andres.simulation.valuation import Portfolio

__all__ = [
    "LeagueResult",
    "LeagueSettings",
    "ManagerResult",
    "Policy",
    "simulate_league",
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
        # Audit item #181. Annotated, so the literals are checked against
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


def simulate_league(
    corpus: SeasonCorpus,
    settings: LeagueSettings,
    *,
    projection_settings: ProjectionSettings | None = None,
    seed: int = 0,
) -> LeagueResult:
    """Play a whole league through the season."""
    pool = _candidate_pool(corpus, settings.start_gameweek)
    if not pool:
        raise ValueError(f"{corpus.season} has no priced pool at GW{settings.start_gameweek}")

    outcome = LeagueResult(season=corpus.season, settings=settings)
    managers: list[_Manager] = []
    roster = settings.policy_roster()
    opening = _opening_squad(corpus, pool, settings, seed)
    last_event = max(corpus.gameweeks, default=settings.start_gameweek)

    for index in range(settings.managers):
        policy = roster[index]
        manager_seed = seed * 1000 + index
        squad = list(opening)
        result = ManagerResult(manager_id=index, policy=policy, seed=manager_seed)
        outcome.managers.append(result)
        managers.append(
            # Zero free transfers here, not one: the week's transfer is granted
            # at the top of _take_transfers, so seeding one as well would hand
            # every manager an extra move over the season.
            _Manager(
                result=result,
                squad=squad,
                free_transfers=0,
                portfolio=Portfolio.opening(
                    [player.element_id for player in squad],
                    {player.element_id: player.price_tenths for player in pool},
                    settings.squad_rules.budget_tenths,
                ),
                chip_plan=_chip_plan(corpus, squad, settings, manager_seed, last_event),
            )
        )

    sorted_pool: dict[str, Mapping[int, Sequence[Candidate]]] = {}

    for gameweek in corpus.gameweeks:
        if gameweek < settings.start_gameweek:
            continue
        actual = corpus.actual_points(gameweek)
        if not actual:
            continue

        projected = {
            projection.element_id: projection.expected_points
            for projection in project_gameweek(corpus, gameweek, settings=projection_settings)
        }
        form = _recent_form(corpus, gameweek)
        minutes = _recent_minutes(corpus, gameweek)
        outcomes = _outcomes(corpus, gameweek)
        crowd = crowd_ranking(corpus, gameweek)
        prices = _prices_at(corpus, gameweek)

        rankings: dict[str, Mapping[int, float]] = {
            "advised": projected,
            "zombie": form,
            # Holds never transfer, but still need a basis for captaincy.
            "hold": form,
            "form_chaser": form,
            "crowd": crowd,
        }
        sorted_pool = {name: _sorted_by(pool, ranking) for name, ranking in rankings.items()}

        ownership = _league_ownership(managers)
        for manager in managers:
            policy = manager.result.policy
            ranking = rankings.get(policy, projected)
            if policy == "rank_aware":
                ranking = _tilted_ranking(manager, managers, projected, ownership, settings)
                by_position: Mapping[int, Sequence[Candidate]] = _sorted_by(pool, ranking)
            else:
                by_position = sorted_pool[manager.result.policy]

            chip = _choose_chip(
                manager,
                settings=settings,
                pool=pool,
                gameweek=gameweek,
                ranking=ranking,
                last_event=last_event,
            )
            if chip == "wildcard":
                # A free rebuild, but only of what the manager can actually
                # fund: today's prices, against today's team value.
                budget = manager.portfolio.team_value(prices)
                repriced = [
                    replace(player, price_tenths=prices.get(player.element_id, player.price_tenths))
                    for player in pool
                ]
                try:
                    rebuilt = build_ranked_squad(
                        repriced,
                        replace(settings.squad_rules, budget_tenths=budget),
                        ranking,
                    )
                except SquadSelectionError:
                    # Nothing legal is affordable, so the chip is simply not
                    # played and the squad and its money are left untouched.
                    rebuilt = None
                if rebuilt is not None:
                    manager.squad = list(rebuilt)
                    # Priced from the same list the squad was built against, so
                    # the portfolio can never disagree with the selection.
                    manager.portfolio = Portfolio.opening(
                        [player.element_id for player in rebuilt],
                        {player.element_id: player.price_tenths for player in rebuilt},
                        budget,
                    )
                    manager.chips.record("wildcard", gameweek)
                else:
                    chip = None
            else:
                _take_transfers(
                    manager,
                    settings=settings,
                    by_position=by_position,
                    projected=ranking,
                    form=form,
                    minutes=minutes,
                    prices=prices,
                )
                if chip is not None:
                    manager.chips.record(chip, gameweek)

            points = _play(manager, settings, outcomes, ranking, form, chip, pool)
            manager.result.weekly_points.append(points)
            manager.result.total_points += points
            manager.result.final_team_value_tenths = manager.portfolio.team_value(prices)
            if chip is not None:
                manager.result.chips_played[chip] = gameweek

    seen: set[str] = set()
    for manager in managers:
        if manager.result.policy in seen:
            continue
        seen.add(manager.result.policy)
        outcome.squad_snapshots.append(
            (
                manager.result.policy,
                [(player.element_id, player.price_tenths) for player in manager.squad],
            )
        )

    return outcome


def _chip_plan(
    corpus: SeasonCorpus,
    squad: Sequence[Candidate],
    settings: LeagueSettings,
    seed: int,
    last_event: int,
) -> dict[int, ChipName]:
    """Date the season's chips from the fixture list.

    The triple captain follows the squad's most expensive player, on the
    reasoning that price tracks expected returns closely enough to pick a
    captain by. It wants him at home against a leaky defence, which is a fixture
    rather than a hunch.
    """
    if not settings.chips_enabled:
        return {}

    start = settings.start_gameweek
    fixtures_by_event = {
        event: len(fixtures) for event, fixtures in corpus.fixtures_by_event.items()
    }
    strength = estimate_strength(corpus.fixtures_before(start))
    star = max(squad, key=lambda player: player.price_tenths, default=None)

    star_value: dict[int, float] = {}
    if star is not None:
        for event in range(start, last_event + 1):
            total = 0.0
            for fixture in corpus.fixtures_for(star.team_id, event):
                opponent = fixture.opponent_of(star.team_id)
                if opponent is None or opponent not in strength:
                    continue
                home = fixture.is_home(star.team_id)
                if not home:
                    # Away captaincy is a worse bet at the same opponent, so an
                    # away fixture never wins the chip on its own.
                    continue
                total += strength[opponent].defence(home=False)
            star_value[event] = total

    # The bench boost pays all fifteen, so it is decided by the weakest of them.
    # A player with no fixture that week scores nothing and sinks the floor,
    # which is exactly the outcome the chip needs to avoid.
    floor_value: dict[int, float] = {}
    for event in range(start, last_event + 1):
        weakest = None
        for player in squad:
            total = 0.0
            for fixture in corpus.fixtures_for(player.team_id, event):
                opponent = fixture.opponent_of(player.team_id)
                if opponent is None or opponent not in strength:
                    continue
                total += strength[opponent].defence(home=fixture.is_home(player.team_id))
            weakest = total if weakest is None else min(weakest, total)
        floor_value[event] = weakest or 0.0

    return plan_chips(
        fixtures_by_event=fixtures_by_event,
        star_fixture_value=star_value,
        from_gameweek=start,
        last_event=last_event,
        rng=random.Random(seed),
        squad_floor_value=floor_value,
    )


def _choose_chip(
    manager: _Manager,
    *,
    settings: LeagueSettings,
    pool: Sequence[Candidate],
    gameweek: int,
    ranking: Mapping[int, float],
    last_event: int,
) -> ChipName | None:
    """Whatever the season plan dated for this week, if it is still available."""
    if not settings.chips_enabled or manager.result.policy in _PASSIVE:
        return None
    chip = manager.chip_plan.get(gameweek)
    if chip is None or not manager.chips.available(chip, gameweek):
        return None
    return chip


def _opening_squad(
    corpus: SeasonCorpus,
    pool: Sequence[Candidate],
    settings: LeagueSettings,
    seed: int,
) -> tuple[Candidate, ...]:
    """The team every policy starts from.

    All policies share it, so any difference in outcome is the policy rather
    than the luck of the draw. The seed picks between credible openings instead
    of drawing at random: a random legal squad is mostly players who never
    appear, and starting there measures recovery from a bad team.
    """
    gameweek = settings.start_gameweek
    owned = {
        row.element_id: float(row.selected)
        for event in range(1, gameweek)
        for row in corpus.rows_by_gameweek.get(event, ())
        if row.selected is not None
    }
    if not owned:
        return build_squad(pool, settings.squad_rules, rng=random.Random(seed))

    variants = [owned]
    prices = {candidate.element_id: candidate.price_tenths for candidate in pool}
    # Ownership per pound, which is how a budget-conscious template is built.
    variants.append(
        {
            element_id: value / max(1, prices.get(element_id, 1))
            for element_id, value in owned.items()
        }
    )
    variants.append(_recent_form(corpus, gameweek))

    ranking = variants[seed % len(variants)]
    try:
        return build_ranked_squad(pool, settings.squad_rules, ranking)
    except SquadSelectionError:
        return build_squad(pool, settings.squad_rules, rng=random.Random(seed))


def _sorted_by(
    pool: Sequence[Candidate], ranking: Mapping[int, float]
) -> dict[int, list[Candidate]]:
    ordered: dict[int, list[Candidate]] = {}
    for candidate in pool:
        ordered.setdefault(candidate.position, []).append(candidate)
    for entries in ordered.values():
        entries.sort(key=lambda entry: ranking.get(entry.element_id, 0.0), reverse=True)
    return ordered


def _league_ownership(managers: Sequence[_Manager]) -> dict[int, float]:
    """Share of the league holding each player, right now."""
    if not managers:
        return {}
    counts: dict[int, int] = {}
    for manager in managers:
        for player in manager.squad:
            counts[player.element_id] = counts.get(player.element_id, 0) + 1
    return {element_id: count / len(managers) for element_id, count in counts.items()}


def _tilted_ranking(
    manager: _Manager,
    managers: Sequence[_Manager],
    projected: Mapping[int, float],
    ownership: Mapping[int, float],
    settings: LeagueSettings,
) -> dict[int, float]:
    """Bend the projection toward, or away from, what the league already owns.

    A manager who is ahead wants the field's players, because matching them
    protects the lead. A manager who is behind needs players the field does not
    have, because matching the field preserves the gap. Neither changes expected
    points; both change the spread of finishing positions, which is the thing
    actually being competed for.
    """
    standings = sorted(managers, key=lambda entry: -entry.result.net_points)
    if len(standings) < 2:
        return dict(projected)
    place = standings.index(manager)
    # -1 when leading, +1 when last.
    tilt = (place / (len(standings) - 1)) * 2 - 1

    return {
        element_id: points
        * (1 + settings.risk_weight * tilt * (0.5 - ownership.get(element_id, 0.0)))
        for element_id, points in projected.items()
    }


def _prices_at(corpus: SeasonCorpus, gameweek: int) -> dict[int, int]:
    """Every player's quoted price as of the most recent gameweek before this one."""
    prices: dict[int, int] = {}
    for event in sorted(corpus.rows_by_gameweek):
        if event >= gameweek:
            break
        for row in corpus.rows_by_gameweek[event]:
            if row.price_tenths:
                prices[row.element_id] = row.price_tenths
    return prices


def _candidate_pool(corpus: SeasonCorpus, gameweek: int) -> list[Candidate]:
    """Prices as they stood at the opening gameweek of the simulation."""
    prices: dict[int, int] = {}
    for event in sorted(corpus.rows_by_gameweek):
        if event > gameweek:
            break
        for row in corpus.rows_by_gameweek[event]:
            if row.price_tenths:
                prices[row.element_id] = row.price_tenths

    pool: list[Candidate] = []
    for element_id, price in prices.items():
        position = corpus.position_by_element.get(element_id)
        team = corpus.team_by_element.get(element_id)
        if position is None or team is None or position not in (1, 2, 3, 4):
            continue
        pool.append(
            Candidate(
                element_id=element_id,
                element_code=element_id,
                position=position,
                team_id=team,
                price_tenths=price,
                web_name=corpus.name_by_element.get(element_id, ""),
            )
        )
    return pool


def _outcomes(corpus: SeasonCorpus, gameweek: int) -> dict[int, SquadGameweek]:
    combined: dict[int, SquadGameweek] = {}
    for row in corpus.rows_by_gameweek.get(gameweek, ()):
        existing = combined.get(row.element_id)
        if existing is None:
            combined[row.element_id] = SquadGameweek(row.element_id, row.minutes, row.total_points)
        else:
            combined[row.element_id] = SquadGameweek(
                row.element_id,
                min(existing.minutes + row.minutes, 120),
                existing.points + row.total_points,
            )
    return combined


def _recent_form(corpus: SeasonCorpus, gameweek: int) -> dict[int, float]:
    totals: dict[int, list[int]] = {}
    for event in range(max(1, gameweek - _FORM_WINDOW), gameweek):
        for element_id, points in corpus.actual_points(event).items():
            totals.setdefault(element_id, []).append(points)
    return {
        element_id: sum(points) / len(points) for element_id, points in totals.items() if points
    }


def _recent_minutes(corpus: SeasonCorpus, gameweek: int) -> dict[int, int]:
    totals: dict[int, int] = {}
    for event in range(max(1, gameweek - _DROPPED_THRESHOLD), gameweek):
        for row in corpus.rows_by_gameweek.get(event, ()):
            totals[row.element_id] = totals.get(row.element_id, 0) + row.minutes
    return totals


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
    outgoing = [player for player in manager.squad if minutes.get(player.element_id, 0) == 0]
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
    current = ranking.get(outgoing.element_id, 0.0)

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


def _play(
    manager: _Manager,
    settings: LeagueSettings,
    outcomes: Mapping[int, SquadGameweek],
    projected: Mapping[int, float],
    form: Mapping[int, float],
    chip: ChipName | None = None,
    pool: Sequence[Candidate] = (),
) -> int:
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
    return points


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
