# 3. Python performance and scalability — work orders

Detailed briefs for items 33–40 of the [improvement audit](../../IMPROVEMENTS.md).
Each brief is self-contained: a sub-agent should be able to implement one item
from its brief alone.

Every brief obeys the repository rules: test-first (failing focused test, minimal
code, refactor), never default a missing controlling FPL rule (fail the source
contract visibly), and nothing may exceed `docs/LIMITATIONS.md`.

---

## 33 — Pre-sort event outcomes once in `_top_n_hit_rate` (Impact: M)

**Files**: `python/fpl_andres/models/backtest.py` (`_top_n_hit_rate`, lines 233–265),
`python/tests/test_backtest.py`

**Problem**: `_top_n_hit_rate` groups outcomes into a per-event dict (`by_event`) and
then, for every event, calls `sorted(event_outcomes, key=…, reverse=True)` twice: once
on `predicted_points` (lines 251–254) and once on `actual_points` (lines 255–259). Both
sorts are O(k log k) in the number of players per event and are repeated for every event
in the corpus. A multi-season backtest with 38 events × 600 players repeats 76 full sorts
on the same data. For a benchmark run over a 5-season corpus the sort cost is the
dominant term in `_metrics`.

**Change**:

1. In `_top_n_hit_rate`, immediately after `by_event` is built, add a pre-sort pass:
   for every event's list in `by_event.values()`, sort once by `predicted_points`
   (descending) and store the result, and sort once more by `actual_points` (descending)
   and store that result, yielding two pre-sorted lists per event.
2. Replace the two inline `sorted(…)` calls inside the event loop with slices of
   those pre-sorted lists.
3. Verify that `PredictionOutcome` objects compared inside `_top_n_hit_rate` are
   accessed only through `element_code`, `predicted_points`, and `actual_points` — no
   other fields — so the refactor cannot change the set of elements selected.

**Constraints**: `_top_n_hit_rate` is called only from `_metrics`
(`python/fpl_andres/models/backtest.py` line 214), which is called from `run_backtest`
(line 164). No public callers outside `backtest.py` touch this function directly. The
result must be numerically identical to the original for every input: same `top_n_hit_rate`
value, same `BacktestReport` structure, same `BacktestLeakError` behaviour.

**Tests first**: in `python/tests/test_backtest.py`:

- Add `test_top_n_hit_rate_sort_count_is_bounded_by_events_not_events_times_two`: use
  `unittest.mock.patch` to instrument `sorted` (or use a call-counting wrapper injected
  via monkeypatch) and assert that the total sort count for a corpus of N events equals
  exactly 2N, not more.
- Confirm that the existing `test_top_n_hit_rate_is_computed_per_event_not_across_the_pool`
  still passes unchanged — it serves as the equivalence test.

**Done when**:

1. `_top_n_hit_rate` performs exactly two sorts per distinct (season, event) pair,
   regardless of how many players are in that event.
2. All pre-existing `test_backtest.py` tests pass without modification.
3. The new sort-count test passes.
4. `python -m pytest python/tests/test_backtest.py -q` is green.

**Validate**: `python -m pytest python/tests/test_backtest.py -q`

---

## 34 — Build the HiGHS constraint matrix sparsely (Impact: M)

**Files**: `python/fpl_andres/optimization/highs.py` (`HighsOptimizer.solve`,
`add_constraint` inner function lines 59–70, `np.vstack(rows)` at line 161),
`python/tests/test_highs_optimizer.py`

**Problem**: `add_constraint` allocates a dense `np.zeros(variable_count)` row for every
constraint and sets only a handful of non-zero entries. The call at line 161
(`np.vstack(rows)`) assembles all these rows into one dense matrix of shape
`(constraint_count × variable_count)`. With a player pool of P players and a three-event
horizon, `variable_count ≈ 3P + 1` and `constraint_count ≈ 5 + 2P + 4 + P + P + 3`.
Every element is stored even though each row is ≥ 95 % zero. Memory and the
`LinearConstraint` construction time both grow as O(P²).
`scipy.optimize.milp` accepts a `scipy.sparse.linalg.LinearConstraint` backed by a
`scipy.sparse.csc_array`; using it reduces memory to O(nnz) and passes the matrix
directly to HiGHS in its native sparse format.

