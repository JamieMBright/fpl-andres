# Changelog

All notable changes to FPL Andres will be documented here.

The project follows Semantic Versioning once milestone tags begin.

## [Unreleased]

### Added

- The backtest runs itself. `.github/workflows/validate-model.yml` reruns
  `fpl_andres.cli.validate` on every change to the projection that lands on
  main, appends a row to `model-history.json`, commits both back, and prints a
  before/after table of every headline metric that moved. The corpus lives in
  Supabase, so this had never run anywhere but by hand — which is how the
  calibration page came to claim the naive baseline was winning months after it
  had stopped.
- The projection carries a version. `MODEL_VERSION` is stamped into the
  artifact, and `scripts/model-version-gate.mjs` fails the build if anything
  under `models/`, `backtesting/` or `rules.py` moves without it. Two runs a
  month apart were otherwise indistinguishable from one model measured over two
  corpora.

- Pre-season Team ID entry is no longer a dead end. Before the first deadline the
  team page shows the manager's historical record and a rule-checked builder for
  the fifteen he is starting with: squad shape, one-hundred-million budget and the
  three-per-club limit are all enforced, every broken rule is listed at once, and
  nothing is stored until the squad is legal. A locked-in squad is held as though
  played in gameweek 1, and `/plan?team=` solves gameweeks 1 to 38 from it. Like a
  declared transfer, it lives only in the manager's own browser and is labelled as
  his claim rather than observed state.
- Captaincy is backtested on its own (`backtesting/captaincy.py`). Every method
  captains from the same shortlist — the 25 most-owned players going into the
  gameweek — and is scored on mean captain return, regret against the shortlist
  ceiling, weeks it picked the best available, and blank rate. The captain
  doubles, so this is the repeating decision with the most leverage in the game
  and nothing here had ever measured it.
- The backtest publishes `components`, the projection with the recent-form blend
  removed. `recent_mean` is both the naive baseline and 20% of the projection, so
  the headline comparison was a superset against its own component; `components`
  is the number that says whether the fourteen-route pricing carries itself. It
  was computed on every run and discarded before it reached the artifact.
- The frontier is fitted to the distribution rather than to individuals. The
  x-range is cut into ten slices, the mean and standard deviation of y are
  measured inside each, and the curve runs two standard deviations above the
  mean. The old non-dominated staircase passed through the single highest x and
  the single highest y — usually two anomalies — and guaranteed nobody could be
  above it. Players who clear the new curve are marked as pioneers.

### Fixed

- The calibration page claimed the naive last-five average "ranks better than my
  projection in every season I tested". The shipped artifact has the model ahead
  on rank correlation, mean absolute error and top-20 hit rate in all four
  seasons, and has done since the fixture and defensive-contribution work landed.
  Both verdicts are now derived from the artifact, with a test that fails if the
  prose and the numbers disagree again.
- The away and third kits were swapped. The green and navy shirt in
  `docs/design/inspiration/` is the 1994 away kit; the yellow and blue is the
  third. The default palette is unchanged — only its name and the toggle order.
- The plot configuration, how-to-read and compare panels are collapsed boxes
  stacked under the chart at the chart's own width, instead of a three-column
  grid of three different widths.
- "Ring the best corner" is now "Shade the good corner", and it shades. The ring
  enclosed whoever was in the top fifth of both axes, which on the opening axes
  is one player, so the checkbox did nothing. Two overlaid gradients — one per
  axis, each fading to nothing at that axis's median or mean line — leave the
  good corner green, the bad corner red and the mixed corners neutral.
- The empty-filter message moved onto the axes, where a reader who has just
  moved a slider is looking, rather than under a table that is also empty.
- The y-axis reserves a little space at its foot so the watermark always lands
  on clear background.
- Switching to a past season and failing to download it left the reader with no
  season picker, because the picker lives inside the body and the body needs a
  pool. The page now does what it says and puts you back on this season, and
  offers a way back while the download is in flight.
- The methodology page is about a third shorter, with the numbers leading.
- The analysis season picker named the live option "This season, as it stands"
  while plotting last season's totals. Between seasons FPL keeps those totals
  under the same column names; the option now names the vintage it is showing and
  flips on its own when a gameweek is scored.
- The player card says FPL publishes no squad number rather than showing a blank
  shirt and a tooltip nobody hovers. Measured 2026-08-05: 0 of 570 elements carry
  one.
- The chart watermark moved inside the plot area, bottom left, so a screenshot
  that keeps the data keeps the mark.

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
