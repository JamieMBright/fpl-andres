"""What a squad could actually reach.

Every number the backtest published until now was scored against the whole
game: rank correlation over the pool, captaincy from the crowd's twenty-five
most owned. Both are the right measurements of a *ranking*, and neither is a
measurement of a *season*, because a manager does not pick from the game. He
picks from fifteen players he bought weeks ago with money he no longer has.

Two questions follow, and both are decided rather than argued:

- **How often is the best player in the game on your field?** If the model's
  single highest projection each week is somebody the squad does not own, the
  projection is describing a game nobody is playing. The suspicion worth
  testing is that this happens constantly, because the best projection is
  usually the most expensive player and a fifteen cannot hold every one of
  them.
- **What does captaincy cost once it has to come from your own eleven?** The
  published captaincy table picks from the crowd's shortlist, which nobody
  owns in full. Scoring the same decision against the eleven the method
  actually fielded is the honest version, and the difference between the two
  is the size of the illusion.

Both are read off `LeagueResult`, which now keeps the squad it played each
gameweek with. Nothing here re-simulates or re-projects: it is arithmetic on a
season that has already been played, so it cannot leak.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from fpl_andres.backtesting.captain_policies import (
    CaptainCandidate,
    build_captain_policies,
    policy_names,
)
from fpl_andres.backtesting.captaincy import CaptaincyScore, score_policies
from fpl_andres.backtesting.corpus import SeasonCorpus
from fpl_andres.positions import PositionUnknown, is_captain_eligible
from fpl_andres.simulation.minileague_state import LeagueResult, ManagerResult, Policy

__all__ = [
    "Acquisition",
    "CaptaincyReach",
    "GiantReach",
    "captaincy_reach",
    "first_acquisition",
    "giant_reach",
    "owned_captain_policy_scores",
]


@dataclass(frozen=True)
class GiantReach:
    """How often the game's best projection was owned, and started.

    `owned` and `started` differ: a squad can hold a player and leave him on
    the bench, which is the same as not having him for the week. Both are
    reported because "we bought him" and "he played for us" are different
    claims and only the second one scores.
    """

    policy: str
    gameweeks: int
    owned: int
    started: int
    captained: int
    #: Element ids that were the game's best projection at least once, and how
    #: many gameweeks each of them held that place.
    weeks_at_the_top: Mapping[int, int]

    @property
    def owned_share(self) -> float:
        return self.owned / self.gameweeks if self.gameweeks else 0.0

    @property
    def started_share(self) -> float:
        return self.started / self.gameweeks if self.gameweeks else 0.0

    @property
    def captained_share(self) -> float:
        return self.captained / self.gameweeks if self.gameweeks else 0.0


def _cohort(result: LeagueResult, policy: Policy) -> Sequence[ManagerResult]:
    return [
        manager
        for manager in result.by_policy(policy)
        if manager.gameweek_squads  # A manager who never played answers nothing.
    ]


def giant_reach(result: LeagueResult, policy: Policy = "advised") -> GiantReach:
    """How often the highest projection in the game was on the field.

    Counted over every manager of the policy and every gameweek they played, so
    a single lucky opening squad cannot carry the answer.
    """
    best = result.best_projected
    gameweeks = 0
    owned = 0
    started = 0
    captained = 0
    weeks_at_the_top: dict[int, int] = {}

    for element in best.values():
        weeks_at_the_top[element] = weeks_at_the_top.get(element, 0) + 1

    for manager in _cohort(result, policy):
        for week in manager.gameweek_squads:
            giant = best.get(week.event)
            if giant is None:
                continue
            gameweeks += 1
            if giant in week.squad:
                owned += 1
            if giant in week.starters:
                started += 1
            if giant == week.captain:
                captained += 1

    return GiantReach(
        policy=policy,
        gameweeks=gameweeks,
        owned=owned,
        started=started,
        captained=captained,
        weeks_at_the_top=weeks_at_the_top,
    )


@dataclass(frozen=True)
class Acquisition:
    """When a policy first got hold of a named player, if it ever did.

    A premium is one transfer that costs most of the bank, so the interesting
    number is not whether he was eventually owned but how many gameweeks were
    played without him. Those weeks are the price of not starting with him.
    """

    element_id: int
    managers: int
    #: Managers who finished the season never having owned him.
    never: int
    #: Mean gameweeks played before he was first owned, over those who got him.
    mean_wait: float
    #: Gameweeks he was owned for, summed over the cohort.
    owned_gameweeks: int


def first_acquisition(
    result: LeagueResult,
    element_id: int,
    policy: Policy = "advised",
) -> Acquisition:
    """How long each manager of a policy played before owning a given player."""
    cohort = _cohort(result, policy)
    waits: list[int] = []
    never = 0
    owned_gameweeks = 0

    for manager in cohort:
        held = [
            index for index, week in enumerate(manager.gameweek_squads) if element_id in week.squad
        ]
        owned_gameweeks += len(held)
        if held:
            waits.append(held[0])
        else:
            never += 1

    return Acquisition(
        element_id=element_id,
        managers=len(cohort),
        never=never,
        mean_wait=sum(waits) / len(waits) if waits else 0.0,
        owned_gameweeks=owned_gameweeks,
    )


@dataclass(frozen=True)
class CaptaincyReach:
    """Captaincy scored twice: from the owned eleven, and from the whole game.

    `chosen` is what the armband actually returned. `owned_ceiling` is the best
    it could have returned from the same eleven -- a decision the manager could
    have made. Both ceilings consider only midfielders and forwards, matching
    the advisory rule. `game_ceiling` is the best legal captain in the entire
    game, which nobody can reach and which is only here to size the gap the
    published table quietly counts as reachable.

    Points are the player's own realised score, not the doubled figure, for the
    same reason the captaincy table does it: doubling is a constant on every
    line and changes no ordering.
    """

    policy: str
    gameweeks: int
    chosen_points: float
    owned_ceiling_points: float
    game_ceiling_points: float

    @property
    def mean_chosen(self) -> float:
        return self.chosen_points / self.gameweeks if self.gameweeks else 0.0

    @property
    def mean_owned_ceiling(self) -> float:
        return self.owned_ceiling_points / self.gameweeks if self.gameweeks else 0.0

    @property
    def mean_game_ceiling(self) -> float:
        return self.game_ceiling_points / self.gameweeks if self.gameweeks else 0.0

    @property
    def owned_regret(self) -> float:
        """What better captaincy from the same eleven was worth, per gameweek."""
        return self.mean_owned_ceiling - self.mean_chosen

    @property
    def reach_gap(self) -> float:
        """What owning a different squad was worth, per gameweek.

        The distance between the best eligible captain in the game and the best
        eligible captain available from the eleven that was fielded. It is not
        a decision anybody could have taken on the day, which is exactly the
        point: a captaincy table scored against the whole game is quoting this
        as if it were.
        """
        return self.mean_game_ceiling - self.mean_owned_ceiling


def _historical_captain_eligible(position: int) -> bool:
    try:
        return is_captain_eligible(position)
    except PositionUnknown:
        return False


def captaincy_reach(
    corpus: SeasonCorpus,
    result: LeagueResult,
    policy: Policy = "advised",
) -> CaptaincyReach:
    """Score the armband against the eleven that was on the field."""
    actual_by_event: dict[int, Mapping[int, int]] = {}
    gameweeks = 0
    chosen = 0.0
    owned_ceiling = 0.0
    game_ceiling = 0.0

    for manager in _cohort(result, policy):
        for week in manager.gameweek_squads:
            if week.event not in actual_by_event:
                actual_by_event[week.event] = corpus.actual_points(week.event)
            actual = actual_by_event[week.event]
            if not actual:
                continue
            gameweeks += 1
            chosen += float(actual.get(week.captain, 0)) if week.captain is not None else 0.0
            eligible_starters = [
                element
                for element in week.starters
                if is_captain_eligible(corpus.position_by_element[element])
            ]
            if len(eligible_starters) < 2:
                raise ValueError("simulated lineup has fewer than two captain-eligible starters")
            owned_ceiling += float(max(actual.get(element, 0) for element in eligible_starters))
            game_ceiling += float(
                max(
                    points
                    for element, points in actual.items()
                    if _historical_captain_eligible(corpus.position_by_element[element])
                )
            )

    return CaptaincyReach(
        policy=policy,
        gameweeks=gameweeks,
        chosen_points=chosen,
        owned_ceiling_points=owned_ceiling,
        game_ceiling_points=game_ceiling,
    )


def owned_captain_policy_scores(
    corpus: SeasonCorpus,
    results: Sequence[LeagueResult],
    candidates_by_event: Mapping[int, Sequence[CaptainCandidate]],
    policy: Policy = "advised",
) -> dict[str, CaptaincyScore]:
    """Replay every captain rule against the eleven the model fielded.

    Each simulated manager gets a fresh policy set because ``set_and_forget``
    carries its own anchor. Scores aggregate across managers and seeds, but the
    candidate population never does: one manager-week is one legal XI.

    A missing candidate skips that manager-week. Quietly scoring the remaining
    ten would turn missing pre-deadline evidence into a different, easier
    choice set and overstate the rule's reach.
    """
    scores = {label: CaptaincyScore(label=label) for label in policy_names()}
    actual_by_event: dict[int, Mapping[int, int]] = {}

    for result in results:
        for manager in _cohort(result, policy):
            active = build_captain_policies()
            for week in manager.gameweek_squads:
                actual = actual_by_event.setdefault(
                    week.event,
                    corpus.actual_points(week.event),
                )
                if not actual:
                    continue
                candidates = candidates_by_event.get(week.event, ())
                by_element = {entry.element_id: entry for entry in candidates}
                eligible_starters = [
                    element
                    for element in week.starters
                    if is_captain_eligible(corpus.position_by_element[element])
                ]
                if len(eligible_starters) < 2:
                    raise ValueError(
                        "simulated lineup has fewer than two captain-eligible starters"
                    )
                if any(element not in by_element for element in eligible_starters):
                    continue
                eleven = [by_element[element] for element in eligible_starters]
                score_policies(
                    eleven,
                    actual,
                    scores,
                    gameweek=week.event,
                    policies=active,
                )

    return scores
