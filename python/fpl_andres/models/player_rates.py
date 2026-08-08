"""Per-90 scoring rates with shrinkage and season carry-forward.

Two problems are solved together because they are the same problem at different
sample sizes.

*Shrinkage*: a player with 200 minutes and three shots is not a 1.35 xG/90
striker. Rates shrink toward a sourced position prior in proportion to how few
minutes back them.

*Carry-forward*: before a ball is kicked there is no current-season evidence at
all, so gameweek 1 leans entirely on the prior season, at a reduced evidence
level that names the season it came from. As current-season minutes accumulate
they progressively displace the carried rate until, at the sourced
``blend_full_weight_minutes``, the prior season contributes nothing.

Carry-forward applies to a player's own rates only. Team context - clean sheets,
opposition strength - belongs to the team model, so a player who changed club
keeps their rates and inherits their new club's context by construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fpl_andres.events import MAX_EVENT
from fpl_andres.models.contracts import EvidenceLevel
from fpl_andres.timeguard import require_utc

_MINUTES_PER_90 = 90.0


class FutureRateEvidenceError(ValueError):
    """Raised when rate evidence postdates the decision cutoff."""


class RateObservation(BaseModel):
    """One completed appearance's attacking return."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    season: Annotated[str, Field(pattern=r"^20[0-9]{2}-[0-9]{2}$")]
    event_id: Annotated[int, Field(ge=1, le=MAX_EVENT)]
    minutes: Annotated[int, Field(ge=0, le=120)]
    goals: Annotated[int, Field(ge=0)]
    assists: Annotated[int, Field(ge=0)]
    expected_goals: Annotated[float, Field(ge=0.0)] | None = None
    expected_assists: Annotated[float, Field(ge=0.0)] | None = None
    kickoff_time: datetime
    # The context the return was produced in, so a carried
    # season can be discounted when it was produced somewhere else. Optional
    # because not every source records them, and a source that does not is
    # reported as unknown rather than assumed unchanged.
    team_id: Annotated[int, Field(ge=1, le=20)] | None = None
    position_id: Annotated[int, Field(ge=1, le=4)] | None = None

    @model_validator(mode="after")
    def validate_observation(self) -> RateObservation:
        _require_utc(self.kickoff_time, "kickoff_time")
        return self


