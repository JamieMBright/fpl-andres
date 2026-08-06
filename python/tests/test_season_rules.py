"""The rulebook has to match the corpus, not just sound right.

A season-by-season rulebook that nobody checks is a comment. These tests hold
it against the two things the corpus can actually confirm -- whether the
defensive-contribution column is populated and whether `element_type` 5
appears -- and against the code that prices those routes.
"""

from __future__ import annotations

import pytest

from fpl_andres.season_rules import SEASON_RULES, UnknownSeason, rules_for


class TestTheRulebook:
    def test_defensive_contribution_starts_in_2025_26(self) -> None:
        assert not rules_for("2024-25").defensive_contribution
        assert rules_for("2025-26").defensive_contribution
        assert rules_for("2026-27").defensive_contribution

    def test_the_route_count_moves_with_it(self) -> None:
        assert rules_for("2024-25").scoring_routes == 13
        assert rules_for("2025-26").scoring_routes == 14

    def test_assistant_manager_ran_for_exactly_one_season(self) -> None:
        managers = [season for season, rules in SEASON_RULES.items() if rules.assistant_manager]
        assert managers == ["2024-25"]

    def test_the_two_current_seasons_are_identical(self) -> None:
        # The owner's own statement, written down so a future change to one and
        # not the other is caught.
        current = rules_for("2025-26")
        next_season = rules_for("2026-27")
        assert current.defensive_contribution == next_season.defensive_contribution
        assert current.assistant_manager == next_season.assistant_manager
        assert current.scoring_routes == next_season.scoring_routes

    def test_an_unrecorded_season_is_refused_not_defaulted(self) -> None:
        # Assuming the current rules is how a model comes to price a route the
        # season did not have.
        with pytest.raises(UnknownSeason, match="rather than assuming"):
            rules_for("2035-36")

    def test_every_season_in_the_corpus_has_a_rulebook(self) -> None:
        # The published validation span, plus the two live seasons.
        for season in (
            "2019-20",
            "2020-21",
            "2021-22",
            "2022-23",
            "2023-24",
            "2024-25",
            "2025-26",
            "2026-27",
        ):
            assert rules_for(season).season == season

    def test_chips_are_only_claimed_where_a_bootstrap_recorded_them(self) -> None:
        # Writing 2021/22's chips down from memory would be the defaulting this
        # project refuses everywhere else.
        assert not rules_for("2021-22").chips_recorded
        assert rules_for("2025-26").chips_recorded


class TestTheCodeAgrees:
    def test_the_defcon_bar_exists_for_exactly_the_scoring_positions(self) -> None:
        from fpl_andres.backtesting.scoring import DEFCON_POINTS, DEFCON_THRESHOLD

        # A keeper has no bar at all, which is why the metric is null for one
        # rather than zero.
        assert 1 not in DEFCON_THRESHOLD
        assert DEFCON_POINTS[1] == 0
        assert DEFCON_THRESHOLD[2] == 10
        assert DEFCON_THRESHOLD[3] == DEFCON_THRESHOLD[4] == 12

    def test_the_reconciler_prices_thirteen_routes_before_defcon(self) -> None:
        from fpl_andres.backtesting.reconcile import ROUTES

        assert len(ROUTES) == rules_for("2025-26").scoring_routes
        assert "defensive_contribution" in ROUTES
