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

#: 2.6 adds the set-and-forget baseline -- captain the most-owned player at the
#: first scored gameweek and never think again, with the armband passing to the
#: next most owned when he does not play. Written without Haaland's name in it,
#: because naming him would be hindsight. It is the baseline that matters: no
#: projection, no form, no fixture, and no decision after the opening week. A
#: model that cannot beat it is not earning its complexity.
#:
#: Also publishes the arithmetic behind every armband, so a surprising pick can
#: be read rather than defended.
#:
#: 2.5 retains the captaincy picks themselves rather than only what they
#: returned. No projection and no metric should move: the scorers compute
#: exactly what they always did and now write down which player they named.
#: That is precisely why it gets a version — the scorer signatures changed, so
#: the run needs a label the CI comparison can hold the previous numbers
#: against and show that none of them moved.
#:
#: 2.4 is the first version that actually produces the intervals 2.3 promised.
#: 2.3 refused to score a gameweek where the captain lost points -- a red card
#: or an own goal -- so the backtest raised before writing anything. Nothing
#: 2.3 claimed was ever measured, which is why this is a version and not a
#: patch: the two are not comparable, because one of them has no numbers.
#:
#: 2.3 stopped ranking the captaincy theses and started testing them. A table of
#: ten means always produces a winner, whether or not one exists, and the 2.2
#: ordering inverted on a single arithmetic fix -- which is what a lead inside
#: the noise looks like. Every thesis is now paired week for week against the
#: projection and resampled, so a gap that does not clear zero is reported as
#: not clearing zero. No projection changed; what changed is what may be
#: claimed from it.
MODEL_VERSION = "2.6"
