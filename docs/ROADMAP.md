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

1. **Understat is joined and barely used.** The crosswalk verifies 94.9% of
   eligible 2025-26 players against Understat, and that brings npxG, xA, shots,
   key passes, shot locations and buildup involvement with it. Only the penalty
   split now feeds anything. The attacking rate still uses FPL's own expected
   goals from 2022-23 onward (see [`MODEL.md`](MODEL.md) §3), so the remaining
   gap is shot volume and shot position. Shot coordinates are what a positional
   matchup would need.

   **Stage 1 is done and measured.** `models/penalties.py` splits penalty from
   open-play xG and the crosswalk CLI carries the exposure per FPL code.
   Penalties are 5.9% of league xG but 44.5% of Cole Palmer's and 38.3% of
   Bruno Fernandes's, with 24 regulars above 15%; losing the duty would cost
   Palmer about 0.82 FPL points a 90. **The exposure is measured but the
   projector still prices from total xG**, because only one Understat season is
   cached and a basis change cannot be backtested on one season.

   **Stage 2 is done and measured, and the honest answer is "small".**
   `models/shot_profile.py` splits npxG/90 into shots/90 times npxG/shot.
   Across four seasons and 553 season pairs, volume repeats at **0.890** year
   to year against 0.860 for npxG/90, while quality repeats at only **0.455**.
   Volume is the durable part — but quality is noisy, not noise: replacing it
   with the league mean makes prediction _worse_, MAE 0.0561 to 0.0666.
   Shrinking it by shot count wins, optimum near ten shots of prior, plus a
   10% regression on volume. The win is **MAE 0.05608 to 0.05417, 3.4%**,
   which is 0.0076 FPL points a 90 for a forward or about **0.29 points across
   a season**. Measured, real, and not on its own a reason to move the
   projector off FPL's own expected goals.

   **Stage 3 is closed as a negative result** — see item 10. Shot context does
   not persist at team level, so the coordinates stay unread on purpose.

2. **FPL published no expected values before 2022-23.** Verified against the
   corpus: 0% coverage for 2019-20, 2020-21 and 2021-22, 100% from 2022-23
   onward. All seven seasons are ingested, so the boundary is reachable rather
   than hypothetical. Two guards now exist: the rate model already refuses to
   blend bases and falls back to actuals when either season is incomplete, and
   the validation artifact carries `expectedGoalsCoverage` per season with the
   site saying so when it is below one. **The published span is 2022-23 to
   2025-26, all at 100%**, so nothing on the site currently mixes regimes. What
   is still missing is a refusal: a backtest spanning the boundary reports two
   different models and only warns.
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

3. **Suspension risk.** `models/suspensions.py` prices the accumulation ban a
   booking eventually triggers, which is worth far more than the minus one for
   the card itself: crossing a rung costs a nailed starter a whole gameweek.
   Not wired, because the thresholds are a controlling rule nobody has sourced
   yet and the model refuses to invent them.
4. **`project_expected_points`**, the promoted xPTS model. The backtest projector
   reimplements scoring rather than calling it, so there are two pricings of the
   same rules and only one is exercised. **Keep it: it is not the weaker of the
   two.** It prices step-function routes analytically as `E[floor(X/d)]` under
   Poisson, which is the closed form of exactly the bug that had to be patched
   out of the projector empirically, and it reads every points value from the
   rules snapshot instead of hardcoding constants.

   The Poisson assumption was checked rather than trusted. Saves are
   **overdispersed** — variance over mean is 1.41, 1.24 and 1.09 across
   2023-24 to 2025-26, where Poisson demands 1.0 — so the assumption is
   formally wrong. It barely matters: the analytic form lands within 0.0001 to
   0.0112 points a start of the measured truth, about thirty times smaller than
   the naive bug it replaces, with a worst per-keeper error of 0.16. Wiring it
   wholesale is a large refactor with no measured accuracy gain, so it stays
   unwired on purpose rather than by neglect.

5. **`HighsHorizonOptimizer`.** Plans across events with free-transfer carry and
   captaincy inside the objective. A greedy swap runs instead. It cannot go in
   the backtest — eleven thousand binary variables times twenty managers times
   three seeds times four seasons times thirty-two gameweeks is not tractable,
   and the request contract wants per-event hashes and a rules snapshot per
   historical season.

   **The live path is a different problem, and it is tractable.** One squad,
   once a week. Measured: a full fifteen-player squad over a hundred candidates
   and three events solves in **0.23s**; two hundred over three in 0.52s; two
   hundred over five in 6.30s; four hundred over five in 10.46s. Locked in by
   `test_horizon_scale.py` so the claim cannot rot. **The blocker is the
   season, not the solver** — `plan_transfers` is itself not on a page yet and
   the site's panel honestly refuses, because no gameweek of 2026/27 has been
   played.

