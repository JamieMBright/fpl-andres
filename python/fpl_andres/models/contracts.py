from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fpl_andres.timeguard import require_utc

EvidenceLevel = Literal["observed", "inferred", "experimental", "unavailable"]


class FixtureResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    season: Annotated[str, Field(pattern=r"^20[0-9]{2}-[0-9]{2}$")]
    event: Annotated[int, Field(ge=1, le=38)]
    home_team_id: Annotated[int, Field(gt=0)]
    away_team_id: Annotated[int, Field(gt=0)]
    home_goals: Annotated[int, Field(ge=0)]
    away_goals: Annotated[int, Field(ge=0)]
    kickoff_time: datetime
    data_available_at: datetime
    source_hash: Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]

    @model_validator(mode="after")
    def validate_fixture(self) -> FixtureResult:
        if self.home_team_id == self.away_team_id:
            raise ValueError("home and away teams must differ")
        for label, value in (
            ("kickoff_time", self.kickoff_time),
            ("data_available_at", self.data_available_at),
        ):
            require_utc(value, label)
        if self.data_available_at <= self.kickoff_time:
            raise ValueError("result data must become available after kickoff")
        return self


class TeamGoalPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    season: Annotated[str, Field(pattern=r"^20[0-9]{2}-[0-9]{2}$")]
    event: Annotated[int, Field(ge=1, le=38)]
    home_team_id: Annotated[int, Field(gt=0)]
    away_team_id: Annotated[int, Field(gt=0)]
    home_expected_goals: Annotated[float, Field(ge=0)]
    away_expected_goals: Annotated[float, Field(ge=0)]
    evidence_level: EvidenceLevel
    reason_codes: tuple[str, ...]
    data_available_at: datetime
    source_hashes: tuple[str, ...]
