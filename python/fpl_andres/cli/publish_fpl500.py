"""Publish FPL500: the five hundred managers worth following.

Reads the swept catalogue and ranks it on sustained elite finishing, measured in
percentile so seasons from different-sized fields are comparable, weighted
toward the game as it is currently scored.

The output is tracked in git. FPL500 is the input to the cohort portfolio, and a
derived ranking whose source is not in the repository cannot be reproduced or
argued with.

Usage:
    python -m fpl_andres.cli.publish_fpl500
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from fpl_andres import cliargs
from fpl_andres.artifacts import FPL500_SCHEMA_VERSION
from fpl_andres.cohorts.absence import DEFAULT_TOLERANCE, departed
from fpl_andres.cohorts.elite import (
    DEFAULT_SETTINGS,
    EliteScore,
    EliteSettings,
    ManagerSeason,
    SweptManager,
    entries_by_season,
    rank_elite,
    season_start_year,
)
from fpl_andres.cohorts.portfolio import MINIMUM_COVERAGE
from fpl_andres.jsonio import parse_json
from fpl_andres.positions import Position

COHORT_DIR = Path("data/cohort")
MANAGERS = COHORT_DIR / "managers.jsonl"
CHECKPOINT = COHORT_DIR / "sweep-checkpoint.json"
#: Where `capture_cohort_picks` writes a gameweek's squads. Empty until the
#: season starts: the fund cannot hold anything before anybody has picked.
PORTFOLIO_DIR = COHORT_DIR / "portfolio"
FPL500_PORTFOLIO_DIR = PORTFOLIO_DIR / "fpl500"
#: This season's Overall standings, written by `harvest_league`.
STANDINGS = COHORT_DIR / "fpl100.json"
#: Who has stopped answering, counted by `capture_cohort_picks`.
ABSENT = COHORT_DIR / "absent.json"
DEFAULT_OUTPUT = COHORT_DIR / "fpl500.json"
DEFAULT_WEB_OUTPUT = Path("apps/web/src/data/fpl500.json")
FPL_GLOBAL = Path("apps/web/public/fpl-global.json")
SCHEMA_VERSION = FPL500_SCHEMA_VERSION

#: How many of the ranking the site lists by name. None of it. Who clears the
#: bar is the one thing in this repository somebody could copy outright, and a
#: page can say everything useful about the cohort as a distribution. The
#: current season's Overall standings below are a different list and are public
#: on FPL's own site, so those are named.
WEB_LISTED = 0

#: How many of this season's standings the page carries. Enough to page
#: through in a bounded box, not so many that the chunk is mostly entry ids.
CURRENT_SEASON_LISTED = 100

#: Where the score distribution is sampled, so a reader can see the curve
#: without shipping five hundred points to draw it with.
WEB_QUANTILES = (1, 10, 25, 50, 100, 200, 300, 400, 500)

#: FPL's live entry count, read from the register rather than assumed: the
#: sweep's own estimate of the largest rank in the season just finished.
LATEST_SEASON_KEY = "latestSeasonEntries"

#: Top captains to include per gameweek in the web artifact. Keeps the file
#: small: the long tail below a percent is noise, not a strategy.
WEB_TOP_CAPTAINS = 5
WEB_CAPTAIN_MIN_SHARE = 0.01


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publish-fpl500")
    parser.add_argument("--managers", default=str(MANAGERS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--web-output",
        default=str(DEFAULT_WEB_OUTPUT),
        help=(
            "The trimmed copy the site reads. Written beside the full ranking "
            "so the two can never describe different sweeps."
        ),
    )
    parser.add_argument("--top", type=cliargs.positive_int, default=500)
    parser.add_argument("--decay", type=cliargs.positive_float, default=None)
    parser.add_argument("--minimum-seasons", type=cliargs.positive_int, default=None)
    parser.add_argument("--absent", default=str(ABSENT))
    parser.add_argument(
        "--absence-tolerance",
        type=cliargs.positive_int,
        default=DEFAULT_TOLERANCE,
        help=(
            "Consecutive deadlines a manager may miss before the ranking gives "
            "his place to the next one down."
        ),
    )
    return parser


def read_catalogue(path: Path) -> list[SweptManager]:
    """Every manager in the catalogue, once.

    The sweep appends and checkpoints a block at a time, so a run killed
    between the two re-sweeps that block on resume and writes its managers
    again. A repeated row would otherwise be ranked twice and take two of the
    five hundred places, leaving a cohort that reports 500 and holds fewer.
    The first copy wins: the rows are identical, and sweep order is what the
    ranking's tie-breaks already see.
    """
    managers: list[SweptManager] = []
    seen: set[int] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = parse_json(line, source=f"{path}:{number}")
        entry_id = int(row["entryId"])
        if entry_id in seen:
            continue
        seen.add(entry_id)
        managers.append(
            SweptManager(
                entry_id=entry_id,
                seasons=tuple(
                    ManagerSeason(
                        season=str(season["season"]),
                        points=int(season["points"]),
                        rank=int(season["rank"]),
                    )
                    for season in row["seasons"]
                    if season.get("rank")
                ),
            )
        )
    return managers


def _gone(path: Path, tolerance: int) -> frozenset[int]:
    """Entries the capture job has stopped being able to reach.

    A deleted account answers a request for its picks with a 404 forever and
    says nothing else, so the only way to know is to have asked several times.
    Dropped from the catalogue before the ranking is cut rather than blanked
    afterwards, so the five hundredth place goes to somebody who is still
    playing instead of being left empty.
    """
    if not path.exists():
        return frozenset()
    saved = parse_json(path.read_text(encoding="utf-8"), source=str(path))
    misses = saved.get("consecutiveMisses", {})
    if not isinstance(misses, dict):
        return frozenset()
    return departed({int(entry): int(count) for entry, count in misses.items()}, tolerance)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.managers)
    if not path.exists():
        raise SystemExit(
            f"{path} does not exist. Run sweep_managers first; FPL500 is derived "
            f"from the catalogue, not discovered independently."
        )

    catalogued = read_catalogue(path)
    gone = _gone(Path(args.absent), args.absence_tolerance)
    managers = [row for row in catalogued if row.entry_id not in gone]
    settings = EliteSettings(
        decay_per_season=args.decay or DEFAULT_SETTINGS.decay_per_season,
        minimum_seasons=args.minimum_seasons or DEFAULT_SETTINGS.minimum_seasons,
    )
    field = entries_by_season(managers)
    ranked = rank_elite(managers, entries=field, settings=settings, top=args.top)

    swept_to = None
    if CHECKPOINT.exists():
        swept_to = parse_json(CHECKPOINT.read_text(encoding="utf-8"), source=str(CHECKPOINT)).get(
            "next_id"
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schemaVersion": SCHEMA_VERSION,
                "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "catalogueSize": len(managers),
                "sweptTo": swept_to,
                "size": len(ranked),
                "settings": {
                    "decayPerSeason": settings.decay_per_season,
                    "preRulesChangeWeight": settings.pre_rules_change_weight,
                    "rulesChangedIn": settings.rules_changed_in,
                    "shrinkageWeight": settings.shrinkage_weight,
                    "priorPercentile": settings.prior_percentile,
                    "minimumSeasons": settings.minimum_seasons,
                },
                # Published because the percentiles are only as good as this,
                # and it is the largest rank observed rather than a true count.
                "estimatedEntriesBySeason": dict(sorted(field.items())),
                "managers": [
                    {
                        "entryId": row.entry_id,
                        "score": round(row.score, 6),
                        "seasons": row.seasons_counted,
                        "weight": round(row.total_weight, 4),
                        "bestPercentile": round(row.best_percentile, 6),
                        "latestPercentile": (
                            None
                            if row.latest_percentile is None
                            else round(row.latest_percentile, 6)
                        ),
                        "latestSeason": row.latest_season,
                    }
                    for row in ranked
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"wrote {output} — {len(ranked)} of {len(managers)} managers")
    if gone:
        print(
            f"  {len(gone)} dropped for missing {args.absence_tolerance} "
            "consecutive deadlines; their places went to the next ranked"
        )
    if ranked:
        print(f"  top score {ranked[0].score:.4f}, cut-off {ranked[-1].score:.4f}")
        print(
            f"  seasons held by the top 500: {min(r.seasons_counted for r in ranked)}"
            f"-{max(r.seasons_counted for r in ranked)}"
        )

    web = Path(args.web_output)
    web.parent.mkdir(parents=True, exist_ok=True)
    web.write_text(
        json.dumps(_web_payload(ranked, managers, field, settings, swept_to), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {web} — {min(WEB_LISTED, len(ranked))} listed, {len(ranked)} counted")
    return 0


#: Where the rank histogram cuts. Log-spaced because the interesting structure
#: is all at the top: the gap between 1,000th and 10,000th matters far more
#: than the gap between a million and two.
RANK_BINS: tuple[int, ...] = (100, 1_000, 5_000, 10_000, 50_000, 100_000, 500_000)

#: How many seasons of the distribution to draw. Five is a chart that reads.
DISTRIBUTION_SEASONS = 5


def _rank_histogram(
    ranked: Sequence[EliteScore],
    managers: Sequence[SweptManager],
    seasons: int,
) -> dict[str, list[int]]:
    """Where the ranked five hundred actually finished, season by season.

    A distribution rather than a list, because who is in FPL500 is the one
    thing this repository has that somebody could simply copy. Counts per bin
    say everything a reader needs about how the cohort performs and name
    nobody.
    """
    members = {row.entry_id for row in ranked}
    finishes: dict[str, list[int]] = {}
    for manager in managers:
        if manager.entry_id not in members:
            continue
        for season in manager.seasons:
            finishes.setdefault(season.season, []).append(season.rank)

    recent = sorted(finishes, key=season_start_year)[-seasons:]
    histogram: dict[str, list[int]] = {}
    for season_name in recent:
        counts = [0] * (len(RANK_BINS) + 1)
        for rank in finishes[season_name]:
            slot = next(
                (index for index, edge in enumerate(RANK_BINS) if rank <= edge),
                len(RANK_BINS),
            )
            counts[slot] += 1
        histogram[season_name] = counts
    return histogram


def _web_payload(
    ranked: Sequence[EliteScore],
    managers: Sequence[SweptManager],
    field: Mapping[str, int],
    settings: EliteSettings,
    swept_to: object,
) -> dict[str, object]:
    """What the site needs, without the hundred kilobytes it does not.

    The ranking is a hundred and five kilobytes of entry ids. A page that lists
    all of them is a page nobody reads to the end, and the browser pays for it
    on every visit. So the head is listed by name, the curve is sampled at
    fixed depths, and the totals that let a reader check both are carried in
    full.
    """
    latest = max(field, key=lambda season: season_start_year(season)) if field else None
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "catalogueSize": len(managers),
        "sweptTo": swept_to,
        "size": len(ranked),
        "listed": min(WEB_LISTED, len(ranked)),
        "settings": {
            "decayPerSeason": settings.decay_per_season,
            "preRulesChangeWeight": settings.pre_rules_change_weight,
            "rulesChangedIn": settings.rules_changed_in,
            "shrinkageWeight": settings.shrinkage_weight,
            "priorPercentile": settings.prior_percentile,
            "minimumSeasons": settings.minimum_seasons,
        },
        "latestSeason": latest,
        LATEST_SEASON_KEY: field.get(latest) if latest else None,
        "estimatedEntriesBySeason": dict(sorted(field.items())),
        # The reconciler's own floor, so the page describing the fund quotes
        # the number that will refuse a snapshot rather than one typed beside it.
        "minimumCoverage": MINIMUM_COVERAGE,
        # Distinct series. The original capture asked the whole 2,786-manager
        # catalogue; it must never be relabelled as the ranked five hundred.
        "cataloguePortfolio": _portfolio_series(
            PORTFOLIO_DIR,
            basis="catalogue-at-deadline",
            label="Catalogue at deadline",
        ),
        "exactFpl500Portfolio": _portfolio_series(
            FPL500_PORTFOLIO_DIR,
            basis="ranked-500",
            label="Exact FPL500",
        ),
        # The score at fixed depths, so the shape of the cut is visible without
        # shipping five hundred points to draw it from.
        "scoreAtRank": {
            str(depth): round(ranked[depth - 1].score, 6)
            for depth in WEB_QUANTILES
            if depth <= len(ranked)
        },
        "seasonsCounted": _histogram(row.seasons_counted for row in ranked),
        "rankBins": list(RANK_BINS),
        "rankHistogram": _rank_histogram(ranked, managers, DISTRIBUTION_SEASONS),
        # This season's Overall standings, which are public and are not the
        # same list. Who is in FPL500 is the one thing here somebody could
        # simply copy, so it is published as a distribution and never as names.
        "thisSeason": _this_season(),
    }


def _this_season() -> dict[str, object]:
    """The current Overall standings, straight off the league.

    Empty before a ball is kicked, which is the honest answer rather than a
    fault: the Overall league exists all summer and nobody has a rank in it.
    """
    if not STANDINGS.exists():
        return {"size": 0, "managers": []}
    saved = parse_json(STANDINGS.read_text(encoding="utf-8"), source=str(STANDINGS))
    assert isinstance(saved, dict)
    rows = saved.get("managers")
    if not isinstance(rows, list):
        return {"size": 0, "managers": []}
    return {
        "generatedAt": saved.get("generatedAt"),
        "rankCeiling": saved.get("rankCeiling"),
        "size": len(rows),
        "managers": rows[:CURRENT_SEASON_LISTED],
    }


def _realised_points(directory: Path, stem: str) -> dict[int, int]:
    """What each element scored in a finished round, or nothing.

    `annotate_portfolio` writes this sidecar only once every fixture in the
    round carries a confirmed score, so its presence is what distinguishes a
    round that is over from one still being played. Absent is the normal state
    for the current gameweek and is not an error.
    """
    path = directory / f"gw{stem}-points.json"
    if not path.exists():
        return {}
    try:
        raw = parse_json(path.read_text(encoding="utf-8"), source=str(path))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    points = raw.get("elementPoints")
    if not isinstance(points, dict):
        return {}
    return {int(element): int(score) for element, score in points.items()}


def _portfolio_captains(directory: Path | None = None) -> dict[str, list[dict[str, float]]]:
    """Top captains per captured gameweek, and what each pick returned.

    Read directly from the portfolio files so the site can render real data as
    soon as a deadline has passed, without a separate fetch. Only captains above
    `WEB_CAPTAIN_MIN_SHARE` are included; the rest are noise.

    `points` is present only for a round FPL has finished scoring. It is left
    off entirely rather than set to zero, because a captain who blanked and a
    captain whose match has not kicked off are different facts and a zero would
    say the first about both.

    Keyed by event number as a string so JSON serialises it naturally.
    """
    portfolio_dir = PORTFOLIO_DIR if directory is None else directory
    result: dict[str, list[dict[str, float]]] = {}
    for path in sorted(portfolio_dir.glob("gw*.json")):
        stem = path.stem.removeprefix("gw")
        if not stem.isdigit():
            continue
        try:
            raw = parse_json(path.read_text(encoding="utf-8"), source=str(path))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        holdings = raw.get("holdings", [])
        if not isinstance(holdings, list):
            continue
        scored = _realised_points(portfolio_dir, stem)
        captains: list[dict[str, float]] = []
        for holding in holdings:
            if not isinstance(holding, dict):
                continue
            if float(holding.get("captainedShare", 0)) < WEB_CAPTAIN_MIN_SHARE:
                continue
            element_id = int(holding["elementId"])
            entry: dict[str, float] = {
                "elementId": element_id,
                "share": round(float(holding["captainedShare"]), 5),
            }
            if element_id in scored:
                entry["points"] = scored[element_id]
            captains.append(entry)
        captains.sort(key=lambda row: -row["share"])
        result[stem] = captains[:WEB_TOP_CAPTAINS]
    return result


def _portfolio_series(
    directory: Path,
    *,
    basis: str,
    label: str,
) -> dict[str, object]:
    """One explicitly based portfolio series, never merged with another."""
    events: list[int] = []
    samples: dict[str, dict[str, object]] = {}
    holdings_by_event: dict[str, list[dict[str, object]]] = {}
    cumulative_points: dict[int, int] = {}
    player_metadata = _player_metadata()
    for path in sorted(directory.glob("gw*.json")):
        stem = path.stem.removeprefix("gw")
        if not stem.isdigit():
            continue
        raw = parse_json(path.read_text(encoding="utf-8"), source=str(path))
        if not isinstance(raw, dict):
            raise ValueError(f"portfolio capture must be an object: {path}")
        saved_basis = raw.get("basis", "catalogue-at-deadline")
        if saved_basis != basis:
            raise ValueError(f"portfolio basis {saved_basis!r} in {path}; expected {basis!r}")
        event = int(stem)
        events.append(event)
        sample: dict[str, object] = {
            "capturedAt": raw.get("capturedAt"),
            "attempted": int(raw.get("attempted", 0)),
            "responded": int(raw.get("responded", 0)),
            "counted": int(raw.get("counted", 0)),
            "coverage": float(raw.get("coverage", 0.0)),
        }
        membership = raw.get("membership")
        if basis == "ranked-500":
            if not isinstance(membership, dict):
                raise ValueError(f"ranked-500 portfolio lacks membership provenance: {path}")
            sample.update(
                {
                    "membershipLabel": membership.get("label"),
                    "membershipSourceTiming": membership.get("sourceTiming"),
                    "membershipSourceGeneratedAt": membership.get("sourceGeneratedAt"),
                    "membershipSecondsFromDeadline": membership.get("secondsFromDeadline"),
                    "membershipSourceCommit": membership.get("sourceCommit"),
                    "membershipSize": membership.get("size"),
                }
            )
            aggregate_path = directory / f"gw{stem}-aggregates.json"
            if aggregate_path.exists():
                aggregate = parse_json(
                    aggregate_path.read_text(encoding="utf-8"),
                    source=str(aggregate_path),
                )
                if not isinstance(aggregate, dict):
                    raise ValueError(f"portfolio aggregate must be an object: {aggregate_path}")
                if aggregate.get("cohortRevision") != raw.get("cohortRevision"):
                    raise ValueError(f"portfolio aggregate revision mismatch: {aggregate_path}")
                sample["aggregate"] = aggregate
            points = _realised_points(directory, stem)
            event_holdings: list[dict[str, object]] = []
            raw_holdings = raw.get("holdings", [])
            if not isinstance(raw_holdings, list):
                raise ValueError(f"portfolio holdings must be a list: {path}")
            for holding in raw_holdings:
                if not isinstance(holding, dict):
                    continue
                element_id = int(holding["elementId"])
                latest = points.get(element_id)
                if latest is not None:
                    cumulative_points[element_id] = cumulative_points.get(element_id, 0) + latest
                owned_share = float(holding.get("ownedShare", 0.0))
                entry: dict[str, object] = {
                    "elementId": element_id,
                    "ownedShare": owned_share,
                    "startedShare": float(holding.get("startedShare", 0.0)),
                    "captainedShare": float(holding.get("captainedShare", 0.0)),
                    "effectiveOwnership": float(holding.get("effectiveOwnership", 0.0)),
                }
                entry.update(player_metadata.get(element_id, {}))
                if latest is not None:
                    entry.update(
                        {
                            "lastWeekPoints": latest,
                            "pointsSinceFirstCapture": cumulative_points[element_id],
                            "weightedContribution": round(latest * owned_share, 5),
                        }
                    )
                event_holdings.append(entry)
            holdings_by_event[stem] = event_holdings
        samples[stem] = sample
    result: dict[str, object] = {
        "basis": basis,
        "label": label,
        "events": sorted(events),
        "samples": samples,
        "captains": _portfolio_captains(directory),
    }
    if basis == "ranked-500":
        result["holdings"] = holdings_by_event
    return result


def _player_metadata() -> dict[int, dict[str, int | str]]:
    """Current official identity for every FPL element, rated or not."""
    if not FPL_GLOBAL.exists():
        return {}
    raw = parse_json(FPL_GLOBAL.read_text(encoding="utf-8"), source=str(FPL_GLOBAL))
    if not isinstance(raw, dict) or not isinstance(raw.get("bootstrap"), dict):
        return {}
    bootstrap = raw["bootstrap"]
    elements = bootstrap.get("elements")
    teams = bootstrap.get("teams")
    if not isinstance(elements, list) or not isinstance(teams, list):
        return {}
    club_by_id = {
        int(team["id"]): str(team["short_name"])
        for team in teams
        if isinstance(team, dict) and "id" in team and "short_name" in team
    }
    position_ids = {position.value for position in Position}
    return {
        int(element["id"]): {
            "code": int(element["code"]),
            "name": str(element["web_name"]),
            "position": Position(int(element["element_type"])).code,
            "club": club_by_id.get(int(element["team"]), "UNK"),
        }
        for element in elements
        if isinstance(element, dict) and int(element.get("element_type", 0)) in position_ids
    }


def _histogram(values: Iterable[int]) -> dict[str, int]:
    counts: dict[int, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return {str(key): counts[key] for key in sorted(counts)}


if __name__ == "__main__":
    raise SystemExit(main())
