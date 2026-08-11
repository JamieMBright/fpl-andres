# FPL Andres

An evidence-gated Fantasy Premier League analyst. It answers the next
deadline's practical questions — transfer or bank, who to captain, how to order
the bench — and then extends them into a full gameweek 1 to 38 plan whose
confidence falls away the further out it reaches.

Independent, and not affiliated with Fantasy Premier League, the Premier
League, Leeds United, or any player or club.

This file is the working brief. Everything needed to build a feature here is
either in it or named by it.

## The rule that governs everything else

A missing source disables or downgrades a feature. It never licenses a
plausible estimate. Every output is labelled `observed`, `inferred`,
`experimental`, or `unavailable`, and carries the timestamp of the evidence it
rests on. If a controlling FPL rule cannot be read from its source, the source
contract fails visibly rather than defaulting.

## Capability boundaries

These are product behaviour, not bugs. A feature absent from this table is
missing; a feature described here is bounded on purpose.

| Boundary                | What it disables or downgrades                                                                                                                                                                                                                             |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Public team state       | No live draft. Bank, free transfers and chips are as of the last processed deadline. Manager corrections are applied separately and stored locally.                                                                                                        |
| Matchups                | Five scoring routes, each bent separately by a fixture. No flank, foot or set-piece splitting: the public sources cannot establish it.                                                                                                                     |
| Out of position         | An attacking defender is flagged, not repriced. Role evidence is recency-decayed; a regime change emits `unavailable` rather than a stale classification.                                                                                                  |
| Defensive contributions | Nothing before 2025/26. The route did not exist, so the column is absent rather than zero.                                                                                                                                                                 |
| Historical data         | Backtests span 2019-20 onward; expected values exist only from 2022-23. No past bank or chip state, so a replayed season cannot honour real budgets.                                                                                                       |
| Injuries                | FPL's own availability flags. No scraped team news.                                                                                                                                                                                                        |
| Prices                  | No live price-change prediction. Ownership history only from the archive.                                                                                                                                                                                  |
| Cold start              | Promoted-club debutants have no measured record. The player pool prices them on a role prior, marked as such, never as a measurement.                                                                                                                      |
| Rivals                  | Individual rival picks are post-deadline only. Aggregate ownership is legal earlier.                                                                                                                                                                       |
| Team goals              | Dixon-Coles, fitted on the completed season, with a single home advantage shared by every club.                                                                                                                                                            |
| Bookmaker odds          | Ingested on a GitHub runner only — the owner's network blocks every price host at the TLS handshake. No correct-score market is bought, so scorelines are reconstructed from 1X2 and over/under under independent Poisson, and the draw error is reported. |
| Suspensions             | Accumulation bans are priced. A disciplinary hearing is a judgement, so it is not modelled.                                                                                                                                                                |
| Execution               | No automated transfers. Every recommendation is advisory.                                                                                                                                                                                                  |
| Rate limiting           | The public proxies are unmetered per client.                                                                                                                                                                                                               |

## Architecture

```text
Browser -> Vercel React app + TypeScript API -> public FPL API
                                      |       -> Supabase
GitHub Actions -> Python projections + optimizer -> Supabase -> Resend
```

- `apps/web` — Vite, React, TypeScript. One route matters: `/plan`.
- `api` — same-origin Vercel functions. The browser never calls FPL directly.
- `packages/contracts` — shared runtime schemas, generated and version-gated.
- `packages/quick-solver` — bounded interactive next-deadline solver.
- `python/fpl_andres` — rules, ingestion, models, backtests, optimizer.
- `supabase` — local configuration and forward-only migrations.

## Working here

```powershell
corepack pnpm install
python -m pip install -e ".[dev]"
corepack pnpm dev          # the web app
corepack pnpm fast         # the iteration loop, ~70s
corepack pnpm check        # the full gate; run before pushing a milestone
corepack pnpm test:e2e     # deterministic browser matrix, no live FPL
```

`fast` runs the lite unit suite: everything except the three files that solve a
whole season or drive a fifteen-pick journey through the market. Those three
cost more than the other seventy-three put together, and none of them is what
breaks while you are moving markup around. `check` runs them, so does CI, and
nothing reaches origin without them.

Prerequisites: Node 20.19+, Python 3.12+, Docker Desktop for the local
database. No global pnpm or Supabase install is needed.

Conventions that bite:

- Never hand-format a file prettier owns. Run `corepack pnpm format` and commit
  its output.
- `noUncheckedIndexedAccess` is on. Guard every indexed access.
- A new component must be added to the inventory table in `DESIGN.md`, or the
  design-inventory test fails.
- Behaviour goes in through a failing focused test first, then minimal code.
- Never copy optimizer code from external FPL solvers.

### Why a local failure can look opaque

An API route is a serverless function in production and does not exist as a
running server locally, so a 404 from `/api/...` under `pnpm dev` is usually a
missing rewrite rather than broken code. A local database starts empty: seed it
before expecting a query to return rows. The Windows Supabase executable may be
blocked by local application-control policy; CI runs Linux, and the SQL policy
tests run without the CLI.

## Secrets

Copy `.env.example` to `.env.local` only when provider-backed work begins.
Values without `VITE_` are server-only. Never put a Supabase secret key, a
Resend key or a subscriber email into a `VITE_` variable, into browser code, or
into a log line.

