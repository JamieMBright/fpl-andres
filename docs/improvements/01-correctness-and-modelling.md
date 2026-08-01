# 1. Correctness and modelling — work orders

Detailed briefs for items 1–18 of the [improvement audit](../../IMPROVEMENTS.md).
Each brief is self-contained: a sub-agent should be able to implement one item
from its brief alone.

Every brief obeys the repository rules: test-first (failing focused test, minimal
code, refactor), never default a missing controlling FPL rule (fail the source
contract visibly), keep `EvidenceLevel` and source timestamps attached to
recommendations, and nothing may exceed `docs/LIMITATIONS.md`.

---

## 1 — Treat zero free transfers as an explicit first-class state (Impact: H)

**Files**: `python/fpl_andres/optimization/contracts.py` (`OptimizationRequest`,
lines 144–190; `HorizonOptimizationRequest`, lines 286–371),
`python/fpl_andres/optimization/highs.py` (`HighsOptimizer.solve`, lines 39–294),
`python/tests/test_highs_optimizer.py`

**Problem**: `available_free_transfers` is typed `NonNegativeInt`, so zero is
accepted by validation. Inside `HighsOptimizer.solve` the transfer constraint is
`{squad_offset + index: 1.0 for index in incoming_indices} + {paid_transfer_index: -1.0}
≤ available_free_transfers` (line 144). When that value is zero the constraint
becomes "number of incoming players ≤ paid transfers", which is satisfiable — the
solver will simply charge for every transfer. There is no distinction between the
case where a manager truly has zero free transfers (all transfers are hits) and the
pathological case where the request is otherwise infeasible. A caller receives an
`OptimizationResult` with no indication that every transfer was charged. In horizon
mode the same field at line 310 drives a multi-event constraint chain with the
same gap.

**Change**:

1. Add a typed constant or `Literal` alias `ZeroFreeTransfers = Literal[0]` and
   introduce a predicate `is_hit_only(request)` in `optimization/contracts.py`
   that returns `True` when `available_free_transfers == 0`.
2. Propagate this signal into `OptimizationResult.reason_codes`: emit a
   `"hit_only_mode"` code whenever every incoming transfer is paid, alongside the
   existing `f"paid_transfers={paid_transfers}"` code.
3. Amend `OptimizationRequest.validate_request` to add an explicit comment (not
   code change) that zero free transfers is intentional and correctly handled by
   the constraint, so a future reader does not re-introduce a guard that silently
   rejects it.
4. Add the same `"hit_only_mode"` emission in `HighsHorizonOptimizer.solve` when
   the initial free-transfer count is zero.

**Constraints**: do not add a validation error for zero free transfers — it is a
valid state (mid-season manager with no rollover). Existing callers in
`python/tests/test_highs_optimizer.py` and `python/tests/test_horizon_optimizer.py`
must pass unmodified. Do not change the solver MIP formulation.

**Tests first**: in `python/tests/test_highs_optimizer.py`, add
`test_zero_free_transfers_emits_hit_only_reason_code` that builds a minimal
`OptimizationRequest` with `available_free_transfers=0`, runs
`HighsOptimizer.solve`, and asserts `"hit_only_mode"` is in the returned
`reason_codes`. Add a symmetric case to `test_horizon_optimizer.py`.

**Done when**:

- `"hit_only_mode"` appears in `reason_codes` for any solve where
  `available_free_transfers == 0`.
- The new tests pass; existing optimizer tests are unchanged.
- No solver MIP formulation is altered.
- `OptimizationResult` still validates cleanly with Pydantic.

**Validate**: `python -m pytest python/tests/test_highs_optimizer.py
python/tests/test_horizon_optimizer.py -q`

---

## 2 — Centralise the UTC-awareness guard (Impact: H)

**Files**: `python/fpl_andres/optimization/contracts.py` (`_require_utc`, line
542), `python/fpl_andres/models/minutes.py` (`_require_utc`, line 337),
`python/fpl_andres/models/player_rates.py` (`_require_utc`, line 284),
`python/fpl_andres/models/deployment.py` (`_require_utc`, line 436),
`python/fpl_andres/adapters/vaastav.py` (`_require_utc`, line 110),
`python/fpl_andres/models/walk_forward.py` (`_require_utc`, line 58),
`python/tests/test_contract_parity.py`

**Problem**: six separate private `_require_utc` implementations carry the same
body — `if value.tzinfo is None or value.utcoffset() != timedelta(0): raise
ValueError(...)` — but with differing signatures (some take `(value, label)`,
`walk_forward` takes `(value)` only, `vaastav` reverses the argument order to
`(label, value)`). A future change to the guard (e.g. accepting a named UTC
timezone whose `utcoffset()` is zero but `tzinfo` is not `UTC`) must be applied
in six places; one will inevitably be missed. `models/backtest.py` (lines 39, 60)
and `models/expected_points.py` (line 110) perform the same check inline without
a helper at all.

**Change**:

1. Create `python/fpl_andres/utils/time.py` and define `require_utc(value:
datetime, label: str) -> None` there, raising `ValueError` with the standard
   message `"{label} must be an aware UTC timestamp"`.
2. Export it from `python/fpl_andres/utils/__init__.py`.
3. Replace every private `_require_utc` definition and every inline UTC check
   across `contracts.py`, `models/minutes.py`, `models/player_rates.py`,
   `models/deployment.py`, `adapters/vaastav.py`, `models/walk_forward.py`,
   `models/backtest.py`, `models/expected_points.py`, and
   `optimization/contracts.py` with a call to `require_utc`.
