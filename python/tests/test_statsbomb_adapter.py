from datetime import UTC, datetime
from pathlib import Path

import pytest

from fpl_andres.adapters.statsbomb import (
    StatsbombAdapterError,
    hash_statsbomb_bytes,
    map_statsbomb_position,
    parse_lineup_role_observations,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "statsbomb" / "lineups_sample.json"
KICKOFF = datetime(2026, 8, 15, 14, 0, tzinfo=UTC)


def _fixture_bytes() -> bytes:
    return FIXTURE_PATH.read_bytes()


def test_maps_known_statsbomb_positions_to_observed_roles() -> None:
    assert map_statsbomb_position("Goalkeeper") == "goalkeeper"
    assert map_statsbomb_position("Right Back") == "full_back"
    assert map_statsbomb_position("Left Wing Back") == "wing_back"
    assert map_statsbomb_position("Left Center Back") == "centre_back"
    assert map_statsbomb_position("Defensive Midfield") == "defensive_midfield"
    assert map_statsbomb_position("Right Midfield") == "central_midfield"
    assert map_statsbomb_position("Center Attacking Midfield") == "attacking_midfield"
    assert map_statsbomb_position("Right Wing") == "wide_forward"
    assert map_statsbomb_position("Striker") == "striker"


def test_unknown_position_is_rejected_not_defaulted() -> None:
    with pytest.raises(StatsbombAdapterError, match="unknown StatsBomb position"):
        map_statsbomb_position("Sweeper Keeper")


def test_lineup_parse_emits_expected_dominant_roles_and_minutes() -> None:
    rows = parse_lineup_role_observations(
        _fixture_bytes(),
        event_id=3,
        kickoff_time=KICKOFF,
    )

    by_player = {row.statsbomb_player_id: row.observation for row in rows}

    # Alice keeper — full 90 as goalkeeper.
    assert by_player[10].observed_role == "goalkeeper"
    assert by_player[10].minutes_played == 90

    # Bob Lundstram — defender-listed player, played the full match at attacking midfield.
    # This is the exact case the Lord Lundstram effect targets.
    assert by_player[11].observed_role == "attacking_midfield"
    assert by_player[11].minutes_played == 90

    # Cara Withdraw — went off before the minimum minutes threshold, dropped.
    assert 12 not in by_player

    # Dan Latesub — 20 minutes late sub, below default 60 threshold, dropped.
    assert 13 not in by_player

    # Erin Reverse — split match between left back and left wing back; wing back wins ties
    # only if minutes are equal, but here both were 45. Dominant is deterministic by first
    # max, which is left_back → full_back. Total minutes is 90 (well above threshold).
    assert by_player[20].observed_role == "full_back"
    assert by_player[20].minutes_played == 90


def test_kickoff_time_and_event_id_are_stamped_on_every_observation() -> None:
    rows = parse_lineup_role_observations(
        _fixture_bytes(),
        event_id=7,
        kickoff_time=KICKOFF,
    )

    assert rows, "fixture must produce at least one accepted observation"
    for row in rows:
        assert row.observation.event_id == 7
        assert row.observation.kickoff_time == KICKOFF


def test_hash_is_deterministic_and_prefixed() -> None:
    payload = _fixture_bytes()
    hash1 = hash_statsbomb_bytes(payload)
    hash2 = hash_statsbomb_bytes(payload)
    assert hash1 == hash2
    assert hash1.startswith("sha256:")
    assert len(hash1) == len("sha256:") + 64


def test_malformed_json_payload_is_rejected() -> None:
    with pytest.raises(StatsbombAdapterError, match="UTF-8 JSON"):
        parse_lineup_role_observations(
            b"not-json",
            event_id=1,
            kickoff_time=KICKOFF,
        )


def test_naive_kickoff_time_is_rejected() -> None:
    with pytest.raises(StatsbombAdapterError, match="UTC"):
        parse_lineup_role_observations(
            _fixture_bytes(),
            event_id=1,
            kickoff_time=datetime(2026, 8, 15, 14, 0),
        )
