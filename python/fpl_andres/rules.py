from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

from fpl_andres.positions import Position


class RulesContractError(ValueError):
    """Raised when the live FPL payload cannot define a complete rules model."""


PUBLISHED_SCORING_FIELDS = frozenset(
    {
        "assists",
        "bonus",
        "bps",
        "clean_sheets",
        "clearances_blocks_interceptions",
        "creativity",
        "defensive_contribution",
        "expected_assists",
        "expected_goal_involvements",
        "expected_goals",
        "expected_goals_conceded",
        "goals_conceded",
        "goals_scored",
        "ict_index",
        "influence",
        "long_play",
        "mng_clean_sheets",
        "mng_draw",
        "mng_goals_scored",
        "mng_loss",
        "mng_underdog_draw",
        "mng_underdog_win",
        "mng_win",
        "own_goals",
        "penalties_missed",
        "penalties_saved",
        "recoveries",
        "red_cards",
        "saves",
        "short_play",
        "special_multiplier",
        "starts",
        "tackles",
        "threat",
        "yellow_cards",
    }
)
POSITION_SCORING_FIELDS = frozenset(
    {
        "clean_sheets",
        "defensive_contribution",
        "goals_conceded",
        "goals_scored",
        "mng_clean_sheets",
        "mng_draw",
        "mng_goals_scored",
        "mng_underdog_draw",
        "mng_underdog_win",
        "mng_win",
    }
)
SCALAR_SCORING_FIELDS = PUBLISHED_SCORING_FIELDS - POSITION_SCORING_FIELDS


@dataclass(frozen=True)
class PositionRule:
    id: int
    code: str
    squad_count: int
    minimum_start: int
    maximum_start: int


@dataclass(frozen=True)
class ChipWindow:
    id: int
    name: str
    chip_type: Literal["transfer", "team"]
    start_event: int
    stop_event: int
    pick_multiplier: int | None


@dataclass(frozen=True)
class ScoringRules:
    published_fields: frozenset[str]
    long_play: int
    short_play: int
    goals_conceded: Mapping[str, int]
    saves: int
    goals_scored: Mapping[str, int]
    assists: int
    clean_sheets: Mapping[str, int]
    penalties_saved: int
    penalties_missed: int
    yellow_cards: int
    red_cards: int
    own_goals: int
    bonus: int
    special_multiplier: int
    defensive_contribution: Mapping[str, int]


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
    sell_at_purchase_price: bool
    currency_multiplier: int
    weekly_free_transfers: int
    max_extra_free_transfers: int
    scoring: ScoringRules
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

        validate_published_bootstrap_contract(bootstrap)
        game_config = _required_mapping(bootstrap, "game_config")
        configured_rules = _required_mapping(game_config, "rules", "game_config")
        scoring_payload = _required_mapping(game_config, "scoring", "game_config")
        position_payloads = _required_list(bootstrap, "element_types")
        chip_payloads = _required_list(bootstrap, "chips")

        scoring = ScoringRules(
            published_fields=PUBLISHED_SCORING_FIELDS,
            long_play=_required_int(scoring_payload, "long_play", "game_config.scoring"),
            short_play=_required_int(scoring_payload, "short_play", "game_config.scoring"),
            goals_conceded=_required_position_points(
                scoring_payload,
                "goals_conceded",
                "game_config.scoring",
            ),
            saves=_required_int(scoring_payload, "saves", "game_config.scoring"),
            goals_scored=_required_position_points(
                scoring_payload,
                "goals_scored",
                "game_config.scoring",
            ),
            assists=_required_int(scoring_payload, "assists", "game_config.scoring"),
            clean_sheets=_required_position_points(
                scoring_payload,
                "clean_sheets",
                "game_config.scoring",
            ),
            penalties_saved=_required_int(
                scoring_payload,
                "penalties_saved",
                "game_config.scoring",
            ),
            penalties_missed=_required_int(
                scoring_payload,
                "penalties_missed",
                "game_config.scoring",
            ),
            yellow_cards=_required_int(
                scoring_payload,
                "yellow_cards",
                "game_config.scoring",
            ),
            red_cards=_required_int(scoring_payload, "red_cards", "game_config.scoring"),
            own_goals=_required_int(scoring_payload, "own_goals", "game_config.scoring"),
            bonus=_required_int(scoring_payload, "bonus", "game_config.scoring"),
            special_multiplier=_required_int(
                scoring_payload,
                "special_multiplier",
                "game_config.scoring",
            ),
            defensive_contribution=_required_position_points(
                scoring_payload,
                "defensive_contribution",
                "game_config.scoring",
            ),
        )

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
            chip_type = _required_chip_type(payload, "chip_type", path)
            overrides_path = f"{path}.overrides"
            overrides = _required_mapping(payload, "overrides", path)
            _required_mapping(overrides, "rules", overrides_path)
            _required_mapping(overrides, "scoring", overrides_path)
            _required_list(overrides, "element_types", overrides_path)
            chip = ChipWindow(
                id=_required_int(payload, "id", path),
                name=_required_str(payload, "name", path),
                chip_type=chip_type,
                start_event=_required_int(payload, "start_event", path),
                stop_event=_required_int(payload, "stop_event", path),
                pick_multiplier=_required_nullable_int(
                    overrides,
                    "pick_multiplier",
                    overrides_path,
                ),
            )
            chips.append(chip)

        return cls(
            season=season,
            source_hash=source_hash,
            squad_size=_required_int(
                configured_rules,
                "squad_squadsize",
                "game_config.rules",
            ),
            starting_size=_required_int(
                configured_rules,
                "squad_squadplay",
                "game_config.rules",
            ),
            club_limit=_required_int(
                configured_rules,
                "squad_team_limit",
                "game_config.rules",
            ),
            budget_tenths=_required_int(
                configured_rules,
                "squad_total_spend",
                "game_config.rules",
            ),
            transfer_cap=_required_int(
                configured_rules,
                "transfers_cap",
                "game_config.rules",
            ),
            selling_fee=_required_number(
                configured_rules,
                "transfers_sell_on_fee",
                "game_config.rules",
            ),
            sell_at_purchase_price=_required_bool(
                configured_rules,
                "element_sell_at_purchase_price",
                "game_config.rules",
            ),
            currency_multiplier=_required_int(
                configured_rules,
                "ui_currency_multiplier",
                "game_config.rules",
            ),
            weekly_free_transfers=weekly_free_transfers,
            max_extra_free_transfers=_required_int(
                configured_rules,
                "max_extra_free_transfers",
                "game_config.rules",
            ),
            scoring=scoring,
            positions=positions,
            chips=tuple(chips),
        )


