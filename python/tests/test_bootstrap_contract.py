"""Upstream payload fields must be validated, not cast.

Audit item #139. `int(element["id"])` asserts a type without saying so, and the
message it produces when the assertion breaks names neither the player nor the
endpoint. These tests pin the replacement and record what the old failures
actually looked like, so the improvement is a comparison rather than a claim.
"""

from __future__ import annotations

import pytest

from fpl_andres.bootstrap import (
    BootstrapElement,
    BootstrapElementError,
    CrowdElement,
    OwnershipElement,
    parse_elements,
)
from fpl_andres.positions import Position


def _element(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": 351,
        "code": 118748,
        "element_type": 3,
        "team": 12,
        "now_cost": 145,
        "web_name": "M.Salah",
        "status": "a",
        "selected_by_percent": "42.1",
        "transfers_in_event": 100,
        "transfers_out_event": 20,
    }
    payload.update(overrides)
    return payload


def test_reads_a_well_formed_element() -> None:
    element = BootstrapElement.model_validate(_element())
    assert element.id == 351
    assert element.position is Position.MIDFIELDER
    assert element.is_available
    assert element.selected_by_percent == pytest.approx(42.1)


def test_accepts_fields_this_package_does_not_know_about() -> None:
    """FPL adds fields between seasons. Refusing the payload because it grew
    would break the publisher on a change that affects nothing it reads."""
    element = BootstrapElement.model_validate(_element(chance_of_playing_next_round=75))
    assert element.web_name == "M.Salah"


def test_a_missing_field_names_the_player_and_the_endpoint() -> None:
    """The bare cast raised `KeyError: 'now_cost'` and stopped there."""
    broken = _element()
    del broken["now_cost"]
    with pytest.raises(BootstrapElementError) as caught:
        parse_elements([broken], model=BootstrapElement)
    message = str(caught.value)
    assert "bootstrap-static" in message
    assert "elements[0]" in message
    assert "id=351" in message
    assert "M.Salah" in message
    assert "now_cost" in message


def test_a_null_field_is_reported_as_a_contract_break() -> None:
    """`int(None)` raised a TypeError that reads like a bug in this repository."""
    with pytest.raises(BootstrapElementError, match="does not match the expected contract"):
        parse_elements([_element(now_cost=None)], model=BootstrapElement)


def test_the_old_cast_produced_the_message_this_replaces() -> None:
    """Recorded so the improvement is measurable, not asserted."""
    with pytest.raises(KeyError, match="now_cost"):
        broken = _element()
        del broken["now_cost"]
        int(broken["now_cost"])  # type: ignore[call-overload]
    with pytest.raises(TypeError, match=r"int\(\)"):
        int(None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 0),
        ("code", -1),
        ("team", 21),
        ("now_cost", 0),
        ("now_cost", 1001),
        ("web_name", ""),
        ("status", ""),
        ("status", "available"),
        ("transfers_in_event", -1),
    ],
)
def test_out_of_range_values_are_refused(field: str, value: object) -> None:
    with pytest.raises(BootstrapElementError):
        parse_elements([_element(**{field: value})], model=BootstrapElement)


def test_one_bad_element_refuses_the_whole_payload() -> None:
    """A publisher that skipped the bad row would ship a squad chosen from an
    incomplete pool and say nothing about it."""
    with pytest.raises(BootstrapElementError, match=r"elements\[1\]"):
        parse_elements(
            [_element(), _element(id=352, team=99), _element(id=353)], model=BootstrapElement
        )


def test_an_empty_element_list_is_a_contract_break_not_an_empty_squad() -> None:
    with pytest.raises(BootstrapElementError, match="returned no elements"):
        parse_elements([], model=BootstrapElement)


def test_a_non_list_payload_says_what_it_got() -> None:
    with pytest.raises(BootstrapElementError, match="must be a list, got dict"):
        parse_elements({"elements": []}, model=BootstrapElement)


def test_an_unknown_element_type_is_deferred_to_the_caller() -> None:
    """FPL shipped element_type 5 (Assistant Manager) in 2024/25. Parsing must
    survive it so the publisher can choose to skip it; only reading `.position`
    refuses."""
    element = BootstrapElement.model_validate(_element(element_type=5))
    assert element.element_type == 5
    with pytest.raises(ValueError, match="5 is not a valid Position"):
        _ = element.position


@pytest.mark.parametrize(
    ("status", "available"),
    [("a", True), ("d", False), ("i", False), ("s", False), ("u", False), ("n", False)],
)
def test_availability_follows_fpls_own_flag(status: str, available: bool) -> None:
    assert BootstrapElement.model_validate(_element(status=status)).is_available is available


def test_a_crowd_capture_needs_neither_price_nor_position() -> None:
    """The three models are layered by what each consumer actually reads. A
    crowd capture that refused a payload for lacking `status` would be inventing
    a coupling FPL never imposed."""
    element = CrowdElement.model_validate(
        {"id": 5, "selected_by_percent": "42.7", "transfers_in_event": 1000}
    )
    assert element.selected_by_percent == pytest.approx(42.7)
    assert element.transfers_out_event is None


def test_ownership_is_required_and_never_defaulted() -> None:
    """A default would turn a field FPL stopped sending into a player nobody
    owns: a plausible reading of the number, and a wrong one. Adding a default
    here broke `test_fplcache`'s refusal guard while this item was being
    written, which is how the rule was rediscovered."""
    with pytest.raises(BootstrapElementError, match="selected_by_percent"):
        parse_elements([{"id": 5}], model=CrowdElement)


def test_absent_transfer_counts_stay_absent_rather_than_becoming_zero() -> None:
    """`None` says 'not captured'. `0` claims nobody moved."""
    element = CrowdElement.model_validate({"id": 5, "selected_by_percent": 1.0})
    assert element.transfers_in_event is None
    assert element.transfers_out_event is None


def test_an_archived_snapshot_must_still_carry_price_and_transfers() -> None:
    """OwnershipElement tightens what CrowdElement leaves open, because the
    ownership table stores a price and a movement."""
    with pytest.raises(BootstrapElementError, match="now_cost"):
        parse_elements([{"id": 5, "code": 1, "selected_by_percent": 1.0}], model=OwnershipElement)


@pytest.mark.parametrize("share", [-0.1, 100.1])
def test_an_impossible_ownership_share_is_refused(share: float) -> None:
    with pytest.raises(BootstrapElementError):
        parse_elements([{"id": 5, "selected_by_percent": share}], model=CrowdElement)