**Change**:

1. Replace the `rows: list[np.ndarray]` accumulator with three parallel lists:
   `coo_row`, `coo_col`, `coo_data` (COO triplets).
2. Rewrite `add_constraint` to append index and value pairs to those lists instead
   of writing into a dense row.
3. Before calling `milp`, assemble a `scipy.sparse.csc_array` (or `csc_matrix`) from
   the COO triplets, and pass it to `LinearConstraint` in place of `np.vstack(rows)`.
4. Leave the `lower_bounds` and `upper_bounds` lists unchanged; only the constraint
   matrix changes format.
5. Keep the `objective`, `integrality`, and `Bounds` arguments dense — they are
   1-D vectors of length `variable_count` and do not benefit from sparsity.

**Constraints**: `HighsOptimizer` is called from `optimization/horizon.py`
(`HighsHorizonOptimizer`, which has its own dense matrix) and from the test suite.
This item changes only `highs.py`; `horizon.py` is a separate item (39). The
`OptimizationResult` contract must not change. Behavioural equivalence — same solver
decisions — must be confirmed against the existing oracle tests.

**Tests first**: in `python/tests/test_highs_optimizer.py`:

- Add `test_highs_constraint_matrix_is_sparse`: after constructing a
  `HighsOptimizer` and calling `solve` on a small fixture request, use monkeypatching
  to capture the argument passed to `LinearConstraint`, assert it is a sparse type
  (e.g. `scipy.sparse.issparse(matrix)`), and assert `matrix.nnz < matrix.shape[0] * matrix.shape[1] * 0.5`.
- The existing `test_highs_matches_independent_exhaustive_oracle` and
  `test_highs_matches_exhaustive_oracle_across_generated_points` serve as equivalence
  tests and must pass unchanged.

**Done when**:

1. The constraint matrix passed to `LinearConstraint` is a sparse type.
2. All existing oracle tests pass with identical solutions.
3. The new sparsity test passes.
4. `python -m pytest python/tests/test_highs_optimizer.py -q` is green.

**Validate**: `python -m pytest python/tests/test_highs_optimizer.py -q`

---

## 35 — Cache player index and forecast dict in `HighsHorizonOptimizer` (Impact: M)

**Files**: `python/fpl_andres/optimization/horizon.py` (`HighsHorizonOptimizer.solve`,
lines 27–38), `python/tests/test_horizon_optimizer.py`

**Problem**: Every call to `HighsHorizonOptimizer.solve` rebuilds `player_ids` (lines
27–33), `player_index` (line 35), and `forecasts` (lines 36–38) from scratch. During a
re-planning sweep that calls `solve` once per candidate gameweek, these three structures
are reconstructed identically on each call even though the request differs only in
`available_free_transfers` or `bank_tenths`. Building `player_index` is O(P) and
`forecasts` is O(F) where F is the total number of forecasts across all horizon events;
for a 5-event horizon with 600 players F ≈ 3000, so the combined rebuild cost is
non-trivial when the sweep covers many gameweeks.

**Change**:

1. Add a private cache attribute `_cache` on `HighsHorizonOptimizer.__init__` (initially
   `None`), typed as an optional tuple of `(player_ids, player_index, forecasts,
cache_key)` where `cache_key` is derived from the sorted tuple of forecast identities
   (e.g., `(forecast.event, forecast.element_id)` pairs).
2. At the top of `solve`, compute the cache key from the incoming `request.forecasts`
   and compare it with `self._cache`. On a hit, reuse the stored structures; on a miss
   (new forecasts), rebuild and store.
3. Do not cache anything that depends on `request.current_squad`, `request.bank_tenths`,
   or `request.available_free_transfers` — those vary across calls.
4. Ensure the cache is invalidated when forecasts change identity (different player set
   or different event horizon), not only when the object is different.

