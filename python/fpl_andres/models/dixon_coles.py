from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from datetime import datetime

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize

from fpl_andres.events import MAX_EVENT
from fpl_andres.models.baselines import InsufficientHistoryError
from fpl_andres.models.contracts import FixtureResult, TeamGoalPrediction
from fpl_andres.timeguard import is_utc


class ModelFitError(RuntimeError):
    """Raised when numerical optimization cannot produce a valid model."""


# Below this the low-score correction is treated as out of bounds. Small enough
# that a real fit never approaches it, large enough that its logarithm is a
# number rather than a way of writing minus infinity.
_MINIMUM_ADJUSTMENT = 1e-6
# How steeply the objective climbs once the correction has gone out of bounds.
# Only its sign and scale matter: it has to dominate the likelihood so the
# optimiser turns round, without being so large it overflows.
_BARRIER_SLOPE = 1e4


class DixonColesModel:
    def __init__(
        self,
        *,
        season: str,
        teams: tuple[int, ...],
        attacks: tuple[float, ...],
        defences: tuple[float, ...],
        home_advantage: float,
        rho: float,
        decay_rate: float,
        minimum_matches: int,
        observed: tuple[FixtureResult, ...],
    ) -> None:
        self._season = season
        self._teams = teams
        self._team_indices = {team_id: index for index, team_id in enumerate(teams)}
        self._attacks = attacks
        self._defences = defences
        self._home_advantage = home_advantage
        self._rho = rho
        self._decay_rate = decay_rate
        self._minimum_matches = minimum_matches
        self._observed = observed

    @property
    def teams(self) -> tuple[int, ...]:
        """Team ids the fit actually saw. Anything else cannot be predicted."""
        return self._teams

    @classmethod
    def fit(
        cls,
        fixtures: Sequence[FixtureResult],
        *,
        season: str,
        as_of: datetime,
        decay_rate: float,
        minimum_matches: int,
        max_iterations: int,
    ) -> DixonColesModel:
        observed = _validate_training_data(
            fixtures,
            season=season,
            as_of=as_of,
            decay_rate=decay_rate,
            minimum_matches=minimum_matches,
            max_iterations=max_iterations,
        )
        teams = tuple(
            sorted(
                {fixture.home_team_id for fixture in observed}
                | {fixture.away_team_id for fixture in observed}
            )
        )
        team_indices = {team_id: index for index, team_id in enumerate(teams)}
        team_count = len(teams)
        initial = np.zeros(2 * (team_count - 1) + 2, dtype=np.float64)
        home_mean = sum(fixture.home_goals for fixture in observed) / len(observed)
        away_mean = sum(fixture.away_goals for fixture in observed) / len(observed)
        initial[-2] = math.log((home_mean + 0.1) / (away_mean + 0.1))
        bounds = (
            [(-4.0, 4.0)] * (team_count - 1)
            + [(-4.0, 4.0)] * (team_count - 1)
            + [(-2.0, 2.0), (-0.2, 0.2)]
        )

        def objective(parameters: NDArray[np.float64]) -> float:
            attacks, defences, home_advantage, rho = _decode(parameters, team_count)
            negative_log_likelihood = 0.0
            for fixture in observed:
                home_index = team_indices[fixture.home_team_id]
                away_index = team_indices[fixture.away_team_id]
                home_rate = math.exp(home_advantage + attacks[home_index] - defences[away_index])
                away_rate = math.exp(attacks[away_index] - defences[home_index])
                adjustment = _low_score_adjustment(
                    fixture.home_goals,
                    fixture.away_goals,
                    home_rate=home_rate,
                    away_rate=away_rate,
                    rho=rho,
                )
                if adjustment <= _MINIMUM_ADJUSTMENT:
                    # The low-score correction has left the region where the
                    # likelihood is defined. Infinity is the truthful value
                    # there, and this used to return it — but a numerical
                    # gradient cannot be read off infinity. `inf - inf` is NaN,
                    # L-BFGS-B reads NaN as a zero gradient, declares
                    # convergence at the starting point and reports success. The
                    # caller then gets a model that rates every side identically
                    # and is never told the fit did not move. Measured on
                    # 2025-26: 380 fixtures, one iteration, zero movement.
                    #
                    # So instead the objective stays finite and slopes back the
                    # way it came. This is not a gradient read off fiction: the
                    # further the correction is out of bounds the worse the
                    # point genuinely is, and the direction of improvement is
                    # genuinely inward.
                    log_adjustment = math.log(_MINIMUM_ADJUSTMENT) - _BARRIER_SLOPE * (
                        _MINIMUM_ADJUSTMENT - adjustment
                    )
                else:
                    log_adjustment = math.log(adjustment)
                age_days = (as_of - fixture.kickoff_time).total_seconds() / 86_400
                weight = math.exp(-decay_rate * age_days)
                log_probability = (
                    fixture.home_goals * math.log(home_rate)
                    - home_rate
                    - math.lgamma(fixture.home_goals + 1)
                    + fixture.away_goals * math.log(away_rate)
                    - away_rate
                    - math.lgamma(fixture.away_goals + 1)
                    + log_adjustment
                )
                negative_log_likelihood -= weight * log_probability
            return negative_log_likelihood

        result = minimize(
            objective,
            initial,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": max_iterations, "ftol": 1e-12},
        )
        if not result.success or not np.all(np.isfinite(result.x)):
            raise ModelFitError(f"Dixon-Coles optimization failed: {result.message}")
        # A fit that never left its starting point is not a fit. L-BFGS-B can
        # report success without moving, and the starting point is every team
        # equal, which is a claim about football rather than a measurement of it.
        if np.array_equal(result.x, initial):
            raise ModelFitError(
                "Dixon-Coles optimization did not move from its starting point, "
                "which would rate every side identically"
            )
        attacks, defences, home_advantage, rho = _decode(result.x, team_count)
        return cls(
            season=season,
            teams=teams,
            attacks=attacks,
            defences=defences,
            home_advantage=home_advantage,
            rho=rho,
            decay_rate=decay_rate,
            minimum_matches=minimum_matches,
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
        for team_id in (home_team_id, away_team_id):
            if team_id not in self._team_indices:
                raise InsufficientHistoryError(
                    f"team {team_id} has 0 observed matches; requires {self._minimum_matches}"
                )
        home_index = self._team_indices[home_team_id]
        away_index = self._team_indices[away_team_id]
        return TeamGoalPrediction(
            season=self._season,
            event=event,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_expected_goals=math.exp(
                self._home_advantage + self._attacks[home_index] - self._defences[away_index]
            ),
            away_expected_goals=math.exp(self._attacks[away_index] - self._defences[home_index]),
            evidence_level="experimental",
            reason_codes=(
                "dixon_coles",
                f"matches_used={len(self._observed)}",
                f"decay_rate_per_day={self._decay_rate:g}",
                f"rho={self._rho:.6f}",
            ),
            data_available_at=max(fixture.data_available_at for fixture in self._observed),
            source_hashes=tuple(sorted({fixture.source_hash for fixture in self._observed})),
        )


def _validate_training_data(
    fixtures: Sequence[FixtureResult],
    *,
    season: str,
    as_of: datetime,
    decay_rate: float,
    minimum_matches: int,
    max_iterations: int,
) -> tuple[FixtureResult, ...]:
    if not is_utc(as_of):
        raise ValueError("as_of must be an aware UTC timestamp")
    if not math.isfinite(decay_rate) or decay_rate < 0:
        raise ValueError("decay_rate must be finite and non-negative")
    if isinstance(minimum_matches, bool) or not isinstance(minimum_matches, int):
        raise ValueError("minimum_matches must be a positive integer")
    if minimum_matches < 1:
        raise ValueError("minimum_matches must be a positive integer")
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int):
        raise ValueError("max_iterations must be a positive integer")
    if max_iterations < 1:
        raise ValueError("max_iterations must be a positive integer")
    if not fixtures:
        raise InsufficientHistoryError("at least one observed fixture is required")
    if any(fixture.season != season for fixture in fixtures):
        raise ValueError("training fixtures must belong to exactly one season")
    if any(fixture.data_available_at > as_of for fixture in fixtures):
        raise ValueError("training fixture became available after as_of")

    counts = Counter(
        team_id for fixture in fixtures for team_id in (fixture.home_team_id, fixture.away_team_id)
    )
    for team_id, count in sorted(counts.items()):
        if count < minimum_matches:
            raise InsufficientHistoryError(
                f"team {team_id} has {count} observed matches; requires {minimum_matches}"
            )
    return tuple(fixtures)


