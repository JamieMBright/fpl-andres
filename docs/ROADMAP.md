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

### Unmodelled but heavily owned

A marquee signing or a promoted-club player has no Premier League record, so no
projection is possible and none will be invented. But ownership is published
from day one, and a player owned by forty percent of the game is a risk whether
or not we can model him.

These are reported as a **known unknown**: named, with their effective
ownership, and an explicit statement that no projection exists. Silence would
imply they are safe to ignore, which is the opposite of true. Once a few
gameweeks of evidence exist they leave this list and enter the projection
normally.

**Proves**: absent evidence disables a projection without hiding a risk.

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

## T9 — Full audit

Last, and deliberately adversarial. Every previous milestone claims something
ships; this one checks whether it is actually reachable.

- **Dead code.** Every public function traced to a caller. Anything reachable
  only from its own tests is either wired up or deleted. `HighsHorizonOptimizer`
  sat in that state for weeks while a weaker greedy planner ran in production.
- **Dead branches.** Every cost path exercised at least once by a test. The
  four-point hit rule was implemented, tested by inspection, and never executed
  because the policy could not reach it.
- **Orphaned data.** Every ingested column consumed by something.
  `goals_conceded` and `defensive_contribution` were fetched and discarded for
  weeks.
- **Stale artifacts.** Published numbers regenerated from the current code and
  diffed. A committed figure that no longer reproduces is a lie with a
  timestamp.
- **Unfair comparisons.** Every baseline scored on the same population and under
  the same constraints as the method it is judged against.
- **Config that is never read.** Settings that exist but change no behaviour.

**Output**: a written finding per issue, each either fixed or recorded in
`LIMITATIONS.md` as a known gap. No issue is closed by asserting it is fine.

**Status: done.** `python/tests/test_reachability.py` walks the package AST and
fails the build on a new orphan, or on a recorded orphan that has quietly been
wired up. Seventeen functions and seven modules were found and are listed in
`LIMITATIONS.md` under "Built but not wired". Every ingested column is now
consumed. Every baseline is scored on a common population.

---

## Standing state, 31 July 2026

What runs today, before a ball is kicked:

- **Players page.** All 564 players in the 2026/27 game, at published prices,
  against a per-match record rebuilt from every scoring route across 2025-26,
  with the opening five rated on measured club strength. 220 have no record and
  are shown blank.
- **Opening squad.** Fifteen players inside the real rules, chosen to maximise
  the starting eleven with a bench that can actually play.
- **Team page.** FPL wipes squads between seasons, so it shows the manager's own
  record, the recommended opening squad and the plan that follows the first
  deadline. It becomes a squad dossier the moment gameweek 1 is processed.
- **Calibration page.** Four seasons, four policies, chips on, including the
  season the method loses.
- **Methodology page.** How the projection is built and where it fails.

---

## Outstanding

Ordered by what would change the answers most, not by effort.

### Measured, and still not wired

1. **Understat is joined and unused.** The crosswalk verifies 94.9% of eligible
   2025-26 players against Understat, and that brings npxG, xA, shots, key
   passes, shot locations and buildup involvement with it. **None of it feeds a
   projection.** The attacking rate already uses FPL's own expected goals from
   2022-23 onward (see [`MODEL.md`](MODEL.md) §3), so the gap is not "no xG" —
   it is penalty-separated xG, shot volume and shot position. Shot coordinates
   are what a positional matchup would need.
2. **FPL published no expected values before 2022-23.** Coverage is 0% for
   2019-20 to 2021-22 and 100% from 2022-23, so the rate model silently switches
   basis at that boundary. Any backtest spanning it is scoring two different
   models and must say so.
3. **A starts blend edges the minutes model, but only just.** Scored on the
   population the model will actually speak for: model `P(start)` **0.547**,
   season minutes 0.513, season starts 0.514, closing-six starts 0.505, and a
   rank blend of season with closing starts **0.559**, winning four of six
   season pairs. The model already beats every crude marker; the blend is worth
   about **+0.012** and is not yet wired. An earlier note in this file claimed
   0.646 against 0.616, which was measured on everyone rather than on the
   model's population and so included fringe players who are trivially
   predictable. That comparison was unfair and the numbers above replace it.

### Built, tested, and called by nothing

3. **`project_expected_points`**, the promoted xPTS model. The backtest projector
   reimplements scoring rather than calling it, so there are two pricings of the
   same rules and only one is exercised.
4. **`HighsHorizonOptimizer`.** Plans across events with free-transfer carry and
   captaincy inside the objective. A greedy swap runs instead. It cannot go in
   the backtest — eleven thousand binary variables times twenty managers times
   three seeds times four seasons times thirty-two gameweeks is not tractable,
   and the request contract wants per-event hashes and a rules snapshot per
   historical season. It belongs on the live single-team path, which needs a
   played gameweek.
5. Fifteen further orphans, listed in `LIMITATIONS.md`. The reachability audit
   fails the build on any new one.

### Not built

6. **`fplcache`** (approved). Six-hourly bootstrap snapshots would give
   retroactive ownership and price history that `crowd_snapshots` can only
   collect forwards. Highest value per unit of effort of anything not started.
7. **Benchmark against FPL Review and FPL Kiwi** (approved). The strongest
   validation available, and it may not flatter us.
8. **Championship minutes for promoted clubs.** Three of twenty come up each
   year with no Premier League record, so they cannot be ranked or picked.
   Scoring rates do not transfer across divisions but minutes might, which is
   exactly what bench cover needs. FBref has it; `soccerdata` does not ship it.
9. **End-of-season projection and posterior carry (T2).** `project_horizon`
   stops at seven gameweeks and refits from scratch each week.
10. **Positional matchups.** One attack and one defence figure per side. Shot
    coordinates would give flank vulnerability; nothing reads them.

### Waiting on the season

11. **Mini-leagues 34555 and 393774.** Rival picks are only legally readable
    after a deadline.
12. **The proven-manager cohort.** A full entry sweep is running; the resulting
    catalogue is not yet wired to anything.
13. **Live smoke test** on entry 212279 once gameweek 1 is processed.

### Unverified

14. **The club limit correction rule** came from the owner, not from the
    published rules text. If FPL allows the correction to wait, the encoding is
    wrong.

## Standing rules

- `pnpm check`, `pnpm format:check` and `pnpm test:e2e` green before every
  milestone commit.
- A missing source disables a feature; it never licenses an estimate.
- Published claims live in a committed artifact, so a number on the site can
  always be traced to the commit that produced it.