def validate_published_bootstrap_contract(bootstrap: Mapping[str, Any]) -> None:
    settings = _required_mapping(bootstrap, "game_settings")
    game_config = _required_mapping(bootstrap, "game_config")
    configured_rules = _required_mapping(game_config, "rules", "game_config")
    mirrored_rule_keys = (
        "squad_squadsize",
        "squad_squadplay",
        "squad_team_limit",
        "squad_total_spend",
        "transfers_cap",
        "transfers_sell_on_fee",
        "max_extra_free_transfers",
        "element_sell_at_purchase_price",
        "ui_currency_multiplier",
    )
    for key in mirrored_rule_keys:
        _require_mirrored_rule_match(settings, configured_rules, key)

    scoring_payload = _required_mapping(game_config, "scoring", "game_config")
    _require_exact_keys(
        scoring_payload,
        expected=PUBLISHED_SCORING_FIELDS,
        parent="game_config.scoring",
    )
    for field in sorted(SCALAR_SCORING_FIELDS):
        _required_int(scoring_payload, field, "game_config.scoring")
    for field in sorted(POSITION_SCORING_FIELDS):
        _required_position_points(scoring_payload, field, "game_config.scoring")

    squad_size = _required_int(configured_rules, "squad_squadsize", "game_config.rules")
    starting_size = _required_int(
        configured_rules,
        "squad_squadplay",
        "game_config.rules",
    )
    position_ids: set[int] = set()
    squad_counts = 0
    minimum_starters = 0
    maximum_starters = 0
    for index, payload in enumerate(_required_list(bootstrap, "element_types")):
        path = f"element_types[{index}]"
        position_id = _required_int(payload, "id", path)
        if position_id in position_ids:
            raise RulesContractError(f"duplicate position id: {position_id}")
        position_ids.add(position_id)
        squad_count = _required_int(payload, "squad_select", path)
        minimum_start = _required_int(payload, "squad_min_play", path)
        maximum_start = _required_int(payload, "squad_max_play", path)
        if not 0 <= minimum_start <= maximum_start <= squad_count:
            raise RulesContractError(f"{path} has invalid formation bounds")
        squad_counts += squad_count
        minimum_starters += minimum_start
        maximum_starters += maximum_start
        _required_str(payload, "singular_name_short", path)
    if squad_counts != squad_size:
        raise RulesContractError("element_types squad counts do not match squad size")
    if not minimum_starters <= starting_size <= maximum_starters:
        raise RulesContractError("position formation bounds do not permit the starting size")

    chip_ids: set[int] = set()
    for index, payload in enumerate(_required_list(bootstrap, "chips")):
        path = f"chips[{index}]"
        chip_id = _required_int(payload, "id", path)
        if chip_id in chip_ids:
            raise RulesContractError(f"duplicate chip id: {chip_id}")
        chip_ids.add(chip_id)
        _required_str(payload, "name", path)
        _required_chip_type(payload, "chip_type", path)
        start_event = _required_int(payload, "start_event", path)
        stop_event = _required_int(payload, "stop_event", path)
        if not 1 <= start_event <= stop_event <= 38:
            raise RulesContractError(f"{path} has an invalid chip window")
        overrides_path = f"{path}.overrides"
        overrides = _required_mapping(payload, "overrides", path)
        _required_mapping(overrides, "rules", overrides_path)
        _required_mapping(overrides, "scoring", overrides_path)
        _required_list(overrides, "element_types", overrides_path)
        _required_nullable_int(overrides, "pick_multiplier", overrides_path)


