# Build Plan — scaffold to shipped product

Execution contract from the v0.5.1 audit to v1.0.0. Every milestone names what
ships, the test that proves it, and what it unblocks. Milestones are ordered by
dependency: nothing later can start before its inputs exist.

The governing constraint throughout is [`LIMITATIONS.md`](LIMITATIONS.md). A
missing source disables a feature; it never licenses a plausible estimate. Every
model output carries `EvidenceLevel` and source timestamps.

## Where we start (v0.5.1 audit, 2026-07-30)

Honest state of the codebase today:

| Capability             | State                                                              |
| ---------------------- | ------------------------------------------------------------------ |
| Supabase tables        | 8 defined, forced RLS, **0 rows, no writer code anywhere**         |
| Historical per-GW data | **none** — parser exists, no fetcher, no table                     |
| Per-player xPTS        | **none** — only team-level xG exists                               |
| Minutes model          | **none**                                                           |
| DefCon                 | scoring-rule name recognised; **no model, no data**                |
| OOP                    | classifier complete; **no live data source**                       |
| Chip planner           | **hard-refused** at schema layer (`chip_scenario=Literal["none"]`) |
| Backtest               | primitives exist; **no driver, never run**                         |
| Optimizer              | MILP solves; **nothing constructs a real request**                 |
| Team dossier           | renders real bank/value/picks as `"FPL element 101"`               |
| FPL50 / p100           | **none**                                                           |

The gap between "scaffold" and "product" is roughly: one persistence layer, one
historical corpus, six models, one backtest harness, one optimizer wiring, and
the surfaces.

---

## Phase 1 — Data foundation

Nothing downstream is possible without persisted history. This phase is pure
plumbing and it is the highest-leverage work in the plan.

### M1 — Persistence layer (v0.6.0)

Ships the first code in the repo that writes a row.

- Service-role Supabase client, Python (`fpl_andres/persistence/`) and
  TypeScript (`api/_lib/supabase.ts`). Reads unprefixed `SUPABASE_URL` /
  `SUPABASE_SECRET_KEY`. Fails closed if either is missing — never a silent
  no-op.
- Idempotent writers for the existing 8 tables, keyed on natural keys so a
  re-run is a no-op rather than a duplicate.
- `workflow_runs` execution log wrapping every job: start, finish, row counts,
  source hashes, failure reason.
- Content-addressed `source_snapshots` writer — raw bytes hashed before parse,
  so every downstream row traces to an immutable snapshot.

**Test**: run a writer twice against a local Supabase; assert row count is
identical and `workflow_runs` shows two entries with the same content hash.
Assert an RLS-forced table rejects an anon client.

**Unblocks**: everything.

### M2 — Schema for match and player history (v0.6.0)

New migrations. All immutable, forced RLS, no browser policy.

| Table                        | Grain                 | Purpose                                    |
| ---------------------------- | --------------------- | ------------------------------------------ |
| `seasons`                    | season                | `2023-24` identity, start/end dates        |
| `teams`                      | season × team         | FPL team id ↔ name ↔ short name ↔ strength |
| `elements`                   | season × element      | player identity, position, team, price     |
| `fixtures`                   | season × fixture      | home/away, kickoff, result, FPL difficulty |
| `element_gameweek_stats`     | season × GW × element | the corpus — see below                     |
| `element_price_observations` | date × element        | daily price + net transfers                |

`element_gameweek_stats` columns: minutes, starts, goals, assists, clean sheets,
goals conceded, own goals, penalties saved/missed, yellow/red, saves, bonus,
bps, influence, creativity, threat, ict, expected_goals, expected_assists,
expected_goal_involvements, expected_goals_conceded, defensive_contribution
(nullable — 2025/26+ only), total_points, value, selected_by, transfers_in/out,
was_home, opponent_team, fixture_id, kickoff_time.

**Test**: `supabase db reset` on Linux CI applies cleanly; RLS policy tests
assert anon cannot read; immutability triggers reject UPDATE and DELETE.

### M3 — Historical ingest (v0.6.1)

- Fetcher for [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League)
  at pinned commit SHAs. The existing parser already rejects same-GW `xP` and
  post-cutoff availability — that leak guard stays on the ingest path.
- Season/GW loop with resumable checkpointing, so a partial run continues rather
  than restarts.
- Normalisation from archive CSV headers to the schema above, with an explicit
  column map per season (headers drift between seasons; a missing mapping is a
  hard failure, never a default).
