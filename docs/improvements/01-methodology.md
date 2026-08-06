# The methodology, criticised

Audit A. This file is not a list of bugs. It asks whether the approach is
sound, and mostly answers no — not because the execution is poor, but because
several of the choices that frame everything else are the wrong choices, and
the quality of the writing around them makes that harder to see rather than
easier.

Every finding names the file that would change. Scores are on the scale in
[`IMPROVEMENTS.md`](../../IMPROVEMENTS.md): **value only**, effort ignored.

---

## A1. The objective is points; the game is rank

**Score 10. Do.**

Every model in this repository maximises expected points. `project_gameweek`
returns `expected_points`; the optimiser objective is a sum of expected points;
the captaincy policies are `argmax` over expected points; the mini-league is
scored on net points.

FPL is not a points game. It is a rank game against nine million entries. The
two objectives coincide only in the middle of the distribution and diverge
exactly where the decisions are interesting:

- A manager in the top 10k protecting a rank should hold the template even when
  a differential has higher expected points, because variance is a cost.
- A manager chasing from 500k should take a lower-expected-points differential,
  because variance is the only thing that can close the gap.
- Both are correct. Neither is expected-points maximisation.

The repository knows this. `python/fpl_andres/planning/effective.py` contains
`RankModel`, `effective_points`, `SwingRisk` and `effective_ownership` — a
complete treatment of exactly this. **Every one of them is in `KNOWN_ORPHANS`.**
The module that addresses the real objective function is the module nothing
calls.

The measured excuse is in `docs/ROADMAP.md`: the rank-aware policy was worth
"only ~+16 points a season over four seasons". That number is evidence about
_one particular_ rank-aware policy inside a mini-league of twenty, not about
whether the objective is right. A 20-manager league has no top-10k and no
500k; there is no rank distribution to be aware of. The experiment could not
have found the effect it was looking for.

**What to do.** Stop reporting expected points as the objective and start
reporting the distribution of finishing rank. Concretely: wire `RankModel` into
the mini-league, run it at a league size where rank actually varies, and score
policies on rank percentiles rather than on mean net points. If the answer is
still that rank-awareness is worth little, that becomes a real finding instead
of an artefact of a 20-team league.

**Handoff.** Read `planning/effective.py` in full, then
`simulation/minileague.py`. The task is to make `effective_points` reachable
and scored, not to invent a new model.

---

## A2. Every published metric describes a model that never ships

**Score 10. Do.**

This is the most damaging finding in the audit and it is already documented in
`docs/MODEL_CARDS.md` under "What the backtest grades that the live path does
not". Being documented is not the same as being acceptable.

Verified row by row against the code:

| Feature                        | Backtest (`score_season`)           | Live (`publish_projections`) |
| ------------------------------ | ----------------------------------- | ---------------------------- |
| Team strength                  | `estimate_strength` — goal averages | Dixon-Coles + venue tilt     |
| Recent-form blend              | applied                             | not applied                  |
| Suspension multiplier          | not applied                         | applied                      |
| Fixture-aware route adjustment | applied                             | not applied                  |

Four of the six rows differ. The consequence is not subtle: **the Spearman
figures, the mean absolute error, the top-N hit rate, the captaincy table, the
paired-bootstrap intervals and the mini-league results are all measurements of
a model that no user ever receives.** The calibration page presents them as
validation of the shipped projection. They are not.

