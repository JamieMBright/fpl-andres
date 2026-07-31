"""Fold a footballer's name down to something two websites can agree on.

Deliberately lossy. "Gabriel dos Santos Magalhães" and "Gabriel Magalhaes" must
collide, because they are the same man. That looseness is safe only because a
name collision is a *candidate* here and never a decision: `resolve` insists on
corroborating evidence before it accepts one.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["normalise", "variants"]

# Characters that survive Unicode decomposition with their letter intact, so
# stripping combining marks does not reach them. Sorted by nothing in
# particular; they are simply the ones that appear in Premier League squads.
_TRANSLITERATIONS = {
    "ß": "ss",
    "æ": "ae",
    "œ": "oe",
    "ø": "o",
    "đ": "d",
    "ð": "d",
    "þ": "th",
    "ł": "l",
    "ı": "i",
    "ŋ": "n",
}
_PUNCTUATION = re.compile(r"[.'\u2019\-_]")
_NON_LETTER = re.compile(r"[^a-z ]")
_SPACES = re.compile(r"\s+")
# Name fragments that carry no identity and differ between sources.
_PARTICLES = frozenset(
    {"de", "del", "della", "der", "di", "do", "dos", "da", "das", "van", "von", "el", "al"}
)


def normalise(name: str) -> str:
    """Casefolded ASCII letters and single spaces, with accents removed."""
    folded = name.casefold()
    for source, target in _TRANSLITERATIONS.items():
        folded = folded.replace(source, target)
    decomposed = unicodedata.normalize("NFKD", folded)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    # Punctuation joins rather than splits: "N'Golo" is one token, not two.
    stripped = _PUNCTUATION.sub("", stripped)
    return _SPACES.sub(" ", _NON_LETTER.sub(" ", stripped)).strip()


def variants(*names: str) -> frozenset[str]:
    """Every spelling of a player worth trying, from every name given.

    Includes the surname alone, because FPL frequently publishes only that,
    and the name with nobiliary particles dropped, because sources disagree on
    whether "dos Santos" belongs in the surname.
    """
    found: set[str] = set()
    for name in names:
        cleaned = normalise(name)
        if not cleaned:
            continue
        found.add(cleaned)
        tokens = cleaned.split(" ")
        if len(tokens) > 1:
            found.add(tokens[-1])
            without_particles = [token for token in tokens if token not in _PARTICLES]
            if without_particles:
                found.add(" ".join(without_particles))
                found.add(without_particles[-1])
                # First and last only: the middle names are where sources differ.
                if len(without_particles) > 2:
                    found.add(f"{without_particles[0]} {without_particles[-1]}")
    return frozenset(found)
