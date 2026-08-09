"""The published artifacts have a shape, and changing it must be deliberate.

Five JSON files are imported directly by the web app. A
publisher that renamed a field or dropped one would break the site at runtime,
and nothing between the CLI writing the file and the browser reading it would
have said so.

These pin the *shape*, not the values: the numbers change on every publish and
asserting them would make the tests fail for the one reason that is not a bug.
A renamed key, a changed type or a missing field fails here instead.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

_DATA = Path(__file__).resolve().parents[2] / "apps" / "web" / "src" / "data"


def _artifact(name: str) -> Any:
    return json.loads((_DATA / f"{name}.json").read_text(encoding="utf-8"))


def _require_keys(payload: dict[str, Any], expected: set[str], label: str) -> None:
    missing = sorted(expected - set(payload))
    assert missing == [], f"{label} lost required key(s): {missing}"


@pytest.mark.parametrize(
    "name",
    ["projections", "opening-squad", "validation", "cohort", "projections-meta", "fpl500"],
)
def test_every_artifact_records_when_it_was_generated(name: str) -> None:
    """Without this the site cannot say how old what it is showing is."""
    generated = _artifact(name)["generatedAt"]

    parsed = datetime.fromisoformat(generated)
    assert parsed.tzinfo is not None, f"{name} generatedAt must carry a timezone"


def test_fpl500_shape() -> None:
    """The ranking the site lists, and the sweep position that produced it.

    `sweptTo` is here because the ranking is only as good as how much of the
    register has been read, and four fifths of it has not. A page showing the
    five hundred without saying that is claiming more than it has.
    """
    payload = _artifact("fpl500")
    _require_keys(
        payload,
        {
            "catalogueSize",
            "generatedAt",
            "listed",
            "managers",
            "minimumCoverage",
            "portfolioEvents",
            "scoreAtRank",
            "seasonsCounted",
            "settings",
            "size",
            "sweptTo",
        },
        "fpl500",
    )
    assert payload["managers"], "fpl500 must list the head of the ranking"
    assert len(payload["managers"]) == payload["listed"]
    _require_keys(
        payload["managers"][0],
        {"bestPercentile", "entryId", "latestSeason", "rank", "score", "seasons"},
        "fpl500 manager",
    )
    # The fund is the point of the page, so its absence has to be a published
    # fact rather than an empty section nobody can explain.
    assert isinstance(payload["portfolioEvents"], list)


def test_projections_shape() -> None:
    payload = _artifact("projections")
    _require_keys(
        payload,
        {"basis", "clubs", "generatedAt", "players", "season", "throughGameweek"},
        "projections",
    )
    assert payload["players"], "projections must carry players"
    _require_keys(
        payload["players"][0],
        {
            "appearances",
            "blankRate",
            "ceiling",
            "code",
            "evidence",
            "expectedMinutes",
            "expectedPoints",
            "floor",
            "median",
            "name",
            "position",
            "priceTenths",
            "probabilityAppear",
            "probabilityStart",
            "recentMatches",
            "recentMinutes",
            "recentStarts",
            "returnRate",
        },
        "projections.players[]",
    )
    _require_keys(
        payload["clubs"][0],
        {"attackAway", "attackHome", "code", "defenceAway", "defenceHome", "shortName"},
        "projections.clubs[]",
    )


def test_every_projection_carries_an_evidence_level() -> None:
    """The repository rule: a recommendation without an evidence label is not
    one this project is allowed to publish."""
    allowed = {"observed", "inferred", "experimental", "unavailable"}
    levels = {player["evidence"] for player in _artifact("projections")["players"]}

    assert levels <= allowed, f"unknown evidence level(s): {sorted(levels - allowed)}"


def test_opening_squad_shape() -> None:
    payload = _artifact("opening-squad")
    _require_keys(
        payload,
        {
            "basis",
            "bitPart",
            "budgetTenths",
            "consideredPlayers",
            "expectedPoints",
            "generatedAt",
            "picks",
            "spentTenths",
            "startRateFloor",
            "unavailable",
            "withoutRecord",
        },
        "opening-squad",
    )
    _require_keys(
        payload["picks"][0],
        {
            "adjusted",
            "club",
            "code",
            "fixtures",
            "name",
            "position",
            "priceTenths",
            "ratedFixtures",
            "record",
            "run",
            "startRate",
            "starter",
        },
        "opening-squad.picks[]",
    )


def test_the_published_squad_is_legal() -> None:
    """A shape check that also checks the rules, because an illegal squad is a
    worse failure than a renamed field and costs nothing extra to catch."""
    payload = _artifact("opening-squad")
    picks = payload["picks"]

    assert len(picks) == 15
    assert sum(1 for pick in picks if pick["starter"]) == 11
    assert payload["spentTenths"] <= payload["budgetTenths"]

    by_club: dict[str, int] = {}
    for pick in picks:
        by_club[pick["club"]] = by_club.get(pick["club"], 0) + 1
    assert max(by_club.values()) <= 3, f"more than three from one club: {by_club}"

    by_position: dict[str, int] = {}
    for pick in picks:
        by_position[pick["position"]] = by_position.get(pick["position"], 0) + 1
    assert by_position == {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}


def test_validation_shape() -> None:
    payload = _artifact("validation")
    _require_keys(payload, {"generatedAt", "league", "seasons"}, "validation")
    _require_keys(
        payload["seasons"][0],
        {
            "elements",
            "expectedGoalsCoverage",
            "firstScoredGameweek",
            "gameweeks",
            "gameweeksPlayed",
            "league",
            "methods",
            "missingGameweeks",
            "rows",
            "season",
        },
        "validation.seasons[]",
    )


def test_cohort_shape() -> None:
    _require_keys(
        _artifact("cohort"),
        {
            "bestRankMedian",
            "entriesMissing",
            "entriesSwept",
            "entriesWithHistory",
            "generatedAt",
            "managers",
            "persistenceMeasurable",
            "persistenceNote",
            "qualifyingSeasonCounts",
            "rankCeiling",
            "seasonsRepresented",
            "sinceSeasonStartYear",
            "sweepComplete",
        },
        "cohort",
    )


def test_projection_metadata_matches_the_projections_it_describes() -> None:
    """The two files are written by the same command and read by different
    components. Drift between them shows the site a season the projections are
    not for."""
    meta = _artifact("projections-meta")
    projections = _artifact("projections")

    for field in ("season", "basis", "throughGameweek", "generatedAt"):
        assert meta[field] == projections[field], f"{field} disagrees between the two"
