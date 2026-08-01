from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from statistics import fmean

from fpl_andres.models.contracts import EvidenceLevel, FixtureResult, TeamGoalPrediction


class InsufficientHistoryError(ValueError):
    """Raised when a team-aware estimate lacks its declared sample floor."""


@dataclass(frozen=True)
class _Rate:
    value: float
    count: int


class LeagueVenueGoalBaseline:
    def __init__(
        self,
        *,
        season: str,
        home_rate: float,
        away_rate: float,
        observed: tuple[FixtureResult, ...],
    ) -> None:
        self._season = season
        self._home_rate = home_rate
        self._away_rate = away_rate
        self._observed = observed

    @classmethod
    def fit(
        cls,
        fixtures: Sequence[FixtureResult],
        *,
        season: str,
    ) -> LeagueVenueGoalBaseline:
        observed = _validate_training_data(fixtures, season=season)
        return cls(
            season=season,
            home_rate=fmean(fixture.home_goals for fixture in observed),
            away_rate=fmean(fixture.away_goals for fixture in observed),
            observed=observed,
        )

    def predict(
        self,
        *,
        home_team_id: int,
        away_team_id: int,
        event: int,
    ) -> TeamGoalPrediction:
        _validate_prediction_ids(home_team_id, away_team_id, event)
        return _prediction(
            season=self._season,
            event=event,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_expected_goals=self._home_rate,
            away_expected_goals=self._away_rate,
            evidence_level="inferred",
            reason_codes=("league_venue_mean", f"matches_used={len(self._observed)}"),
            observed=self._observed,
        )


class TeamVenueGoalRateModel:
    def __init__(
        self,
        *,
        season: str,
        minimum_matches: int,
        observed: tuple[FixtureResult, ...],
        home_attack: dict[int, _Rate],
        home_conceded: dict[int, _Rate],
        away_attack: dict[int, _Rate],
        away_conceded: dict[int, _Rate],
    ) -> None:
        self._season = season
        self._minimum_matches = minimum_matches
        self._observed = observed
        self._home_attack = home_attack
        self._home_conceded = home_conceded
        self._away_attack = away_attack
        self._away_conceded = away_conceded

    @classmethod
    def fit(
        cls,
        fixtures: Sequence[FixtureResult],
        *,
        season: str,
        minimum_matches: int,
    ) -> TeamVenueGoalRateModel:
        if isinstance(minimum_matches, bool) or minimum_matches < 1:
            raise ValueError("minimum_matches must be a positive integer")
        observed = _validate_training_data(fixtures, season=season)
        return cls(
            season=season,
            minimum_matches=minimum_matches,
            observed=observed,
            home_attack=_rates(observed, team_side="home", value="scored"),
            home_conceded=_rates(observed, team_side="home", value="conceded"),
            away_attack=_rates(observed, team_side="away", value="scored"),
            away_conceded=_rates(observed, team_side="away", value="conceded"),
        )

    def predict(
        self,
        *,
        home_team_id: int,
        away_team_id: int,
        event: int,
    ) -> TeamGoalPrediction:
        _validate_prediction_ids(home_team_id, away_team_id, event)
        components = (
            (home_team_id, self._home_attack.get(home_team_id)),
            (away_team_id, self._away_conceded.get(away_team_id)),
            (away_team_id, self._away_attack.get(away_team_id)),
            (home_team_id, self._home_conceded.get(home_team_id)),
        )
        for team_id, rate in components:
            if rate is None or rate.count < self._minimum_matches:
                count = 0 if rate is None else rate.count
                raise InsufficientHistoryError(
                    f"team {team_id} has {count} venue matches; requires {self._minimum_matches}"
                )

        home_attack = _known_rate(components[0][1])
        away_conceded = _known_rate(components[1][1])
        away_attack = _known_rate(components[2][1])
        home_conceded = _known_rate(components[3][1])
        matches_used = sum(rate.count for _, rate in components if rate is not None)
        return _prediction(
            season=self._season,
            event=event,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_expected_goals=fmean((home_attack.value, away_conceded.value)),
            away_expected_goals=fmean((away_attack.value, home_conceded.value)),
            evidence_level="experimental",
            reason_codes=("team_venue_rates", f"matches_used={matches_used}"),
            observed=self._observed,
        )


def _validate_training_data(
    fixtures: Sequence[FixtureResult],
    *,
    season: str,
) -> tuple[FixtureResult, ...]:
    if not fixtures:
        raise InsufficientHistoryError("at least one observed fixture is required")
    if any(fixture.season != season for fixture in fixtures):
        raise ValueError("training fixtures must belong to exactly one season")
    return tuple(fixtures)


def _rates(
    fixtures: Iterable[FixtureResult],
    *,
    team_side: str,
    value: str,
) -> dict[int, _Rate]:
    values: defaultdict[int, list[int]] = defaultdict(list)
    for fixture in fixtures:
        if team_side == "home":
            team_id = fixture.home_team_id
            goals = fixture.home_goals if value == "scored" else fixture.away_goals
        else:
            team_id = fixture.away_team_id
            goals = fixture.away_goals if value == "scored" else fixture.home_goals
        values[team_id].append(goals)
    return {
        team_id: _Rate(value=fmean(team_values), count=len(team_values))
        for team_id, team_values in values.items()
    }


def _prediction(
    *,
    season: str,
    event: int,
    home_team_id: int,
    away_team_id: int,
    home_expected_goals: float,
    away_expected_goals: float,
    evidence_level: EvidenceLevel,
    reason_codes: tuple[str, ...],
    observed: tuple[FixtureResult, ...],
) -> TeamGoalPrediction:
    return TeamGoalPrediction(
        season=season,
        event=event,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_expected_goals=home_expected_goals,
        away_expected_goals=away_expected_goals,
        evidence_level=evidence_level,
        reason_codes=reason_codes,
        data_available_at=max(fixture.data_available_at for fixture in observed),
        source_hashes=tuple(sorted({fixture.source_hash for fixture in observed})),
    )


def _validate_prediction_ids(home_team_id: int, away_team_id: int, event: int) -> None:
    if home_team_id < 1 or away_team_id < 1 or home_team_id == away_team_id:
        raise ValueError("prediction teams must be distinct positive IDs")
    if not 1 <= event <= 38:
        raise ValueError("prediction event must be between 1 and 38")


def _known_rate(rate: _Rate | None) -> _Rate:
    if rate is None:
        raise AssertionError("rate must be validated before use")
    return rate


__all__ = [
    "InsufficientHistoryError",
    "LeagueVenueGoalBaseline",
    "TeamVenueGoalRateModel",
]
