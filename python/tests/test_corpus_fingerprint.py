"""A backtest score is only meaningful next to the data that produced it.

The corpus is a mutable Supabase table. A re-ingest that
corrects one fixture changes every metric derived from it, and nothing in a
stored backtest artifact said which corpus state it came from — so a moved
number was indistinguishable from a moved model.

`SeasonCorpus.fingerprint` closes that. These tests pin what it covers, what it
deliberately ignores, and that a golden run over a fixed corpus is replayable.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from fpl_andres.backtesting.corpus import ElementRow, SeasonCorpus
from fpl_andres.backtesting.fixtures import Fixture


def _row(element_id: int, gameweek: int, **overrides: object) -> ElementRow:
    base = {
        "gameweek": gameweek,
        "element_id": element_id,
        "element_code": 100_000 + element_id,
        "fixture_id": gameweek * 10 + element_id,
        "minutes": 90,
        "started": True,
        "goals": 1,
        "assists": 0,
        "expected_goals": 0.42,
        "expected_assists": 0.11,
        "total_points": 8,
        "bps": 27,
        "price_tenths": 75,
        "selected": 1_000_000,
        "kickoff_time": datetime(2025, 8, 16, 14, 0, tzinfo=UTC),
    }
    base.update(overrides)
    return ElementRow(**base)  # type: ignore[arg-type]


def _fixture(fixture_id: int, event: int) -> Fixture:
    return Fixture(
        fixture_id=fixture_id,
        event=event,
        team_h=1,
        team_a=2,
        team_h_score=2,
        team_a_score=1,
        finished=True,
        kickoff_time=datetime(2025, 8, 16, 14, 0, tzinfo=UTC),
    )


def _corpus(season: str = "2025-26") -> SeasonCorpus:
    corpus = SeasonCorpus(season=season)
    for gameweek in (1, 2, 3):
        corpus.rows_by_gameweek[gameweek] = [_row(element, gameweek) for element in (7, 3, 11)]
        corpus.fixtures_by_event[gameweek] = [
            _fixture(gameweek * 100 + 2, gameweek),
            _fixture(gameweek * 100 + 1, gameweek),
        ]
    corpus.name_by_element = {7: "Salah", 3: "Haaland", 11: "Saka"}
    corpus.price_by_element = {7: 145, 3: 150, 11: 100}
    return corpus


def test_the_fingerprint_is_stable_across_two_reads_of_the_same_data() -> None:
    assert _corpus().fingerprint == _corpus().fingerprint


def test_the_fingerprint_does_not_depend_on_row_order() -> None:
    """Supabase paging order is an implementation detail, not corpus identity."""
    ordered = _corpus()
    shuffled = _corpus()
    for gameweek in shuffled.rows_by_gameweek:
        shuffled.rows_by_gameweek[gameweek].reverse()
        shuffled.fixtures_by_event[gameweek].reverse()
    assert ordered.fingerprint == shuffled.fingerprint


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("total_points", 9),
        ("minutes", 45),
        ("goals", 2),
        ("assists", 1),
        ("expected_goals", 0.43),
        ("expected_assists", 0.12),
        ("clean_sheets", 1),
        ("saves", 3),
        ("bonus", 2),
        ("bps", 31),
        ("goals_conceded", 1),
        ("yellow_cards", 1),
        ("red_cards", 1),
        ("own_goals", 1),
        ("penalties_saved", 1),
        ("penalties_missed", 1),
        ("defensive_contribution", 12),
        ("clearances_blocks_interceptions", 8),
        ("tackles", 4),
        ("recoveries", 7),
        ("started", False),
        ("element_code", 999_999),
    ],
)
def test_any_change_to_a_scored_field_moves_the_fingerprint(field_name: str, value: object) -> None:
    corpus = _corpus()
    before = corpus.fingerprint
    corpus.rows_by_gameweek[2][0] = replace(corpus.rows_by_gameweek[2][0], **{field_name: value})
    assert corpus.fingerprint != before, f"{field_name} changed without moving the fingerprint"


def test_a_corrected_fixture_result_moves_the_fingerprint() -> None:
    """The case that motivated the item: a re-ingest fixing one scoreline."""
    corpus = _corpus()
    before = corpus.fingerprint
    corpus.fixtures_by_event[2][0] = replace(corpus.fixtures_by_event[2][0], team_h_score=3)
    assert corpus.fingerprint != before


def test_a_missing_gameweek_moves_the_fingerprint() -> None:
    corpus = _corpus()
    before = corpus.fingerprint
    del corpus.rows_by_gameweek[2]
    assert corpus.fingerprint != before


def test_two_seasons_with_identical_rows_fingerprint_differently() -> None:
    assert _corpus("2025-26").fingerprint != _corpus("2024-25").fingerprint


@pytest.mark.parametrize("attribute", ["name_by_element", "price_by_element"])
def test_display_only_data_is_deliberately_excluded(attribute: str) -> None:
    """Names and prices cannot move a score, so letting them move the
    fingerprint would make it change for reasons that cannot affect the number
    it is guarding — and a guard that cries wolf gets ignored."""
    corpus = _corpus()
    before = corpus.fingerprint
    getattr(corpus, attribute).clear()
    assert corpus.fingerprint == before


def test_the_fingerprint_is_a_declared_hash_not_a_bare_hex_string() -> None:
    """Matches the `sha256:` convention every other hash in this repo uses, so
    a future change of algorithm is visible in stored artifacts."""
    fingerprint = _corpus().fingerprint
    assert fingerprint.startswith("sha256:")
    assert len(fingerprint) == len("sha256:") + 64


def test_a_golden_corpus_replays_to_a_known_fingerprint() -> None:
    """The replayable run #153 asked for.

    If this value changes, either the corpus construction above changed or the
    fingerprint definition did. Both are things a reviewer should be told about
    explicitly rather than discovering when a backtest metric drifts.

    Moved from 97211ac7 when the defensive-contribution components joined, and
    from 1af90f94 when BPS became a model input. A value the projection reads
    that the fingerprint does not cover is a re-ingest that can move the model
    with nothing to say it did.
    """
    assert _corpus().fingerprint == (
        "sha256:4307f7e004e57f751ce6e9b2e54f8009a2c5b43a2453f39f76c0c34f2983cd1d"
    )
