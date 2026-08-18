"""Competing captaincy theses, and the traps in comparing them.

Nine policies is nine chances to find a winner by luck, so the rules that keep
the comparison honest matter more than any individual policy: every thesis sees
the same shortlist, the same gameweeks and the same pre-deadline facts, none can
see the outcome it is being graded on, and the crowd's own pick is in the set
rather than being treated as a foil.
"""

from __future__ import annotations

from fpl_andres.backtesting.captain_policies import (
    CAPTAIN_POLICIES,
    CaptainCandidate,
    SetAndForget,
    build_captain_policies,
    policy_names,
)
from fpl_andres.backtesting.captaincy import CaptaincyScore, score_policies


def _candidate(
    element_id: int,
    *,
    expected: float = 5.0,
    components: float = 5.0,
    recent: float | None = 5.0,
    deviation: float = 0.0,
    start: float = 1.0,
    ownership: float = 10.0,
) -> CaptainCandidate:
    return CaptainCandidate(
        element_id=element_id,
        expected_points=expected,
        component_points=components,
        recent_points=recent,
        recent_deviation=deviation,
        probability_start=start,
        ownership=ownership,
    )


def _scores() -> dict[str, CaptaincyScore]:
    return {label: CaptaincyScore(label=label) for label in policy_names()}


class TestEachThesisPicksWhatItClaimsTo:
    def test_expected_points_takes_the_highest_projection(self) -> None:
        candidates = [_candidate(1, expected=9.0), _candidate(2, expected=4.0)]
        assert CAPTAIN_POLICIES["expected_points"](candidates) == 1

    def test_availability_adjusted_prefers_the_nailed_starter(self) -> None:
        # 7.5 at 60% is 4.5; 6.5 at a certainty is 6.5. The rotation risk is
        # the whole point, and only this policy prices it.
        candidates = [
            _candidate(1, expected=7.5, start=0.6),
            _candidate(2, expected=6.5, start=1.0),
        ]
        assert CAPTAIN_POLICIES["expected_points"](candidates) == 1
        assert CAPTAIN_POLICIES["availability_adjusted"](candidates) == 2

    def test_upside_and_robust_disagree_on_the_same_pair(self) -> None:
        # The whole reason both are in the set: one buys the tail, the other
        # sells it, and no measurement exists yet to say which is right.
        candidates = [
            _candidate(1, expected=6.0, deviation=4.0),
            _candidate(2, expected=7.0, deviation=0.5),
        ]
        assert CAPTAIN_POLICIES["upside"](candidates) == 1
        assert CAPTAIN_POLICIES["robust"](candidates) == 2

    def test_form_refuses_a_player_under_the_floor(self) -> None:
        candidates = [
            _candidate(1, expected=9.0, recent=1.0),
            _candidate(2, expected=4.0, recent=6.0),
        ]
        assert CAPTAIN_POLICIES["form"](candidates) == 2

    def test_form_falls_back_when_nobody_clears_the_floor(self) -> None:
        # Refusing to captain is not an option the game offers.
        candidates = [
            _candidate(1, expected=9.0, recent=0.5),
            _candidate(2, expected=4.0, recent=1.0),
        ]
        assert CAPTAIN_POLICIES["form"](candidates) == 1

    def test_crowd_takes_the_template_however_it_projects(self) -> None:
        candidates = [
            _candidate(1, expected=4.0, ownership=70.0),
            _candidate(2, expected=9.0, ownership=5.0),
        ]
        assert CAPTAIN_POLICIES["crowd"](candidates) == 1

    def test_differential_and_template_split_on_ownership(self) -> None:
        candidates = [
            _candidate(1, expected=7.0, ownership=70.0),
            _candidate(2, expected=6.5, ownership=5.0),
        ]
        assert CAPTAIN_POLICIES["differential"](candidates) == 2
        assert CAPTAIN_POLICIES["template"](candidates) == 1

    def test_a_premium_everybody_owns_is_still_reachable(self) -> None:
        # A framework that can never pick the best player because everybody
        # owns him is answering a different question. Seven of nine policies
        # take him here; only the differential declines.
        haaland = _candidate(1, expected=9.5, components=9.5, recent=9.0, ownership=65.0)
        punt = _candidate(2, expected=5.0, components=5.0, recent=4.0, ownership=3.0)
        picks = {label: policy([haaland, punt]) for label, policy in CAPTAIN_POLICIES.items()}
        assert picks["expected_points"] == 1
        assert picks["crowd"] == 1
        assert picks["form"] == 1
        assert picks["template"] == 1
        assert sum(1 for pick in picks.values() if pick == 1) >= 7

    def test_every_policy_returns_nothing_when_there_is_nobody(self) -> None:
        for label, policy in CAPTAIN_POLICIES.items():
            assert policy([]) is None, label