4. For `walk_forward.py` (which omits the `label` argument), supply a descriptive
   label string, e.g. `"prediction_cutoff"`.

**Constraints**: all public error messages must remain byte-for-byte identical to
preserve existing tests that match on the message text. The function name must be
`require_utc` (public, importable) not `_require_utc` (private) since multiple
modules need it. Do not alter any model-validator logic beyond the
`_require_utc` calls.

**Tests first**: add `test_require_utc_rejects_naive` and
`test_require_utc_rejects_non_utc` to `python/tests/test_contract_parity.py` (or
a new `test_utils_time.py`), then run all existing tests to confirm the inline
refactor is transparent.

**Done when**:

- `grep -rn "def _require_utc" python/` returns zero results.
- `grep -rn "tzinfo is None" python/fpl_andres/` returns zero results outside of
  `utils/time.py`.
- All existing model and adapter tests pass unmodified.

**Validate**: `python -m pytest python/tests/ -q`

---

## 3 — Validate contiguous gameweek set in the backtest corpus (Impact: H)

**Files**: `python/fpl_andres/backtesting/corpus.py` (`SeasonCorpus`,
`load_season`, `require_gameweeks`, lines 74–329),
`python/tests/test_walk_forward.py`

**Problem**: `load_season` pages all rows into `SeasonCorpus.rows_by_gameweek`
without checking that the resulting set of gameweek keys is a contiguous integer
range. A database gap (e.g. GW18 missing because a postponed fixture was never
ingested) reduces every rolling aggregate — MAE, RMSE, Spearman — silently. The
existing helper `require_gameweeks(corpus, minimum)` (line 323) only checks the
count, not contiguity. The caller in `backtesting/projector.py` and
`backtesting/score.py` would proceed with a 37-element season silently scoring
as if 38 gameweeks had occurred.

**Change**:

1. Add a function `validate_gameweek_range(corpus: SeasonCorpus, *, expected:
range | None = None) -> None` in `corpus.py` that computes the expected
   contiguous range from `min(corpus.gameweeks)` to `max(corpus.gameweeks)` and
   raises `CorpusLoadError` (already defined at line 37) if any integer in that
   range is absent from `corpus.gameweeks`. If `expected` is provided, also
   validate against it.
2. Call `validate_gameweek_range` inside `load_season` after the stats rows are
   added (after line 263), so every consumer gets the guard for free.
3. Amend `require_gameweeks` to call `validate_gameweek_range` before returning,
   so callers that go through `require_gameweeks` also benefit.

**Constraints**: the 2019/20 season ran to GW47 (documented at `corpus.py`
line 31); the valid range spans up to 47, not 38. Do not hard-code 38.
`CorpusLoadError` is the correct error type; do not raise a plain `ValueError`.

**Tests first**: add `test_load_season_rejects_missing_gameweek` to
`python/tests/test_walk_forward.py`, constructing a `SeasonCorpus` manually with
GW2 absent and verifying `CorpusLoadError` is raised by
`validate_gameweek_range`. Add `test_contiguous_range_accepted` for a complete
consecutive range.

**Done when**:

- A corpus with a missing interior gameweek raises `CorpusLoadError` with a
  message naming the missing gameweek.
- A corpus with GWs 1–38 or 1–47 is accepted without error.
- `require_gameweeks` still returns the gameweek sequence for valid inputs.

**Validate**: `python -m pytest python/tests/test_walk_forward.py -q`

---

## 4 — Cross-validate `blend_full_weight_minutes` against `minimum_minutes` (Impact: H)

**Files**: `python/fpl_andres/models/player_rates.py` (`PlayerRateEvidence`,
lines 72–114, specifically fields at lines 86–88),
`python/tests/test_player_rates.py`

**Problem**: `PlayerRateEvidence` has two sourced parameters: `minimum_minutes`
(the sample floor below which projection returns `unavailable`, line 86) and
`blend_full_weight_minutes` (the current-season minutes at which the carried
season contributes nothing, line 88). Neither validation checks whether
`blend_full_weight_minutes > minimum_minutes`. If
`blend_full_weight_minutes ≤ minimum_minutes`, then a player with exactly
`minimum_minutes` of current-season history would already have `current_weight =
min(1.0, minimum_minutes / blend_full_weight_minutes) = 1.0`, i.e. the blend
weight saturates immediately and the carry-forward mechanism has no effect for any
player who clears the sample floor. This is an incoherent parameter combination
that should fail loudly, because it means sourced parameters are silently
contradictory.

**Change**:

1. Add a cross-field validation in `PlayerRateEvidence.validate_evidence` (after
   line 107) that raises `ValueError("blend_full_weight_minutes must exceed
minimum_minutes")` when `self.blend_full_weight_minutes <=
self.minimum_minutes`. This follows the established pattern of cross-field
   validators in that class.
2. Record the constraint and its rationale in `docs/MODEL.md` under the player
   rates section, noting that the rule is structural (not a tuning choice) and
   must be enforced at ingestion time.

**Constraints**: both parameters are sourced and must not be defaulted. The
validator must raise `ValueError`, not `RulesContractError`. No callers currently
supply a contradictory combination, so no existing tests need updating.

**Tests first**: add `test_blend_weight_minutes_must_exceed_minimum_minutes` to
`python/tests/test_player_rates.py` that constructs a `PlayerRateEvidence` with
`blend_full_weight_minutes=90.0` and `minimum_minutes=90.0` and asserts
`ValidationError` is raised (or `ValueError` if called directly). Add a passing
case with `blend_full_weight_minutes=91.0`.

