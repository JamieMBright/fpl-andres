# Projection Model Cards

These cards govern team goal-rate models. They describe implemented behavior, not a
claim that a model is accurate enough for recommendations. No candidate is active in
the product until a persisted walk-forward evaluation passes the promotion gate.

## Evidence labels

- `observed`: a fact present in source evidence, such as a completed score.
- `inferred`: a transparent deterministic calculation from observed evidence.
- `experimental`: an unpromoted model output under evaluation.
- `unavailable`: the required evidence or controlling rule is missing.

An expected-goal output is never itself an observed fact. Every prediction retains the
newest `data_available_at` timestamp and the unique content hashes of all training rows.

## Model registry

| Identity              | Role                   | Output label   | Product status         |
| --------------------- | ---------------------- | -------------- | ---------------------- |
| `league_venue_mean/1` | Required benchmark     | `inferred`     | Backtest baseline only |
| `team_venue_rates/1`  | Transparent candidate  | `experimental` | Not promoted           |
| `dixon_coles/1`       | Time-decayed candidate | `experimental` | Not promoted           |
| `deployment_signal/1` | OOP role classifier    | source-bound   | Context/watchlist only |

### League venue mean / 1

**Purpose.** Establish the minimum benchmark a candidate must beat. Home and away
expected goals are the separate arithmetic means of observed home and away scores in
the requested season.

**Inputs.** Completed same-season fixtures. At least one fixture is required. The model
does not use team identity, form, player availability or future fixtures.

**Failure behavior.** Empty or mixed-season training data fails. This benchmark can
predict unseen teams because it deliberately contains no team effect.

### Team venue rates / 1

**Purpose.** Provide an inspectable team-aware candidate. A home prediction averages
the home team's home scoring rate with the away team's away concession rate. The away
prediction mirrors that calculation.

**Inputs.** Completed same-season fixtures and an explicit per-component venue sample
floor. All four attack/concession components must meet the floor.

**Known limits.** Raw means have no shrinkage and are unstable in small samples. Home
and away splits discard information. The candidate fails for unseen or under-sampled
teams and remains `experimental` unless it passes promotion.

### Dixon-Coles / 1

**Purpose.** Estimate attack, defence and home-advantage parameters by maximizing a
time-weighted Poisson score likelihood with the Dixon-Coles low-score correction.

**Inputs.** Completed same-season fixtures; an aware UTC fit cutoff; decay rate per
day; minimum team appearance count; and optimizer iteration limit. Every row must have
become available at or before the fit cutoff. The latest sorted team is the fixed
reference attack parameter, and bounded L-BFGS-B optimization is deterministic for
identical bytes and parameters.

**Outputs.** Positive home and away goal rates plus the fitted low-score `rho`, decay
rate, match count, evidence timestamp and exact source hashes. `rho` informs fitting;
the public rates are the fitted Poisson intensities.

**Failure behavior.** Invalid cutoffs or parameters, mixed seasons, late-arriving rows,
under-sampled teams, unseen prediction teams and optimizer failure all stop the model.
There is no silent fallback to a candidate estimate.

**Known limits.** The model sees scores, venue and recency only. It has no player,
injury, lineup, tactical, event or market features. Bounds stabilize optimization but
do not establish calibration. A successful fit is not evidence of predictive gain.

### Deployment signal / 1

**Purpose.** Compare official FPL scoring position with a sourced on-pitch role. A
defender deployed in a midfield/forward role emits `lord_lundstram_effect`; movement in
the other direction emits `reverse_oop`. The output is a watchlist/context signal, not
a direct points adjustment.

**Inputs.** Historical role window, starts observed, explicit minimum starts, source
reference/hash, availability cutoff and method. Declared lineup roles may be observed.
Manager observations are inferred. Heatmap clusters require rights-cleared data,
confidence and model version and remain inferred/experimental.

**Scoring behavior.** Official FPL position remains the scoring position. The role can
inform attacking-event probabilities, while listed-position goal and clean-sheet rules
are applied once by the scoring engine. A fixed OOP bonus is prohibited because it
would double-count role effects already present in attacking projections.

**Failure behavior.** Late/current-event evidence raises a leakage error. Samples below
the explicit starts floor emit `unavailable`. Missing source/method metadata fails the
contract.

