# 2. Numerical and statistical rigour — work orders

Detailed briefs for items 19–32 of the [improvement audit](../../IMPROVEMENTS.md).
Each brief is self-contained: a sub-agent should be able to implement one item
from its brief alone.

Every brief obeys the repository rules: test-first (failing focused test, minimal
code, refactor), never default a missing controlling FPL rule (fail the source
contract visibly), keep `EvidenceLevel` and source timestamps attached to
recommendations, and nothing may exceed `docs/LIMITATIONS.md`.

---

## 19 — Replace the `1e12` penalty sentinel in `models/dixon_coles.py` (Impact: H)

**Files**: `python/fpl_andres/models/dixon_coles.py`
(`DixonColesModel.fit`, objective closure, lines 82–111, specifically line 98),
`python/tests/test_dixon_coles.py`

**Problem**: the `objective` closure inside `DixonColesModel.fit` returns `1e12`
when `_low_score_adjustment` is non-positive (line 97–98). This sentinels an
infeasible likelihood evaluation, but `scipy.optimize.minimize` with `L-BFGS-B`
interprets a finite return value as a valid (if very large) function value. The
optimiser will follow the gradient away from `1e12` toward the boundary, which
distorts the search surface in the neighbourhood of the constraint — L-BFGS-B
will attempt to fit the slope of the `1e12` cliff rather than ignoring the region.
The correct response is to signal infeasibility explicitly so the optimiser skips
the region, not to inject a large finite number.

**Change**:

1. Replace the `return 1e12` at line 98 with `return math.inf`. `scipy.optimize`
   with `L-BFGS-B` treats `inf` as a signal that the point is outside the
   feasible domain and does not attempt to differentiate through it.
2. Alternatively, add a guard before the `if adjustment <= 0` check: clamp `rho`
   to a domain where `_low_score_adjustment` is always positive given the
   `bounds` on `rho` (`(-0.2, 0.2)` at line 79). If the bounds already prevent
   `adjustment ≤ 0` in practice, add a comment documenting this; if they do not,
   tighten the bound.
3. If `math.inf` is used, remove the `1e12` constant and add a note in the
   docstring of `fit` that the objective uses `math.inf` for infeasible
   adjustments.

**Constraints**: do not change the Dixon-Coles model structure or the
`_low_score_adjustment` formula. Do not suppress `ModelFitError` — it must still
fire on convergence failure (line 120). The fix must not make the optimisation
slower in the typical case where `adjustment > 0`.

**Tests first**: add `test_infeasible_adjustment_does_not_produce_finite_penalty`
to `test_dixon_coles.py` that constructs a parameter vector where
`_low_score_adjustment` would be ≤ 0 (e.g. `rho = -1.0`, `home_goals = 0,
away_goals = 0`, `home_rate = away_rate = 1.0`: adjustment `= 1 - 1 * 1 * (-1)
= 2 > 0`; try `rho = 2.0` outside bounds to produce `adjustment ≤ 0`), calls the
objective function directly (as an extracted helper or via inspection), and
asserts the return is `math.inf`, not `1e12`.

**Done when**:

- `1e12` does not appear in `dixon_coles.py`.
- The optimiser still converges on valid training data (existing tests pass).
- `_low_score_adjustment <= 0` returns `math.inf` from the objective.

**Validate**: `python -m pytest python/tests/test_dixon_coles.py -q`

---

## 20 — Fix bootstrap confidence bound indexing in `models/promotion.py` (Impact: H)

**Files**: `python/fpl_andres/models/promotion.py` (`_bootstrap_result`, lines
193–215), `python/tests/test_model_promotion.py`

**Problem**: `_bootstrap_result` computes the confidence interval as:

```
tail = (1 - confidence) / 2
lower_index = max(0, math.floor(tail * resamples))
upper_index = min(resamples - 1, math.ceil((1 - tail) * resamples) - 1)
```

(lines 203–205). For `confidence = 0.95` and `resamples = 1000`, `tail = 0.025`,
`lower_index = floor(25.0) = 25`, `upper_index = min(999, ceil(975.0) - 1) = min(999,
974) = 974`. This is correct. However for small `resamples` — e.g.
`resamples = 40`, `confidence = 0.95` — `tail = 0.025`, `upper_index =
min(39, ceil(39.0 * 0.975) - 1) = min(39, ceil(38.025) - 1) = min(39, 39 - 1)
= 38`, which is the 95th percentile of 40 samples — but `ceil(38.025) = 39`,
so `upper_index = 38` instead of using the nearest quantile. The bias is small
at large resample counts but can reach a full percentile rank at small counts
(e.g. `resamples = 10`, where rounding errors decide the bound). The standard
approach is to compute the quantile with explicit interpolation rather than
index arithmetic.

