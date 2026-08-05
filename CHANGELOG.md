# Changelog

All notable changes to FPL Andres will be documented here.

The project follows Semantic Versioning once milestone tags begin.

## [Unreleased]

### Added

- Pre-season Team ID entry is no longer a dead end. Before the first deadline the
  team page shows the manager's historical record and a rule-checked builder for
  the fifteen he is starting with: squad shape, one-hundred-million budget and the
  three-per-club limit are all enforced, every broken rule is listed at once, and
  nothing is stored until the squad is legal. A locked-in squad is held as though
  played in gameweek 1, and `/plan?team=` solves gameweeks 1 to 38 from it. Like a
  declared transfer, it lives only in the manager's own browser and is labelled as
  his claim rather than observed state.

## [0.5.1] — 2026-07-30

### Fixed

- FPL transport now returns a typed `reason` (`unreachable`, `unexpected_format`,
  `oversize`) on every 502 and no longer rejects the promise when a body stream
  errors mid-read.
- The composite team-state route translates transport reasons into
  `fpl_unreachable` versus `fpl_source_failed` instead of collapsing both to
  unreachable.
- `entry_unavailable` responses now return HTTP 200 so browsers stop treating a
  valid envelope as an error.
- Vercel deployment: added `.js` extensions to every relative import in
  `api/*.ts`, gave `TeamPublicStateContractError` an explicit constructor that
  accepts an ES2022 `cause` option, and tightened `tsconfig.api.json` to
  `NodeNext` so CI catches the same errors locally.
- Vercel dashboard direction corrected in the owner setup: Framework Preset
  `Other`, empty Root Directory, Node.js 22.x or newer.
- Team analysis route now keys `TeamAnalysisPage` on the URL parameter, so
  navigating from one team to another never renders the previous snapshot for a
  frame; the heading is marked `translate="no"` to keep the Team ID stable.
- `refreshTeamAnalysis` distinguishes storage `QuotaExceededError` from schema
  failure and still surfaces valid state instead of reporting `invalid_response`.
- Manager corrections dialog: the "remove" alert dialog closes on Escape,
  traps focus between its two buttons, and restores focus to the button that
  opened it. The removal-confirmed status region now receives focus.
- Saving a manager correction prunes any older correction for the same team so
  browser storage stays bounded.
- Deployment classification replaces its ordinal comparison with an explicit
  36-cell `(listed_position, observed_role) → classification` table.
- HiGHS optimizer applies deterministic lineup and captain tie-break terms so
  identical inputs always produce the same captain and starting XI.
- Promotion evaluator requires an explicit `metric_direction` and computes
  `paired improvement` accordingly, so higher-is-better metrics can promote.

### Added

- Recency-weighted OOP contract: `DeploymentRoleObservation` records
  per-event roles, kickoffs and minutes; `classify_deployment` applies an
  exponential decay to weighted starts and emits `unavailable` when the recent
  run reverses the prior window.
- StatsBomb Open Data ingest adapter: maps their 26 position labels to our
  nine observed roles, aggregates minutes per player, and produces
  `DeploymentRoleObservation` records with a deterministic sha256 payload
  hash.
- Forward-only migration adding foreign-key indexes to `rules_snapshots`,
  `projection_runs`, `model_promotion_decisions` and `optimization_runs`.
- Playwright feature-walk suite covering corrections save/remove/Escape,
  cross-team route navigation, methodology/calibration focus, all unavailable
  envelope variants, degraded rendering and axe scans on home + degraded
  screens.
- Dependabot, CodeQL and dependency-review workflows; a `pnpm.auditConfig`
  ignore for the React Router RSC-only advisory `GHSA-qwww-vcr4-c8h2`, which
  does not affect this SPA.
- `.vercelignore` to trim the Vercel bundle.
- `docs/RUNBOOK.md` capturing the deploy and incident response steps that were
  learned during the v0.5.0 → v0.5.1 turnaround.

### Documentation

- `LIMITATIONS.md` and `MODEL_CARDS.md` codify the recency requirement that
  blocks live OOP evidence until per-event observations, exponential decay and
  a regime-change check are attached.
- `OPTIMIZER.md` introduces a `pre-GW1 initial squad` mode with no Team ID; the
  bootstrap requires promoted player forecasts and sourced initial rules.
- `OWNER_SETUP.md` records the completed Vercel/Supabase steps, selects
  StatsBomb Open Data as the free prototype source for OOP, and captures the
  design-direction conflict raised by the dark landing inspiration for an
  owner decision.

## [0.5.0] — 2026-07-29

### Added

- Evidence-gated monorepo foundation.
- Team-ID-first application shell and health endpoint.
- Strict FPL rules contract with multi-window chip support.
- Local Supabase configuration and default-deny workflow migration.
- Pinned design guidance and project design contract.
- Bounded TypeScript and Python FPL API adapters with retries and provenance.
- Strict published scoring, mirrored-rules and chip-window contracts.
- Cross-language Zod/Pydantic contract corpus and deterministic JSON Schema drift gate.
- Pinned vaastav CSV parsing with same-gameweek `xP` exclusion and cutoff checks.
- Immutable source/rules snapshot persistence and a live FPL contract canary.
- Provenance-bearing team goal-rate baselines and an experimental time-decayed
  Dixon-Coles candidate.
- Deterministic walk-forward leakage rejection and paired-bootstrap model promotion
  gates.
- Immutable projection, prediction and model-promotion persistence with forced RLS.
- Projection model cards, evidence labels and explicit capability limits.
- Strict public team state with separate, locally stored manager corrections.
- Provenance-bound single-event and rolling HiGHS optimizers with free-transfer and bank
  state flow.
- Bounded TypeScript quick solver with independently verified regret fixtures and a
  representative full-squad benchmark.
- Immutable optimization run/event persistence with default-deny RLS and database-level
  integrity checks.
- Evidence-gated Lord Lundstram attacking-OOP and reverse-OOP signals, including
  rights-cleared heatmap role evidence.
- Same-origin public Team-ID API with bounded transport, exact-byte provenance and
  typed ready/degraded/unavailable responses.
- Evidence-labelled browser dossier with validated local cache, stale-state retention,
  source timestamps and expandable content hashes.
- Deadline-bound manager correction workflow for bank, free transfers, queued moves and
  available chips, stored separately in the browser.
- Keyboard, 360 px, 200%-equivalent reflow, reduced-motion, forced-colors and axe
  browser validation across ready, stale, unavailable and error states.

### Earlier milestone tags — 2026-07-29

Milestones `v0.1.0` through `v0.5.0` were tagged in sequence on 2026-07-29 as part
of an autonomous overnight build. Their scope is captured by the annotated tag
messages in git; the aggregate "Added" list above is what shipped by `v0.5.0`.
`v0.5.1` records the delta relative to `v0.5.0`.