class TestTheComparisonIsFair:
    def test_every_policy_is_scored_on_the_same_gameweeks(self) -> None:
        candidates = [
            _candidate(index, expected=float(index), ownership=float(30 - index))
            for index in range(1, 11)
        ]
        actual = {index: index for index in range(1, 11)}
        scores = _scores()

        score_policies(candidates, actual, scores, gameweek=1)

        assert {score.gameweeks for score in scores.values()} == {1}

    def test_every_policy_is_graded_against_the_same_ceiling(self) -> None:
        candidates = [
            _candidate(1, expected=9.0, ownership=50.0),
            _candidate(2, expected=4.0, ownership=40.0),
        ]
        actual = {1: 3, 2: 17}
        scores = _scores()

        score_policies(candidates, actual, scores, gameweek=1)

        assert {score.best_points for score in scores.values()} == {17}

    def test_realised_players_outside_the_supplied_xi_are_not_reachable(self) -> None:
        # Element 99 outscores everybody but is not in the XI supplied by the
        # season simulation, so no policy may reach him.
        candidates = [
            _candidate(index, expected=5.0, ownership=float(50 - index)) for index in range(1, 4)
        ]
        actual = {1: 2, 2: 2, 3: 2, 99: 24}
        scores = _scores()

        score_policies(candidates, actual, scores, gameweek=1)

        assert all(score.captain_points == 2 for score in scores.values())
        assert all(score.best_points == 2 for score in scores.values())

    def test_a_player_with_no_realised_row_is_not_captainable(self) -> None:
        candidates = [
            _candidate(1, expected=9.0, ownership=60.0),
            _candidate(2, expected=4.0, ownership=50.0),
        ]
        scores = _scores()

        score_policies(candidates, {2: 8}, scores, gameweek=1)

        assert all(score.captain_points == 8 for score in scores.values())

    def test_nothing_is_scored_when_the_shortlist_is_empty(self) -> None:
        scores = _scores()

        score_policies([_candidate(1)], {}, scores, gameweek=1)

        assert all(score.gameweeks == 0 for score in scores.values())

    def test_the_policy_set_is_ordered_so_two_runs_agree(self) -> None:
        assert policy_names() == tuple(build_captain_policies())
        assert len(set(policy_names())) == len(policy_names())
        # The stateless mapping is a subset; the full set adds the ones that
        # carry season state and therefore cannot live at module level.
        assert set(CAPTAIN_POLICIES) < set(policy_names())