**Change**:

1. Replace the `ceil(...) - 1` index formula with `numpy.quantile(ordered, 1 -
tail)` for the upper bound and `numpy.quantile(ordered, tail)` for the lower
   bound, using the default `'linear'` interpolation method. This is the
   statistically correct approach for a percentile bootstrap.
2. Remove the `math.ceil` and `math.floor` index computation; the `ordered = sorted(samples)` list
   can be converted to a numpy array for the `quantile` call.
3. Update `BootstrapResult.lower` and `.upper` to be set from the `quantile`
   output.

**Constraints**: `numpy` is already a dependency (used in `optimization/highs.py`
and `optimization/horizon.py`). Do not change the `BootstrapResult` dataclass
fields. Do not change the `confidence` semantics (a value of 0.95 means a 95%
interval). The `_degenerate_result` function (lines 218–234) must remain
unchanged.

**Tests first**: add `test_bootstrap_upper_bound_correct_at_small_resamples` to
`test_model_promotion.py`, constructing 20 deterministic samples (e.g. integers 0
through 19), calling `_bootstrap_result` with `confidence=0.9` and `resamples=20`,
and asserting the upper bound equals `numpy.quantile(range(20), 0.95)`.

**Done when**:

- `math.ceil` and `math.floor` index arithmetic no longer appear in
  `_bootstrap_result`.
- The upper bound matches `numpy.quantile(sorted_samples, 1 - tail)` for
  arbitrary `resamples` values.
- All `test_model_promotion.py` tests pass.

**Validate**: `python -m pytest python/tests/test_model_promotion.py -q`

---

## 21 — Justify or source the Poisson truncation limit in `models/expected_points.py` (Impact: H)

**Files**: `python/fpl_andres/models/expected_points.py` (`_POISSON_TRUNCATION`,
line 38; `_expected_floor_divide`, lines 251–260),
`python/fpl_andres/models/contracts.py`,
`python/tests/test_expected_points.py`

**Problem**: `_POISSON_TRUNCATION = 15` (line 38) is a bare module-level constant
with only the comment `"Poisson tail beyond this contributes less than
floating-point noise."` For a Poisson rate of `λ = 3` (a busy forward in a week
with two fixtures), `P(X > 15) ≈ 1.5e-8`, which is indeed negligible. However
for higher rates — e.g. a team facing two fixtures with `xG = 4` each, giving
`λ = 4` — `P(X > 15) ≈ 3e-6`, still small. But the comment "floating-point noise"
is imprecise: it is the contribution to the floor-divide expectation, not to the
PMF, that must be noise. Additionally, as a bare constant with no source
reference, a reviewer cannot verify it is appropriate without recomputing.

**Change**:

1. Add a function `_poisson_truncation_error(rate: float, truncation: int) ->
float` that computes the tail mass `sum(poisson.pmf(k, rate) * (k // divisor)
for k in range(truncation+1, truncation+100))` for a given divisor. This is
   used only in the docstring example and in the new test.
2. Expand the comment on `_POISSON_TRUNCATION` to: (a) name the maximum
   `expected_goals_conceded` value accepted by `TeamMatchContext` (15.0, from
   `models/contracts.py`), (b) show that `P(X > 15 | λ = 15)` is below the
   tolerance of the floor-divide sum, and (c) state that the constant must be
   re-evaluated if the `TeamMatchContext.expected_goals_conceded` bound is
   increased.
3. Record the truncation limit and its justification in `docs/MODEL.md` under
   "Expected points model", so it is visible to reviewers without reading the
   source.

**Constraints**: do not change the numerical value of `_POISSON_TRUNCATION`
unless the analysis in step 2 shows it is insufficient. The constant must not be
sourced from an external API — it is a numerical convergence parameter intrinsic
to the model. Do not make it a field on any contract model.

**Tests first**: add `test_poisson_truncation_tail_mass_below_tolerance` to
`test_expected_points.py`, asserting that for `rate = 15.0` (the maximum
`expected_goals_conceded`) and `divisor = 2`, the tail mass above
`_POISSON_TRUNCATION` is below `1e-6`.

**Done when**:

- The comment on `_POISSON_TRUNCATION` cites the `TeamMatchContext` upper bound
  and the tail mass at that bound.
- `docs/MODEL.md` documents the truncation decision.
- The new test passes.
- All existing `test_expected_points.py` tests pass.

**Validate**: `python -m pytest python/tests/test_expected_points.py -q`

---

## 22 — Fail loudly when recency decay underflows to zero in `models/minutes.py` (Impact: H)