**Done when**:

- `PlayerRateEvidence(... blend_full_weight_minutes=X, minimum_minutes=Y)` raises
  when `X ≤ Y`.
- The constraint is documented in `docs/MODEL.md`.
- All existing `test_player_rates.py` tests pass unmodified.

**Validate**: `python -m pytest python/tests/test_player_rates.py -q`

---

## 5 — Guard `None` before the chronology comparison in `SourceSnapshot` (Impact: H)

**Files**: `python/fpl_andres/contracts.py` (`SourceSnapshot.validate_chronology`,
lines 33–43), `python/tests/test_contract_parity.py`

**Verified**: `SourceSnapshot` declares both `fetched_at: datetime` and
`data_available_at: datetime` as required, non-optional Pydantic fields with
`strict=True`. Pydantic guarantees neither is `None` before `validate_chronology`
runs, so a `TypeError` from a `None` comparison cannot arise through the normal
Pydantic path.

The real gap is that `parse_source_snapshot` (line 50) accepts a raw `Mapping`
and calls `SourceSnapshot.model_validate` without first checking that
`fetched_at` and `data_available_at` are present and non-null. If either key is
missing the Pydantic error is an opaque `ValidationError` rather than a
recognisable contract error. More importantly, the UTC guard (lines 39–40) runs
before the chronology check (line 41); if a non-UTC timestamp passes `strict=True`
only at the field level, the validator order is correct — but the two checks are
separate `for` loops that could be collapsed.

**Change**:

1. In `parse_source_snapshot`, add an explicit pre-check that raises `ValueError`
   (not `ValidationError`) with a descriptive message if `fetched_at` or
   `data_available_at` is absent or `None` before calling `model_validate`.
2. Ensure the error type is `ValueError` so callers can catch it uniformly
   alongside the UTC guard.
3. Add a comment in `validate_chronology` explaining why the UTC guard precedes
   the chronology comparison — naive timestamps cannot be compared with UTC-aware
   ones without raising `TypeError`, so the UTC check is a pre-condition for the
   `>` comparison.

**Constraints**: do not alter the `SourceSnapshot` Pydantic field types. Do not
weaken strict validation. The public API of `parse_source_snapshot` must remain
`(object) -> SourceSnapshot`.

**Tests first**: add `test_parse_source_snapshot_missing_fetched_at` and
`test_parse_source_snapshot_missing_data_available_at` to
`python/tests/test_contract_parity.py`, asserting `ValueError` rather than
`ValidationError` for missing timestamp keys.

**Done when**:

- `parse_source_snapshot({"fetched_at": None, ...})` raises `ValueError` with a
  readable message.
- `parse_source_snapshot({"data_available_at": None, ...})` raises `ValueError`
  with a readable message.
- All existing `test_contract_parity.py` tests pass.

**Validate**: `python -m pytest python/tests/test_contract_parity.py -q`

---

## 6 — Reject unsorted or duplicate-event observation sequences (Impact: M)

**Files**: `python/fpl_andres/models/player_rates.py` (`PlayerRateEvidence`,
lines 94–108; `RateObservation`, lines 41–58),
`python/fpl_andres/models/minutes.py` (`MinutesEvidence.validate_evidence`, lines
98–108), `python/tests/test_player_rates.py`,
`python/tests/test_minutes_model.py`

**Problem**: `MinutesEvidence.validate_evidence` (line 105–107) rejects duplicate
`event_id`s in `observations` but does not require them to be sorted. The decay
weight loop at lines 168–172 of `minutes.py` constructs a dict keyed by
`event_id` and so is order-independent — but downstream code at lines 199–212
iterates `evidence.observations` directly (filtering `started`/`benched`) and
`_weighted_share` / `_weighted_mean` rely on the weights dict being built from the
same ordering. In `player_rates.py` neither duplicate nor ordering validation
exists for `current_season_observations` or `prior_season_observations`; the
recency-weighted version of carry-forward (`project_player_rates`, lines 147–213)
processes observations in tuple order, and an unsorted sequence would silently
produce a rate as if events occurred in a different order.

**Change**:

1. In `PlayerRateEvidence.validate_evidence` (after line 107), assert that
   `current_season_observations` and `prior_season_observations` are each sorted
   by `event_id` (ascending) and contain no duplicate `event_id` values. Raise
   `ValueError` with a message naming the offending sequence.
2. In `MinutesEvidence.validate_evidence` (after line 107), extend the existing
   duplicate check to also assert that `observations` are sorted by `event_id`.
   Raise `ValueError` for an out-of-order sequence.

**Constraints**: the existing duplicate check in `MinutesEvidence` (line 105–107)
must be preserved as-is and the ordering check added after it. The error type must
be `ValueError` in both cases. No change to the public function signatures.

**Tests first**: add to `test_player_rates.py`: `test_unsorted_observations_rejected`
(same `event_id` ascending requirement violated), and
`test_duplicate_event_id_rejected`. Add the same pair to `test_minutes_model.py`
for `MinutesEvidence`.

**Done when**:

- Constructing `PlayerRateEvidence` with observations in descending `event_id`
  order raises `ValueError`.
- Constructing `MinutesEvidence` with observations out of order raises
  `ValueError`.
- Constructing either with a duplicate `event_id` raises `ValueError`.
- All existing tests pass.

**Validate**: `python -m pytest python/tests/test_player_rates.py
python/tests/test_minutes_model.py -q`

