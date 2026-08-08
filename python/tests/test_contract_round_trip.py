"""A payload must survive the round trip through Python unchanged.

`test_contract_parity.py` proves Python accepts what Zod accepts
and rejects what Zod rejects. It says nothing about what Python emits.

A model that parses `{"entryId": 123}` and serialises to `{"entry_id": 123}`
passes every existing test and breaks the wire, because the browser validates
with Zod and Zod is camelCase. The Python side is the producer for every
published artifact, so this is the direction that matters.

Round trip: parse the shared fixture, dump it, and require the result to be
accepted again and to equal what went in.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from fpl_andres.contracts import (
    FplEntry,
    PublicTeamState,
    SourceSnapshot,
    TeamStateOverrides,
)
from fpl_andres.models.deployment import DeploymentSignal

_FIXTURES = Path(__file__).resolve().parents[2] / "packages" / "contracts" / "fixtures"

_CONTRACTS: list[tuple[str, type[BaseModel], str]] = [
    ("fpl-entry-cases.json", FplEntry, "entry"),
    ("source-snapshot-cases.json", SourceSnapshot, "snapshot"),
    ("public-team-state-cases.json", PublicTeamState, "team state"),
    ("team-state-overrides-cases.json", TeamStateOverrides, "overrides"),
    ("deployment-signal-cases.json", DeploymentSignal, "deployment"),
]


def _valid_cases(filename: str) -> list[dict[str, Any]]:
    payload = json.loads((_FIXTURES / filename).read_text(encoding="utf-8"))
    return list(payload["valid"])


def _cases() -> list[tuple[str, type[BaseModel], dict[str, Any], int]]:
    return [
        (label, model, case, index)
        for filename, model, label in _CONTRACTS
        for index, case in enumerate(_valid_cases(filename))
    ]


_ALL = _cases()


def test_there_are_cases_to_round_trip() -> None:
    """A parametrised suite over an empty list passes and proves nothing."""
    assert len(_ALL) >= len(_CONTRACTS)


def _parse(model: type[BaseModel], case: dict[str, Any]) -> BaseModel:
    """Through JSON, because JSON is the wire.

    The contracts are `strict=True`, so a raw dict fails: a list is not a tuple
    and a string is not a datetime. Parsing the serialised form is what the API
    routes and the publishers actually do.
    """
    return model.model_validate_json(json.dumps(case))


@pytest.mark.parametrize(
    ("label", "model", "case", "index"), _ALL, ids=[f"{c[0]}-{c[3]}" for c in _ALL]
)
def test_a_valid_payload_survives_the_round_trip(
    label: str, model: type[BaseModel], case: dict[str, Any], index: int
) -> None:
    """Parse, dump, and the result must equal what went in.

    `by_alias=True` is what the publishers use, so this is the shape that
    actually reaches the browser.
    """
    dumped = _parse(model, case).model_dump(by_alias=True, mode="json", exclude_none=False)

    for key, value in case.items():
        assert key in dumped, f"{label} case {index} lost the field {key!r}"
        assert dumped[key] == value, (
            f"{label} case {index} changed {key!r}: {value!r} became {dumped[key]!r}"
        )


@pytest.mark.parametrize(
    ("label", "model", "case", "index"), _ALL, ids=[f"{c[0]}-{c[3]}" for c in _ALL]
)
def test_the_dumped_payload_is_accepted_again(
    label: str, model: type[BaseModel], case: dict[str, Any], index: int
) -> None:
    """The property that makes the round trip a loop rather than a line."""
    once = _parse(model, case)
    twice = _parse(model, once.model_dump(by_alias=True, mode="json"))

    assert twice == once


@pytest.mark.parametrize(
    ("label", "model", "case", "index"), _ALL, ids=[f"{c[0]}-{c[3]}" for c in _ALL]
)
def test_no_field_leaves_python_in_snake_case(
    label: str, model: type[BaseModel], case: dict[str, Any], index: int
) -> None:
    """Zod is camelCase, and the browser validates with Zod.

    Checked on the output rather than the input, because the input is the
    fixture and the fixture is already right. The output is the part nothing was
    watching.
    """
    dumped = _parse(model, case).model_dump(by_alias=True, mode="json")

    snake = sorted(key for key in _keys(dumped) if "_" in key)
    assert snake == [], f"{label} case {index} emitted snake_case keys: {snake}"


@pytest.mark.parametrize(
    ("label", "model", "case", "index"), _ALL, ids=[f"{c[0]}-{c[3]}" for c in _ALL]
)
def test_the_round_trip_is_stable_under_repetition(
    label: str, model: type[BaseModel], case: dict[str, Any], index: int
) -> None:
    """Two loops must equal one. A normalisation applied on every parse rather
    than once would drift a value further each time it was republished."""
    once = _parse(model, case).model_dump(by_alias=True, mode="json")
    twice = _parse(model, once).model_dump(by_alias=True, mode="json")

    assert once == twice


@pytest.mark.parametrize(
    ("label", "model", "case", "index"), _ALL, ids=[f"{c[0]}-{c[3]}" for c in _ALL]
)
def test_the_dump_is_json_serialisable(
    label: str, model: type[BaseModel], case: dict[str, Any], index: int
) -> None:
    """`mode="json"` should already guarantee it. Asserted because a datetime
    escaping into an artifact fails at write time, in a workflow, not here."""
    json.dumps(_parse(model, case).model_dump(by_alias=True, mode="json"))


def _keys(value: object) -> list[str]:
    """Every key at every depth."""
    if isinstance(value, dict):
        return [
            key
            for entry in value.items()
            for key in [entry[0], *_keys(entry[1])]
            if isinstance(key, str)
        ]
    if isinstance(value, list):
        return [key for item in value for key in _keys(item)]
    return []