**Files**: `python/fpl_andres/models/minutes.py` (`project_minutes`, lines
140–244; total-weight guard, lines 173–176),
`python/tests/test_minutes_model.py`

**Problem**: when `total_weight <= 0.0` (line 174), `project_minutes` appends
`"recency_weights_vanished"` to reasons and calls `_unavailable`, returning a
projection with `evidence_level = "unavailable"` and zero expected minutes. This
is correct behaviour when all weights genuinely vanish — but the current check
cannot distinguish between (a) a legitimate out-of-window observation where the
decay truly approaches zero, and (b) a data error where `prediction_event` is
less than every `observation.event_id`, making all exponents negative and all
weights less than 1 but still positive. The `_reject_future_evidence` guard (line 311) prevents observations from _equalling or exceeding_ `prediction_event` but
does not prevent an observation from being very close to it, yielding a weight
near zero but not zero.

The audit says "fail loudly when recency decay underflows to zero" — meaning: the
`"recency_weights_vanished"` path is acceptable as a graceful degradation _only
if_ the weight sum is the result of legitimate far-future observations. If
observations are within the expected window and the weight sum is still zero, that
is a numerical anomaly that should raise, not silently degrade.

**Change**:

1. Before `_reject_future_evidence`, add a check: if
   `evidence.minimum_observations > 0` and `len(evidence.observations) >=
evidence.minimum_observations` (i.e. the sample floor is met) but
   `total_weight <= 0.0` despite all observations being within the valid window,
   raise `FutureMinutesEvidenceError` (reusing the existing error type) with the
   message `"all recency weights underflowed to zero despite a sufficient sample;
verify prediction_event and observation event_ids"`.
2. The legitimate zero-weight path — which occurs when `decay_half_life_events` is
   very small and observations are old — should still return `_unavailable`. Gate
   the raise on: the weight underflowed AND all observations are within the decay
   window (i.e. `prediction_event - max(event_id) < 2 * decay_half_life_events`).

**Constraints**: do not remove the `"recency_weights_vanished"` path — it is
correct for far-out-of-window observations. The change is a tighter diagnostic in
the anomalous case. `FutureMinutesEvidenceError` is the correct error type (it
signals the evidence structure is inconsistent).

**Tests first**: add `test_underflow_raises_when_observations_in_window` to
`test_minutes_model.py`, constructing `MinutesEvidence` with observations within
two half-lives of `prediction_event` but with an artificially tiny
`decay_half_life_events` that causes underflow, and asserting
`FutureMinutesEvidenceError` is raised. Add `test_underflow_returns_unavailable_when_far_out_of_window`
for the legitimate out-of-window case.

**Done when**:

- In-window underflow raises `FutureMinutesEvidenceError`.
- Out-of-window underflow returns `evidence_level = "unavailable"`.
- All existing `test_minutes_model.py` tests pass.

**Validate**: `python -m pytest python/tests/test_minutes_model.py -q`

---

## 23 — Clamp the normal CDF output in `planning/effective.py` (Impact: M)

**Files**: `python/fpl_andres/planning/effective.py` (`RankModel.share_below`,
lines 53–56; `RankModel.rank_of`, lines 58–60),
`python/tests/test_effective_points.py`

**Problem**: `share_below` returns `0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))`
(line 56). `math.erf` is documented to return values in `[-1.0, 1.0]` but for
extreme positive `z` (large positive points gap) it returns exactly `1.0`,
making `share_below = 1.0` and `(1.0 - share_below) * field_size = 0.0`. The
`max(1.0, ...)` guard in `rank_of` (line 60) then correctly returns `1.0`.
However, floating-point arithmetic at intermediate stages can occasionally produce
`erf(z) = 1.0 + ε` where `ε` is a sub-ULP rounding artefact, making
`share_below > 1.0` and `rank_of < 1.0` (a rank below 1 is meaningless — there
is no rank 0). The `max(1.0, ...)` guard handles the `> 1.0` case for `rank_of`
but `share_below` itself can still return a value slightly above 1.0, which
appears in `places_gained` as a negative places gain when the margin is tiny.

**Change**:

1. Clamp `share_below` to `[0.0, 1.0]` by wrapping the return with
   `max(0.0, min(1.0, 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))))`.
2. Add a one-line comment: `# erf(z) can return 1.0 ± float-epsilon; clamp
before computing ranks.`
3. The existing `max(1.0, ...)` guard in `rank_of` may then be relaxed but should
   be retained for defence in depth.

**Constraints**: the change is one line plus a comment. Do not introduce a
dependency on `scipy.stats.norm` — the current `math.erf` approach is correct and
lightweight. Do not change the `RankModel` public API.