**Constraints**: `HighsHorizonOptimizer` is not documented as thread-safe; the cache
does not need a lock. The `HorizonOptimizationResult` contract must not change.
The existing oracle tests must pass with identical solver decisions.

**Tests first**: in `python/tests/test_horizon_optimizer.py`:

- Add `test_solve_reuses_index_on_repeated_calls_with_same_forecasts`: call `solve`
  twice with the same forecasts but different `available_free_transfers`; use
  `unittest.mock.patch` on `dict.__init__` or a custom counter to assert that
  `player_index` was built only once (i.e., the expensive dict-comprehension path
  ran once).
- Alternatively, assert that calling `solve` a second time with the same forecasts
  does not re-sort `player_ids` by confirming the `sorted()` call count is 1, not 2.
- The existing `test_horizon_matches_dynamic_programming_oracle_across_generated_points`
  serves as the equivalence test.

**Done when**:

1. Two consecutive `solve` calls with identical forecasts trigger the index-build path
   exactly once.
2. A `solve` call with a different forecast set triggers a fresh build.
3. All existing oracle tests pass with identical results.
4. `python -m pytest python/tests/test_horizon_optimizer.py -q` is green.

**Validate**: `python -m pytest python/tests/test_horizon_optimizer.py -q`

---

## 36 — Cap crosswalk candidate generation to avoid unbounded sets (Impact: M)

**Files**: `python/fpl_andres/crosswalk/resolve.py` (`_index` lines 147–156,
`resolve_crosswalk` lines 174–180), `python/fpl_andres/crosswalk/names.py`
(`variants`), `python/tests/test_crosswalk.py`

**Problem**: In `resolve_crosswalk`, for each FPL player, `variants(player.first_name,
player.second_name, player.web_name)` generates every spelling worth trying (full name,
surname alone, name without particles, etc.). For each spelling, `index.get((player.season,
club, spelling), ())` yields all foreign players sharing that key. The results are
accumulated in `nominated` (a dict keyed by `source_id`). A common surname shared by
many players at one club — e.g., a large squad where many foreign-source players have the
same second name — makes `nominated` grow without bound. More importantly, the `variants`
function itself generates a combinatorial expansion when a name has multiple particles or
tokens, and the index accumulates every matching foreign player under every spelling
variant. With no cap, a degenerate input (e.g., a season with a common surname appearing
many times at the same club) causes the candidate set to be O(|variants| × |players with
that name|) per FPL player.

**Change**:

1. Introduce a module-level constant `_MAX_CANDIDATES` (e.g., 25) in `resolve.py`.
2. In the inner candidate-accumulation loop of `resolve_crosswalk` (lines 178–180),
   after adding a candidate to `nominated`, break out of the inner loop when
   `len(nominated) >= _MAX_CANDIDATES` and set outcome to `MatchOutcome.AMBIGUOUS`
   immediately, skipping the agreement check. This preserves the correctness invariant:
   a set this large cannot be resolved to a single verified match regardless.
3. Add `_MAX_CANDIDATES` to the `__all__` list so callers can inspect the limit.
4. Document the cap value's rationale: a real Premier League squad has at most 25
   players, so more than 25 candidates at one club-season is already pathological.

**Constraints**: `MatchOutcome.AMBIGUOUS` is already a valid outcome (returned when
`len(agreeing) > 1`). The `CrosswalkReport.coverage()` method counts `AMBIGUOUS` as
an eligible but unmatched player, which is correct. Existing tests must not see any
change for typical inputs where `nominated` stays well under 25 entries.

**Tests first**: in `python/tests/test_crosswalk.py`:

- Add `test_a_degenerate_surname_shared_by_many_candidates_is_capped_ambiguous`: build
  a foreign player list with 30 players sharing the same name at the same club-season,
  and a single FPL player with that name. Assert the result is `AMBIGUOUS`, not an
  infinite loop, and that `CrosswalkReport.counts[MatchOutcome.AMBIGUOUS] == 1`.
