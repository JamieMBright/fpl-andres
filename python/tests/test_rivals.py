"""Reading a mini-league's rival squads and measuring ownership inside it."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from fpl_andres.adapters.fpl import FplPicksUnavailable
from fpl_andres.contracts import FetchedPayload, SourceSnapshot
from fpl_andres.planning.rivals import differentials, read_league

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
HAALAND = 1
SALAH = 2
RARE = 3


def snapshot(index: int) -> SourceSnapshot:
    return SourceSnapshot(
        source="fpl",
        fetched_at=NOW,
        data_available_at=NOW,
        content_hash=f"sha256:{index:064x}",
        upstream_reference=f"https://example.invalid/{index}",
    )


class FakeClient:
    """Three rivals: two own the template striker, one owns a rare pick."""

    def __init__(self, *, missing: set[int] | None = None) -> None:
        self.missing = missing or set()
        self.squads = {
            11: ([HAALAND, SALAH], HAALAND),
            12: ([HAALAND, SALAH], SALAH),
            13: ([RARE, SALAH], SALAH),
        }

    async def fetch_standings(self, league_id: int, **_: Any) -> FetchedPayload[dict[str, Any]]:
        return FetchedPayload(
            payload={
                "league": {"name": "The Office"},
                "standings": {
                    "results": [
                        {
                            "entry": entry_id,
                            "entry_name": f"Team {entry_id}",
                            "player_name": f"Player {entry_id}",
                            "rank": rank,
                            "total": 100 - rank,
                        }
                        for rank, entry_id in enumerate(sorted(self.squads), start=1)
                    ]
                },
            },
            snapshot=snapshot(0),
        )

    async def fetch_entry_picks(
        self, entry_id: int, *, event: int
    ) -> FetchedPayload[dict[str, Any]]:
        if entry_id in self.missing:
            raise FplPicksUnavailable(entry_id, event)
        elements, captain = self.squads[entry_id]
        return FetchedPayload(
            payload={
                "picks": [
                    {"element": element, "is_captain": element == captain} for element in elements
                ]
            },
            snapshot=snapshot(entry_id),
        )


@pytest.mark.asyncio
async def test_ownership_is_measured_inside_the_league_not_globally() -> None:
    league = await read_league(FakeClient(), 999, event=30)  # type: ignore[arg-type]

    ownership = league.ownership()

    assert ownership[HAALAND].owned_share == pytest.approx(2 / 3)
    assert ownership[SALAH].owned_share == pytest.approx(1.0)
    assert ownership[RARE].owned_share == pytest.approx(1 / 3)


@pytest.mark.asyncio
async def test_captaincy_raises_effective_ownership_above_the_owned_share() -> None:
    league = await read_league(FakeClient(), 999, event=30)  # type: ignore[arg-type]

    ownership = league.ownership()

    assert ownership[SALAH].captained_share == pytest.approx(2 / 3)
    assert ownership[SALAH].effective > ownership[SALAH].owned_share


@pytest.mark.asyncio
async def test_an_entry_without_picks_is_named_rather_than_silently_dropped() -> None:
    league = await read_league(FakeClient(missing={12}), 999, event=30)  # type: ignore[arg-type]

    assert league.unavailable == (12,)
    assert len(league.squads) == 2


@pytest.mark.asyncio
async def test_every_response_contributes_a_source_hash() -> None:
    league = await read_league(FakeClient(), 999, event=30)  # type: ignore[arg-type]

    assert len(league.source_hashes) == 4
    assert league.source_hashes == tuple(sorted(set(league.source_hashes)))


@pytest.mark.asyncio
async def test_differentials_rank_by_gain_on_the_field_not_raw_points() -> None:
    league = await read_league(FakeClient(), 999, event=30)  # type: ignore[arg-type]

    # Salah scores more but everyone owns him, so he cannot gain you anything.
    ranked = differentials(league, mine=[], projected={SALAH: 9.0, RARE: 6.0})

    assert ranked[0][0] == RARE
    assert ranked[0][2] > ranked[1][2]


@pytest.mark.asyncio
async def test_players_already_held_are_not_offered_as_differentials() -> None:
    league = await read_league(FakeClient(), 999, event=30)  # type: ignore[arg-type]

    ranked = differentials(league, mine=[RARE], projected={SALAH: 9.0, RARE: 6.0})

    assert [row[0] for row in ranked] == [SALAH]


@pytest.mark.asyncio
async def test_a_zero_limit_is_rejected_rather_than_returning_an_empty_league() -> None:
    with pytest.raises(ValueError, match="at least one entry"):
        await read_league(FakeClient(), 999, event=30, limit=0)  # type: ignore[arg-type]
