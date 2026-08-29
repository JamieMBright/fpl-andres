"""Between-seasons projection: a per-match rate, with no fixture to lean on.

The pre-season number is the one most likely to be over-read, so its boundaries
are pinned here: it must ignore the fixture list entirely, key on the code that
follows a player between seasons, and stay silent about anyone without evidence.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus
from fpl_andres.backtesting.fixtures import Fixture, TeamStrength
from fpl_andres.backtesting.projector import project_next_match
from fpl_andres.cli.publish_projections import (
    _clubs,
    _entry,
    _live_snapshots,
    corpus_from_live_snapshot,
    corpus_from_live_snapshots,
)

KICKOFF = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)
STEADY = 1
CAMEO = 2
TEAM = 1
OPPONENT = 2


def _row(gameweek: int, element_id: int, *, minutes: int, points: int) -> ElementRow:
    return ElementRow(
        gameweek=gameweek,
        element_id=element_id,
        element_code=element_id * 1000,
        fixture_id=gameweek * 10 + element_id,
        minutes=minutes,
        started=minutes >= 60,
        goals=1 if points >= 6 else 0,
        assists=0,
        expected_goals=0.5,
        expected_assists=0.2,
        total_points=points,
        price_tenths=70 + gameweek,
        selected=1000,
        kickoff_time=KICKOFF + timedelta(days=7 * gameweek),
        clean_sheets=0,
        saves=0,
        bonus=1,
        bps=18 + (gameweek % 5),
    )


def _corpus(*, with_fixtures: bool) -> SeasonCorpus:
    corpus = SeasonCorpus(season="2025-26")
    for element_id in (STEADY, CAMEO):
        corpus.position_by_element[element_id] = 4
        corpus.team_by_element[element_id] = TEAM
        corpus.name_by_element[element_id] = f"P{element_id}"
        corpus.code_by_element[element_id] = element_id * 1000

    for gameweek in range(1, 21):
        rows = [_row(gameweek, STEADY, minutes=90, points=6)]
        # Two brief appearances is not a season anyone can describe.
        if gameweek <= 2:
            rows.append(_row(gameweek, CAMEO, minutes=8, points=1))
        corpus.rows_by_gameweek[gameweek] = rows

    if with_fixtures:
        for event in range(1, 21):
            corpus.fixtures_by_event[event] = [
                Fixture(
                    fixture_id=event,
                    event=event,
                    team_h=TEAM,
                    team_a=OPPONENT,
                    kickoff_time=KICKOFF + timedelta(days=7 * event),
                    team_h_score=3,
                    team_a_score=0,
                    finished=True,
                )
            ]
    return corpus


class ProjectNextMatchTest(unittest.TestCase):
    def test_live_snapshot_builds_current_start_evidence(self) -> None:
        kickoff = datetime(2026, 8, 21, 19, 0, tzinfo=UTC)
        corpus = corpus_from_live_snapshot(
            {
                "season": "2026-27",
                "event": 1,
                "capturedAt": "2026-08-26T16:26:47Z",
                "roundComplete": True,
                "elements": [
                    {
                        "id": 7,
                        "stats": {
                            "minutes": 62,
                            "starts": 1,
                            "goals_scored": 0,
                            "assists": 0,
                            "expected_goals": "0.10",
                            "expected_assists": "0.20",
                            "total_points": 2,
                        },
                        "explain": [{"fixture": 101}],
                    }
                ],
            },
            {
                "elements": [
                    {
                        "id": 7,
                        "code": 7000,
                        "web_name": "Current",
                        "element_type": 3,
                        "team": 1,
                        "now_cost": 75,
                        "selected_by_percent": "10.0",
                        "transfers_in_event": 0,
                        "transfers_out_event": 0,
                        "status": "a",
                    }
                ],
                "teams": [{"id": 1, "code": 3, "short_name": "ARS", "name": "Arsenal"}],
            },
            [
                {
                    "id": 101,
                    "event": 1,
                    "team_h": 1,
                    "team_a": 2,
                    "kickoff_time": kickoff.isoformat(),
                }
            ],
        )

        [row] = corpus.rows_by_gameweek[1]
        self.assertEqual(corpus.season, "2026-27")
        self.assertEqual(row.minutes, 62)
        self.assertTrue(row.started)
        self.assertEqual(row.fixture_id, 101)
        self.assertEqual(row.kickoff_time, kickoff)

    def test_live_snapshot_refuses_an_unsourced_fixture_time(self) -> None:
        with self.assertRaisesRegex(ValueError, "fixture 101 kickoff"):
            corpus_from_live_snapshot(
                {
                    "season": "2026-27",
                    "event": 1,
                    "capturedAt": "2026-08-26T16:26:47Z",
                    "roundComplete": True,
                    "elements": [
                        {
                            "id": 7,
                            "stats": {"minutes": 62, "starts": 1},
                            "explain": [{"fixture": 101}],
                        }
                    ],
                },
                {
                    "elements": [
                        {
                            "id": 7,
                            "code": 7000,
                            "web_name": "Current",
                            "element_type": 3,
                            "team": 1,
                            "now_cost": 75,
                            "selected_by_percent": "10.0",
                            "transfers_in_event": 0,
                            "transfers_out_event": 0,
                            "status": "a",
                        }
                    ],
                    "teams": [{"id": 1, "code": 3, "short_name": "ARS", "name": "Arsenal"}],
                },
                [],
            )

    def test_live_snapshots_keep_every_settled_event(self) -> None:
        bootstrap = {
            "elements": [
                {
                    "id": 7,
                    "code": 7000,
                    "web_name": "Current",
                    "element_type": 3,
                    "team": 1,
                    "now_cost": 75,
                    "selected_by_percent": "10.0",
                    "transfers_in_event": 0,
                    "transfers_out_event": 0,
                    "status": "a",
                }
            ],
            "teams": [{"id": 1, "code": 3, "short_name": "ARS", "name": "Arsenal"}],
        }
        snapshots = [
            {
                "season": "2026-27",
                "event": event,
                "capturedAt": f"2026-08-{20 + event:02d}T20:00:00Z",
                "roundComplete": True,
                "elements": [
                    {
                        "id": 7,
                        "stats": {"minutes": 90, "starts": 1},
                        "explain": [{"fixture": 100 + event}],
                    }
                ],
            }
            for event in (1, 2)
        ]
        fixtures = [
            {
                "id": 100 + event,
                "event": event,
                "team_h": 1,
                "team_a": 2,
                "team_h_score": 2,
                "team_a_score": 0,
                "finished": True,
                "kickoff_time": f"2026-08-{20 + event:02d}T19:00:00Z",
            }
            for event in (1, 2)
        ]

        corpus = corpus_from_live_snapshots(snapshots, bootstrap, fixtures)

        self.assertEqual(sorted(corpus.rows_by_gameweek), [1, 2])
        self.assertEqual(sorted(corpus.fixtures_by_event), [1, 2])
        self.assertEqual(corpus.fixtures_by_event[1][0].team_h_score, 2)
        self.assertEqual(corpus.last_event, 2)

    def test_live_directory_skips_the_week_still_being_played(self) -> None:
        """The corpus is realised points, so a live round is not one of them.

        The same directory now also carries the week in progress, captured for
        the xStart posterior. Scoring it here would grade half-played matches as
        final, so the directory selects the settled events and leaves the rest.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for event, complete in ((1, True), (2, False)):
                (root / f"gw{event:02d}.json").write_text(
                    json.dumps(
                        {
                            "season": "2026-27",
                            "event": event,
                            "capturedAt": f"2026-08-{20 + event:02d}T20:00:00Z",
                            "roundComplete": complete,
                            "elements": [],
                        }
                    ),
                    encoding="utf-8",
                )

            snapshots = _live_snapshots(root)

        self.assertEqual([snapshot["event"] for snapshot in snapshots], [1])

    def test_live_directory_without_a_settled_event_is_an_error(self) -> None:
        """Silence here would publish a projection with no current season in it."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "gw01.json").write_text(
                json.dumps(
                    {
                        "season": "2026-27",
                        "event": 1,
                        "capturedAt": "2026-08-21T20:00:00Z",
                        "roundComplete": False,
                        "elements": [],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                _live_snapshots(root)

    def test_a_named_live_file_still_has_to_be_settled(self) -> None:
        """Asking for one event by name is a claim that it is finished."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gw02.json"
            path.write_text(
                json.dumps(
                    {
                        "season": "2026-27",
                        "event": 2,
                        "capturedAt": "2026-08-22T20:00:00Z",
                        "roundComplete": False,
                        "elements": [],
                    }
                ),
                encoding="utf-8",
            )

            snapshots = _live_snapshots(path)

        self.assertEqual([snapshot["event"] for snapshot in snapshots], [2])

    def test_club_strength_carries_by_code_until_current_sample_is_ready(self) -> None:
        previous = SeasonCorpus(season="2025-26")
        previous.code_by_team = {11: 3, 12: 7}
        current = SeasonCorpus(season="2026-27")
        current.code_by_team = {1: 3, 2: 7, 3: 91}
        current.short_name_by_team = {1: "ARS", 2: "AVL", 3: "LEE"}
        current.fixtures_by_event = {
            event: [
                Fixture(
                    fixture_id=event,
                    event=event,
                    team_h=1,
                    team_a=2 if event == 1 else 3,
                    kickoff_time=KICKOFF + timedelta(days=7 * event),
                    team_h_score=2,
                    team_a_score=0,
                    finished=True,
                )
            ]
            for event in range(1, 6)
        }
        carried_arsenal = TeamStrength(1.1, 1.05, 0.8, 0.85)
        carried_villa = TeamStrength(0.9, 0.85, 1.2, 1.15)
        current_arsenal = TeamStrength(1.4, 1.3, 0.6, 0.7)
        premature_villa = TeamStrength(1.3, 1.2, 0.7, 0.8)

        with patch(
            "fpl_andres.cli.publish_projections._strength",
            side_effect=[
                {1: current_arsenal, 2: premature_villa},
                {11: carried_arsenal, 12: carried_villa},
            ],
        ):
            clubs = _clubs(current, previous)

        by_code = {club["code"]: club for club in clubs}
        self.assertEqual(by_code[3]["attackHome"], 1.4)
        self.assertEqual(by_code[3]["strengthBasis"], "current-season fitted")
        self.assertEqual(by_code[7]["attackHome"], 0.9)
        self.assertEqual(by_code[7]["strengthBasis"], "carried fitted")
        self.assertEqual(by_code[7]["sourceSeason"], "2025-26")
        self.assertNotIn(91, by_code)

    def test_projects_a_single_match_not_a_season(self) -> None:
        [projection] = [
            entry
            for entry in project_next_match(_corpus(with_fixtures=False))
            if entry.element_id == STEADY
        ]

        # Even an ever-present is pulled away from certainty: model 8.9's
        # two-event memory and four-event prior were selected on held-out
        # xStart rather than tuned to make a full campaign read as ninety.
        self.assertGreater(projection.expected_minutes, 60.0)
        self.assertLess(projection.expected_minutes, 80.0)
        # One match of a player scoring six a week, not twenty.
        self.assertGreater(projection.expected_points, 2.0)
        self.assertLess(projection.expected_points, 12.0)

    def test_the_fixture_list_makes_no_difference(self) -> None:
        """A schedule that has already been played must not tilt next season."""
        without = {
            entry.code: entry.expected_points
            for entry in project_next_match(_corpus(with_fixtures=False))
        }
        with_schedule = {
            entry.code: entry.expected_points
            for entry in project_next_match(_corpus(with_fixtures=True))
        }

        self.assertEqual(without.keys(), with_schedule.keys())
        for code, points in without.items():
            self.assertAlmostEqual(points, with_schedule[code], places=6)

    def test_publishes_a_bps_distribution_for_bonus_ranking(self) -> None:
        [projection] = [
            entry
            for entry in project_next_match(_corpus(with_fixtures=False))
            if entry.element_id == STEADY
        ]

        self.assertGreater(projection.expected_bps, 0.0)
        self.assertGreater(projection.bps_deviation, 0.0)
        artifact = _entry(projection)
        self.assertEqual(artifact["expectedBps"], round(projection.expected_bps, 3))
        self.assertEqual(artifact["bpsDeviation"], round(projection.bps_deviation, 3))

    def test_publishes_start_and_sixty_minute_probabilities_separately(self) -> None:
        corpus = _corpus(with_fixtures=False)
        corpus.rows_by_gameweek[20][0] = replace(
            corpus.rows_by_gameweek[20][0],
            minutes=45,
            started=True,
        )
        [projection] = [entry for entry in project_next_match(corpus) if entry.element_id == STEADY]
        artifact = _entry(projection)

        self.assertNotEqual(
            projection.minutes.probability_start,
            projection.minutes.probability_sixty_minutes,
        )
        self.assertEqual(
            artifact["probabilityStartModel"],
            round(projection.minutes.probability_start, 3),
        )
        self.assertEqual(
            artifact["probabilitySixtyMinutes"],
            round(projection.minutes.probability_sixty_minutes, 3),
        )
        self.assertEqual(
            artifact["probabilityStart"],
            artifact["probabilitySixtyMinutes"],
        )

    def test_current_start_updates_the_carried_xstart_record(self) -> None:
        previous = _corpus(with_fixtures=False)
        for gameweek, rows in previous.rows_by_gameweek.items():
            previous.rows_by_gameweek[gameweek] = [
                replace(row, minutes=20, started=False, total_points=1) for row in rows
            ]
        current = SeasonCorpus(season="2026-27")
        current.position_by_element[7] = 4
        current.team_by_element[7] = TEAM
        current.name_by_element[7] = "Returning"
        current.code_by_element[7] = STEADY * 1000
        current.rows_by_gameweek[1] = [
            replace(
                _row(1, 7, minutes=90, points=2),
                element_code=STEADY * 1000,
                kickoff_time=KICKOFF + timedelta(days=365),
            )
        ]

        [projection] = project_next_match(current, previous=previous)

        self.assertIn("current_plus_carried_start", projection.minutes.reason_codes)
        self.assertGreater(projection.minutes.probability_start, 0.1)
        self.assertLess(projection.minutes.probability_start, 0.8)

    def test_keys_on_the_code_that_survives_the_season(self) -> None:
        codes = {entry.code for entry in project_next_match(_corpus(with_fixtures=False))}

        self.assertIn(STEADY * 1000, codes)
        self.assertNotIn(STEADY, codes)

    def test_a_player_without_minutes_is_left_out(self) -> None:
        projected = {entry.element_id for entry in project_next_match(_corpus(with_fixtures=False))}

        self.assertNotIn(CAMEO, projected)

    def test_an_empty_season_projects_nobody(self) -> None:
        self.assertEqual(project_next_match(SeasonCorpus(season="2025-26")), [])

    def test_a_season_that_ran_past_gameweek_38_still_projects(self) -> None:
        """2019-20 finished at gameweek 47, so the next event is not a legal one."""
        corpus = _corpus(with_fixtures=False)
        overrun = {
            gameweek + 27: [_row(gameweek + 27, STEADY, minutes=90, points=6) for _ in range(1)]
            for gameweek in range(1, 21)
        }
        corpus.rows_by_gameweek = overrun

        projected = project_next_match(corpus)

        self.assertEqual([entry.code for entry in projected], [STEADY * 1000])


if __name__ == "__main__":
    unittest.main()
