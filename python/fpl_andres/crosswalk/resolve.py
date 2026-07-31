"""Match a foreign player id to an FPL player, and refuse when unsure.

The join is not really a name join. A name only nominates candidates; the match
is settled by quantities both sites measured independently. If FPL says a man
played 2,916 minutes and scored 29 in a season, and the other site says the same
of its candidate, they are the same footballer. Two sources agreeing to the
minute by accident is not a thing that happens.

Goals and minutes are both allowed to disagree a little, because measurement
showed that they do. Against Understat for 2025-26, FPL minutes ran 3-5% adrift
for players nobody disputes are the same man (Calafiori 1697 v 1755, Jesus 418 v
395), and goals differ by one where the Premier League's dubious goals panel has
reassigned a scorer and Opta has not (Madueke 3 v 2). Tolerances that ignored
that rejected roughly a quarter of the correct matches.

The tolerances are still far tighter than the gap between two different
footballers at the same club in the same season, which is what they exist to
catch. **Assists are reported and never gated on**: FPL awards assists under its
own rules, so a disagreement there is expected and means nothing.

The output always accounts for every FPL player. An unmatched player is named,
with the reason, because a crosswalk that quietly drops a third of the league is
worse than no crosswalk at all.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from fpl_andres.crosswalk.clubs import canonical_club
from fpl_andres.crosswalk.names import variants

__all__ = [
    "ForeignPlayer",
    "FplPlayer",
    "MatchOutcome",
    "PlayerMatch",
    "CrosswalkReport",
    "resolve_crosswalk",
]

# Measured against Understat 2025-26: the worst honest disagreement was about
# five percent. Ten percent leaves room without admitting a different player,
# who would differ by far more inside a single club-season.
_MINUTES_TOLERANCE = 0.10
_MINUTES_FLOOR = 45
# The Premier League reassigns disputed goals; Opta does not always follow.
_GOALS_TOLERANCE = 1
# Below this a season is too short for minutes and goals to identify anyone:
# plenty of fringe players have one substitute appearance and no goals.
_MINIMUM_MINUTES = 270


class MatchOutcome(StrEnum):
    """Why a player did or did not get an id on the other side."""

    VERIFIED = "verified"
    AMBIGUOUS = "ambiguous"
    CONTRADICTED = "contradicted"
    NO_CANDIDATE = "no_candidate"
    TOO_LITTLE_FOOTBALL = "too_little_football"


@dataclass(frozen=True)
class FplPlayer:
    """One FPL player-season. ``code`` is the Opta player id."""

    code: int
    season: str
    club: str
    first_name: str
    second_name: str
    web_name: str
    minutes: int
    goals: int
    assists: int


@dataclass(frozen=True)
class ForeignPlayer:
    """One player-season from a source that does not publish Opta ids."""

    source: str
    source_id: str
    season: str
    club: str
    name: str
    minutes: int
    goals: int
    assists: int


@dataclass(frozen=True)
class PlayerMatch:
    code: int
    season: str
    web_name: str
    outcome: MatchOutcome
    source_id: str | None = None
    minutes_delta: int | None = None
    goals_delta: int | None = None
    # Recorded but never gated on; FPL's assist rule is its own.
    assists_delta: int | None = None
    candidates: tuple[str, ...] = ()

    @property
    def matched(self) -> bool:
        return self.outcome is MatchOutcome.VERIFIED


@dataclass(frozen=True)
class CrosswalkReport:
    source: str
    matches: tuple[PlayerMatch, ...]
    counts: Mapping[MatchOutcome, int] = field(default_factory=dict)

    @property
    def verified(self) -> tuple[PlayerMatch, ...]:
        return tuple(match for match in self.matches if match.matched)

    def coverage(self) -> float:
        """Share of eligible players that got a verified id.

        Players with too little football are excluded from the denominator: a
        man with forty minutes is not a mapping failure, he is unidentifiable.
        """
        eligible = [
            match for match in self.matches if match.outcome is not MatchOutcome.TOO_LITTLE_FOOTBALL
        ]
        if not eligible:
            return 0.0
        return sum(1 for match in eligible if match.matched) / len(eligible)

    def by_outcome(self, outcome: MatchOutcome) -> tuple[PlayerMatch, ...]:
        return tuple(match for match in self.matches if match.outcome is outcome)


def _agrees(player: FplPlayer, candidate: ForeignPlayer) -> bool:
    if abs(player.goals - candidate.goals) > _GOALS_TOLERANCE:
        return False
    allowed = max(float(_MINUTES_FLOOR), player.minutes * _MINUTES_TOLERANCE)
    return abs(player.minutes - candidate.minutes) <= allowed


def _index(players: Iterable[ForeignPlayer]) -> dict[tuple[str, str, str], list[ForeignPlayer]]:
    """Candidates keyed by season, canonical club and one spelling of the name."""
    index: dict[tuple[str, str, str], list[ForeignPlayer]] = {}
    for player in players:
        club = canonical_club(player.club)
        if club is None:
            continue
        for spelling in variants(player.name):
            index.setdefault((player.season, club, spelling), []).append(player)
    return index


def resolve_crosswalk(
    fpl: Sequence[FplPlayer],
    foreign: Sequence[ForeignPlayer],
    *,
    source: str,
) -> CrosswalkReport:
    """Resolve every FPL player against one foreign source, season by season.

    Candidates must share a season and a club, so a name shared by two players
    at different clubs never competes. A name that still nominates more than one
    surviving candidate is reported ambiguous and mapped to nothing.
    """
    index = _index(foreign)
    matches: list[PlayerMatch] = []

    for player in fpl:
        club = canonical_club(player.club)
        nominated: dict[str, ForeignPlayer] = {}
        if club is not None:
            for spelling in variants(player.first_name, player.second_name, player.web_name):
                for candidate in index.get((player.season, club, spelling), ()):
                    nominated[candidate.source_id] = candidate

        if player.minutes < _MINIMUM_MINUTES:
            outcome = MatchOutcome.TOO_LITTLE_FOOTBALL
        elif not nominated:
            outcome = MatchOutcome.NO_CANDIDATE
        else:
            outcome = MatchOutcome.CONTRADICTED

        if outcome is MatchOutcome.CONTRADICTED:
            agreeing = [candidate for candidate in nominated.values() if _agrees(player, candidate)]
            if len(agreeing) == 1:
                accepted = agreeing[0]
                matches.append(
                    PlayerMatch(
                        code=player.code,
                        season=player.season,
                        web_name=player.web_name,
                        outcome=MatchOutcome.VERIFIED,
                        source_id=accepted.source_id,
                        minutes_delta=accepted.minutes - player.minutes,
                        goals_delta=accepted.goals - player.goals,
                        assists_delta=accepted.assists - player.assists,
                    )
                )
                continue
            if len(agreeing) > 1:
                outcome = MatchOutcome.AMBIGUOUS

        matches.append(
            PlayerMatch(
                code=player.code,
                season=player.season,
                web_name=player.web_name,
                outcome=outcome,
                candidates=tuple(sorted(nominated)),
            )
        )

    counts: dict[MatchOutcome, int] = {outcome: 0 for outcome in MatchOutcome}
    for match in matches:
        counts[match.outcome] += 1
    return CrosswalkReport(source=source, matches=tuple(matches), counts=counts)
