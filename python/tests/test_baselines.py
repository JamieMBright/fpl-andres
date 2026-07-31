"""The three baselines the method is measured against."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus
from fpl_andres.simulation.baselines import (
    crowd_ranking,
    form_ranking,
    hold_ranking,
    ranking_for,
)

KICKOFF = datetime(2024, 8, 17, 14, 0, tzinfo=UTC)


def row(
    gameweek: int,
    element_id: int,
    points: int,
    *,
    transfers_in: int | None = None,
    transfers_out: int | None = None,
) -> ElementRow:
    return ElementRow(
        gameweek=gameweek,
        element_id=element_id,
        element_code=element_id,
        fixture_id=gameweek * 100 + element_id,
        minutes=90,
        started=True,
        goals=0,
        assists=0,
        expected_goals=None,
        expected_assists=None,
        total_points=points,
        price_tenths=50,
        selected=1000,
        kickoff_time=KICKOFF + timedelta(days=7 * gameweek),
        transfers_in=transfers_in,
        transfers_out=transfers_out,
    )


def corpus_with(rows: list[ElementRow]) -> SeasonCorpus:
    corpus = SeasonCorpus(season="2024-25")
    for entry in rows:
        corpus.rows_by_gameweek.setdefault(entry.gameweek, []).append(entry)
    return corpus


def test_hold_never_prefers_anything() -> None:
    corpus = corpus_with([row(1, 1, 10), row(2, 1, 12)])

    assert hold_ranking(corpus, 3) == {}


def test_form_averages_the_window_and_never_reads_the_current_week() -> None:
    corpus = corpus_with([row(1, 1, 2), row(2, 1, 4), row(3, 1, 6), row(4, 1, 100)])

    ranking = form_ranking(corpus, 4, window=3)

    assert ranking[1] == pytest.approx(4.0)


def test_form_respects_a_shorter_window() -> None:
    corpus = corpus_with([row(1, 1, 0), row(2, 1, 0), row(3, 1, 9)])

    assert form_ranking(corpus, 4, window=1)[1] == pytest.approx(9.0)


def test_the_crowd_reads_net_transfers_not_gross() -> None:
    corpus = corpus_with(
        [
            # Heavily traded both ways: a price scare, not a view.
            row(3, 1, 5, transfers_in=900_000, transfers_out=850_000),
            row(3, 2, 5, transfers_in=200_000, transfers_out=10_000),
        ]
    )

    ranking = crowd_ranking(corpus, 4)

    assert ranking[2] > ranking[1]


def test_the_crowd_falls_back_to_the_last_week_that_published_counts() -> None:
    corpus = corpus_with(
        [
            row(2, 1, 5, transfers_in=100, transfers_out=10),
            row(3, 1, 5),
        ]
    )

    assert crowd_ranking(corpus, 4) == {1: pytest.approx(90.0)}


def test_the_crowd_says_nothing_when_no_counts_were_ever_published() -> None:
    corpus = corpus_with([row(1, 1, 5), row(2, 1, 5)])

    assert crowd_ranking(corpus, 3) == {}


def test_an_unknown_baseline_is_refused_rather_than_defaulted() -> None:
    with pytest.raises(ValueError, match="unknown baseline"):
        ranking_for("vibes", corpus_with([]), 3)


def test_every_named_baseline_is_reachable_by_name() -> None:
    corpus = corpus_with([row(1, 1, 5, transfers_in=10, transfers_out=1)])

    for name in ("hold", "form_chaser", "crowd"):
        assert isinstance(ranking_for(name, corpus, 2), dict)