The card is honest that the backtest grades a _weaker_ strength model, and
frames closing the gap as a costing problem ("fitting Dixon-Coles once per
scored gameweek across four seasons... has not been costed"). That framing
understates it. The direction of the bias is unknown, not favourable — a
weaker strength model could as easily flatter the projection as penalise it,
because the baselines are scored on the same fixtures.

**What to do.** One projection path. Either the backtest fits Dixon-Coles per
gameweek (expensive but correct), or the live path drops to `estimate_strength`
(cheap and honest). A third option — keep both but publish the backtest twice,
once per strength model, and report the difference — is the cheapest way to
find out whether it matters before paying for it.

**Handoff.** `backtesting/projector.py::project_gameweek` line ~171 calls
`estimate_strength(corpus.fixtures_before(gameweek))`.
`cli/publish_projections.py` line ~213 calls `DixonColesModel.fit`. The
divergence starts there. `models/dixon_coles.py` already has a `fit` that takes
a fixture list, so the backtest can call it; the question is runtime.

---

## A3. Nothing models the fact that a squad is a portfolio

**Score 9. Do.**

Two Arsenal defenders do not keep independent clean sheets. They keep the same
clean sheet. `backtesting/scoring.py` computes `clean_sheet_rate` per player and
multiplies by `probability_sixty_minutes` per player; the covariance between
two players at the same club is nowhere in the projection.

For a **mean** projection this does not matter — expectation is linear. It
matters enormously for everything else:

- `upside` (`μ + σ`) and `robust` (`μ − σ`) are captaincy policies built on a
  variance estimate. The σ they use is `recent_deviation`, a per-player
  historical standard deviation of realised points. That is not the predictive
  distribution's standard deviation, and it contains no covariance term at all.
  Both policies are therefore being scored on a quantity that is not the
  quantity their thesis is about. `upside` finishing 1.20 points a week _below_
  the projection may be a fact about the policy or a fact about the proxy.
- Bench and autosub logic in the mini-league assumes independent draws. Bench
  players blank together when their clubs blank together.
- Any statement about the _risk_ of a squad — the thing rank-aware play needs
  (A1) — is unavailable without covariance.

`planning/effective.py` defines a `PointsCovariance` protocol and `swing_risk`,
and they are orphaned, and `docs/LIMITATIONS.md` records that no source
publishes the covariance. That is not the blocker it appears to be: the
dominant covariance term in FPL is **same-club clean sheets and same-club
attacking returns**, both of which are directly estimable from the corpus. It
does not need an external source.

**What to do.** Estimate a block-diagonal covariance from the corpus: within
club, within position group. Wire it into `swing_risk`. Then re-run `upside`
and `robust` against a predictive σ that includes it.

---

## A4. There is no held-out season, so the hyperparameters are fitted to the test set

**Score 9. Do.**

The corpus holds seven seasons. Validation runs on four (2022-23 to 2025-26),
because expected-goals coverage is zero before 2022-23.

Every tuning constant in the model was chosen by a person who has seen all four
of those seasons: the recency half-lives, the prior strengths
(`_PRIOR_MATCHES = 10`, `_BOOKING_PRIOR_MATCHES = 19`, `_VENUE_PRIOR_MATCHES = 19`),
the multiplier clamps `[0.4, 2.2]`, the 20% recent-form blend weight, the
25-player captaincy shortlist, the 2.0 form floor, the 1.5-per-100%-owned
ownership coefficient.

The repository is careful about _leakage within a season_ — the corpus enforces
the cutoff structurally, `iter_walk_forward_slices` exists as a guard, and
`test_leakage_guards.py` polices it. All of that is protection against the
model seeing the future of a gameweek. **None of it is protection against the
modeller having seen the future of a season.** That is researcher degrees of
freedom, and it is the larger of the two effects when the constants are chosen
by hand and the reported edges are tenths of a point.

The strongest available evidence that this matters is already in the history:
the captaincy ordering inverted completely when a single arithmetic error was
fixed. A result that fragile cannot survive having its constants tuned on the
same data it is scored on.

**What to do.** Declare 2025-26 a holdout and stop looking at it. Fit and
choose on 2022-23 to 2024-25, report the holdout once. Where a constant is
already sourced from a paper or a practitioner, say so and exempt it — the
point is to separate the tuned constants from the sourced ones, which the repo
already believes it does.

**Handoff.** `python/fpl_andres/cli/validate.py` takes `--seasons`. The work is
policy and reporting, not code: a `HOLDOUT_SEASON` constant, a validate flag
that refuses to score it unless asked, and a note on the calibration page.

---

## A5. Nine comparisons, no multiplicity correction

**Score 8. Do.**

`backtesting/captain_significance.py` compares nine theses against the
incumbent, each with its own 95% interval. The calibration page marks a thesis
"better" when its individual interval clears zero.

Nine independent tests at 95% have a family-wise error rate near 37%. On the
current data nothing clears zero on the winning side, so no false positive has
been published — but the instrument as built _will_ produce one, and the page
is written to celebrate it when it does. The two significant losers (`upside`,
`form`) are far enough out that they survive any reasonable correction, so the
current published conclusions stand; the machinery does not.

This is a hole in code written earlier in this same session, which is the
cleanest possible illustration of why the audit is worth doing.

**What to do.** Either Holm-Bonferroni across the family, or report the
comparison as exploratory and say so on the page. Holm is two lines and costs
nothing on the current data.

**Handoff.** `compare_policies` in
`python/fpl_andres/backtesting/captain_significance.py` returns a list of
`PolicyVerdict`. Sort by p-value equivalent (use the bootstrap tail mass), apply
Holm, set `better` only where it survives. Add a `family_size` field so the page
can say how many comparisons were made.

---

## A6. The percentile bootstrap under-covers; BCa is the right tool

**Score 6. Owner decision.**

`models/promotion.py::_improvement_interval` uses the raw percentile bootstrap.
For a paired mean difference on a skewed distribution — which captain points
emphatically are, being a mixture of 2s and 20s — the percentile interval has
real coverage below nominal, typically 88–92% at a nominal 95%.

The `seed_replicates` unanimity requirement is protection against Monte-Carlo
noise across seeds. It is not protection against the estimator's bias, which is
systematic and does not average out across seeds.

Rated 6 rather than 9 because the current conclusions are not close to the
boundary: `template` at +0.15 with an interval of −0.34 to +0.69 is nowhere near
significant under any interval, and `form` at −1.57 is nowhere near
non-significant. Bias-correction changes neither. It matters when a genuinely
marginal candidate arrives, which is precisely when it will be trusted most.

**Handoff.** Implement BCa in `models/promotion.py` alongside the percentile
method, keep both, and report which was used. The acceleration constant needs a
jackknife over the paired differences.

---

## A7. Rank correlation over the whole pool is not a decision anybody makes

**Score 7. Do.**

The calibration page leads with pooled Spearman across the whole player pool.
The repo already knows this is Simpson's-paradox bait — the model loses pooled
and wins in 28 of 28 season-position cells, and both are reported, which is
good practice.

The deeper problem is that neither number is a decision. Nobody sorts 600
players. The decision is: _given these fifteen, this bank and this free
transfer, what do I do?_ The only instrument that measures that is the
mini-league, and it runs 20 managers over 5 seeds against three deliberately
weak policies.

A ranking metric that matched the decision would be **top-of-pool precision
under a budget constraint**: of the players the model would actually recommend
buying at each price point, what share outperformed the alternative at that
price point. That is computable from the existing corpus and is much closer to
the thing being claimed.

---

## A8. The baselines are weak and the strong comparator is unreachable

**Score 5. Owner decision.**

`recent_mean` is a genuinely strong baseline for the reason the repo gives:
`total_points` already contains all fourteen routes, perfectly weighted. Beating
it is real work.

But the mini-league baselines are not: `hold` never transfers, `form_chaser`
buys last week's top scorer, `crowd` follows ownership. Beating a manager who
never transfers is not evidence of anything. The real competitor is the
template, played competently, and the template is _good_ — it is the aggregate
of millions of decisions.

The genuine external comparators (FPL Review, FPL Kiwi) are unreachable:
`robots.txt` explicitly refuses, and the second domain no longer resolves. That
is a hard constraint and the repo respects it correctly.

**What can still be done.** A "competent template" policy — own the most-owned
XV, captain the most-owned, take a free transfer toward the most-owned each
week — is buildable from the corpus and is a much harder baseline than the three
that exist. Rated 5 rather than higher because `crowd` already approximates it.

---

## A9. Captaincy is a right-tail bet priced with a point estimate

**Score 8. Do.**

The captain multiplier means the quantity that matters is not `E[X]` but
`E[2X]`, and since the doubling is linear those are the same ordering — which
is the argument the methodology page makes, and it is correct as far as it goes.

It stops one step short. A manager does not choose a captain to maximise
expected points in isolation; he chooses under a _rank_ objective (A1), and
under a rank objective the shape of the distribution is decisive. Doubling a
player whose distribution is `{2 with p=0.6, 15 with p=0.4}` is a different
decision from doubling one at a flat 6.8, even though the means are equal.

The repo has the raw material — `ceiling_ratio`, `PointsShape`,
`describe_shape` in `backtesting/reliability.py` — and the `ceiling_and_fixture`
policy uses it. But there is no predictive distribution, only a ratio, and the
policy scored _below_ the plain projection.

**What to do.** Produce a predictive distribution per player per gameweek from
the component model — the routes are already Poisson-ish and the pieces exist in
`models/expected_points.py` (orphaned, analytic, closed-form
`E[floor(X/d)]`). Then captaincy policies can be scored on `P(haul > k)` rather
than on a ratio.

---

## A10. The captaincy shortlist makes two policies measure the opposite of their thesis

**Score 7. Do.**

`SHORTLIST_SIZE = 25`, most-owned first. Every policy picks from that set.

The justification is sound and well argued: given the whole pool a policy would
captain the week's cheapest hat-trick and report skill at a decision nobody
faced. Constraining to a realistic pool is right.

But `differential` — "captain the player the field does not own" — is being
made to choose among the **twenty-five most-owned players in the game**. Its
measured mean is not the value of a differential strategy; it is the value of
preferring the 25th-most-owned over the 1st. `template` has the mirrored
problem, and `ceiling_and_fixture` never sees the low-owned high-ceiling punt
that is the entire point of a ceiling bet.

The table reports these under their thesis names as if they had been tested.
They have not been. This is the same class of error as the ownership-scaling
bug that already collapsed two policies into "most owned" and "least owned" —
plausible numbers measuring the wrong thing.

**What to do.** Score the ownership-sensitive policies on a second, wider
shortlist (say the top 60 by projected points regardless of ownership) and
publish both. Where the two disagree, the shortlist was doing the work.

---

## A11. Transfers are priced on one gameweek

**Score 8. Do.**

`simulation/minileague_policies.py::_take_transfers` authorises a −4 hit when
this gameweek's projected gain exceeds 4. A transfer buys a player for the rest
of the season.

The consequence runs both ways: the policy refuses a move worth 3 points a week
for five weeks (15 for a cost of 4), and accepts one worth 5 points once and
nothing after. This is the single most common mistake real managers make, and
the simulation encodes it as the advised policy's behaviour.

`project_horizon` exists and produces exactly the multi-week number needed. The
mini-league does not call it.

---

## A12. Team value is not modelled, and it compounds

**Score 7. Do.**

`docs/LIMITATIONS.md`: "Squad value and price changes. Not modelled at all."

For a project whose central artifact is a **38-gameweek season plan**, this is a
large hole. Team value is not decoration; it is the constraint that determines
which squads are reachable in gameweek 20. A manager 3.0m up on the field has a
strictly larger feasible set. The season plan solves a budget-constrained MILP
with a budget that never moves.

The repo correctly refuses to _predict_ price changes — the mechanism is
unpublished and guessing thresholds would be inventing a rule. That refusal does
not require ignoring value entirely. Two things are available without any
prediction:

- Realised price changes are in the corpus. The backtest can carry value
  correctly even if it cannot forecast it. `simulation/valuation.py` already
  does sell-at-half-profit; the season plan does not use it.
- The _option value_ of a rising player can be stated qualitatively without a
  threshold model.

---

## A13. Chips are heuristic and worth a lot of points

**Score 6. Owner decision.**

`simulation/chips.py::plan_chips` picks chip weeks from fixture counts and a
squad-value floor. The optimiser contracts hard-refuse `chip_scenario != "none"`
at the schema layer.

Four chips across a season are plausibly worth 80–150 points. Deciding them by
fixture count is leaving a decision the project claims to be about — season-long
planning — to a heuristic while the MILP sits idle. The refusal is defended in
`docs/LIMITATIONS.md` on the grounds that chip optimisation needs calibrated
outcome distributions, which is honest and is also A9's problem.

Rated 6 not 9 because it is downstream of A9: without a predictive distribution,
a chip optimiser would be optimising the wrong object anyway. Do A9 first.

---

## A14. "Share of ceiling" uses a hindsight ceiling and reads as failure

**Score 4. Owner decision.**

Captaincy is reported against the best realised return on the shortlist.
Nobody achieves that; it requires knowing the outcome. Reporting "46% of the
ceiling" invites the reader to conclude the model is poor when the denominator
is unattainable by construction.

A more informative denominator is the best _expected_ return on the shortlist,
which is a decision that was actually available. Publish both: the gap to the
expected-optimal is skill, the gap from expected-optimal to realised-optimal is
variance. Splitting them says which part is addressable.

Rated 4 because the current presentation is explicitly explained on the page and
is not misleading to an attentive reader. It is a clarity improvement, not a
correctness one.

---

## A15. The prose is better than the evidence, and that is a risk in itself

**Score 6. Do.**

This is a criticism of the writing, and it is meant seriously.

The documentation in this repository is unusually good — precise, self-critical,
and willing to record failures. That quality does work that evidence should be
doing. A reader encountering "measured over 127 paired gameweeks" and a
confident paragraph about paired bootstraps will reasonably assume the
underlying instrument is sound. Several of the findings above show it is not:
the metric describes a model that does not ship (A2), the constants were tuned
on the scored seasons (A4), and two of the ten policies measure something other
than their name (A10).

The specific mechanism to worry about: `Methodology.tsx` contains at least
**five blocks of hardcoded quantitative claims** — 7.5%, 34,383 vs 34,382,
0.616/0.605/0.646, 0.012/0.019/0.020, 15.45 and 7.12 — none of which is derived
from the artifact beside them. The repo has been bitten by exactly this before:
the calibration page claimed the naive baseline was winning for months after the
artifact had reversed. `state/validation-verdict.ts` exists because of it.

**What to do.** Every number in prose is either derived from the artifact at
render time or carries the commit and date it was measured at. Prefer the first.

---

## A16. What is genuinely good, and should not be "improved"

Recording this because an audit that only lists faults distorts the picture, and
because two of these are load-bearing enough that changing them would be a
regression.

- **The reconciliation.** Rebuilding realised points from component columns and
  matching FPL's own total to one point in 34,383 is the strongest single piece
  of evidence in the project. It proves the scoring table is right, which is the
  foundation everything else stands on. Keep it, keep publishing it.
- **Fail-closed on missing controlling rules.** `rules_for()` refusing an
  unrecorded season, `positions.py` refusing an unknown element type, the
  contract errors on missing timestamps. This is the right instinct and it is
  applied consistently.
- **The orphan ratchet.** `test_reachability.py` is an unusual and excellent
  idea: it makes dead capability visible instead of letting it rot silently. It
  is how most of this audit's section C was found.
- **Recording negative results.** The positional-matchup investigation was
  closed as "signal does not persist half-to-half" rather than quietly dropped.
  The cohort persistence measurement refuses rather than reporting a
  selection-biased number. Both are better science than most of what gets
  published.
- **The evidence-level system.** Attaching `EvidenceLevel` and source timestamps
  to every projection, and downgrading rather than defaulting, is the right
  architecture for a project whose main risk is quietly inventing data.
