# 2. Published artifacts are immutable

- **Status**: accepted
- **Date**: 2026-08-01 (recording a decision already encoded in the migrations)

## Context

`supabase/migrations/20260730120000_projection_artifacts.sql` installs a trigger
that raises on any `update` or `delete` against the projection artifact tables.
Rows can be inserted and then never touched again.

That is unusual enough to look like over-engineering, and the reason was not
recorded anywhere.

## Decision

Keep artifacts append-only, enforced by a database trigger rather than by
convention or application code.

## Consequences

**A published number can always be traced to the run that produced it.** The
site shows projections and calibration figures. If a reader asks "why did you
say Raya was worth 3.3 points on the first of August", the answer has to be a
row that still says 3.3, not a row that has since been recalculated. Mutable
artifacts would make every historical claim unverifiable the moment the model
improved.

**A model change cannot rewrite its own history.** This is the failure mode the
trigger exists to prevent. A backtest that can update its previous results is a
backtest that can be made to look better than it was, without anybody acting in
bad faith — an `upsert` where an `insert` was meant is enough.

**Corrections are additive.** A wrong artifact is superseded by a new one with a
later timestamp, and both remain. That is more storage and more query complexity
than overwriting, and it is the price of the property.

**Enforced in the database, not the application.** Application-level
immutability is a promise every future caller has to keep. A trigger is a
promise the database keeps on their behalf, including for a caller written in a
different language or run from a psql session at three in the morning.

## Alternatives considered

**Convention plus code review.** Rejected: it fails silently and only under the
conditions where it matters, which is the worst combination.

**Soft deletes with a `superseded_at` column.** Rejected as insufficient on its
own: it prevents deletion but not update, and update is the dangerous one. The
append-only posture already gives supersession for free by insertion order.

**Versioned rows with an `is_current` flag.** Rejected: the flag is mutable, so
the same problem returns one level down, and now a reader has to know which flag
to trust.