**Recency requirement (blocks live OOP).** The current fixed-window classifier is a v0
approximation and must be superseded before live OOP evidence fires. The v1 contract
requires per-event role observations across the decision window carrying kickoff
timestamp, minutes played and role probability. Weighted starts apply an exponential
decay whose half-life is sourced (for example, two played gameweeks), so the last few
played events dominate the classification. A regime-change check compares the most
recent contiguous role run to the prior window; a decisive reversion downgrades the
signal to `unavailable` rather than emitting a stale `attacking_oop` or `reverse_oop`.
Historical open-data corpora used only to validate the classifier are exempt from the
recency check because they cover completed seasons rather than the live sequence.

## Walk-forward evaluation

Each UTC prediction cutoff creates three deterministic buckets:

- `train`: played fixtures whose bytes were available by the cutoff;
- `holdout`: fixtures kicking off after the cutoff;
- `rejected_leaks`: played fixtures whose bytes arrived after the cutoff.

Cutoffs must be strictly increasing. Equality at the evidence timestamp is available.
Evaluation pairs baseline and candidate errors on the same holdout observations.

## Measured performance

Targets were never written down, so the target is the thesis:
beat the baselines a competent human actually uses. Numbers below are from
`apps/web/src/data/validation.json`, the artifact the calibration page serves.

Walk-forward across four seasons, ~11,900 scored predictions each. `recent_mean`
is the form chaser; `ownership` is the crowd.

The two tables below are regenerated by `fpl_andres.cli.track_model` on every
backtest run. Editing them by hand is how the last set went stale.

<!-- measured-performance:start -->

| Season  | MAE   | vs form | Spearman | vs form | Top-20 hit | form  | crowd | Bias   |
| ------- | ----- | ------- | -------- | ------- | ---------- | ----- | ----- | ------ |
| 2022-23 | 1.765 | −6.5%   | 0.497    | +0.051  | 0.189      | 0.153 | 0.176 | −0.089 |
| 2023-24 | 1.715 | −7.3%   | 0.511    | +0.047  | 0.208      | 0.167 | 0.177 | −0.096 |
| 2024-25 | 1.675 | −7.2%   | 0.508    | +0.042  | 0.192      | 0.148 | 0.166 | −0.108 |
| 2025-26 | 1.865 | −6.4%   | 0.467    | +0.044  | 0.169      | 0.119 | 0.136 | −0.067 |

<!-- measured-performance:end -->

**The model beats the form chaser on all three metrics in all four seasons, and
beats the crowd's top-20 hit rate in all four.** The margin is stable rather than
large: 7–10% on error, about 0.04 on rank correlation.

Three things this does not say.

**Bias is negative in every season.** The model under-predicts by 0.11 to 0.20
points per player per gameweek, consistently. That is a systematic error, not
noise, and it is the clearest open lead in the calibration: something in the
scoring composition is not being credited. The form chaser's bias is near zero
because a mean of recent scores cannot be biased against itself.

**2025-26 is the worst season on every metric.** MAE is 0.19 higher than 2024-25
and rank correlation 0.04 lower. Defensive contribution points arrived that
season and the model had no history to fit them against, which is the obvious
explanation and not a verified one.

**Rank correlation is worst where the squad is largest.** In 2025-26: GKP 0.589,
FWD 0.553, MID 0.481, DEF 0.425. Defenders are the hardest to rank and there are
five of them in a squad, so the weakest part of the model carries the most weight
in a selection.

Reproducing these numbers needs the corpus they were measured over, not just the
code — see `corpusFingerprint` in the artifact.

### The unblended projection is scored separately

`recent_mean` is both the naive baseline and 20% of the projection, so the
comparison above is a superset against its own component and cannot fully fail.
`backtesting/score.py` therefore scores a fourth ranking, `components`: the same
projection with `_blend` removed. If `components` does not beat `recent_mean`,
the fourteen-route pricing is not carrying itself and the lead above is the naive
term the model is wrapped around.

The method was computed and discarded before it reached the artifact until
2026-08-05. Artifacts generated before that date carry three methods, not four,
and the calibration page says so rather than showing a blank column.

### Captaincy

`backtesting/captaincy.py`. The captain doubles, so one call per gameweek carries
two to three times the expected-value impact of a routine transfer — the
reasoning is standard across the practitioner literature and is why it is scored
on its own rather than folded into the pooled rank correlation.

Every method captains from the same shortlist: the 25 most-owned players going
into that gameweek, from ownership at the previous gameweek. Captaining from the
whole pool would grade a decision nobody faces. The ceiling is the best captain
_inside that shortlist_, so the reported regret is a call a manager could have
made.

Reported per season and per method: gameweeks scored, mean realised points of the
captain, mean points of the best available, regret per gameweek, share of the
ceiling, weeks the pick was the best available, and blank rate (two points or
fewer). Figures are the player's own score, not the doubled one — doubling is a
constant on every method and on the ceiling, so it changes no ordering, and a gap
is worth twice what it reads over a season.

