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

from fpl_andres.cli.track_model import PERFORMANCE_MARKERS, render_performance

_ROOT = Path(__file__).resolve().parents[2]
_CARDS = _ROOT / "docs" / "MODEL_CARDS.md"
_VALIDATION = _ROOT / "apps" / "web" / "src" / "data" / "validation.json"


def _seasons() -> list[dict[str, object]]:
    return json.loads(_VALIDATION.read_text(encoding="utf-8"))["seasons"]


def _methods(season: dict[str, object]) -> dict[str, dict[str, float]]:
    return {entry["label"]: entry for entry in season["methods"]}  # type: ignore[index,union-attr]


def _documented_rows() -> dict[str, tuple[float, float, float]]:
    """Season -> (MAE, spearman, top-N hit rate) as published in the card."""
    text = _CARDS.read_text(encoding="utf-8")
    start, end = PERFORMANCE_MARKERS
    measured = text.partition(start)[2].partition(end)[0]
    rows: dict[str, tuple[float, float, float]] = {}
    for match in re.finditer(
        r"^\|\s*(20\d\d-\d\d)\s*\|\s*([\d.]+)\s*\|[^|]*\|\s*([\d.]+)\s*\|[^|]*\|\s*([\d.]+)\s*\|",
        measured,
        re.MULTILINE,
    ):
        rows[match.group(1)] = (
            float(match.group(2)),
            float(match.group(3)),
            float(match.group(4)),
        )
    return rows


def test_captaincy_rows_cannot_overwrite_the_performance_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    card = tmp_path / "MODEL_CARDS.md"
    card.write_text(
        "\n".join(
            (
                PERFORMANCE_MARKERS[0],
                "| 2025-26 | 1.865 | -6.4% | 0.467 | +0.044 | 0.169 | 0.119 | 0.136 | -0.067 |",
                PERFORMANCE_MARKERS[1],
                "<!-- measured-captaincy:start -->",
                "| 2025-26 | 540 | 6.73 | 12.18 | 5.45 | 80 | 0.28 |",
                "<!-- measured-captaincy:end -->",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("test_measured_performance._CARDS", card)

    assert _documented_rows()["2025-26"] == (1.865, 0.467, 0.169)


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


def test_the_complete_measured_block_is_generated_from_the_artifact() -> None:
    text = _CARDS.read_text(encoding="utf-8")
    start, end = PERFORMANCE_MARKERS
    documented = text.partition(start)[2].partition(end)[0].strip()
    report = json.loads(_VALIDATION.read_text(encoding="utf-8"))

    def normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    assert normalize(documented) == normalize(render_performance(report))


def test_the_model_still_beats_the_form_chaser_everywhere() -> None:
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


def test_the_card_points_at_the_corpus_the_numbers_came_from() -> None:
    """Reproducing them needs the data, not just the code."""
    assert "corpusFingerprint" in _CARDS.read_text(encoding="utf-8")
