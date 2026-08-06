"""The version of the projection, and the rule for moving it.

A number on the site is only interpretable against the model that produced it.
Two runs of `validate` a month apart are not comparable unless something records
whether the code between them changed, and "look at the commit" is not an answer
when the artifact is regenerated on a schedule.

So the projection carries a version. It is bumped by hand, in the same commit as
the change, and `scripts/model-version-gate.mjs` fails the build if a file under
`MODEL_PATHS` moved without it. That is the same shape as the contracts version
gate, for the same reason: the alternative is a number that silently means
something different from the last one.

## What counts as a change

Anything that can move a projected point. The rate models, the minutes model,
the scoring tables, the fixture adjustment, the blend, and the backtest that
grades them. Not the CLI's output formatting, and not the web app.

## Semantics

`MAJOR.MINOR`. Minor for a change that moves numbers; major for one that changes
what the numbers mean — a new scoring route, a different target, a different
population. There is no patch component because a change that cannot move a
number does not need a version.
"""

from __future__ import annotations

__all__ = ["MODEL_VERSION"]

#: 2.0 is the first version under the gate. The projection it names is the one
#: measured in `apps/web/src/data/validation.json`: fourteen priced routes, a
#: minutes-first reconstruction, route-specific fixture adjustment, and an
#: 0.8/0.2 blend with the last five gameweeks.
MODEL_VERSION = "2.0"