---

## 7 — Validate `team_id` against the rules snapshot in optimisation requests (Impact: M)

**Files**: `python/fpl_andres/optimization/contracts.py`
(`OptimizationRequest.validate_request`, lines 159–190;
`HorizonOptimizationRequest.validate_horizon`, lines 300–371),
`python/fpl_andres/rules.py` (`RulesSnapshot`, lines 109–128),
`python/tests/test_highs_optimizer.py`

**Problem**: `OptimizationPlayer.team_id` (line 93) is a positive integer but is
never cross-checked against a known set of team IDs from the rules snapshot.
`OptimizationRules` (lines 54–84) encodes position constraints and a `club_limit`
but carries no roster of known `team_id` values. Inside `HighsOptimizer.solve`,
the club constraint is built by grouping all players into `team_indices` (lines
114–121 of `highs.py`) without any check that those team IDs are legitimate. A
player with a fabricated or stale `team_id` escapes the three-per-club constraint
entirely, which can produce illegal squads (e.g. four players from one club
recorded with the correct ID plus a fifth with an off-by-one ID).

**Change**:

1. Add an optional field `known_team_ids: frozenset[int] | None = None` to
   `OptimizationRules` (or as a separate field on `OptimizationRequest`).
2. In `OptimizationRequest.validate_request`, when `known_team_ids` is supplied,
   assert that every `player.team_id` is in `known_team_ids`, raising `ValueError`
   with the unknown ID in the message.
3. Document in `docs/MODEL.md` that `known_team_ids` should be sourced from the
   FPL bootstrap snapshot's teams list and that the field is not defaulted — a
   caller that cannot supply it omits it and gets no validation.
4. Propagate the same guard to `HorizonOptimizationRequest`.

**Constraints**: `known_team_ids` must be optional (backward-compatible); existing
callers that do not supply it receive no validation failure. Do not invent a
default set of team IDs. `RulesSnapshot` in `rules.py` has `club_limit` but no
team list; do not parse team IDs from it — they must come from the bootstrap
separately.

**Tests first**: add `test_unknown_team_id_rejected_when_known_ids_supplied` to
`test_highs_optimizer.py`, constructing an `OptimizationRequest` with one player
carrying a `team_id` not in `known_team_ids` and asserting `ValidationError`.
Add `test_unknown_team_id_accepted_when_known_ids_absent` to confirm backward
compatibility.

**Done when**:

- An `OptimizationRequest` with `known_team_ids={1,2,3}` and a player with
  `team_id=99` raises `ValidationError`.
- The same request without `known_team_ids` passes validation.
- Existing optimizer tests pass unmodified.

**Validate**: `python -m pytest python/tests/test_highs_optimizer.py -q`

---

## 8 — Make `FutureMinutesEvidenceError` part of the public error taxonomy (Impact: M)

**Files**: `python/fpl_andres/models/minutes.py` (`FutureMinutesEvidenceError`,
line 37; `__all__`, lines 342–350), `python/fpl_andres/models/__init__.py`,
`python/tests/test_minutes_model.py`

**Problem**: `FutureMinutesEvidenceError` is defined at line 37 of `minutes.py`
and already included in `__all__` (lines 342–350). However, no caller in the
workflow path (`backtesting/projector.py`, `cli/`, `adapters/`) catches it
explicitly — it propagates as an unhandled `ValueError` subclass and surfaces as
a traceback in a workflow run rather than a structured error. The audit notes "no
caller currently handles it". In addition, `FutureRateEvidenceError` (in
`player_rates.py`) has the same problem. Neither error type is re-exported from
`fpl_andres.models.__init__` or from any top-level package surface.

**Change**:

1. Re-export `FutureMinutesEvidenceError` from `python/fpl_andres/models/__init__.py`
   so callers can `from fpl_andres.models import FutureMinutesEvidenceError`
   without knowing the submodule.
2. Re-export `FutureRateEvidenceError` from the same file, treating it as the
   same class of error.
3. Add a section to `docs/MODEL.md` documenting both error types, their meaning
   (evidence arrived after the decision cutoff), and the expected caller handling
   (log and mark the projection as unavailable; do not silently ignore).
4. In at least one call site — `backtesting/projector.py`'s `project_gameweek` —
   add a `try/except (FutureMinutesEvidenceError, FutureRateEvidenceError)` that
   logs the failure and returns an `unavailable` projection rather than
   propagating.

**Constraints**: do not change the exception class hierarchy (both remain
`ValueError` subclasses). Do not suppress the error in tests. The re-export must
not change import paths that already work.

**Tests first**: add `test_future_evidence_error_is_importable_from_models` to
`test_minutes_model.py` that does `from fpl_andres.models import
FutureMinutesEvidenceError` and asserts `issubclass(FutureMinutesEvidenceError,
ValueError)`.

**Done when**:

- `from fpl_andres.models import FutureMinutesEvidenceError` succeeds.
- Both error types are documented in `docs/MODEL.md`.
- `project_gameweek` in `projector.py` handles the errors without traceback.

**Validate**: `python -m pytest python/tests/test_minutes_model.py -q`

---

## 9 — Deduplicate `_EVIDENCE_ORDER` across model modules (Impact: M)

**Files**: `python/fpl_andres/models/expected_points.py` (`_EVIDENCE_ORDER`,
lines 40–45), `python/fpl_andres/models/contracts.py` (`EvidenceLevel`, line 8),
`python/fpl_andres/models/player_rates.py`,
`python/fpl_andres/models/minutes.py`