**Tests first**: add `test_share_below_never_exceeds_one` to
`test_effective_points.py` using `pytest.approx` to verify `share_below` returns
at most `1.0` for very large positive `z` values, and `test_rank_of_never_below_one`
to verify `rank_of` ≥ 1.0 for any score.

**Done when**:

- `RankModel(mean_points=0.0, standard_deviation=1.0, field_size=100_000).share_below(1e300) <= 1.0` is `True`.
- `rank_of` never returns a value below 1.0 for any finite input.
- All existing `test_effective_points.py` tests pass.

**Validate**: `python -m pytest python/tests/test_effective_points.py -q`

---

## 24 — Handle degenerate-variance rank correlation explicitly in `models/backtest.py` (Impact: M)

**Files**: `python/fpl_andres/models/backtest.py` (`_spearman`, lines 218–230),
`python/tests/test_backtest.py`

**Problem**: `_spearman` already returns `None` when `len(set(predicted)) < 2`
or `len(set(actual)) < 2` (lines 225–226), guarding the constant-column case.
The return value `None` is correct — but the reason for the `None` is lost: a
caller receiving `spearman = None` cannot tell whether the event had fewer than 3
predictions (line 221 guard), had a constant prediction vector, had a constant
actual vector, or produced a NaN from scipy (line 228). All four cases are
distinct:

- Fewer than 3 predictions: not enough data to rank.
- Constant predictions: all players were projected equally (model failure or
  featureless event).
- Constant actuals: all players scored identically (unusual event).
- scipy NaN: numerical issue in the correlation computation itself.

**Change**:

1. Replace `float | None` with an explicit `BacktestSpearman` type (either a
   dataclass or `NamedTuple`) that carries `value: float | None` and
   `reason: str | None`. Alternatively, return a typed `SpearmanResult` from
   `_spearman` that includes a `degenerate_reason` field, used only for
   diagnostics and not surfaced in `BacktestMetrics.spearman`.
2. Update `BacktestMetrics.spearman` to remain `float | None` for the public API,
   but internally use `SpearmanResult` in `_spearman` and have `score_backtest`
   log the degenerate reason when it is not `None`.

**Constraints**: `BacktestMetrics.spearman` must remain `float | None` — no
public API change. The diagnostic reason must not change the computed value. The
existing `_spearman` function in `backtesting/score.py` (a separate copy — see
item 31) is out of scope for this item.

**Tests first**: add `test_constant_predicted_returns_none_with_reason` to
`test_backtest.py`, constructing `PredictionOutcome` tuples with identical
predicted values and asserting that the internal `SpearmanResult.degenerate_reason`
is `"constant_predicted"` (or equivalent string). Add
`test_normal_correlation_returns_value_with_no_reason`.

**Done when**:

- `_spearman` returns a result that distinguishes the four `None`-returning
  cases.
- `BacktestMetrics.spearman` remains `float | None`.
- All existing `test_backtest.py` tests pass.

**Validate**: `python -m pytest python/tests/test_backtest.py -q`

---

## 25 — Weight or report top-N hit rate for short-event gameweeks (Impact: M)

**Files**: `python/fpl_andres/models/backtest.py` (`_top_n_hit_rate`, lines
233–265), `python/fpl_andres/backtesting/score.py` (`_score`, lines 164–207),
`python/tests/test_backtest.py`

**Problem**: `_top_n_hit_rate` (line 247) silently skips events where
`len(event_outcomes) < top_n`. The aggregate rate is then the unweighted mean over
only well-covered gameweeks (line 263). Gameweeks with fewer scored players —
blanks, cup-deflected rounds, early-season gameweeks — are excluded, biasing the
aggregate toward gameweeks where the model had the most data. A model that
performs well in full gameweeks but poorly in blanks would show an inflated
hit rate.

Similarly, `_score` in `score.py` (line 176) skips the entire gameweek if
`len(shared) < top_n`, for the same reason.

**Change**:

1. In `_top_n_hit_rate`, replace the `continue` skip with a weighted rate: for
   events with fewer than `top_n` scored players, compute the hit rate as
   `len(predicted_top & actual_top) / len(event_outcomes)` (i.e. use the actual
   event size as the denominator) and weight this event's contribution
   proportionally to its size.
2. Add `events_skipped_short: int` and `events_included_partial: int` fields to
   `BacktestMetrics` (or a supplementary `BacktestCoverage` dataclass) so the
   caller can see how many gameweeks were excluded vs partially counted.
3. Apply the same weighted treatment in `backtesting/score.py`'s `_score`.

