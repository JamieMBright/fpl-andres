"""Boundary behaviour of the ingest and crosswalk, stated as properties.

Both modules make tolerance judgements — how close two minute
counts have to be, how many name spellings to try — and both were tested with
worked examples. These state what must hold for every input.

The interesting cases here are the ones a hand-written example would not think
to try: a name that is entirely whitespace, a CSV where a numeric column holds
the empty string, a player whose minutes are exactly on the tolerance boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from fpl_andres.crosswalk.names import variants
from fpl_andres.crosswalk.resolve import (
    _MINUTES_FLOOR,
    _MINUTES_TOLERANCE,
    _agrees,
)
from fpl_andres.ingest.normalise import _bool, _float, _int

_SAFE_TEXT = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), min_size=0, max_size=40)


@given(value=st.integers(min_value=-10_000, max_value=10_000))
@settings(max_examples=200, deadline=None)
def test_an_integer_column_round_trips(value: int) -> None:
    assert _int(str(value), column="minutes") == value


@given(value=st.integers(min_value=-1000, max_value=1000))
@settings(max_examples=200, deadline=None)
def test_a_float_written_into_an_integer_column_truncates_consistently(value: int) -> None:
    """Archive rows carry floats in integer columns ("90.0"). Whatever the
    conversion does, it must not depend on how the float was spelled."""
    assert _int(f"{value}.0", column="minutes") == _int(str(value), column="minutes")


@given(raw=st.sampled_from(["", "   ", "\t", "\n"]))
@settings(max_examples=20, deadline=None)
def test_blank_is_absent_rather_than_zero(raw: str) -> None:
    """A column FPL stopped publishing must not read as a player who did
    nothing. None says absent; 0 says measured and found to be nothing."""
    assert _int(raw, column="minutes") is None
    assert _float(raw, column="expected_goals") is None


@given(value=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False))
@settings(max_examples=200, deadline=None)
def test_a_float_column_round_trips(value: float) -> None:
    parsed = _float(repr(value), column="expected_goals")
    assert parsed is not None
    assert abs(parsed - value) < 1e-9


@given(raw=st.sampled_from(["True", "true", "TRUE", "1"]))
@settings(max_examples=20, deadline=None)
def test_truthy_spellings_all_read_as_true(raw: str) -> None:
    assert _bool(raw, column="was_home") is True


@given(raw=st.sampled_from(["False", "false", "FALSE", "0"]))
@settings(max_examples=20, deadline=None)
def test_falsy_spellings_all_read_as_false(raw: str) -> None:
    assert _bool(raw, column="was_home") is False


@given(name=_SAFE_TEXT)
@settings(max_examples=300, deadline=None)
def test_every_spelling_variant_is_non_empty_and_stripped(name: str) -> None:
    """An empty spelling would key the crosswalk index on nothing, pooling every
    unnameable player into one bucket."""
    for spelling in variants(name):
        assert spelling == spelling.strip()
        assert spelling != ""


@given(name=_SAFE_TEXT)
@settings(max_examples=300, deadline=None)
def test_variants_are_deterministic(name: str) -> None:
    assert variants(name) == variants(name)


@given(first=_SAFE_TEXT, second=_SAFE_TEXT)
@settings(max_examples=200, deadline=None)
def test_adding_a_name_never_removes_a_spelling(first: str, second: str) -> None:
    """Passing more of a player's name must not make them harder to find."""
    assume(second.strip())
    assert set(variants(first)) <= set(variants(first, second))


@dataclass(frozen=True)
class _Side:
    minutes: int
    goals: int


@given(
    minutes=st.integers(min_value=0, max_value=4000),
    goals=st.integers(min_value=0, max_value=40),
)
@settings(max_examples=300, deadline=None)
def test_a_source_always_agrees_with_itself(minutes: int, goals: int) -> None:
    """Reflexive, or the crosswalk could reject a perfect match."""
    side = _Side(minutes=minutes, goals=goals)
    assert _agrees(side, side)  # type: ignore[arg-type]


@given(
    minutes=st.integers(min_value=0, max_value=4000),
    goals=st.integers(min_value=0, max_value=40),
    drift=st.integers(min_value=-40, max_value=40),
)
@settings(max_examples=400, deadline=None)
def test_minute_agreement_is_symmetric_within_the_floor(
    minutes: int, goals: int, drift: int
) -> None:
    """The tolerance is a band around the player, not a direction. A source
    reporting 40 minutes fewer must be judged the same as one reporting 40
    more, or which feed is `player` decides the match.
    """
    assume(abs(drift) <= _MINUTES_FLOOR)
    a = _Side(minutes=minutes, goals=goals)
    b = _Side(minutes=max(0, minutes + drift), goals=goals)
    assert _agrees(a, b) == _agrees(b, a)  # type: ignore[arg-type]


@given(minutes=st.integers(min_value=0, max_value=4000))
@settings(max_examples=300, deadline=None)
def test_the_minute_floor_holds_for_a_player_with_almost_no_football(
    minutes: int,
) -> None:
    """The allowance is `max(floor, minutes * tolerance)`, so a substitute with
    twenty minutes is not held to a two-minute band."""
    assume(minutes * _MINUTES_TOLERANCE < _MINUTES_FLOOR)
    a = _Side(minutes=minutes, goals=0)
    b = _Side(minutes=minutes + _MINUTES_FLOOR, goals=0)
    assert _agrees(a, b)  # type: ignore[arg-type]


@given(minutes=st.integers(min_value=1, max_value=4000))
@settings(max_examples=300, deadline=None)
def test_a_wildly_different_minute_count_never_agrees(minutes: int) -> None:
    a = _Side(minutes=minutes, goals=0)
    b = _Side(minutes=minutes * 4 + _MINUTES_FLOOR * 4, goals=0)
    assert not _agrees(a, b)  # type: ignore[arg-type]
