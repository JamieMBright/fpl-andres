"""Every model module must be described somewhere a reader would look.

Audit item #186. `models/shot_profile.py`, `models/penalties.py`,
`models/suspensions.py` and `backtesting/reliability.py` existed, were tested,
and were documented nowhere — while `MODEL.md` claimed to be the description of
the model.

The numbers in the prose are the measured ones from each module's docstring, so
this also fails if a documented measurement drifts from the code that made it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MODEL = _ROOT / "docs" / "MODEL.md"
_PACKAGE = _ROOT / "python" / "fpl_andres"

# Modules that produce or shape a projection. Adapters, persistence and CLI are
# not model description and are deliberately out of scope.
_MODEL_MODULES = [
    "models/minutes.py",
    "models/player_rates.py",
    "models/expected_points.py",
    "models/shot_profile.py",
    "models/penalties.py",
    "models/suspensions.py",
    "models/deployment.py",
    "models/dixon_coles.py",
    "backtesting/reliability.py",
    "backtesting/fixtures.py",
]


def _model() -> str:
    return _MODEL.read_text(encoding="utf-8")


@pytest.mark.parametrize("module", _MODEL_MODULES)
def test_every_model_module_is_named_in_the_model_document(module: str) -> None:
    """A module the description does not mention is a part of the model nobody
    reading the description knows exists."""
    assert module in _model(), f"docs/MODEL.md never mentions {module}"


def _docstring(module: str) -> str:
    tree = ast.parse((_PACKAGE / module).read_text(encoding="utf-8"))
    return ast.get_docstring(tree) or ""


@pytest.mark.parametrize(
    ("module", "measurement"),
    [
        ("models/shot_profile.py", "0.890"),
        ("models/shot_profile.py", "0.455"),
        ("models/shot_profile.py", "0.0666"),
        ("models/penalties.py", "5.9%"),
        ("models/penalties.py", "44.5%"),
        ("models/penalties.py", "38.3%"),
    ],
)
def test_a_quoted_measurement_matches_the_module_that_made_it(
    module: str, measurement: str
) -> None:
    """Both places must agree. A document quoting a number the code no longer
    produces is the failure mode #196 caught in the prior table."""
    assert measurement in _docstring(module), f"{module} no longer states {measurement}"
    assert measurement in _model(), f"MODEL.md no longer quotes {measurement}"


def test_the_shot_split_records_that_the_league_mean_is_worse() -> None:
    """The finding that justifies keeping a noisy quantity: substituting the
    league mean makes prediction worse, not better."""
    text = _model()

    assert "0.0561" in text and "0.0666" in text
    assert "worse" in text


def test_suspension_thresholds_are_documented_as_sourced() -> None:
    """The competition resets cautions partway through a season, and the reset
    point is a rule rather than a modelling choice."""
    text = _model()

    assert "sourced, never assumed" in text
    assert "SuspensionRules" in text


def test_return_shape_is_documented_as_separate_from_the_mean() -> None:
    """Folding it in would produce one number implying a certainty the evidence
    does not support."""
    text = _model()

    assert "floor, median and ceiling" in text
    assert "20th, 50th and 90th" in text


def test_penalty_exposure_is_described_as_measurement_not_prediction() -> None:
    """It measures exposure to an assumption the projection already makes. A
    reader who thinks it predicts penalty takers will misuse it."""
    text = _model()

    assert "predicts who will take penalties" in text


def test_the_document_still_covers_what_it_covered_before() -> None:
    """A regression guard on the sections that already existed."""
    text = _model()

    for heading in (
        "## 2. Minutes, before anything else",
        "## 3. Attacking rate",
        "## 4. Every scoring route, priced",
        "## 8. Between seasons",
        "## 13. What this does not calculate",
    ):
        assert heading in text
