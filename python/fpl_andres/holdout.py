"""Retrospective seasons included in model validation.

All four outcomes were visible while model 7.1 was developed, so none is a
holdout. Genuine prospective evidence starts with the pre-GW1 2026/27 manifest
and is frozen before its deadline rather than relabelled after the fact.
"""

from __future__ import annotations

__all__ = ["SCORED_SEASONS"]

#: Every season the backtest reports on. Expected-goals coverage is zero before
#: 2022-23, so earlier seasons describe a different model rather than a longer
#: history of this one.
SCORED_SEASONS: tuple[str, ...] = ("2022-23", "2023-24", "2024-25", "2025-26")
