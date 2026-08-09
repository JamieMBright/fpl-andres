"""League priors, shrinkage, and the per-player rates a projection is built on.

`projector.py` was 882 lines covering three separate jobs:
working out what a player does per ninety minutes, turning that into points, and
orchestrating both across a season. This is the first.

Nothing here knows what a goal is worth. That is deliberate -- these are rates,
and the scoring table that prices them changes between seasons while the rates
do not.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from fpl_andres.backtesting.corpus import ElementRow
from fpl_andres.cliargs import MAX_EVENT
from fpl_andres.models.minutes import (
    AppearanceObservation,
    AvailabilityEvidence,
    MinutesEvidence,
    MinutesProjection,
    project_minutes,
)
from fpl_andres.models.player_rates import (
    PlayerRateEvidence,
    PlayerRateProjection,
    RateObservation,
    RatePrior,
    project_player_rates,
)

if TYPE_CHECKING:
    from fpl_andres.backtesting.projector import ProjectionSettings

_SOURCE_HASH = "sha256:" + "0" * 64
# Saves and goals conceded are counted per point in the published table; the
# rates below are shrunk on the same denominators so a per-90 rate and the
# points it earns cannot drift apart.
_SAVES_PER_POINT = 3
_CONCEDED_PER_POINT = 2

_MINUTES_PER_90 = 90.0

# Position priors, expressed per 90. Sourced from league-wide long-run rates
# rather than tuned, so the backtest cannot flatter itself by fitting them.
_GOAL_PRIOR: Mapping[int, float] = {1: 0.00, 2: 0.05, 3: 0.12, 4: 0.28}
_ASSIST_PRIOR: Mapping[int, float] = {1: 0.00, 2: 0.06, 3: 0.13, 4: 0.12}
# Defensive contribution, new for 2025/26. Threshold is on the raw action count.
_DEFCON_THRESHOLD: Mapping[int, int] = {2: 10, 3: 12, 4: 12}
_DEFENDER = 2


def defensive_actions(row: ElementRow, position: int) -> int | None:
    """The count that faces the bar, counted for the position being projected.

    FPL publishes `defensive_contribution` for the position a player held at the
    time, and it reclassifies players between seasons and within them. A
    wing-back moved to midfield carries a clearances-blocks-interceptions-and-
    tackles record into a bar that also counts recoveries and sits two actions
    higher: every recovery he has ever made is missing from the count his new
    threshold is applied to, so he reads as a worse defensive midfielder than
    the one FPL just decided he is. Re-deriving from the components counts him
    as a midfielder for as long as he is one.

    Falls back to the published label when a component is absent, which is every
    season before 2025/26. Returns None for a keeper, who has no bar to clear,
    and when nothing was published at all.
    """
    if position not in _DEFCON_THRESHOLD:
        return None
    if row.clearances_blocks_interceptions is None or row.tackles is None:
        return row.defensive_contribution
    counted = row.clearances_blocks_interceptions + row.tackles
    if position == _DEFENDER:
        return counted
    if row.recoveries is None:
        return row.defensive_contribution
    return counted + row.recoveries


@dataclass(frozen=True)
class LeagueRates:
    """Per-position, per-90 route rates measured across every player to date.

    Used as the shrinkage target for thin individual histories. Measured rather
    than chosen, so a rarely-seen route cannot be given a flattering prior, and
    computed only from gameweeks earlier than the one being projected.
    """

    conceded_deductions: Mapping[int, float]
    save_points: Mapping[int, float]
    yellow_cards: Mapping[int, float]
    red_cards: Mapping[int, float]
    own_goals: Mapping[int, float]
    penalties_saved: Mapping[int, float]
    penalties_missed: Mapping[int, float]
    defcon_hits: Mapping[int, float]
    #: Per appearance rather than per ninety: a clean sheet is a property of the
    #: match, and a substitute who played twenty minutes of one shares it.
    clean_sheets: Mapping[int, float]
    #: Per appearance, for the same reason -- bonus is awarded once per match.
    bonus: Mapping[int, float]


def league_rates(rows: Sequence[ElementRow], position_by_element: Mapping[int, int]) -> LeagueRates:
    nineties: dict[int, float] = {}
    totals: dict[str, dict[int, float]] = {
        name: {}
        for name in (
            "conceded",
            "saves",
            "yellow",
            "red",
            "own_goal",
            "pen_saved",
            "pen_missed",
            "defcon",
            "clean_sheet",
            "bonus",
        )
    }
    defcon_nineties: dict[int, float] = {}
    appearances: dict[int, float] = {}

    for row in rows:
        if row.minutes <= 0:
            continue
        position = position_by_element.get(row.element_id)
        if position is None:
            continue
        played = row.minutes / _MINUTES_PER_90
        nineties[position] = nineties.get(position, 0.0) + played
        appearances[position] = appearances.get(position, 0.0) + 1
        totals["clean_sheet"][position] = (
            totals["clean_sheet"].get(position, 0.0) + row.clean_sheets
        )
        totals["bonus"][position] = totals["bonus"].get(position, 0.0) + row.bonus
        totals["conceded"][position] = totals["conceded"].get(position, 0.0) + (
            row.goals_conceded // _CONCEDED_PER_POINT
        )
        totals["saves"][position] = totals["saves"].get(position, 0.0) + (
            row.saves // _SAVES_PER_POINT
        )
        totals["yellow"][position] = totals["yellow"].get(position, 0.0) + row.yellow_cards
        totals["red"][position] = totals["red"].get(position, 0.0) + row.red_cards
        totals["own_goal"][position] = totals["own_goal"].get(position, 0.0) + row.own_goals
        totals["pen_saved"][position] = totals["pen_saved"].get(position, 0.0) + row.penalties_saved
        totals["pen_missed"][position] = (
            totals["pen_missed"].get(position, 0.0) + row.penalties_missed
        )
        threshold = _DEFCON_THRESHOLD.get(position)
        actions = defensive_actions(row, position)
        if threshold is not None and actions is not None:
            defcon_nineties[position] = defcon_nineties.get(position, 0.0) + played
            if actions >= threshold:
                totals["defcon"][position] = totals["defcon"].get(position, 0.0) + 1

    def per_ninety(name: str, denominator: Mapping[int, float]) -> dict[int, float]:
        return {
            position: totals[name].get(position, 0.0) / played
            for position, played in denominator.items()
            if played > 0
        }

    return LeagueRates(
        conceded_deductions=per_ninety("conceded", nineties),
        save_points=per_ninety("saves", nineties),
        yellow_cards=per_ninety("yellow", nineties),
        red_cards=per_ninety("red", nineties),
        own_goals=per_ninety("own_goal", nineties),
        penalties_saved=per_ninety("pen_saved", nineties),
        penalties_missed=per_ninety("pen_missed", nineties),
        defcon_hits=per_ninety("defcon", defcon_nineties),
        clean_sheets=per_ninety("clean_sheet", appearances),
        bonus=per_ninety("bonus", appearances),
    )


def shrunk_rate(
    events: float, nineties_played: float, prior: float, prior_nineties: float
) -> float:
    """Observed rate pulled toward the league rate in proportion to how thin it is."""
    return (events + prior * prior_nineties) / (nineties_played + prior_nineties)


def project_element_minutes(
    element_id: int,
    season: str,
    gameweek: int,
    rows: Sequence[ElementRow],
    cutoff: datetime,
    config: ProjectionSettings,
    prior_rows: Sequence[ElementRow] = (),
    availability: AvailabilityEvidence | None = None,
) -> MinutesProjection:
    # One appearance per gameweek: a double gameweek's fixtures are combined,
    # because the models reason about events, not matches.
    source = rows
    prediction_event = gameweek
    if not rows and prior_rows:
        # No football yet this season, so the read is "how did they finish last
        # season", projected one event past its end.
        source = prior_rows
        prediction_event = min(MAX_EVENT, max(row.gameweek for row in prior_rows) + 1)

    # One observation per match, not per gameweek. `MinutesEvidence` says so
    # itself -- "a double gameweek is two real appearances in one event" -- and
    # combining them here contradicted that: two 90-minute matches became one
    # observation clipped at 120, and `fixture_points` then spent that figure
    # once per fixture. A player whose history contained doubles was trained
    # somewhere between 90 and 120 and priced per match on it.
    observations = tuple(
        AppearanceObservation(
            event_id=row.gameweek,
            minutes=min(row.minutes, 120),
            started=(row.started or row.minutes >= 60) and row.minutes > 0,
            kickoff_time=row.kickoff_time,
            fixture_id=row.fixture_id,
        )
        for row in sorted(source, key=lambda entry: (entry.gameweek, entry.fixture_id))
        if row.gameweek < prediction_event and row.kickoff_time <= cutoff
    )

    evidence = MinutesEvidence(
        element_code=element_id,
        season=season,
        prediction_event=prediction_event,
        observations=observations,
        availability=availability,
        decay_half_life_events=config.decay_half_life_events,
        minimum_observations=config.minimum_observations,
        prior_start_rate=config.prior_start_rate,
        prior_strength_events=config.prior_strength_events,
        prediction_cutoff=cutoff,
        data_available_at=cutoff,
        source_hashes=(_SOURCE_HASH,),
    )
    return project_minutes(evidence)


def project_element_rates(
    element_id: int,
    season: str,
    gameweek: int,
    rows: Sequence[ElementRow],
    cutoff: datetime,
    config: ProjectionSettings,
    position: int,
    prior_rows: Sequence[ElementRow] = (),
    prior_season: str | None = None,
    team_id: int | None = None,
    prior_team_id: int | None = None,
    prior_position: int | None = None,
) -> PlayerRateProjection:
    observations = tuple(
        observation(row, season, cutoff, team_id=team_id, position_id=position)
        for row in rows
        if row.gameweek < gameweek and row.kickoff_time <= cutoff
    )
    carried = (
        tuple(
            observation(
                row,
                prior_season,
                cutoff,
                team_id=prior_team_id,
                position_id=prior_position,
            )
            for row in prior_rows
            if row.kickoff_time <= cutoff
        )
        if prior_season and prior_season != season
        else ()
    )

    evidence = PlayerRateEvidence(
        element_code=element_id,
        season=season,
        prediction_event=gameweek,
        current_season_observations=observations,
        prior_season_observations=carried,
        prior=RatePrior(
            goals_per_90=_GOAL_PRIOR[position],
            assists_per_90=_ASSIST_PRIOR[position],
            strength_minutes=config.prior_strength_minutes,
        ),
        minimum_minutes=config.minimum_minutes,
        blend_full_weight_minutes=config.blend_full_weight_minutes,
        carried_context_weight=config.carried_context_weight,
        # The same half-life the minutes model uses. A goal and an appearance
        # go stale at the same rate because they are the same weekend.
        decay_half_life_events=config.decay_half_life_events,
        prediction_cutoff=cutoff,
        data_available_at=cutoff,
        source_hashes=(_SOURCE_HASH,),
    )
    return project_player_rates(evidence)


def observation(
    row: ElementRow,
    season: str,
    cutoff: datetime,
    *,
    team_id: int | None = None,
    position_id: int | None = None,
) -> RateObservation:
    """Club and role travel with the return, when they are known.

    Both default to None rather than to a guess. A carried season whose club is
    unknown is reported as unknown by `project_player_rates`, which is not the
    same as reported as unchanged -- and the difference is the whole point.

    `cutoff` is not used to clamp the kickoff. It once was, which meant the leak
    guard in `project_player_rates` compared a value that had already been made
    to satisfy it. Callers filter on the real kickoff instead, so a match played
    after the decision moment never reaches this at all.
    """
    return RateObservation(
        season=season,
        event_id=row.gameweek,
        minutes=min(row.minutes, 120),
        goals=row.goals,
        assists=row.assists,
        expected_goals=row.expected_goals,
        expected_assists=row.expected_assists,
        kickoff_time=row.kickoff_time,
        team_id=team_id,
        position_id=position_id,
    )


__all__ = [
    "LeagueRates",
    "league_rates",
    "observation",
    "project_element_minutes",
    "project_element_rates",
    "shrunk_rate",
]
