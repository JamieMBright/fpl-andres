from __future__ import annotations

import math
from datetime import datetime
from itertools import pairwise
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from fpl_andres.contracts import PlanningTeamState
from fpl_andres.rules import RulesSnapshot
from fpl_andres.timeguard import require_utc

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
    # Bounded, not merely positive: a wrong id splits one club into two groups
    # in the three-per-club constraint, and each group gets its own allowance.
    team_id: Annotated[int, Field(ge=1, le=20)]
    position_id: PositiveInt
    buy_price_tenths: NonNegativeInt
    expected_points: float
    # What the same match is worth on his best afternoon. Defaults to the mean,
    # which claims no upside, so a caller who has not measured one is not
    # silently given one.
    expected_ceiling: float | None = None
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
        if self.expected_ceiling is not None:
            if not math.isfinite(self.expected_ceiling):
                raise ValueError("expected_ceiling must be finite")
            if self.expected_ceiling < self.expected_points:
                raise ValueError("a ceiling below the mean is not a ceiling")
        _require_sorted_hashes(self.source_hashes)
        return self


class CurrentSquadPlayer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    element_id: PositiveInt
    selling_price_tenths: NonNegativeInt


class OptimizationStateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    public_state_as_of: datetime
    public_data_available_at: datetime
    overrides_updated_at: datetime
    public_source_hashes: tuple[Hash, ...]
    manager_overrides_hash: Hash

    @model_validator(mode="after")
    def validate_evidence(self) -> OptimizationStateEvidence:
        for label, value in (
            ("public_state_as_of", self.public_state_as_of),
            ("public_data_available_at", self.public_data_available_at),
            ("overrides_updated_at", self.overrides_updated_at),
        ):
            _require_utc(value, label)
        if self.public_data_available_at < self.public_state_as_of:
            raise ValueError("public data cannot predate public state")
        if self.overrides_updated_at < self.public_state_as_of:
            raise ValueError("manager overrides cannot predate public state")
        _require_sorted_hashes(self.public_source_hashes)
        return self


class OptimizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    event: Annotated[int, Field(ge=1, le=38)]
    prediction_cutoff: datetime
    objective: Literal["expected_value"]
    price_scenario: Literal["current_prices"]
    chip_scenario: Literal["none"]
    players: tuple[OptimizationPlayer, ...]
    current_squad: tuple[CurrentSquadPlayer, ...]
    bank_tenths: NonNegativeInt
    available_free_transfers: NonNegativeInt
    state_evidence: OptimizationStateEvidence
    rules: OptimizationRules

    @model_validator(mode="after")
    def validate_request(self) -> OptimizationRequest:
        _require_utc(self.prediction_cutoff, "prediction_cutoff")
        if self.rules.data_available_at > self.prediction_cutoff:
            raise ValueError("rules became available after prediction_cutoff")
        if self.state_evidence.public_data_available_at > self.prediction_cutoff:
            raise ValueError("public team state became available after prediction_cutoff")
        if self.state_evidence.overrides_updated_at > self.prediction_cutoff:
            raise ValueError("manager state became available after prediction_cutoff")
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
    objective: Literal["expected_value"]
    price_scenario: Literal["current_prices"]
    chip_scenario: Literal["none"]
    squad_element_ids: tuple[int, ...]
    starter_element_ids: tuple[int, ...]
    bench_element_ids: tuple[int, ...]
    captain_element_id: PositiveInt
    vice_captain_element_id: PositiveInt
    transfers_in: tuple[int, ...]
    transfers_out: tuple[int, ...]
    # Carried onto the result so a reader can tell a deliberate hit from a plan
    # that had no free transfer to spend. Both produce paid_transfers > 0.
    free_transfers_available: NonNegativeInt
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
        expected_paid = max(0, len(incoming) - self.free_transfers_available)
        if self.paid_transfers != expected_paid:
            raise ValueError(
                f"paid transfers ({self.paid_transfers}) must be the transfers beyond "
                f"the free allowance ({expected_paid} from {len(incoming)} transfers "
                f"and {self.free_transfers_available} free)"
            )
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


class HorizonPlayerForecast(OptimizationPlayer):
    sell_price_tenths: NonNegativeInt


class HorizonEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    event: Annotated[int, Field(ge=1, le=38)]
    prediction_cutoff: datetime
    objective_weight: float

    @model_validator(mode="after")
    def validate_event(self) -> HorizonEvent:
        _require_utc(self.prediction_cutoff, "prediction_cutoff")
        if not math.isfinite(self.objective_weight) or self.objective_weight <= 0:
            raise ValueError("objective_weight must be finite and positive")
        return self


class HorizonOptimizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    events: tuple[HorizonEvent, ...]
    forecasts: tuple[HorizonPlayerForecast, ...]
    current_squad: tuple[CurrentSquadPlayer, ...]
    bank_tenths: NonNegativeInt
    available_free_transfers: NonNegativeInt
    state_evidence: OptimizationStateEvidence
    price_scenario: Literal["provided_event_prices"]
    objective: Literal["expected_value"]
    chip_scenario: Literal["none"]
    rules: OptimizationRules

    @model_validator(mode="after")
    def validate_horizon(self) -> HorizonOptimizationRequest:
        if len(self.events) < 2:
            raise ValueError("rolling optimization requires at least two events")
        if any(
            current.event >= following.event
            or current.prediction_cutoff >= following.prediction_cutoff
            for current, following in pairwise(self.events)
        ):
            raise ValueError("horizon events and cutoffs must be strictly increasing")
        if self.available_free_transfers > self.rules.transfer_rules.maximum_free_transfers:
            raise ValueError("available free transfers exceed the sourced season maximum")
        event_by_id = {event.event: event for event in self.events}
        if len(event_by_id) != len(self.events):
            raise ValueError("horizon event IDs must be unique")
        if self.rules.data_available_at > self.events[0].prediction_cutoff:
            raise ValueError("rules became available after the first prediction cutoff")
        if self.state_evidence.public_data_available_at > self.events[0].prediction_cutoff:
            raise ValueError("public team state became available after the first cutoff")
        if self.state_evidence.overrides_updated_at > self.events[0].prediction_cutoff:
            raise ValueError("manager state became available after the first cutoff")

        forecasts_by_event: dict[int, list[HorizonPlayerForecast]] = {
            event.event: [] for event in self.events
        }
        for forecast in self.forecasts:
            event = event_by_id.get(forecast.event)
            if event is None:
                raise ValueError("forecast event is outside the optimization horizon")
            if forecast.data_available_at > event.prediction_cutoff:
                raise ValueError("forecast became available after its prediction cutoff")
            if forecast.season != self.rules.season:
                raise ValueError("forecast season must match optimizer rules")
            forecasts_by_event[forecast.event].append(forecast)

        first_event = self.events[0].event
        first_ids = tuple(
            sorted(forecast.element_id for forecast in forecasts_by_event[first_event])
        )
        if len(first_ids) < self.rules.squad_size or len(set(first_ids)) != len(first_ids):
            raise ValueError("each event requires a unique candidate pool large enough for a squad")
        identity = {
            forecast.element_id: (forecast.team_id, forecast.position_id)
            for forecast in forecasts_by_event[first_event]
        }
        for event in self.events[1:]:
            event_forecasts = forecasts_by_event[event.event]
            event_ids = tuple(sorted(forecast.element_id for forecast in event_forecasts))
            if event_ids != first_ids:
                raise ValueError("all horizon events must contain the same candidate elements")
            if any(
                identity[forecast.element_id] != (forecast.team_id, forecast.position_id)
                for forecast in event_forecasts
            ):
                raise ValueError(
                    "candidate team and position must remain stable across the horizon"
                )

        current_ids = tuple(player.element_id for player in self.current_squad)
        if len(current_ids) != self.rules.squad_size or len(set(current_ids)) != len(current_ids):
            raise ValueError("current squad must contain the required number of unique elements")
        if not set(current_ids) <= set(first_ids):
            raise ValueError("every current squad element requires horizon forecasts")
        first_forecasts = {
            forecast.element_id: forecast for forecast in forecasts_by_event[first_event]
        }
        if any(
            first_forecasts[player.element_id].sell_price_tenths != player.selling_price_tenths
            for player in self.current_squad
        ):
            raise ValueError("first-event sell prices must match current squad selling prices")
        return self

    def first_event_request(self) -> OptimizationRequest:
        first_event = self.events[0]
        return OptimizationRequest(
            event=first_event.event,
            prediction_cutoff=first_event.prediction_cutoff,
            objective="expected_value",
            price_scenario="current_prices",
            chip_scenario=self.chip_scenario,
            players=tuple(
                OptimizationPlayer.model_validate(
                    forecast.model_dump(exclude={"sell_price_tenths"})
                )
                for forecast in self.forecasts
                if forecast.event == first_event.event
            ),
            current_squad=self.current_squad,
            bank_tenths=self.bank_tenths,
            available_free_transfers=self.available_free_transfers,
            state_evidence=self.state_evidence,
            rules=self.rules,
        )


class HorizonEventPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    event: Annotated[int, Field(ge=1, le=38)]
    objective_weight: float
    squad_element_ids: tuple[int, ...]
    starter_element_ids: tuple[int, ...]
    bench_element_ids: tuple[int, ...]
    captain_element_id: PositiveInt
    vice_captain_element_id: PositiveInt
    transfers_in: tuple[int, ...]
    transfers_out: tuple[int, ...]
    free_transfers_before: NonNegativeInt
    free_transfers_used: NonNegativeInt
    paid_transfers: NonNegativeInt
    free_transfers_next_event: NonNegativeInt
    transfer_cost_points: NonNegativeInt
    projected_points_before_cost: float
    net_expected_points: float
    bank_after_tenths: NonNegativeInt

    @model_validator(mode="after")
    def validate_plan(self) -> HorizonEventPlan:
        squad = set(self.squad_element_ids)
        starters = set(self.starter_element_ids)
        bench = set(self.bench_element_ids)
        if starters & bench or starters | bench != squad:
            raise ValueError("starters and bench must partition the event squad")
        if (
            self.captain_element_id not in starters
            or self.vice_captain_element_id not in starters
            or self.captain_element_id == self.vice_captain_element_id
        ):
            raise ValueError("captain and vice-captain must be distinct starters")
        if len(self.transfers_in) != len(self.transfers_out):
            raise ValueError("event transfers must balance")
        if self.free_transfers_used + self.paid_transfers != len(self.transfers_in):
            raise ValueError("free and paid transfers must account for all transfers")
        if self.free_transfers_used > self.free_transfers_before:
            raise ValueError("used free transfers cannot exceed the available balance")
        if not math.isclose(
            self.net_expected_points,
            self.projected_points_before_cost - self.transfer_cost_points,
            abs_tol=1e-8,
        ):
            raise ValueError("event net points must include transfer cost")
        return self


class HorizonOptimizationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    solver: Literal["scipy-highs"]
    solver_status: Literal["optimal"]
    objective: Literal["expected_value"]
    price_scenario: Literal["provided_event_prices"]
    chip_scenario: Literal["none"]
    events: tuple[HorizonEventPlan, ...]
    weighted_net_expected_points: float
    evidence_level: Literal["inferred", "experimental"]
    data_available_at: datetime
    source_hashes: tuple[Hash, ...]
    reason_codes: tuple[str, ...]

    @model_validator(mode="after")
    def validate_result(self) -> HorizonOptimizationResult:
        _require_utc(self.data_available_at, "data_available_at")
        _require_sorted_hashes(self.source_hashes)
        if not self.events:
            raise ValueError("horizon result requires event plans")
        if any(current.event >= following.event for current, following in pairwise(self.events)):
            raise ValueError("horizon result events must be strictly increasing")
        expected_total = sum(
            event.objective_weight * event.net_expected_points for event in self.events
        )
        if not math.isclose(
            self.weighted_net_expected_points,
            expected_total,
            abs_tol=1e-7,
        ):
            raise ValueError("weighted horizon total must match the event plans")
        if not self.reason_codes:
            raise ValueError("horizon result requires reason codes")
        acquired: set[int] = set()
        for event in self.events:
            if acquired & set(event.transfers_out):
                raise ValueError("horizon cannot resell a player acquired inside the plan")
            acquired.update(event.transfers_in)
        return self


class OptimizerPort(Protocol):
    def solve(self, request: OptimizationRequest) -> OptimizationResult: ...


def optimization_state_evidence_from_team_state(
    state: PlanningTeamState,
) -> OptimizationStateEvidence:
    return OptimizationStateEvidence(
        public_state_as_of=state.public_state_as_of,
        public_data_available_at=state.public_data_available_at,
        overrides_updated_at=state.overrides_updated_at,
        public_source_hashes=state.public_source_hashes,
        manager_overrides_hash=state.manager_overrides_hash,
    )


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
    require_utc(value, label)


def _require_sorted_hashes(hashes: tuple[str, ...]) -> None:
    if not hashes:
        raise ValueError("at least one source hash is required")
    if hashes != tuple(sorted(set(hashes))):
        raise ValueError("source hashes must be sorted and unique")


__all__ = [
    "CurrentSquadPlayer",
    "Hash",
    "HorizonEvent",
    "HorizonEventPlan",
    "HorizonOptimizationRequest",
    "HorizonOptimizationResult",
    "HorizonPlayerForecast",
    "NonNegativeInt",
    "OptimizationPlayer",
    "OptimizationRequest",
    "OptimizationResult",
    "OptimizationRules",
    "OptimizationStateEvidence",
    "OptimizerPort",
    "PositionConstraint",
    "PositiveInt",
    "TransferRulesAddendum",
    "optimization_rules_from_snapshot",
    "optimization_state_evidence_from_team_state",
]
