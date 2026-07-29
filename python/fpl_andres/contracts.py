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
