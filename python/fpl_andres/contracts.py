from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    model_validator,
)
from pydantic.alias_generators import to_camel


class SourceSnapshot(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    source: Literal["fpl", "vaastav", "derived"]
    fetched_at: datetime
    data_available_at: datetime
    content_hash: Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
    upstream_reference: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def validate_chronology(self) -> SourceSnapshot:
        for label, value in (
            ("fetchedAt", self.fetched_at),
            ("dataAvailableAt", self.data_available_at),
        ):
            if value.tzinfo is None or value.utcoffset() != timedelta(0):
                raise ValueError(f"{label} must be an aware UTC timestamp")
        if self.data_available_at > self.fetched_at:
            raise ValueError("dataAvailableAt cannot be later than fetchedAt")
        return self

    @field_serializer("fetched_at", "data_available_at", when_used="json")
    def serialize_utc(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")


def parse_source_snapshot(input_value: object) -> SourceSnapshot:
    if isinstance(input_value, Mapping):
        candidate = dict(input_value)
        hash_key = "contentHash" if "contentHash" in candidate else "content_hash"
        content_hash = candidate.get(hash_key)
        if isinstance(content_hash, str):
            candidate[hash_key] = content_hash.lower()
        return SourceSnapshot.model_validate(candidate)
    return SourceSnapshot.model_validate(input_value)


@dataclass(frozen=True)
class FetchedPayload[PayloadT]:
    payload: PayloadT
    snapshot: SourceSnapshot


EventId = Annotated[int, Field(ge=1, le=38)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class FplEntry(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )

    id: Annotated[int, Field(ge=1, le=4_294_967_295)]
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    started_event: EventId
    current_event: EventId | None
    last_deadline_bank: NonNegativeInt | None
    last_deadline_value: NonNegativeInt | None
    last_deadline_total_transfers: NonNegativeInt


class PublicTeamPick(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )

    element_id: Annotated[int, Field(gt=0)]
    squad_position: Annotated[int, Field(ge=1, le=15)]
    multiplier: Annotated[int, Field(ge=0, le=3)]
    is_captain: bool
    is_vice_captain: bool

    @model_validator(mode="after")
    def validate_roles(self) -> PublicTeamPick:
        if self.is_captain and self.is_vice_captain:
            raise ValueError("a pick cannot be both captain and vice-captain")
        return self


class PublicTeamState(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )

    entry_id: Annotated[int, Field(gt=0)]
    event: EventId
    bank_tenths: NonNegativeInt
    squad_value_tenths: NonNegativeInt
    event_transfers: NonNegativeInt
    event_transfer_cost_points: NonNegativeInt
    total_transfers: NonNegativeInt
    active_chip: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
        ]
        | None
    )
    picks: tuple[PublicTeamPick, ...]
    state_as_of: datetime
    data_available_at: datetime
    evidence_level: Literal["observed"]
    source_hashes: tuple[Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")], ...]

    @model_validator(mode="after")
    def validate_state(self) -> PublicTeamState:
        for label, value in (
            ("stateAsOf", self.state_as_of),
            ("dataAvailableAt", self.data_available_at),
        ):
            if value.tzinfo is None or value.utcoffset() != timedelta(0):
                raise ValueError(f"{label} must be an aware UTC timestamp")
        if self.data_available_at < self.state_as_of:
            raise ValueError("public team evidence cannot predate stateAsOf")
        if len(self.picks) != 15:
            raise ValueError("public team state requires exactly 15 picks")
        if {pick.squad_position for pick in self.picks} != set(range(1, 16)):
            raise ValueError("public team picks must occupy positions 1 through 15")
        if len({pick.element_id for pick in self.picks}) != 15:
            raise ValueError("public team picks must contain 15 distinct elements")
        if sum(pick.is_captain for pick in self.picks) != 1:
            raise ValueError("public team state requires exactly one captain")
        if sum(pick.is_vice_captain for pick in self.picks) != 1:
            raise ValueError("public team state requires exactly one vice-captain")
        if not self.source_hashes:
            raise ValueError("public team state requires source hashes")
        if self.source_hashes != tuple(sorted(set(self.source_hashes))):
            raise ValueError("source hashes must be sorted and unique")
        return self


class ManagerTeamPlayer(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )

    element_id: Annotated[int, Field(gt=0)]
    squad_position: Annotated[int, Field(ge=1, le=15)]
    purchase_price_tenths: NonNegativeInt
    selling_price_tenths: NonNegativeInt


class QueuedTransfer(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )

    element_out_id: Annotated[int, Field(gt=0)]
    element_in_id: Annotated[int, Field(gt=0)]
    selling_price_tenths: NonNegativeInt
    purchase_price_tenths: NonNegativeInt

    @model_validator(mode="after")
    def validate_transfer(self) -> QueuedTransfer:
        if self.element_out_id == self.element_in_id:
            raise ValueError("queued transfer must change the element")
        return self


ChipName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
]


class TeamStateOverrides(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )

    source: Literal["manager"]
    based_on_state_as_of: datetime
    updated_at: datetime
    bank_tenths: NonNegativeInt | None
    available_free_transfers: NonNegativeInt | None
    current_squad: tuple[ManagerTeamPlayer, ...] | None
    queued_transfers: tuple[QueuedTransfer, ...] | None
    available_chips: tuple[ChipName, ...] | None

    @model_validator(mode="after")
    def validate_overrides(self) -> TeamStateOverrides:
        for label, value in (
            ("basedOnStateAsOf", self.based_on_state_as_of),
            ("updatedAt", self.updated_at),
        ):
            if value.tzinfo is None or value.utcoffset() != timedelta(0):
                raise ValueError(f"{label} must be an aware UTC timestamp")
        if self.updated_at < self.based_on_state_as_of:
            raise ValueError("updatedAt cannot predate basedOnStateAsOf")
        if all(
            value is None
            for value in (
                self.bank_tenths,
                self.available_free_transfers,
                self.current_squad,
                self.queued_transfers,
                self.available_chips,
            )
        ):
            raise ValueError("at least one manager override is required")
        if self.current_squad is not None:
            _validate_manager_squad(self.current_squad)
        if self.queued_transfers is not None:
            outgoing = tuple(transfer.element_out_id for transfer in self.queued_transfers)
            incoming = tuple(transfer.element_in_id for transfer in self.queued_transfers)
            if len(set(outgoing)) != len(outgoing) or len(set(incoming)) != len(incoming):
                raise ValueError("queued transfer elements must be unique")
            if set(outgoing) & set(incoming):
                raise ValueError("queued incoming elements cannot already be outgoing")
        if self.available_chips is not None and self.available_chips != tuple(
            sorted(set(self.available_chips))
        ):
            raise ValueError("available chips must be sorted and unique")
        return self


class PlanningTeamState(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )

    entry_id: Annotated[int, Field(gt=0)]
    event: EventId
    bank_tenths: NonNegativeInt
    available_free_transfers: NonNegativeInt
    current_squad: tuple[ManagerTeamPlayer, ...]
    queued_transfers: tuple[QueuedTransfer, ...]
    available_chips: tuple[ChipName, ...]
    public_state_as_of: datetime
    public_data_available_at: datetime
    overrides_updated_at: datetime
    public_source_hashes: tuple[Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")], ...]

    @model_validator(mode="after")
    def validate_planning_state(self) -> PlanningTeamState:
        _validate_manager_squad(self.current_squad)
        for label, value in (
            ("publicStateAsOf", self.public_state_as_of),
            ("publicDataAvailableAt", self.public_data_available_at),
            ("overridesUpdatedAt", self.overrides_updated_at),
        ):
            if value.tzinfo is None or value.utcoffset() != timedelta(0):
                raise ValueError(f"{label} must be an aware UTC timestamp")
        if self.public_data_available_at < self.public_state_as_of:
            raise ValueError("public evidence cannot predate publicStateAsOf")
        if self.overrides_updated_at < self.public_state_as_of:
            raise ValueError("overrides cannot predate publicStateAsOf")
        return self


def _validate_manager_squad(squad: tuple[ManagerTeamPlayer, ...]) -> None:
    if len(squad) != 15:
        raise ValueError("manager current squad requires exactly 15 players")
    if {player.squad_position for player in squad} != set(range(1, 16)):
        raise ValueError("manager current squad must occupy positions 1 through 15")
    if len({player.element_id for player in squad}) != 15:
        raise ValueError("manager current squad must contain 15 distinct elements")
