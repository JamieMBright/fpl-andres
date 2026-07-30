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
from dataclasses import dataclass, field
from typing import Literal

from fpl_andres.backtesting.corpus import SeasonCorpus
from fpl_andres.backtesting.projector import ProjectionSettings, project_gameweek
from fpl_andres.simulation.season import LineupRules, SquadGameweek
from fpl_andres.simulation.squad import Candidate, SquadRules, build_squad

__all__ = [
    "LeagueResult",
    "LeagueSettings",
    "ManagerResult",
    "Policy",
    "simulate_league",
]

Policy = Literal["advised", "zombie"]

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
    free_transfers_per_event: int = 1
    max_free_transfers: int = 5
    start_gameweek: int = 7

    def advised_count(self) -> int:
        return max(1, round(self.managers * self.advised_share))


@dataclass
class ManagerResult:
    manager_id: int
    policy: Policy
    seed: int
    total_points: int = 0
    transfers_made: int = 0
    hit_points: int = 0
    weekly_points: list[int] = field(default_factory=list)

    @property
    def net_points(self) -> int:
        return self.total_points - self.hit_points


@dataclass
class LeagueResult:
    season: str
    settings: LeagueSettings
    managers: list[ManagerResult] = field(default_factory=list)

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
    advised = settings.advised_count()
    managers: list[_Manager] = []

    for index in range(settings.managers):
        policy: Policy = "advised" if index < advised else "zombie"
        manager_seed = seed * 1000 + index
        squad = list(build_squad(pool, settings.squad_rules, rng=random.Random(manager_seed)))
        result = ManagerResult(manager_id=index, policy=policy, seed=manager_seed)
        outcome.managers.append(result)
        managers.append(
            _Manager(result=result, squad=squad, free_transfers=settings.free_transfers_per_event)
        )

    by_element = {candidate.element_id: candidate for candidate in pool}

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

        for manager in managers:
            _take_transfers(
                manager,
                settings=settings,
                by_element=by_element,
                projected=projected,
                form=form,
                minutes=minutes,
            )
            points = _play(manager, settings, outcomes, projected, form)
            manager.result.weekly_points.append(points)
            manager.result.total_points += points

    return outcome


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
    by_element: Mapping[int, Candidate],
    projected: Mapping[int, float],
    form: Mapping[int, float],
    minutes: Mapping[int, int],
) -> None:
    ranking = projected if manager.result.policy == "advised" else form
    if not ranking:
        return

    if manager.result.policy == "zombie":
        # Only acts when a player has stopped featuring.
        outgoing = [player for player in manager.squad if minutes.get(player.element_id, 0) == 0]
        if not outgoing:
            manager.free_transfers = min(
                manager.free_transfers + settings.free_transfers_per_event,
                settings.max_free_transfers,
            )
            return
        worst = min(outgoing, key=lambda player: form.get(player.element_id, 0.0))
    else:
        worst = min(manager.squad, key=lambda player: ranking.get(player.element_id, 0.0))

    held = {player.element_id for player in manager.squad}
    clubs: dict[int, int] = {}
    for player in manager.squad:
        clubs[player.team_id] = clubs.get(player.team_id, 0) + 1

    budget = _squad_value(manager.squad, settings) - _squad_cost(manager.squad) + worst.price_tenths
    replacement = _best_replacement(
        worst, by_element, ranking, held, clubs, budget, settings.squad_rules.club_limit
    )
    if replacement is None:
        manager.free_transfers = min(
            manager.free_transfers + settings.free_transfers_per_event,
            settings.max_free_transfers,
        )
        return

    manager.squad[manager.squad.index(worst)] = replacement
    manager.result.transfers_made += 1
    if manager.free_transfers > 0:
        manager.free_transfers -= 1
    else:
        manager.result.hit_points += _TRANSFER_HIT_POINTS
    manager.free_transfers = min(
        manager.free_transfers + settings.free_transfers_per_event,
        settings.max_free_transfers,
    )


def _best_replacement(
    outgoing: Candidate,
    by_element: Mapping[int, Candidate],
    ranking: Mapping[int, float],
    held: set[int],
    clubs: Mapping[int, int],
    budget: int,
    club_limit: int,
) -> Candidate | None:
    best: Candidate | None = None
    best_score = ranking.get(outgoing.element_id, 0.0)

    for candidate in by_element.values():
        if candidate.position != outgoing.position or candidate.element_id in held:
            continue
        if candidate.price_tenths > budget:
            continue
        if candidate.team_id != outgoing.team_id and clubs.get(candidate.team_id, 0) >= club_limit:
            continue
        score = ranking.get(candidate.element_id)
        if score is None or score <= best_score:
            continue
        best = candidate
        best_score = score
    return best


def _squad_cost(squad: Sequence[Candidate]) -> int:
    return sum(player.price_tenths for player in squad)


def _squad_value(squad: Sequence[Candidate], settings: LeagueSettings) -> int:
    # Selling-price accounting is not modelled; the squad is valued at its
    # opening budget, which keeps every manager on equal terms.
    return settings.squad_rules.budget_tenths


def _play(
    manager: _Manager,
    settings: LeagueSettings,
    outcomes: Mapping[int, SquadGameweek],
    projected: Mapping[int, float],
    form: Mapping[int, float],
) -> int:
    available = {
        player.element_id: outcomes.get(player.element_id, SquadGameweek(player.element_id, 0, 0))
        for player in manager.squad
    }
    ranking = projected if manager.result.policy == "advised" else form

    starters = _starting_eleven(manager.squad, ranking, settings.lineup_rules)
    starters = _autosub(manager.squad, starters, available, settings.lineup_rules)

    captain = max(starters, key=lambda pid: ranking.get(pid, 0.0), default=None)
    points = sum(available[pid].points for pid in starters)
    if captain is not None:
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