<!-- captaincy:start -->

| Season  | Method        | Weeks | Captain | Best available | Left behind | Nailed it | Blanked |
| ------- | ------------- | ----- | ------- | -------------- | ----------- | --------- | ------- |
| 2022-23 | `model`       | 31    | 7.26    | 15.45          | 8.19        | 2         | 0.29    |
| 2022-23 | `components`  | 31    | 7.81    | 15.45          | 7.64        | 5         | 0.26    |
| 2022-23 | `recent_mean` | 31    | 5.74    | 15.45          | 9.71        | 3         | 0.35    |
| 2022-23 | `ownership`   | 31    | 6.74    | 15.45          | 8.71        | 2         | 0.39    |
| 2023-24 | `model`       | 32    | 5.72    | 15.41          | 9.69        | 3         | 0.34    |
| 2023-24 | `components`  | 32    | 4.97    | 15.41          | 10.44       | 2         | 0.41    |
| 2023-24 | `recent_mean` | 32    | 4.91    | 15.41          | 10.50       | 2         | 0.50    |
| 2023-24 | `ownership`   | 32    | 5.81    | 15.41          | 9.59        | 4         | 0.47    |
| 2024-25 | `model`       | 32    | 8.22    | 14.53          | 6.31        | 8         | 0.28    |
| 2024-25 | `components`  | 32    | 7.94    | 14.53          | 6.59        | 8         | 0.28    |
| 2024-25 | `recent_mean` | 32    | 6.69    | 14.53          | 7.84        | 5         | 0.34    |
| 2024-25 | `ownership`   | 32    | 7.78    | 14.53          | 6.75        | 8         | 0.38    |
| 2025-26 | `model`       | 32    | 5.22    | 13.50          | 8.28        | 4         | 0.41    |
| 2025-26 | `components`  | 32    | 5.56    | 13.50          | 7.94        | 4         | 0.38    |
| 2025-26 | `recent_mean` | 32    | 4.09    | 13.50          | 9.41        | 2         | 0.53    |
| 2025-26 | `ownership`   | 32    | 5.16    | 13.50          | 8.34        | 6         | 0.53    |

<!-- captaincy:end -->

### Competing captaincy theses

`backtesting/captain_policies.py`. The practitioner sources agree that taking
the highest projected scorer is not how the decision is made, and agree on
almost nothing else: one says take the form, one the crowd's pick, one the
differential, one shrinks a score by its own uncertainty. Each is stated without
a measurement, so all of them are scored on the same weeks and the same
shortlist.

Nine policies, each a different family rather than a variant. Tuning a
coefficient inside one and calling the result a new thesis would be fitting four
seasons of about 127 gameweeks; where a coefficient is unavoidable it is taken
from the source that proposed it, once, and never swept.

| Thesis                  | Maximises                        | Source                            |
| ----------------------- | -------------------------------- | --------------------------------- |
| `expected_points`       | the projection                   | what this project already did     |
| `components`            | the projection without the blend | the unblended control             |
| `availability_adjusted` | projection × P(start)            | Oracle step 5, rotation risk      |
| `upside`                | projection + one deviation       | the multiplier is a tail bet      |
| `robust`                | projection − one deviation       | Ramezani and Dinh, robust variant |
| `form`                  | recent scoring, floor at 2.0     | FPL360                            |
| `crowd`                 | ownership                        | the template; Bhatt 2019          |
| `differential`          | projection − 1.5 per 100% owned  | Oracle step 3, climbing           |
| `template`              | projection + 1.5 per 100% owned  | Oracle step 3, protecting         |
| `ceiling_and_fixture`   | ceiling × fixture multiplier     | the owner's own rule              |

`ceiling_and_fixture` is a product rather than a filter: a big enough ceiling
tolerates a harder fixture, an ordinary one needs a kind draw. No separate home
term is applied, because venue is already measured inside the attacking
multiplier and adding it twice would outrank the ceiling it is meant to modify.

Ownership reaches a policy rescaled to 0–100 against the most-owned player of
that gameweek. Model 2.1 handed it the raw `selected` count — of the order of a
million — so the ownership term swamped every projection and `template` reduced
to `crowd` while `differential` reduced to "captain the least owned of the
twenty-five". Both scored, both were reported, and neither was the thesis it
claimed to be. `test_the_rank_policies_have_not_collapsed_into_the_crowd` now
fails if either does it again.

Both halves of the rank rule are scored because the backtest has no rank to
condition on. A policy that is right only for managers in one league position
must not be reported as right in general.

