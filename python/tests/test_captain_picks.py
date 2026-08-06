"""The picks table is an index, and an index is a thing that can be wrong.

Every saving here is a chance to point a cell at the wrong player or drop a
gameweek and have the columns silently close up, which would misalign every row
after it and still look plausible. These pin the alignment, the holes, and the
venue casing.
"""

from __future__ import annotations

from fpl_andres.backtesting.captain_picks import opponent_labels, picks_payload
from fpl_andres.backtesting.captaincy import CaptaincyScore, CaptainPick
from fpl_andres.backtesting.corpus import SeasonCorpus
from fpl_andres.backtesting.fixtures import Fixture


def _fixture(fixture_id: int, event: int, home: int, away: int) -> Fixture:
    return Fixture(fixture_id=fixture_id, event=event, team_h=home, team_a=away, kickoff_time=None)


def _corpus() -> SeasonCorpus:
    corpus = SeasonCorpus(season="2024-25")
    corpus.name_by_element.update({1: "Salah", 2: "Haaland", 3: "Saka"})
    corpus.team_by_element.update({1: 10, 2: 20, 3: 30})
    corpus.short_name_by_team.update({10: "LIV", 20: "MCI", 30: "ARS"})
    corpus.code_by_team.update({10: 14, 20: 43, 30: 3})
    corpus.fixtures_by_event.update(
        {
            1: [_fixture(1, 1, 10, 20), _fixture(2, 1, 30, 10)],
            2: [_fixture(3, 2, 20, 30)],
        }
    )
    return corpus


def _score(label: str, *picks: CaptainPick) -> CaptaincyScore:
    score = CaptaincyScore(label=label)
    score.picks.extend(picks)
    return score


class TestOpponentLabels:
    def test_home_is_upper_and_away_is_lower(self) -> None:
        labels = opponent_labels(_corpus(), 2)
        assert labels[20] == "ARS"
        assert labels[30] == "mci"

    def test_a_double_gameweek_lists_both_with_their_own_venue(self) -> None:
        # Liverpool play City at home and Arsenal away in the same week. One
        # label carrying one venue would misreport half of it.
        assert opponent_labels(_corpus(), 1)[10] == "MCI ars"

    def test_a_blank_gameweek_is_an_empty_label_not_a_missing_key(self) -> None:
        # A club with no fixture still has to occupy its slot, or the caller
        # cannot tell "not playing" from "club unknown".
        assert opponent_labels(_corpus(), 2)[10] == ""


class TestPicksPayload:
    def test_a_gameweek_a_method_skipped_is_a_hole_not_a_shift(self) -> None:
        # The failure this exists to prevent: dropping the empty cell would
        # slide gameweek 2 into gameweek 1's column for that row only, and
        # every cell after it would name the wrong week.
        payload = picks_payload(
            _corpus(),
            [
                (
                    "method",
                    "model",
                    _score(
                        "model",
                        CaptainPick(gameweek=1, element_id=1, points=12, best_points=15),
                        CaptainPick(gameweek=2, element_id=2, points=6, best_points=9),
                    ),
                ),
                (
                    "thesis",
                    "sparse",
                    _score(
                        "sparse",
                        CaptainPick(gameweek=2, element_id=3, points=2, best_points=9),
                    ),
                ),
            ],
        )

        assert payload["gameweeks"] == [1, 2]
        rows = {row["label"]: row["picks"] for row in payload["rows"]}
        assert rows["sparse"][0] is None
        assert rows["sparse"][1] is not None
        assert rows["sparse"][1][0] == 3

    def test_two_rows_may_share_a_label_without_one_being_dropped(self) -> None:
        # `components` is the name of both a ranking method and a thesis. Keyed
        # by label alone one silently overwrites the other, and the grid then
        # renders thirteen rows while claiming fourteen.
        payload = picks_payload(
            _corpus(),
            [
                ("method", "components", _score("components", CaptainPick(1, 1, 5, 9))),
                ("thesis", "components", _score("components", CaptainPick(1, 2, 7, 9))),
            ],
        )

        assert len(payload["rows"]) == 2
        assert [row["group"] for row in payload["rows"]] == ["method", "thesis"]

    def test_a_cell_carries_the_player_his_haul_and_the_opponent(self) -> None:
        payload = picks_payload(
            _corpus(),
            [
                (
                    "method",
                    "model",
                    _score(
                        "model",
                        CaptainPick(gameweek=2, element_id=2, points=13, best_points=13),
                    ),
                )
            ],
        )

        assert payload["rows"][0]["picks"][0] == [2, 13, "ARS"]
        assert payload["players"]["2"] == ["Haaland", 43]
        assert payload["clubs"]["43"] == "MCI"

    def test_the_row_order_is_the_order_given_not_the_dict_order(self) -> None:
        # Iterating a mapping would reshuffle the artifact between runs and
        # make every refresh commit look like a change.
        payload = picks_payload(
            _corpus(),
            [
                ("method", "a", _score("a", CaptainPick(1, 2, 2, 4))),
                ("thesis", "b", _score("b", CaptainPick(1, 1, 1, 4))),
            ],
        )
        assert [row["label"] for row in payload["rows"]] == ["a", "b"]

    def test_the_ceiling_is_one_row_because_every_method_shares_a_shortlist(
        self,
    ) -> None:
        # Eight points is a good week or a wasted one depending on what was on
        # offer, so the cell is unreadable without it.
        payload = picks_payload(
            _corpus(),
            [
                ("method", "model", _score("model", CaptainPick(1, 1, 8, 17))),
                ("thesis", "other", _score("other", CaptainPick(1, 2, 3, 17))),
            ],
        )
        assert payload["ceiling"] == [17]

    def test_a_player_appears_once_however_many_methods_picked_him(self) -> None:
        payload = picks_payload(
            _corpus(),
            [
                ("method", "model", _score("model", CaptainPick(1, 1, 12, 12))),
                ("thesis", "other", _score("other", CaptainPick(2, 1, 4, 9))),
            ],
        )
        assert list(payload["players"]) == ["1"]

    def test_a_season_nobody_was_scored_in_publishes_nothing(self) -> None:
        # An empty table and a missing key are different claims, and only the
        # second one makes the page say it has nothing rather than drawing an
        # axis with no cells under it.
        assert picks_payload(_corpus(), [("method", "model", _score("model"))]) == {}
