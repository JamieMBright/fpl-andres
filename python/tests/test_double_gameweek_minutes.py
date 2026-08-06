"""A double gameweek is two matches, and two halves of the model disagreed.

`MinutesEvidence` says it in its own validator -- "a double gameweek is two real
appearances in one event, and rejecting it would throw away half of what he
played". The projector contradicted it, summing a gameweek's rows into one
observation clipped at 120 minutes. `fixture_points` then spent that figure once
per fixture, so a nailed ninety-minute player whose history contained doubles
trained somewhere between 90 and 120 and every single-fixture projection he
appeared in was inflated by the difference.

Splitting the rows exposed a second bug underneath. `weights` is a dict keyed by
`event_id`, so a double gameweek contributed one entry to the denominator while
the numerator iterated observations and counted it twice. A player who started
both halves of a double carried a weighted start rate above one. Nothing had
ever hit it because nothing had ever produced two observations in one event.

Measured, not guessed. Six single weeks of ninety minutes projects 74.45 with a
start probability of 0.827; five singles plus a double of two ninety-minute
matches projects 76.12 at 0.846, on an effective sample that rises from 5.53 to
6.43 because there really is one more match of evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fpl_andres.backtesting.corpus import ElementRow
from fpl_andres.backtesting.projector import ProjectionSettings
from fpl_andres.backtesting.rates import project_element_minutes

KICKOFF = datetime(2025, 8, 16, 14, 0, tzinfo=UTC)
SYNTHETIC = datetime(2000, 1, 1, tzinfo=UTC)
CUTOFF = datetime(2030, 1, 1, tzinfo=UTC)


def _row(gameweek: int, fixture_id: int, minutes: int, kickoff: datetime) -> ElementRow:
    return ElementRow(
        gameweek=gameweek,
        element_id=1,
        element_code=1,
        fixture_id=fixture_id,
        minutes=minutes,
        started=minutes >= 60,
        goals=0,
        assists=0,
        expected_goals=0.0,
        expected_assists=0.0,
        total_points=2,
        price_tenths=50,
        selected=1000,
        kickoff_time=kickoff,
    )


def _singles(weeks: int, start: datetime = KICKOFF) -> list[ElementRow]:
    return [_row(week, week, 90, start + timedelta(days=7 * week)) for week in range(1, weeks + 1)]


def _projected(rows: list[ElementRow]):
    return project_element_minutes(1, "2025-26", 30, rows, CUTOFF, ProjectionSettings())


def _reason(projection, prefix: str) -> str:
    return next(code for code in projection.reason_codes if code.startswith(prefix))


class TestADoubleGameweekIsTwoMatches:
    def test_both_fixtures_become_observations(self) -> None:
        projection = _projected(
            [
                *_singles(5),
                _row(6, 601, 90, KICKOFF + timedelta(days=42)),
                _row(6, 602, 90, KICKOFF + timedelta(days=45)),
            ]
        )

        assert _reason(projection, "observations=") == "observations=7"

    def test_the_extra_match_is_extra_evidence(self) -> None:
        # The weights dict is keyed by event, so a double used to add nothing to
        # the effective sample while adding its weight to the numerator.
        plain = _projected(_singles(6))
        doubled = _projected(
            [
                *_singles(5),
                _row(6, 601, 90, KICKOFF + timedelta(days=42)),
                _row(6, 602, 90, KICKOFF + timedelta(days=45)),
            ]
        )

        assert _reason(plain, "effective_sample=") == "effective_sample=5.53"
        assert _reason(doubled, "effective_sample=") == "effective_sample=6.43"

    def test_starting_both_halves_cannot_push_the_rate_above_one(self) -> None:
        # The bug this replaces: denominator counted the event once, numerator
        # counted the observations, so the ratio exceeded one and the start
        # probability pinned at certainty off six matches.
        doubled = _projected(
            [
                *_singles(5),
                _row(6, 601, 90, KICKOFF + timedelta(days=42)),
                _row(6, 602, 90, KICKOFF + timedelta(days=45)),
            ]
        )

        assert doubled.probability_start == pytest.approx(0.846, abs=0.005)
        assert doubled.probability_start < 1.0

    def test_a_double_no_longer_inflates_the_per_match_minutes(self) -> None:
        # 90 + 90 clipped to 120 made one observation of 120, and the projection
        # was then spent per fixture. Two ninety-minute matches must read as
        # ninety a match, not as a hundred and twenty.
        plain = _projected(_singles(6))
        doubled = _projected(
            [
                *_singles(5),
                _row(6, 601, 90, KICKOFF + timedelta(days=42)),
                _row(6, 602, 90, KICKOFF + timedelta(days=45)),
            ]
        )

        assert plain.expected_minutes == pytest.approx(74.45, abs=0.05)
        assert doubled.expected_minutes == pytest.approx(76.12, abs=0.05)

    def test_a_cameo_in_a_double_drags_the_mean_down(self) -> None:
        # The honest read of ninety minutes then ten is two matches, one of them
        # brief -- not one match of a hundred.
        cameo = _projected(
            [
                *_singles(5),
                _row(6, 601, 90, KICKOFF + timedelta(days=42)),
                _row(6, 602, 10, KICKOFF + timedelta(days=45)),
            ]
        )

        assert cameo.expected_minutes == pytest.approx(65.61, abs=0.05)
        assert cameo.probability_start == pytest.approx(0.695, abs=0.005)

    def test_a_synthesised_kickoff_does_not_make_a_double_look_like_a_repeat(
        self,
    ) -> None:
        # The corpus fills a missing kickoff with a per-gameweek stand-in, so
        # both halves of a double land on the same timestamp. Keyed on the
        # kickoff, the second one is rejected as a duplicate match.
        projection = _projected(
            [
                *_singles(5, SYNTHETIC),
                _row(6, 601, 90, SYNTHETIC + timedelta(days=42)),
                _row(6, 602, 45, SYNTHETIC + timedelta(days=42)),
            ]
        )

        assert _reason(projection, "observations=") == "observations=7"
