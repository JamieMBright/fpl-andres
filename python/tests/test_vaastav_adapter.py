import hashlib
from datetime import UTC, datetime

import pytest

from fpl_andres.adapters.vaastav import (
    FutureInformationError,
    VaastavRevision,
    parse_gameweek_csv,
)

REVISION = "a" * 40
DATA_AVAILABLE_AT = datetime(2026, 7, 1, 12, tzinfo=UTC)
PREDICTION_CUTOFF = datetime(2026, 7, 1, 13, tzinfo=UTC)
FETCHED_AT = datetime(2026, 7, 29, 18, tzinfo=UTC)


def test_gameweek_archive_is_pinned_and_excludes_same_gw_xp() -> None:
    raw_csv = b"name,total_points,xP,minutes\nPlayer A,8,7.5,90\n"
    revision = VaastavRevision(commit_sha=REVISION, season="2025-26")

    batch = parse_gameweek_csv(
        raw_csv,
        revision=revision,
        gameweek=38,
        fetched_at=FETCHED_AT,
        data_available_at=DATA_AVAILABLE_AT,
        prediction_cutoff=PREDICTION_CUTOFF,
    )

    assert revision.gameweek_url(38).endswith(f"/{REVISION}/data/2025-26/gws/gw38.csv")
    assert batch.rows == ({"name": "Player A", "total_points": "8", "minutes": "90"},)
    assert batch.excluded_fields == ("xP",)
    assert batch.snapshot.source == "vaastav"
    assert batch.snapshot.content_hash == f"sha256:{hashlib.sha256(raw_csv).hexdigest()}"
    assert batch.snapshot.data_available_at == DATA_AVAILABLE_AT
    assert batch.snapshot.fetched_at == FETCHED_AT


def test_archive_rejects_unpinned_revision() -> None:
    with pytest.raises(ValueError, match="40-character commit"):
        VaastavRevision(commit_sha="main", season="2025-26")


def test_archive_rejects_information_available_after_prediction_cutoff() -> None:
    with pytest.raises(FutureInformationError, match="prediction cutoff"):
        parse_gameweek_csv(
            b"name,total_points\nPlayer A,8\n",
            revision=VaastavRevision(commit_sha=REVISION, season="2025-26"),
            gameweek=38,
            fetched_at=FETCHED_AT,
            data_available_at=PREDICTION_CUTOFF,
            prediction_cutoff=DATA_AVAILABLE_AT,
        )
