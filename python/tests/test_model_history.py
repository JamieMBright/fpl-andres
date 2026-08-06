"""The model's own history has to be comparable with itself.

A snapshot artifact says how the model scores now and forgets how it scored
before, which is the wrong shape for the only question that matters after a
first release. These are the rules that keep the record honest: one row per
model and corpus, no row without a version, and a comparison that names a
regression instead of burying it in a JSON diff.
"""

from __future__ import annotations

from typing import Any

import pytest

from fpl_andres.cli.compare_validation import compare
from fpl_andres.cli.track_model import merge_history
from fpl_andres.model_version import MODEL_VERSION


def _run(version: str, fingerprint: str, spearman: float = 0.5) -> dict[str, Any]:
    return {
        "modelVersion": version,
        "generatedAt": "2026-08-06T00:00:00+00:00",
        "seasons": [
            {
                "season": "2024-25",
                "corpusFingerprint": fingerprint,
                "methods": {"model": {"spearman": spearman}},
                "captaincy": {},
            }
        ],
    }


class TestHistory:
    def test_the_first_run_is_recorded(self) -> None:
        history, changed = merge_history([], _run("2.0", "abc"))
        assert changed
        assert len(history) == 1

    def test_the_same_model_on_the_same_corpus_is_not_recorded_twice(self) -> None:
        first, _ = merge_history([], _run("2.0", "abc"))
        second, changed = merge_history(first, _run("2.0", "abc"))
        assert not changed
        assert len(second) == 1

    def test_a_new_model_version_is_a_new_row(self) -> None:
        first, _ = merge_history([], _run("2.0", "abc"))
        second, changed = merge_history(first, _run("2.1", "abc"))
        assert changed
        assert [entry["modelVersion"] for entry in second] == ["2.0", "2.1"]

    def test_the_same_model_on_a_changed_corpus_is_a_new_row(self) -> None:
        # The numbers moved without the model moving, which is a fact about the
        # data. Recording it is the only way to tell the two causes apart.
        first, _ = merge_history([], _run("2.0", "abc"))
        second, changed = merge_history(first, _run("2.0", "def"))
        assert changed
        assert len(second) == 2

    def test_an_unversioned_run_is_refused(self) -> None:
        run = _run("2.0", "abc")
        del run["modelVersion"]
        with pytest.raises(ValueError, match="modelVersion"):
            merge_history([], run)

    def test_the_shipped_version_is_the_one_the_gate_reads(self) -> None:
        # `scripts/model-version-gate.mjs` parses this by regex, so the literal
        # has to stay a plain double-quoted string on its own line.
        source = (
            __import__("pathlib")
            .Path(__file__)
            .resolve()
            .parents[2]
            .joinpath("python/fpl_andres/model_version.py")
            .read_text(encoding="utf-8")
        )
        assert f'MODEL_VERSION = "{MODEL_VERSION}"' in source


class TestComparison:
    def _report(self, version: str, **metrics: float) -> dict[str, Any]:
        return {
            "modelVersion": version,
            "seasons": [
                {
                    "season": "2024-25",
                    "methods": [{"label": "model", **metrics}],
                }
            ],
        }

    def test_an_unchanged_run_says_so(self) -> None:
        report = self._report("2.0", spearman=0.5, meanAbsoluteError=1.7)
        assert "No headline metric moved." in compare(report, report)

    def test_a_regression_is_named_not_buried(self) -> None:
        before = self._report("2.0", spearman=0.500)
        after = self._report("2.1", spearman=0.460)
        text = compare(before, after)
        assert "WORSE" in text
        assert "-0.040" in text

    def test_an_improvement_is_marked_as_one(self) -> None:
        before = self._report("2.0", meanAbsoluteError=1.800)
        after = self._report("2.1", meanAbsoluteError=1.700)
        text = compare(before, after)
        assert "better" in text
        assert "WORSE" not in text

    def test_lower_is_better_is_not_inverted(self) -> None:
        # Error going up is worse; rank correlation going up is better. One
        # table, two directions, and getting it backwards would report every
        # regression as progress.
        worse_error = compare(
            self._report("2.0", meanAbsoluteError=1.700),
            self._report("2.1", meanAbsoluteError=1.900),
        )
        assert "WORSE" in worse_error

    def test_a_method_with_no_earlier_row_is_marked_new(self) -> None:
        before = {"modelVersion": "2.0", "seasons": []}
        after = self._report("2.1", spearman=0.5)
        assert "new" in compare(before, after)