def _decode(
    parameters: NDArray[np.float64],
    team_count: int,
) -> tuple[tuple[float, ...], tuple[float, ...], float, float]:
    """Free parameters back into attacks, defences, home advantage and rho.

    Both vectors are pinned, not only the attacks. Rates are
    `exp(home_advantage + attack_i - defence_j)`, so adding a constant to every
    defence and the same constant to the home advantage leaves every rate
    unchanged: with the defences all free the likelihood had a flat ridge and
    the optimiser settled wherever its path happened to end. Predictions were
    unaffected -- they only ever depended on differences -- but the reported
    home advantage and any raw attack or defence was an artefact of the run
    rather than a measurement.
    """
    attack_end = team_count - 1
    defence_end = attack_end + team_count - 1
    attacks = (*tuple(float(value) for value in parameters[:attack_end]), 0.0)
    defences = (*tuple(float(value) for value in parameters[attack_end:defence_end]), 0.0)
    return attacks, defences, float(parameters[-2]), float(parameters[-1])


def _low_score_adjustment(
    home_goals: int,
    away_goals: int,
    *,
    home_rate: float,
    away_rate: float,
    rho: float,
) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1 - home_rate * away_rate * rho
    if home_goals == 0 and away_goals == 1:
        return 1 + home_rate * rho
    if home_goals == 1 and away_goals == 0:
        return 1 + away_rate * rho
    if home_goals == 1 and away_goals == 1:
        return 1 - rho
    return 1.0


def _validate_prediction_ids(home_team_id: int, away_team_id: int, event: int) -> None:
    if home_team_id < 1 or away_team_id < 1 or home_team_id == away_team_id:
        raise ValueError("prediction teams must be distinct positive IDs")
    if not 1 <= event <= MAX_EVENT:
        raise ValueError(f"prediction event must be between 1 and {MAX_EVENT}")


__all__ = [
    "DixonColesModel",
    "ModelFitError",
]
