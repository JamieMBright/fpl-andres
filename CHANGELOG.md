# Changelog

All notable changes to FPL Andres will be documented here.

The project follows Semantic Versioning once milestone tags begin.

## [Unreleased]

### Added

- Model 7.0 carries route-level market evidence into goals, assists, cards,
  shots, participation, save pressure, defensive contribution and bonus. BPS
  is reconstructed from the official action weights plus each player's
  historical residual, then ranked within complete expected starting elevens.
- A dated Leeds GW1 probable-XI validation records the owner's 10-of-11 prior,
  the model's 10-of-11 overlap and, after the fixture, the actual-XI overlap
  and Brier score. The prior is validation-only and never changes production
  start probabilities.

### Fixed

- Player-market ingestion now preserves card fields, resolves the observed
  `Ben White` and reversed `Magalhaes Gabriel` provider spellings without fuzzy
  matching, and reads shots/shot-on-target over-under lines as expected counts.
- Capped odds runs rotate uncovered fixtures ahead of refreshes and retain
  timestamped current quotes. Previously every daily run started at the same
  earliest fixture and overwrote the artifact, so later weekend fixtures could
  remain permanently unvisited despite a week of green jobs.
- Team odds now fall back to The Odds API's 1X2 and totals markets when
  football-data.co.uk publishes no current Premier League rows. The fallback
  fetches each uncovered fixture in the nearest round once and retains it, so
  clean sheets, goals conceded, save pressure and DefCon pressure can open
  before the CSV source does without exhausting the shared allowance.

- Canonical URLs, route metadata, social sharing, sitemap coverage and crawler
  exclusions now agree. Team-specific URLs canonicalise without the Team ID,
  missing and QA routes are `noindex`, and a 1200×630 sharing card ships with
  the page.
- The analysis-request endpoint now rejects non-JSON, oversized and cross-origin
  browser requests before rate limiting or database access.
- Private diagnostic rows no longer outlive their purpose. A daily production
  job deletes request diagnostics after 30 days and declared-transfer copies
  seven days after their gameweek deadline, with a 30-day backstop.
- The player pool's name column was crushed to nothing on a phone, leaving the
  header reading "PLAYERCLUB" and every row nameless. The shared table style
  pins the first column at 54px because in a squad table that column holds a
  kit; here it holds the name. The pool now keeps a real width for it, freezes
  it as the rest scrolls, and takes tighter gutters below 620px.
- The odds workflows never declared `environment: production`, so the API keys
  the owner had configured were invisible to them and every expression expanded
  to an empty string. `Ingest Player Odds` run 1 failed reporting that its key
  was not set while the key existed. All three now name the environment, and
  `test_workflow_environments.py` fails any workflow that reads one of those
  secrets without it — there is no error from GitHub when this is wrong, only a
  step that fails further down for a reason that looks unrelated.
- A Wildcard is refused unless the rebuild moves at least five of the fifteen,
  in both the published plan and the browser solve. It was being offered
  against a single transfer, which is a chip thrown away: the free transfer
  makes that move and the chip is still in hand. The published plan's two
  wildcards now move six each.
- The Wildcard is priced over the run it opens rather than one afternoon. The
  note claimed five gameweeks while the number underneath measured one, which
  is also why it kept landing on the second-best week.
- A chip badge on a solved plan says `advised`. The squad below it has not been
  rebuilt around the chip, and a badge that did not say so read as a Wildcard
  being spent on the single transfer printed underneath it.

### Changed

- Player-market goals, participation and card evidence now persist beyond the
  quoted fixture with a two-gameweek half-life toward the historical or
  depth-role baseline. GW1 gets the full signal; by GW9 one-sixteenth remains.
  Team odds remain fixture-specific and do not leak one opponent into another.

- The two-sigma curve control is disabled, rather than silently drawing
  nothing, when the axes have too few players or no spread to measure. The
  reason is on the control.
- Expected points can be totalled over the next 1, 3, 5, 7 or 9 gameweeks
  against the real opponents, on the player pool, the player card and as a
  scatter axis (`state/horizon-points.ts`). A double counts twice and a blank
  counts nothing, which is what a per-match figure cannot express. It is a
  plain sum rather than the solver's decayed lookahead: the solver discounts
  later weeks because it will get another transfer before them, and a reader
  comparing two players over nine gameweeks is asking a different question.