- Assert that `_MAX_CANDIDATES` is importable from `fpl_andres.crosswalk.resolve`.

**Done when**:

1. A degenerate input with 30 same-name candidates at one club resolves in O(1) time
   and returns `AMBIGUOUS`.
2. All existing `test_crosswalk.py` tests pass unchanged.
3. `_MAX_CANDIDATES` is exported.
4. `python -m pytest python/tests/test_crosswalk.py -q` is green.

**Validate**: `python -m pytest python/tests/test_crosswalk.py -q`

---

## 37 — Hoist reciprocal decay constant out of the weight comprehension (Impact: L)

**Files**: `python/fpl_andres/models/minutes.py` (`project_minutes`, lines 168–172),
`python/tests/test_minutes_model.py`

**Problem**: The dict comprehension at lines 168–172 computes the recency weight for
each observation as `0.5 ** ((evidence.prediction_event - observation.event_id) /
evidence.decay_half_life_events)`. The division by `evidence.decay_half_life_events` is
a constant for the entire comprehension but is evaluated once per observation iteration
because it appears inside the exponent expression. Pre-computing
`inv_half_life = 1.0 / evidence.decay_half_life_events` and converting the exponent to
`(evidence.prediction_event - observation.event_id) * inv_half_life` removes one
floating-point division per observation. For a player with a full 38-game season as
evidence, this is 38 divisions saved per call to `project_minutes`.

**Change**:

1. Before the `weights` dict comprehension (line 168), bind
   `inv_half_life = 1.0 / evidence.decay_half_life_events`.
2. Replace the comprehension body's divisor with `* inv_half_life`.
3. Do not change `MinutesEvidence`, its validators, or any other part of
   `project_minutes`; this is a local arithmetic rearrangement only.

**Constraints**: The result must be numerically identical to the original to within
floating-point rounding (the division and multiplication are algebraically equivalent,
and IEEE 754 floating-point makes the two forms identical). The existing evidence-level
and availability-gating logic must not be touched. No change to any model contract or
`MinutesProjection` field.

**Tests first**: in `python/tests/test_minutes_model.py`:

- Add `test_decay_weights_are_numerically_equivalent_before_and_after_hoist`:
  compute `project_minutes` on a fixed `MinutesEvidence` fixture with at least 20
  observations, collect the `expected_minutes` and `probability_start` fields, then
  verify they match a reference computed with the original formula to within
  `pytest.approx(rel=1e-12)`.
- The existing tests `test_recency_dominates_a_stale_run_of_starts` and
  `test_a_recent_return_to_the_side_outweighs_an_older_benching` serve as equivalence
  tests.

**Done when**:

1. The `weights` comprehension contains no division by `decay_half_life_events` inside
   the loop body.
2. All existing `test_minutes_model.py` tests pass unchanged.
3. The new equivalence test passes.
4. `python -m pytest python/tests/test_minutes_model.py -q` is green.

**Validate**: `python -m pytest python/tests/test_minutes_model.py -q`

---

## 38 — Consolidate per-player passes in `HighsOptimizer.solve` (Impact: L)

**Files**: `python/fpl_andres/optimization/highs.py` (`HighsOptimizer.solve`,
lines 123–149 and surrounding loops), `python/tests/test_highs_optimizer.py`

**Problem**: `HighsOptimizer.solve` iterates over the `players` tuple six times across
separate blocks: once for the objective (lines 50–53), once for lineup/captain bounds
(lines 87–95), once for team grouping (lines 114–121), once for budget coefficients
(lines 123–131), once for incoming indices (lines 137–139), and once for the transfer
objective (lines 189–191). Several of these loops access `current.get(player.element_id)`
separately. Each extra pass is O(P) and accesses the same player attributes; combining
the budget-and-incoming pass into a single loop and pre-joining with `current` removes
at least three redundant iterations over `players`.

**Change**:

1. Add a single pre-join loop immediately after `current` is built (line 47) that
   produces, for each player index, the tuple
   `(is_current, buy_price, sell_price)` stored in a list indexed by player position.