class RatePrior(BaseModel):
    """Sourced position prior the rates shrink toward."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    goals_per_90: Annotated[float, Field(ge=0.0, le=5.0)]
    assists_per_90: Annotated[float, Field(ge=0.0, le=5.0)]
    # Prior strength expressed in the currency it shrinks: minutes.
    strength_minutes: Annotated[float, Field(gt=0.0, le=10_000.0)]


class PlayerRateEvidence(BaseModel):
    """Everything the rate model may see for one player."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    element_code: Annotated[int, Field(gt=0)]
    season: Annotated[str, Field(pattern=r"^20[0-9]{2}-[0-9]{2}$")]
    prediction_event: Annotated[int, Field(ge=1, le=MAX_EVENT)]

    current_season_observations: tuple[RateObservation, ...] = ()
    prior_season_observations: tuple[RateObservation, ...] = ()

    prior: RatePrior
    # Sourced. Below this many total minutes nothing is projected.
    minimum_minutes: Annotated[float, Field(ge=0.0, le=10_000.0)]
    # Sourced. The current-season minutes at which the carried season stops contributing.
    blend_full_weight_minutes: Annotated[float, Field(gt=0.0, le=10_000.0)]
    # Caller. How much of a carried season survives a change of club or role.
    #
    # The blend weighted the carried season by minutes alone,
    # so a striker's twenty goals for a relegated side counted exactly as a
    # striker's twenty goals for the same side he still plays for. A move
    # changes the service, the set pieces and the penalty order; a move to a
    # deeper role changes what the position prior should even be.
    #
    # No default, because nothing here can measure it and a number invented at
    # this layer would be indistinguishable from one somebody checked. 1.0
    # keeps the previous behaviour, and says so at the call site.
    carried_context_weight: Annotated[float, Field(ge=0.0, le=1.0)]
    # Sourced. Gameweeks over which a current-season observation loses half its
    # weight. Without it a gameweek 1 goal and a gameweek 37 goal counted the
    # same, while the minutes model beside this one had decayed per event all
    # along. The carried season is not decayed within itself: it is a whole
    # season ago and the season blend already prices that.
    decay_half_life_events: Annotated[float, Field(gt=0.0, le=100.0)]

    prediction_cutoff: datetime
    data_available_at: datetime
    source_hashes: tuple[str, ...]

    @model_validator(mode="after")
    def validate_evidence(self) -> PlayerRateEvidence:
        _require_utc(self.prediction_cutoff, "prediction_cutoff")
        _require_utc(self.data_available_at, "data_available_at")
        if not self.source_hashes:
            raise ValueError("rate evidence must cite at least one source hash")
        for observation in self.current_season_observations:
            if observation.season != self.season:
                raise ValueError("current-season observations must match the evidence season")
        prior_seasons = {observation.season for observation in self.prior_season_observations}
        if self.season in prior_seasons:
            raise ValueError("carried observations must not come from the current season")
        if len(prior_seasons) > 1:
            raise ValueError("carried observations must come from a single prior season")
        # Rates are sums over observations, so the same match counted twice
        # doubles its minutes and its returns into the per-90 figure. A match is
        # identified by its event *and its kickoff*: a double gameweek is two
        # matches in one event, and both of them really happened.
        for label, observations in (
            ("current-season", self.current_season_observations),
            ("carried", self.prior_season_observations),
        ):
            matches = [
                (observation.event_id, observation.kickoff_time) for observation in observations
            ]
            if len(set(matches)) != len(matches):
                raise ValueError(f"{label} observations must not repeat a match")
        # Two sourced parameters that must agree with each other. If the blend
        # saturates at or below the floor for projecting at all, then every
        # player who clears the floor is already at full current-season weight
        # and the carried season can never contribute anything.
        if self.blend_full_weight_minutes <= self.minimum_minutes:
            raise ValueError(
                f"blend_full_weight_minutes ({self.blend_full_weight_minutes}) must exceed "
                f"minimum_minutes ({self.minimum_minutes}), or the carried season "
                "is silently discarded for every player who clears the floor"
            )
        return self

    @property
    def carried_season(self) -> str | None:
        if not self.prior_season_observations:
            return None
        return self.prior_season_observations[0].season