**Verified**: `_EVIDENCE_ORDER` is defined only in `models/expected_points.py`
(lines 40–45). The audit claimed it appears in `player_rates.py` and `minutes.py`
as well — those files do not define `_EVIDENCE_ORDER` but do import and use
`EvidenceLevel`. The `_worst` helper (line 263–264 of `expected_points.py`) is
also local to that module. The actual risk is that any future module that needs
`_worst` or `_EVIDENCE_ORDER` will re-implement it independently.

**Change**:

1. Move `_EVIDENCE_ORDER: dict[EvidenceLevel, int]` and the `_worst(*levels:
EvidenceLevel) -> EvidenceLevel` helper from `models/expected_points.py` to
   `models/contracts.py`, making them module-level names there (the ordering
   constant can remain private; the `_worst` helper can be exported as
   `worst_evidence_level` for callers who need it).
2. Update `models/expected_points.py` to import from `models/contracts.py`
   instead.
3. Add `worst_evidence_level` to `models/contracts.py`'s `__all__` if that file
   has one, or document it in `docs/MODEL.md`.

**Constraints**: the behaviour of `_worst` must be identical: it returns the
`EvidenceLevel` with the highest `_EVIDENCE_ORDER` value. Existing tests in
`test_expected_points.py` must pass unmodified (no public API change). The
constant must not be imported into `player_rates.py` or `minutes.py` unless those
modules need it (do not add unnecessary imports).

**Tests first**: add `test_evidence_order_is_canonical` to
`test_expected_points.py` asserting `_worst("observed", "inferred") == "inferred"`
and `_worst("observed", "unavailable") == "unavailable"`, and confirming the
function still lives in `models/contracts.py` after the move.

**Done when**:

- `grep -rn "_EVIDENCE_ORDER" python/fpl_andres/` returns exactly one definition
  (in `models/contracts.py`).
- All `test_expected_points.py` tests pass.

**Validate**: `python -m pytest python/tests/test_expected_points.py -q`

---

## 10 — Deduplicate position-name mappings between `deployment.py` and `score.py` (Impact: M)

**Files**: `python/fpl_andres/models/deployment.py` (`_POSITION_GROUP`, lines
30–35), `python/fpl_andres/backtesting/score.py` (`_POSITION_NAMES`, line 30),
`python/fpl_andres/models/contracts.py`

**Problem**: `deployment.py` defines `_POSITION_GROUP: dict[ListedPosition, int]
= {"GKP": 0, "DEF": 1, "MID": 2, "FWD": 3}` (lines 30–35). `score.py` defines
`_POSITION_NAMES: dict[int, str] = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}`
(line 30) — the inverse mapping, with a different key range (1–4 vs 0–3). These
are two representations of the same FPL rule: four positions with integer type
codes. A change to the FPL position list (unlikely but not impossible) requires
updating both maps separately, and the different offset convention (0-based vs
1-based) is a latent confusion source.

**Change**:

1. Define a single authoritative mapping in `models/contracts.py`:
   `POSITION_TYPE_CODES: dict[str, int] = {"GKP": 1, "DEF": 2, "MID": 3, "FWD":
4}` using the FPL API's own 1-based `element_type` values. Add
   `POSITION_TYPE_NAMES: dict[int, str] = {v: k for k, v in
POSITION_TYPE_CODES.items()}`.
2. Update `deployment.py` to derive `_POSITION_GROUP` from `POSITION_TYPE_CODES`
   (normalising to 0-based by subtracting 1, or switching entirely to 1-based).
3. Update `score.py` to use `POSITION_TYPE_NAMES` imported from `models/contracts`.
4. Export both from `models/contracts.py`'s `__all__`.

**Constraints**: the FPL API uses 1-based `element_type` codes (GKP=1, DEF=2,
MID=3, FWD=4) as sourced from the bootstrap payload; do not invent a mapping that
contradicts the API. The `_DEPLOYMENT_CLASSIFICATION` dict in `deployment.py`
is keyed by `(ListedPosition, ObservedRole)` strings, not integers — preserve
that; only `_POSITION_GROUP` uses the integer offset. Existing tests for
`test_deployment_signal.py` and `test_backtest.py` must pass unmodified.

**Tests first**: add `test_position_names_consistent_with_group` to a new
`test_models_contracts.py` asserting that `POSITION_TYPE_NAMES` is the inverse of
`POSITION_TYPE_CODES` and that both cover exactly `{"GKP", "DEF", "MID", "FWD"}`.

**Done when**:

- `grep -rn "_POSITION_NAMES\|_POSITION_GROUP" python/fpl_andres/` returns zero
  definition sites (both replaced by imports of the shared constants).
- All `test_deployment_signal.py` and `test_backtest.py` tests pass.

**Validate**: `python -m pytest python/tests/test_deployment_signal.py
python/tests/test_backtest.py -q`

---

## 11 — Make `_BENCH_WEIGHT` and `PLAYABLE_START_RATE` injectable sourced parameters (Impact: M)

**Files**: `python/fpl_andres/planning/opening.py` (`_BENCH_WEIGHT`, line 33;
`PLAYABLE_START_RATE`, lines 38–39; `OpeningSettings`, lines 44–51),
`python/fpl_andres/simulation/season.py` (no `_BENCH_WEIGHT` defined here —
**correction: see below**), `python/tests/test_opening_squad.py`