**Constraints**: changing the `top_n_hit_rate` formula changes the metric values
in existing tests — update those tests with the new expected values, or add a
new field `weighted_top_n_hit_rate` alongside the existing one. Do not remove the
existing `top_n_hit_rate` field from `BacktestMetrics`.

**Tests first**: add `test_short_event_contributes_to_hit_rate` to `test_backtest.py`
constructing an event with only 5 outcomes and `top_n = 20`, asserting that the
event contributes to the metric (rather than being skipped).

**Done when**:

- Short events contribute to `top_n_hit_rate` with appropriate weighting.
- `BacktestMetrics` includes a field reporting how many events were short.
- All `test_backtest.py` tests pass (with updated expectations if needed).

**Validate**: `python -m pytest python/tests/test_backtest.py -q`

---

## 26 — Document and test the shrinkage boundary at zero observed minutes (Impact: M)

**Files**: `python/fpl_andres/models/player_rates.py` (`_shrink`, lines
242–248; `project_player_rates`, lines 147–213),
`python/tests/test_player_rates.py`, `docs/MODEL.md`

**Problem**: `_shrink(events, minutes, prior_rate, prior)` (lines 242–248) handles
`total_minutes <= 0.0` by returning `prior_rate` directly (line 247). This is the
correct shrinkage limit — with zero observations the estimate collapses to the
prior — but it is not tested explicitly and not documented in `docs/MODEL.md`.
Furthermore, the `project_player_rates` function has a separate guard at line 168
(`if current_minutes <= 0.0: current_weight = 0.0`) that forces the blend toward
the carried season when the current season has no minutes; then `_shrink` is
called with `blended_minutes = carried_minutes * carried_weight`. If carried
minutes are also zero, `_shrink` returns `prior_rate`, and the projection carries
`goals_per_90 = prior.goals_per_90` at `evidence_level = "inferred"`. A caller
reading only `evidence_level` would not know the estimate is entirely prior-driven
with no observational support.

**Change**:

1. Add a dedicated `reason_code` such as `"prior_only_no_minutes"` in
   `project_player_rates` when both `current_minutes == 0` and
   `carried_minutes == 0` and the function is about to call `_shrink` with
   `blended_minutes = 0`.
2. Document the boundary case in `docs/MODEL.md` under "Player rates" with the
   explicit statement: zero observed minutes → estimate equals `prior.goals_per_90`
   / `prior.assists_per_90`, evidence level remains at the default for carried
   observations.
3. Add a docstring to `_shrink` explaining the zero-minutes branch.

**Constraints**: do not change the numerical result of `_shrink` — the prior
collapse is the correct behaviour. Do not change `evidence_level` for this case
unless item 29 (evidence quality in blend weight) is also implemented. The reason
code must be added to `PlayerRateProjection.reason_codes`.

**Tests first**: add `test_zero_minutes_returns_prior_rate` to `test_player_rates.py`
constructing `PlayerRateEvidence` with empty `current_season_observations` and
empty `prior_season_observations` but a non-zero `prior.goals_per_90`, and
asserting `projection.goals_per_90 == prior.goals_per_90` and
`"prior_only_no_minutes"` in `projection.reason_codes`.

**Done when**:

- `"prior_only_no_minutes"` appears in `reason_codes` for zero-minutes projections.
- `docs/MODEL.md` documents the shrinkage boundary.
- New and existing `test_player_rates.py` tests pass.

**Validate**: `python -m pytest python/tests/test_player_rates.py -q`

---

## 27 — Validate beta-binomial prior strength bounds in `models/minutes.py` (Impact: M)

**Files**: `python/fpl_andres/models/minutes.py` (`MinutesEvidence`,
`prior_strength_events` field, line 92; `project_minutes`, lines 140–244),
`python/tests/test_minutes_model.py`, `docs/MODEL.md`

**Problem**: `prior_strength_events` is bounded `Field(ge=0.0, le=38.0)` (line
92). The upper bound of 38 events is the maximum season length, which is a
reasonable structural limit but is not documented as a sourced value. More
importantly, a very large `prior_strength_events` (e.g. 37.9) would make the
beta-binomial posterior nearly identical to the prior start rate regardless of
observed data — `probability_start` would be dominated by
`evidence.prior_start_rate * prior_strength` over any realistic `effective_sample`.
A sourced value this extreme is incoherent with the model's purpose (updating the
prior with observations) and should fail its contract rather than silently
dominate.

**Change**:

