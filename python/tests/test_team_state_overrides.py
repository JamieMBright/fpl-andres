from datetime import UTC, datetime, timedelta

import pytest

from fpl_andres.contracts import (
    ManagerTeamPlayer,
    PublicTeamPick,
    PublicTeamState,
    QueuedTransfer,
    TeamStateOverrides,
)
from fpl_andres.optimization.contracts import optimization_state_evidence_from_team_state
from fpl_andres.team_state import TeamStateResolutionError, resolve_team_state

STATE_AS_OF = datetime(2026, 9, 12, 10, 30, tzinfo=UTC)


def public_state() -> PublicTeamState:
    picks = tuple(
        PublicTeamPick(
            element_id=element_id,
            squad_position=position,
            multiplier=2 if position == 1 else (0 if position > 11 else 1),
            is_captain=position == 1,
            is_vice_captain=position == 2,
        )
        for position, element_id in enumerate(range(101, 116), start=1)
    )
    return PublicTeamState(
        entry_id=123,
        event=5,
        bank_tenths=17,
        squad_value_tenths=1_004,
        event_transfers=0,
        event_transfer_cost_points=0,
        total_transfers=4,
        active_chip=None,
        picks=picks,
        state_as_of=STATE_AS_OF,
        data_available_at=STATE_AS_OF + timedelta(hours=2),
        evidence_level="observed",
        source_hashes=(f"sha256:{'a' * 64}", f"sha256:{'b' * 64}"),
    )


def current_squad() -> tuple[ManagerTeamPlayer, ...]:
    element_ids = (201, *range(102, 116))
    return tuple(
        ManagerTeamPlayer(
            element_id=element_id,
            squad_position=position,
            purchase_price_tenths=65 if element_id == 201 else 50,
            selling_price_tenths=65 if element_id == 201 else 50,
        )
        for position, element_id in enumerate(element_ids, start=1)
    )


def overrides(**updates: object) -> TeamStateOverrides:
    values: dict[str, object] = {
        "source": "manager",
        "based_on_state_as_of": STATE_AS_OF,
        "updated_at": STATE_AS_OF + timedelta(hours=3),
        "bank_tenths": 12,
        "available_free_transfers": 1,
        "current_squad": current_squad(),
        "queued_transfers": (
            QueuedTransfer(
                element_out_id=101,
                element_in_id=201,
                selling_price_tenths=60,
                purchase_price_tenths=65,
            ),
        ),
        "available_chips": ("bench_boost", "wildcard"),
    }
    values.update(updates)
    return TeamStateOverrides.model_validate(values)


def test_resolves_exact_manager_state_without_mutating_public_snapshot() -> None:
    public = public_state()

    resolved = resolve_team_state(public, overrides())

    assert public.picks[0].element_id == 101
    assert resolved.current_squad[0].element_id == 201
    assert resolved.bank_tenths == 12
    assert resolved.available_free_transfers == 1
    assert resolved.available_chips == ("bench_boost", "wildcard")
    assert resolved.public_state_as_of == STATE_AS_OF
    assert resolved.overrides_updated_at == STATE_AS_OF + timedelta(hours=3)
    assert resolved.public_source_hashes == public.source_hashes
    assert resolved.manager_overrides_hash.startswith("sha256:")
    assert (
        resolved.manager_overrides_hash
        == resolve_team_state(
            public,
            overrides(),
        ).manager_overrides_hash
    )

    evidence = optimization_state_evidence_from_team_state(resolved)
    assert evidence.public_state_as_of == resolved.public_state_as_of
    assert evidence.public_source_hashes == resolved.public_source_hashes
    assert evidence.manager_overrides_hash == resolved.manager_overrides_hash
    assert (
        resolved.manager_overrides_hash
        != resolve_team_state(
            public,
            overrides(bank_tenths=None),
        ).manager_overrides_hash
    )


def test_resolution_refuses_to_default_missing_private_state() -> None:
    with pytest.raises(TeamStateResolutionError, match="available_free_transfers"):
        resolve_team_state(public_state(), overrides(available_free_transfers=None))

    with pytest.raises(TeamStateResolutionError, match="available_chips"):
        resolve_team_state(public_state(), overrides(available_chips=None))


def test_resolution_rejects_stale_base_or_unreconciled_transfer() -> None:
    with pytest.raises(TeamStateResolutionError, match="different public deadline"):
        resolve_team_state(
            public_state(),
            overrides(based_on_state_as_of=STATE_AS_OF - timedelta(days=7)),
        )

    wrong_transfer = (
        QueuedTransfer(
            element_out_id=102,
            element_in_id=201,
            selling_price_tenths=60,
            purchase_price_tenths=65,
        ),
    )
    with pytest.raises(TeamStateResolutionError, match="current squad"):
        resolve_team_state(public_state(), overrides(queued_transfers=wrong_transfer))


def test_resolution_rejects_bank_that_does_not_match_transfer_prices() -> None:
    with pytest.raises(TeamStateResolutionError, match="bank"):
        resolve_team_state(public_state(), overrides(bank_tenths=13))
