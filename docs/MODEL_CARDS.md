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

## Walk-forward evaluation

Each UTC prediction cutoff creates three deterministic buckets:

- `train`: played fixtures whose bytes were available by the cutoff;
- `holdout`: fixtures kicking off after the cutoff;
- `rejected_leaks`: played fixtures whose bytes arrived after the cutoff.

Cutoffs must be strictly increasing. Equality at the evidence timestamp is available.
Evaluation pairs baseline and candidate errors on the same holdout observations.

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
