"""A season-long horizon is not a special case, and frozen form does not wreck it.

`project_horizon` was recorded as stopping at seven gameweeks. It does not:
seven is only the default in `horizons`, and any length works. The real worry
was that form is measured once at the projection gameweek and held for every
week after, so a hot player would stay hot for thirty-one weeks.

Measured against realised totals, projecting from GW8 across three seasons, the
bias per gameweek at a thirty-one week horizon is +0.197, -0.005 and +0.095 -
small and inconsistent in sign, so noise rather than drift. Rank correlation
*improves* with horizon (0.48-0.51 against 0.24-0.32 at one week) because
weekly noise averages out.
"""

from __future__ import annotations

from test_horizon import OPPONENT, TEAM, corpus_with

from fpl_andres.backtesting.projector import project_horizon

FULL_SEASON = tuple(range(1, 29))


def _every_week_schedule() -> dict[int, list[tuple[int, int]]]:
    return {event: [(TEAM, OPPONENT)] for event in range(1, 40)}


def test_a_season_long_horizon_is_accepted() -> None:
    """Seven is a default, not a ceiling."""
    projections = project_horizon(corpus_with(_every_week_schedule()), 11, horizons=FULL_SEASON)

    assert projections
    for projection in projections:
        assert set(projection.points_by_horizon) == set(FULL_SEASON)


def test_points_accumulate_monotonically_across_the_season() -> None:
    projections = project_horizon(corpus_with(_every_week_schedule()), 11, horizons=FULL_SEASON)

    for projection in projections:
        running = [projection.points_over(h) for h in FULL_SEASON]
        assert running == sorted(running), "a longer horizon cannot be worth less"


def test_a_long_horizon_agrees_with_the_short_one_where_they_overlap() -> None:
    """The ladder is one walk forward, so a shared rung must match exactly."""
    corpus = corpus_with(_every_week_schedule())

    short = {p.element_id: p for p in project_horizon(corpus, 11, horizons=(1, 5))}
    long = {p.element_id: p for p in project_horizon(corpus, 11, horizons=(1, 5, 20, 28))}

    assert short and short.keys() == long.keys()
    for element_id, projection in short.items():
        assert projection.points_over(1) == long[element_id].points_over(1)
        assert projection.points_over(5) == long[element_id].points_over(5)


def test_a_blank_week_late_in_the_horizon_still_pays_nothing() -> None:
    schedule = _every_week_schedule()
    del schedule[25]

    projections = project_horizon(corpus_with(schedule), 11, horizons=(14, 15, 16))

    for projection in projections:
        # Gameweek 25 is the fifteenth week of a horizon starting at 11.
        assert projection.points_over(15) == projection.points_over(14)
        assert projection.points_over(16) > projection.points_over(15)
