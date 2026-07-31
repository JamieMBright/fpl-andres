"""Reachability audit.

Every public function should be called by something other than its own tests.
Anything that is not is either dead or, worse, a capability the product believes
it has and does not use.

This has already happened twice in this repository. ``HighsHorizonOptimizer``
plans across gameweeks with proper free-transfer accounting and was reachable
only from its own test file while a weaker greedy planner ran in its place. A
chip stopping rule was written, tested, and never called from the decision that
was supposed to use it.

Run as a test so the answer cannot drift.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "fpl_andres"
TESTS = Path(__file__).resolve().parents[1] / "tests"

# Reachable from a command line, a workflow, or the public API rather than from
# another module. Each needs a reason, so the list cannot quietly grow.
ENTRY_POINTS = {
    "main": "CLI entry point",
    "build_parser": "CLI argument parsing",
    "season_from": "CLI, derives the season label",
    "summarise": "operator-facing corpus description",
    "load_season": "used by every CLI and script",
    "validate_published_bootstrap_contract": "live contract workflow",
    "normalize_entry": "adapter surface",
    "read_league": "mini-league surface, not yet on a page",
    "differentials": "mini-league surface, not yet on a page",
    "persist_backtest": "backtest persistence, called by scripts",
    "current_revision": "backtest persistence",
    "plan_transfers": "planning surface, not yet on a page",
    "premium_is_justified": "planning surface, not yet on a page",
    "effective_points": "planning surface, not yet on a page",
    "effective_ownership": "planning surface, not yet on a page",
    "mandatory_players": "planning surface, not yet on a page",
    "swing": "planning surface, not yet on a page",
    "project_horizon": "planning surface, not yet on a page",
    "describe_shape": "carried on every horizon projection",
    "evaluate_gameweek": "regret scoring, called by scripts",
    "ranking_for": "baseline lookup by name",
    "hold_ranking": "baseline, selected by name",
    "form_ranking": "baseline, selected by name",
    "selling_price": "valuation rule, used through Portfolio",
    "build_squad": "fallback squad construction",
    "validate_squad": "squad rule enforcement",
    "parse_history": "cohort verification",
    "extract_entry_ids": "cohort verification",
    "qualifies": "cohort verification",
    "rank_cohort": "cohort verification",
    "open_run": "workflow run logging",
    "plan_chips": "chip planning, called by the league",
    "estimate_strength": "team strength, called by the projector",
    "route_adjustment": "fixture adjustment, called by the projector",
}

# Reached from TypeScript, a workflow, or nothing at all. Each entry is a
# finding, not an excuse: the list is a ratchet, so it may shrink but a new
# orphan fails the build. Recorded in LIMITATIONS.md.
KNOWN_ORPHANS = {
    "project_expected_points": "promoted xPTS model; the projector prices scoring itself",
    "run_backtest": "original harness, superseded by backtesting/score.py",
    "classify_deployment": "out-of-position classifier; no live data source",
    "evaluate_promotion": "promotion gate; nothing promotes a model yet",
    "iter_walk_forward_slices": "leak guard; the corpus enforces the cutoff instead",
    "simulate_season": "single-manager season sim, superseded by the mini-league",
    "optimization_state_evidence_from_team_state": "MILP builder; optimiser unwired",
    "optimization_rules_from_snapshot": "MILP builder; optimiser unwired",
    "normalize_public_team_state": "consumed by the TypeScript API, not by Python",
    "resolve_team_state": "consumed by the TypeScript API, not by Python",
    "parse_source_snapshot": "contract helper used across the boundary",
    "parse_gameweek_csv": "vaastav adapter, called through the ingest CLI",
    "parse_lineup_role_observations": "StatsBomb adapter; no ingest path exists",
    "hash_statsbomb_bytes": "StatsBomb adapter; no ingest path exists",
    "require_gameweeks": "corpus guard, used by scripts",
    "bench_value": "chip valuation, orphaned when timing moved to the fixture plan",
    "triple_captain_value": "chip valuation, orphaned when timing moved to fixtures",
}

KNOWN_ORPHAN_MODULES = {
    "dixon_coles": "team goals model; the projector uses its own strength estimate",
    "expected_points": "promoted xPTS model, not called by the backtest",
    "metrics": "scoring helpers, superseded",
    "promotion": "promotion gate, nothing promotes yet",
    "statsbomb": "adapter with no ingest path",
    "team_state": "consumed by the TypeScript API",
    "walk_forward": "leak-guard slicing, superseded by the corpus cutoff",
}


def _module_files() -> list[Path]:
    return sorted(path for path in PACKAGE.rglob("*.py") if "__pycache__" not in str(path))


def _defined_functions() -> dict[str, Path]:
    defined: dict[str, Path] = {}
    for path in _module_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if node.name.startswith("_"):
                    continue
                defined[node.name] = path
    return defined


def _called_names(paths: list[Path]) -> set[str]:
    called: set[str] = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    called.add(func.id)
                elif isinstance(func, ast.Attribute):
                    called.add(func.attr)
            elif isinstance(node, ast.Attribute):
                called.add(node.attr)
    return called


def test_every_public_function_is_reachable_from_the_package() -> None:
    """No function may be reachable only from its own tests."""
    defined = _defined_functions()
    called = _called_names(_module_files())

    orphans = {
        name: path.relative_to(PACKAGE).as_posix()
        for name, path in defined.items()
        if name not in called and name not in ENTRY_POINTS and name not in KNOWN_ORPHANS
    }

    assert orphans == {}, (
        "these are called by nothing inside the package. Wire them up, delete "
        f"them, or record them in KNOWN_ORPHANS with a reason: {orphans}"
    )


def test_the_orphan_list_only_ever_shrinks() -> None:
    """A recorded orphan that is now wired up must leave the list."""
    defined = _defined_functions()
    called = _called_names(_module_files())
    resolved = sorted(name for name in KNOWN_ORPHANS if name in called or name not in defined)

    assert resolved == [], (
        f"these are no longer orphaned, or no longer exist. Remove them from "
        f"KNOWN_ORPHANS: {resolved}"
    )


def test_every_named_entry_point_still_exists() -> None:
    """A stale exemption hides the next orphan."""
    defined = _defined_functions()
    stale = sorted(name for name in ENTRY_POINTS if name not in defined)

    assert stale == [], f"ENTRY_POINTS names functions that no longer exist: {stale}"


def test_no_module_is_imported_only_by_its_own_tests() -> None:
    """A module nothing imports is a capability the product does not have."""
    imported: set[str] = set()
    for path in _module_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.rsplit(".", 1)[-1])
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.rsplit(".", 1)[-1])

    # Modules that are legitimately reached only from outside the package.
    external = {
        "__init__",
        "capture_crowd",
        "crosswalk",
        "ingest_historical",
        "live_contracts",
        "publish_opening_squad",
        "publish_projections",
        "validate",
        "verify_veterans",
        "regret",
        "rivals",
        "backtest",
        "effective",
        "horizon",
        "highs",
    }
    modules = {path.stem for path in _module_files()}
    orphans = sorted(modules - imported - external - set(KNOWN_ORPHAN_MODULES))

    assert orphans == [], f"nothing imports these modules: {orphans}"


def test_every_scoring_route_reaches_the_projection() -> None:
    """Columns fetched and then discarded are a silent modelling gap.

    goals_conceded and defensive_contribution were selected from the database
    and dropped on the floor for weeks, which cost roughly eight percent of the
    game's points.
    """
    projector = (PACKAGE / "backtesting" / "projector.py").read_text(encoding="utf-8")
    routes = (
        "goals_conceded",
        "defensive_contribution",
        "yellow_cards",
        "red_cards",
        "own_goals",
        "penalties_saved",
        "penalties_missed",
        "clean_sheets",
        "saves",
        "bonus",
    )
    missing = [route for route in routes if route not in projector]

    assert missing == [], f"these scoring routes are never priced: {missing}"


def test_corpus_columns_are_all_consumed() -> None:
    """Every column the corpus selects is read by something."""
    corpus = (PACKAGE / "backtesting" / "corpus.py").read_text(encoding="utf-8")
    tree = ast.parse(corpus)
    fields: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ElementRow":
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                    fields.add(statement.target.id)

    consumers = "\n".join(
        path.read_text(encoding="utf-8") for path in _module_files() if path.name != "corpus.py"
    )
    # fixture_id identifies the row within a double gameweek. Nothing models it
    # directly, but dropping it would make two rows indistinguishable.
    identity = {"fixture_id"}
    unused = sorted(name for name in fields if f".{name}" not in consumers)
    unused = [name for name in unused if name not in identity]

    assert unused == [], f"ElementRow carries columns nothing reads: {unused}"
