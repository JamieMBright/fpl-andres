"""The published performance numbers must be the measured ones.

`MODEL_CARDS.md` described the evaluation method and never said
what it produced, so a reader had to run the backtest to find out whether the
model beat anything.

Now it says. These tests read the same artifact the calibration page serves and
fail if the document disagrees with it — a performance claim that has drifted
from the measurement is worse than no claim, because it is quotable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_CARDS = _ROOT / "docs" / "MODEL_CARDS.md"
_VALIDATION = _ROOT / "apps" / "web" / "src" / "data" / "validation.json"


def _seasons() -> list[dict[str, object]]:
    return json.loads(_VALIDATION.read_text(encoding="utf-8"))["seasons"]


def _methods(season: dict[str, object]) -> dict[str, dict[str, float]]:
    return {entry["label"]: entry for entry in season["methods"]}  # type: ignore[index,union-attr]


def _documented_rows() -> dict[str, tuple[float, float, float]]:
    """Season -> (MAE, spearman, top-N hit rate) as published in the card."""
    rows: dict[str, tuple[float, float, float]] = {}
    for match in re.finditer(
        r"^\|\s*(20\d\d-\d\d)\s*\|\s*([\d.]+)\s*\|[^|]*\|\s*([\d.]+)\s*\|[^|]*\|\s*([\d.]+)\s*\|",
        _CARDS.read_text(encoding="utf-8"),
        re.MULTILINE,
    ):
        rows[match.group(1)] = (
            float(match.group(2)),
            float(match.group(3)),
            float(match.group(4)),
        )
    return rows


def test_the_card_publishes_a_row_for_every_scored_season() -> None:
    measured = {str(season["season"]) for season in _seasons()}

    assert set(_documented_rows()) == measured


@pytest.mark.parametrize("season", [str(s["season"]) for s in _seasons()])
def test_the_published_numbers_are_the_measured_ones(season: str) -> None:
    model = next(_methods(s)["model"] for s in _seasons() if str(s["season"]) == season)
    mae, spearman, top_n = _documented_rows()[season]

    assert mae == pytest.approx(model["meanAbsoluteError"], abs=0.001)
    assert spearman == pytest.approx(model["spearman"], abs=0.001)
    assert top_n == pytest.approx(model["topNHitRate"], abs=0.001)


def test_the_model_still_beats_the_form_chaser_everywhere() -> None:
    """The claim the card makes. If this fails the card is wrong, and so is the
    thesis until it is rewritten."""
    for season in _seasons():
        methods = _methods(season)
        model, form = methods["model"], methods["recent_mean"]

        assert model["meanAbsoluteError"] < form["meanAbsoluteError"], season["season"]
        assert model["spearman"] > form["spearman"], season["season"]
        assert model["topNHitRate"] > form["topNHitRate"], season["season"]


def test_the_model_still_beats_the_crowd_on_hit_rate() -> None:
    for season in _seasons():
        methods = _methods(season)

        assert methods["model"]["topNHitRate"] > methods["ownership"]["topNHitRate"], season[
            "season"
        ]


def test_the_negative_bias_is_recorded_rather_than_omitted() -> None:
    """It is the clearest open lead in the calibration, and the number most
    tempting to leave out of a card that otherwise reads well."""
    biases = [_methods(season)["model"]["bias"] for season in _seasons()]

    assert all(bias < 0 for bias in biases), "the bias changed sign; update the card"
    assert "Bias is negative in every season" in _CARDS.read_text(encoding="utf-8")


def test_the_card_names_the_worst_season_rather_than_averaging_it_away() -> None:
    worst = max(_seasons(), key=lambda s: _methods(s)["model"]["meanAbsoluteError"])

    assert f"{worst['season']} is the worst season" in _CARDS.read_text(encoding="utf-8")


def test_the_card_reports_the_weakest_position() -> None:
    """Defenders are the hardest to rank and there are five in a squad, so the
    weakest part of the model carries the most weight in a selection."""
    latest = _seasons()[-1]
    by_position = _methods(latest)["model"]["byPosition"]  # type: ignore[index]

    weakest = min(by_position, key=lambda code: by_position[code])  # type: ignore[index]
    assert weakest == "DEF"
    assert "Defenders are the hardest to rank" in _CARDS.read_text(encoding="utf-8")


def test_the_card_points_at_the_corpus_the_numbers_came_from() -> None:
    """Reproducing them needs the data, not just the code."""
    assert "corpusFingerprint" in _CARDS.read_text(encoding="utf-8")