Nothing here excludes a premium the whole field owns. Seven of the nine take the
best player on the shortlist when he is also the most owned, and only
`differential` declines — a framework that could never captain Haaland would be
answering a different question.

#### Why the table below has an interval column

A ranked table of ten means always produces a winner, whether or not one exists.
Model 2.2 fixed a single arithmetic error in the ownership term and the top of
the order changed — which is what a lead inside the noise looks like from the
outside.

So every thesis is now paired against the projection week for week across all
scored gameweeks of every season, and the differences are resampled 2,000 times
(`backtesting/captain_significance.py`). The interval is the 95% percentile
interval on the mean paired difference. A thesis is only reported as better when
the whole interval sits above zero; `better` is not set by placing first.

Paired rather than pooled, because the two policies play the same fixtures in
the same weeks: a blank gameweek depresses both, and comparing unpaired means
would charge that to whichever one happened to be measured over more of them.

The bootstrap refuses fewer than 32 paired weeks rather than returning a narrow
interval from a short series, and it refuses two series of different lengths
rather than truncating one to fit.

**The measured result, over 127 paired gameweeks: nothing beats the
projection.** Not one interval clears zero. `template` tops the table by 0.15
points a week on an interval of −0.34 to +0.69, so the ordering is inside its
own noise and the two seasons it won are two coin flips. The only findings that
survive are negative: `upside` costs 1.20 a week and `form` 1.57, both with
intervals entirely below zero. Maximising the ceiling and chasing form are
measurably worse than taking the highest projected scorer.

A captain's return can be negative — a red card is −3, an own goal −2 — and
`TripletPrediction` refuses a negative row because the metrics it was built for
are error magnitudes. Both series are therefore lifted by one constant before
the bootstrap. That is exact rather than a workaround: the verdict is built
from a paired difference of means, and a shift common to both cancels out of
the point estimate, the resamples and the interval alike. Only the two reported
means move, by exactly the offset, and they are moved back.

<!-- captain-policies:start -->

| Thesis                  | Mean captain points | Seasons won (of 4) | vs projection (95% CI) |
| ----------------------- | ------------------- | ------------------ | ---------------------- |
| `template`              | 7.03                | 1                  | +0.42 [-0.20, +1.30]   |
| `differential`          | 6.70                | 1                  | +0.10 [-0.66, +0.82]   |
| `robust`                | 6.66                | 1                  | +0.06 [-1.24, +1.28]   |
| `availability_adjusted` | 6.64                | 0                  | +0.04 [-0.27, +0.43]   |
| `expected_points`       | 6.60                | 0                  | baseline               |
| `components`            | 6.57                | 1                  | -0.04 [-0.90, +0.69]   |
| `crowd`                 | 6.37                | 0                  | -0.23 [-1.57, +1.25]   |
| `upside`                | 6.18                | 0                  | -0.42 [-1.87, +0.94]   |
| `ceiling_and_fixture`   | 5.60                | 0                  | -1.00 [-2.54, +0.30]   |
| `form`                  | 5.36                | 0                  | -1.24 [-2.75, +0.22]   |
| `set_and_forget`        | 4.24                | 0                  | -2.35 [-4.05, -0.84]   |

<!-- captain-policies:end -->

#### Why the rule is chosen from a list rather than learned

The obvious next step is to stop picking between ten hand-written rules and fit
the weights instead. It is not taken, and the reason is arithmetic rather than
taste.

The captaincy decision produces **one** graded observation per gameweek. Four
seasons is about 127 of them. A learned policy over the same features the ten
theses use — projection, deviation, start probability, ownership, ceiling,
fixture — is fitting six or more parameters to 127 points whose week-to-week
standard deviation is larger than the entire spread between best and worst
thesis in the table above. Any such fit will report an in-sample lead. It will
report one on shuffled labels too.

The instrument also cannot resolve what would be learned. The whole measured
range from `template` to `form` is under two points a gameweek, and the paired
interval on a single thesis is wider than most of the gaps inside it. Fitting
inside a band the test cannot separate is fitting noise with extra steps.

This is not a permanent refusal. The conditions under which it changes are
written down so the decision can be revisited rather than re-argued:

- a learned policy enters as one more candidate in `CAPTAIN_POLICIES`, scored on
  the same shortlist, in the same weeks, by the same paired bootstrap;
- it is fit on seasons it is not scored on, walk-forward, never on all four;
- it is only adopted if its interval clears zero against `expected_points` —
  the same bar all ten hand-written theses have now failed to clear.

