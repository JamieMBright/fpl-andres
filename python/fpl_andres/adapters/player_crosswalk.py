"""Match a bookmaker's player name to an FPL element id.

A book writes "Erling Haaland"; FPL stores `first_name`, `second_name` and a
`web_name` of "Haaland". Nothing joins those two without a decision about how
much difference to tolerate, and a wrong join is worse than no join: it moves
the wrong player's projection.

So this refuses anything it is not sure of. An unmatched row keeps its quoted
name and is reported, because a striker the crosswalk cannot find is a gap
somebody has to close, not a row to drop quietly.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping, Sequence

from fpl_andres.crosswalk.names import variants
from fpl_andres.models.player_odds import PlayerMatchOdds

__all__ = ["crosswalk", "fold_name"]

#: Letters NFKD leaves alone. A book usually writes the ASCII form, so these
#: have to meet in the middle or Odegaard never joins Ødegaard.
_TRANSLITERATE = str.maketrans(
    {
        "\u00d8": "O",
        "\u00f8": "o",
        "\u00c6": "AE",
        "\u00e6": "ae",
        "\u0110": "D",
        "\u0111": "d",
        "\u00d0": "D",
        "\u00f0": "d",
        "\u00de": "Th",
        "\u00fe": "th",
        "\u0141": "L",
        "\u0142": "l",
        "\u00df": "ss",
    }
)

# Provider spellings observed in live player markets. Keep this explicit: a
# broad fuzzy match can move one footballer's price onto another footballer.
_FIRST_NAME_ALIASES = {"ben": "benjamin", "brendan": "brenden"}

# One-off provider names observed in live player markets where FPL's bootstrap
# carries only a shorter public name. Values are FPL element ids; ambiguity is
# still refused everywhere else.
_QUOTED_NAME_OVERRIDES = {
    "abdul fatawu issahaku": 315,
    "alvaro daniel rodriguez munoz": 201,
    "alysson edward": 52,
    "chiedoze ogbene": 314,
    "christopher rigg": 548,
    "damian emiliano martinez": 28,
    "degnand wilfried gnonto": 341,
    "edward nketiah": 224,
    "emile smith rowe": 262,
    "emile smithrowe": 262,
    "iliman cheikh ndiaye": 237,
    "ilimancheikh ndiaye": 237,
    "iliya gruev": 344,
    "iyenoma destiny udogie": 506,
    "jaden philogene bidace": 318,
    "jaden philogenebidace": 318,
    "jens hjerto dahl": 574,
    "jocelin ta bi": 550,
    "joseph willock": 460,
    "joshua kofi acheampong": 151,
    "kaine hayden": 177,
    "kai andrews": 192,
    "konstantinos tsimikas": 364,
    "marcelino ignacio nunez espinoza": 309,
    "mickey van de ven": 503,
    "mamodou sarr": 150,
    "niko oreilly": 387,
    "nilson david angulo ramirez": 551,
    "ogochukwu onyeka frank": 104,
    "oliver mcburnie": 295,
    "omari giraud hutchinson": 484,
    "omari giraudhutchinson": 484,
    "rayan ait nouri": 392,
    "valentino livramento": 450,
    "vitaliy mykolenko": 233,
    "yeremi pino": 211,
}


def fold_name(value: str) -> str:
    """Lower case, no accents, no punctuation. Joins on this or not at all."""
    stripped = unicodedata.normalize("NFKD", value.translate(_TRANSLITERATE))
    without_marks = "".join(char for char in stripped if not unicodedata.combining(char))
    return " ".join(
        "".join(char.lower() for char in without_marks if char.isalnum() or char == " ").split()
    )


def _expand_first_name_alias(value: str) -> str:
    tokens = value.split()
    if tokens:
        tokens[0] = _FIRST_NAME_ALIASES.get(tokens[0], tokens[0])
    return " ".join(tokens)


def _keys(element: Mapping[str, object]) -> set[str]:
    first = str(element.get("first_name") or "")
    second = str(element.get("second_name") or "")
    web = str(element.get("web_name") or "")
    candidates = {
        f"{first} {second}",
        second,
        web,
        f"{first} {web}",
    }
    candidates.update(variants(f"{first} {second}", second, web))
    return {fold_name(name) for name in candidates if name.strip()}


def _unordered_keys(names: Iterable[str]) -> set[str]:
    return {
        " ".join(sorted(tokens)) for name in names if len(tokens := fold_name(name).split()) > 1
    }


def crosswalk(
    rows: Sequence[PlayerMatchOdds],
    elements: Iterable[Mapping[str, object]],
    clubs_by_id: Mapping[int, str],
) -> tuple[tuple[PlayerMatchOdds, ...], tuple[str, ...]]:
    """
    Rows with element ids where the name is unambiguous, and the names left.

    A fold that maps to two different elements is dropped rather than guessed.
    Two players really can share a surname, and picking one of them at random
    would move a projection with no evidence behind it.
    """
    index: dict[str, set[int]] = {}
    unordered_index: dict[str, set[int]] = {}
    club_of: dict[int, str] = {}
    element_ids: set[int] = set()
    for element in elements:
        element_id = element.get("id")
        team = element.get("team")
        if not isinstance(element_id, int):
            continue
        element_ids.add(element_id)
        keys = _keys(element)
        for key in keys:
            index.setdefault(key, set()).add(element_id)
        for key in _unordered_keys(keys):
            unordered_index.setdefault(key, set()).add(element_id)
        if isinstance(team, int) and team in clubs_by_id:
            club_of[element_id] = clubs_by_id[team]

    matched: list[PlayerMatchOdds] = []
    unmatched: list[str] = []
    for row in rows:
        folded = fold_name(row.quoted_name)
        override = _QUOTED_NAME_OVERRIDES.get(folded)
        candidates = (
            {override}
            if override is not None and override in element_ids
            else set(index.get(folded, set()))
        )
        expanded = _expand_first_name_alias(folded)
        if expanded != folded:
            candidates.update(index.get(expanded, set()))
        if not candidates:
            for key in _unordered_keys(variants(row.quoted_name)):
                candidates.update(unordered_index.get(key, set()))
        if len(candidates) != 1:
            unmatched.append(row.quoted_name)
            matched.append(row)
            continue
        element_id = next(iter(candidates))
        matched.append(
            PlayerMatchOdds(
                element_id=element_id,
                quoted_name=row.quoted_name,
                home_team=row.home_team,
                away_team=row.away_team,
                kickoff=row.kickoff,
                club=club_of.get(element_id),
                anytime_goal=row.anytime_goal,
                first_goal=row.first_goal,
                last_goal=row.last_goal,
                anytime_assist=row.anytime_assist,
                any_card=row.any_card,
                red_card=row.red_card,
                shots=row.shots,
                shots_on_target=row.shots_on_target,
                observed_at=row.observed_at,
                books=row.books,
            )
        )
    return tuple(matched), tuple(sorted(set(unmatched)))
