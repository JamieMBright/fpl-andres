# Built and not wired, asked for and not done

Audit C. Capability that exists in the repository and does not run, and work
that was planned and never executed. Sourced from `test_reachability.py`'s two
orphan ledgers, `docs/LIMITATIONS.md`, `docs/ROADMAP.md`, `docs/BUILD_PLAN.md`
and a table-by-table check of the migrations.

Scores are on the scale in [`IMPROVEMENTS.md`](../../IMPROVEMENTS.md).

---

## C1. The rank model — the objective the game actually has

**Score 10. Do.** `python/fpl_andres/planning/effective.py`

`RankModel`, `effective_points`, `effective_ownership`, `swing_risk`,
`mandatory_players` and `SwingRisk` are complete, tested, and called by nothing.

This is the same finding as [A1](01-methodology.md#a1-the-objective-is-points-the-game-is-rank)
and it is listed twice deliberately: A1 argues the objective is wrong, C1
records that the correction is already written and sitting unused. Whichever way
the argument in A1 lands, the code is there.

---

## C2. Six Supabase tables with forced RLS, immutability triggers, and no rows

**Score 6. Do — decide per table.**

Checked every `create table` in `supabase/migrations/` against every read and
write in `python/` and `api/`. Six have no writer anywhere:

| Table                        | Migration                                   | Intended purpose                            | Why it is empty                                                   |
| ---------------------------- | ------------------------------------------- | ------------------------------------------- | ----------------------------------------------------------------- |
| `rules_snapshots`            | `20260729183000_evidence_snapshots.sql`     | The FPL rules in force for a projection run | Nothing records them; `RulesSnapshot` lives only in memory        |
| `projection_runs`            | `20260730120000_projection_artifacts.sql`   | Header row per promoted projection run      | Projections ship as a committed JSON artifact instead             |
| `team_goal_projections`      | `20260730120000_projection_artifacts.sql`   | Dixon-Coles output per fixture              | Same — output lands in `projections.json`                         |
| `optimization_runs`          | `20260731120000_optimization_artifacts.sql` | The M14 optimiser wiring target             | Optimiser never called with a live team                           |
| `optimization_event_plans`   | `20260731120000_optimization_artifacts.sql` | Child of the above                          | Same                                                              |
| `element_price_observations` | `20260801120000_history_corpus.sql`         | Daily price series                          | `cli/ingest_ownership.py` writes gitignored JSONL to disk instead |

This is dead surface area carrying real cost: every one is in the migration
ordering test, the RLS policy test and the rollback script, and each is a
schema a future change has to stay compatible with.

**Decide per table, not as a batch.** `element_price_observations` should be
filled — the ingest already produces the data and A12 needs it. The
`optimization_*` pair should be filled if and only if the optimiser is wired.
`projection_runs` and `team_goal_projections` duplicate a committed artifact
that works; they are candidates for **deletion**, not population. Dropping a
table is a migration and a rollback, both cheap.

---

## C3. Sixteen CLI entry points with no schedule and no runbook

**Score 7. Do.**

`.github/workflows/` invokes exactly seven CLI modules: `capture_crowd`,
`ingest_historical`, `live_contracts`, `validate`, `track_model`, `reconcile`,
`compare_validation`.

The other sixteen — `backtest_ceiling`, `benchmark`, `capture_cohort_picks`,
`cohort_captains`, `crosswalk`, `ingest_ownership`, `publish_analysis_seasons`,
`publish_cohort`, `publish_fpl500`, `publish_opening_squad`,
`publish_projections`, `publish_season_inputs`, `publish_season_plan`,
`publish_understat`, `sweep_managers`, `verify_veterans` — have no scheduled
runner. `docs/RUNBOOK.md` and `docs/OPERATIONS.md` do not mention any of them:
grepping both files for `fpl_andres.cli` returns nothing.

Nine of those sixteen generate the committed artifacts under
`apps/web/src/data/`. **The site's contents depend on an operator remembering to
run nine undocumented commands in an unrecorded order.** The failure mode is not
hypothetical: it is exactly how the calibration page came to claim the naive
baseline was winning for months.

**Fix.** Two things, in order. First, a `docs/RUNBOOK.md` section listing every
publish command, what artifact it writes, what it needs in the environment, and
when it must be rerun. Second, a workflow that runs the artifact-producing ones
on a schedule and commits the result, exactly as `validate-model.yml` already
does for the backtest.

---

## C4. The horizon MILP runs once, offline, for one squad

**Score 8. Do.**

`HighsHorizonOptimizer` plans across events with free-transfer carry and
captaincy inside the objective. It is reachable — but only from
`cli/publish_season_plan.py`, which produces the static opening-squad artifact.

Three different planners coexist:

| Path                       | Planner          | Where                               |
| -------------------------- | ---------------- | ----------------------------------- |
| Publish-time opening squad | HiGHS MILP       | `planning/season_plan.py`           |
| Backtest                   | greedy best-swap | `simulation/minileague_policies.py` |
| The user's own live plan   | JS beam search   | `packages/quick-solver`             |

So the model that is _measured_ is the greedy one, the model that is _shown_ to
a visitor is the beam search, and the MILP — the only one with an optimality
argument — plans a squad nobody owns.

`python/tests/test_horizon_scale.py` opens with "The horizon MILP was left
unwired for being intractable. At live scale it is not." The tractability
objection has already been retired by the repo's own test. `docs/ROADMAP.md`
agrees: "The blocker is the season, not the solver."

**Fix.** Wire the MILP into the live path for a single manager's horizon. The
orphaned builders `optimization_state_evidence_from_team_state` and
`optimization_rules_from_snapshot` exist precisely to construct that request and
are unused because `publish_season_plan.py` builds its request longhand.

---

## C5. The beam search ships at a width its regret was never measured at

**Score 7. Do.** `apps/web/src/state/season-solver.ts`,
`packages/quick-solver/src/index.test.ts`

Regret against a HiGHS reference is asserted on three fixtures at
`beamWidth: 16`. The season solver runs at `beamWidth: 12`:

```ts
const solved = solveQuickPlan(input, {
  beamWidth: 12,
  candidateLimitPerPosition: 8,
  maxTransfers: 2,
});
```

No test measures regret at the shipped setting. Worse, all three fixtures have
`maxAllowedRegret: 0` and are miniature (4, 6 and 22 elements) — a real solve
sees 500+ players, sets `bounded_search_truncated` on every run, and chains 38
greedy steps.

The user is shown a net-points figure for a season plan with no gap estimate at
all. The code comment is honest about this; the UI is not.

**Fix.** Add a regret fixture at production settings and realistic pool size,
and publish the measured gap next to the plan.

---

## C6. `plan_transfers` and `premium_is_justified` are complete and unreachable

**Score 6. Do.** `python/fpl_andres/planning/transfers.py`

Both are in `KNOWN_ORPHANS` with the reason "planning surface, not yet on a
page". The site's `TransferPlanPanel` refuses honestly — "I will not show you a
transfer plan built on nothing" — while the module that would fill it sits
unused.

`premium_is_justified` answers a question people actually ask (does the marquee
striker beat spreading the money) and nothing surfaces it.

---

## C7. The starts blend is measured, better, and not wired

**Score 7. Do.**

Measured across six season pairs against next season's opening starts: season
minutes score 0.616 on rank correlation, season starts 0.620, and a rank blend
of season starts with closing-six starts 0.646 — winning five of the six pairs.

`docs/MODEL.md`: "**The blend is measured and not yet wired in.**"

An improvement that has already been measured as an improvement, on the metric
the project uses, and has not been adopted. Whatever the reason, it is not
recorded anywhere, which makes it indistinguishable from having been forgotten.

---

## C8. Understat volume and quality shrinkage: measured 3.4% better, deferred

**Score 6. Owner decision.**

`data/crosswalk/understat-2025-26.json` holds shot profile and penalty exposure
keyed by FPL code for 407 verified players. The penalty split is done. The
projector still prices from total xG.

Measured MAE gain: 3.4%. Shipping deferred with no recorded reason.

Rated 6 rather than 7 because only ~56% of the current pool joins the crosswalk
(departed players lose their code), so the improvement is partial by
construction and the evidence-level handling for the non-joining half needs
designing.

---

## C9. Chips are chosen by fixture count

**Score 6. Owner decision.** `python/fpl_andres/simulation/chips.py`

`plan_chips` reads fixture counts and a squad-value floor. The optimiser
contracts refuse `chip_scenario != "none"` at the schema layer, so no solver
ever sees a chip.

Four chips are plausibly worth 80–150 points across a season. See
[A13](01-methodology.md#a13-chips-are-heuristic-and-worth-a-lot-of-points):
this is downstream of the predictive-distribution work in A9 and should not be
started first.

---

## C10. Capability blocked by something outside the repository

**Score 2. Don't — record and move on.**

Grouped because the correct action for all of them is the same: leave them
alone, keep the harness, and do not spend effort on workarounds.

| Capability                     | Blocker                                                                         | Evidence                                                                              |
| ------------------------------ | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Bookmaker odds                 | Every price host refuses TLS from this network                                  | See [`05-data-and-sources.md`](05-data-and-sources.md) — this one has a route forward |
| StatsBomb ingest               | Parsers exist, no ingest path, no licence resolved                              | `adapters/statsbomb.py`                                                               |
| FPL Review comparison          | `robots.txt` refuses `ClaudeBot` explicitly, plus `Content-Signal: ai-train=no` | Do not scrape                                                                         |
| FPL Kiwi comparison            | Domain does not resolve                                                         | Gone                                                                                  |
| Championship minutes           | FBref 403s behind Cloudflare; `openfootball` has no player minutes              | Do not circumvent the challenge                                                       |
| Out-of-position classifier     | `classify_deployment` complete; no live role data source                        | `models/deployment.py`                                                                |
| Historical manager journeys    | `entry/{id}/event/{gw}/picks/` returns 404 for completed seasons                | Verified 2026-07-31                                                                   |
| Cohort persistence measurement | Sweep filters on outcome; cannot measure that outcome                           | `repeat_rate` correctly refuses                                                       |

The last one is worth singling out as _good_: refusing to publish a
selection-biased number is the right call and most projects would have published
it.

---

## C11. `project_expected_points` — the analytic model that lost

**Score 3. Don't.** `python/fpl_andres/models/expected_points.py`

A closed-form `E[floor(X/d)]` xPTS model, promoted, tested, and bypassed because
the backtest projector prices scoring itself.

Rated low as an _integration_ task — two scoring implementations is worse than
one, and the projector's is the one that reconciles to within one point of FPL's
own total across 34,383 player-gameweeks.

It becomes valuable for a different reason: it is the natural home for the
predictive distribution that [A9](01-methodology.md#a9-captaincy-is-a-right-tail-bet-priced-with-a-point-estimate)
needs. Do not wire it as a competitor to the projector. Mine it for the
distribution work.

---

## C12. Retention policies that nothing enforces

**Score 3. Owner decision.**

`docs/RETENTION.md` promises a one-year window on `workflow_run_events` and a
ceiling on `backtest_predictions`. Neither is automated, and the doc says so
plainly and gives a reason: a scheduled job with `delete` privileges pointed at
the evidence table would be untested code.

That reasoning is sound today and expires the moment either table grows. Rated
low because nothing is currently at risk; recorded because the trigger for
action is a size, and nothing measures the size.
