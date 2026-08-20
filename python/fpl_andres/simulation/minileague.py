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
from dataclasses import replace

from fpl_andres.backtesting.corpus import SeasonCorpus
from fpl_andres.backtesting.fixtures import estimate_strength
from fpl_andres.backtesting.projector import ProjectionSettings, project_gameweek
from fpl_andres.simulation.baselines import crowd_ranking
from fpl_andres.simulation.chips import ChipName, ChipState, chip_rules_for, plan_chips
from fpl_andres.simulation.minileague_policies import (
    _take_transfers,
)
from fpl_andres.simulation.minileague_scoring import _play
from fpl_andres.simulation.minileague_state import (
    _DROPPED_THRESHOLD,
    _FORM_WINDOW,
    _PASSIVE,
    GameweekLedger,
    GameweekSquad,
    LeagueResult,
    LeagueSettings,
    ManagerResult,
    Policy,
    _Manager,
)
from fpl_andres.simulation.season import SquadGameweek
from fpl_andres.simulation.squad import (
    Candidate,
    SquadSelectionError,
    build_ranked_squad,
    build_squad,
)
from fpl_andres.simulation.valuation import Portfolio

__all__ = [
    "GameweekSquad",
    "LeagueResult",
    "LeagueSettings",
    "ManagerResult",
    "Policy",
    "simulate_league",
]


def simulate_league(
    corpus: SeasonCorpus,
    settings: LeagueSettings,
    *,
    projection_settings: ProjectionSettings | None = None,
    seed: int = 0,
    previous: SeasonCorpus | None = None,
) -> LeagueResult:
    """Play a whole league through the season.

    ``previous`` supplies last season's record. Without it the season cannot be
    opened before there is enough of itself to project from, which is why the
    default start is a seventh of the way in; with it the opening weeks are
    projected the way the live planner projects an August gameweek, and the
    total becomes comparable to a real manager's.
    """
    pool = _candidate_pool(corpus, settings.start_gameweek)
    if not pool:
        raise ValueError(f"{corpus.season} has no priced pool at GW{settings.start_gameweek}")

    outcome = LeagueResult(season=corpus.season, settings=settings)
    managers: list[_Manager] = []
    roster = settings.policy_roster()
    opening = _opening_squad(corpus, pool, settings, seed, previous=previous)
    last_event = max(corpus.gameweeks, default=settings.start_gameweek)
    # What this particular season allowed. From 2025-26 that is a full set of
    # four chips in each half rather than one set for the year.
    chip_rules = chip_rules_for(corpus.season)

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
                chip_plan=_chip_plan(
                    corpus, squad, settings, manager_seed, last_event, previous=previous
                ),
                chips=ChipState(rules=chip_rules),
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
            for projection in project_gameweek(
                corpus, gameweek, settings=projection_settings, previous=previous
            )
        }
        # The one player the model would have taken above everybody else this
        # week, whether or not anybody owned him. Kept so "how often was the
        # best player in the game on your field" can be asked afterwards.
        if projected:
            outcome.best_projected[gameweek] = max(
                projected, key=lambda element: (projected[element], -element)
            )
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
            manager.pending_transfers.clear()
            hits_before = manager.result.hit_points
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

            played = _play(manager, settings, outcomes, ranking, form, chip, pool)
            manager.result.weekly_points.append(played.points)
            manager.result.total_points += played.points
            manager.result.gameweek_squads.append(
                GameweekSquad(
                    event=gameweek,
                    squad=played.squad,
                    starters=played.starters,
                    captain=played.captain,
                )
            )
            manager.result.final_team_value_tenths = manager.portfolio.team_value(prices)
            if chip is not None:
                manager.result.chips_played.setdefault(chip, []).append(gameweek)
            week_hits = manager.result.hit_points - hits_before
            manager.result.ledger.append(
                GameweekLedger(
                    event=gameweek,
                    points=played.points,
                    running_total=manager.result.total_points - manager.result.hit_points,
                    chip=chip,
                    captain=played.captain,
                    captain_points=played.captain_points,
                    bench_points=played.bench_points,
                    hit_points=week_hits,
                    transfers=tuple(manager.pending_transfers),
                    squad=played.squad,
                    starters=played.starters,
                    team_value_tenths=manager.result.final_team_value_tenths,
                    bank_tenths=manager.portfolio.bank_tenths,
                )
            )

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
    *,
    previous: SeasonCorpus | None = None,
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
    if not strength and previous is not None:
        # Opening the season there are no results yet to estimate strength
        # from, and every week scores identically -- which dated the free hit in
        # gameweek one and rebuilt the squad in gameweek two. Last season's
        # table is what a manager actually has in August.
        strength = estimate_strength(previous.fixtures_before(previous.last_event + 1))
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
        rules=chip_rules_for(corpus.season),
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
    *,
    previous: SeasonCorpus | None = None,
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
        if previous is not None:
            # Opening week: there is no season yet to read ownership from, so
            # the fifteen is built the way the live planner builds it in August
            # -- off last season and the opening projection. The random legal
            # squad below would measure recovery from a bad team instead.
            ranking = {
                projection.element_id: projection.expected_points
                for projection in project_gameweek(corpus, gameweek, previous=previous)
            }
            if ranking:
                try:
                    return build_ranked_squad(pool, settings.squad_rules, ranking)
                except SquadSelectionError:
                    pass
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
    if settings.open_with:
        # Above everything else in the ranking, so the greedy pass reaches him
        # first. He is still subject to the budget floor and the club limit: a
        # player the squad cannot legally afford is simply not taken, and the
        # league is then the same as the one it is being compared against,
        # which is the honest outcome rather than a special case.
        ceiling = max(ranking.values(), default=0.0) + 1.0
        ranking = {**ranking, **{element: ceiling for element in settings.open_with}}
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