2. Rewrite the budget-coefficient block (lines 123–131) and the incoming-indices block
   (lines 137–139) to read from this pre-joined list instead of calling
   `current.get(player.element_id)` again.
3. Where the transfer-objective loop (lines 189–191) relies on `incoming_indices`,
   keep that variable computed in step 2 so it is not recomputed.
4. Do not merge the objective loop (lines 50–53) or the team-grouping loop (lines
   114–121) into the pre-join unless the change is obviously safe and tested; restrict
   the merge to the budget and incoming blocks.

**Constraints**: No change to `OptimizationResult`, `OptimizationRequest`, or
`OptimizationError`. The solver decisions must remain identical; the existing oracle
tests serve as the equivalence guarantee. `HighsHorizonOptimizer` in `horizon.py` is
a separate solver and must not be touched.

**Tests first**: in `python/tests/test_highs_optimizer.py`:

- The existing `test_highs_matches_independent_exhaustive_oracle` and
  `test_highs_matches_exhaustive_oracle_across_generated_points` serve as equivalence
  tests; they must pass unchanged.
- Add `test_budget_and_incoming_use_pre_joined_current`: monkeypatch `dict.get` on
  the `current` dict and assert it is called at most once per player (i.e., the total
  call count ≤ P), not once in the budget block and once in the incoming block.

**Done when**:

1. `current.get(player.element_id)` is called at most once per player across the
   budget and incoming blocks.
2. All existing oracle tests pass with identical results.
3. The new test passes.
4. `python -m pytest python/tests/test_highs_optimizer.py -q` is green.

**Validate**: `python -m pytest python/tests/test_highs_optimizer.py -q`

---

## 39 — Extract shared constraint-building logic from both solvers (Impact: L)

**Files**: `python/fpl_andres/optimization/highs.py` (`add_constraint` inner function,
lines 59–70; constraint blocks lines 72–121),
`python/fpl_andres/optimization/horizon.py` (`add_constraint` inner function, lines
61–72; constraint blocks lines 88–164),
`python/tests/test_highs_optimizer.py`, `python/tests/test_horizon_optimizer.py`