class PlayerRateProjection(BaseModel):
    """Shrunk, blended per-90 attacking rates for one player."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    element_code: Annotated[int, Field(gt=0)]
    season: Annotated[str, Field(pattern=r"^20[0-9]{2}-[0-9]{2}$")]
    event: Annotated[int, Field(ge=1, le=MAX_EVENT)]
    goals_per_90: Annotated[float, Field(ge=0.0)]
    assists_per_90: Annotated[float, Field(ge=0.0)]
    current_season_minutes: Annotated[float, Field(ge=0.0)]
    carried_season: str | None
    carried_weight: Annotated[float, Field(ge=0.0, le=1.0)]
    evidence_level: EvidenceLevel
    reason_codes: tuple[str, ...]
    data_available_at: datetime
    source_hashes: tuple[str, ...]

    @model_validator(mode="after")
    def validate_projection(self) -> PlayerRateProjection:
        _require_utc(self.data_available_at, "data_available_at")
        if self.evidence_level == "unavailable" and (
            self.goals_per_90 != 0.0 or self.assists_per_90 != 0.0
        ):
            raise ValueError("an unavailable projection must not carry rates")
        if self.carried_weight > 0.0 and self.carried_season is None:
            raise ValueError("a carried weight requires the season it was carried from")
        return self


def project_player_rates(evidence: PlayerRateEvidence) -> PlayerRateProjection:
    """Blend carried and current-season rates, shrunk toward the sourced prior."""
    _reject_future_evidence(evidence)

    current_minutes = _total_minutes(evidence.current_season_observations)
    carried_minutes = _total_minutes(evidence.prior_season_observations)
    reasons: list[str] = [
        f"current_minutes={current_minutes:.0f}",
        f"carried_minutes={carried_minutes:.0f}",
    ]

    if current_minutes + carried_minutes < evidence.minimum_minutes:
        # No comparable prior observation exists: a promoted-club debutant, an
        # arrival from outside the league, or a player below the sample floor.
        reasons.append(f"below_minutes_floor={evidence.minimum_minutes:.0f}")
        return _unavailable(evidence, current_minutes, reasons)

    # Current-season evidence displaces the carried season progressively.
    current_weight = min(1.0, current_minutes / evidence.blend_full_weight_minutes)
    if current_minutes <= 0.0:
        current_weight = 0.0
    # Last, so it cannot be undone: with nothing carried there is nothing for a
    # carried weight to refer to, and the projection contract rejects one.
    if not evidence.prior_season_observations:
        current_weight = 1.0
    carried_weight = 1.0 - current_weight

    # A carried season produced somewhere else is worth less
    # than the same minutes produced here. The discount is applied to the
    # carried share rather than to the minutes, so it cannot push the blend
    # below the minutes floor that already decided the projection was possible.
    context = _carried_context(evidence)
    reasons.append(f"carried_context={context}")
    if context == "changed" and carried_weight > 0.0:
        carried_weight *= evidence.carried_context_weight
        current_weight = 1.0 - carried_weight
    reasons.append(f"carried_weight={carried_weight:.3f}")

    # Decide the measurement basis once, across both sets. Blending expected
    # values with actual ones would mix two different measurements.
    use_expected = _has_complete_expected(evidence.current_season_observations) and (
        _has_complete_expected(evidence.prior_season_observations)
    )
    reasons.append("basis=expected" if use_expected else "basis=actual")

    current_goals, current_assists = _totals(evidence.current_season_observations, use_expected)
    carried_goals, carried_assists = _totals(evidence.prior_season_observations, use_expected)
    reasons.append(f"current_returns={current_goals + current_assists:.2f}")

    # One weight per observation: the season share, times recency within the
    # current season. The rate is a ratio so the weights cancel out of it; they
    # decide only how much of the player's own evidence survives the shrinkage.
    current_decay = _decay_weights(
        evidence.current_season_observations,
        evidence.prediction_event,
        evidence.decay_half_life_events,
    )
    weights = [current_weight * decay for decay in current_decay] + [
        carried_weight for _ in evidence.prior_season_observations
    ]
    spans = [
        float(observation.minutes)
        for observation in (
            *evidence.current_season_observations,
            *evidence.prior_season_observations,
        )
    ]
    weighted_minutes = sum(weight * span for weight, span in zip(weights, spans, strict=True))
    current_goal_credit, current_assist_credit = _weighted_totals(
        evidence.current_season_observations, use_expected, current_decay
    )
    blended_minutes = weighted_minutes
    blended_goals = current_weight * current_goal_credit + carried_weight * carried_goals
    blended_assists = current_weight * current_assist_credit + carried_weight * carried_assists
    effective_minutes = _effective_minutes(weights, spans)

    goals_per_90 = _shrink(
        _per_90(blended_goals, blended_minutes),
        effective_minutes,
        evidence.prior.goals_per_90,
        evidence.prior,
    )
    assists_per_90 = _shrink(
        _per_90(blended_assists, blended_minutes),
        effective_minutes,
        evidence.prior.assists_per_90,
        evidence.prior,
    )
    reasons.append(f"effective_minutes={effective_minutes:.0f}")

    evidence_level: EvidenceLevel = "observed"
    if carried_weight > 0.0:
        # A carried rate is evidence about a different season. Say so.
        evidence_level = "inferred"
        reasons.append(f"carried_forward_from={evidence.carried_season}")

    return PlayerRateProjection(
        element_code=evidence.element_code,
        season=evidence.season,
        event=evidence.prediction_event,
        goals_per_90=goals_per_90,
        assists_per_90=assists_per_90,
        current_season_minutes=current_minutes,
        carried_season=evidence.carried_season,
        carried_weight=carried_weight,
        evidence_level=evidence_level,
        reason_codes=tuple(reasons),
        data_available_at=evidence.data_available_at,
        source_hashes=evidence.source_hashes,
    )


def _has_complete_expected(observations: tuple[RateObservation, ...]) -> bool:
    """True when every observation carries both expected columns.

    An empty set is vacuously complete so it never drags the basis down.
    """
    return all(
        observation.expected_goals is not None and observation.expected_assists is not None
        for observation in observations
    )


class InconsistentObservationBasis(ValueError):
    """Raised when expected values are asked for and one is absent.

    `_totals` used ``observation.expected_goals or 0.0``, which
    reads as a default for a missing value and is not one: the caller only
    reaches that branch after `_has_complete_expected` has confirmed every
    observation carries both columns.

    The substitution was therefore unreachable, and that is the problem with it.
    A silent zero standing thirty lines from the guarantee that makes it
    unreachable is a zero somebody will one day reach, by relaxing the guarantee
    without noticing what depended on it -- and the failure would be a player
    credited with no expected goals rather than an error.
    """


def _totals(observations: tuple[RateObservation, ...], use_expected: bool) -> tuple[float, float]:
    """Total goal and assist credit on the chosen measurement basis.

    The basis is decided once across both seasons, so a set reaching here with
    ``use_expected`` set has already been checked complete. This states that
    rather than assuming it.
    """
    if use_expected:
        goals = 0.0
        assists = 0.0
        for observation in observations:
            if observation.expected_goals is None or observation.expected_assists is None:
                raise InconsistentObservationBasis(
                    f"event {observation.event_id} in {observation.season} has no expected "
                    "values, but the expected basis was chosen for this set"
                )
            goals += observation.expected_goals
            assists += observation.expected_assists
        return goals, assists
    goals = float(sum(observation.goals for observation in observations))
    assists = float(sum(observation.assists for observation in observations))
    return goals, assists


def _total_minutes(observations: tuple[RateObservation, ...]) -> float:
    return float(sum(observation.minutes for observation in observations))


def _per_90(credit: float, minutes: float) -> float:
    """A per-90 rate, or zero where nothing was played."""
    if minutes <= 0.0 and credit > 0.0:
        raise ValueError(f"{credit} returns cannot have come from {minutes} minutes")
    return 0.0 if minutes <= 0.0 else credit * _MINUTES_PER_90 / minutes


def _weighted_totals(
    observations: tuple[RateObservation, ...],
    use_expected: bool,
    weights: Sequence[float],
) -> tuple[float, float]:
    """Goal and assist credit with each match weighted by its recency."""
    goals = 0.0
    assists = 0.0
    for observation, weight in zip(observations, weights, strict=True):
        if use_expected:
            if observation.expected_goals is None or observation.expected_assists is None:
                raise InconsistentObservationBasis(
                    f"event {observation.event_id} in {observation.season} has no expected "
                    "values, but the expected basis was chosen for this set"
                )
            goals += weight * observation.expected_goals
            assists += weight * observation.expected_assists
        else:
            goals += weight * observation.goals
            assists += weight * observation.assists
    return goals, assists


def _carried_context(evidence: PlayerRateEvidence) -> str:
    """Whether the carried season was produced in the same club and role.

    Three answers, and the third matters as much as the others.

    "same"      the carried season is directly comparable
    "changed"   a different club or a different role, so discount it
    "unknown"   the source did not record club or role

    Unknown is not treated as same. A source that cannot say is a source that
    cannot rule out a move, and silently reading it as "unchanged" would apply
    the optimistic answer exactly where there is no evidence for it. The reason
    code carries it forward so a projection built on an incomplete source is
    distinguishable from one built on a complete one.

    Determined from the most recent observation on each side rather than from a
    majority: a player who moved in January is described by where he plays now,
    and averaging the two halves of his season describes nowhere.
    """
    carried = evidence.prior_season_observations
    current = evidence.current_season_observations
    if not carried or not current:
        return "unknown"

    last_carried = max(carried, key=lambda observation: observation.kickoff_time)
    last_current = max(current, key=lambda observation: observation.kickoff_time)
    pairs = (
        (last_carried.team_id, last_current.team_id),
        (last_carried.position_id, last_current.position_id),
    )
    if any(before is None or after is None for before, after in pairs):
        return "unknown"
    return "same" if all(before == after for before, after in pairs) else "changed"


def _decay_weights(
    observations: tuple[RateObservation, ...],
    prediction_event: int,
    half_life: float,
) -> tuple[float, ...]:
    """Exponential recency weight per observation, newest weighing one."""
    return tuple(
        0.5 ** ((prediction_event - observation.event_id) / half_life)
        for observation in observations
    )


def _effective_minutes(weights: Sequence[float], minutes: Sequence[float]) -> float:
    """How many unweighted minutes carry the same precision as this weighted set.

    The rate itself is a ratio, so the weights cancel and any scaling of them
    gives the same estimate. Its *precision* does not cancel, and shrinkage is
    entirely a statement about precision.

    For returns g_i ~ Poisson(lambda * m_i) the weighted estimate has variance
    lambda * sum(w_i^2 * m_i) / sum(w_i * m_i)^2. Setting that equal to
    lambda / N gives N below. It is the Kish effective sample size written for
    minutes rather than for counts.

    The previous code used the weighted *mean* of the two seasons' minute
    totals, which is not a sample size at all: 900 minutes in each of two
    seasons came out as 900 rather than 1800, so a player with two full seasons
    of evidence was shrunk toward the position prior as hard as one with a
    single season.
    """
    numerator = sum(weight * span for weight, span in zip(weights, minutes, strict=True))
    denominator = sum(weight * weight * span for weight, span in zip(weights, minutes, strict=True))
    if denominator <= 0.0:
        return 0.0
    return numerator * numerator / denominator


def _shrink(rate: float, effective_minutes: float, prior_rate: float, prior: RatePrior) -> float:
    """Pull an observed per-90 rate toward the prior, by effective sample size."""
    total_minutes = effective_minutes + prior.strength_minutes
    if total_minutes <= 0.0:
        return prior_rate
    return (rate * effective_minutes + prior_rate * prior.strength_minutes) / total_minutes


def _unavailable(
    evidence: PlayerRateEvidence, current_minutes: float, reasons: list[str]
) -> PlayerRateProjection:
    return PlayerRateProjection(
        element_code=evidence.element_code,
        season=evidence.season,
        event=evidence.prediction_event,
        goals_per_90=0.0,
        assists_per_90=0.0,
        current_season_minutes=current_minutes,
        carried_season=evidence.carried_season,
        carried_weight=0.0,
        evidence_level="unavailable",
        reason_codes=tuple(reasons),
        data_available_at=evidence.data_available_at,
        source_hashes=evidence.source_hashes,
    )


def _reject_future_evidence(evidence: PlayerRateEvidence) -> None:
    if evidence.data_available_at > evidence.prediction_cutoff:
        raise FutureRateEvidenceError("rate evidence became available after the prediction cutoff")
    for observation in evidence.current_season_observations:
        if observation.event_id >= evidence.prediction_event:
            raise FutureRateEvidenceError("observations must precede the event being predicted")
    for observation in (
        *evidence.current_season_observations,
        *evidence.prior_season_observations,
    ):
        if observation.kickoff_time > evidence.prediction_cutoff:
            raise FutureRateEvidenceError("observation kickoff must precede the prediction cutoff")


def _require_utc(value: datetime, label: str) -> None:
    require_utc(value, label)


__all__ = [
    "FutureRateEvidenceError",
    "PlayerRateEvidence",
    "PlayerRateProjection",
    "RateObservation",
    "RatePrior",
    "project_player_rates",
]