- The plan's per-gameweek reasoning is folded away by default, and the move
  section gives one line per transfer. Thirty-eight cards of open reasoning is
  a wall to scroll past, and a double transfer read as one sentence about four
  players with no way to tell which price belonged to which move.
- The club shirts on the plan are ten to a row, centred, rather than however
  many the width allows. Sized against their own column with a container query,
  so all twenty appear on one line if the column ever gets wide enough.
- The manager record chart's season labels are angled and smaller. Sixteen
  seasons in a 500px column put them hard against each other.
- The FAQ is written out properly: full answers in several paragraphs, a
  definition of every term that actually defines it, and no first person. It is
  the one page with no numbers on it, so a clipped answer there is only an
  answer somebody has to ask again.
- The method page carries one body size instead of five, and no longer speaks
  in the first person. It is a description of what a program does.
- The odds credentials are `THE_ODDS_API_KEY` and `API_FOOTBALL_API_KEY`.
  SportMonks is removed: its odds need a paid plan and the owner is not
  signing up.
- The mini-league verdict is derived from the artifact instead of typed
  (`state/validation-verdict.ts`, `leagueVerdict`). It said the form chaser beat
  the projection outright in 2024-25. It had, when it was written; the backtest
  reran, the sign flipped to +15, and the page went on saying it — the exact
  drift that file exists to stop. It now reads the margins out on the way past
  and reports what they are: beaten in all four seasons by 228, 71, 15 and 13,
  a margin that is narrowing, and the crowd ahead outright in 2025-26. Two
  tests hold it to the shipped numbers whichever way they fall.
- Step nine of the method no longer says the plan is solved once and never
  re-read. The season is re-solved in the browser on every visit from today's
  squad, prices and bank; what is published once is the projection underneath
  it, and that is what goes stale as the season runs on.
- The plot configuration is a sidebar down the left of the chart rather than a
  panel beside or under it. It sticks as the page scrolls and scrolls inside
  itself, so the controls stay next to the thing they control however far down
  the reader has gone. The panel itself is the scroll container: Chromium wraps
  the content of a `details` in an anonymous box, so a grid row set on the
  `details` sized that box and never reached the div inside it, which kept
  spilling past the panel and over the page below.
- Every mutually-exclusive and multi-choice control in that sidebar is a
  wrapped box, like the club picker: positions, colour-by, and the whole
  reference-lines group. The input stays in the document and keeps all of its
  keyboard and screen-reader behaviour; only its rendering moves to the span
  beside it, which is why they are not buttons with `aria-pressed`.
- The club toggles carry the club's kit colours. The picker and the plot are
  the same legend, and twenty three-letter codes are not something anyone
  reads as clubs at a glance.
- A dimmed point's name dims with it. Isolating a club left every other name at
  full weight, so the chart read as busier than the selection it was showing.

### Added

- A measured-results route turns the calibration, season simulations and
  FPL500 catalogue into three concise, source-dated evidence cases. It links to
  the full tables and never substitutes testimonials or ratings for measured
  outcomes.
- A reusable, `noindex` thank-you route now follows accepted contact messages,
  with neutral direct-visit copy so it can later support paid onboarding
  without pretending accounts or payments exist today. Contact copy states a
  two-working-day reply target.
- Optional Google Analytics is disabled unless a valid GA4 measurement ID is
  configured and the visitor explicitly opts in on the privacy page. Events
  contain only sanitised route paths; Team IDs and query strings are removed,
  advertising signals are disabled, and consent can be revoked.
- The Team ID form now comes before deferred rankings on Home. Content routes
  gain a phone-only, safe-area-aware action back to that form; Home, Plan and
  completion routes suppress the duplicate action.
- A privacy and data page states what stays in the browser, what reaches the
  server and for how long, with a confirmed one-click reset that preserves the
  selected kit and unrelated origin data. The standard
  `/.well-known/security.txt` route publishes the existing private reporting
  channel.