def _required_mapping(
    payload: Mapping[str, Any],
    key: str,
    parent: str = "",
) -> Mapping[str, Any]:
    value = _required_value(payload, key, parent)
    if not isinstance(value, Mapping):
        path = f"{parent}.{key}" if parent else key
        raise RulesContractError(f"{path} must be an object")
    return value


def _required_position_points(
    payload: Mapping[str, Any],
    key: str,
    parent: str,
) -> Mapping[str, int]:
    values = _required_mapping(payload, key, parent)
    path = f"{parent}.{key}"
    return MappingProxyType(
        {position.code: _required_int(values, position.code, path) for position in Position}
    )


def _required_list(
    payload: Mapping[str, Any],
    key: str,
    parent: str = "",
) -> list[Mapping[str, Any]]:
    value = _required_value(payload, key, parent)
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        path = f"{parent}.{key}" if parent else key
        raise RulesContractError(f"{path} must be an array of objects")
    return value


def _required_value(payload: Mapping[str, Any], key: str, parent: str) -> Any:
    path = f"{parent}.{key}" if parent else key
    if key not in payload:
        raise RulesContractError(f"missing required rule: {path}")
    return payload[key]


def _rule_path(parent: str, key: str) -> str:
    """Audit item #18: one spelling of a rule's path.

    `_required_value` already handled an empty parent and the type checks below
    did not, so a top-level rule failed with a message beginning in a full stop.
    """
    return f"{parent}.{key}" if parent else key


def _wrong_type(parent: str, key: str, value: Any, expected: str) -> RulesContractError:
    """One wording for one class of failure.

    Audit item #18. "must be an integer" and "must be numeric" described the
    same thing two ways, so a reader could not tell whether they were different
    checks. They are not, and the message now names what arrived as well as what
    was wanted -- an FPL payload that starts sending "15" instead of 15 is a
    real change, and a message that says only "must be an integer" sends
    somebody to look at the wrong thing.
    """
    return RulesContractError(
        f"{_rule_path(parent, key)} must be {expected}, not {type(value).__name__}"
    )


def _required_int(payload: Mapping[str, Any], key: str, parent: str) -> int:
    value = _required_value(payload, key, parent)
    if not isinstance(value, int) or isinstance(value, bool):
        raise _wrong_type(parent, key, value, "an integer")
    return value


def _required_number(payload: Mapping[str, Any], key: str, parent: str) -> float:
    value = _required_value(payload, key, parent)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise _wrong_type(parent, key, value, "a number")
    return float(value)


def _required_bool(payload: Mapping[str, Any], key: str, parent: str) -> bool:
    value = _required_value(payload, key, parent)
    if not isinstance(value, bool):
        raise _wrong_type(parent, key, value, "a boolean")
    return value


def _required_nullable_int(payload: Mapping[str, Any], key: str, parent: str) -> int | None:
    value = _required_value(payload, key, parent)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise _wrong_type(parent, key, value, "an integer or null")
    return value


def _required_chip_type(
    payload: Mapping[str, Any],
    key: str,
    parent: str,
) -> Literal["transfer", "team"]:
    value = _required_str(payload, key, parent)
    if value == "transfer":
        return "transfer"
    if value == "team":
        return "team"
    raise RulesContractError(f"{parent}.{key} must be 'transfer' or 'team'")


def _require_mirrored_rule_match(
    settings: Mapping[str, Any],
    configured_rules: Mapping[str, Any],
    key: str,
) -> None:
    settings_value = _required_value(settings, key, "game_settings")
    configured_value = _required_value(configured_rules, key, "game_config.rules")
    if type(settings_value) is not type(configured_value) or settings_value != configured_value:
        raise RulesContractError(f"game_settings.{key} does not match game_config.rules.{key}")


def _require_exact_keys(
    payload: Mapping[str, Any],
    *,
    expected: frozenset[str],
    parent: str,
) -> None:
    actual = frozenset(payload)
    missing = sorted(expected - actual)
    if missing:
        raise RulesContractError(f"missing required rule: {parent}.{missing[0]}")
    unexpected = sorted(actual - expected)
    if unexpected:
        raise RulesContractError(f"unexpected rule field: {parent}.{unexpected[0]}")


def _required_str(payload: Mapping[str, Any], key: str, parent: str) -> str:
    value = _required_value(payload, key, parent)
    if not isinstance(value, str) or not value:
        raise RulesContractError(f"{parent}.{key} must be a non-empty string")
    return value


__all__ = [
    "ChipWindow",
    "PositionRule",
    "RulesContractError",
    "RulesSnapshot",
    "ScoringRules",
    "validate_published_bootstrap_contract",
]