1. Add a cross-field validator in `MinutesEvidence.validate_evidence` (after the
   existing duplicate check) that raises `ValueError` when
   `prior_strength_events > evidence.minimum_observations * 10` — i.e. when the
   prior strength is more than ten times the minimum sample required to project
   at all. The factor 10 is a conservative bound; document it and its source in
   `docs/MODEL.md`.
2. Document the intended domain of `prior_strength_events` in `docs/MODEL.md`:
   typical values are 1–5 events; values above 20 indicate a misconfiguration.

**Constraints**: the sourced value must not be defaulted if not supplied. The
validator must raise `ValueError`, not `ValidationError`. Do not change the
field's Pydantic bounds — they remain the structural limit. No existing tests
should fail (no existing test passes a prior strength above 10x the minimum).

**Tests first**: add `test_extreme_prior_strength_rejected` to
`test_minutes_model.py` constructing `MinutesEvidence` with
`prior_strength_events=38.0` and `minimum_observations=3` (giving 38 > 3*10=30,
which trips the guard), and asserting `ValidationError` (or `ValueError` if called
directly).

**Done when**:

- `prior_strength_events` that dominates the posterior (relative to
  `minimum_observations`) raises `ValueError`.
- `docs/MODEL.md` documents the intended range.
- All existing `test_minutes_model.py` tests pass.

**Validate**: `python -m pytest python/tests/test_minutes_model.py -q`

---

## 28 — Model rival-ownership covariance in `planning/effective.py` (Impact: M)

**Files**: `python/fpl_andres/planning/effective.py` (`EffectivePoints`, lines
68–94; `effective_points`, lines 97–120),
`python/tests/test_effective_points.py`

**Problem**: `EffectivePoints.swing`, `.cover`, and `.upside` (lines 77–90) are
computed per-player independently. The rank model in `RankModel` treats the total
gameweek score as normally distributed, but the swing calculation
`(mine - effective_ownership) * expected_points` implicitly assumes players are
independent — i.e. that owning Player A has no correlation with owning Player B.
In practice, popular players cluster: a manager who has Salah also tends to have
Alexander-Arnold, so the covariance between their ownership indicators is
positive. This means the variance of the net swing is understated, and a plan
that holds two high-ownership differentials in the same fixture gets a lower
variance estimate than it should.

This item is a modelling extension, not a bug fix.

**Change**:

1. Add a `covariance_matrix: dict[tuple[int, int], float] | None = None` optional
   parameter to `effective_points`, where the keys are pairs of `element_id` and
   the values are the Pearson correlation between their ownership indicators.
2. Add a method `portfolio_variance(model: RankModel, owned: Sequence[int]) ->
float` to the module (or as a standalone function) that, when
   `covariance_matrix` is supplied, computes the variance of the total swing as
   `sum_i sum_j cov(swing_i, swing_j)` using the ownership correlations and the
   individual player expected points.
3. Document in `docs/LIMITATIONS.md` that ownership covariance data is not
   currently sourced, so the function accepts `None` and returns the independent
   approximation in that case.

**Constraints**: the change must be backward-compatible — `effective_points`
without `covariance_matrix` must behave identically to the current code. The
covariance matrix must be sourced externally; this module must not compute or
default it. Nothing may exceed `docs/LIMITATIONS.md`.

**Tests first**: add `test_portfolio_variance_with_covariance_exceeds_independent`
to `test_effective_points.py`, constructing two players with positive correlation
and asserting the correlated variance exceeds the uncorrelated sum.

**Done when**:

- `effective_points(..., covariance_matrix=None)` produces identical output to
  the current function.
- `portfolio_variance` correctly aggregates correlated swings.
- `docs/LIMITATIONS.md` notes the unsourced covariance.

**Validate**: `python -m pytest python/tests/test_effective_points.py -q`

---

## 29 — Carry evidence quality into the cross-season blend weight (Impact: M)

**Files**: `python/fpl_andres/models/player_rates.py` (`project_player_rates`,
lines 147–213; specifically carried_weight computation, lines 164–170),
`python/tests/test_player_rates.py`, `docs/MODEL.md`

**Problem**: `carried_weight = 1.0 - current_weight` (line 170) depends only on
the current-season minutes accumulated (`current_weight = min(1.0,
current_minutes / blend_full_weight_minutes)`). The carried season contributes
with weight `carried_weight` regardless of whether the prior-season observations
came from the same club and role. A player who changed club or position between
seasons carries observations from a context that is no longer representative;
those observations deserve a discount relative to same-club, same-role data. The
current code applies the same carry weight whether the prior-season data is
contextually appropriate or not.

**Change**:

1. Add an optional boolean field `prior_context_matches: bool | None = None` to
   `PlayerRateEvidence` (default `None` = unknown). When `False` (different club
   or role), apply a discount factor `context_discount: float` (a new sourced
   field, `Field(gt=0.0, le=1.0)`) to `carried_weight`.
