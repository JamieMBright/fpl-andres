"""Map one season of FPL players onto a scraped source, and report the gaps.

Writes only the matches that survived corroboration. The report on stdout is the
point of the job: a coverage figure nobody has to take on trust, and a named
list of everyone who did not map.

Requires the optional scrape extra:
    python -m pip install -e ".[scrape]"

Usage:
    python -m fpl_andres.cli.crosswalk --season 2025-26
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpl_andres.backtesting.corpus import SeasonCorpus, load_season
from fpl_andres.crosswalk import (
    ForeignPlayer,
    FplPlayer,
    MatchOutcome,
    resolve_crosswalk,
)
from fpl_andres.models.penalties import PenaltyExposure, penalty_exposure
from fpl_andres.persistence.supabase import SupabaseCredentials, SupabaseRestClient

DEFAULT_OUTPUT = Path("data/crosswalk")
# Cached scrapes live beside the repository, never inside it, and are gitignored.
CACHE_DIR = Path("data/soccerdata")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crosswalk")
    parser.add_argument("--season", default="2025-26")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def _understat_season(season: str) -> str:
    """2025-26 becomes 2526, which is how soccerdata names a season."""
    start, end = season.split("-")
    return f"{start[2:]}{end}"


def _fpl_players(corpus: SeasonCorpus) -> list[FplPlayer]:
    totals: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0])
    for gameweek in corpus.rows_by_gameweek.values():
        for row in gameweek:
            entry = totals[row.element_id]
            entry[0] += row.minutes
            entry[1] += row.goals
            entry[2] += row.assists

    players: list[FplPlayer] = []
    for element_id, code in corpus.code_by_element.items():
        club = corpus.name_by_team.get(corpus.team_by_element.get(element_id, 0))
        if club is None:
            continue
        minutes, goals, assists = totals[element_id]
        full_name = corpus.full_name_by_element.get(element_id, "")
        first, _, second = full_name.partition(" ")
        players.append(
            FplPlayer(
                code=code,
                season=corpus.season,
                club=club,
                first_name=first,
                second_name=second,
                web_name=corpus.name_by_element.get(element_id, ""),
                minutes=minutes,
                goals=goals,
                assists=assists,
            )
        )
    return players


def _understat_frame(season: str) -> Any:
    """soccerdata is an optional extra, so its DataFrame is not typed here."""
    os.environ.setdefault("SOCCERDATA_DIR", str(CACHE_DIR.resolve()))
    try:
        import soccerdata
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise SystemExit(
            'soccerdata is not installed. Run: python -m pip install -e ".[scrape]"'
        ) from error

    return soccerdata.Understat(
        leagues="ENG-Premier League", seasons=_understat_season(season)
    ).read_player_season_stats()


def _understat_players(season: str) -> list[ForeignPlayer]:
    frame = _understat_frame(season)
    return [
        ForeignPlayer(
            source="understat",
            source_id=str(row.player_id),
            season=season,
            club=str(row.team),
            name=str(row.player),
            minutes=int(row.minutes),
            goals=int(row.goals),
            assists=int(row.assists),
        )
        for row in frame.reset_index().itertuples()
    ]


def _penalty_exposures(season: str) -> dict[str, PenaltyExposure]:
    """Keyed by Understat id, so the crosswalk match can carry it to an FPL code."""
    exposures: dict[str, PenaltyExposure] = {}
    for row in _understat_frame(season).reset_index().itertuples():
        exposures[str(row.player_id)] = penalty_exposure(
            expected_goals=float(row.xg),
            non_penalty_expected_goals=float(row.np_xg),
            goals=int(row.goals),
            non_penalty_goals=int(row.np_goals),
            minutes=int(row.minutes),
        )
    return exposures


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    credentials = SupabaseCredentials.from_env(os.environ)
    with SupabaseRestClient(credentials) as client:
        corpus = load_season(client, args.season)

    report = resolve_crosswalk(
        _fpl_players(corpus), _understat_players(args.season), source="understat"
    )

    print(f"{args.season} against {report.source}")
    for outcome in MatchOutcome:
        print(f"  {outcome.value:<22}{report.counts[outcome]:>5}")
    print(f"  coverage{report.coverage():>21.1%}")

    for outcome in (MatchOutcome.CONTRADICTED, MatchOutcome.AMBIGUOUS):
        refused = report.by_outcome(outcome)
        if refused:
            names = ", ".join(match.web_name for match in refused)
            print(f"\n  refused as {outcome.value}: {names}")

    exposures = _penalty_exposures(args.season)
    matched_exposure = {
        match.code: exposures[match.source_id]
        for match in report.verified
        if match.source_id in exposures
    }
    ranked = sorted(
        (
            (match.web_name, matched_exposure[match.code])
            for match in report.verified
            if match.code in matched_exposure
            and matched_exposure[match.code].penalty_expected_goals > 0
        ),
        # By absolute penalty xG, not share: a share is a ratio on whatever
        # denominator a player happens to have, so one penalty on a total of
        # 0.98 xG reads as 78% dependent and tells nobody anything.
        key=lambda pair: -pair[1].penalty_expected_goals,
    )
    if ranked:
        print("\n  most penalty-dependent (by penalty xG, share alongside):")
        for name, exposure in ranked[:10]:
            print(
                f"    {name[:22]:22s} {exposure.penalty_expected_goals:5.2f} penalty xG "
                f"of {exposure.expected_goals:5.2f} ({exposure.share:5.1%}), "
                f"{exposure.penalties_scored} scored"
            )

    output = Path(args.output) / f"understat-{args.season}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "generatedAt": datetime.now(UTC).isoformat(),
                "season": args.season,
                "source": report.source,
                "coverage": round(report.coverage(), 4),
                "counts": {outcome.value: report.counts[outcome] for outcome in MatchOutcome},
                "matched": {str(match.code): match.source_id for match in report.verified},
                "penaltyExposure": {
                    str(code): {
                        "expectedGoals": round(exposure.expected_goals, 4),
                        "nonPenaltyExpectedGoals": round(exposure.non_penalty_expected_goals, 4),
                        "penaltyExpectedGoals": round(exposure.penalty_expected_goals, 4),
                        "share": round(exposure.share, 4),
                        "penaltiesScored": exposure.penalties_scored,
                        "expectedGoalsAtRiskPer90": round(
                            exposure.expected_goals_at_risk_per_90(), 4
                        ),
                    }
                    for code, exposure in sorted(matched_exposure.items())
                },
                "unmatched": [
                    {"code": match.code, "name": match.web_name, "why": match.outcome.value}
                    for match in report.matches
                    if not match.matched and match.outcome is not MatchOutcome.TOO_LITTLE_FOOTBALL
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
