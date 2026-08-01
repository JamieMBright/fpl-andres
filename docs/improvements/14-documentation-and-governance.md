# 14. Documentation and governance — work orders

Detailed briefs for items 185–204 of the [improvement audit](../../IMPROVEMENTS.md).
Each brief is self-contained: a sub-agent should be able to implement one item
from its brief alone.

Every brief obeys the repository rules: treat `docs/LIMITATIONS.md` as a hard
capability boundary, never expose a Supabase secret, Resend key or subscriber
email, and never iterate directly on the hosted production Supabase project.
Documentation items must not invent facts — every statement must be derivable
from the codebase, a migration file, a committed ADR, or a workflow run result.

---

## 185 — Add SECURITY.md with disclosure route and response expectations (Impact: H)

**Files**: `SECURITY.md` (create at repository root)

**Problem**: No `SECURITY.md` exists. The project proxies the FPL public API
through Vercel functions (`api/fpl/[...path].ts`) and maintains a production
Supabase database (`qpmlfbuouporvwebjxhk.supabase.co`) that stores manager-level
data, crowd snapshots and model artifacts. There is no published channel for
reporting vulnerabilities and no stated response window. GitHub displays a
"Security policy" notice on the repository's Security tab when `SECURITY.md` is
absent.

**Change**: Create `SECURITY.md` at the repository root with the following
sections, deriving every fact from the codebase or `docs/RUNBOOK.md`:

1. **Supported versions** — state that only the `main` branch is supported; no
   versioned releases carry separate security maintenance.
2. **Scope** — name the three attack surfaces: (a) the Vercel API functions in
   `api/` that proxy FPL and read from Supabase, (b) the production Supabase
   project with forced RLS and no browser-facing policy, and (c) the GitHub
   Actions workflows that hold `SUPABASE_SECRET_KEY` in the `production`
   environment. State that the FPL-proxied data is public aggregate data (no
   individual credentials are held). State that subscriber emails (if the Resend
   routes ship) are stored in Supabase and are in scope.
3. **Out of scope** — the FPL API itself (third-party), GitHub infrastructure,
   and Vercel infrastructure.
4. **Reporting** — direct reporters to open a GitHub private security advisory
   (Settings → Security → Advisories → New draft). Do not list an email address.
5. **Response** — commit to acknowledging the report within 7 days and providing
   a resolution timeline within 14 days. State that critical findings (secret
   exposure, RLS bypass) will be patched before disclosure.
6. **Known limitations** — reference `docs/LIMITATIONS.md` for capability
   limits that are not security vulnerabilities.

**Constraints**: Do not include any secret values, project credentials or
subscriber data. Do not invent response SLAs that cannot be met — use only the
timelines above. The file must pass `pnpm format:check` (prettier).

**Tests first**: Not applicable for a new document. Validate by confirming
GitHub shows "Security policy" as active on the repository Security tab after
the PR merges.

**Done when**:

1. `SECURITY.md` exists at the repository root with all six sections.
2. `pnpm format:check` passes.
3. The GitHub repository Security tab shows the policy as active.
4. No credential, secret or subscriber email appears in the file.

**Validate**: `pnpm format:check`. Inspect the GitHub Security tab post-merge.

---

## 186 — Complete `docs/MODEL.md` with all documented algorithm parameters (Impact: H)

**Files**: `docs/MODEL.md`

**Problem**: `docs/MODEL.md` documents attacking rates (§5), supporting points
(§1 lines 23–24), cross-season blending (line 90, `blend_full_weight_minutes`),
and notes that calibration has not been established (line 72). However, the
document's own header (lines 4–8) states "every constant in the source or a
figure measured from the corpus … each says which" — yet several parameters
referenced within the document are not sourced with a code path or commit-stable
identifier:

- The recency decay half-life for the deployment classifier is referenced in
  `docs/LIMITATIONS.md` ("exponential recency decay") but its numeric value is
  not in `docs/MODEL.md`.
- The `blend_full_weight_minutes` threshold and the `current_weight` formula
  (line 94) are shown but the source (corpus measurement vs. domain choice) is
  not stated.
- The calibration gap (line 72) is noted but no acceptance criterion for
  future calibration is given.

**Change**: For each parameter in `docs/MODEL.md` that lacks a source citation:

1. Find the parameter value in `python/fpl_andres/` source files (use
   `grep -rn "decay_half_life\|blend_full_weight\|shrinkage" python/`).
2. For each parameter, add a parenthetical source note in the form
   `(source: \`python/fpl_andres/models/deployment.py\` line N)`or`(measured from the 2019-20–2025-26 corpus)` as appropriate.
3. Add a **§ Calibration acceptance criterion** subsection under the calibration
   note (line 72) stating the quantitative gate that would change the label from
   "experimental" to "active": paired bootstrap `p < 0.05` on the 2024/25
   holdout, as described in `docs/MODEL_CARDS.md` line 119.
4. Do not add parameters or claims that are not present in the current source.
   Do not describe candidate or experimental models as active.

**Constraints**: Every added fact must be traceable to a code line, a migration
file or a documented corpus measurement. Do not contradict `docs/LIMITATIONS.md`.
Do not document candidate models (`dixon_coles/1`, `np_xg` extension) as
promoted — they are `experimental` per `docs/MODEL_CARDS.md`.

**Tests first**: Before editing, extract all parameter names from
`python/fpl_andres/models/` and `python/fpl_andres/projector.py` with `grep -rn`
and list which are already sourced in `docs/MODEL.md`. Edit only the unsourced
ones.

**Done when**:

1. Every numeric constant in `docs/MODEL.md` carries a source note pointing to a
   code path or a documented corpus measurement.
2. A calibration acceptance criterion is stated.
3. `pnpm format:check` passes on the file.
4. No statement contradicts `docs/LIMITATIONS.md`.

**Validate**: `pnpm format:check`. `grep -n "source:\|measured from" docs/MODEL.md`
(all parameters should match).

---

## 187 — Write missing ADRs for four existing architectural decisions (Impact: H)

**Files**: `docs/adr/` (create `0002-*.md`, `0003-*.md`, `0004-*.md`,
`0005-*.md`). Reference: `docs/adr/0001-vercel-only-topology.md` as the template.

**Problem**: Only one ADR exists (`0001-vercel-only-topology.md`). The codebase
encodes at least four more significant architectural decisions that have no ADR:

1. **Forced RLS with no browser-facing policy** — all Supabase tables have RLS
   enabled but no `CREATE POLICY` statement; browser code never reads Supabase
   directly. This is visible in `supabase/migrations/20260729180000_foundation.sql`
   but undocumented as a decision.
2. **Artifact immutability** — `projection_runs`, `team_goal_projections` and
   `model_promotion_decisions` are append-only with no `UPDATE` or `DELETE`
   grants. Referenced in `docs/MODEL_CARDS.md` line 135 but no ADR records why.
3. **Structural walk-forward leakage guards** — the walk-forward runner rejects
   any feature whose `data_available_at` is after the decision cutoff, enforced
   structurally. Referenced in `docs/LIMITATIONS.md` ("Historical archive
   revisions are pinned") but the design decision is not recorded.
4. **Recency-decayed deployment classification** — the OOP classifier uses
   exponential recency decay rather than a fixed window, and emits `unavailable`
   on a regime change. Documented in `docs/LIMITATIONS.md` (Out of position
   section) but not captured as an ADR.

**Change**: Write four ADR files following the `0001` template (Status, Date,
Context, Decision, Consequences):

- `0002-forced-rls-no-browser-policy.md`: cite the foundation migration and the
  `docs/RUNBOOK.md` data-plane section.
- `0003-artifact-immutability.md`: cite `docs/MODEL_CARDS.md` line 135 and the
  projection migration.
- `0004-walk-forward-leakage-guards.md`: cite `docs/LIMITATIONS.md` and the
  walk-forward runner source path.
- `0005-recency-decayed-deployment-classification.md`: cite
  `docs/LIMITATIONS.md` (Out of position section) and the deployment classifier
  source path.

**Constraints**: Each ADR must state "Status: accepted" (these decisions are
already in production). Do not describe alternative approaches that were not
actually considered — limit the Context to what the code and documentation
already record. Do not add parameters or numeric values not present in the source.

**Tests first**: Not applicable for documentation. Validate by confirming each
ADR's "Decision" section matches the current implementation: run
`grep -rn "rls\|immutable\|data_available_at\|recency" supabase/ python/` to
confirm the cited code exists.

**Done when**:

1. Four new ADR files exist in `docs/adr/`, numbered 0002–0005.
2. Each cites at least one source file with a line reference.
3. `pnpm format:check` passes on all four files.
4. No ADR contradicts `docs/LIMITATIONS.md`.

**Validate**: `pnpm format:check`. Manually confirm cited file paths exist with
`ls supabase/migrations/ python/fpl_andres/`.

---

## 188 — Document secret rotation in `docs/RUNBOOK.md` (Impact: H)

**Files**: `docs/RUNBOOK.md` (section "Secrets", currently lists secrets but
omits rotation)

**Problem**: The "Secrets" section in `docs/RUNBOOK.md` lists where each secret
lives (`SUPABASE_URL`, `SUPABASE_SECRET_KEY`, Resend keys, workflow tokens) and
states that nothing with a `VITE_` prefix may hold a secret. It does not describe
how to rotate any of them. If `SUPABASE_SECRET_KEY` is compromised or expires,
the operator has no documented procedure. The Resend API key and webhook secret
are not yet configured in production but their rotation path should be documented
before they are needed. GitHub workflow tokens rotate automatically, but the
`production` environment secret values do not.

**Change**: Add a "Secret rotation" subsection to the "Secrets" section of
`docs/RUNBOOK.md`. For each secret:

1. **`SUPABASE_URL` and `SUPABASE_SECRET_KEY`**: state that the URL is a static
   identifier (does not rotate), but the secret key is rotated from the Supabase
   project dashboard under Settings → API → Reset service role key. After reset,
   update the value in: (a) the GitHub `production` environment secret, and (b)
   the Vercel production environment variable. Describe the test: the canary
   endpoint `GET /api/team/212279` should return a valid degraded or full
   envelope within 30 seconds of the Vercel deployment triggered by the secret
   update.
2. **Resend `RESEND_API_KEY` and `RESEND_WEBHOOK_SECRET`**: rotate from the
   Resend dashboard, update in Vercel Production only (not in GitHub Actions
   unless a workflow uses them). Test by triggering a test webhook event.
3. **GitHub Actions `GITHUB_TOKEN`**: automatically rotated per run; no manual
   step required.
4. **Vercel deployment token** (if used): rotate from Vercel Account Settings →
   Tokens. Update in the GitHub repository secret if it appears there.

State that all rotation steps must be performed without committing the new value
to git. Reference the "Secrets" section constraints (no `VITE_`-prefixed names).

**Constraints**: Do not include any actual secret values, even example strings.
Do not describe rotation paths for secrets that are not yet in use (Resend) as
mandatory — mark them "(when configured)". The procedure must not suggest
`supabase db push` or AI-tool row inspection.

**Tests first**: No code test. Validate the canary test instruction by confirming
`GET /api/team/212279` is a valid test target (it is, per `docs/RUNBOOK.md` Live
canary section).

**Done when**:

1. A "Secret rotation" subsection exists under "Secrets" in `docs/RUNBOOK.md`.
2. Rotation steps for `SUPABASE_SECRET_KEY` and Resend keys are documented.
3. The canary verification step is named.
4. `pnpm format:check` passes.
5. No secret value appears in the document.

**Validate**: `pnpm format:check`. Manual review for absent secret values.

---

## 189 — Document corpus provenance durably in `docs/BUILD_PLAN.md` and `docs/OWNER_SETUP.md` (Impact: H)

**Files**: `docs/OWNER_SETUP.md` (Baseline section), `docs/BUILD_PLAN.md`

**Problem**: `docs/OWNER_SETUP.md` already records that the historical corpus was
loaded on 2026-07-30, covering seasons 2019-20 through 2025-26 with 185,954
player-gameweek rows, and that verified on 2026-07-31. However, the exact
vaastav archive commit SHA used for the load is not recorded in `OWNER_SETUP.md`
— it is only an input to `historical-ingest.yml` at dispatch time. Without the
SHA, the corpus cannot be reproduced from the document alone. `docs/BUILD_PLAN.md`
references the ingest milestone ("M3 historical ingest — shipped, not yet run")
but was written before the actual dispatch occurred and does not record the final
provenance.

**Change**:

1. In `docs/OWNER_SETUP.md`, add the specific vaastav commit SHA used for the
   2026-07-30 ingest run to the Baseline section. The SHA can be recovered from
   the GitHub Actions run log for the `historical-ingest.yml` dispatch (the
   `INGEST_COMMIT` environment variable is logged). Record it as:
   "Historical corpus pinned to vaastav/Fantasy-Premier-League commit `<SHA>`."
2. Add the `data_available_at` timestamp used at dispatch (or "now" if blank was
   used, meaning the dispatch timestamp).
3. In `docs/BUILD_PLAN.md` under "M3 historical ingest", update the status from
   "shipped, not yet run" to "shipped and run" and add the dispatch date, the
   commit SHA and the row counts from `OWNER_SETUP.md`.
4. Add a note to `docs/OWNER_SETUP.md` stating that future re-dispatches of
   `historical-ingest.yml` for a season update must record their commit SHA and
   row delta in this file under a dated log entry.

**Constraints**: The commit SHA must be recovered from the Actions run log, not
invented. If the SHA is not recoverable from logs, state that it is unknown and
describe how future dispatches will record it. Do not modify the ingest workflow
itself as part of this item.

**Tests first**: Not applicable for documentation. Validate by confirming the SHA
exists on GitHub at
`https://github.com/vaastav/Fantasy-Premier-League/commit/<SHA>` before
recording it.

**Done when**:

1. The vaastav commit SHA (or an explicit "not recoverable" note with a procedure
   for future runs) appears in `docs/OWNER_SETUP.md`.
2. `docs/BUILD_PLAN.md` M3 status reflects the actual dispatch outcome.
3. `pnpm format:check` passes on both files.

**Validate**: `pnpm format:check`. Confirm the SHA or "not recoverable" note is
present via `grep -n "vaastav.*commit\|SHA" docs/OWNER_SETUP.md`.

---

## 190 — Add `CONTRIBUTING.md` (Impact: M)

**Files**: `CONTRIBUTING.md` (create at repository root)

**Problem**: No `CONTRIBUTING.md` exists. The repository has a specific
contribution workflow — test-first, focused validation then `pnpm check`,
`docs/LIMITATIONS.md` as a hard boundary, no agent-defaulted parameters — that
is not documented anywhere a new contributor would look. The PR template
(`docs/pull_request_template.md`) contains the delivery checklist but not the
rationale or workflow.

**Change**: Create `CONTRIBUTING.md` with the following sections, deriving every
fact from existing repository files:

1. **Environment prerequisites** — Node 20.20.2 (from `package.json`
   `engines`), pnpm 9.15.9 (from `packageManager`), Python 3.12 (from
   `pyproject.toml`), Docker (for `supabase db start`). Reference
   `docs/RUNBOOK.md` local dev environment row.
2. **Getting started** — `corepack enable`, `pnpm install --frozen-lockfile`,
   `python -m pip install -e ".[dev]"`, `pnpm exec supabase db start`,
   `pnpm exec supabase db reset --local`.
3. **The contribution loop** — (a) write a failing test, (b) implement the
   minimum change to make it pass, (c) run the focused test, (d) run
   `pnpm check` before opening a PR. Name the focused test commands from item 183.
4. **Hard boundaries** — link to `docs/LIMITATIONS.md`; state that a missing
   source disables or downgrades a feature and never licenses a plausible
   estimate.
5. **Workflow actions policy** — all action references in `.github/workflows/`
   must use full 40-character commit SHAs (from item 172).
6. **Secret hygiene** — no `VITE_`-prefixed secret names; no secret in git;
   no AI-tool row inspection of the production database.
7. **PR checklist** — reference `.github/pull_request_template.md` for the
   delivery checklist.
8. **Pre-commit hooks** — if item 177 is implemented, add installation
   instructions here.

**Constraints**: Every fact must be derivable from an existing file in the
repository. Do not invent a process that is not already practiced. Do not
describe the production Supabase project's internal schema.

**Tests first**: Not applicable for a new document. Validate by following the
"Getting started" steps on a clean machine (or clean checkout) and confirming
they succeed.

**Done when**:

1. `CONTRIBUTING.md` exists at the repository root with all eight sections.
2. The "Getting started" steps match the commands in `docs/RUNBOOK.md` and
   `package.json`.
3. `pnpm format:check` passes.
4. No secret value or production row data appears in the file.

**Validate**: `pnpm format:check`. Follow the "Getting started" steps in a clean
environment.

---

## 191 — Document the API surface (Impact: M)

**Files**: `docs/API.md` (create new), or add a section to `docs/RUNBOOK.md`

**Problem**: No API surface document exists. The project exposes three route
families from `api/`: `GET /api/health`, `GET /api/fpl/*` (proxied FPL
endpoints), and `GET /api/team/:id`. Response shapes are defined in
`packages/contracts/`, but the status codes, degraded-reason values and
parameter constraints are scattered across `api/` TypeScript files and not
collected in one place a consumer can read.

**Change**: Create `docs/API.md` with the following sections, deriving all facts
from `api/health.ts`, `api/fpl/[...path].ts`, `api/team/[id].ts`, and the Zod
schemas in `packages/contracts/`:

1. **`GET /api/health`** — response shape (`{ status, service, revision }`),
   status codes (200 always), `Cache-Control: no-store` header, and the meaning
   of `revision` (Vercel git commit SHA or `"local"`).
2. **`GET /api/fpl/*`** — describe the pass-through proxy behaviour, the
   `x-fpl-andres-version` or user-agent header added, rate-limit behaviour (if
   any), and the status codes proxied from the upstream FPL API. Note that the
   proxied paths are not authenticated and expose only public FPL data.
3. **`GET /api/team/:id`** — parameter constraint (`id` is a positive integer
   FPL Team ID), response shape (cite the Zod contract schema name and file),
   every possible value of the `degraded_reason` field with its cause, the
   `x-fpl-andres-debug` response header behaviour, and status codes (200 for
   both full and degraded responses, 500 only if the top-level catch fails).
4. **Error handling** — describe the `try/catch` wrapper, the degraded envelope
   contract, and the `console.error` prefix used in Vercel function logs.

**Constraints**: Every stated parameter, status code and response field must exist
in the current source. Do not document endpoints that do not exist yet. Do not
invent degraded reason values — enumerate only those present in the contract
schema. The document must not contain any secret values.

**Tests first**: Not applicable for documentation. Validate by running the canary
`curl -s https://qpmlfbuouporvwebjxhk.supabase.co` — actually, validate by
reading the source files and confirming each stated fact with `grep`.

**Done when**:

1. `docs/API.md` exists with all four sections.
2. Every `degraded_reason` value is listed and sourced to a code path.
3. `pnpm format:check` passes.
4. `grep -n "degraded_reason\|DegradedReason" packages/contracts/` confirms all
   listed values exist.

**Validate**: `pnpm format:check`. `grep -rn "degraded_reason" packages/` to
confirm values match the document.

---

## 192 — Add a schema reference document for `supabase/` (Impact: M)

**Files**: `docs/SCHEMA.md` (create new)

**Problem**: The `supabase/migrations/` directory contains ten migration files
spanning `foundation`, `evidence_snapshots`, `projection_artifacts`,
`optimization_artifacts`, `foreign_key_indexes`, `history_corpus`,
`defensive_components`, `fixture_grain_and_event_range`, `backtest_artifacts`,
and `crowd_snapshots`. There is no single reference document that names each
table, its purpose, its grain (one row per what?), and its immutability status.
`docs/MODEL_CARDS.md` references `projection_runs` and `model_promotion_decisions`
as immutable but a contributor must read the migration SQL to confirm grain.

**Change**: Create `docs/SCHEMA.md` by reading each migration file in
`supabase/migrations/` and extracting:

1. A table inventory listing every table name, the migration file that defines
   it, its grain (e.g. "one row per player × gameweek × season"), and its
   immutability status (append-only with no UPDATE/DELETE grants, or mutable).
2. For each table: a one-sentence purpose statement.
3. A note on RLS — all tables have forced RLS enabled; no browser-facing policy
   exists; only the server role (`SUPABASE_SECRET_KEY`) reads and writes.
4. A note on foreign key structure — reference the `foreign_key_indexes`
   migration and note that all FK indexes are listed there.
5. A note that production was bootstrapped by pasting migrations into the SQL
   Editor, not via `supabase db push`, and that new migrations must follow the
   procedure in `docs/RUNBOOK.md`.

**Constraints**: Every stated table name must exist in a migration file —
confirm with `grep -rn "CREATE TABLE" supabase/migrations/`. Do not describe
the internal contents of application rows. Do not reveal the production project
ref (`qpmlfbuouporvwebjxhk`) unless it is already public in `docs/RUNBOOK.md`
(it is).

**Tests first**: Not applicable for documentation. Before writing, generate the
table list with `grep -rn "CREATE TABLE" supabase/migrations/` and use it as
the source of truth.

**Done when**:

1. `docs/SCHEMA.md` lists every table defined across the ten migration files.
2. Each table entry states grain, purpose and immutability status.
3. `pnpm format:check` passes.
4. `grep -rn "CREATE TABLE" supabase/migrations/ | wc -l` matches the count of
   table entries in the document.

**Validate**: `pnpm format:check`. `grep -c "##" docs/SCHEMA.md` vs.
`grep -c "CREATE TABLE" supabase/migrations/*.sql`.

---

## 193 — Mark `docs/BUILD_PLAN.md` as historical (Impact: M)

**Files**: `docs/BUILD_PLAN.md`

**Problem**: `docs/ROADMAP.md` opens with "Supersedes the milestone list in
`BUILD_PLAN.md`, which took the product from scaffold to a working corpus and
models. That work is done." However, `docs/BUILD_PLAN.md` itself carries no
such notice. A contributor reading `BUILD_PLAN.md` directly — via a direct link
or a `docs/` directory browse — encounters an active-looking milestone plan
without knowing it has been superseded. The "Where we start" table in
`BUILD_PLAN.md` uses present tense ("none", "not yet run") that is now stale for
several milestones.

**Change**:

1. Add a callout box or bold notice at the very top of `docs/BUILD_PLAN.md`
   (before the `# Build Plan` heading or immediately after it) stating:
   "**Historical document.** This plan is superseded by
   [`docs/ROADMAP.md`](ROADMAP.md), which describes the current delivery
   roadmap. The milestone records below are preserved for provenance."
2. Update the "Where we start" table rows for milestones that have shipped
   (M1 persistence layer, M2 history schema, M3 historical ingest, M5 minutes)
   to reflect their shipped status, consistent with the "Shipped so far" table
   already present in the document.
3. Do not delete the document or rewrite its content — it is a provenance
   record.

**Constraints**: The notice must appear before any substantive content so it is
the first thing a reader sees. `pnpm format:check` must pass. Do not alter the
milestone descriptions, only their status markers and the header notice.

**Tests first**: Not applicable. Validate by reading the file in a browser-side
Markdown renderer to confirm the notice renders prominently.

**Done when**:

1. A "Historical document" notice appears at or near the top of
   `docs/BUILD_PLAN.md`.
2. The notice links to `docs/ROADMAP.md`.
3. The "Where we start" table statuses are consistent with "Shipped so far".
4. `pnpm format:check` passes.

**Validate**: `pnpm format:check`. Read the top of `docs/BUILD_PLAN.md` and
confirm the notice appears before the first heading or immediately after the
title.

---

## 194 — Add incident playbooks for corrupt ingest, failed promotion and stale public state (Impact: M)

**Files**: `docs/RUNBOOK.md` (add new incident sections)

**Problem**: `docs/RUNBOOK.md` contains one incident section ("Incident:
`/api/team/{id}` returning HTTP 500") and a general Data plane section. It
does not document what to do when: (a) a historical ingest run writes corrupt
rows (wrong season mapping, duplicate keys), (b) a model promotion run fails its
paired-bootstrap gate but the candidate is visible in the artifact tables, or
(c) the public state (`crowd_snapshots`, `element_price_observations`) is stale
because a scheduled workflow failed silently.

**Change**: Add three incident sections to `docs/RUNBOOK.md` after the existing
incident section:

1. **Incident: corrupt historical ingest** — symptoms (duplicate keys, wrong
   season in a gameweek row, row count differs from expected 185,954 baseline),
   detection (query `history_corpus` row count and join against the vaastav
   commit), remediation (identify the offending season, delete only that season's
   rows via the SQL Editor, re-dispatch `historical-ingest.yml` with the correct
   commit SHA and season filter, record the re-dispatch in `docs/OWNER_SETUP.md`).
2. **Incident: failed model promotion** — symptoms (`model_promotion_decisions`
   contains a row where the bootstrap p-value exceeds 0.05, or no promotion row
   exists for a candidate that ran), detection (query `model_promotion_decisions`
   for the candidate identity), remediation (the candidate remains
   `experimental`; do not manually insert a promotion row; investigate the
   walk-forward evaluation run in the Actions log).
3. **Incident: stale public state** — symptoms (`crowd_snapshots` or
   `element_price_observations` last row timestamp is more than 48 hours before
   a known deadline), detection (check the `capture-crowd.yml` Actions run
   history for failed or skipped runs), remediation (manually dispatch
   `capture-crowd.yml` with blank `season` and `event` inputs; confirm the new
   row's timestamp in the database).

**Constraints**: Each playbook must be actionable without AI-tool database row
inspection — row queries are described as SQL Editor steps only. Do not include
secret values. Reference existing `docs/RUNBOOK.md` sections for the SQL Editor
deployment pattern. Do not suggest `supabase db push`.

**Tests first**: Not applicable for documentation. Validate by confirming the
table names (`history_corpus`, `model_promotion_decisions`, `crowd_snapshots`,
`element_price_observations`) exist in `supabase/migrations/`.

**Done when**:

1. Three new incident sections appear in `docs/RUNBOOK.md`.
2. Each names the detection query, affected table and remediation steps.
3. `pnpm format:check` passes.
4. All referenced table names exist in `supabase/migrations/`.

**Validate**: `pnpm format:check`. `grep -n "history_corpus\|model_promotion\|crowd_snapshots" docs/RUNBOOK.md`.

---

## 195 — Record measured model performance in `docs/MODEL_CARDS.md` (Impact: M)

**Files**: `docs/MODEL_CARDS.md`

**Problem**: `docs/MODEL_CARDS.md` defines a promotion gate (paired bootstrap
`p < 0.05`, line 119) and lists four model identities but does not record the
actual measured MAE, RMSE, rank correlation or calibration figures for any model.
The "Model registry" table lists `league_venue_mean/1` and `team_venue_rates/1`
as their promotion status, but not the walkforward evaluation scores that
determined that status. A backtest claim cannot be reproduced from the document
alone without these figures.

**Change**: For each model in the registry that has been evaluated (i.e., a
walk-forward run exists in `backtest_artifacts`):

1. Add a "**Evaluation results**" subsection under each model card with:
   - The evaluation date (derived from the `backtest_artifacts` run).
   - The holdout season (2024/25 per `docs/OWNER_SETUP.md`).
   - Measured MAE, RMSE and rank correlation against the league venue mean
     baseline.
   - The bootstrap p-value.
   - The promotion decision outcome (promoted / not promoted).
2. If no walk-forward evaluation has been run yet for a model, add a placeholder:
   "Evaluation: not yet run. Run the walk-forward backtest driver and record
   results here."
3. Add a "**Performance targets**" section at the top of the document, before the
   model registry, stating the acceptance threshold (beat the league venue mean
   benchmark at `p < 0.05`) so readers can interpret the evaluation results.

**Constraints**: Only record figures that exist in the `backtest_artifacts` table
or in Actions run logs. Do not invent or estimate figures. If no evaluation has
been run, say so explicitly — do not substitute a calibration estimate. The
`experimental` label must not be changed to `active` without a passing evaluation
run.

**Tests first**: Before editing, query `backtest_artifacts` via the SQL Editor to
determine which models have run evaluations. If the table is empty (no
evaluations run), add only placeholders and the Performance targets section.

**Done when**:

1. A "Performance targets" section exists at the top of `docs/MODEL_CARDS.md`.
2. Each model card has an "Evaluation results" subsection, either with measured
   figures or an explicit "not yet run" placeholder.
3. `pnpm format:check` passes.
4. No figure is stated without a source (evaluation run date and artifact table).

**Validate**: `pnpm format:check`. `grep -n "Evaluation results\|not yet run" docs/MODEL_CARDS.md`.

---

## 196 — Document parameter provenance in `docs/MODEL.md` (Impact: M)

**Files**: `docs/MODEL.md`

**Problem**: `docs/MODEL.md` header (lines 4–8) states that every constant is
"a figure measured from the corpus" or a domain choice, and each says which.
However, several parameters in the document do not yet carry that attribution:

- `decay_half_life_events = 4.0` (line 53) is shown but not attributed to a
  source (corpus measurement, domain literature, or agent choice).
- The `0.8/0.2` form blend (line 271) is shown without a source note.
- The `positional prior` used in shrinkage (line 102) does not name the corpus
  query or literature reference that calibrated it.
- The `current_weight = min(1, current_minutes / 900)` formula (line 94)
  cites 900 as a full-season minute count but does not state whether this is a
  FIFA/FPL convention or a corpus-derived threshold.

**Change**: For each unsourced parameter, find its definition in
`python/fpl_andres/` source files (use
`grep -rn "decay_half_life\|form_blend\|positional_prior\|900" python/`) and
determine whether it is:

1. A corpus-measured figure — add `(corpus-measured: <description of corpus
query>)`.
2. A domain convention — add `(domain convention: <source, e.g. "38 matches × 
90 minutes/match = 3420 total minutes, capped at 900 for a starting player">)`.
3. An agent default that violates the "no agent defaults" rule — if found,
   this must be escalated to a failing test and the parameter must be sourced.

Add a `## Parameter provenance table` section near the end of `docs/MODEL.md`
summarising all parameters with their values and attribution type in a Markdown
table.

**Constraints**: Do not add parameters that are not present in the source. Do
not mark any parameter as "domain convention" without naming the convention's
origin. The "no agent defaults" rule is absolute — if a parameter cannot be
sourced, it is a bug to fix, not a documentation gap to paper over.

**Tests first**: Run `grep -rn "decay_half_life\|form_blend\|900\|shrinkage" python/fpl_andres/` to list all parameters before editing. Confirm each appears in
the source with the value documented.

**Done when**:

1. A `## Parameter provenance table` section exists in `docs/MODEL.md` with
   all parameters, their values and their attribution type.
2. No parameter is listed as "agent default" — each must be corpus-measured or
   a named convention.
3. `pnpm format:check` passes.

**Validate**: `pnpm format:check`. `grep -n "Parameter provenance" docs/MODEL.md`.

---

## 197 — Record model lineage on promotion decisions (Impact: M)

**Files**: `docs/MODEL_CARDS.md`, `supabase/migrations/` (read-only reference)

**Problem**: `docs/MODEL_CARDS.md` (line 119) states "Every promotion run
supplies its metric, seed, bootstrap resample count, confidence and [data]".
The `model_promotion_decisions` table (defined in a migration) is append-only.
However, the document does not specify that the code version (git commit SHA),
the Python and key-library dependency versions, and the corpus revision (vaastav
commit SHA) must be recorded alongside the statistical metrics. Without these,
a promotion decision cannot be reproduced even if the metric, seed and confidence
are known.

**Change**:

1. In `docs/MODEL_CARDS.md`, add a "**Promotion record requirements**" subsection
   (after line 119) listing the mandatory fields for each promotion decision row:
   - Model identity and version.
   - Evaluation corpus: vaastav commit SHA and season range.
   - Holdout season.
   - Evaluation date (`data_available_at` timestamp).
   - Code version: git commit SHA of the repository at the time of the run.
   - Key dependency versions: Python version, numpy version, scipy version,
     pydantic version (all from `pyproject.toml` bounds at run time).
   - Statistical metrics: MAE, RMSE, rank correlation vs. baseline, bootstrap
     p-value, seed, resample count.
   - Promotion outcome and reviewer (GitHub Actions run URL).
2. Check the `model_promotion_decisions` migration schema to confirm which of
   these fields have columns already. For fields without columns, note in the
   document that they are recorded in the Actions run log URL, and that the URL
   must be stored in the table's `notes` or `run_url` column (or that a future
   migration should add those columns).

**Constraints**: Do not alter the production schema as part of this item. Do not
add a migration without the full local-CI review cycle. If a column is absent,
note it as a gap to close in a future migration. Do not invent column names —
read the actual migration SQL with
`grep -A 30 "model_promotion_decisions" supabase/migrations/*.sql`.

**Tests first**: Not applicable for documentation. Validate by reading the
migration and confirming the stated column names exist.

**Done when**:

1. A "Promotion record requirements" subsection exists in `docs/MODEL_CARDS.md`.
2. All nine mandatory fields are listed.
3. Missing database columns are explicitly noted as gaps.
4. `pnpm format:check` passes.

**Validate**: `pnpm format:check`. `grep -n "Promotion record" docs/MODEL_CARDS.md`.

---

## 198 — Add a local development runbook (Impact: M)

**Files**: `docs/RUNBOOK.md` (add "Local development" section) or
`docs/LOCAL_DEV.md` (create new)

**Problem**: `docs/RUNBOOK.md` mentions the local dev environment in one table
row ("Local dev: `pnpm dev` — Vite dev server + Vercel functions via `vercel dev`
if required. Uses local Supabase CLI stack.") but does not explain how to seed
the local database, how to inspect local rows, or how to debug an API route
locally. A contributor who has never used the Supabase CLI or Vercel dev mode
cannot complete a local development cycle from `docs/RUNBOOK.md` alone.

**Change**: Add a "Local development" section to `docs/RUNBOOK.md` (or create
`docs/LOCAL_DEV.md` and link from `RUNBOOK.md`) with the following subsections,
deriving all commands from `package.json` scripts and `docs/RUNBOOK.md`
existing content:

1. **Starting the local stack** — `pnpm exec supabase db start`,
   `pnpm exec supabase db reset --local`, `pnpm dev` (Vite dev server).
2. **Seeding local data** — how to run `historical-ingest.yml`-equivalent
   commands locally using the Supabase local connection string (not the
   production secret). Note that the production key must not be used locally.
3. **Inspecting the local database** — use `pnpm exec supabase db studio` or
   `psql` with the local connection string from `supabase status`. Do not use
   AI tools to inspect rows.
4. **Debugging API routes** — `vercel dev` at the repo root; confirm the
   `SUPABASE_URL` and `SUPABASE_SECRET_KEY` environment variables point to the
   local Supabase instance (not production) by setting them in a `.env.local`
   file (which must be in `.gitignore`).
5. **Running focused tests** — reference the `pnpm test:focused` and
   `pnpm py:test` aliases from item 183 once added.
6. **Escalating to the full gate** — `pnpm check` is the final local gate
   before opening a PR.

**Constraints**: The `SUPABASE_SECRET_KEY` for the local Supabase stack is the
fixed Supabase CLI default (not a secret) — state this clearly so contributors
do not confuse it with the production key. Do not include the production project
ref or production key. `.env.local` must be listed in `.gitignore` (confirm with
`grep ".env.local" .gitignore`).

**Tests first**: Follow the "Starting the local stack" steps on a clean checkout
to confirm they work before writing.

**Done when**:

1. A "Local development" section exists with all six subsections.
2. No production secret appears in the document.
3. The document clearly distinguishes local Supabase credentials from production.
4. `pnpm format:check` passes.

**Validate**: `pnpm format:check`. Follow steps 1 and 3 in a clean environment.

---

## 199 — Add a quick-reference table to `docs/LIMITATIONS.md` (Impact: M)

**Files**: `docs/LIMITATIONS.md`

**Problem**: `docs/LIMITATIONS.md` documents six capability limits (public team
state, matchups, out of position, defensive contributions, historical data,
historical manager state) in prose paragraphs. A developer implementing a new
feature must read the entire document to determine which features are affected by
which limits. There is no at-a-glance summary that maps each limit to the product
features it disables or downgrades.

**Change**: Add a "Quick reference" section at the top of `docs/LIMITATIONS.md`
(after the introductory paragraph, before the "Public team state" section) with a
Markdown table. Each row maps one limit to the features it affects. Derive the
feature names from `apps/web/`, `api/`, and `docs/ROADMAP.md`.

Table columns: **Limit** | **Affected features** | **Behavior** (disables /
downgrades / requires `state_as_of`).

Rows to include (verify each against the prose that follows the table):

- Public team state staleness → team dossier bank/transfers/chips/selling prices
  → requires `state_as_of` and manager correction.
- Matchups unavailable → flank assignment, sprint speed, marking, aerial
  weakness, high-line exposure → feature disabled, `unavailable` label.
- OOP without licensed event data → specific player-v-player matchup → disabled.
- Defensive contributions pre-2025/26 → DefCon model → small-sample warning,
  `experimental` label.
- Historical archive pinned revisions → walk-forward runner → rejects post-cutoff
  features.
- Historical manager state lost at season rollover → personal squad replay,
  rival cohort reconstruction → `unavailable` for completed seasons.

**Constraints**: The table must not add new limits — it summarises what the prose
already states. Every row must be derived from the existing paragraphs in
`docs/LIMITATIONS.md`. Do not add an "estimated" or "plausible" row; the table
must not soften any limit into a downgrade that the prose describes as disabled.

**Tests first**: Not applicable for documentation. Validate by reading the prose
paragraph for each table row and confirming the "Behavior" column matches.

**Done when**:

1. A "Quick reference" table exists in `docs/LIMITATIONS.md` with at least six
   rows.
2. Every row in the table has a matching prose paragraph below it.
3. `pnpm format:check` passes.
4. No table row contradicts the prose it summarises.

**Validate**: `pnpm format:check`. Read each table row and its corresponding
prose section to confirm consistency.

---

## 200 — Add issue templates for bug reports, data-source breaks and model regressions (Impact: L)

**Files**: `.github/ISSUE_TEMPLATE/` (create directory and template files)

**Problem**: No GitHub issue templates exist. Without templates, bug reports and
data-source break reports arrive without the structured information needed to
reproduce or triage them. A model regression report without the model identity,
the evaluation date and the corpus revision cannot be acted on. GitHub defaults
to a blank issue form, which produces low-signal reports.

**Change**: Create three issue templates in `.github/ISSUE_TEMPLATE/`:

1. `bug_report.yml` — fields: describe the bug (required), steps to reproduce
   (required), expected behavior, actual behavior, FPL Team ID (optional, for
   API issues), browser and OS (for web issues), relevant log output.
2. `data_source_break.yml` — fields: which data source (FPL API endpoint, vaastav
   archive, Understat — select list), observed symptom (required), last known
   working date, whether the break affects live or historical data.
3. `model_regression.yml` — fields: model identity (from the MODEL_CARDS registry:
   `league_venue_mean/1`, `team_venue_rates/1`, `dixon_coles/1`,
   `deployment_signal/1`), metric that regressed (MAE, RMSE, rank correlation),
   evaluation corpus (season and vaastav commit SHA if known), expected and
   observed values.

Use YAML-based issue templates (`.yml` format) rather than Markdown templates so
GitHub renders structured forms. Each template must include `name:`, `description:`,
`labels:` and `body:` keys. Apply existing repository labels (`bug`,
`dependencies`) where appropriate; do not introduce new labels that have not
been created in the repository.

**Constraints**: Do not include secret values or production row data in the
templates. The model identity select list must match the current registry in
`docs/MODEL_CARDS.md`. Templates must pass `yamllint`.

**Tests first**: Not applicable. Validate by opening a new issue in the GitHub
UI and confirming the template chooser appears with all three options.

**Done when**:

1. Three template files exist in `.github/ISSUE_TEMPLATE/`.
2. Each renders a structured form in the GitHub new-issue UI.
3. `yamllint .github/ISSUE_TEMPLATE/*.yml` passes.
4. Model identity options match `docs/MODEL_CARDS.md`.

**Validate**: `yamllint .github/ISSUE_TEMPLATE/*.yml`. Open the GitHub
"New issue" page and confirm three template options appear.

---

## 201 — Add a troubleshooting FAQ for Docker, corepack and Supabase CLI setup failures (Impact: L)

**Files**: `docs/TROUBLESHOOTING.md` (create new), or add to `CONTRIBUTING.md`

**Problem**: No troubleshooting document exists. Contributors installing the
development stack for the first time frequently encounter three failure modes that
are not documented: (a) Docker not running when `supabase db start` is invoked,
(b) corepack version mismatch or activation failure, (c) Supabase CLI version
mismatch when the local container does not match the migration SQL dialect.
These failures produce cryptic error messages that require knowing the root cause
to interpret.

**Change**: Create `docs/TROUBLESHOOTING.md` with the following sections,
sourcing every remedy from `package.json`, `pyproject.toml` and the Supabase CLI
behavior documented in `docs/RUNBOOK.md`:

1. **Docker not running** — symptom: `Cannot connect to the Docker daemon`;
   remedy: start Docker Desktop or the Docker daemon (`sudo systemctl start
docker`); note that Supabase CLI requires Docker for `supabase db start`.
2. **corepack activation failure** — symptom: `pnpm: command not found` or
   `corepack: command not found`; remedy: ensure Node 20.20.2 is active
   (check with `node --version`), then run `corepack enable`. Note the
   `packageManager` field in `package.json` pins pnpm 9.15.9.
3. **Supabase CLI migration mismatch** — symptom: `ERROR: column X does not
exist` during `supabase db reset --local`; remedy: confirm the supabase CLI
   version matches the version in `package.json` devDependencies (`supabase`
   at `2.110.0`) with `pnpm exec supabase --version`; reinstall with
   `pnpm install`.
4. **Python version mismatch** — symptom: `SyntaxError` or mypy type errors
   caused by running Python <3.12; remedy: confirm `python --version` returns
   3.12.x; use `pyenv` or your system package manager to install 3.12.
5. **`pnpm check` fails at `contracts:check`** — symptom: schema drift error;
   remedy: run `pnpm contracts:generate` and commit the output.

**Constraints**: Every version number cited must match the current `package.json`
or `pyproject.toml`. Do not describe workarounds that bypass pinned versions.
Do not include production secrets or the production Supabase URL.

**Tests first**: Reproduce each failure mode on a clean checkout (or VM) and
confirm the remedy resolves it before documenting.

**Done when**:

1. `docs/TROUBLESHOOTING.md` exists with all five sections.
2. Version numbers match `package.json` and `pyproject.toml`.
3. `pnpm format:check` passes.

**Validate**: `pnpm format:check`. Verify version numbers with
`grep -n "supabase\|pnpm\|node" package.json`.

---

## 202 — Extend `DESIGN.md` with a component inventory and accessibility checklist (Impact: L)

**Files**: `DESIGN.md`

**Problem**: `DESIGN.md` documents the product posture, signature elements, voice
and palette but does not contain a component inventory (which UI components exist
and what accessibility role they carry) or an accessibility checklist that the
Playwright browser journeys (`pnpm test:e2e`) can assert. Without an explicit
checklist, accessibility regressions are invisible until a user reports them. The
`eslint-plugin-jsx-a11y` (listed in `package.json` devDependencies at `6.10.2`)
enforces static a11y rules but not runtime or interaction semantics.

**Change**: Add two sections to `DESIGN.md`:

1. **Component inventory** — a table listing the primary UI components in
   `apps/web/src/` (team dossier, recommendation card, evidence chip, formation
   view, error envelope) with: component name, file path, primary ARIA role and
   keyboard interaction model. Derive the component names from `apps/web/src/`
   directory listing and `App.tsx`.
2. **Accessibility checklist** — a numbered list of assertions that the Playwright
   journeys must make (or that a manual audit must cover). Items to include:
   - All interactive elements are reachable by keyboard (Tab order).
   - All images and icons have `aria-label` or `aria-hidden`.
   - Error states announce themselves to screen readers (ARIA live regions or
     role="alert").
   - Color is not the sole means of conveying information (the goalkeeper-kit
     hot accent carries a role label as well as a color).
   - Form inputs (Team ID entry) have associated `<label>` elements.
   - Contrast ratio meets WCAG 2.1 AA for all text on both themes.

**Constraints**: The component inventory must list only components that currently
exist in `apps/web/src/`. Do not invent components or claim accessibility
properties that have not been verified. The checklist must not contradict the
color system described in `DESIGN.md` (goalkeeper-kit accent is intentional, not
a violation).

**Tests first**: Before editing, list `apps/web/src/` components with
`find apps/web/src -name "*.tsx" | head -20` and use that as the source for the
inventory.

**Done when**:

1. A component inventory table exists in `DESIGN.md`.
2. An accessibility checklist with at least six items exists.
3. `pnpm format:check` passes.
4. The checklist items are referenced (or can be referenced) in Playwright
   journey comments.

**Validate**: `pnpm format:check`. `grep -n "Component inventory\|Accessibility" DESIGN.md`.

---

## 203 — Add a first-contribution checklist (Impact: L)

**Files**: `CONTRIBUTING.md` (add section, or create if item 190 is not yet
done)

**Problem**: No first-contribution checklist exists. A new contributor must
discover the documents to read and the verification commands to run by exploring
the repository. The order matters: reading `docs/LIMITATIONS.md` before writing
any code prevents a class of rejected PR comments; understanding `pnpm check`
before opening a PR prevents failed CI surprises.

**Change**: Add a "First contribution checklist" section to `CONTRIBUTING.md`
(or as a standalone section if `CONTRIBUTING.md` does not yet exist — in that
case, also complete item 190):

1. Read `docs/LIMITATIONS.md` — know which features are disabled vs. degraded.
2. Read `DESIGN.md` — understand the voice, component model and accessibility
   checklist before touching frontend code.
3. Read `docs/RUNBOOK.md` — understand deploy, secrets and incident procedures.
4. Read `docs/MODEL.md` — understand the scoring model before touching
   `python/fpl_andres/`.
5. Install dependencies: `corepack enable && pnpm install --frozen-lockfile &&
python -m pip install -e ".[dev]"`.
6. Start the local stack: `pnpm exec supabase db start &&
pnpm exec supabase db reset --local`.
7. Verify the environment: `pnpm check` (must exit 0). This is the single
   command that proves the environment works.
8. Read `.github/pull_request_template.md` — know the delivery checklist before
   writing a single line.

State that steps 1–4 are mandatory reads, not optional skims, because the
repository has hard constraints that override general conventions.

**Constraints**: Every command must exist as a `package.json` script or a
documented Python command. Do not add commands that require production secrets.
`pnpm check` must be reachable without production credentials because it uses
only the local Supabase stack.

**Tests first**: Run step 7 (`pnpm check`) on a clean checkout (only local
Supabase running) and confirm it exits 0.

**Done when**:

1. A "First contribution checklist" section with eight numbered steps exists in
   `CONTRIBUTING.md`.
2. Step 7 (`pnpm check`) is confirmed to pass on a clean local setup.
3. `pnpm format:check` passes.

**Validate**: `pnpm format:check`. Follow steps 5–7 on a clean checkout.

---

## 204 — Add a performance-debugging note for the projector, solvers and API latency (Impact: L)

**Files**: `docs/RUNBOOK.md` (add section) or `docs/PERFORMANCE.md` (create new)

**Problem**: No performance-debugging guidance exists. The three main performance
hot spots are the Python projector (`python/fpl_andres/projector.py`), the MILP
solver (`python/fpl_andres/solver/`), and the Vercel API function latency for
`/api/team/:id`. A contributor who adds a slow loop to the projector or a
redundant solver constraint has no documented method for measuring the regression.

**Change**: Add a "Performance debugging" section to `docs/RUNBOOK.md` (or create
`docs/PERFORMANCE.md`) with the following subsections:

1. **Profiling the projector** — run
   `python -m cProfile -o profile.out -m fpl_andres.cli.<entry>` followed by
   `python -m pstats profile.out` and sort by `cumtime`. State the expected
   baseline: full-season projection for one team should complete in under N
   seconds (derive N from a local timing run on the current codebase and record
   it). Note that `scipy.optimize` calls dominate; look for unexpectedly high
   call counts before optimizing.
2. **Timing the solvers** — wrap the solver call in `time.perf_counter()` and
   log the duration. The MILP solver (`python-mip` or equivalent) scales with
   the number of binary variables; if solve time exceeds 5 seconds, log the
   model size (variables, constraints) and check for missing bounds.
3. **Measuring API latency** — use `curl -w "%{time_total}" -s -o /dev/null
https://<vercel-preview-url>/api/team/212279` against the preview deployment.
   The target is under 3 seconds for a cold-start Vercel function (10-second
   `maxDuration` from `vercel.json`). If latency is high, check the Vercel
   function logs for database query duration vs. FPL API fetch duration.
4. **Bundle impact** — reference item 179 (`pnpm --filter @fpl-andres/web
size:check`) for measuring JavaScript bundle growth.

**Constraints**: Profiling commands must use only tools available in
`pyproject.toml` `[dev]` extras or Python's standard library (`cProfile`,
`pstats`, `time`). Do not recommend commercial profiling tools. The Vercel
preview URL in the curl command must use a placeholder, not the actual production
URL. The production canary Team ID `212279` may be used as it is a public
identifier.

**Tests first**: Run the cProfile command locally on the current projector entry
point, record the wall time, and use that as the documented baseline N.

**Done when**:

1. A "Performance debugging" section exists with all four subsections.
2. The projector baseline wall time is documented from a real local run.
3. The API latency target (under 3 seconds) matches `vercel.json`
   `maxDuration: 10`.
4. `pnpm format:check` passes.

**Validate**: `pnpm format:check`. Run the cProfile command locally to confirm
it works against the current codebase.
