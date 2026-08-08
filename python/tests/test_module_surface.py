"""Library modules declare `__all__`; CLI entry points do not.

It was asked for consistency. Before this, 40 modules declared `__all__`
and 27 did not, with no rule distinguishing them.

The rule chosen: anything importable as a library must state its surface, because
`from module import *` and, more importantly, the reachability audit in
`test_reachability.py` both depend on knowing what is deliberately public.
Modules under `cli/` are exempt: they are invoked, not imported, so an `__all__`
there names an audience that does not exist.
"""

from __future__ import annotations

import ast
from functools import cache
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parents[1] / "fpl_andres"


@cache
def _modules() -> tuple[tuple[str, ast.Module], ...]:
    return tuple(
        (path.relative_to(_PACKAGE).as_posix(), ast.parse(path.read_text(encoding="utf-8")))
        for path in sorted(_PACKAGE.rglob("*.py"))
        if path.name != "__init__.py"
    )


def _all_names(tree: ast.Module) -> list[str] | None:
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
            )
            and isinstance(node.value, ast.List)
        ):
            return [
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
    return None


def _public_definitions(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and not node.name.startswith("_")
    }


def test_every_library_module_declares_its_surface() -> None:
    missing = sorted(
        relative
        for relative, tree in _modules()
        if not relative.startswith("cli/")
        and _all_names(tree) is None
        and _public_definitions(tree)
    )
    assert missing == [], (
        "these library modules export public names without declaring __all__: " + ", ".join(missing)
    )


def test_all_entries_name_something_that_exists() -> None:
    """An `__all__` entry that names nothing breaks `import *` at runtime and is
    invisible to mypy, so it survives indefinitely."""
    broken: dict[str, list[str]] = {}
    for relative, tree in _modules():
        declared = _all_names(tree)
        if declared is None:
            continue
        defined = _public_definitions(tree) | {
            target.id
            for node in tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        defined |= {
            node.target.id
            for node in tree.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        defined |= {
            alias.asname or alias.name.split(".")[0]
            for node in tree.body
            if isinstance(node, ast.Import | ast.ImportFrom)
            for alias in node.names
        }
        absent = sorted(name for name in declared if name not in defined)
        if absent:
            broken[relative] = absent
    assert broken == {}, f"__all__ names that are not defined in the module: {broken}"


def test_no_all_entry_is_private() -> None:
    offenders = {
        relative: [name for name in declared if name.startswith("_")]
        for relative, tree in _modules()
        if (declared := _all_names(tree)) is not None
        and any(name.startswith("_") for name in declared)
    }
    assert offenders == {}, f"__all__ must not export underscore-prefixed names: {offenders}"


def test_cli_modules_stay_out_of_the_rule() -> None:
    """Records the exemption rather than leaving it implied by absence."""
    cli = [relative for relative, _ in _modules() if relative.startswith("cli/")]
    assert len(cli) > 5, "the exemption should still be covering real modules"
