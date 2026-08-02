# Retention

Audit item #104. Several tables here only ever grow, and nothing recorded what
the plan was. That is a decision either way, and an unrecorded one becomes
whatever the free tier decides for it — usually during a season, usually with
no warning, and usually by refusing a write rather than by asking.

The policy below is mostly "keep everything", which is only a defensible answer
with a number attached. The numbers are here.

---

## The measurement

Supabase's free tier allows 500 MB of database storage. That is the ceiling
every figure below is measured against.

Measured on the loaded corpus (`docs/CORPUS.md`, audit item #98): **185,954
player-gameweek rows across seven seasons occupy 26 MB**, and a season adds
about **28,396 rows and 6.6 MB**.

| Table                        | Grows with         | Rows per season | Notes                                               |
| ---------------------------- | ------------------ | --------------- | --------------------------------------------------- |
| `element_gameweek_stats`     | seasons × players  | ~28,400         | The corpus. 6.6 MB a season.                        |
| `element_price_observations` | seasons × players  | ~28,400 max     | Primary key is `(season, element_id, observed_on)`. |
| `crowd_snapshots`            | captures × players | ~63,000         | Three captures a week, ~550 elements.               |
| `backtest_predictions`       | backtest runs      | unbounded       | See below — the only one with a real ceiling risk.  |
| `source_snapshots`           | fetches            | ~1,000          | Hashes and URLs, no payloads.                       |
| `workflow_run_events`        | job runs           | ~2,000          | Two rows per run, a handful of runs a day.          |
| `projection_runs`            | projection runs    | ~40             | One per gameweek.                                   |
| `optimization_runs`          | plans              | ~200            | A few per gameweek.                                 |

At 6.6 MB a season for the largest table, the corpus reaches the free-tier
ceiling somewhere around the year 2100. It is not the constraint.

---

## Policy per table

### Keep indefinitely

`element_gameweek_stats`, `element_price_observations`, `crowd_snapshots`,
`fixtures`, `teams`, `elements`, `seasons`.

These are the evidence. Every backtest number this project publishes is
measured over them, and a claim about 2022-23 is only reproducible while
2022-23 is still here. Deleting the oldest season to save six megabytes would
trade the thing the project is for against a cost that is not being paid.

`crowd_snapshots` is the fastest-growing of these, at roughly 63,000 rows a
season, because ownership is captured three times a week — Thursday, Friday and
Saturday, bracketing a typical deadline. That cadence is the point: the table
exists to show how the crowd moved, and a single weekly capture would not show
movement, it would show a sequence of unrelated states. At about 3 MB a season
it stays well inside the budget.

### Keep, with a stated ceiling

`backtest_predictions`.

One row per player per gameweek per backtest run. A single seven-season
backtest writes on the order of 186,000 rows, and the promotion process from
audit item #30 runs **twenty seeds** for a candidate — so one promotion decision
can write around 3.7 million rows and several hundred megabytes.

This is the only table that can reach the ceiling in a season rather than in a
century, and it is the one the item is really about.

**Policy**: predictions are kept for runs referenced by a
`model_promotion_decisions` row, and for the most recent run per model
otherwise. A backtest that informed a promotion is evidence and stays. A
backtest run to try something out is working, and working can be regenerated —
the lineage recorded in audit item #197 exists precisely so it can be, from the
same corpus fingerprint and the same code revision.

**Not yet automated, deliberately.** No promotion has run against production,
so there is nothing to prune and a scheduled job that deletes rows would be
untested code with `delete` privileges pointed at the evidence table. The
trigger to write it is the first promotion decision, not a date.

### Keep for one year

`workflow_run_events`.

Two rows per run, a handful of runs a day: about 2,000 rows a year, which is
nothing. The limit is not about space. It is that a status transition from
eighteen months ago answers no question anybody asks — every use of this table
is "what happened in the last few days", and an unbounded log makes the index
larger for no gain.

Not yet automated, same reasoning as above: the table is new, and the first
year is exactly when the history is most worth having in full.

---

## Revision

None of these tables may be revised in place, and most are held to it by an
immutability trigger rather than by convention.

Correcting an observation therefore means appending a corrected one, not
editing the wrong one. That is not a workaround. The wrong value was what the
model saw when it made a recommendation, and deleting it makes that
recommendation unexplainable — the corpus fingerprint recorded with every
backtest (audit item #197) would then point at a corpus that no longer exists.

`workflow_runs` is the single exception and says so in `docs/SCHEMA.md`: its
status changes in place, because a run that started and then finished is one
run and not two. The history of those changes is in `workflow_run_events`,
which is itself immutable.

---

## What would change this

The policy above is right for a project with a seven-season corpus and no
production promotions. Each of these would make it wrong:

- **A promotion decision runs against production.** `backtest_predictions`
  becomes the largest table by an order of magnitude, and the pruning described
  above needs writing rather than describing.
- **Crowd capture goes daily.** 63,000 rows a season becomes 200,000. Still
  affordable, but the cadence change should be a decision rather than a
  side effect.
- **Storage passes 250 MB.** Half the free tier, and the point at which the
  next season's growth needs checking against the remainder rather than assumed
  to fit.
- **A season is loaded from a second source.** Two copies of the same
  player-gameweek at different grains is a bigger problem than either one's
  size, and this document is not the place that solves it.
