"""Archive CSV to schema-row normalisation.

Archive headers drift between seasons. A column this product depends on is
either present or the ingest fails loudly; a missing column is never defaulted,
because a silent zero would be indistinguishable from an observed zero and would
poison every rate derived from it.

Genuinely season-scoped columns (``expected_goals`` before 2022/23,
``defensive_contribution`` before 2025/26) are declared optional and normalise to
SQL ``NULL``, which is a statement that the observation does not exist rather
than a claim that it was zero.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final

__all__ = [
    "ColumnMappingError",
    "normalise_fixtures",
    "normalise_gameweek_stats",
    "normalise_players",
    "normalise_teams",
]


class ColumnMappingError(ValueError):
    """Raised when an archive CSV lacks a column the schema depends on."""


# Columns that must exist in every supported season of a gameweek file.
_GAMEWEEK_REQUIRED: Final = (
    "element",
    "fixture",
    "round",
    "minutes",
    "total_points",
    "goals_scored",
    "assists",
    "clean_sheets",
    "goals_conceded",
    "own_goals",
    "penalties_saved",
    "penalties_missed",
    "yellow_cards",
    "red_cards",
    "saves",
    "bonus",
    "bps",
    "value",
    "was_home",
)

# Present only in some seasons. Absent means "not observed", which is NULL.
_GAMEWEEK_OPTIONAL_NUMERIC: Final = (
    "influence",
    "creativity",
    "threat",
    "ict_index",
    "expected_goals",
    "expected_assists",
    "expected_goal_involvements",
    "expected_goals_conceded",
)

_PLAYERS_REQUIRED: Final = (
    "id",
    "code",
    "first_name",
    "second_name",
    "element_type",
    "team",
)

_TEAMS_REQUIRED: Final = ("id", "code", "name", "short_name")

_FIXTURES_REQUIRED: Final = ("id", "team_h", "team_a")


def _decode(raw_csv: bytes) -> str:
    """Decode an archive CSV, tolerating the older seasons' encoding.

    Seasons before 2019/20 are cp1252, later ones UTF-8. cp1252 maps all 256
    byte values so it cannot itself fail; trying UTF-8 first means a genuine
    UTF-8 file is never mis-decoded.
    """
    try:
        return raw_csv.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw_csv.decode("cp1252")


def _rows(raw_csv: bytes) -> tuple[list[dict[str, str]], tuple[str, ...]]:
    reader = csv.DictReader(io.StringIO(_decode(raw_csv), newline=""))
    if reader.fieldnames is None:
        raise ColumnMappingError("archive CSV must include a header")
    header = tuple(reader.fieldnames)
    _reject_ambiguous_header(header)
    parsed: list[dict[str, str]] = []
    for row in reader:
        parsed.append({key: ("" if value is None else value) for key, value in row.items() if key})
    return parsed, header


def _reject_ambiguous_header(header: Sequence[str]) -> None:
    """Refuse a header that cannot be read unambiguously.

    `csv.DictReader` keys by name, so a repeated column silently keeps only the
    last occurrence. An archive that published `total_points` twice would ingest
    one of them with nothing to say which, and the corpus would be wrong in a
    way no later check could detect.

    Column *order* is deliberately not checked: reading by name makes a
    reordered header harmless, and rejecting one would break ingestion for a
    change that cannot affect the data.
    """
    duplicates = sorted(name for name, count in Counter(header).items() if count > 1)
    if duplicates:
        raise ColumnMappingError(
            f"archive CSV repeats column(s) {', '.join(duplicates)}; the reader keys "
            "by name, so only the last of each would survive"
        )
    if any(name is None or not name.strip() for name in header):
        raise ColumnMappingError("archive CSV has an unnamed column in its header")


def _require(header: Sequence[str], required: Iterable[str], label: str) -> None:
    missing = sorted(set(required) - set(header))
    if missing:
        raise ColumnMappingError(f"{label} is missing required columns: {', '.join(missing)}")


def _int(value: str | None, column: str = "?") -> int | None:
    if value is None or value.strip() == "":
        return None
    try:
        # Some archive rows carry floats in integer columns ("90.0").
        return int(float(value))
    except ValueError as error:
        raise ColumnMappingError(
            f"column {column!r} should hold a number and holds {value.strip()!r}"
        ) from error


def _required_int(row: Mapping[str, str], column: str) -> int:
    parsed = _int(row.get(column), column)
    if parsed is None:
        raise ColumnMappingError(f"column {column!r} must carry a value on every row")
    return parsed


def _float(value: str | None, column: str = "?") -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError as error:
        raise ColumnMappingError(
            f"column {column!r} should hold a number and holds {value.strip()!r}"
        ) from error


# What the archive has actually used for booleans. Anything else is a format
# change, not a false: reading an unrecognised value as False would have turned
# every fixture into an away fixture the day the archive switched to H/A.
_TRUE = frozenset({"true", "1", "t", "yes"})
_FALSE = frozenset({"false", "0", "f", "no"})


def _bool(value: str | None, column: str = "?") -> bool | None:
    if value is None or value.strip() == "":
        return None
    normalised = value.strip().casefold()
    if normalised in _TRUE:
        return True
    if normalised in _FALSE:
        return False
    raise ColumnMappingError(f"column {column!r} should hold a boolean and holds {value.strip()!r}")


def _text(value: str | None) -> str:
    return "" if value is None else value.strip()


def _timestamp(value: str | None) -> str | None:
    stamp = _text(value)
    return stamp or None


def normalise_gameweek_stats(
    raw_csv: bytes,
    *,
    season: str,
    gameweek: int,
    element_codes: Mapping[int, int],
    source_snapshot_id: str,
) -> list[dict[str, Any]]:
    """Normalise one ``gws/gw{N}.csv`` into ``element_gameweek_stats`` rows.

    ``element_codes`` maps the season-scoped element id to FPL's cross-season
    player code and must already be populated from ``players_raw.csv``.
    """
    rows, header = _rows(raw_csv)
    _require(header, _GAMEWEEK_REQUIRED, f"{season} gw{gameweek}")

    normalised: list[dict[str, Any]] = []
    for row in rows:
        element_id = _required_int(row, "element")
        code = element_codes.get(element_id)
        if code is None:
            raise ColumnMappingError(
                f"{season} gw{gameweek} references element {element_id} "
                "that is absent from players_raw.csv"
            )

        recorded_round = _required_int(row, "round")
        if recorded_round != gameweek:
            raise ColumnMappingError(
                f"{season} gw{gameweek} contains a row for round {recorded_round}"
            )

        record: dict[str, Any] = {
            "season": season,
            "gameweek": gameweek,
            "element_id": element_id,
            "element_code": code,
            # Double and triple gameweeks put a player in more than one fixture
            # per gameweek, so the fixture is part of the row's identity.
            "fixture_id": _required_int(row, "fixture"),
            "opponent_team": _int(row.get("opponent_team"), "opponent_team"),
            "was_home": _bool(row.get("was_home"), "was_home"),
            "kickoff_time": _timestamp(row.get("kickoff_time")),
            "minutes": _required_int(row, "minutes"),
            "starts": _int(row.get("starts"), "starts"),
            "goals_scored": _required_int(row, "goals_scored"),
            "assists": _required_int(row, "assists"),
            "clean_sheets": _required_int(row, "clean_sheets"),
            "goals_conceded": _required_int(row, "goals_conceded"),
            "own_goals": _required_int(row, "own_goals"),
            "penalties_saved": _required_int(row, "penalties_saved"),
            "penalties_missed": _required_int(row, "penalties_missed"),
            "yellow_cards": _required_int(row, "yellow_cards"),
            "red_cards": _required_int(row, "red_cards"),
            "saves": _required_int(row, "saves"),
            "bonus": _required_int(row, "bonus"),
            "bps": _required_int(row, "bps"),
            "total_points": _required_int(row, "total_points"),
            "value": _int(row.get("value"), "value"),
            "selected": _int(row.get("selected"), "selected"),
            "transfers_in": _int(row.get("transfers_in"), "transfers_in"),
            "transfers_out": _int(row.get("transfers_out"), "transfers_out"),
            # Observed defensive-contribution labels begin in 2025/26.
            "defensive_contribution": _int(
                row.get("defensive_contribution"), "defensive_contribution"
            ),
            # Components behind that label. Defenders qualify on CBIT,
            # midfielders and forwards on CBIRT, so the split is required.
            "clearances_blocks_interceptions": _int(
                row.get("clearances_blocks_interceptions"), "clearances_blocks_interceptions"
            ),
            "tackles": _int(row.get("tackles"), "tackles"),
            "recoveries": _int(row.get("recoveries"), "recoveries"),
            "source_snapshot_id": source_snapshot_id,
        }
        for column in _GAMEWEEK_OPTIONAL_NUMERIC:
            record[column] = _float(row.get(column), column)
        normalised.append(record)

    return _drop_identical_duplicates(normalised, season=season, gameweek=gameweek)


def _drop_identical_duplicates(
    rows: list[dict[str, Any]], *, season: str, gameweek: int
) -> list[dict[str, Any]]:
    """Collapse rows the archive repeats verbatim.

    Some elements are emitted twice per gameweek with byte-identical stats, so
    keeping one is lossless. A repeated key carrying *different* values is a
    real upstream conflict and is raised rather than silently resolved, because
    picking a winner would be an invented fact.
    """
    kept: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        key = (row["element_id"], row["fixture_id"])
        existing = kept.get(key)
        if existing is None:
            kept[key] = row
            continue
        if existing != row:
            raise ColumnMappingError(
                f"{season} gw{gameweek} repeats element {key[0]} in fixture {key[1]} "
                "with conflicting values"
            )
    return list(kept.values())


def normalise_players(
    raw_csv: bytes,
    *,
    season: str,
    source_snapshot_id: str,
) -> list[dict[str, Any]]:
    """Normalise ``players_raw.csv`` into ``elements`` rows."""
    rows, header = _rows(raw_csv)
    _require(header, _PLAYERS_REQUIRED, f"{season} players_raw")

    normalised: list[dict[str, Any]] = []
    for row in rows:
        first_name = _text(row.get("first_name"))
        second_name = _text(row.get("second_name"))
        normalised.append(
            {
                "season": season,
                "element_id": _required_int(row, "id"),
                "code": _required_int(row, "code"),
                "first_name": first_name,
                "second_name": second_name,
                "web_name": _text(row.get("web_name")) or second_name or first_name,
                "element_type": _required_int(row, "element_type"),
                "team_id": _required_int(row, "team"),
                "start_cost": _int(row.get("now_cost"), "now_cost"),
                "source_snapshot_id": source_snapshot_id,
            }
        )
    return normalised


def normalise_teams(
    raw_csv: bytes,
    *,
    season: str,
    source_snapshot_id: str,
) -> list[dict[str, Any]]:
    """Normalise ``teams.csv`` into ``teams`` rows."""
    rows, header = _rows(raw_csv)
    _require(header, _TEAMS_REQUIRED, f"{season} teams")

    normalised: list[dict[str, Any]] = []
    for row in rows:
        normalised.append(
            {
                "season": season,
                "team_id": _required_int(row, "id"),
                "code": _required_int(row, "code"),
                "name": _text(row.get("name")),
                "short_name": _text(row.get("short_name")),
                "strength": _int(row.get("strength"), "strength"),
                "strength_overall_home": _int(
                    row.get("strength_overall_home"), "strength_overall_home"
                ),
                "strength_overall_away": _int(
                    row.get("strength_overall_away"), "strength_overall_away"
                ),
                "strength_attack_home": _int(
                    row.get("strength_attack_home"), "strength_attack_home"
                ),
                "strength_attack_away": _int(
                    row.get("strength_attack_away"), "strength_attack_away"
                ),
                "strength_defence_home": _int(
                    row.get("strength_defence_home"), "strength_defence_home"
                ),
                "strength_defence_away": _int(
                    row.get("strength_defence_away"), "strength_defence_away"
                ),
                "source_snapshot_id": source_snapshot_id,
            }
        )
    return normalised


def normalise_fixtures(
    raw_csv: bytes,
    *,
    season: str,
    source_snapshot_id: str,
) -> list[dict[str, Any]]:
    """Normalise ``fixtures.csv`` into ``fixtures`` rows."""
    rows, header = _rows(raw_csv)
    _require(header, _FIXTURES_REQUIRED, f"{season} fixtures")

    normalised: list[dict[str, Any]] = []
    for row in rows:
        home_score = _int(row.get("team_h_score"), "team_h_score")
        away_score = _int(row.get("team_a_score"), "team_a_score")
        # The schema requires both scores or neither.
        if (home_score is None) != (away_score is None):
            home_score = None
            away_score = None
        finished = _bool(row.get("finished"), "finished") or False
        normalised.append(
            {
                "season": season,
                "fixture_id": _required_int(row, "id"),
                "event": _int(row.get("event"), "event"),
                "kickoff_time": _timestamp(row.get("kickoff_time")),
                "team_h": _required_int(row, "team_h"),
                "team_a": _required_int(row, "team_a"),
                "team_h_score": home_score,
                "team_a_score": away_score,
                "team_h_difficulty": _int(row.get("team_h_difficulty"), "team_h_difficulty"),
                "team_a_difficulty": _int(row.get("team_a_difficulty"), "team_a_difficulty"),
                "finished": finished and home_score is not None,
                "source_snapshot_id": source_snapshot_id,
            }
        )
    return normalised
