from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from pydantic import ValidationError

from fpl_andres.contracts import (
    FplEntry,
    PlanningTeamState,
    PublicTeamPick,
    PublicTeamState,
    SourceSnapshot,
    TeamStateOverrides,
)


class TeamStateContractError(ValueError):
    """Raised when public entry evidence cannot form a safe planning snapshot."""


class TeamStateResolutionError(ValueError):
    """Raised when manager overrides cannot produce exact current planning state."""


def normalize_public_team_state(
    entry: FplEntry,
    picks_payload: Mapping[str, Any],
    *,
    state_as_of: datetime,
    entry_snapshot: SourceSnapshot,
    picks_snapshot: SourceSnapshot,
) -> PublicTeamState:
    if state_as_of.tzinfo is None or state_as_of.utcoffset() != timedelta(0):
        raise TeamStateContractError("state_as_of must be an aware UTC timestamp")
    if entry.current_event is None:
        raise TeamStateContractError("entry has no processed event")
    if entry.last_deadline_bank is None or entry.last_deadline_value is None:
        raise TeamStateContractError("entry has no public last-deadline bank or value")

    event = entry.current_event
    _require_snapshot(
        entry_snapshot,
        label="entry",
        expected_reference=f"https://fantasy.premierleague.com/api/entry/{entry.id}/",
    )
    _require_snapshot(
        picks_snapshot,
        label="picks",
        expected_reference=(
            f"https://fantasy.premierleague.com/api/entry/{entry.id}/event/{event}/picks/"
        ),
    )

    history = _required_mapping(picks_payload, "entry_history")
    history_event = _required_value(history, "event")
    history_bank = _required_value(history, "bank")
    history_value = _required_value(history, "value")
    if history_event != event:
        raise TeamStateContractError("entry and picks event disagree")
    if history_bank != entry.last_deadline_bank:
        raise TeamStateContractError("entry and picks bank disagree")
    if history_value != entry.last_deadline_value:
        raise TeamStateContractError("entry and picks value disagree")

    raw_picks = _required_value(picks_payload, "picks")
    if not isinstance(raw_picks, list):
        raise TeamStateContractError("picks must be an array")
    normalized_picks: list[PublicTeamPick] = []
    try:
        for raw_pick in raw_picks:
            if not isinstance(raw_pick, Mapping):
                raise TeamStateContractError("each pick must be an object")
            normalized_picks.append(
                PublicTeamPick.model_validate(
                    {
                        "elementId": _required_value(raw_pick, "element"),
                        "squadPosition": _required_value(raw_pick, "position"),
                        "multiplier": _required_value(raw_pick, "multiplier"),
                        "isCaptain": _required_value(raw_pick, "is_captain"),
                        "isViceCaptain": _required_value(raw_pick, "is_vice_captain"),
                    }
                )
            )
        return PublicTeamState(
            entry_id=entry.id,
            event=event,
            bank_tenths=entry.last_deadline_bank,
            squad_value_tenths=entry.last_deadline_value,
            event_transfers=_required_value(history, "event_transfers"),
            event_transfer_cost_points=_required_value(history, "event_transfers_cost"),
            total_transfers=entry.last_deadline_total_transfers,
            active_chip=_required_value(picks_payload, "active_chip"),
            picks=tuple(normalized_picks),
            state_as_of=state_as_of,
            data_available_at=max(
                entry_snapshot.data_available_at,
                picks_snapshot.data_available_at,
            ),
            evidence_level="observed",
            source_hashes=tuple(sorted({entry_snapshot.content_hash, picks_snapshot.content_hash})),
        )
    except ValidationError as error:
        raise TeamStateContractError(f"invalid public team state: {error}") from error


def resolve_team_state(
    public: PublicTeamState,
    overrides: TeamStateOverrides,
) -> PlanningTeamState:
    if overrides.based_on_state_as_of != public.state_as_of:
        raise TeamStateResolutionError("manager overrides target a different public deadline")
    current_squad = _required_override(overrides.current_squad, "current_squad")
    available_free_transfers = _required_override(
        overrides.available_free_transfers,
        "available_free_transfers",
    )
    queued_transfers = _required_override(overrides.queued_transfers, "queued_transfers")
    available_chips = _required_override(overrides.available_chips, "available_chips")

    public_elements = {pick.element_id for pick in public.picks}
    outgoing = {transfer.element_out_id for transfer in queued_transfers}
    incoming = {transfer.element_in_id for transfer in queued_transfers}
    if not outgoing <= public_elements or incoming & public_elements:
        raise TeamStateResolutionError("queued transfers do not start from the public squad")
    expected_current_elements = (public_elements - outgoing) | incoming
    current_elements = {player.element_id for player in current_squad}
    if current_elements != expected_current_elements:
        raise TeamStateResolutionError("current squad does not reconcile with queued transfers")

    expected_bank = public.bank_tenths + sum(
        transfer.selling_price_tenths - transfer.purchase_price_tenths
        for transfer in queued_transfers
    )
    if expected_bank < 0:
        raise TeamStateResolutionError("queued transfers make the bank negative")
    bank = expected_bank if overrides.bank_tenths is None else overrides.bank_tenths
    if bank != expected_bank:
        raise TeamStateResolutionError(
            "manager bank does not reconcile with queued transfer prices"
        )

    current_by_element = {player.element_id: player for player in current_squad}
    for transfer in queued_transfers:
        if (
            current_by_element[transfer.element_in_id].purchase_price_tenths
            != transfer.purchase_price_tenths
        ):
            raise TeamStateResolutionError(
                "incoming player purchase price does not match queued transfer"
            )

    return PlanningTeamState(
        entry_id=public.entry_id,
        event=public.event,
        bank_tenths=bank,
        available_free_transfers=available_free_transfers,
        current_squad=current_squad,
        queued_transfers=queued_transfers,
        available_chips=available_chips,
        public_state_as_of=public.state_as_of,
        public_data_available_at=public.data_available_at,
        overrides_updated_at=overrides.updated_at,
        manager_overrides_hash=_manager_overrides_hash(overrides),
        public_source_hashes=public.source_hashes,
    )


def _require_snapshot(
    snapshot: SourceSnapshot,
    *,
    label: str,
    expected_reference: str,
) -> None:
    if snapshot.source != "fpl" or snapshot.upstream_reference != expected_reference:
        raise TeamStateContractError(f"{label} source does not match the requested team state")


def _required_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = _required_value(payload, key)
    if not isinstance(value, Mapping):
        raise TeamStateContractError(f"{key} must be an object")
    return value


def _required_value(payload: Mapping[str, Any], key: str) -> Any:
    if key not in payload:
        raise TeamStateContractError(f"picks payload is missing required field: {key}")
    return payload[key]


def _required_override[ValueT](value: ValueT | None, field_name: str) -> ValueT:
    if value is None:
        raise TeamStateResolutionError(f"manager override must provide {field_name}")
    return value


def _manager_overrides_hash(overrides: TeamStateOverrides) -> str:
    canonical = json.dumps(
        overrides.model_dump(by_alias=True, mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"