- Element identity resolution across seasons (FPL element ids are **not** stable
  between seasons — resolve on name + team + DOB where available, and record
  ambiguity rather than guessing).
- CLI: `python -m fpl_andres.cli.ingest_historical --season 2023-24 --gw 1-38`.
- GitHub Actions workflow, manual dispatch, `production` environment secrets.

**Target corpus**: 2023/24, 2024/25, 2025/26 — three complete seasons,
~700 elements × 38 GW × 3 = ~80k rows. 2025/26 carries the first
`defensive_contribution` labels.

**Test**: ingest one known GW; assert exact row count, assert a known player's
known score matches, assert re-running changes nothing, assert a CSV with a
post-cutoff `data_available_at` raises `FutureInformationError`.

**Unblocks**: every model, the backtest, all calibration.

### M4 — Live FPL ingest (v0.6.2)

- Scheduled post-deadline job: `bootstrap-static`, `fixtures`,
  `entry/{id}/history`, `element-summary/{id}`.
- Writes into the same tables as history, so live and historical rows are one
  continuous corpus and the models never branch on provenance.
- Daily price observation job for the price model.

**Test**: live-contract schema validation already runs daily; extend it to
assert the ingest wrote the expected GW and that `state_as_of` advanced.

---

## Phase 2 — Models

Each model is built failing-test-first, evaluated walk-forward, and gated
through the existing paired-bootstrap promotion machinery before it can
influence a recommendation. An unpromoted model renders `unavailable`.

### M5 — Minutes (v0.6.3)

**The most important model in the system.** Every other projection multiplies by
expected minutes; a good points model with a bad minutes model is worthless.

- `P(start)` from recent start sequence with recency decay, FPL `status`,
  `chance_of_playing_next_round`, and news timestamp.
- `P(60+ | start)` from historical substitution patterns per player and position.
- `E[minutes]` as the composed distribution, not a point estimate.
- Rotation risk for players in European competition weeks.

**Test**: Brier score and calibration curve on 2024/25 holdout; must beat a
naive "started last week ⇒ starts this week" baseline.

### M6 — Team goal projection promoted (v0.6.4)

The Dixon-Coles and baseline models already exist and have never seen real data.

- Walk-forward driver: train on all fixtures before cutoff, predict the next GW,
  reveal, advance. Across three seasons.
- Paired bootstrap through the existing `evaluate_promotion` gate.
- Persist the decision to `model_promotion_decisions`; add active-model dispatch
  so promoted models actually get used.

**Test**: promotion decision row exists with p-value, sample size and both model
identities. Active dispatch returns the promoted model, not a hardcoded choice.

### M7 — Player rate models (v0.7.0)

- Per-90 xG and xA with Bayesian shrinkage toward position and team priors, so a
  200-minute player is not projected off three shots.
- Share-of-team-xG allocation: team projection → player share. Handles the
  "new signing with no minutes" cold-start via position/price prior.
- Penalty and set-piece duty as a separate observed signal with its own
  evidence level (order changes mid-season; recency-weighted).

**Test**: Spearman correlation against realised xG on holdout, per position.
Assert a cold-start player gets an `EvidenceLevel` reflecting no history rather
than a confident number.

### M8 — Supporting scoring models (v0.7.1)

- **Clean sheets / goals conceded**: from the team goals-conceded distribution
  produced in M6, not a separate model.
- **Saves**: GK saves per 90 conditioned on opposition shot volume.
- **Bonus**: BPS components model → `P(bonus=3|2|1|0)`. BPS is deterministic
  from match stats, so this is a distribution over realised stats.
- **Cards**: yellow/red rates, small but non-zero.

### M9 — Expected points assembly (v0.7.2)

Compose M5–M8 into `element_projections`: per element, per GW, `xPTS` with a
credible interval, plus the component breakdown (appearance, goals, assists,
clean sheet, saves, bonus, DefCon, cards) so the UI can show _why_.

New table `element_projections`, written per projection run.

**Test**: total xPTS decomposes exactly into its components. Holdout MAE and
Spearman versus realised points, per position, versus two baselines: FPL's own
`ep_next` and a naive "last 5 GW mean".

**This is the first milestone where the product has something to say.**

### M10 — DefCon (v0.8.0)

- 2025/26+ `defensive_contribution` ingest already landed in M3.
- Per-position threshold rules (defenders 10 CBIT, midfielders and forwards 12
  CBIRT) sourced from the rules snapshot, never defaulted.
- `P(threshold reached)` from per-90 rate, opposition possession share, and
  expected minutes.
