"""Flatten the captaincy picks into something a browser can hold.

Fourteen methods times about 32 scored gameweeks times four seasons is roughly
eighteen hundred armbands. Written out as objects with a name, a club and an
opponent on every row that is a quarter of a megabyte of mostly repeated
strings, in a file the web app imports at build time and ships to every reader.

So the picks are emitted as a table plus an index. Names and clubs appear once
each and a pick is a three-element array pointing into them. The same eighteen
hundred armbands land in about a tenth of the space, and the shape is still
something a person can read in the diff of a refresh commit.

The opponent is written pre-cased -- upper for home, lower for away, joined by
a space in a double gameweek -- because that convention already exists on the
season plan and having two places compute it is how the two come to disagree.
An empty string is a blank gameweek, which is a real thing a captain can have
when his club is not playing and he was picked anyway.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any

from fpl_andres.backtesting.captain_policies import CaptainCandidate
from fpl_andres.backtesting.captaincy import CaptaincyScore
from fpl_andres.backtesting.corpus import SeasonCorpus

__all__ = ["MATHS_FIELDS", "opponent_labels", "picks_payload"]

MAPPING_PROXY_EMPTY: Mapping[int, Sequence[CaptainCandidate]] = MappingProxyType({})


def opponent_labels(corpus: SeasonCorpus, gameweek: int) -> dict[int, str]:
    """Each club's opponents that gameweek, cased to carry the venue.

    Keyed by club id rather than by player so a double gameweek is resolved
    once for the twenty clubs instead of once for six hundred players.
    """
    labels: dict[int, str] = {}
    for team_id in corpus.short_name_by_team:
        parts: list[str] = []
        for fixture in corpus.fixtures_for(team_id, gameweek):
            opponent = fixture.opponent_of(team_id)
            if opponent is None:
                continue
            short = corpus.short_name_by_team.get(opponent)
            if short is None:
                continue
            parts.append(short.upper() if fixture.is_home(team_id) else short.lower())
        labels[team_id] = " ".join(parts)
    return labels


def picks_payload(
    corpus: SeasonCorpus,
    rows: Sequence[tuple[str, str, CaptaincyScore]],
    shortlists: Mapping[int, Sequence[CaptainCandidate]] = MAPPING_PROXY_EMPTY,
) -> dict[str, Any]:
    """The per-gameweek armbands, indexed rather than repeated.

    ``rows`` is an ordered sequence of ``(group, label, score)``. Ordered, so
    the artifact does not reshuffle between runs on dictionary iteration and
    make every refresh look like a change. A sequence rather than a mapping
    because ``components`` is the name of both a ranking method and a thesis:
    keyed by label alone the two collide and one is silently dropped.

    ``shortlists`` is the pool each armband was chosen from. It is what turns a
    surprising pick from something to be defended into something to be read.
    """
    gameweeks = sorted({pick.gameweek for _, _, score in rows for pick in score.picks})
    if not gameweeks:
        return {}

    opponents_by_gameweek = {week: opponent_labels(corpus, week) for week in gameweeks}
    column = {week: index for index, week in enumerate(gameweeks)}

    players: dict[str, list[Any]] = {}
    clubs: dict[str, str] = {}
    table: list[dict[str, Any]] = []

    for group, label, score in rows:
        # One slot per scored gameweek, null where the method named nobody, so
        # a reader can see the hole rather than the columns silently closing up.
        cells: list[list[Any] | None] = [None] * len(gameweeks)
        for pick in score.picks:
            element = pick.element_id
            team_id = corpus.team_by_element.get(element)
            club_code = corpus.code_by_team.get(team_id) if team_id is not None else None
            if club_code is not None:
                clubs[str(club_code)] = corpus.short_name_by_team.get(team_id or 0, "")
            players.setdefault(
                str(element),
                [corpus.name_by_element.get(element, f"#{element}"), club_code],
            )
            cells[column[pick.gameweek]] = [
                element,
                pick.points,
                opponents_by_gameweek[pick.gameweek].get(team_id or 0, ""),
            ]
        table.append({"group": group, "label": label, "picks": cells})

    picked_by_gameweek: dict[int, set[int]] = {}
    for _, _, score in rows:
        for pick in score.picks:
            picked_by_gameweek.setdefault(pick.gameweek, set()).add(pick.element_id)

    maths = _maths(shortlists, picked_by_gameweek, gameweeks)
    for week_entries in maths:
        for key in week_entries:
            element = int(key)
            team = corpus.team_by_element.get(element)
            club_code = corpus.code_by_team.get(team) if team is not None else None
            if club_code is not None:
                clubs[str(club_code)] = corpus.short_name_by_team.get(team or 0, "")
            players.setdefault(
                key,
                [corpus.name_by_element.get(element, f"#{element}"), club_code],
            )

    return {
        "gameweeks": gameweeks,
        "clubs": clubs,
        "players": players,
        "ceiling": _ceilings(rows, gameweeks, column),
        "rows": table,
        "maths": maths,
    }


#: How many of the best-projected candidates are published per gameweek. Enough
#: to show what a pick was chosen *over*, few enough that 127 gameweeks of them
#: still fit in a lazily loaded chunk.
RIVALS_PER_GAMEWEEK = 6

#: The order the numbers appear in a published row. Read by the web app.
MATHS_FIELDS = (
    "expectedPoints",
    "componentPoints",
    "recentPoints",
    "probabilityStart",
    "ownership",
    "ceilingPoints",
    "fixtureEase",
)


def _maths(
    shortlists: Mapping[int, Sequence[CaptainCandidate]],
    picked_by_gameweek: Mapping[int, set[int]],
    gameweeks: list[int],
) -> list[dict[str, list[float | None]]]:
    """The numbers each policy actually read, per gameweek.

    Restricted to the union of the best-projected few and everybody some policy
    named. That is exactly the set needed to answer "why him and not the obvious
    one": the pick is present because it was picked, and the obvious one is
    present because it projected well.

    Published as bare arrays against ``MATHS_FIELDS`` rather than as objects,
    because twenty-five thousand keys of ``"probabilityStart"`` is most of the
    file.
    """
    out: list[dict[str, list[float | None]]] = []
    for week in gameweeks:
        shortlist = shortlists.get(week, ())
        if not shortlist:
            out.append({})
            continue
        best = sorted(shortlist, key=lambda entry: -entry.expected_points)
        keep = {entry.element_id for entry in best[:RIVALS_PER_GAMEWEEK]}
        keep |= picked_by_gameweek.get(week, set())
        out.append(
            {
                str(entry.element_id): [
                    round(entry.expected_points, 2),
                    round(entry.component_points, 2),
                    None if entry.recent_points is None else round(entry.recent_points, 2),
                    round(entry.probability_start, 3),
                    round(entry.ownership, 1),
                    round(entry.ceiling_points, 2),
                    round(entry.fixture_ease, 3),
                ]
                for entry in best
                if entry.element_id in keep
            }
        )
    return out


def _ceilings(
    rows: Sequence[tuple[str, str, CaptaincyScore]],
    gameweeks: list[int],
    column: Mapping[int, int],
) -> list[int | None]:
    """The best return available on the shortlist, per gameweek.

    Every method sees the same shortlist in the same week, so this is one row
    rather than fourteen copies of it. It is what makes a cell readable: eight
    points is a good week or a wasted one depending on what was on offer.
    """
    best: list[int | None] = [None] * len(gameweeks)
    for _, _, score in rows:
        for pick in score.picks:
            index = column[pick.gameweek]
            current = best[index]
            if current is None or pick.best_points > current:
                best[index] = pick.best_points
    return best
