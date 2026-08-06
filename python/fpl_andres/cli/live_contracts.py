from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from fpl_andres.adapters.fpl import FplClient
from fpl_andres.rules import (
    validate_published_bootstrap_contract,
    validate_published_squad_contract,
)


async def validate_live_contracts() -> None:
    async with httpx.AsyncClient() as http:
        client = FplClient(http=http, clock=lambda: datetime.now(UTC))
        fetched = await client.fetch_bootstrap()
    validate_published_bootstrap_contract(fetched.payload)
    validate_published_squad_contract(fetched.payload)
    print(
        "Validated published FPL bootstrap contract "
        f"at {fetched.snapshot.fetched_at.isoformat()} "
        f"({fetched.snapshot.content_hash})."
    )


def main() -> None:
    asyncio.run(validate_live_contracts())


if __name__ == "__main__":
    main()
