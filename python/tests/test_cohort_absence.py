"""A cohort read once and never re-read decays.

Accounts are deleted, renamed and abandoned. FPL answers a request for a gone
entry with a 404 and says nothing else, so the only way to know is to have
asked several times and counted. The capture job hits every catalogued manager
after every deadline, which makes it the one place that can learn this.

These pin the arithmetic, because the failure it prevents is silent: a
ranking whose five hundredth place is held by somebody who stopped playing two
seasons ago looks exactly like a ranking that is right.
"""

from __future__ import annotations

import pytest

from fpl_andres.cohorts.absence import DEFAULT_TOLERANCE, departed, record_attempt


class TestCountingWhoAnswered:
    def test_a_manager_who_answered_carries_no_absence(self) -> None:
        assert record_attempt({}, [1, 2], [1, 2]) == {}

    def test_a_manager_who_did_not_is_counted_once(self) -> None:
        assert record_attempt({}, [1, 2], [1]) == {2: 1}

    def test_misses_accumulate_across_deadlines(self) -> None:
        after_one = record_attempt({}, [1], [])
        after_two = record_attempt(after_one, [1], [])

        assert after_two == {1: 2}

    def test_one_answer_clears_a_run_of_misses(self) -> None:
        """The question is whether he is still there, and an answer settles it."""
        stale = {1: 5}

        assert record_attempt(stale, [1], [1]) == {}

    def test_a_manager_nobody_asked_about_keeps_what_he_had(self) -> None:
        """A run cut short by its budget must not look like one that found nobody."""
        assert record_attempt({7: 2}, [1], [1]) == {7: 2}


class TestDecidingWhoIsGone:
    def test_nobody_is_gone_below_the_tolerance(self) -> None:
        assert departed({1: 2}, tolerance=3) == frozenset()

    def test_the_tolerance_is_inclusive(self) -> None:
        assert departed({1: 3}, tolerance=3) == frozenset({1})

    def test_a_tolerance_of_nothing_is_refused(self) -> None:
        """Zero would drop everyone the moment a single request failed."""
        with pytest.raises(ValueError):
            departed({1: 1}, tolerance=0)

    def test_the_default_gives_a_manager_three_weeks(self) -> None:
        assert DEFAULT_TOLERANCE == 3
