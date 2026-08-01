# 3. Leakage is prevented structurally, not by discipline

- **Status**: accepted
- **Date**: 2026-08-01 (recording a decision already encoded in the code)

## Context

Every backtest in this repository is a claim about what the model would have
said at a moment in the past. That claim is worthless if any input postdates the
moment. The failure is silent: a leaked feature makes the model look better, and
nothing in the output distinguishes a genuinely good projection from one that
peeked.

The codebase guards against this in several places at once, and the pattern was
never stated:

- `SeasonCorpus.before(gameweek)` is documented as "the only supported way to
  read history during a backtest".
- `FutureMinutesEvidenceError` and `FutureInformationError` are raised by the
  models and the vaastav adapter when evidence postdates the cutoff.
- `SourceSnapshot` refuses a `dataAvailableAt` later than its `fetchedAt`.
- Every timestamp in the package must be aware and in UTC, now via one shared
  guard in `fpl_andres.timeguard`.

## Decision

Leakage guards are structural. A caller should not be _able_ to read future
information through the supported interface, rather than being expected to
remember not to.

## Consequences

**The cutoff lives in the data structure, not the caller.** `before()` takes the
gameweek and returns only earlier rows. There is no version that takes a list of
rows and trusts the caller to have filtered it, because that version would work
correctly right up until somebody forgot.

**Guards raise rather than warn.** A leak is not a degraded result; it is a
wrong one. Returning a projection with a warning attached would let a leaked
number reach a published artifact, and the warning would be the first thing
dropped by whatever consumed it.

**Naive timestamps are refused everywhere.** Comparing a naive datetime to an
aware cutoff either raises or, worse, compares in the wrong direction depending
on how it was constructed. Requiring UTC awareness at every boundary removes the
class of bug rather than the instance. The check was written out fifteen times
before it was centralised, which is itself evidence that scattered discipline
does not hold.

**Some legitimate work is made awkward.** Reading the whole corpus for a
descriptive statistic means going around `before()`, deliberately and visibly.
That is the correct trade: the awkward path is the unusual one.

## Alternatives considered

**Filter at the call site and review carefully.** Rejected: this is the default
that produced fifteen copies of a UTC check. Discipline does not scale across a
codebase, and the failure is invisible in the output.

**Assert after the fact — check the projection did not use future data.**
Rejected: by the time a projection exists, the evidence of which inputs it used
has been aggregated away. There is nothing left to assert against.

**Tolerate leakage in exploratory work and guard only in published paths.**
Rejected: exploratory results are exactly what gets quoted later, and nothing
marks a number as exploratory once it is in a commit message or a chat.