**Problem**: Both solvers define a nearly identical `add_constraint` inner function that
appends a dense row and two bound values to accumulator lists. The squad-count, lineup-
size, captain-count, position-bound, and club-limit constraint patterns are repeated in
both files. Any future change to these patterns must be applied twice, and the two
implementations can drift silently (as noted in the audit: "keep the two solvers
behaviourally identical"). There is no shared module that owns these constraint-building
primitives.

**Change**:

1. Create `python/fpl_andres/optimization/constraint_builder.py` exporting a
   `ConstraintAccumulator` class (or a plain helper function `add_constraint`) that
   owns the accumulator lists and the row-append logic.
2. Move the common squad-count, lineup-size, captain-count, position-bound, and
   club-limit helpers into named functions (`add_squad_count`, `add_lineup_bounds`,
   `add_captain_constraint`, `add_position_bounds`, `add_club_limit`) in that module,
   each taking the accumulator and the relevant indices/bounds as arguments.
3. Replace the duplicated inner functions in `highs.py` and `horizon.py` with calls
   to the shared helpers.
4. If item 34 (sparse matrix) is implemented first, make `ConstraintAccumulator`
   accumulate COO triplets rather than dense rows; otherwise keep it dense and note
   the dependency.

**Constraints**: The `OptimizationResult` and `HorizonOptimizationResult` contracts
must not change. Solver decisions must be identical; both oracle test suites serve as
the equivalence guarantee. The shared module must not import from `highs.py` or
`horizon.py` to avoid a circular dependency — it may only import from
`optimization/contracts.py` or standard library.

**Tests first**: Add `python/tests/test_constraint_builder.py`:

- `test_add_constraint_appends_row_lower_and_upper`: verify that a single call to
  the accumulator produces one row, one lower bound, and one upper bound.
- `test_squad_count_sets_equal_bounds`: verify that `add_squad_count` produces a row
  with `lower == upper == squad_size`.
- Existing oracle tests in `test_highs_optimizer.py` and `test_horizon_optimizer.py`
  serve as equivalence guarantees.

**Done when**:

1. Neither `highs.py` nor `horizon.py` defines its own `add_constraint` inner function.
2. Both solvers produce identical results to their respective oracle tests.
3. `python/tests/test_constraint_builder.py` tests pass.
4. `python -m pytest python/tests/test_highs_optimizer.py python/tests/test_horizon_optimizer.py python/tests/test_constraint_builder.py -q` is green.

**Validate**: `python -m pytest python/tests/test_highs_optimizer.py python/tests/test_horizon_optimizer.py -q`

---

## 40 — Split `simulation/minileague.py` into independently profilable modules (Impact: L)

**Files**: `python/fpl_andres/simulation/minileague.py` (813 lines total),
`python/tests/test_minileague.py`

**Problem**: `simulation/minileague.py` is the largest single-responsibility module in
the repository at 813 lines. It interleaves four distinct concerns without separation:
(1) the main season loop (`simulate_league`, lines 170–320), (2) rival policy
implementations (`_zombie_transfer`, `_take_transfers`, `_best_swap`, `_best_replacement`,
`_tilted_ranking`, lines 470–708), (3) chip planning (`_chip_plan`, `_choose_chip`,
lines 323–404), and (4) scoring and lineup logic (`_play`, `_starting_eleven`,
`_autosub`, `_outcomes`, lines 540–813). Because these are intermingled, profiling
identifies `simulate_league` as a single entry point rather than locating the expensive
sub-concern. It is also the hardest module in the repository to review in one sitting.

**Change**:

1. Extract the scoring and lineup helpers (`_play`, `_starting_eleven`, `_autosub`,
   `_outcomes`, `_recent_form`, `_recent_minutes`) into
   `python/fpl_andres/simulation/scoring.py`, keeping them as private module functions
   (no public `__all__` needed unless callers outside `minileague.py` exist).
2. Extract the policy transfer helpers (`_zombie_transfer`, `_take_transfers`,
   `_best_swap`, `_best_replacement`, `_settle`, `_squad_cost`) into
   `python/fpl_andres/simulation/policies.py`.
3. Extract chip logic (`_chip_plan`, `_choose_chip`) into the existing
   `python/fpl_andres/simulation/chips.py` if it does not break that module's
   existing `__all__`, or into a new `simulation/chip_plan.py` if it does.
4. `minileague.py` retains `simulate_league`, `_opening_squad`, `_sorted_by`,
   `_candidate_pool`, `_league_ownership`, `_prices_at`, and `_tilted_ranking`,
   importing from the new modules.
5. Update `__all__` in `minileague.py` to remain identical; no public API changes.

**Constraints**: `LeagueResult`, `LeagueSettings`, `ManagerResult`, `Policy`, and
`simulate_league` are the public API (`__all__` at line 47); none may be moved or
renamed. `python/tests/test_minileague.py` imports directly from
`fpl_andres.simulation.minileague` — do not break those imports. The existing
`test_simulation.py` may also import from this path; verify with `grep -r
"from fpl_andres.simulation" python/tests/`. No behavioural change: the same
`LeagueResult` must be produced for the same seed and corpus.

**Tests first**: in `python/tests/test_minileague.py`:

- Add `test_simulate_league_result_is_stable_across_refactor`: run `simulate_league`
  on a fixed deterministic corpus and seed before and after the refactor, asserting
  that `LeagueResult.standings()[0].net_points` and the policy distribution are
  identical. Since the refactor is structural only, this test can be written before
  the split and used as the regression guard.

**Done when**:

1. `minileague.py` is under 400 lines.
2. Each new module is under 300 lines.
3. All existing `test_minileague.py` and `test_simulation.py` tests pass unchanged.
4. The regression test passes.
5. `python -m pytest python/tests/test_minileague.py python/tests/test_simulation.py -q` is green.

**Validate**: `python -m pytest python/tests/test_minileague.py python/tests/test_simulation.py -q`