class TestTheSetAndForgetBaseline:
    """The \"just captain Haaland\" rule, written without his name in it."""

    def test_it_commits_to_the_most_owned_and_never_changes_its_mind(self) -> None:
        # The point of the baseline: week two makes element 2 both the highest
        # projected and the most owned, and it captains element 1 anyway.
        policy = SetAndForget()
        opening = [_candidate(1, ownership=90.0), _candidate(2, ownership=10.0)]
        later = [
            _candidate(1, ownership=5.0, expected=1.0),
            _candidate(2, ownership=95.0, expected=9.0),
        ]

        assert policy(opening) == 1
        assert policy(later) == 1
        assert policy.anchor == 1

    def test_the_armband_passes_to_the_vice_when_the_anchor_is_not_playing(self) -> None:
        # Not a fudge to keep the week count equal: this is the vice-captain,
        # which is a real rule and what happens to a real set-and-forget manager.
        policy = SetAndForget()
        assert policy([_candidate(1, ownership=90.0), _candidate(2, ownership=50.0)]) == 1
        assert policy([_candidate(2, ownership=50.0), _candidate(3, ownership=20.0)]) == 2

    def test_the_anchor_survives_a_week_the_captain_missed(self) -> None:
        policy = SetAndForget()
        policy([_candidate(1, ownership=90.0), _candidate(2, ownership=50.0)])
        policy([_candidate(2, ownership=50.0)])

        assert policy([_candidate(1, ownership=1.0), _candidate(2, ownership=99.0)]) == 1

    def test_an_empty_shortlist_does_not_commit_it_to_anybody(self) -> None:
        # Committing to nothing would burn the one decision it gets to make.
        policy = SetAndForget()
        assert policy([]) is None
        assert policy.anchor is None

    def test_a_fresh_set_is_built_per_season_so_the_anchor_cannot_leak(self) -> None:
        # The failure this prevents: 2022-23's anchor carried into 2023-24 would
        # captain a player who had left the league, and it would look like a
        # modelling result rather than a leak.
        first = build_captain_policies()["set_and_forget"]
        first([_candidate(1, ownership=90.0)])
        second = build_captain_policies()["set_and_forget"]

        assert isinstance(first, SetAndForget)
        assert isinstance(second, SetAndForget)
        assert first.anchor == 1
        assert second.anchor is None

    def test_it_is_scored_alongside_every_other_thesis(self) -> None:
        scores = _scores()
        policies = build_captain_policies()

        score_policies(
            [_candidate(1, ownership=90.0), _candidate(2, ownership=10.0)],
            {1: 12, 2: 3},
            scores,
            gameweek=1,
            policies=policies,
        )

        assert scores["set_and_forget"].captain_points == 12

    def test_no_policy_can_read_the_outcome_it_is_graded_on(self) -> None:
        # The candidate record is the whole boundary. If a realised-points
        # field ever appears on it, every number in the comparison is a leak.
        assert not any(
            "actual" in field or "realised" in field
            for field in CaptainCandidate.__dataclass_fields__
        )

    def test_the_rank_policies_have_not_collapsed_into_the_crowd(self) -> None:
        # Both scored identically to `crowd` in all four seasons on the first
        # run, because ownership arrived as a manager count rather than a
        # percentage and the term swamped every projection. Two theses were
        # reported that had never been tested, and the table looked fine.
        candidates = [
            _candidate(1, expected=7.0, ownership=90.0),
            _candidate(2, expected=6.6, ownership=20.0),
        ]
        assert CAPTAIN_POLICIES["crowd"](candidates) == 1
        # A 0.4 projection gap against 70 points of ownership: at Oracle's
        # price of 1.5 per 100 that is 1.05, so the differential takes it and
        # the template does not.
        assert CAPTAIN_POLICIES["differential"](candidates) == 2
        assert CAPTAIN_POLICIES["template"](candidates) == 1

    def test_a_clear_projection_gap_survives_the_ownership_term(self) -> None:
        # Oracle's own rule: two points ahead and you captain him regardless.
        # If ownership can overturn that, the coefficient is wrong.
        candidates = [
            _candidate(1, expected=9.0, ownership=95.0),
            _candidate(2, expected=6.5, ownership=2.0),
        ]
        assert CAPTAIN_POLICIES["differential"](candidates) == 1
        assert CAPTAIN_POLICIES["template"](candidates) == 1
