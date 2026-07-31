"""The crosswalk must refuse a bad match more reliably than it makes a good one.

A silent mis-map corrupts a player's whole history without erroring, so every
test here is really asking the same question: when the evidence is thin, does it
say so rather than guess?
"""

from __future__ import annotations

import unittest

from fpl_andres.crosswalk import (
    ForeignPlayer,
    FplPlayer,
    MatchOutcome,
    canonical_club,
    normalise,
    resolve_crosswalk,
    variants,
)

SEASON = "2025-26"


def fpl(
    code: int,
    first: str,
    second: str,
    web: str,
    *,
    club: str = "Liverpool",
    minutes: int = 2916,
    goals: int = 29,
    assists: int = 18,
) -> FplPlayer:
    return FplPlayer(
        code=code,
        season=SEASON,
        club=club,
        first_name=first,
        second_name=second,
        web_name=web,
        minutes=minutes,
        goals=goals,
        assists=assists,
    )


def foreign(
    source_id: str,
    name: str,
    *,
    club: str = "Liverpool",
    minutes: int = 2916,
    goals: int = 29,
    assists: int = 14,
) -> ForeignPlayer:
    return ForeignPlayer(
        source="understat",
        source_id=source_id,
        season=SEASON,
        club=club,
        name=name,
        minutes=minutes,
        goals=goals,
        assists=assists,
    )


class NormaliseTest(unittest.TestCase):
    def test_strips_accents_so_two_sites_can_agree(self) -> None:
        self.assertEqual(normalise("Magalhães"), "magalhaes")
        self.assertEqual(normalise("Ødegaard"), "odegaard")
        self.assertEqual(normalise("Groß"), "gross")

    def test_punctuation_joins_a_name_rather_than_splitting_it(self) -> None:
        self.assertEqual(normalise("N'Golo"), "ngolo")
        self.assertEqual(normalise("Alexander-Arnold"), "alexanderarnold")

    def test_a_full_name_reaches_the_surname_alone(self) -> None:
        found = variants("Gabriel", "dos Santos Magalhães")

        self.assertIn("magalhaes", found)
        self.assertIn("gabriel", found)

    def test_particles_are_optional_because_sources_disagree(self) -> None:
        self.assertIn("santos magalhaes", variants("dos Santos Magalhães"))


class ClubTest(unittest.TestCase):
    def test_every_source_spelling_lands_on_one_club(self) -> None:
        for spelling in ("Man City", "Manchester City"):
            self.assertEqual(canonical_club(spelling), "Man City")
        for spelling in ("Spurs", "Tottenham", "Tottenham Hotspur"):
            self.assertEqual(canonical_club(spelling), "Spurs")

    def test_the_two_manchester_clubs_never_collapse(self) -> None:
        self.assertNotEqual(canonical_club("Manchester City"), canonical_club("Manchester United"))

    def test_an_unknown_club_returns_nothing_rather_than_itself(self) -> None:
        self.assertIsNone(canonical_club("Real Madrid"))


