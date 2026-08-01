"""Expected points assembly.

Composes the minutes model, the per-90 rate model and team context into a
per-player expected-points projection, decomposed into the components that
produced it so a surface can show why rather than just how much.

Every points value comes from the rules snapshot. Nothing here hardcodes an FPL
scoring number, because a rule change must break visibly rather than silently
produce stale arithmetic.

Components this module cannot yet source - bonus, saves, defensive contribution,
cards - are reported as missing rather than assumed to be zero, so a caller can
tell the difference between "no bonus expected" and "no bonus model".
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy.stats import poisson

from fpl_andres.models.contracts import EvidenceLevel
from fpl_andres.models.minutes import MinutesProjection
from fpl_andres.models.player_rates import PlayerRateProjection
from fpl_andres.rules import ScoringRules

# A season can exceed 38 events when it is disrupted: 2019/20 was suspended
# and resumed, running to 47. The history schema already allows this.
MAX_EVENT = 47

_MINUTES_PER_90 = 90.0
_GOALS_CONCEDED_PER_POINT = 2
_SAVES_PER_POINT = 3
# Standard deviations of headroom above the mean before the tail is dropped.
# Twelve keeps the remaining mass below 1e-12 for every rate this model can be
# handed; ten was measurably short at low rates, leaving 1.6e-12 at rate 3. The
# constant this replaces was a flat 15, whose comment claimed the tail was below
# floating-point noise. Measured, that was false wherever the rate ran high: at
# 14 saves a match the tail held 0.33 of the mass and cost 1.88 points, and a
# defensive-contribution rate of 20 cost 5.68.
_POISSON_SIGMAS = 12.0
_POISSON_FLOOR = 15

_EVIDENCE_ORDER: dict[EvidenceLevel, int] = {
    "observed": 0,
    "inferred": 1,
    "experimental": 2,
    "unavailable": 3,
}


class TeamMatchContext(BaseModel):
    """Opposition scoring expectation for the fixture, from the team model."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_goals_conceded: Annotated[float, Field(ge=0.0, le=15.0)]
    evidence_level: EvidenceLevel

    @property
    def clean_sheet_probability(self) -> float:
        return float(poisson.pmf(0, self.expected_goals_conceded))


class ExpectedPointsBreakdown(BaseModel):
    """Per-component decomposition. Components sum exactly to the total."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    appearance: float
    goals: float
    assists: float
    clean_sheet: float
    goals_conceded: float
    saves: float
    bonus: float
    defensive_contribution: float
    cards: float

    @property
    def total(self) -> float:
        return (
            self.appearance
            + self.goals
            + self.assists
            + self.clean_sheet
            + self.goals_conceded
            + self.saves
            + self.bonus
            + self.defensive_contribution
            + self.cards
        )


class ExpectedPointsProjection(BaseModel):
    """Expected points for one player in one event."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    element_code: Annotated[int, Field(gt=0)]
    season: Annotated[str, Field(pattern=r"^20[0-9]{2}-[0-9]{2}$")]
    event: Annotated[int, Field(ge=1, le=MAX_EVENT)]
    position_code: str
    expected_points: float
    breakdown: ExpectedPointsBreakdown
    evidence_level: EvidenceLevel
    missing_components: tuple[str, ...]
    reason_codes: tuple[str, ...]
    data_available_at: datetime
    source_hashes: tuple[str, ...]

    @model_validator(mode="after")
    def validate_projection(self) -> ExpectedPointsProjection:
        if self.data_available_at.tzinfo is None or self.data_available_at.utcoffset() != timedelta(
            0
        ):
            raise ValueError("data_available_at must be an aware UTC timestamp")
        if abs(self.expected_points - self.breakdown.total) > 1e-9:
            raise ValueError("expected points must equal the sum of its components")
        if self.evidence_level == "unavailable" and self.expected_points != 0.0:
            raise ValueError("an unavailable projection must not carry expected points")
        return self


