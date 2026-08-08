# Parameter provenance

The repository has one rule that overrides everything else:

> Never default a missing controlling FPL rule; fail its source contract visibly.

That rule is only auditable if someone can look up any number the model uses and
find out where it came from. This is that lookup.

Every parameter is in one of four states. The state matters more than the value:

| State        | Meaning                                                        |
| ------------ | -------------------------------------------------------------- |
| **FPL rule** | Published by the game. Not ours to choose.                     |
| **Measured** | Fitted or checked against data, with the measurement recorded. |
| **Caller**   | A contract field with no default. Missing it raises.           |
| **Assumed**  | Chosen by judgement. No measurement behind it.                 |

**Assumed is not a failure state.** Some numbers cannot be measured before the
season that would measure them. It is a failure state to have one and not say so,
because an assumed number presented as a measured one is the thing this document
exists to prevent.

`python/tests/test_parameter_provenance.py` fails if a value here disagrees with
the code, so this file cannot drift out of date the way `MODEL.md`'s prior table
did — see the note at the end.

---

## Caller-supplied: the model refuses to invent these

These are Pydantic fields with no default. Omitting one is a `ValidationError`
before any projection happens, which is the mechanism the repository rule
describes.

| Parameter                                   | Contract                               |
| ------------------------------------------- | -------------------------------------- |
| `decay_half_life_events`                    | `MinutesEvidence`                      |
| `minimum_observations`                      | `MinutesEvidence`                      |
| `prior_start_rate`                          | `MinutesEvidence`                      |
| `prior_strength_events`                     | `MinutesEvidence`                      |
| `RatePrior.goals_per_90`                    | `PlayerRateEvidence`                   |
| `RatePrior.assists_per_90`                  | `PlayerRateEvidence`                   |
| `RatePrior.strength_minutes`                | `PlayerRateEvidence`                   |
| `minimum_minutes`                           | `PlayerRateEvidence`                   |
| `blend_full_weight_minutes`                 | `PlayerRateEvidence`                   |
| `carried_context_weight`                    | `PlayerRateEvidence`                   |
| `decay_rate`, `minimum_matches`             | `DixonColesModel.fit`                  |
| `thresholds`, `source_reference`            | `SuspensionRules` — "no default"       |
| `budget_tenths`, `club_limit`               | `SquadRules` — "never inferred"        |
| formation bounds                            | `LineupRules` — "never inferred"       |
| `weekly_free_transfers` and siblings        | `TransferRulesAddendum` — needs a hash |
| `squad_size`, `lineup_size`, `transfer_cap` | `OptimizationRules` — needs a hash     |
| membership rules                            | `CohortCriteria` — "never inferred"    |
| `resamples`, `seed`, `confidence`           | `evaluate_promotion`                   |

`project_expected_points` treats absent optional components the same way: a
missing `expected_saves_per_90` produces a `missing_components` marker rather
than a zero, so a partial projection is visibly partial.

---

## Measured

Values with the measurement recorded next to them in the code.

| Parameter                    | Value | Where                       | Measurement                                                                            |
| ---------------------------- | ----- | --------------------------- | -------------------------------------------------------------------------------------- |
| `_QUALITY_PRIOR_SHOTS`       | 10.0  | `models/shot_profile.py`    | Fitted on 553 season pairs. MAE 0.05608 at k=0, 0.05435 at 10, 0.05821 at 100.         |
| `_VOLUME_REGRESSION`         | 0.1   | `models/shot_profile.py`    | MAE 0.05435 to 0.05417.                                                                |
| `recent_form_weight`         | 0.2   | `backtesting/projector.py`  | Correlation measured at 0.7–0.8 in all seven corpus seasons independently.             |
| `_POISSON_SIGMAS`            | 12.0  | `models/expected_points.py` | Keeps residual mass below 1e-12 at every rate; 10 measured short at 1.6e-12.           |
| `_MINUTES_TOLERANCE`         | 0.10  | `crosswalk/resolve.py`      | Worst honest Understat 2025-26 disagreement was ~5%. 10% leaves headroom.              |
| `_CONTRADICTION_TOLERANCE`   | 1e-6  | `models/penalties.py`       | Understat publishes xG at full float precision; this allows float noise only.          |
| `_MIP_FEASIBILITY_TOLERANCE` | 1e-6  | `optimization/highs.py`     | HiGHS' own documented default.                                                         |
| Scoring routes               | —     | `backtesting/projector.py`  | 2025-26 reconciles to 34,383 against an actual 34,382; 27,353/27,605 exact in 2024-25. |

