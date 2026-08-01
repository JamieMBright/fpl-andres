"""The crosswalk candidate set is already bounded by squad size.

Audit item #36 said shared surnames make the candidate set "grow quadratically
with no bound". The bound exists: candidates are keyed by
`(season, canonical club, spelling)`, so a name shared across clubs never
competes and the largest bucket is the number of same-named players registered
at one club in one season.

Measured under the worst case the item describes — every player at every club
sharing a name — the largest bucket equals the per-club count exactly: 25 players
per club gives a bucket of 25, 100 gives 100. It scales with squad size, which
the Premier League caps at 25 senior registrations, not with the dataset.

No cap added. A cap would silently discard a candidate that might have been the
correct match, which is worse than examining twenty-five of them.
"""

from __future__ import annotations

from dataclasses import dataclass

from fpl_andres.crosswalk.resolve import _index


@dataclass(frozen=True)
class _Foreign:
    name: str
    club: str
    season: str
    source_id: str
    goals: int = 1
    minutes: int = 900


def _squad(club: str, size: int, name: str = "John Smith") -> list[_Foreign]:
    return [
        _Foreign(name=name, club=club, season="2025-26", source_id=f"{club}-{index}")
        for index in range(size)
    ]


def test_a_shared_name_across_clubs_never_shares_a_bucket() -> None:
    """The key that provides the bound #36 said was missing."""
    players = [*_squad("Arsenal", 25), *_squad("Chelsea", 25), *_squad("Liverpool", 25)]

    index = _index(players)  # type: ignore[arg-type]

    assert max(len(bucket) for bucket in index.values()) == 25
    assert len(players) == 75


def test_the_largest_bucket_tracks_squad_size_not_dataset_size() -> None:
    """Quadratic growth would show the bucket rising with the total. It does
    not: it equals the per-club count at every scale."""
    for per_club in (10, 25, 50):
        players = [
            player
            for club in ("Arsenal", "Chelsea", "Liverpool", "Everton", "Fulham")
            for player in _squad(club, per_club)
        ]
        index = _index(players)  # type: ignore[arg-type]

        assert max(len(bucket) for bucket in index.values()) == per_club
        assert len(players) == per_club * 5


def test_different_seasons_do_not_share_a_bucket_either() -> None:
    """A player at the same club in two seasons is two candidates, and the
    season key keeps them apart."""
    players = [
        _Foreign(name="John Smith", club="Arsenal", season=season, source_id=season)
        for season in ("2023-24", "2024-25", "2025-26")
    ]

    index = _index(players)  # type: ignore[arg-type]

    assert all(len(bucket) == 1 for bucket in index.values())


def test_an_unrecognised_club_is_dropped_rather_than_pooled() -> None:
    """Otherwise every unmappable club would collapse into one bucket, which is
    the unbounded growth #36 was worried about, arriving by a different route."""
    players = [
        _Foreign(name="John Smith", club="Not A Real Club", season="2025-26", source_id="x"),
        *_squad("Arsenal", 3),
    ]

    index = _index(players)  # type: ignore[arg-type]

    assert max(len(bucket) for bucket in index.values()) == 3
    assert all("Not A Real Club" not in key for key in index)