2. In `project_player_rates`, multiply `carried_weight` by `context_discount` when
   `prior_context_matches is False`.
3. When `prior_context_matches is None` (unknown), emit a reason code
   `"context_unknown"` and apply no discount.
4. Document in `docs/MODEL.md` that `context_discount` is sourced and that the
   default of 1.0 (no discount) applies when context is unknown.

**Constraints**: `context_discount` must not be defaulted without a source
reference — if `prior_context_matches is False` and no `context_discount` is
supplied, raise `ValueError`. The model output (`goals_per_90`, `assists_per_90`)
must remain deterministic given the inputs. The `EvidenceLevel` for a carried
observation already downgrades to `"inferred"` (line 197) — this item refines the
weight within that level, not the level itself.

**Tests first**: add `test_context_mismatch_discounts_carried_weight` to
`test_player_rates.py` comparing two projections with identical inputs but
`prior_context_matches=True` vs `prior_context_matches=False` (and a
`context_discount=0.5`), asserting the mismatch projection carries a lower
`carried_weight` and therefore a different rate estimate.

**Done when**:

- `prior_context_matches=False` with a sourced `context_discount` reduces
  `carried_weight`.
- `prior_context_matches=None` emits `"context_unknown"` in reason codes.
- `docs/MODEL.md` documents the field.
- All existing `test_player_rates.py` tests pass (they supply no
  `prior_context_matches`, so default `None` applies).

**Validate**: `python -m pytest python/tests/test_player_rates.py -q`

---

## 30 — Support multi-seed bootstrap aggregation in `models/promotion.py` (Impact: M)

**Files**: `python/fpl_andres/models/promotion.py` (`evaluate_promotion`, lines
51–156; `BootstrapResult`, lines 29–38),
`python/tests/test_model_promotion.py`

**Problem**: `evaluate_promotion` accepts a single integer `seed` (line 58) and
constructs `rng = random.Random(seed)` (line 97). A promotion decision is
therefore fully determined by one seed. If the seed happens to produce a resample
distribution that just crosses the zero-improvement boundary, a different seed
would produce the opposite decision. Users comparing runs with different seeds
will see different promotion decisions — or the same seed could be reused
inappropriately across evaluations, producing spuriously similar results.

**Change**:

1. Change the `seed` parameter of `evaluate_promotion` to accept `int | Sequence[int]`.
   When a sequence of seeds is supplied, run the bootstrap once per seed and
   aggregate the per-seed sample lists by concatenation before computing quantiles.
2. Update `BootstrapResult.seed` to `seed: int | tuple[int, ...]` to carry all
   seeds used.
3. Update `_validate_parameters` to accept either type.
4. Keep backward compatibility: a single integer seed behaves identically to the
   current code.

**Constraints**: the effective `resamples` reported in `BootstrapResult.resamples`
should be the total number of resamples across all seeds. Do not change the
`resamples` parameter meaning. The promotion decision (`promoted: bool`) must
remain a deterministic function of the inputs (seeds + triplets + metric).

**Tests first**: add `test_multi_seed_aggregates_samples` to
`test_model_promotion.py` calling `evaluate_promotion` with `seed=[42, 43, 44]`
and `resamples=100`, asserting `bootstrap_result.resamples == 300` and that the
point estimate equals the single-seed result (point estimates are seed-independent).

**Done when**:

- `evaluate_promotion(... seed=[42, 43])` runs without error.
- `BootstrapResult.resamples` equals the sum of per-seed resample counts.
- Single-seed calls return identical results to the current code.
- All `test_model_promotion.py` tests pass.

**Validate**: `python -m pytest python/tests/test_model_promotion.py -q`

---

## 31 — Centralise NaN/validity handling for Spearman correlation (Impact: L)

**Files**: `python/fpl_andres/models/backtest.py` (`_spearman`, lines 218–230),
`python/fpl_andres/backtesting/score.py` (`_spearman`, lines 210–216),
`python/fpl_andres/models/player_rates.py` (no Spearman here),
`python/tests/test_backtest.py`

**Problem**: two private `_spearman` functions with the same name exist in
different modules. `models/backtest.py` version (line 218) takes
`Sequence[PredictionOutcome]` and handles three guard conditions: fewer than 3
outcomes, constant predicted, constant actual. `backtesting/score.py` version
(line 210) takes two `Sequence[float]` directly and handles: fewer than 3
values, fewer than 2 distinct values in either sequence, scipy NaN. The two
implementations are structurally similar but not identical — they have different
guard orderings and the `score.py` version checks `len(set(actual)) < 2` while
`backtest.py` checks `len(set(actual)) < 2` (same). However, `score.py` does not
check for scipy NaN by the `value != value` idiom used in `backtest.py` (it
relies on scipy guaranteeing finite output, which is not documented).

