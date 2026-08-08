"""Small guarantees that were true and untested, and one that was not stated.

Each is a place where the code was
either already correct in a way nothing recorded, or correct only because of
something written thirty lines away.
"""

from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from tests.builders import credentials

from fpl_andres.contracts import PublicTeamPick, PublicTeamState
from fpl_andres.models import minutes as minutes_module
from fpl_andres.models.player_rates import (
    InconsistentObservationBasis,
    RateObservation,
    _totals,
)
from fpl_andres.persistence.supabase import SupabaseRestClient
from fpl_andres.rules import RulesContractError, _required_int, _required_number

CUTOFF = datetime(2026, 9, 12, 9, tzinfo=UTC)


class TestValidationWording:
    """#18: two spellings of one class of failure."""

    def test_every_type_failure_reads_the_same_way(self) -> None:
        with pytest.raises(RulesContractError) as integer_error:
            _required_int({"a": "15"}, "a", "game_settings")
        with pytest.raises(RulesContractError) as number_error:
            _required_number({"a": "1.5"}, "a", "game_settings")

        assert "must be an integer, not str" in str(integer_error.value)
        assert "must be a number, not str" in str(number_error.value)

    def test_the_message_names_what_arrived(self) -> None:
        # An FPL payload that starts sending "15" instead of 15 is a real
        # change, and a message saying only "must be an integer" sends somebody
        # to look at the wrong thing.
        with pytest.raises(RulesContractError, match="not bool"):
            _required_int({"a": True}, "a", "game_settings")
        with pytest.raises(RulesContractError, match="not NoneType"):
            _required_int({"a": None}, "a", "game_settings")

    def test_a_top_level_rule_does_not_begin_with_a_full_stop(self) -> None:
        # The type checks built the path themselves and did not handle an empty
        # parent, so a top-level rule failed with ".squad_size must be ...".
        with pytest.raises(RulesContractError) as error:
            _required_int({"squad_size": "15"}, "squad_size", "")
        assert not str(error.value).startswith(".")
        assert str(error.value).startswith("squad_size")


class TestObservationBasis:
    """#32: a substitution that was unreachable, and read as a default."""

    def _observation(self, *, expected: bool) -> RateObservation:
        return RateObservation(
            season="2025-26",
            event_id=1,
            minutes=90,
            goals=1,
            assists=0,
            expected_goals=0.4 if expected else None,
            expected_assists=0.2 if expected else None,
            kickoff_time=CUTOFF - timedelta(days=30),
        )

    def test_a_complete_set_totals_the_expected_columns(self) -> None:
        goals, assists = _totals((self._observation(expected=True),), use_expected=True)
        assert goals == pytest.approx(0.4)
        assert assists == pytest.approx(0.2)

    def test_a_missing_expected_value_raises_instead_of_counting_zero(self) -> None:
        # It was `observation.expected_goals or 0.0`, which is unreachable
        # today and is the problem: a silent zero standing thirty lines from
        # the guarantee that makes it unreachable is a zero somebody will one
        # day reach, and the failure would be a player credited with no
        # expected goals rather than an error.
        with pytest.raises(InconsistentObservationBasis, match="event 1"):
            _totals((self._observation(expected=False),), use_expected=True)

    def test_the_actual_basis_is_unaffected(self) -> None:
        goals, assists = _totals((self._observation(expected=False),), use_expected=False)
        assert goals == pytest.approx(1.0)
        assert assists == pytest.approx(0.0)

    def test_a_genuine_zero_is_not_confused_with_absence(self) -> None:
        # The old `or 0.0` produced the same answer for both, which is why the
        # bug was invisible: a player with 0.0 expected goals and a player with
        # none at all were indistinguishable.
        blank = RateObservation(
            season="2025-26",
            event_id=2,
            minutes=90,
            goals=0,
            assists=0,
            expected_goals=0.0,
            expected_assists=0.0,
            kickoff_time=CUTOFF - timedelta(days=30),
        )
        goals, _ = _totals((blank,), use_expected=True)
        assert goals == pytest.approx(0.0)


class TestDecayWeights:
    """#37, disproved."""

    def test_the_weights_are_computed_once_and_reused(self) -> None:
        # The item asked for the decay-weight computation to be hoisted out of
        # a per-observation loop. There is no such loop: the weights are a
        # single dict comprehension, and every later use is a lookup keyed by
        # event id. There is nothing to hoist.
        source = inspect.getsource(minutes_module.project_minutes)
        assert source.count("0.5\n        **") + source.count("0.5 **") == 1
        assert "weights[o.event_id]" in inspect.getsource(minutes_module)

    def test_each_weight_depends_only_on_its_own_event(self) -> None:
        # Which is why it cannot be hoisted even in principle.
        source = inspect.getsource(minutes_module.project_minutes)
        assert "prediction_event - observation.event_id" in source


