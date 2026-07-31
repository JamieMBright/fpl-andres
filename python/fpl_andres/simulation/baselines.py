"""Baseline policies. The yardstick the method has to beat.

Three of them, weakest to strongest, all playing under identical rules: one free
transfer a week banking to five, four points for anything beyond the bank, three
players per club, a real budget.

- ``hold`` never transfers. It establishes what skill is worth at all.
- ``form_chaser`` buys the highest-scoring recent player it does not own. This is
  the conventional non-naive way people actually play, and it is the honest
  comparison.
- ``crowd`` buys whoever the game as a whole is buying, from the published
  transfer counts. Beating the aggregate decision of eleven million managers is
  the real bar, and it is a genuinely strong baseline: the crowd has access to
  team news, press conferences and each other.

Beating a policy nobody plays proves nothing, which is why ``hold`` is reported
but never claimed as evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from fpl_andres.backtesting.corpus import SeasonCorpus

__all__ = [
    "BaselineName",
    "crowd_ranking",
    "form_ranking",
    "hold_ranking",
    "ranking_for",
]

BaselineName = str


@dataclass(frozen=True)
class BaselineSettings:
    form_window: int = 4


def hold_ranking(corpus: SeasonCorpus, gameweek: int) -> dict[int, float]:
    """Nothing is ever preferred, so no transfer ever clears its cost."""
    return {}


def form_ranking(corpus: SeasonCorpus, gameweek: int, *, window: int = 4) -> dict[int, float]:
    """Mean points over the last ``window`` gameweeks, strictly before this one."""
    totals: dict[int, list[int]] = {}
    for event in range(max(1, gameweek - window), gameweek):
        for element_id, points in corpus.actual_points(event).items():
            totals.setdefault(element_id, []).append(points)
    return {
        element_id: sum(points) / len(points) for element_id, points in totals.items() if points
    }


def crowd_ranking(corpus: SeasonCorpus, gameweek: int) -> dict[int, float]:
    """Net transfers in at the previous gameweek: what the game is buying.

    Net rather than gross, because a player can be heavily traded in both
    directions during a price scare without the crowd having formed a view.
    """
    previous = gameweek - 1
    while previous >= 1:
        rows = corpus.rows_by_gameweek.get(previous, ())
        net: dict[int, float] = {}
        for row in rows:
            if row.transfers_in is None and row.transfers_out is None:
                continue
            net[row.element_id] = float((row.transfers_in or 0) - (row.transfers_out or 0))
        if net:
            return net
        previous -= 1
    return {}


def ranking_for(
    name: BaselineName,
    corpus: SeasonCorpus,
    gameweek: int,
    *,
    settings: BaselineSettings | None = None,
) -> Mapping[int, float]:
    config = settings or BaselineSettings()
    if name == "hold":
        return hold_ranking(corpus, gameweek)
    if name == "form_chaser":
        return form_ranking(corpus, gameweek, window=config.form_window)
    if name == "crowd":
        return crowd_ranking(corpus, gameweek)
    raise ValueError(f"unknown baseline: {name}")
