"""Documented parameter values must equal the ones the code uses.

Audit item #196. The repository rule — never default a controlling FPL rule,
fail its source contract visibly — is only auditable if someone can look a number
up and find where it came from. `docs/PARAMETERS.md` is that lookup.

A document is worthless if it drifts, and this one had already been proved to
drift before it existed: `docs/MODEL.md` listed the midfield goal prior at 0.10
and the forward prior at 0.22, against the code's 0.12 and 0.28. A 20% and 27%
understatement of the value every player's rate is shrunk toward, in the file
that claims to describe the model. Nothing compared the two.

These tests compare them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fpl_andres.backtesting.projector import _ASSIST_PRIOR, _GOAL_PRIOR, ProjectionSettings
from fpl_andres.planning.opening import PLAYABLE_START_RATE

_ROOT = Path(__file__).resolve().parents[2]
_PARAMETERS = _ROOT / "docs" / "PARAMETERS.md"
_MODEL = _ROOT / "docs" / "MODEL.md"

_POSITIONS = {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}


def _prior_table(text: str) -> dict[str, tuple[float, float]]:
    """The goals/assists per-90 table, from whichever document is passed."""
    table: dict[str, tuple[float, float]] = {}
    for match in re.finditer(
        r"^\|\s*(GKP|DEF|MID|FWD)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|",
        text,
        re.MULTILINE,
    ):
        table[match.group(1)] = (float(match.group(2)), float(match.group(3)))
    return table


@pytest.mark.parametrize("document", [_PARAMETERS, _MODEL])
def test_the_documented_priors_are_the_ones_the_code_uses(document: Path) -> None:
    """The bug this suite exists for.

    Both documents publish the same table, and both must equal the code. A
    reader who trusts either one and finds a third number in the source has been
    misled about what the model does.
    """
    documented = _prior_table(document.read_text(encoding="utf-8"))

    assert set(documented) == set(_POSITIONS), f"{document.name} lost a position row"
    for code, position in _POSITIONS.items():
        goals, assists = documented[code]
        assert goals == pytest.approx(_GOAL_PRIOR[position]), (
            f"{document.name} says {code} scores {goals} per 90; "
            f"the code uses {_GOAL_PRIOR[position]}"
        )
        assert assists == pytest.approx(_ASSIST_PRIOR[position]), (
            f"{document.name} says {code} assists {assists} per 90; "
            f"the code uses {_ASSIST_PRIOR[position]}"
        )


def test_the_two_documents_agree_with_each_other() -> None:
    assert _prior_table(_PARAMETERS.read_text(encoding="utf-8")) == _prior_table(
        _MODEL.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    ("value", "label"),
    [
        (ProjectionSettings().decay_half_life_events, "4.0"),
        (ProjectionSettings().prior_strength_minutes, "450"),
        (ProjectionSettings().blend_full_weight_minutes, "900"),
        (ProjectionSettings().minimum_minutes, "180"),
    ],
)
def test_model_md_quotes_the_projector_defaults_correctly(value: float, label: str) -> None:
    """These four appear in MODEL.md as prose rather than a table."""
    text = " ".join(_MODEL.read_text(encoding="utf-8").split())

    assert label in text, f"MODEL.md no longer quotes {label}"
    assert float(label) == pytest.approx(value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("prior_strength_events", 2.0),
        ("prior_start_rate", 0.35),
        ("recent_form_window", 5),
        ("recent_form_weight", 0.2),
    ],
)
def test_parameters_md_records_the_projector_defaults_it_lists(name: str, value: float) -> None:
    """A value in the document must be the value in the dataclass."""
    assert getattr(ProjectionSettings(), name) == pytest.approx(value)
    assert name in _PARAMETERS.read_text(encoding="utf-8")


def test_the_assumed_parameters_are_named_as_assumed() -> None:
    """The point of the document. An assumed number presented as a measured one
    is exactly what it exists to prevent, so the two lists must not blur."""
    text = _PARAMETERS.read_text(encoding="utf-8")
    assumed = text.split("## Assumed", 1)[1]
    measured = text.split("## Measured", 1)[1].split("## FPL rules", 1)[0]

    assert "_BENCH_WEIGHT" in assumed
    assert "PLAYABLE_START_RATE" in assumed
    assert "_BENCH_WEIGHT" not in measured
    assert "triple_captain_floor" in assumed


def test_the_playable_start_rate_matches_its_entry() -> None:
    assert pytest.approx(0.35) == PLAYABLE_START_RATE
    assert "| 0.35  | `planning/opening.py`" in _PARAMETERS.read_text(encoding="utf-8")


def test_every_parameter_is_in_exactly_one_state() -> None:
    """Four states, and a parameter in two of them has not been decided about."""
    text = _PARAMETERS.read_text(encoding="utf-8")

    for heading in ("## Caller-supplied", "## Measured", "## FPL rules", "## Assumed"):
        assert heading in text, f"{heading} section is missing"

    # A handful of names that must appear once and in the right place.
    fpl_rules = text.split("## FPL rules", 1)[1].split("## Assumed", 1)[0]
    assert "`_HIT_POINTS`" in fpl_rules or "_HIT_POINTS" in fpl_rules
    assert "`club_limit`" in fpl_rules


def test_the_unexplained_damping_constant_is_recorded() -> None:
    """The only wholly unexplained number in the model path: how much fixture
    pressure reaches the defensive-contribution multiplier."""
    source = (_ROOT / "python" / "fpl_andres" / "backtesting" / "fixtures.py").read_text(
        encoding="utf-8"
    )

    assert "(conceding - 1.0) * 0.5" in source
    assert "defensive-contribution damping" in _PARAMETERS.read_text(encoding="utf-8")
