"""The four FPL positions must have exactly one definition.

This said the element-type-to-code mapping was written twice, in
`backtesting/score.py` and `models/deployment.py`. That was true. This pins the
merge so a third copy cannot quietly appear.

It was asked for the `Literal` position codes in `deployment.py` to
become an enum. The `Literal` is deliberately kept: it is a Pydantic field type
that determines the shape of published JSON, and swapping it for an enum changes
serialisation for no behavioural gain. The drift risk #14 was actually worried
about is closed by `test_listed_position_matches_the_enum` below, which fails if
the two ever disagree.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import get_args

import pytest

from fpl_andres.backtesting.score import _position_label
from fpl_andres.models.deployment import ListedPosition
from fpl_andres.positions import Position, PositionUnknown, position_code

_PACKAGE = Path(__file__).resolve().parents[1] / "fpl_andres"


class PositionMappingTest:
    pass


@pytest.mark.parametrize(
    ("element_type", "code"),
    [(1, "GKP"), (2, "DEF"), (3, "MID"), (4, "FWD")],
)
def test_maps_fpl_element_types_to_their_codes(element_type: int, code: str) -> None:
    assert position_code(element_type) == code


def test_refuses_an_unknown_element_type_rather_than_guessing() -> None:
    """Assistant Manager was element_type 5. Silently coding it 'UNK' inside a
    projection would price a position the model has never fitted."""
    with pytest.raises(PositionUnknown, match="not one of the four"):
        position_code(5)


def test_the_enum_value_is_fpls_own_element_type() -> None:
    assert [position.value for position in Position] == [1, 2, 3, 4]
    assert Position.MIDFIELDER.code == "MID"


def test_listed_position_matches_the_enum() -> None:
    """#14's real risk: two lists of the same four codes drifting apart."""
    assert set(get_args(ListedPosition)) == {position.code for position in Position}


def test_scoring_labels_an_unknown_type_instead_of_refusing_the_season() -> None:
    """A historical corpus legitimately contains element_type 5 (2024/25's
    Assistant Manager). Backtesting groups it; it does not project it."""
    assert _position_label(3) == "MID"
    assert _position_label(5) == "UNK"


def test_no_module_redefines_the_position_mapping() -> None:
    """Fails if a third copy of the GKP/DEF/MID/FWD map is added anywhere."""
    literal = re.compile(r'"GKP".{0,60}"DEF".{0,60}"MID".{0,60}"FWD"', re.DOTALL)
    offenders = sorted(
        path.relative_to(_PACKAGE).as_posix()
        for path in _PACKAGE.rglob("*.py")
        if path.name not in {"positions.py", "deployment.py"}
        and literal.search(path.read_text(encoding="utf-8"))
    )
    assert offenders == [], (
        f"these re-declare the four FPL positions; import fpl_andres.positions instead: {offenders}"
    )


def test_the_enum_is_exhaustive_over_the_code_table() -> None:
    """A new member without a code would be a KeyError at runtime, not import."""
    for position in Position:
        assert isinstance(position.code, str)


def test_positions_module_has_no_package_imports() -> None:
    """It sits at the bottom of the dependency graph; anything else risks a
    cycle when models and backtesting both import it."""
    tree = ast.parse((_PACKAGE / "positions.py").read_text(encoding="utf-8"))
    imported = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(name.startswith("fpl_andres") for name in imported)