6. Fifteen further orphans, listed in `LIMITATIONS.md`. The reachability audit
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
9. **End-of-season projection and posterior carry (T2): mostly a non-issue,
   measured.** The claim was that `project_horizon` stops at seven gameweeks
   and refits from scratch each week. Neither is quite a defect. Seven is only
   the default in `horizons`; any length is accepted, now covered by
   `test_season_horizon.py`. And refitting on all history each week **is** the
   posterior update for a conjugate shrinkage model, so nothing is lost by not
   carrying one explicitly.

   The real worry was frozen form: form is measured once at the projection
   gameweek and held for every week after, so a hot player would stay hot for
   thirty-one weeks. Measured against realised totals from GW8 across three
   seasons, bias per gameweek at a thirty-one week horizon is **+0.197,
   -0.005 and +0.095** — small and inconsistent in sign, so noise rather than
   drift. Rank correlation _improves_ with horizon, 0.48-0.51 against 0.24-0.32
   at one week, because weekly noise averages out. What remains is presentation:
   no surface asks for a season-long view.

10. **Positional matchups: tested and refused.** The premise was that shot
    coordinates reveal which defences leak down a flank, from distance, or at
    set pieces. It does not survive contact with the data. Splitting each
    team's season in half across all four seasons and correlating the first
    half's concession profile against the second gives, for flank share, +0.04,
    +0.04, +0.16, +0.26; for close-range share +0.16, +0.21, +0.08, +0.05; for
    long-range share +0.70, +0.53, **-0.05**, **-0.20**; and for set-piece
    share +0.07, -0.01, **-0.23**, **-0.29**.

    The control is the point. **Total xG conceded persists at +0.57, +0.75,
    +0.71 and +0.49**, so the method detects a real team property when one is
    there. The context shares do not: long range looked convincing for two
    seasons and then flipped sign, and set-piece share is mostly negative.
    **One defence figure per side is the right granularity.** The shot
    coordinates are not worth reading for this. Recorded so nobody spends the
    effort twice.

11. **Bookmaker odds as a probability source.** Bookmakers price fixtures for a
    living and are marked to market by people trying to take their money, so
    their implied probabilities are the strongest freely available estimate of
    the things this model already guesses at: match outcome, total goals, clean
    sheets, and — in the goalscorer markets — the chance a named player scores.

    What maps onto what: `1X2` and Asian handicap give relative team strength;
    over/under 2.5 gives a total-goals expectation that pins both Poisson means
    once combined with the handicap; "both teams to score" and correct-score
    markets back out P(clean sheet) directly, which is currently one of the
    weakest parts of the projector; anytime-goalscorer prices are a per-player
    goal probability that would be checked against the xG route rather than
    replace it.

    Three problems to solve before any of that is worth writing:

    - **The overround has to come out.** Quoted prices are not probabilities.
      They sum to more than one, typically a few per cent on `1X2` and far more
      on goalscorer markets, because the margin is the bookmaker's income.
      Dividing through by the total — the obvious fix — is biased, because the
      margin is not spread evenly: longshots carry more of it than favourites.
      Shin's method or a power fit handle that; proportional de-vigging would
      systematically flatter exactly the cheap differential punts FPL rewards.
    - **The sharp prices arrive too late to act on.** Odds are most accurate at
      kickoff, but the FPL deadline is usually a day or two earlier and team
      news is what moves them. Anything built here must be fitted on prices as
      they stood _at the deadline_, not on closing prices, or the backtest will
      score information the manager could never have had. This is the same
      leak the corpus cutoff already guards against elsewhere.
    - **Sourcing has to be legitimate, and this machine cannot currently reach
      any of it.** Scraping bookmakers directly is against their terms and is
      bot-protected in any case. The defensible routes are redistributors and
      documented APIs: football-data.co.uk publishes free per-season CSVs of
      multi-bookmaker closing odds with no key, The Odds API documents a free
      tier, and the Betfair exchange is an open market rather than a bookmaker,
      so its prices carry commission instead of a margin and are usually the
      sharpest of the lot. **Measured 1 August 2026: all three domains fail at
      the TLS handshake from this network while the FPL API and Understat
      succeed**, which is the signature of a gambling-category content filter
      rather than an outage. This item therefore cannot be started here without
      the owner confirming a network that permits it.

### Waiting on the season

12. **Mini-leagues 34555 and 393774.** Rival picks are only legally readable
    after a deadline.
13. **The proven-manager cohort.** A full entry sweep is running; the resulting
    catalogue is not yet wired to anything.
14. **Live smoke test** on entry 212279 once gameweek 1 is processed.

### Unverified

15. **The club limit correction rule** came from the owner, not from the
    published rules text. If FPL allows the correction to wait, the encoding is
    wrong.

## Standing rules

- `pnpm check`, `pnpm format:check` and `pnpm test:e2e` green before every
  milestone commit.
- A missing source disables a feature; it never licenses an estimate.
- Published claims live in a committed artifact, so a number on the site can
  always be traced to the commit that produced it.
