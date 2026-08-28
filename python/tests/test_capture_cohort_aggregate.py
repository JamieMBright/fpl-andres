from __future__ import annotations

import json
from pathlib import Path

from fpl_andres.cli.capture_cohort_aggregate import write_structure
from fpl_andres.cohorts.portfolio import (
    DistributionSummary,
    KeeperPairing,
    PopularitySquad,
    PortfolioStructure,
)


def test_structure_correction_is_additive_and_names_what_it_supersedes(
    tmp_path: Path,
) -> None:
    original = tmp_path / "gw01-structure.json"
    original.write_text('{"schemaVersion": 1}\n', encoding="utf-8")
    corrected = tmp_path / "gw01-structure-v3.json"
    summary = DistributionSummary(100, 100, 90, 110, 80, 120)
    structure = PortfolioStructure(
        event=1,
        cohort_revision="sha256:pinned",
        attempted=500,
        responded=500,
        keeper_pairings=(KeeperPairing(1, 2, 300, 0.6),),
        common_starting_xi=tuple(range(1, 12)),
        formation=(3, 4, 3),
        positional_spend={position: summary for position in range(1, 5)},
        popularity_squad=PopularitySquad(
            squad=tuple(range(1, 16)),
            starters=tuple(range(1, 12)),
            bench=tuple(range(12, 16)),
            formation=(3, 4, 3),
            spent_tenths=995,
            xi_spent_tenths=790,
            mean_ownership=0.42,
            mean_started_share=0.51,
        ),
    )

    write_structure(
        structure,
        corrected,
        supersedes="gw01-structure-v2.json",
        correction_reason="adds-legal-popularity-squad",
    )

    payload = json.loads(corrected.read_text(encoding="utf-8"))
    assert json.loads(original.read_text(encoding="utf-8")) == {"schemaVersion": 1}
    assert payload["schemaVersion"] == 3
    assert payload["supersedes"] == "gw01-structure-v2.json"
    assert payload["correctionReason"] == "adds-legal-popularity-squad"
    assert payload["popularitySquad"]["squad"] == list(range(1, 16))
    assert payload["popularitySquad"]["bankTenths"] == 5
    assert "entryId" not in json.dumps(payload)