def project_expected_points(
    *,
    minutes: MinutesProjection,
    rates: PlayerRateProjection,
    position_code: str,
    team_context: TeamMatchContext,
    scoring: ScoringRules,
    expected_saves_per_90: float | None = None,
    expected_bonus: float | None = None,
    defensive_contribution_probability: float | None = None,
    expected_card_points: float | None = None,
) -> ExpectedPointsProjection:
    """Assemble expected points from promoted component models."""
    if minutes.element_code != rates.element_code:
        raise ValueError("minutes and rate projections must describe the same player")
    if minutes.event != rates.event:
        raise ValueError("minutes and rate projections must describe the same event")

    evidence_level = _worst(
        minutes.evidence_level, rates.evidence_level, team_context.evidence_level
    )
    missing: list[str] = []
    reasons: list[str] = [
        f"position={position_code}",
        f"expected_minutes={minutes.expected_minutes:.1f}",
        f"clean_sheet_probability={team_context.clean_sheet_probability:.3f}",
    ]

    if evidence_level == "unavailable":
        return _unavailable(
            minutes=minutes,
            rates=rates,
            position_code=position_code,
            missing=tuple(missing),
            reasons=tuple([*reasons, "component_model_unavailable"]),
        )

    ninety_share = minutes.expected_minutes / _MINUTES_PER_90

    appearance = (
        minutes.probability_appear - minutes.probability_sixty_minutes
    ) * scoring.short_play + minutes.probability_sixty_minutes * scoring.long_play

    goals = (
        ninety_share * rates.goals_per_90 * _position_points(scoring.goals_scored, position_code)
    )
    assists = ninety_share * rates.assists_per_90 * scoring.assists

    # A clean sheet only scores for a player who reaches the long-play threshold.
    clean_sheet = (
        minutes.probability_sixty_minutes
        * team_context.clean_sheet_probability
        * _position_points(scoring.clean_sheets, position_code)
    )

    conceded_points = _position_points(scoring.goals_conceded, position_code)
    goals_conceded = 0.0
    if conceded_points != 0:
        expected_penalised = _expected_floor_divide(
            team_context.expected_goals_conceded, _GOALS_CONCEDED_PER_POINT
        )
        goals_conceded = minutes.probability_sixty_minutes * expected_penalised * conceded_points

    if expected_saves_per_90 is None:
        saves = 0.0
        missing.append("saves")
    else:
        expected_saves = ninety_share * expected_saves_per_90
        saves = _expected_floor_divide(expected_saves, _SAVES_PER_POINT) * scoring.saves

    if expected_bonus is None:
        bonus = 0.0
        missing.append("bonus")
    else:
        bonus = expected_bonus

    if defensive_contribution_probability is None:
        defensive_contribution = 0.0
        missing.append("defensive_contribution")
    else:
        defensive_contribution = defensive_contribution_probability * _position_points(
            scoring.defensive_contribution, position_code
        )

    if expected_card_points is None:
        cards = 0.0
        missing.append("cards")
    else:
        cards = expected_card_points

    if missing:
        reasons.append("missing=" + ",".join(missing))

    breakdown = ExpectedPointsBreakdown(
        appearance=appearance,
        goals=goals,
        assists=assists,
        clean_sheet=clean_sheet,
        goals_conceded=goals_conceded,
        saves=saves,
        bonus=bonus,
        defensive_contribution=defensive_contribution,
        cards=cards,
    )

    return ExpectedPointsProjection(
        element_code=minutes.element_code,
        season=minutes.season,
        event=minutes.event,
        position_code=position_code,
        expected_points=breakdown.total,
        breakdown=breakdown,
        evidence_level=evidence_level,
        missing_components=tuple(missing),
        reason_codes=tuple(reasons),
        data_available_at=min(minutes.data_available_at, rates.data_available_at),
        source_hashes=tuple(sorted({*minutes.source_hashes, *rates.source_hashes})),
    )


def _position_points(mapping: Mapping[str, int], position_code: str) -> int:
    """Read a position-keyed scoring value, refusing to default a missing key."""
    if position_code not in mapping:
        raise KeyError(
            f"scoring rules do not define {position_code!r}; "
            "a missing rule must fail rather than default"
        )
    return mapping[position_code]


def _poisson_truncation(rate: float) -> int:
    """Where the tail is safe to drop, for this rate rather than in general.

    A Poisson's spread grows with the square root of its mean, so a fixed cut
    that is generous at rate 1 is severe at rate 20.
    """
    return max(_POISSON_FLOOR, math.ceil(rate + _POISSON_SIGMAS * math.sqrt(rate)))


def _expected_floor_divide(rate: float, divisor: int) -> float:
    """E[floor(X / divisor)] for X ~ Poisson(rate)."""
    if rate <= 0.0:
        return 0.0
    return float(
        sum(
            (count // divisor) * poisson.pmf(count, rate)
            for count in range(_poisson_truncation(rate) + 1)
        )
    )


def _worst(*levels: EvidenceLevel) -> EvidenceLevel:
    return max(levels, key=lambda level: _EVIDENCE_ORDER[level])


def _unavailable(
    *,
    minutes: MinutesProjection,
    rates: PlayerRateProjection,
    position_code: str,
    missing: tuple[str, ...],
    reasons: tuple[str, ...],
) -> ExpectedPointsProjection:
    empty = ExpectedPointsBreakdown(
        appearance=0.0,
        goals=0.0,
        assists=0.0,
        clean_sheet=0.0,
        goals_conceded=0.0,
        saves=0.0,
        bonus=0.0,
        defensive_contribution=0.0,
        cards=0.0,
    )
    return ExpectedPointsProjection(
        element_code=minutes.element_code,
        season=minutes.season,
        event=minutes.event,
        position_code=position_code,
        expected_points=0.0,
        breakdown=empty,
        evidence_level="unavailable",
        missing_components=missing,
        reason_codes=reasons,
        data_available_at=min(minutes.data_available_at, rates.data_available_at),
        source_hashes=tuple(sorted({*minutes.source_hashes, *rates.source_hashes})),
    )


__all__ = [
    "ExpectedPointsBreakdown",
    "ExpectedPointsProjection",
    "TeamMatchContext",
    "project_expected_points",
]
