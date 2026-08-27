from __future__ import annotations

import json
from pathlib import Path

from fpl_andres.cli.capture_cohort_aggregate import write_structure
from fpl_andres.cohorts.portfolio import (
    DistributionSummary,
    KeeperPairing,
    PortfolioStructure,
)


def test_structure_correction_is_additive_and_names_what_it_supersedes(
    tmp_path: Path,
) -> None:
    original = tmp_path / "gw01-structure.json"
    original.write_text('{"schemaVersion": 1}\n', encoding="utf-8")
    corrected = tmp_path / "gw01-structure-v2.json"
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
    )

    write_structure(
        structure,
        corrected,
        supersedes=original.name,
        correction_reason="bench-boost-lineups-use-team-sheet-slots",
    )

    payload = json.loads(corrected.read_text(encoding="utf-8"))
    assert json.loads(original.read_text(encoding="utf-8")) == {"schemaVersion": 1}
    assert payload["schemaVersion"] == 2
    assert payload["supersedes"] == original.name
    assert payload["correctionReason"] == "bench-boost-lineups-use-team-sheet-slots"
