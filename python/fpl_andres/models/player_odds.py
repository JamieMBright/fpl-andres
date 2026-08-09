"""A bookmaker's view of one player in one match.

The fixture-level artifact prices a team: how many goals, how likely a clean
sheet. It says nothing about who scores them. FPL pays a player, so the gap
between the two is the whole reason a striker with a thin record and a settled
starting place is mispriced by a model reading last season only.

Probabilities, never prices. A quoted price carries the book's margin and is
not a probability until the margin is removed, and every field here has been
through `devig_shin`. Two-way markets are de-vigged as a pair; anytime-scorer
markets are quoted one player at a time against an implicit "no", so each is
de-vigged on its own two-way book.

Nothing here emits or implies a betting recommendation. A price is read as a
probability and used as evidence about a footballer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

__all__ = ["PlayerMatchOdds", "PlayerOddsArtifact"]


@dataclass(frozen=True)
class PlayerMatchOdds:
    """What the market thinks one player does in one match."""

    #: FPL element id, once crosswalked. None while the name is unmatched.
    element_id: int | None
    #: The bookmaker's name for him, kept so an unmatched row can be chased.
    quoted_name: str
    #: The fixture, as the book named it. A player market says nothing about
    #: which of the two sides he plays for; the crosswalk settles that.
    home_team: str
    away_team: str
    kickoff: datetime | None
    #: FPL club code, filled by the crosswalk. None while unmatched.
    club: str | None = None
    #: P(scores at least once), de-vigged.
    anytime_goal: float | None = None
    #: P(assists at least once), where the book prices it.
    anytime_assist: float | None = None
    #: P(shown a card).
    card: float | None = None
    #: P(one or more shots on target), a proxy for being on the pitch.
    shot_on_target: float | None = None
    #: How many books were averaged into the numbers above.
    books: int = 0

    @property
    def priced(self) -> bool:
        """False when the row carries a name and nothing else."""
        return any(
            value is not None
            for value in (
                self.anytime_goal,
                self.anytime_assist,
                self.card,
                self.shot_on_target,
            )
        )


@dataclass(frozen=True)
class PlayerOddsArtifact:
    """Everything one ingest run read, and where it read it."""

    season: str
    fetched_at: datetime
    source: str
    players: tuple[PlayerMatchOdds, ...]

    @property
    def matched(self) -> int:
        return sum(1 for player in self.players if player.element_id is not None)
