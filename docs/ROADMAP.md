# Thesis delivery roadmap

Supersedes the milestone list in [`BUILD_PLAN.md`](BUILD_PLAN.md), which took
the product from scaffold to a working corpus and models. That work is done.
This plan delivers [`THESIS.md`](THESIS.md): a wired site that plans an optimal
transfer path against effective points, proves it against real baselines, and
shows the reader the working.

Ordered by dependency. Nothing later can be judged before its inputs exist.

---

## T1 — The yardstick

Nothing about the engine can be claimed until there is something honest to beat.
Three baselines, weakest to strongest, all playing under identical rules: one
free transfer a week banking to five, four points a hit, three per club, real
budget.

| Baseline      | Rule                                                       |
| ------------- | ---------------------------------------------------------- |
| `hold`        | Never transfers. Autosubs only.                            |
| `form_chaser` | Every week, buys the highest-form player not owned.        |
| `crowd`       | Every week, buys the most-transferred-in player not owned. |

`crowd` needs `transfers_in_event`, which is already in
`element_price_observations` and `crowd_snapshots`.

**Proves**: a skill score that means something. **Test**: each policy is
reproducible from a seed and obeys the transfer budget.

---

## T2 — Projection to the end of the season

`project_horizon` stops at seven gameweeks and freezes form at the planning
week. The thesis needs every remaining gameweek.

- Extend the ladder to an arbitrary horizon, capped at the final event.
- Decay confidence with distance rather than pretending week 30 is as knowable
  as week 2.
- Carry the posterior forward: this gameweek's result updates the prior for the
  next, rather than the whole history being refitted from scratch each week.

**Proves**: a projection the planner can actually optimise against.

---

## T3 — Wire the optimiser

`HighsHorizonOptimizer` already plans across events with free-transfer carry and
captaincy inside the objective. It is reachable only from its own tests.

- Build a real `HorizonOptimizationRequest` from the corpus and the projection.
- Replace the greedy swap in `simulate_league` with the solver.
- Re-plan every gameweek on the updated posterior, executing only the first
  move of the plan.

**Proves**: the optimal-path claim. **Test**: the solver's plan scores at least
as well as the greedy planner over the same horizon.

---

## T4 — Chips

Absent today. The optimiser hard-refuses anything but `chip_scenario="none"`.

| Chip           | Objective                                                                                            |
| -------------- | ---------------------------------------------------------------------------------------------------- |
| Triple Captain | argmax of expected points over every player-gameweek remaining                                       |
| Free Hit       | the gameweek where an unconstrained one-week squad most exceeds the held squad, with no carry-over   |
| Wildcard       | the gameweek where an unconstrained _persistent_ squad most exceeds the reachable one, once per half |
| Bench Boost    | the gameweek where the bench's expected points peak                                                  |

Each is a comparison between a constrained and an unconstrained solve, so the
optimiser does the work and the chip logic only chooses when.

**Proves**: chip strategy. **Test**: a season with an obvious double gameweek
places the wildcard before it.

---

## T5 — Effective points

Expected points are not the objective; rank movement is. This is the part of the
thesis with real mathematics left in it.

- Map a points delta to an expected rank delta, from the distribution of manager
  scores. Needs the published average and the rank distribution.
- Effective points combine the raw projection with ownership: a haul everyone
  owns moves nobody.
- Maximising points and maximising rank climb are **not** the same objective.
  Ownership cancels out of a transfer's expected gain and changes only variance,
  so the split is risk, not return: cover the field when ahead, take variance
  when behind.

**Proves**: the ExPts claim. **Test**: against a field that all owns one
premium, the recommendation changes with league position.

---

## T6 — Full backtest

Run the whole engine, chips included, from a random opening squad across all
seven seasons, re-planning weekly, against all three baselines.

Publish the result whether or not it flatters the method, including where it
loses. Persist every run to `backtest_runs` keyed by git revision so two runs
are comparable only when the code matches.

**Proves**: the thesis, or disproves it.

---

## T7 — The site

Everything above is invisible until it is wired.

- Serverless endpoint returning projection, plan and chip advice for an entry.
- Pitch view carries per-player expected points, floor and ceiling.
- Transfer plan: the next moves in order, each with its horizon gain and cost.
- Chip strategy as a season timeline.
- Methodology page stating what the engine does, in the same voice as the
  calibration page.
- Calibration page carries the full backtest against all three baselines.

All of it in the Ceefax treatment already established in `DESIGN.md`.

---

## T8 — Verified manager cohort

Deliberately last and deliberately separate. It is a feature for readers, not
part of the thesis. The Reddit veterans list did not survive verification
against the official record, so this ships as "here is what can actually be
confirmed", with percentile ranks rather than raw ones, because the player base
has grown roughly fivefold since 2010.

---

## Standing rules

- `pnpm check`, `pnpm format:check` and `pnpm test:e2e` green before every
  milestone commit.
- A missing source disables a feature; it never licenses an estimate.
- Published claims live in a committed artifact, so a number on the site can
  always be traced to the commit that produced it.
