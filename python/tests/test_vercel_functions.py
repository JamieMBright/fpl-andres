"""Every `functions` key in `vercel.json` must match a real function.

Written after a production incident, not before one.

Audit item #86 asked for per-route duration budgets. The implementation replaced
a working `api/**/*.ts` glob with three literal paths:

    "api/health.ts"
    "api/fpl/[...path].ts"
    "api/team/[id].ts"

Vercel resolves those keys as **globs**, and in a glob `[id]` is a character
class matching one of `i` or `d`, while `[...path]` matches one of `.path`.
Neither matches the file it was named after. `api/health.ts` has no brackets,
matched fine, and kept working -- which is exactly why the mistake was invisible:
the one route with a bracket-free name was the one that stayed up.

Production returned 404 on `/api/fpl/*` and 500 on `/api/team/*` while
`/api/health` answered normally, for six days, with every test passing. The
tests mock the upstream and never load `vercel.json`.

The general rule this encodes: a configuration key that silently matches nothing
is worse than one that errors, so anything glob-shaped gets asserted against the
filesystem.
"""

from __future__ import annotations

import json
from glob import glob
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_CONFIG = json.loads((_ROOT / "vercel.json").read_text(encoding="utf-8"))


def _handlers() -> set[str]:
    """Every deployable function: a .ts file under api/ outside _lib."""
    return {
        path.relative_to(_ROOT).as_posix()
        for path in (_ROOT / "api").rglob("*.ts")
        if "_lib" not in path.parts
    }


def test_there_are_handlers_to_check() -> None:
    assert len(_handlers()) >= 3


@pytest.mark.parametrize("pattern", sorted(_CONFIG.get("functions", {})))
def test_every_functions_key_matches_at_least_one_handler(pattern: str) -> None:
    matched = glob(pattern, root_dir=_ROOT)
    assert matched, (
        f"vercel.json functions key {pattern!r} matches no file. Vercel reads "
        "these as globs, so a Next-style [param] name is a character class and "
        "matches nothing."
    )


def test_every_handler_is_covered_by_a_budget() -> None:
    """An uncovered handler silently takes the platform default, which is not
    the budget anyone reasoned about."""
    covered: set[str] = set()
    for pattern in _CONFIG.get("functions", {}):
        covered.update(Path(match).as_posix() for match in glob(pattern, root_dir=_ROOT))
    uncovered = sorted(_handlers() - covered)
    assert uncovered == [], f"no maxDuration configured for: {uncovered}"


def test_no_functions_key_uses_a_bracket_parameter_name() -> None:
    """The specific mistake, named so it cannot come back by a different route."""
    bracketed = [key for key in _CONFIG.get("functions", {}) if "[" in key]
    assert bracketed == [], (
        "these keys contain glob character classes and will match nothing: "
        f"{bracketed}. Use api/<dir>/*.ts instead."
    )


def test_the_rewrite_does_not_swallow_the_api() -> None:
    """The other way every route could 404 at once."""
    sources = [rule["source"] for rule in _CONFIG.get("rewrites", [])]
    assert sources, "expected a SPA rewrite"
    for source in sources:
        assert "?!api/" in source, (
            f"rewrite {source!r} does not exclude /api/, so it would serve "
            "index.html for every endpoint"
        )


def test_the_budgets_reflect_what_each_route_does() -> None:
    """The team route fans out to three upstream calls including the 1.3 MB
    bootstrap; health does no I/O at all."""
    budgets = {
        pattern: config["maxDuration"] for pattern, config in _CONFIG.get("functions", {}).items()
    }
    assert budgets["api/health.ts"] < budgets["api/team/*.ts"]
    assert budgets["api/team/*.ts"] >= 15