---

## FPL rules

Published by the game. A change here is a rule change, not a tuning decision.

| Parameter                                   | Value                                  |
| ------------------------------------------- | -------------------------------------- |
| `_FULL_MATCH_MINUTES`                       | 90                                     |
| `_APPEARANCE_POINT_THRESHOLD`               | 60                                     |
| `_HIT_POINTS` / `_TRANSFER_HIT_POINTS`      | 4                                      |
| `club_limit`                                | 3                                      |
| squad size / lineup size                    | 15 / 11                                |
| position counts                             | 2 / 5 / 5 / 3                          |
| lineup minima and maxima                    | 1-1, 3-5, 2-5, 1-3                     |
| `free_transfers_per_event` / max            | 1 / 5                                  |
| `_SECOND_HALF_FIRST_EVENT` / `_FINAL_EVENT` | 20 / 38                                |
| `_NORMAL_FIXTURE_COUNT`                     | 10 (20 clubs / 2)                      |
| `MAX_EVENT`                                 | 47 — 2019/20 was suspended and resumed |

---

## Assumed

**No measurement stands behind these.** Each is a judgement call. They are listed
so the judgement is visible and can be challenged, and so nobody mistakes one for
a fitted value.

### Flagged as assumed in the code already

| Parameter                | Value | Where                      | Note                                                                                                                                                                                                                                                                                                                                                                     |
| ------------------------ | ----- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `_BENCH_WEIGHT`          | 0.25  | `planning/opening.py`      | Fallback only. The publishers pass appearance chances instead and `bench_weights` derives each bench place from the chance its cover is needed, so the first substitute and the fourth are no longer priced alike.                                                                                                                                                       |
| `_BOOKING_PRIOR_MATCHES` | 19.0  | `backtesting/projector.py` | Assumed, not measured. How many league-average matches a player's own card record is weighed against, so five appearances cannot claim a discipline record.                                                                                                                                                                                                              |
| `PLAYABLE_START_RATE`    | 0.35  | `planning/opening.py`      | Reasoned from two examples, not fitted.                                                                                                                                                                                                                                                                                                                                  |
| `carried_context_weight` | 0.6   | `backtesting/projector.py` | Audit #29. How much of a carried season survives a change of club or role. A **Caller** field on `PlayerRateEvidence` with no default; this is the value the backtester passes. A move changes the service, the set pieces and the penalty order, but the player does not become a different player. Applied only when the change is known, never on an unknown context. |

### Not flagged anywhere until now

