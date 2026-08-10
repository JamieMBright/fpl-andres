"""Harvesting the Overall league, end to end, without touching the network.

`cohorts/league.py` is tested for what a page means. This is tested for what
the command does with a sequence of them: where it stops, what it writes, and
which histories it decides it still needs. Those are the parts a scheduled
job depends on and the parts that break silently.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from fpl_andres.cli import harvest_league

#: Captured before anything is patched, so a test that runs the command twice
#: does not end up wrapping its own wrapper.
REAL_CLIENT = httpx.AsyncClient


def _standings_page(page: int, ranks: range, *, has_next: bool) -> dict[str, object]:
    return {
        "standings": {
            "has_next": has_next,
            "page": page,
            "results": [
                {"entry": 1000 + rank, "rank": rank, "total": 3000 - rank} for rank in ranks
            ],
        }
    }


def _history(entry_id: int) -> dict[str, object]:
    return {
        "past": [
            {"season_name": "2023/24", "total_points": 2400, "rank": 900 + entry_id},
            {"season_name": "2024/25", "total_points": 2500, "rank": 800 + entry_id},
        ]
    }


class _Fixture:
    """A fake FPL that serves standings pages and entry histories."""

    def __init__(self, *, pages: int, missing: frozenset[int] = frozenset()) -> None:
        self.pages = pages
        self.missing = missing
        self.requested: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requested.append(str(request.url))
        if "standings" in request.url.path:
            page = int(request.url.params["page_standings"])
            first = (page - 1) * harvest_league.PAGE_SIZE + 1
            ranks = range(first, first + harvest_league.PAGE_SIZE)
            return httpx.Response(
                200, json=_standings_page(page, ranks, has_next=page < self.pages)
            )
        entry_id = int(request.url.path.rstrip("/").split("/")[-2])
        if entry_id in self.missing:
            return httpx.Response(404)
        return httpx.Response(200, json=_history(entry_id))


@pytest.fixture
def no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    """The rate limit is real and is not what any of this is testing."""

    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(harvest_league.asyncio, "sleep", instant)


def _run(
    tmp_path: Path,
    fixture: _Fixture,
    monkeypatch: pytest.MonkeyPatch,
    *extra: str,
) -> int:
    def client(**kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("timeout", None)
        return REAL_CLIENT(  # type: ignore[return-value]
            transport=httpx.MockTransport(fixture.handler),
            **kwargs,  # type: ignore[arg-type]
        )

    monkeypatch.setattr(harvest_league.httpx, "AsyncClient", client)
    return harvest_league.main(
        [
            "--standings",
            str(tmp_path / "fpl100.json"),
            "--results",
            str(tmp_path / "managers.jsonl"),
            *extra,
        ]
    )


@pytest.mark.usefixtures("no_waiting")
class TestReadingTheStandings:
    def test_it_stops_at_the_ceiling_rather_than_reading_the_whole_league(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The Overall league holds every entry. Nobody wants every entry."""
        fixture = _Fixture(pages=40)

        assert (
            _run(
                tmp_path,
                fixture,
                monkeypatch,
                "--rank-ceiling",
                "100",
                "--skip-histories",
            )
            == 0
        )

        saved = json.loads((tmp_path / "fpl100.json").read_text(encoding="utf-8"))
        assert saved["size"] == 100
        assert saved["rankCeiling"] == 100
        assert len(fixture.requested) == 2

    def test_the_ranks_it_keeps_are_the_ranks_it_was_asked_for(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fixture = _Fixture(pages=40)

        _run(tmp_path, fixture, monkeypatch, "--rank-ceiling", "60", "--skip-histories")

        saved = json.loads((tmp_path / "fpl100.json").read_text(encoding="utf-8"))
        assert [row["rank"] for row in saved["managers"]] == list(range(1, 61))

    def test_a_league_that_has_not_started_is_written_as_empty_not_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Between seasons this runs every six hours and finds nothing."""

        def empty(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"standings": {"has_next": False, "page": 1, "results": []}}
            )

        fixture = _Fixture(pages=1)
        fixture.handler = empty  # type: ignore[method-assign]

        assert _run(tmp_path, fixture, monkeypatch, "--rank-ceiling", "100") == 0

        saved = json.loads((tmp_path / "fpl100.json").read_text(encoding="utf-8"))
        assert saved["size"] == 0
        assert (tmp_path / "managers.jsonl").exists() is False

    def test_a_payload_that_is_not_standings_stops_the_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A silent partial harvest would publish a truncated FPL100."""
        fixture = _Fixture(pages=1)
        fixture.handler = lambda _request: httpx.Response(200, json={"detail": "Not found."})  # type: ignore[method-assign,assignment]

        with pytest.raises(SystemExit):
            _run(tmp_path, fixture, monkeypatch, "--rank-ceiling", "50", "--skip-histories")


@pytest.mark.usefixtures("no_waiting")
class TestLearningTheirHistory:
    def test_it_fetches_a_history_for_everyone_the_catalogue_has_not_seen(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fixture = _Fixture(pages=1)

        assert _run(tmp_path, fixture, monkeypatch, "--rank-ceiling", "3") == 0

        lines = (tmp_path / "managers.jsonl").read_text(encoding="utf-8").splitlines()
        assert [json.loads(line)["entryId"] for line in lines] == [1001, 1002, 1003]

    def test_a_manager_already_catalogued_is_not_fetched_again(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Past seasons never change. Re-reading them is the whole cost."""
        results = tmp_path / "managers.jsonl"
        results.write_text(json.dumps({"entryId": 1002, "seasons": []}) + "\n", encoding="utf-8")
        fixture = _Fixture(pages=1)

        _run(tmp_path, fixture, monkeypatch, "--rank-ceiling", "3")

        fetched = [url for url in fixture.requested if "/entry/" in url]
        assert [url for url in fetched if "1002" in url] == []
        assert len(fetched) == 2

    def test_one_run_fetches_no_more_than_it_was_allowed_to(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A scheduled job that could run for hours is not a scheduled job."""
        fixture = _Fixture(pages=1)

        _run(tmp_path, fixture, monkeypatch, "--rank-ceiling", "20", "--max-histories", "4")

        lines = (tmp_path / "managers.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 4

    def test_an_entry_that_will_not_answer_is_counted_not_fatal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deleted accounts are ordinary. One must not end the harvest."""
        fixture = _Fixture(pages=1, missing=frozenset({1002}))

        assert _run(tmp_path, fixture, monkeypatch, "--rank-ceiling", "3") == 0

        lines = (tmp_path / "managers.jsonl").read_text(encoding="utf-8").splitlines()
        assert [json.loads(line)["entryId"] for line in lines] == [1001, 1003]

    def test_a_second_run_over_the_same_standings_does_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fixture = _Fixture(pages=1)
        _run(tmp_path, fixture, monkeypatch, "--rank-ceiling", "3")
        before = (tmp_path / "managers.jsonl").read_text(encoding="utf-8")

        _run(tmp_path, fixture, monkeypatch, "--rank-ceiling", "3")

        assert (tmp_path / "managers.jsonl").read_text(encoding="utf-8") == before
