"""JSON reads that say which file or endpoint was malformed.

Audit item #55. Only `cli/sweep_managers.py` guarded `ValueError` from a JSON
parse. Everywhere else a truncated checkpoint or an HTML error page served in
place of an API response produced a raw `JSONDecodeError` traceback naming a
character offset — "Expecting value: line 1 column 1 (char 0)" — and nothing
about which of the seven parse sites had failed or what it had been reading.

The offset is the least useful part of that message. The path is the useful
part, and it was the part missing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ["MalformedJsonError", "parse_json", "read_json_file", "read_json_lines"]


class MalformedJsonError(ValueError):
    """Raised when JSON cannot be parsed, naming the source that produced it."""


def parse_json(text: str, *, source: str) -> Any:
    try:
        return json.loads(text)
    except ValueError as error:
        raise MalformedJsonError(f"{source} is not valid JSON: {error}") from error


def read_json_file(path: Path) -> Any:
    """Read and parse a JSON file, naming the path when either step fails."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise MalformedJsonError(f"{path} could not be read: {error}") from error
    return parse_json(text, source=str(path))


def read_json_lines(path: Path) -> list[Any]:
    """Parse newline-delimited JSON, naming the line that failed.

    A single bad line in a 2,000-line sweep output is otherwise found by
    bisection.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise MalformedJsonError(f"{path} could not be read: {error}") from error
    entries: list[Any] = []
    for number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        entries.append(parse_json(line, source=f"{path} line {number}"))
    return entries
