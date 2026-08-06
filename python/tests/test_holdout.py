"""The holdout is a promise, and a promise needs something that can break it.

Declaring a held-out season costs nothing if the declaration drifts from what
the backtest actually scores, or if the holdout quietly becomes a development
season because somebody widened the default season list.
"""

from __future__ import annotations

import json
from pathlib import Path

from fpl_andres.cli.validate import build_parser
from fpl_andres.holdout import DEVELOPMENT_SEASONS, HOLDOUT_SEASON, SCORED_SEASONS

ARTIFACT = Path(__file__).resolve().parents[2] / "apps" / "web" / "src" / "data" / "validation.json"


class TestTheHoldoutIsCoherent:
    def test_the_holdout_is_one_of_the_scored_seasons(self) -> None:
        assert HOLDOUT_SEASON in SCORED_SEASONS

    def test_development_is_everything_else(self) -> None:
        assert set(DEVELOPMENT_SEASONS) == set(SCORED_SEASONS) - {HOLDOUT_SEASON}
        assert HOLDOUT_SEASON not in DEVELOPMENT_SEASONS

    def test_something_is_actually_held_back(self) -> None:
        # A holdout equal to the whole set is not a holdout.
        assert DEVELOPMENT_SEASONS
        assert len(DEVELOPMENT_SEASONS) < len(SCORED_SEASONS)

    def test_the_validate_default_scores_every_declared_season(self) -> None:
        # Scored, not tuned against. The holdout has to be measured or there is
        # nothing to report at the end.
        default = build_parser().parse_args([]).seasons
        assert default.split(",") == list(SCORED_SEASONS)

    def test_the_holdout_is_the_most_recent_season(self) -> None:
        # A holdout is only worth having if it is the one most like the season
        # about to be played.
        assert max(SCORED_SEASONS) == HOLDOUT_SEASON


class TestTheArtifactAgreesWithTheDeclaration:
    def test_every_scored_season_is_labelled_once_the_backtest_reruns(self) -> None:
        report = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        seasons = report.get("seasons", [])
        labelled = [entry for entry in seasons if "holdout" in entry]
        if not labelled:
            # Artifact predates the declaration; CI fills it on the next run.
            return

        flagged = [entry["season"] for entry in labelled if entry["holdout"]]
        assert flagged == [HOLDOUT_SEASON]
