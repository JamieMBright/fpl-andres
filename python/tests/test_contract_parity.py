import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from fpl_andres.contracts import FplEntry, SourceSnapshot, parse_source_snapshot

CASES_PATH = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "contracts"
    / "fixtures"
    / "fpl-entry-cases.json"
)
SOURCE_CASES_PATH = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "contracts"
    / "fixtures"
    / "source-snapshot-cases.json"
)


def contract_cases() -> dict[str, list[dict[str, object]]]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def source_cases() -> dict[str, list[dict[str, object]]]:
    return json.loads(SOURCE_CASES_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", contract_cases()["valid"])
def test_python_accepts_shared_valid_entry_cases(case: dict[str, object]) -> None:
    entry = FplEntry.model_validate(case)

    assert entry.id == case["id"]
    assert entry.model_dump(by_alias=True) == case


@pytest.mark.parametrize("case", contract_cases()["invalid"])
def test_python_rejects_shared_invalid_entry_cases(case: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        FplEntry.model_validate(case)


@pytest.mark.parametrize("case", source_cases()["valid"])
def test_python_accepts_shared_valid_source_cases(case: dict[str, object]) -> None:
    snapshot = SourceSnapshot.model_validate(case)
    assert snapshot.model_dump(by_alias=True, mode="json") == case


@pytest.mark.parametrize("case", source_cases()["invalid"])
def test_python_rejects_shared_invalid_source_cases(case: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SourceSnapshot.model_validate(case)


def test_python_normalizes_external_uppercase_source_hash() -> None:
    uppercase_case = source_cases()["invalid"][1]

    snapshot = parse_source_snapshot(uppercase_case)

    assert snapshot.content_hash == f"sha256:{'a' * 64}"