Until then the honest position is that the ceiling is the thing worth chasing,
not the ranking. The best captain available on the shortlist averages 15.45; the
best thesis takes 7.12. Nobody is leaving less than half of it on the table, and
no reweighting of these features closes a gap that size.

### Studying the elite cohort's armband

`cohorts/captain_agreement.py`. A separate question from the one above, and it
is kept separate on purpose: the backtest asks which rule **scores** best, this
asks which rule best **describes** what the top-500 actually captained.

Worth asking because the backtest can only compare rules that were written down
first. A week where all ten theses pick one player and most of the cohort
captained another is evidence that the list of ideas is short, and the residual
names the player to go and look at.

It is not a score, and the module will not be read as one. The cohort is
selected on final rank; selecting on the outcome and then measuring the outcome
is the trap `data/cohort/fpl500.json` already records. A high agreement rate
says a thesis resembles elite behaviour — not that the thesis scores well, and
not that the cohort's captaincy is what made them elite.

The measurement that decides whether the study is worth running at all is
`contestedWeeks`. Captaincy in a top-500 cohort is close to unanimous most
weeks, and a week where 90% of the cohort captains the same player separates no
two theses. Only weeks where the plurality is at or below 50% carry information,
so the agreement rate is reported over those separately. If that count stays
near zero, the honest conclusion is that the armband is not where the cohort's
edge lives, and the study stops.

### What the backtest grades that the live path does not, and the reverse

Named because it is a real gap, not because it is fixed.

| Feature                          | Backtest (`score_season`) | Live (`publish_projections`) |
| -------------------------------- | ------------------------- | ---------------------------- |
| Fourteen-route component pricing | Yes                       | Yes                          |
| Fixture-aware route adjustment   | Yes                       | Not applied (next match)     |
| Team strength                    | Goal averages             | Dixon-Coles + venue tilt     |
| Recent-form blend                | Yes                       | No                           |
| Suspension multiplier            | No                        | Yes                          |
| Live availability                | Structurally impossible   | Yes                          |

The strength row is the one that matters: the backtest grades a **weaker**
strength model than the one that ships. Closing it means fitting Dixon-Coles once
per scored gameweek across four seasons, which has not been costed, so it is
recorded rather than done. Until it is, the measured performance above is a floor
on what the shipped projection does, not an estimate of it.

### Where the method came from

The evaluation design draws on published work rather than being invented here.

- Ramezani and Dinh, _A data-driven framework for team selection in Fantasy
  Premier League_, [arXiv:2505.02170](https://arxiv.org/abs/2505.02170). Source
  of three things used directly: that recency-weighted averages and low-order
  ARIMA are the baselines worth beating, that a hybrid weighted toward the model
  beats one weighted toward realised points, and that captaincy is normally
  handled outside the optimiser and should not be.
- FPL Oracle, _FPL Captaincy Logic_. Source of the shortlist framing: build two
  to four candidates on expected points first, then separate them on effective
  ownership and rank situation. Our shortlist is the crowd's holdings for the
  same reason — it is the pool the decision is actually made from.
- FPL360, _FPL Captaincy Strategy_. Source of the blank-rate column: the cost of
  a captaincy call is felt on the weeks it returns nothing, which a mean hides.

What was **not** taken: FPL360's "never captain a player with form below 2.0" and
its form-first ordering. Form is realised points, and this project already
measures that as the baseline it is trying to beat. Neither source publishes a
measurement of its own framework, so nothing from either is treated as evidence —
only as a design input whose value has to show up in our own backtest.

## Promotion contract

Every promotion run supplies its metric, seed, bootstrap resample count, confidence and
minimum sample size. Bootstrap draws reuse the same sampled indices for baseline and
candidate. For a lower-is-better metric, paired improvement is:

`baseline metric - candidate metric`.

A candidate is promoted only when the sample floor is met and the lower percentile
confidence bound is strictly greater than zero. Equal models, insufficient samples and
intervals touching or crossing zero remain inactive with machine-readable reason
codes. An insufficient sample skips resampling and records zero executed resamples;
eligible evaluations must execute at least one. Current tests use mean absolute error;
selecting the production metric and threshold configuration remains an explicit
evaluation decision, never a code default.

## Persisted audit record

`projection_runs`, `team_goal_projections` and `model_promotion_decisions` are immutable,
forced-RLS tables. They record model identity and configuration, prediction cutoff,
evidence level and timestamps, source hashes, paired interval, seed, resamples, sample
floor and reason codes. The database independently rejects a promoted decision unless
the sample floor is met and the paired lower bound is positive.