- Feeds the xPTS component breakdown and the "DefCon beasts" paid surface.

**Gate**: one season of labels is a small sample. Ships with explicit
small-sample bands and an `EvidenceLevel` that says so.

### M11 — Price movement (v0.8.1)

Calibrated movement probabilities from daily net-transfer observations. Per
`LIMITATIONS.md`, no exact-threshold claims — probabilities only.

---

## Phase 3 — Backtesting

This is what answers "does any of it work?"

### M12 — Walk-forward harness (v0.8.2)

- Orchestrator that, for each GW in each season, builds a projection using
  **only** rows whose `data_available_at` precedes that GW's deadline, then
  reveals actuals.
- Leak guard is structural: the query itself cannot see post-cutoff rows.
- New tables `backtest_runs` and `backtest_predictions`.
- Metrics per prediction type: Spearman, MAE, Brier, calibration curve,
  top-N hit rate, per position and per price band.

**Test**: a deliberate leak (feeding a post-cutoff row) must fail the run loudly.

### M13 — Manager simulation (v0.8.3)

**The answer to "where are the backtest results for my team ID?"**

- Take a real team's actual opening squad in a past season, then simulate the
  full season: each GW, the algo picks transfers and captain under real
  constraints (bank, free transfers, hit costs, price changes).
- Compare against: the manager's actual score, the overall average, and a
  "no transfers, captain highest-owned" control.
- Report per-GW: what it would have done, what it scored, where it diverged.

**Output**: a reproducible report artifact per team per season, and the
`/calibration` route stops being a placeholder.

---

## Phase 4 — Optimization and recommendation

### M14 — Optimizer wiring (v0.9.0)

- Assemble a real `OptimizationRequest` from a live team ID, the rules snapshot
  and promoted projections.
- Selling-price accounting via acquisition cohorts (FPL sells at purchase price
  plus half the rise, rounded down — cohort-tracked, not squad-averaged).
- Captaincy recommendation with the runner-up and the margin.
- Transfer recommendation including the "no transfer" option and honest hit
  arithmetic.
- Persist to `optimization_runs` / `optimization_event_plans`.

### M15 — Horizon planner (v0.9.1)

6–8 GW rolling path from the existing horizon MILP, with fixture difficulty
derived from the promoted team-goal model rather than FPL's static FDR.

### M16 — Chip planner (v0.9.2)

Blocked on an authoritative chip-semantics contract (multiplier, bench and
transfer behaviour are not published in `bootstrap`). Once sourced, the
`chip_scenario` literal expands across the three optimizer contracts and the
quick solver. Until then every chip path fails closed, by design.

### M17 — FPL50 / p100 / groupthink (v0.9.3)

Post-deadline only, per `LIMITATIONS.md`.

- `standings` ingest for the top-N overall cohort.
- Effective ownership and template divergence.
- Contextual view that does **not** alter projections in v1.

---

## Phase 5 — Surfaces

### M18 — Design system into the app (v0.9.4)

The Ceefax direction currently lives only in a static mockup.

- `--fa-*` tokens from `DESIGN.md` into the real stylesheet.
- Theme toggle, Teletext strip, Bielsa bucket mark, Subbuteo evidence chips.
- Player enrichment so the dossier shows names, prices, positions and teams
  instead of `"FPL element 101"`.

### M19 — Recommendation surfaces (v0.9.5)

Captaincy, transfers, fixture planner, DefCon beasts, OOP flags, FPL50 context.
Every verdict carries its evidence chip and an expandable source trail.

### M20 — Paywall (v1.0.0)

Per [`PAYWALL.md`](PAYWALL.md): beta open, then free tier (context-less advice,
`+1 GW`) versus paid (`£3` — planner, OOP, DefCon, FPL50, p100, groupthink).
Gating shim ships last so nothing is gated before it works.

---

## Cross-cutting, continuous

- **Migration deployment workflow** — replaces manual SQL Editor bootstrap.
  Required before any schema change after M2.
- **Model cards** updated on every promotion, with sample size and holdout
  metrics.
- **`pnpm check`** green before every milestone commit: contracts, lint,
  typecheck, vitest, build, ruff, mypy strict, pytest.
- **Evidence discipline** — every surfaced number carries `EvidenceLevel` and
  source timestamps, or renders `unavailable`.

## Owner decisions that gate this plan

Tracked in [`OWNER_SETUP.md`](OWNER_SETUP.md). The blocking ones are the
historical source, the ingest execution environment, and the promotion policy.
Everything in Phase 1 stalls without them.
