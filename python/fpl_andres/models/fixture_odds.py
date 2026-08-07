"""Reading the published odds artifact into the quantity the model speaks.

`cli.ingest_odds` writes one row per fixture keyed by FPL club code. Nothing
downstream wants a fixture row: the projector asks "what is this club's chance
of a clean sheet in this match, and how many goals do I expect them to score",
and this turns one into the other.

Both sides of a fixture become two club-level views, because a clean sheet
belongs to the side keeping it and is driven by the *other* side's expected
goals. Getting that backwards is the easiest mistake here and the hardest to
notice, so the join is done once, in one place, with a test that pins it.

A club with no priced fixture gets nothing back. It does not get a league
average: a fixture with no market is a fixture with no evidence, which is a
different thing from a fixture priced level, and the caller has to decide what
to do about it rather than being handed a number that looks measured.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "ClubMatchOdds",
    "OddsArtifactError",
    "club_views",
    "load_fixture_odds",
]


class OddsArtifactError(ValueError):
    """Raised when the published odds artifact cannot be read."""


@dataclass(frozen=True)
class ClubMatchOdds:
    """One club's view of one priced fixture."""

    club: str
    opponent: str
    home: bool
    kickoff: datetime | None
    #: Goals this club is expected to score.
    expected_goals: float
    #: Goals the opponent is expected to score. The clean sheet follows from it.
    opponent_expected_goals: float
    clean_sheet: float
    draw_residual: float


def _number(row: Mapping[str, Any], key: str) -> float:
    value = row.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise OddsArtifactError(f"fixture row is missing a numeric {key}")
    return float(value)


def _kickoff(row: Mapping[str, Any]) -> datetime | None:
    raw = row.get("kickoff")
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise OddsArtifactError("kickoff must be an ISO timestamp or null")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise OddsArtifactError(f"kickoff {raw!r} is not an ISO timestamp") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def load_fixture_odds(path: Path) -> list[dict[str, Any]]:
    """Read the artifact, refusing a shape this reader was not written against."""
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise OddsArtifactError(
            f"no odds artifact at {path}; run the Ingest Bookmaker Odds workflow"
        ) from error
    except json.JSONDecodeError as error:
        raise OddsArtifactError(f"{path} is not valid JSON: {error}") from error

    if not isinstance(artifact, dict):
        raise OddsArtifactError(f"{path} is not an object")
    fixtures = artifact.get("fixtures")
    if not isinstance(fixtures, list):
        raise OddsArtifactError(f"{path} carries no fixtures list")
    return [row for row in fixtures if isinstance(row, dict)]


def club_views(fixtures: list[dict[str, Any]]) -> dict[str, list[ClubMatchOdds]]:
    """Both clubs' views of every priced fixture, keyed by FPL club code."""
    views: dict[str, list[ClubMatchOdds]] = {}

    for row in fixtures:
        home = row.get("home")
        away = row.get("away")
        if not isinstance(home, str) or not isinstance(away, str):
            raise OddsArtifactError("a fixture row is missing a club code")

        home_goals = _number(row, "homeExpectedGoals")
        away_goals = _number(row, "awayExpectedGoals")
        residual = _number(row, "drawResidual")
        kickoff = _kickoff(row)

        # The clean sheet is the OPPONENT failing to score, so each side's
        # clean sheet is driven by the other side's expected goals.
        views.setdefault(home, []).append(
            ClubMatchOdds(
                club=home,
                opponent=away,
                home=True,
                kickoff=kickoff,
                expected_goals=home_goals,
                opponent_expected_goals=away_goals,
                clean_sheet=_number(row, "homeCleanSheet"),
                draw_residual=residual,
            )
        )
        views.setdefault(away, []).append(
            ClubMatchOdds(
                club=away,
                opponent=home,
                home=False,
                kickoff=kickoff,
                expected_goals=away_goals,
                opponent_expected_goals=home_goals,
                clean_sheet=_number(row, "awayCleanSheet"),
                draw_residual=residual,
            )
        )

    for matches in views.values():
        matches.sort(key=lambda match: (match.kickoff is None, match.kickoff))
    return views