**Change**:

1. Create `python/fpl_andres/utils/statistics.py` with a single public function
   `spearman_rank_correlation(predicted: Sequence[float], actual: Sequence[float])
-> float | None` that combines all guards: fewer than 3 values, fewer than 2
   distinct values in either sequence, and NaN check.
2. Export from `python/fpl_andres/utils/__init__.py`.
3. Replace both private `_spearman` functions with imports of the shared
   function. `models/backtest.py`'s version must unwrap `PredictionOutcome`
   before calling the shared function.

**Constraints**: both existing `_spearman` functions return `float | None` — the
shared function must have the same return type. No behaviour change in either
module. Run both test suites to confirm.

**Tests first**: add `test_spearman_returns_none_for_constant_sequence` and
`test_spearman_returns_correlation_for_valid_sequences` to a new
`test_utils_statistics.py` (or `test_backtest.py`).

**Done when**:

- `grep -rn "def _spearman" python/fpl_andres/` returns zero results.
- Both `test_backtest.py` and a test for `score.py` pass unmodified.

**Validate**: `python -m pytest python/tests/test_backtest.py -q`

---

## 32 — Require consistent presence of optional inputs across observations (Impact: L)

**Files**: `python/fpl_andres/models/player_rates.py` (`_has_complete_expected`,
lines 216–224; `_totals`, lines 227–235; `RateObservation`, lines 41–58),
`python/tests/test_player_rates.py`

**Problem**: `_has_complete_expected(observations)` (line 216) returns `True` only
when every observation has both `expected_goals` and `expected_assists` non-null —
vacuously `True` for an empty set. `_totals` (line 227) then branches on this
boolean: if `use_expected` is `True`, it sums `observation.expected_goals or 0.0`
(line 230). The `or 0.0` is the real gap: if `_has_complete_expected` returns
`True` for the combined (current + prior) set but one of those observations has
`expected_goals = None` (which `_has_complete_expected` would have rejected), the
`or 0.0` silently substitutes zero rather than raising. The combination that
triggers this is when `_has_complete_expected` is called separately for
`current_season_observations` and `prior_season_observations` (line 175) but the
`use_expected` flag is then applied to both sets together in `_totals`.

Looking at the code: `use_expected` at line 175 is `_has_complete_expected(current)
and _has_complete_expected(prior)`. So if either set is incomplete,
`use_expected=False` and no `or 0.0` fallback is reached. However, if
`_has_complete_expected` is vacuously `True` for an empty prior set and the
current set has a mix of null and non-null expected values — this cannot happen
because `_has_complete_expected` requires ALL observations to have both fields.

The real gap is simpler: `_has_complete_expected` silently allows a partial
`prior_season_observations` set where some observations have expected values and
some do not, because it short-circuits on the first `None`. In practice it either
passes or fails the whole set, which is correct. The `or 0.0` at line 230 is
technically unreachable given the guards, but it obscures the intent.

**Change**:

1. Replace `observation.expected_goals or 0.0` and `observation.expected_assists
or 0.0` in `_totals` with `observation.expected_goals` and
   `observation.expected_assists` directly (no fallback), after asserting that
   both are non-None using `assert observation.expected_goals is not None`. This
   makes the invariant explicit.
2. Add a docstring to `_has_complete_expected` stating that it is a pre-condition
   for calling `_totals` with `use_expected=True`.
3. Add a note to `RateObservation` about consistency: if any observation in a
   sequence is missing expected values, `use_expected` falls back to actual goals;
   mixed presence within a sequence is treated as complete absence.

**Constraints**: the change is cosmetic and defensive — no numerical change for
valid inputs. The `or 0.0` removal converts a silent fallback into a clear
`AssertionError` for a state that should be unreachable; add a comment saying so.

**Tests first**: add `test_totals_asserts_not_none_when_use_expected` to
`test_player_rates.py` constructing a mock `RateObservation` with
`expected_goals=None` and calling `_totals` with `use_expected=True`, asserting
`AssertionError` is raised (confirming the invariant is checked).

**Done when**:

- `_totals` raises `AssertionError` when called with `use_expected=True` on an
  observation that has `expected_goals = None`.
- All existing `test_player_rates.py` tests pass.
- No `or 0.0` fallback exists in `_totals`.

**Validate**: `python -m pytest python/tests/test_player_rates.py -q`