- A scorecard: what was advised for a gameweek against what the manager
  actually did (`state/scorecard.ts`, `Scorecard`). The call is recorded before
  the deadline and never rewritten afterwards — the plan is re-solved on every
  visit and the numbers move, so taking the last version before the deadline
  would score whichever answer happened to be on screen when he stopped
  looking. It settles against the fifteen FPL publishes: his transfer is the
  difference between that squad and the one the advice was given from, and more
  than one change is reported as a hit or a chip rather than reduced to a swap
  somebody picked. Agreement only, not points: scoring one captain against
  another needs every player's points for the gameweek and no endpoint this
  site is allowed to call publishes them, so the smaller claim is the one made.
- The declared fifteen rides in the link as well as in this browser
  (`state/squad-code.ts`). Mobile Safari clears script-written storage after a
  week without a first-party visit, so a manager coming back to check his plan
  found his squad gone. A bookmark is not script-written storage. The fifteen
  are packed into 44 URL-safe characters with a checksum, so a truncated paste
  fails rather than restoring a squad he never picked — fifteen plausible names
  is exactly what a wrong answer looks like. Nothing leaves the browser and no
  table was added: a Team ID is public and enumerable, so a squad that came
  back from a server could have been written by anybody who guessed the number,
  and that is still the reason it does not. A squad already in this browser is
  never overwritten by a link.
- The defensive-contribution bar is counted for the position being projected
  (`backtesting/rates.py`, `defensive_actions`). FPL sums clearances, blocks,
  interceptions and tackles for a defender and adds recoveries for everyone
  else, publishing whichever applied at the time in one column — and it
  reclassifies players. A wing-back moved to midfield therefore carried a count
  missing every recovery he had ever made into a bar two actions higher, and
  read as a worse defensive midfielder than the one FPL had just decided he was.
  The three components are now read out of the corpus and summed for the
  position being projected. The arithmetic was checked against the live
  bootstrap rather than assumed: Gabriel 239 + 38 = 277, Rice 127 + 69 + 180 =
  376, both exactly what FPL published. They join the corpus fingerprint too,
  because a value the projection reads that the fingerprint does not cover is a
  re-ingest that can move every DefCon number with nothing to say it did. Model
  version 4.2.
- Clearances-blocks-interceptions, tackles and recoveries are three separate
  scatter axes. The sum cannot say whether a player clears the bar by defending
  his own box or by winning the ball back in the opposition half, and those are
  not the same player: one of them keeps doing it when his side goes a goal up.
- A club with no Premier League record is rated on FPL's own published
  strength rather than one hand-picked constant (`planning/fixture_routes.py`,
  `published_strength`). FPL sets `strength_attack_home`, `strength_attack_away`,
  `strength_defence_home` and `strength_defence_away` for all twenty clubs before
  a ball is kicked; they were being ingested and read by nothing while every
  promoted side shared a single 0.80/1.25 pair. Each club is now put against the
  league's own mean of the four fields, so above one is a stronger attack and,
  because FPL's defence is higher-is-better and this module's is higher-is-leakier,
  the defence rating is inverted. The constant survives only for a bootstrap that
  carries no strength at all, and a zero is read as absent rather than as
  infinitely weak. Model version 4.1.
- The captaincy theses are tested rather than ranked
  (`backtesting/captain_significance.py`). Ten policies is ten chances to top a
  table by accident, and the 2.2 ordering inverted on a single arithmetic fix —
  which is what a lead inside the noise looks like from outside. Each thesis is
  now paired against the projection week for week across every scored gameweek
  of all four seasons and the differences resampled 2,000 times; a thesis is
  reported as better only when the whole 95% interval clears zero. Paired rather
  than pooled, because both rules face the same fixtures in the same weeks. The
  calibration page draws it as a dot-and-whisker against zero, which is the only
  chart on the page that can return "no".
- Groundwork for reading the elite cohort's armband
  (`cohorts/captain_agreement.py`, `cli.cohort_captains`). Scores each thesis on
  how often it names the same captain the top-500 named, which is a different
  question from which thesis scores best and is kept separate from it: the
  cohort is selected on final rank, so agreement describes elite behaviour and
  cannot measure it. Reports contested weeks first — a week where 90% of the
  cohort captains the same player separates no two theses, and if almost every
  week looks like that then the armband is not where their edge lives.
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
