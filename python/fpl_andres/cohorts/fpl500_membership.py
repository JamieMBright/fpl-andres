"""Immutable event-specific membership for the ranked FPL500 cohort."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from fpl_andres.jsonio import read_json_file

SCHEMA_VERSION = 1
MembershipTiming = Literal["pre-deadline", "at-deadline", "post-deadline"]


@dataclass(frozen=True)
class Fpl500Membership:
    event: int
    deadline: datetime
    source_generated_at: datetime
    source_timing: MembershipTiming
    seconds_from_deadline: int
    source_commit: str
    source_path: str
    source_catalogue_size: int
    pinned_at: datetime
    membership_hash: str
    entry_ids: tuple[int, ...]
    label: str

    @property
    def size(self) -> int:
        return len(self.entry_ids)


def _timestamp(value: object, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must carry a timezone")
    return parsed


def _timing(source_generated_at: datetime, deadline: datetime) -> MembershipTiming:
    if source_generated_at < deadline:
        return "pre-deadline"
    if source_generated_at > deadline:
        return "post-deadline"
    return "at-deadline"


def _label(timing: MembershipTiming) -> str:
    if timing == "post-deadline":
        return "post-deadline capture-era FPL500 membership"
    if timing == "pre-deadline":
        return "pre-deadline FPL500 membership"
    return "at-deadline FPL500 membership"


def _membership_hash(entry_ids: tuple[int, ...]) -> str:
    encoded = "\n".join(str(entry_id) for entry_id in sorted(entry_ids)).encode("ascii")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _validate(membership: Fpl500Membership) -> None:
    if membership.event < 1:
        raise ValueError("membership event must be positive")
    if len(membership.entry_ids) != 500 or len(set(membership.entry_ids)) != 500:
        raise ValueError("FPL500 membership requires exactly 500 unique entry ids")
    if any(isinstance(entry_id, bool) or entry_id < 1 for entry_id in membership.entry_ids):
        raise ValueError("membership entry ids must be positive integers")
    if not re.fullmatch(r"[0-9a-f]{40}", membership.source_commit):
        raise ValueError("membership source commit must be a full lowercase Git SHA")
    if not membership.source_path:
        raise ValueError("membership source path must be named")
    if membership.source_catalogue_size < membership.size:
        raise ValueError("source catalogue cannot be smaller than the pinned membership")
    expected_timing = _timing(membership.source_generated_at, membership.deadline)
    seconds = int((membership.source_generated_at - membership.deadline).total_seconds())
    if membership.source_timing != expected_timing or membership.seconds_from_deadline != seconds:
        raise ValueError("membership timing does not agree with its source timestamps")
    if membership.label != _label(expected_timing):
        raise ValueError("membership label does not agree with its source timing")
    if membership.membership_hash != _membership_hash(membership.entry_ids):
        raise ValueError("membership hash does not agree with its entry ids")


def build_membership(
    source: Mapping[str, object],
    *,
    event: int,
    deadline: datetime,
    source_commit: str,
    source_path: str,
    pinned_at: datetime,
) -> Fpl500Membership:
    """Pin one ranked 500 with the timing and revision that produced it."""
    managers = source.get("managers")
    if not isinstance(managers, list):
        raise ValueError("FPL500 source must contain a managers list")
    entry_ids: list[int] = []
    for row in managers:
        if not isinstance(row, Mapping):
            raise ValueError("FPL500 source managers must be objects")
        entry_id = row.get("entryId")
        if isinstance(entry_id, bool) or not isinstance(entry_id, int):
            raise ValueError("FPL500 source entry ids must be integers")
        entry_ids.append(entry_id)
    declared_size = source.get("size")
    if declared_size != len(entry_ids):
        raise ValueError("FPL500 source size does not agree with its managers")
    catalogue_size = source.get("catalogueSize")
    if isinstance(catalogue_size, bool) or not isinstance(catalogue_size, int):
        raise ValueError("FPL500 source catalogue size must be an integer")
    source_generated_at = _timestamp(source.get("generatedAt"), label="source generatedAt")
    timing = _timing(source_generated_at, deadline)
    membership = Fpl500Membership(
        event=event,
        deadline=deadline,
        source_generated_at=source_generated_at,
        source_timing=timing,
        seconds_from_deadline=int((source_generated_at - deadline).total_seconds()),
        source_commit=source_commit,
        source_path=source_path,
        source_catalogue_size=catalogue_size,
        pinned_at=pinned_at,
        membership_hash=_membership_hash(tuple(entry_ids)),
        entry_ids=tuple(sorted(entry_ids)),
        label=_label(timing),
    )
    _validate(membership)
    return membership


def _payload(membership: Fpl500Membership) -> dict[str, object]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "event": membership.event,
        "label": membership.label,
        "deadline": membership.deadline.isoformat().replace("+00:00", "Z"),
        "sourceGeneratedAt": membership.source_generated_at.isoformat().replace("+00:00", "Z"),
        "sourceTiming": membership.source_timing,
        "secondsFromDeadline": membership.seconds_from_deadline,
        "sourceCommit": membership.source_commit,
        "sourcePath": membership.source_path,
        "sourceCatalogueSize": membership.source_catalogue_size,
        "pinnedAt": membership.pinned_at.isoformat().replace("+00:00", "Z"),
        "size": membership.size,
        "membershipHash": membership.membership_hash,
        "entryIds": list(membership.entry_ids),
    }


def write_membership(membership: Fpl500Membership, output: Path) -> None:
    """Write once: changing membership later would rewrite observed history."""
    if output.exists():
        raise FileExistsError(f"refusing to overwrite immutable membership {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(_payload(membership), indent=2) + "\n", encoding="utf-8")


def read_membership(path: Path) -> Fpl500Membership:
    raw = read_json_file(path)
    if not isinstance(raw, dict) or raw.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(f"unsupported FPL500 membership schema in {path}")
    entry_ids = raw.get("entryIds")
    if not isinstance(entry_ids, list) or any(
        isinstance(entry_id, bool) or not isinstance(entry_id, int) for entry_id in entry_ids
    ):
        raise ValueError(f"membership entryIds must be integers in {path}")
    timing = raw.get("sourceTiming")
    if timing not in ("pre-deadline", "at-deadline", "post-deadline"):
        raise ValueError(f"unsupported membership source timing in {path}")
    membership = Fpl500Membership(
        event=int(raw["event"]),
        deadline=_timestamp(raw.get("deadline"), label="deadline"),
        source_generated_at=_timestamp(raw.get("sourceGeneratedAt"), label="sourceGeneratedAt"),
        source_timing=timing,
        seconds_from_deadline=int(raw["secondsFromDeadline"]),
        source_commit=str(raw["sourceCommit"]),
        source_path=str(raw["sourcePath"]),
        source_catalogue_size=int(raw["sourceCatalogueSize"]),
        pinned_at=_timestamp(raw.get("pinnedAt"), label="pinnedAt"),
        membership_hash=str(raw["membershipHash"]),
        entry_ids=tuple(entry_ids),
        label=str(raw["label"]),
    )
    if raw.get("size") != membership.size:
        raise ValueError(f"membership size does not agree with entryIds in {path}")
    _validate(membership)
    return membership


__all__ = [
    "Fpl500Membership",
    "build_membership",
    "read_membership",
    "write_membership",
]
