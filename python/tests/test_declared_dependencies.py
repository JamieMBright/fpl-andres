"""Every third-party import is declared in ``pyproject.toml``.

An undeclared dependency is invisible locally. Development environments
accumulate packages transitively — ``pyyaml`` arrives with half a dozen common
tools — so the import resolves on the machine that wrote it and fails only on
the clean install CI performs. That is the same shape as a config key that is
never parsed: the feedback arrives from somewhere other than the change.

This caught ``pyyaml``, imported by ``test_ci_gates.py`` and declared nowhere,
which broke collection for the entire Python suite on CI while passing locally.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Import name differs from the distribution name for a handful of packages.
DISTRIBUTION_FOR_IMPORT = {
    "yaml": "pyyaml",
    "dateutil": "python-dateutil",
}

# Modules that live in this repository rather than site-packages.
FIRST_PARTY = {"fpl_andres", "tests", "conftest"}


def _declared_distributions() -> set[str]:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    specs = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        specs.extend(group)
    return {re.split(r"[<>=!~\[ ]", spec)[0].lower() for spec in specs}


def _python_files() -> list[Path]:
    return sorted((REPO_ROOT / "python").rglob("*.py")) + sorted(
        (REPO_ROOT / "scripts").rglob("*.py")
    )


def _imported_distributions() -> dict[str, set[str]]:
    # Sibling test modules import each other for shared fixtures; they are files
    # on the path, not packages to install.
    test_modules = {path.stem for path in (REPO_ROOT / "python" / "tests").glob("*.py")}
    imports: dict[str, set[str]] = {}

    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module.split(".")[0]] if node.module and node.level == 0 else []
            else:
                continue

            for name in names:
                if name in sys.stdlib_module_names:
                    continue
                if name in FIRST_PARTY or name in test_modules:
                    continue
                distribution = DISTRIBUTION_FOR_IMPORT.get(name, name)
                imports.setdefault(distribution, set()).add(
                    str(path.relative_to(REPO_ROOT)).replace("\\", "/")
                )

    return imports


def test_every_third_party_import_is_declared() -> None:
    declared = _declared_distributions()
    undeclared = {
        distribution: sorted(files)
        for distribution, files in _imported_distributions().items()
        if distribution not in declared
    }

    assert not undeclared, (
        "imported but absent from pyproject.toml, so a clean install will not "
        f"have them: {undeclared}"
    )


def test_the_scan_finds_the_dependencies_that_are_known_to_be_there() -> None:
    """Guards the scan itself: a broken walk would vacuously pass the above."""
    found = _imported_distributions()
    for expected in ("httpx", "numpy", "pydantic", "pytest", "pyyaml"):
        assert expected in found, f"{expected} is imported somewhere but the scan missed it"
