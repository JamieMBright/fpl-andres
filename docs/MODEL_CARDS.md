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

Audit item #195. Targets were never written down, so the target is the thesis:
beat the baselines a competent human actually uses. Numbers below are from
`apps/web/src/data/validation.json`, the artifact the calibration page serves.

Walk-forward across four seasons, ~11,900 scored predictions each. `recent_mean`
is the form chaser; `ownership` is the crowd.

| Season  | MAE   | vs form | Spearman | vs form | Top-20 hit | form  | crowd | Bias   |
| ------- | ----- | ------- | -------- | ------- | ---------- | ----- | ----- | ------ |
| 2022-23 | 1.745 | −10.1%  | 0.492    | +0.045  | 0.187      | 0.148 | 0.176 | −0.202 |
| 2023-24 | 1.718 | −8.2%   | 0.507    | +0.044  | 0.198      | 0.170 | 0.177 | −0.119 |
| 2024-25 | 1.670 | −8.0%   | 0.507    | +0.041  | 0.188      | 0.142 | 0.166 | −0.126 |
| 2025-26 | 1.857 | −7.4%   | 0.465    | +0.043  | 0.148      | 0.116 | 0.136 | −0.114 |

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
code — see `corpusFingerprint` in the artifact and audit item #153.

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
