"""The typed payload shapes describe what this repository actually reads.

Audit item #140. The client returned ``dict[str, Any]`` for every endpoint,
which is honest about the transport and useless as documentation: nothing
recorded which of FPL's roughly two hundred fields this project depends on, and
a mistyped key type-checked cleanly and failed at runtime.

Two things are worth testing and one is not.

Worth testing: that a typo is now a type error (otherwise the change bought
nothing), and that every key the production code reads is declared (otherwise
the documentation is wrong, which is worse than absent).

Not worth testing: that FPL sends these fields. It is not a promise anybody
made, which is why the TypedDicts are ``total=False`` and why refusal still
lives in ``rules.py`` and the Pydantic models.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import get_type_hints

import pytest

from fpl_andres.adapters import payloads

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "python" / "fpl_andres"


def _keys(shape: type) -> set[str]:
    return set(get_type_hints(shape))


class TestDeclaredShapes:
    def test_every_shape_is_total_false(self) -> None:
        # Marking a key required would claim a guarantee FPL never gave, and
        # would make mypy enforce it on our reads rather than on their writes.
        for name in payloads.__all__:
            shape = getattr(payloads, name)
            assert shape.__total__ is False, f"{name} is total=True"

    def test_bootstrap_declares_what_capture_crowd_reads(self) -> None:
        assert {"total_players", "events", "elements"} <= _keys(payloads.BootstrapPayload)
        assert {"deadline_time", "is_current", "is_next", "id"} <= _keys(payloads.BootstrapEvent)

    def test_bootstrap_declares_what_the_rules_validator_reads(self) -> None:
        assert {"game_settings", "game_config", "element_types", "chips"} <= _keys(
            payloads.BootstrapPayload
        )
        assert {
            "id",
            "squad_select",
            "squad_min_play",
            "squad_max_play",
            "singular_name_short",
        } <= _keys(payloads.BootstrapElementType)

    def test_history_declares_what_the_veteran_cohort_reads(self) -> None:
        assert "past" in _keys(payloads.EntryHistoryPayload)
        assert {"season_name", "rank", "total_points"} <= _keys(payloads.PastSeason)

    def test_picks_declares_what_rivals_and_team_state_read(self) -> None:
        assert {"element", "is_captain", "is_vice_captain", "position", "multiplier"} <= _keys(
            payloads.Pick
        )
        assert {"active_chip", "entry_history", "picks"} <= _keys(payloads.PicksPayload)
        assert {
            "event",
            "bank",
            "value",
            "event_transfers",
            "event_transfers_cost",
        } <= _keys(payloads.EntryHistorySummary)

    def test_standings_declares_what_read_league_reads(self) -> None:
        assert {"league", "standings"} <= _keys(payloads.StandingsPayload)
        assert {"entry", "entry_name", "player_name", "rank", "total"} <= _keys(
            payloads.StandingsResult
        )

    def test_entry_declares_what_normalize_entry_reads(self) -> None:
        assert {
            "id",
            "name",
            "started_event",
            "current_event",
            "last_deadline_bank",
            "last_deadline_value",
            "last_deadline_total_transfers",
        } <= _keys(payloads.EntryPayload)

    def test_fixtures_declares_what_the_opening_squad_publisher_reads(self) -> None:
        assert {"id", "event", "team_h", "team_a"} <= _keys(payloads.FixturePayload)

    def test_elements_stays_loose_because_pydantic_owns_it(self) -> None:
        # Two descriptions of the same rows, one checked and one not, is worse
        # than one. bootstrap.parse_elements validates each element against a
        # model the caller chooses.
        hints = get_type_hints(payloads.BootstrapPayload)
        assert str(hints["elements"]) == "list[dict[str, typing.Any]]"


class TestTypeCheckingCatchesTypos:
    """The change is only worth having if mypy now refuses a wrong key."""

    @pytest.mark.slow
    def test_a_mistyped_key_is_a_type_error(self, tmp_path: Path) -> None:
        # Before this, `payload["last_deadline_bnk"]` type-checked cleanly and
        # failed in production. Running mypy for real because the claim is
        # about mypy, and asserting it any other way would be asserting a
        # belief about mypy instead.
        probe = tmp_path / "probe.py"
        probe.write_text(
            "from fpl_andres.adapters.payloads import EntryPayload\n"
            "def read(payload: EntryPayload) -> object:\n"
            "    return payload['last_deadline_bnk']\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, "-m", "mypy", "--no-error-summary", str(probe)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT / "python",
            check=False,
        )
        assert result.returncode != 0, "mypy accepted a key that does not exist"
        assert "last_deadline_bnk" in result.stdout

    @pytest.mark.slow
    def test_a_correct_key_is_accepted(self, tmp_path: Path) -> None:
        probe = tmp_path / "probe_ok.py"
        probe.write_text(
            "from fpl_andres.adapters.payloads import EntryPayload\n"
            "def read(payload: EntryPayload) -> object:\n"
            "    return payload['last_deadline_bank']\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, "-m", "mypy", "--no-error-summary", str(probe)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT / "python",
            check=False,
        )
        assert result.returncode == 0, result.stdout


class TestTheClientUsesThem:
    def test_no_fetch_method_still_returns_an_untyped_object(self) -> None:
        # element-summary is the exception and says so: nothing in Python reads
        # it, so there is no set of keys to declare and inventing one would be
        # documentation of a dependency that does not exist.
        source = (SOURCE / "adapters" / "fpl.py").read_text(encoding="utf-8")
        untyped = re.findall(
            r"async def (fetch_\w+)\([^)]*\)\s*->\s*FetchedPayload\[dict\[str, Any\]\]",
            source,
            re.DOTALL,
        )
        assert untyped == ["fetch_element_summary"], untyped

    def test_the_transport_check_is_unchanged(self) -> None:
        # The TypedDict is a cast, not a validation. What is genuinely checked
        # is still that the body is a JSON object with string keys.
        source = (SOURCE / "adapters" / "fpl.py").read_text(encoding="utf-8")
        assert "FPL response must be a JSON object" in source
        assert "FPL response must be an array of JSON objects" in source