**Verified**: `_BENCH_WEIGHT = 0.25` and `PLAYABLE_START_RATE = 0.35` are both in
`python/fpl_andres/planning/opening.py` (lines 33 and 38). `OpeningSettings`
already exposes `bench_weight: float = _BENCH_WEIGHT` and `playable_start_rate:
float = _PLAYABLE_START_RATE` as injectable fields (lines 50–51). The audit's
reference to `simulation/season.py` for `_BENCH_WEIGHT` is stale — that file does
not define the constant.

The current `OpeningSettings` allows override at runtime but the module-level
constants remain as magic numbers with no source reference. The comment at line
29–32 says the bench weight is "assumed, not measured" — but this is precisely the
kind of parameter that must be sourced (or explicitly documented as an assumption
with an `EvidenceLevel`).

**Change**:

1. Add a `source_reference: str | None = None` field to `OpeningSettings` and
   document it in the class docstring: when `None`, the parameter is an
   assumption; when supplied, it names the analysis or document that justifies the
   value.
2. In `docs/MODEL.md`, add a row for `bench_weight` and `playable_start_rate`
   under "Opening squad" noting the current assumed values, their rationale, and
   that a season of squad data would be required to measure them.
3. Add a `validate_settings` method to `OpeningSettings` that raises `ValueError`
   if `bench_weight` is not in `(0.0, 1.0)` or `playable_start_rate` is not in
   `[0.0, 1.0]`, making the bounds explicit.

**Constraints**: the module-level defaults (`_BENCH_WEIGHT`, `PLAYABLE_START_RATE`)
must be retained so that callers using `OpeningSettings()` with no arguments
still work. Do not remove the public export `PLAYABLE_START_RATE` from `__all__`.

**Tests first**: add `test_opening_settings_rejects_out_of_range_bench_weight` to
`test_opening_squad.py`, asserting `ValueError` for `bench_weight=1.5`. Add
`test_opening_settings_accepts_source_reference`.

**Done when**:

- `OpeningSettings(bench_weight=1.5)` raises `ValueError`.
- `docs/MODEL.md` documents both parameters with their current assumed values.
- Existing `test_opening_squad.py` tests pass unmodified.

**Validate**: `python -m pytest python/tests/test_opening_squad.py -q`

---

## 12 — Extract named constraint builders from `HighsHorizonOptimizer.solve` (Impact: M)

**Files**: `python/fpl_andres/optimization/horizon.py`
(`HighsHorizonOptimizer.solve`, lines 24–481),
`python/tests/test_horizon_optimizer.py`

**Problem**: `HighsHorizonOptimizer.solve` is ~457 lines of nested indexing and
local closures (`variable`, `add_constraint`, `optimize`) with no internal
seams. The constraint blocks for budget, club limit, formation, free-transfer
accounting and bank tracking are all inlined. This makes it impossible to unit
test individual constraint blocks in isolation: a bug in the bank constraint
cannot be reproduced without constructing a full `HorizonOptimizationRequest`.

**Change**:

1. Extract the following named functions from inside `solve` (keeping them in the
   same module, below the class, prefixed `_horizon_`):
   - `_horizon_formation_constraints(...)` — position squad and lineup bounds.
   - `_horizon_club_constraints(...)` — per-club player limit.
   - `_horizon_budget_constraint(...)` — per-event budget and bank tracking.
   - `_horizon_transfer_constraints(...)` — free-transfer accounting, paid
     transfers, cap.
2. Each builder receives the pre-computed index maps (`player_index`, `forecasts`,
   variable offsets) and an `add_constraint` callable, returns nothing (mutations
   via the callable), and has a typed signature.
3. `solve` delegates to these builders in sequence, replacing the current inline
   blocks.

**Constraints**: the behaviour of `solve` must be identical — the existing
`test_horizon_optimizer.py` tests must pass without modification. Do not change
the public API (`HighsHorizonOptimizer`, `solve`, `HorizonOptimizationRequest`,
`HorizonOptimizationResult`). Do not share constraint builders with
`highs.py`; that refactor is item 39 (a separate change).

**Tests first**: add `test_horizon_formation_constraints_alone` to
`test_horizon_optimizer.py` that calls `_horizon_formation_constraints` with
stub inputs and asserts the correct number of constraint rows are added. Repeat
for `_horizon_club_constraints`.

**Done when**:

- `HighsHorizonOptimizer.solve` body is ≤200 lines excluding the extracted
  functions.
- Each extracted builder has a unit test that does not require a full solve.
- All existing `test_horizon_optimizer.py` tests pass unmodified.

**Validate**: `python -m pytest python/tests/test_horizon_optimizer.py -q`

---

## 13 — Split `backtesting/projector.py` along its natural seams (Impact: M)

**Files**: `python/fpl_andres/backtesting/projector.py` (882 lines),
`python/tests/test_walk_forward.py`, `python/tests/test_baselines.py`

**Problem**: `projector.py` at 882 lines contains three distinct concerns that are
currently interleaved: (1) feature assembly from corpus rows into model evidence
objects (`MinutesEvidence`, `PlayerRateEvidence`); (2) running the model stack
(`project_minutes`, `project_player_rates`) and composing `ElementProjection`; (3)
baseline computations (`baseline_recent_mean`, `baseline_ownership`). Reviewing or
modifying one concern requires understanding all three. The file is the largest in
the repository.

**Change**:

1. Create `python/fpl_andres/backtesting/features.py` containing the evidence
   assembly functions: the logic that transforms `ElementRow` sequences into
   `MinutesEvidence` and `PlayerRateEvidence` objects (including
   `ProjectionSettings`, prior assembly, and observation filtering).