## The hosted database

The sole hosted Supabase project is production. There is no CLI migration
ledger for it, so the table below **is** the ledger. VS Code MCP is disabled by
organization policy; do not add an alternate interactive database connector,
and never inspect application rows through an AI tool.

Apply only tracked migrations that pass the local policy tests and Linux CI.
The bootstrap is this list, pasted into the SQL Editor **in filename order**.

The migrations are **not idempotent** — 20 `create table`, 34 `create index`,
12 `create trigger` and 6 `create function` statements are written without a
guard — so a file cannot be safely re-run after a partial paste. If a paste
failed part-way, run `supabase/rollback/down.sql` to return to empty before
re-applying. That is a teardown, not a repair: it drops everything.

| #   | Migration                                                     | Applied                        |
| --- | ------------------------------------------------------------- | ------------------------------ |
| 1   | `20260729180000_foundation.sql`                               | yes                            |
| 2   | `20260729183000_evidence_snapshots.sql`                       | yes                            |
| 3   | `20260730120000_projection_artifacts.sql`                     | yes                            |
| 4   | `20260731120000_optimization_artifacts.sql`                   | yes                            |
| 5   | `20260731130000_foreign_key_indexes.sql`                      | yes                            |
| 6   | `20260801120000_history_corpus.sql`                           | yes — corpus loaded 2026-07-30 |
| 7   | `20260801130000_defensive_components.sql`                     | **owner to confirm**           |
| 8   | `20260801140000_fixture_grain_and_event_range.sql`            | **owner to confirm**           |
| 9   | `20260801150000_backtest_artifacts.sql`                       | **owner to confirm**           |
| 10  | `20260801160000_crowd_snapshots.sql`                          | **owner to confirm**           |
| 11  | `20260801170000_access_path_indexes.sql`                      | no                             |
| 12  | `20260801180000_backtest_corpus_fingerprint.sql`              | no                             |
| 13  | `20260801190000_promotion_lineage.sql`                        | no                             |
| 14  | `20260801200000_workflow_run_audit.sql`                       | no                             |
| 15  | `20260802120000_snapshot_path_integrity.sql`                  | no                             |
| 16  | `20260804120000_analysis_requests_and_declared_transfers.sql` | yes — applied 2026-08-04       |

Rows 7–10 are marked for confirmation rather than guessed: their state was
never recorded and cannot be inferred from the repository. Check the hosted
project's `information_schema` for `crowd_snapshots`, `backtest_runs` and
`element_gameweek_stats.clearances_blocks_interceptions`, then update this
table. `python/tests/test_migration_checklist.py` fails if a migration file
exists that this table does not name.

### Retention

Nothing is pruned, and that is a measurement rather than a hope. The free tier
allows 500 MB; the whole history corpus is 6.6 MB across 185,954
player-gameweek rows. The growing tables — `element_gameweek_stats`,
`element_price_observations`, `crowd_snapshots`, `backtest_predictions`,
`source_snapshots`, `workflow_run_events` — are therefore kept in full. The one
table that can reach the ceiling is `backtest_predictions`, because a sweep
writes a row per player per gameweek per candidate; prune it by run, oldest
first, if it ever does.

Analysis requests, declared transfers, contact messages and reply addresses are
personal data and are the exception. Request diagnostics are deleted after 30
days. Declared-transfer copies are deleted seven days after the relevant
deadline and never kept beyond 30 days. Contact content is never written to
Supabase: it passes through Resend to the private project mailbox, whose copy is
deleted within 30 days after the conversation closes. Resend retains its
processor copy under its own service terms unless content storage has been
disabled. Personal data is never exported for analysis or marketing. The
`prune-private-state.yml` workflow enforces the database limits and refuses an
unexpectedly large deletion batch; `/privacy` exposes the local-data controls.

## Operations

- `api/_lib/rate-limit.ts` bounds the rate at which this project calls FPL. It
  does not meter the caller.
- `api/_lib/request-log.ts` records the shape of a request and never its
  identifiers.
- `canary.yml` probes the deployed site on a schedule. A red canary means the
  deployment, not the model.
- The odds ingest and the player-market survey run on GitHub runners only,
  because the owner's network blocks every price host.

## The rest of the documentation

- `DESIGN.md` — the visual system and the component inventory.
- `docs/MODEL.md` — the projection model, its identities and failure modes.
- `docs/MODEL_CARDS.md` — generated by `track_model.py` and committed by
  `validate-model.yml`. Inputs, promotion rules and measured performance.
- `docs/PARAMETERS.md` — every parameter with its source. A parameter without
  provenance fails the build.
- `docs/CORPUS.md` — what is loaded, from which pinned commit, and what a
  backtest needs beyond a SHA.
- `docs/SCHEMA.md` — the only readable view of a model defined across sixteen
  migrations. Every created table must appear.
- `docs/ERRORS.md` — the error taxonomy the code is tested against.
- `docs/PLAYER_MARKETS.md` — candidate player-prop sources, and how to survey
  them.
- `docs/adr/` — architecture decisions: forced RLS with no policies, immutable
  published artifacts, structural leakage guards, recency-decayed deployment,
  and why the corpus is not partitioned.

## License

Project-authored code is all rights reserved while the source-code licence is
selected. Vendored development guidance retains its own licences; see
`THIRD_PARTY_NOTICES.md`.
