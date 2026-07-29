from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from fpl_andres.rules import RulesSnapshot

Hash = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class PositionConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    position_id: PositiveInt
    squad_count: PositiveInt
    lineup_minimum: NonNegativeInt
    lineup_maximum: NonNegativeInt

    @model_validator(mode="after")
    def validate_position(self) -> PositionConstraint:
        if self.lineup_minimum > self.lineup_maximum:
            raise ValueError("lineup minimum cannot exceed maximum")
        if self.lineup_maximum > self.squad_count:
            raise ValueError("lineup maximum cannot exceed squad count")
        return self


class TransferRulesAddendum(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    season: Annotated[str, Field(pattern=r"^20[0-9]{2}-[0-9]{2}$")]
    weekly_free_transfers: PositiveInt
    maximum_free_transfers: PositiveInt
    transfer_cost_points: PositiveInt
    source_reference: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    source_hash: Hash
    data_available_at: datetime

    @model_validator(mode="after")
    def validate_addendum(self) -> TransferRulesAddendum:
        _require_utc(self.data_available_at, "data_available_at")
        if self.maximum_free_transfers < self.weekly_free_transfers:
            raise ValueError("maximum free transfers cannot be below the weekly award")
        return self


class OptimizationRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    season: Annotated[str, Field(pattern=r"^20[0-9]{2}-[0-9]{2}$")]
    squad_size: PositiveInt
    lineup_size: Annotated[int, Field(ge=2)]
    club_limit: PositiveInt
    transfer_cap: PositiveInt
    positions: tuple[PositionConstraint, ...]
    transfer_rules: TransferRulesAddendum
    published_rules_hash: Hash
    data_available_at: datetime

    @model_validator(mode="after")
    def validate_rules(self) -> OptimizationRules:
        _require_utc(self.data_available_at, "data_available_at")
        if self.transfer_rules.season != self.season:
            raise ValueError("published and transfer rules must have the same season")
        if self.data_available_at < self.transfer_rules.data_available_at:
            raise ValueError("rules availability cannot predate the transfer addendum")
        if not self.positions:
            raise ValueError("at least one position constraint is required")
        if len({position.position_id for position in self.positions}) != len(self.positions):
            raise ValueError("position constraints must have unique IDs")
        if sum(position.squad_count for position in self.positions) != self.squad_size:
            raise ValueError("position squad counts must equal squad size")
        if sum(position.lineup_minimum for position in self.positions) > self.lineup_size:
            raise ValueError("lineup minimums exceed lineup size")
        if sum(position.lineup_maximum for position in self.positions) < self.lineup_size:
            raise ValueError("lineup maximums cannot fill lineup size")
        return self


class OptimizationPlayer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    season: Annotated[str, Field(pattern=r"^20[0-9]{2}-[0-9]{2}$")]
    event: Annotated[int, Field(ge=1, le=38)]
    element_id: PositiveInt
    team_id: PositiveInt
    position_id: PositiveInt
    buy_price_tenths: NonNegativeInt
    expected_points: float
    evidence_level: Literal["inferred", "experimental"]
    model_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    model_version: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    data_available_at: datetime
    source_hashes: tuple[Hash, ...]

    @model_validator(mode="after")
    def validate_player(self) -> OptimizationPlayer:
        _require_utc(self.data_available_at, "data_available_at")
        if not math.isfinite(self.expected_points):
            raise ValueError("expected_points must be finite")
        _require_sorted_hashes(self.source_hashes)
        return self


class CurrentSquadPlayer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    element_id: PositiveInt
    selling_price_tenths: NonNegativeInt


class OptimizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    event: Annotated[int, Field(ge=1, le=38)]
    prediction_cutoff: datetime
    players: tuple[OptimizationPlayer, ...]
    current_squad: tuple[CurrentSquadPlayer, ...]
    bank_tenths: NonNegativeInt
    available_free_transfers: NonNegativeInt
    rules: OptimizationRules

    @model_validator(mode="after")
    def validate_request(self) -> OptimizationRequest:
        _require_utc(self.prediction_cutoff, "prediction_cutoff")
        if self.rules.data_available_at > self.prediction_cutoff:
            raise ValueError("rules became available after prediction_cutoff")
        if len(self.players) < self.rules.squad_size:
            raise ValueError("candidate pool is smaller than the required squad")
        player_ids = tuple(player.element_id for player in self.players)
        if len(set(player_ids)) != len(player_ids):
            raise ValueError("candidate elements must be unique")
        if any(
            player.season != self.rules.season or player.event != self.event
            for player in self.players
        ):
            raise ValueError("candidate forecasts must match request season and event")
        if any(player.data_available_at > self.prediction_cutoff for player in self.players):
            raise ValueError("candidate forecast became available after prediction_cutoff")
        position_ids = {position.position_id for position in self.rules.positions}
        if any(player.position_id not in position_ids for player in self.players):
            raise ValueError("candidate has a position absent from optimizer rules")
        current_ids = tuple(player.element_id for player in self.current_squad)
        if len(current_ids) != self.rules.squad_size or len(set(current_ids)) != len(current_ids):
            raise ValueError("current squad must contain the required number of unique elements")
        if not set(current_ids) <= set(player_ids):
            raise ValueError("every current squad element requires a candidate forecast")
        if self.available_free_transfers > self.rules.transfer_rules.maximum_free_transfers:
            raise ValueError("available free transfers exceed the sourced season maximum")
        return self


class OptimizationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    solver: Literal["scipy-highs"]
    solver_status: Literal["optimal"]
    squad_element_ids: tuple[int, ...]
    starter_element_ids: tuple[int, ...]
    bench_element_ids: tuple[int, ...]
    captain_element_id: PositiveInt
    vice_captain_element_id: PositiveInt
    transfers_in: tuple[int, ...]
    transfers_out: tuple[int, ...]
    paid_transfers: NonNegativeInt
    transfer_cost_points: NonNegativeInt
    projected_points_before_cost: float
    net_expected_points: float
    bank_after_tenths: NonNegativeInt
    evidence_level: Literal["inferred", "experimental"]
    data_available_at: datetime
    source_hashes: tuple[Hash, ...]
    reason_codes: tuple[str, ...]

    @model_validator(mode="after")
    def validate_result(self) -> OptimizationResult:
        _require_utc(self.data_available_at, "data_available_at")
        _require_sorted_hashes(self.source_hashes)
        squad = set(self.squad_element_ids)
        starters = set(self.starter_element_ids)
        bench = set(self.bench_element_ids)
        if len(squad) != len(self.squad_element_ids):
            raise ValueError("squad elements must be unique")
        if len(starters) != len(self.starter_element_ids) or len(bench) != len(
            self.bench_element_ids
        ):
            raise ValueError("starter and bench elements must be unique")
        if starters & bench or starters | bench != squad:
            raise ValueError("starters and bench must partition the squad")
        if len(starters) < 2:
            raise ValueError("at least two starters are required")
        if (
            self.captain_element_id not in starters
            or self.vice_captain_element_id not in starters
            or self.captain_element_id == self.vice_captain_element_id
        ):
            raise ValueError("captain and vice-captain must be distinct starters")
        incoming = set(self.transfers_in)
        outgoing = set(self.transfers_out)
        if (
            len(incoming) != len(self.transfers_in)
            or len(outgoing) != len(self.transfers_out)
            or incoming & outgoing
            or len(incoming) != len(outgoing)
        ):
            raise ValueError("transfers must be unique, disjoint and balanced")
        if self.paid_transfers > len(incoming):
            raise ValueError("paid transfers cannot exceed total transfers")
        if not math.isfinite(self.projected_points_before_cost) or not math.isfinite(
            self.net_expected_points
        ):
            raise ValueError("optimizer point totals must be finite")
        if not math.isclose(
            self.net_expected_points,
            self.projected_points_before_cost - self.transfer_cost_points,
            abs_tol=1e-8,
        ):
            raise ValueError("net expected points must include the transfer cost")
        if not self.reason_codes:
            raise ValueError("optimizer result requires reason codes")
        return self


class OptimizerPort(Protocol):
    def solve(self, request: OptimizationRequest) -> OptimizationResult: ...


def optimization_rules_from_snapshot(
    published: RulesSnapshot,
    *,
    transfer_rules: TransferRulesAddendum,
    published_data_available_at: datetime,
) -> OptimizationRules:
    if transfer_rules.season != published.season:
        raise ValueError("published and transfer rules must have the same season")
    if transfer_rules.weekly_free_transfers != published.weekly_free_transfers:
        raise ValueError("weekly free-transfer rules disagree between sources")
    if transfer_rules.maximum_free_transfers != published.max_free_transfers:
        raise ValueError("maximum free-transfer rules disagree between sources")
    return OptimizationRules(
        season=published.season,
        squad_size=published.squad_size,
        lineup_size=published.starting_size,
        club_limit=published.club_limit,
        transfer_cap=published.transfer_cap,
        positions=tuple(
            PositionConstraint(
                position_id=position.id,
                squad_count=position.squad_count,
                lineup_minimum=position.minimum_start,
                lineup_maximum=position.maximum_start,
            )
            for position in sorted(
                published.positions.values(),
                key=lambda position: position.id,
            )
        ),
        transfer_rules=transfer_rules,
        published_rules_hash=published.source_hash,
        data_available_at=max(
            published_data_available_at,
            transfer_rules.data_available_at,
        ),
    )


def _require_utc(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be an aware UTC timestamp")


def _require_sorted_hashes(hashes: tuple[str, ...]) -> None:
    if not hashes:
        raise ValueError("at least one source hash is required")
    if hashes != tuple(sorted(set(hashes))):
        raise ValueError("source hashes must be sorted and unique")