2. Create `python/fpl_andres/backtesting/baselines.py` (or extend the existing
   `python/fpl_andres/models/baselines.py`) containing `baseline_recent_mean` and
   `baseline_ownership`.
3. Retain `projector.py` for the orchestration: `project_gameweek`,
   `project_horizon`, and `ElementProjection` — using the new modules.
4. Update `__all__` in each file and fix all imports in `score.py`,
   `test_walk_forward.py`, and `test_baselines.py`.

**Constraints**: the split is a refactor — no logic changes. Existing solver tests
must pass unmodified. The invariant that proves behaviour is unchanged is: every
existing test in `test_walk_forward.py` passes before and after the split.
`baseline_recent_mean` and `baseline_ownership` must remain importable from
`backtesting.projector` via `__all__` (or explicit re-export) for backward
compatibility.

**Tests first**: no new tests are needed if the existing suite serves as the
invariant. Confirm by running `test_walk_forward.py` and `test_baselines.py` both
before and after the split.

**Done when**:

- `projector.py` is ≤400 lines.
- `features.py` is the sole site of evidence assembly.
- All existing walk-forward and baseline tests pass unmodified.

**Validate**: `python -m pytest python/tests/test_walk_forward.py
python/tests/test_baselines.py -q`

---

## 14 — Replace position `Literal` codes with an enum in `models/deployment.py` (Impact: L)

**Files**: `python/fpl_andres/models/deployment.py` (`ListedPosition`, line 11),
`python/fpl_andres/models/contracts.py`, `python/tests/test_deployment_signal.py`

**Problem**: `ListedPosition = Literal["GKP", "DEF", "MID", "FWD"]` (line 11 of
`deployment.py`) is used as a type alias but cannot be iterated exhaustively or
matched with `match` statements in Python 3.10+. Every caller that needs to check
all four positions must write them out again as a tuple or set, which is a
duplication hazard. An `enum.StrEnum` (available from Python 3.11, or
`enum.Enum` with `str` mixin in 3.10) provides `__members__` for exhaustive
iteration and plays well with Pydantic's `strict=True` mode.

**Change**:

1. Define `class ListedPosition(str, enum.Enum): GKP = "GKP"; DEF = "DEF"; MID =
"MID"; FWD = "FWD"` in `models/contracts.py` (near `EvidenceLevel`).
2. Replace the `Literal` alias in `deployment.py` with an import of the new enum.
3. Confirm that Pydantic accepts the enum in `strict=True` models by running
   existing tests; adjust `model_config` if Pydantic requires `use_enum_values=True`.
4. Update `score.py`'s `_POSITION_NAMES` (or the shared constant from item 10)
   to key on `ListedPosition` enum members.

**Constraints**: string values of the enum members must remain `"GKP"`,
`"DEF"`, `"MID"`, `"FWD"` — Pydantic serialises them as strings; no JSON schema
changes. Existing tests must pass without modification.

**Tests first**: add `test_listed_position_is_exhaustive` to
`test_deployment_signal.py` asserting `len(ListedPosition) == 4` and that
`ListedPosition("GKP")` returns the correct member.

**Done when**:

- `ListedPosition` is a `str`-enum importable from `models/contracts.py`.
- `deployment.py` imports it from there.
- All `test_deployment_signal.py` tests pass.

**Validate**: `python -m pytest python/tests/test_deployment_signal.py -q`

---

## 15 — Name the tie-break coefficients in `optimization/highs.py` (Impact: L)

**Files**: `python/fpl_andres/optimization/highs.py`
(`HighsOptimizer.solve`, lines 199–207)