| Parameter                      | Value            | Where                        | What it controls                                                                                               |
| ------------------------------ | ---------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------- |
| defensive-contribution damping | 0.5              | `backtesting/fixtures.py`    | How much fixture pressure reaches the defcon multiplier. The only wholly unexplained number in the model path. |
| `_PRIOR_MATCHES`               | 10.0             | `backtesting/fixtures.py`    | Strength of the home/away split prior.                                                                         |
| `_MIN_MULTIPLIER`              | 0.4              | `backtesting/fixtures.py`    | Floor on any fixture multiplier.                                                                               |
| `_MAX_MULTIPLIER`              | 2.2              | `backtesting/fixtures.py`    | Ceiling on any fixture multiplier.                                                                             |
| `prior_strength_events`        | 2.0              | `backtesting/projector.py`   | Beta-binomial prior weight for starts.                                                                         |
| `prior_start_rate`             | 0.35             | `backtesting/projector.py`   | Start probability before evidence.                                                                             |
| `recent_form_window`           | 5                | `backtesting/projector.py`   | Matches counted as "recent".                                                                                   |
| `_POISSON_FLOOR`               | 15               | `models/expected_points.py`  | Minimum truncation point.                                                                                      |
| `_MINIMUM_MATCHES`             | 5                | `models/suspensions.py`      | Below this a booking rate is noise.                                                                            |
| `_MINIMUM_PAIRS`               | 20               | `models/benchmark.py`        | Below this a rank correlation is not reported.                                                                 |
| `MINIMUM_RANKED_OBSERVATIONS`  | 3                | `models/metrics.py`          | Below this a correlation is undefined.                                                                         |
| `_RETURN_THRESHOLD`            | 5                | `backtesting/reliability.py` | What counts as a return.                                                                                       |
| `_BLANK_CEILING`               | 2                | `backtesting/reliability.py` | What counts as a blank.                                                                                        |
| `_MINIMUM_APPEARANCES`         | 4                | `backtesting/reliability.py` | Sample floor for reliability.                                                                                  |
| floor / median / ceiling       | 0.2 / 0.5 / 0.9  | `backtesting/reliability.py` | Percentiles published as the range.                                                                            |
| `_MINUTES_FLOOR`               | 45               | `crosswalk/resolve.py`       | Absolute minutes tolerance for short appearances.                                                              |
| `_MINIMUM_MINUTES`             | 270              | `crosswalk/resolve.py`       | Below this a crosswalk match is not attempted.                                                                 |
| `margin`                       | 0.5              | `planning/transfers.py`      | Points a transfer must beat to be worth the churn.                                                             |
| `horizon` / `max_moves`        | 5 / 6            | `planning/transfers.py`      | Planning depth and breadth.                                                                                    |
| `risk_weight`                  | 0.3              | `simulation/minileague.py`   | How much variance a rival policy accepts.                                                                      |
| `advised_share`                | 0.25             | `simulation/minileague.py`   | Share of simulated managers following advice.                                                                  |
| `start_gameweek`               | 7                | `simulation/minileague.py`   | Where a simulated season begins.                                                                               |
| `triple_captain_floor`         | 7.0              | `simulation/minileague.py`   | Chip-burn threshold.                                                                                           |
| `bench_boost_floor`            | 12.0             | `simulation/minileague.py`   | Chip-burn threshold.                                                                                           |
| `wildcard_floor`               | 12.0             | `simulation/minileague.py`   | Chip-burn threshold.                                                                                           |
| `free_hit_floor`               | 12.0             | `simulation/minileague.py`   | Chip-burn threshold.                                                                                           |
| `_FORM_WINDOW`                 | 4                | `simulation/minileague.py`   | Rival form window.                                                                                             |
| `_DROPPED_THRESHOLD`           | 3                | `simulation/minileague.py`   | Rival drop rule.                                                                                               |
| `rank_ceiling`                 | 10,000           | `cohorts/sweep.py`           | Owner-defined "elite" cutoff.                                                                                  |
| Dixon-Coles optimiser bounds   | ±4.0, ±2.0, ±0.2 | `models/dixon_coles.py`      | Parameter search box.                                                                                          |

The chip floors are the ones most worth challenging: four thresholds, three of
them identical, none of them measured, each deciding when a once-a-season
resource is spent.

---

## Positional priors

`_GOAL_PRIOR` and `_ASSIST_PRIOR` in `backtesting/projector.py`, per 90:

| Position | goals/90 | assists/90 |
| -------- | -------- | ---------- |
| GKP      | 0.00     | 0.00       |
| DEF      | 0.05     | 0.06       |
| MID      | 0.12     | 0.13       |
| FWD      | 0.28     | 0.12       |

Described in code as "sourced from league-wide long-run rates rather than tuned,
so the backtest cannot flatter itself by fitting them". The rates are not cited
to a specific published table, so they sit between _measured_ and _assumed_: the
method is stated, the source is not.

**These numbers were wrong in `docs/MODEL.md` until this document was written.**
It listed MID at 0.10 and FWD at 0.22 against the code's 0.12 and 0.28 — a 20%
and 27% understatement of the value every player's rate is pulled toward. Nothing
compared the two, so the documentation had been describing a different model from
the one running. `test_parameter_provenance.py` now compares them on every run.
