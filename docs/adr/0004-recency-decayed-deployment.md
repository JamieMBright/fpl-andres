# 4. Deployment is classified from recency-decayed evidence

- **Status**: accepted
- **Date**: 2026-08-01 (recording a decision already encoded in the code)

## Context

`models/deployment.py` decides how a player is being used — whether he starts,
whether he plays a full match, whether his role has changed. It does this from
weighted recent appearances rather than a season average, with an exponential
half-life applied to the event distance.

Half-lives are the sort of parameter that invites arbitrary choice, and an
arbitrary choice here would move every projection. The reasoning was not
written down.

## Decision

Classify deployment from recency-decayed observations, with the half-life a
sourced parameter rather than a tuned one, and refuse an observation whose
weight has decayed to nothing.

## Consequences

**A season average is the wrong summary of a changing role.** A player who
started the first ten matches and has been benched since has a season start rate
near 0.6 and a current start probability near zero. FPL is played one deadline
at a time, so the recent state is the one that pays.

**The half-life is sourced, not fitted.** Fitting it on the same corpus the
model is scored against is how a backtest flatters itself. It is recorded with
its provenance in `docs/MODEL.md`.

**Effective sample size shrinks with the weighting, and the shrinkage must
follow.** Weighted evidence is worth less than its raw count suggests, so the
shrinkage uses the Kish effective sample size `(Σw)²/Σw²` rather than `Σw`.
Using the raw weight sum understates nailed starters, which was measured and is
recorded in the repository notes.

**An observation that decays to zero weight is refused.** It contributes nothing
to the estimate while still counting towards the minimum-observations floor, so
the projection would rest on less evidence than the caller believes. Raising
names the offending events rather than silently proceeding.

## Alternatives considered

**Fixed window — last N matches, unweighted.** Rejected: it throws away the
distinction between a player benched last week and one benched six weeks ago,
and it makes the estimate jump discontinuously as matches leave the window.

**Season average.** Rejected for the reason above: it answers a question nobody
is asking at a deadline.

**Fit the half-life on holdout data.** Rejected for now. It is defensible, but
it requires the promotion gate to be exercised, and until a fitted value beats
the sourced one on a paired bootstrap with the sample floor met, the sourced
value stands. That gate exists in `models/promotion.py` and nothing has passed
it yet.