**Problem**: the three inline literals `1e-9`, `1e-11`, `1e-13` at lines 202–206
already carry inline comments, but the comments describe the _effect_ ("prefer
lower element indices") rather than the _invariant_ that makes the magnitudes
safe. For the tie-break to be transparent it must be provably smaller than the
smallest non-zero score difference it can encounter. A future change to expected
points scale could violate the implicit assumption.

**Change**:

1. Extract three module-level named constants:
   `_SQUAD_TIEBREAK_SCALE = 1e-9`, `_LINEUP_TIEBREAK_SCALE = 1e-11`,
   `_CAPTAIN_TIEBREAK_SCALE = 1e-13`.
2. Replace the inline literals with the named constants at lines 202–206.
3. Add a block comment above the constants (in the module header, after
   `_MIP_FEASIBILITY_TOLERANCE`) explaining: (a) why three levels are needed
   (lexicographic ordering: squad, then lineup, then captain), (b) the assumption
   that the smallest meaningful expected-points difference is ≥ 0.001, (c) why
   `1e-9 * player_count` (at most `1e-9 * 700 ≈ 7e-7`) remains below that floor.

**Constraints**: the numerical values must not change. The comment must state the
invariant explicitly so a future change to expected-points scale triggers a
review. No test changes are needed.

**Tests first**: no new tests required; the existing `test_highs_optimizer.py`
suite already covers tie-break behaviour indirectly. Add an assertion that
`_SQUAD_TIEBREAK_SCALE < _LINEUP_TIEBREAK_SCALE ** 0.5` to document the ordering.

**Done when**:

- No bare `1e-9`, `1e-11`, `1e-13` literals appear in the tie-break block.
- The block comment states the invariant.
- All existing optimizer tests pass.

**Validate**: `python -m pytest python/tests/test_highs_optimizer.py -q`

---

## 16 — Document `_optimum_slack` in `optimization/highs.py` (Impact: L)

**Files**: `python/fpl_andres/optimization/highs.py` (`_optimum_slack`, lines
28–30; `_MIP_FEASIBILITY_TOLERANCE`, line 25)

**Verified**: `_optimum_slack` already has a one-line docstring (`"Slack for
re-solving against a proven optimum, scaled to its magnitude."`) at line 29. The
comment block at lines 21–24 explains why re-solving is necessary. However, the
docstring does not document the two-part tolerance formula —
`max(_MIP_FEASIBILITY_TOLERANCE, abs(optimum) * 1e-9)` — or why both an absolute
floor and a relative component are required.

**Change**:

1. Expand the `_optimum_slack` docstring to three to five sentences covering: (a)
   the absolute floor equals `_MIP_FEASIBILITY_TOLERANCE` (1e-6) so that the
   re-solve is never tighter than HiGHS's own feasibility tolerance; (b) the
   relative term `abs(optimum) * 1e-9` grows with the objective so that rounding
   at larger magnitudes does not invalidate the bound; (c) the two-part formula is
   load-bearing for every optimality claim the solver makes, so changing either
   constant requires re-running the test suite.
2. Add a reference to `_MIP_FEASIBILITY_TOLERANCE` in the docstring by name so
   the dependency is explicit.

**Constraints**: do not change the implementation. Do not change the constant
values. The docstring must be a standard Python docstring (triple-quoted),
not a comment.

**Tests first**: no new tests required. The existing optimizer tests that verify
`solver_status == "optimal"` implicitly test the tolerance.

**Done when**:

- `_optimum_slack.__doc__` contains the words "absolute floor" and "relative"
  (or equivalent phrasing) explaining both components.
- `python -m pytest python/tests/test_highs_optimizer.py -q` passes.

**Validate**: `python -m pytest python/tests/test_highs_optimizer.py -q`

---

## 17 — Rename mixed `*_offset` / `*_index` variables in `optimization/highs.py` (Impact: L)

**Files**: `python/fpl_andres/optimization/highs.py`
(`HighsOptimizer.solve`, lines 42–46)

**Problem**: lines 42–46 define:

```
squad_offset = 0
lineup_offset = player_count
captain_offset = 2 * player_count
paid_transfer_index = 3 * player_count
variable_count = paid_transfer_index + 1
```

Three variables use the suffix `_offset` (the start of a block of player-wide
binary variables) while `paid_transfer_index` uses `_index` (a single scalar
variable at position `3 * player_count`). The naming conflates two concepts: a
block start offset (used as `offset + player_index` to reach a per-player
variable) and a scalar variable index (used directly). A reader must realise that
`paid_transfer_index` does not have a per-player dimension.

**Change**:

1. Rename `paid_transfer_index` to `paid_transfer_col` throughout `solve` to make
   clear it is a column index into the LP variable vector, not a block offset.
2. Optionally add a comment after line 46 clarifying: `squad_offset`,
   `lineup_offset`, `captain_offset` are block starts (each block has
   `player_count` columns); `paid_transfer_col` is a single scalar column.

**Constraints**: purely a rename — no logic change. All references to
`paid_transfer_index` in `solve` must be updated (approximately 8 occurrences:
lines 45, 46, 53, 141, 142, 153, 179–185). The variable value in the MIP and the
objective coefficient must be unchanged.

**Tests first**: no new tests. Run the existing suite to confirm the rename is
transparent.

**Done when**:

- `grep -n "paid_transfer_index" python/fpl_andres/optimization/highs.py` returns
  zero results.
- All existing optimizer tests pass.

**Validate**: `python -m pytest python/tests/test_highs_optimizer.py -q`

---

## 18 — Standardise validation message wording in `rules.py` (Impact: L)

**Files**: `python/fpl_andres/rules.py` (`_required_int`, line 418;
`_required_number`, line 422–425; `_required_nullable_int`, line 441),
`python/tests/test_rules_snapshot.py`

**Problem**: `_required_int` raises `RulesContractError` with message
`"{path} must be an integer"` (line 418), while `_required_number` raises
`"{path} must be numeric"` (line 425). Both describe a type constraint on a rules
payload field, but use different vocabulary ("integer" vs "numeric"). A caller
that catches `RulesContractError` and pattern-matches the message text for
diagnostics must handle two phrasings for the same class of failure. The
`_required_nullable_int` message at line 441 uses a third variant: `"must be an
integer or null"`.

**Change**:

1. Standardise the three messages to a single template `"{path} must be a valid
{type_name}"` where `type_name` is `"integer"`, `"number"`, or `"integer or
null"`.
2. Alternatively, align all three to the same prefix `"must be"` followed by a
   consistent type description.
3. Update any test in `test_rules_snapshot.py` that matches error message text to
   use the new wording.

**Constraints**: `RulesContractError` must remain the raised type. The change is
cosmetic — no logic or API changes. Grep for any test that `.match`es or
`.assertIn`s message substrings and update them.

**Tests first**: add `test_required_int_and_number_messages_consistent` to
`test_rules_snapshot.py` that calls `_required_int` and `_required_number` with
the same non-conforming value and asserts both messages begin with the same prefix.

**Done when**:

- `_required_int`, `_required_number` and `_required_nullable_int` raise messages
  that share a common prefix.
- All `test_rules_snapshot.py` tests pass with updated message assertions.

**Validate**: `python -m pytest python/tests/test_rules_snapshot.py -q`
