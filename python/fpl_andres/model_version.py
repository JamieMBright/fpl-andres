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

#: 2.3 stops ranking the captaincy theses and starts testing them. A table of
#: ten means always produces a winner, whether or not one exists, and the 2.2
#: ordering inverted on a single arithmetic fix -- which is what a lead inside
#: the noise looks like. Every thesis is now paired week for week against the
#: projection and resampled, so a gap that does not clear zero is reported as
#: not clearing zero. No projection changed; what changed is what may be
#: claimed from it.
MODEL_VERSION = "2.3"
