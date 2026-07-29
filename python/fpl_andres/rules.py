from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class RulesContractError(ValueError):
    """Raised when the live FPL payload cannot define a complete rules model."""


@dataclass(frozen=True)
class PositionRule:
    id: int
    code: str
    squad_count: int
    minimum_start: int
    maximum_start: int


@dataclass(frozen=True)
class ChipWindow:
    name: str
    start_event: int
    stop_event: int


@dataclass(frozen=True)
class RulesSnapshot:
    season: str
    source_hash: str
    squad_size: int
    starting_size: int
    club_limit: int
    budget_tenths: int
    transfer_cap: int
    selling_fee: float
    weekly_free_transfers: int
    max_extra_free_transfers: int
    positions: Mapping[int, PositionRule]
    chips: tuple[ChipWindow, ...]

    @property
    def max_free_transfers(self) -> int:
        return self.weekly_free_transfers + self.max_extra_free_transfers

    @classmethod
    def from_bootstrap(
        cls,
        bootstrap: Mapping[str, Any],
        *,
        season: str,
        source_hash: str,
        weekly_free_transfers: int,
    ) -> RulesSnapshot:
        if weekly_free_transfers < 1:
            raise RulesContractError("weekly_free_transfers must be a positive integer")

        settings = _required_mapping(bootstrap, "game_settings")
        position_payloads = _required_list(bootstrap, "element_types")
        chip_payloads = _required_list(bootstrap, "chips")

        positions: dict[int, PositionRule] = {}
        for index, payload in enumerate(position_payloads):
            path = f"element_types[{index}]"
            position = PositionRule(
                id=_required_int(payload, "id", path),
                code=_required_str(payload, "singular_name_short", path),
                squad_count=_required_int(payload, "squad_select", path),
                minimum_start=_required_int(payload, "squad_min_play", path),
                maximum_start=_required_int(payload, "squad_max_play", path),
            )
            if position.id in positions:
                raise RulesContractError(f"duplicate position id: {position.id}")
            positions[position.id] = position

        chips: list[ChipWindow] = []
        for index, payload in enumerate(chip_payloads):
            path = f"chips[{index}]"
            chip = ChipWindow(
                name=_required_str(payload, "name", path),
                start_event=_required_int(payload, "start_event", path),
                stop_event=_required_int(payload, "stop_event", path),
            )
            chips.append(chip)

        return cls(
            season=season,
            source_hash=source_hash,
            squad_size=_required_int(settings, "squad_squadsize", "game_settings"),
            starting_size=_required_int(settings, "squad_squadplay", "game_settings"),
            club_limit=_required_int(settings, "squad_team_limit", "game_settings"),
            budget_tenths=_required_int(settings, "squad_total_spend", "game_settings"),
            transfer_cap=_required_int(settings, "transfers_cap", "game_settings"),
            selling_fee=_required_number(settings, "transfers_sell_on_fee", "game_settings"),
            weekly_free_transfers=weekly_free_transfers,
            max_extra_free_transfers=_required_int(
                settings,
                "max_extra_free_transfers",
                "game_settings",
            ),
            positions=positions,
            chips=tuple(chips),
        )


def _required_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = _required_value(payload, key, "")
    if not isinstance(value, Mapping):
        raise RulesContractError(f"{key} must be an object")
    return value


def _required_list(payload: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = _required_value(payload, key, "")
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise RulesContractError(f"{key} must be an array of objects")
    return value


def _required_value(payload: Mapping[str, Any], key: str, parent: str) -> Any:
    path = f"{parent}.{key}" if parent else key
    if key not in payload:
        raise RulesContractError(f"missing required rule: {path}")
    return payload[key]


def _required_int(payload: Mapping[str, Any], key: str, parent: str) -> int:
    value = _required_value(payload, key, parent)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RulesContractError(f"{parent}.{key} must be an integer")
    return value


def _required_number(payload: Mapping[str, Any], key: str, parent: str) -> float:
    value = _required_value(payload, key, parent)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise RulesContractError(f"{parent}.{key} must be numeric")
    return float(value)


def _required_str(payload: Mapping[str, Any], key: str, parent: str) -> str:
    value = _required_value(payload, key, parent)
    if not isinstance(value, str) or not value:
        raise RulesContractError(f"{parent}.{key} must be a non-empty string")
    return value