class TestClientClose:
    """#68: safe twice, and safe before the constructor finished."""

    def test_closing_twice_is_harmless(self) -> None:
        client = SupabaseRestClient(
            credentials(), transport=httpx.MockTransport(lambda _: httpx.Response(200))
        )
        client.close()
        client.close()

    def test_closing_a_partially_built_client_does_not_mask_the_real_error(self) -> None:
        # A `finally` around a failed constructor would otherwise raise
        # AttributeError, replacing the real error at exactly the moment
        # somebody is trying to read it.
        partial = SupabaseRestClient.__new__(SupabaseRestClient)
        partial.close()

    def test_the_context_manager_still_closes(self) -> None:
        client = SupabaseRestClient(
            credentials(), transport=httpx.MockTransport(lambda _: httpx.Response(200))
        )
        with client:
            pass
        client.close()


class TestTimestampRoundTrip:
    """#69: the wire format the TypeScript contract will accept."""

    def _state(self) -> PublicTeamState:
        return PublicTeamState(
            entry_id=1,
            event=5,
            bank_tenths=10,
            squad_value_tenths=1000,
            event_transfers=0,
            event_transfer_cost_points=0,
            total_transfers=0,
            active_chip=None,
            picks=tuple(
                PublicTeamPick(
                    element_id=100 + index,
                    squad_position=index + 1,
                    multiplier=1 if index < 11 else 0,
                    is_captain=index == 0,
                    is_vice_captain=index == 1,
                )
                for index in range(15)
            ),
            state_as_of=datetime(2026, 8, 21, 17, 30, tzinfo=UTC),
            data_available_at=datetime(2026, 8, 21, 18, 0, tzinfo=UTC),
            evidence_level="observed",
            source_hashes=("sha256:" + "a" * 64,),
        )

    @pytest.mark.parametrize("field", ["stateAsOf", "dataAvailableAt"])
    def test_the_wire_format_ends_in_z_not_an_offset(self, field: str) -> None:
        # `datetime.isoformat()` produces "+00:00", and zod's `z.iso.datetime()`
        # rejects offsets by default -- verified against zod 4.4.3: "Z" and
        # ".000Z" accepted, "+00:00" rejected. Pydantic emits "Z", so the round
        # trip is safe; nothing recorded that it was, and a hand-rolled
        # `isoformat()` anywhere on this path would break the contract in a way
        # only a browser would see.
        payload = json.loads(self._state().model_dump_json(by_alias=True))
        assert payload[field].endswith("Z")
        assert "+00:00" not in payload[field]

    def test_a_round_trip_preserves_the_instant(self) -> None:
        # Through the JSON string, not a dict: the model is strict, so a dict
        # of JSON scalars is refused on principle and only the wire form is a
        # real round trip.
        original = self._state()
        restored = PublicTeamState.model_validate_json(original.model_dump_json(by_alias=True))
        assert restored.state_as_of == original.state_as_of
        assert restored.data_available_at == original.data_available_at

    def test_the_restored_timestamp_is_still_aware_and_utc(self) -> None:
        restored = PublicTeamState.model_validate_json(self._state().model_dump_json(by_alias=True))
        assert restored.state_as_of.tzinfo is not None
        assert restored.state_as_of.utcoffset() == timedelta(0)

    def test_a_naive_timestamp_is_refused_on_the_way_in(self) -> None:
        payload = json.loads(self._state().model_dump_json(by_alias=True))
        payload["stateAsOf"] = "2026-08-21T17:30:00"
        with pytest.raises(ValueError, match="stateAsOf"):
            PublicTeamState.model_validate_json(json.dumps(payload))

    def test_a_non_utc_offset_is_refused_on_the_way_in(self) -> None:
        # Not merely converted: a timestamp in another zone is evidence that
        # something upstream is not doing what this contract assumes.
        payload = json.loads(self._state().model_dump_json(by_alias=True))
        payload["stateAsOf"] = "2026-08-21T18:30:00+01:00"
        with pytest.raises(ValueError, match="stateAsOf"):
            PublicTeamState.model_validate_json(json.dumps(payload))