class ResolveTest(unittest.TestCase):
    def test_accepts_a_match_two_sources_independently_corroborate(self) -> None:
        report = resolve_crosswalk(
            [fpl(118748, "Mohamed", "Salah", "M.Salah")],
            [foreign("1250", "Mohamed Salah")],
            source="understat",
        )

        [match] = report.matches
        self.assertEqual(match.outcome, MatchOutcome.VERIFIED)
        self.assertEqual(match.source_id, "1250")
        self.assertEqual(report.coverage(), 1.0)

    def test_a_name_that_agrees_but_a_season_that_does_not_is_refused(self) -> None:
        report = resolve_crosswalk(
            [fpl(118748, "Mohamed", "Salah", "M.Salah")],
            [foreign("1250", "Mohamed Salah", goals=7)],
            source="understat",
        )

        [match] = report.matches
        self.assertEqual(match.outcome, MatchOutcome.CONTRADICTED)
        self.assertIsNone(match.source_id)

    def test_one_disputed_goal_does_not_break_a_match(self) -> None:
        """The Premier League reassigns scorers; Opta does not always follow."""
        report = resolve_crosswalk(
            [fpl(1, "Noni", "Madueke", "Madueke", minutes=1205, goals=3)],
            [foreign("20", "Noni Madueke", minutes=1246, goals=2)],
            source="understat",
        )

        [match] = report.matches
        self.assertEqual(match.outcome, MatchOutcome.VERIFIED)
        self.assertEqual(match.goals_delta, -1)

    def test_the_clubs_may_be_spelled_differently_on_each_side(self) -> None:
        report = resolve_crosswalk(
            [fpl(1, "Son", "Heung-min", "Son", club="Spurs")],
            [foreign("30", "Son Heung-Min", club="Tottenham")],
            source="understat",
        )

        self.assertEqual(report.matches[0].outcome, MatchOutcome.VERIFIED)

    def test_an_unrecognised_club_is_a_visible_gap_not_a_wrong_match(self) -> None:
        report = resolve_crosswalk(
            [fpl(1, "A", "Player", "Player", club="Some New Club")],
            [foreign("40", "A Player", club="Some New Club")],
            source="understat",
        )

        self.assertEqual(report.matches[0].outcome, MatchOutcome.NO_CANDIDATE)

    def test_two_players_of_the_same_name_at_one_club_map_to_neither(self) -> None:
        report = resolve_crosswalk(
            [fpl(1, "Bruno", "Fernandes", "Fernandes", club="Man Utd")],
            [
                foreign("10", "Bruno Fernandes", club="Man Utd"),
                foreign("11", "Bruno Fernandes", club="Man Utd"),
            ],
            source="understat",
        )

        [match] = report.matches
        self.assertEqual(match.outcome, MatchOutcome.AMBIGUOUS)
        self.assertIsNone(match.source_id)
        self.assertEqual(match.candidates, ("10", "11"))

    def test_the_same_name_at_another_club_never_competes(self) -> None:
        report = resolve_crosswalk(
            [fpl(1, "Danny", "Ward", "Ward", club="Leicester")],
            [
                foreign("10", "Danny Ward", club="Leicester"),
                foreign("11", "Danny Ward", club="Huddersfield"),
            ],
            source="understat",
        )

        [match] = report.matches
        self.assertEqual(match.outcome, MatchOutcome.VERIFIED)
        self.assertEqual(match.source_id, "10")

    def test_stoppage_time_rounding_does_not_break_a_match(self) -> None:
        report = resolve_crosswalk(
            [fpl(118748, "Mohamed", "Salah", "M.Salah")],
            [foreign("1250", "Mohamed Salah", minutes=2916 + 120)],
            source="understat",
        )

        self.assertEqual(report.matches[0].outcome, MatchOutcome.VERIFIED)
        self.assertEqual(report.matches[0].minutes_delta, 120)

    def test_half_a_season_of_difference_does_break_it(self) -> None:
        report = resolve_crosswalk(
            [fpl(118748, "Mohamed", "Salah", "M.Salah")],
            [foreign("1250", "Mohamed Salah", minutes=1400)],
            source="understat",
        )

        self.assertEqual(report.matches[0].outcome, MatchOutcome.CONTRADICTED)

    def test_an_assist_disagreement_is_recorded_and_forgiven(self) -> None:
        """FPL awards assists under its own rules. Gating on them would be wrong."""
        report = resolve_crosswalk(
            [fpl(118748, "Mohamed", "Salah", "M.Salah", assists=18)],
            [foreign("1250", "Mohamed Salah", assists=14)],
            source="understat",
        )

        [match] = report.matches
        self.assertEqual(match.outcome, MatchOutcome.VERIFIED)
        self.assertEqual(match.assists_delta, -4)

    def test_a_player_nobody_else_lists_is_named_not_dropped(self) -> None:
        report = resolve_crosswalk(
            [fpl(999, "Some", "Debutant", "Debutant")],
            [],
            source="understat",
        )

        [match] = report.matches
        self.assertEqual(match.outcome, MatchOutcome.NO_CANDIDATE)
        self.assertEqual(match.web_name, "Debutant")

    def test_a_cameo_is_unidentifiable_and_does_not_count_against_coverage(self) -> None:
        report = resolve_crosswalk(
            [
                fpl(118748, "Mohamed", "Salah", "M.Salah"),
                fpl(2, "A", "Cameo", "Cameo", minutes=40, goals=0),
            ],
            [foreign("1250", "Mohamed Salah")],
            source="understat",
        )

        self.assertEqual(report.by_outcome(MatchOutcome.TOO_LITTLE_FOOTBALL)[0].web_name, "Cameo")
        self.assertEqual(report.coverage(), 1.0)

    def test_every_player_is_accounted_for_exactly_once(self) -> None:
        players = [fpl(index, "First", f"Second{index}", f"P{index}") for index in range(5)]

        report = resolve_crosswalk(players, [], source="understat")

        self.assertEqual(len(report.matches), len(players))
        self.assertEqual(sum(report.counts.values()), len(players))


if __name__ == "__main__":
    unittest.main()
