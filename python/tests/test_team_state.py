from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from fpl_andres.contracts import FplEntry, SourceSnapshot
from fpl_andres.team_state import TeamStateContractError, normalize_public_team_state

STATE_AS_OF = datetime(2026, 9, 12, 10, 30, tzinfo=UTC)
FETCHED_AT = STATE_AS_OF + timedelta(hours=2)


def snapshot(path: str, hash_digit: str) -> SourceSnapshot:
    return SourceSnapshot(
        source="fpl",
        fetched_at=FETCHED_AT,
        data_available_at=FETCHED_AT,
        content_hash=f"sha256:{hash_digit * 64}",
        upstream_reference=f"https://fantasy.premierleague.com/api/{path}",
    )


def entry() -> FplEntry:
    return FplEntry(
        id=123,
        name="Public XI",
        started_event=1,
        current_event=5,
        last_deadline_bank=17,
        last_deadline_value=1_004,
        last_deadline_total_transfers=4,
    )


def picks_payload() -> dict[str, object]:
    picks = [
        {
            "element": element_id,
            "position": position,
            "multiplier": 0 if position > 11 else 1,
            "is_captain": False,
            "is_vice_captain": False,
        }
        for position, element_id in enumerate(range(101, 116), start=1)
    ]
    picks[0]["multiplier"] = 2
    picks[0]["is_captain"] = True
    picks[1]["is_vice_captain"] = True
    return {
        "active_chip": None,
        "entry_history": {
            "event": 5,
            "bank": 17,
            "value": 1_004,
            "event_transfers": 1,
            "event_transfers_cost": 0,
        },
        "picks": picks,
    }


def test_public_state_preserves_deadline_evidence_without_private_guesses() -> None:
    state = normalize_public_team_state(
        entry(),
        picks_payload(),
        state_as_of=STATE_AS_OF,
        entry_snapshot=snapshot("entry/123/", "a"),
        picks_snapshot=snapshot("entry/123/event/5/picks/", "b"),
    )

    assert state.entry_id == 123
    assert state.event == 5
    assert state.bank_tenths == 17
    assert state.squad_value_tenths == 1_004
    assert state.event_transfers == 1
    assert state.event_transfer_cost_points == 0
    assert state.state_as_of == STATE_AS_OF
    assert state.data_available_at == FETCHED_AT
    assert state.evidence_level == "observed"
    assert state.source_hashes == (f"sha256:{'a' * 64}", f"sha256:{'b' * 64}")
    assert len(state.picks) == 15

    public_fields = state.model_dump()
    assert "available_free_transfers" not in public_fields
    assert "purchase_price_tenths" not in public_fields["picks"][0]
    assert "selling_price_tenths" not in public_fields["picks"][0]


def test_public_state_rejects_entry_and_picks_disagreement() -> None:
    payload = picks_payload()
    history = payload["entry_history"]
    assert isinstance(history, dict)
    history["bank"] = 18

    with pytest.raises(TeamStateContractError, match="bank"):
        normalize_public_team_state(
            entry(),
            payload,
            state_as_of=STATE_AS_OF,
            entry_snapshot=snapshot("entry/123/", "a"),
            picks_snapshot=snapshot("entry/123/event/5/picks/", "b"),
        )


def test_public_state_rejects_invalid_squad_or_misassociated_source() -> None:
    missing_pick = deepcopy(picks_payload())
    picks = missing_pick["picks"]
    assert isinstance(picks, list)
    picks.pop()

    with pytest.raises(TeamStateContractError, match="15 picks"):
        normalize_public_team_state(
            entry(),
            missing_pick,
            state_as_of=STATE_AS_OF,
            entry_snapshot=snapshot("entry/123/", "a"),
            picks_snapshot=snapshot("entry/123/event/5/picks/", "b"),
        )

    with pytest.raises(TeamStateContractError, match="picks source"):
        normalize_public_team_state(
            entry(),
            picks_payload(),
            state_as_of=STATE_AS_OF,
            entry_snapshot=snapshot("entry/123/", "a"),
            picks_snapshot=snapshot("entry/999/event/5/picks/", "b"),
        )
