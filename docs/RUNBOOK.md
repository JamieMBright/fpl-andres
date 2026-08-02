# FPL Andres Runbook

Operational playbook for the hosted production project. This file records what
the agent and owner have already needed to do; it is not a comprehensive SRE
manual. Every action here has a corresponding safety net in code, migrations
or the design contract — the runbook is a fast index into them.

## Environments

| Environment | Where                                             | Purpose                                                                                         |
| ----------- | ------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Production  | Vercel project `prj_SVGVMksXtLPebuLfEH8Xh1CJyIGz` | Sole hosted deployment for `main`. Free-plan Supabase `fpl-andres-production` sits behind it.   |
| Preview     | Vercel per-PR                                     | Ephemeral, driven off feature branches. Reads no private state.                                 |
| Local dev   | `pnpm dev`                                        | Vite dev server + Vercel functions via `vercel dev` if required. Uses local Supabase CLI stack. |

The production Supabase project ref is `qpmlfbuouporvwebjxhk` and the URL is
`https://qpmlfbuouporvwebjxhk.supabase.co`. Both are public identifiers; keys
never appear in git or chat.

## Deploy

The Vercel project's production branch is `main`. Every push to `main` triggers
a deploy. `vercel.json` at the repo root pins:

- `installCommand`: `corepack pnpm install --frozen-lockfile`
- `buildCommand`: `corepack pnpm --filter @fpl-andres/web build`
- `outputDirectory`: `apps/web/dist`
- `regions`: `["lhr1"]`
- `functions."api/**/*.ts".maxDuration`: `10`

Dashboard settings that must match:

- Framework Preset: `Other` (not `Vite`).
- Root Directory: empty (repo root).
- Node.js Version: `22.x` or newer — the repo requires `>=20.19.0` under
  `engine-strict=true`.
- Install/Build/Output overrides: all blank so `vercel.json` wins.

If a deploy fails, the actual error appears in the log AFTER the pnpm install
progress. Common causes we have already seen and their fixes:

- **TS2835 in `api/*.ts` about missing `.js` extensions** — `tsconfig.api.json`
  is `NodeNext`; every relative import in `api/` must include the `.js`
  suffix. `pnpm typecheck` reproduces this locally.
- **TS2554 "Expected 0-1 arguments, but got 2" on `new Error(msg, { cause })`** —
  the affected error subclass needs an explicit constructor that accepts and
  copies the `cause` option (see `TeamPublicStateContractError`).
- **`ERR_PNPM_UNSUPPORTED_ENGINE`** — the Vercel dashboard has Node pinned
  below 20.19. Update it to 22.x.

## Incident: `/api/team/{id}` returning HTTP 500 with an empty body

Both handlers under `api/` are wrapped in a top-level `try/catch` that returns a
schema-valid degraded envelope. The exception detail is **not** sent to the
client: it would expose stack paths, upstream hostnames and payload fragments to
anyone who triggers a 502. Instead the response carries an opaque
`x-fpl-andres-request-id`, repeated in the JSON body, and the detail goes to the
server log under the same id. Steps:

1. Ask the reporter for the `requestId` from the response body, or read it from
   the `x-fpl-andres-request-id` header.
2. Search the Vercel function logs for that id. Each failure emits one JSON line
   with `event: "handler_failure"`, the route, status, duration and full stack.
3. Reproduce locally with `corepack pnpm --filter @fpl-andres/web test -- src/api/team-public-state-handler.test.ts`
   and add a red test case for the observed error before fixing.

## Data plane

The production Supabase project was bootstrapped by pasting the ordered files
under `supabase/migrations/` into the SQL Editor. There is no CLI migration
ledger for those files. New migrations must:

- Be forward-only and reviewed on the PR.
- Prefer idempotent DDL (`create ... if not exists`, `create or replace`,
  `drop trigger if exists` before `create trigger`) so a partial paste can be
  re-run. Most existing migrations predate this and are **not** idempotent:
  18 `create table`, 28 `create index`, 12 `create trigger` and 6
  `create function` statements will fail on a second run.
  `python/tests/test_rollback_harness.py` pins that count.
- Pass local policy tests and Linux CI (`pnpm exec supabase db reset --local`
  plus `supabase db lint`).
- Be applied to production via the SQL Editor, then their line-item added to
  `docs/OWNER_SETUP.md` under `Open owner items` so the owner records it.

Do not run `supabase db push` against the hosted project. Do not iterate on
production schema through AI tools. Row inspection of application rows through
AI tools is also prohibited.

### Incident: a migration paste failed part-way through

Symptom: the SQL Editor reports an error mid-file, and re-running the file
fails with `relation "..." already exists` rather than completing.

The migrations are not idempotent, so there is no safe way to resume from the
middle. Do not hand-edit the file to skip the statements that succeeded: that
produces a schema no migration in the repository describes, and every later
`db reset` in CI will diverge from production.

1. Establish whether the failed migration created anything. A `create table`
   that succeeded before the error is still there.
2. If the project holds no data you cannot re-ingest — which is the case for
   every table here, since all of them are rebuilt from FPL and the vaastav
   archive — run `supabase/rollback/down.sql` in the SQL Editor. It is a single
   transaction and drops every object the migrations create, in reverse
   dependency order.
3. Re-paste the migrations in filename order from the beginning.
4. Re-run the ingest workflows to repopulate.

If the project does hold data that cannot be re-ingested, stop and take a
backup before step 2. `down.sql` destroys everything; it is a teardown, not a
per-migration undo.

The harness is exercised on every CI run: `db reset`, teardown, `db reset`
again. A table added without a matching drop fails that job rather than
failing here.

### Incident: the corpus has ingested wrong data

Symptom: a metric moves and no model changed. Or `validate` reports a season
whose `missingGameweeks` is non-empty, or whose `rows` count differs sharply
from its neighbours.

The corpus is deliberately mutable, so a bad ingest overwrites good data rather
than failing. That is the cost of being able to accept FPL's own corrections.

1. **Do not delete the season.** Re-ingesting is an upsert keyed on
   `(season, gameweek, element_id, fixture_id)`, so a corrected run replaces the
   bad rows in place. Deleting first turns a recoverable problem into a gap.
2. Identify what changed. Every corpus row carries `source_snapshot_id`; the
   `source_snapshots` row behind it is immutable and holds the content hash and
   the upstream reference. Two ingests of the same gameweek with different
   hashes is the archive having been revised, which is legitimate.
3. Re-dispatch `historical-ingest.yml` for the affected season only, pinning the
   `--commit` SHA you intend. Leaving it unpinned re-reads whatever the archive
   holds now, which is how a second wrong ingest happens.
4. Re-run `validate` and compare `corpusFingerprint` before and after. If it did
   not change, the ingest did not do what you thought.
5. Any `backtest_runs` row carrying the old `corpus_fingerprint` was measured
   over the bad data. It stays — the table is immutable — but it is no longer
   comparable to anything measured after.

The fingerprint is what makes step 5 possible. Before it existed, a moved metric
and a moved model were indistinguishable.

### Incident: a promotion decision looks wrong

Symptom: a candidate was promoted and its live behaviour disagrees, or two runs
of the same comparison disagree with each other.

1. Read the `model_promotion_decisions` row. It carries `code_revision`,
   `corpus_fingerprint`, `dependency_fingerprint` and `dependency_versions`.
2. **If `seeds_promoting` is less than `seed_replicates`, the decision was
   refused** and `reason_codes` says `seed_disagreement`. Nothing was promoted;
   look elsewhere.
3. Reproduce it: check out `code_revision`, install the versions in
   `dependency_versions`, and re-run with the recorded `seed` and `resamples`.
   A different answer means the corpus moved — compare `corpus_fingerprint`
   against the current one.
4. If it reproduces and is still wrong, the metric is wrong, not the decision.
   The bootstrap only answers the question it was given.

There is no un-promote. The table is immutable and a superseding decision is a
new row, which is the record you want: what was believed, when, and on what.

### Incident: the site is showing stale public state

Symptom: a dossier shows "Showing a stale verified snapshot", or the published
projections name a gameweek that has passed.

Two different failures wear the same face.

**The refresh is failing.** The banner is working as designed: the last verified
snapshot stays visible rather than being replaced by an error. Check
`/api/health`, then the degraded reason in the response — `fpl_unreachable`,
`fpl_source_failed` and `source_contract_failed` distinguish FPL being down from
FPL having changed shape. Only the third needs code.

**The artifacts are stale.** `projections.json` and `opening-squad.json` are
committed files, so they are exactly as fresh as the last publish commit. Check
`generatedAt` in `projections-meta.json` against the current gameweek. Republish
by running the publish CLIs and committing the result; there is no runtime path
that refreshes them, deliberately, because a claim about a commit belongs in the
commit.

Nothing here is an emergency. A stale snapshot that says it is stale is the
system behaving correctly; a stale snapshot presented as current would not be,
and the evidence banner exists to keep those apart.

## Secrets

- `SUPABASE_URL` and `SUPABASE_SECRET_KEY` live in Vercel Production and the
  GitHub `production` environment. Nothing prefixed with `VITE_` may hold a
  secret; the frontend never reads Supabase.
- Resend keys (`RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET`) are entered directly
  into Vercel Production when the email routes ship, and never mirrored into
  git.
- Any paid data provider credential goes directly into the approved
  server/worker environment. No provider secret is ever committed.

### Rotation

Rotate on a schedule and immediately on any suspicion of exposure. The order
matters: create the new secret before revoking the old one, or the scheduled
workflows fail in the gap.

**`SUPABASE_SECRET_KEY`** — rotate every 90 days.

1. In the Supabase dashboard, under Project Settings → API Keys, generate a new
   service role key. Both keys are valid at this point.
2. Update the value in Vercel Production, then in the GitHub `production`
   environment. Both must change; the web deployment and the scheduled jobs use
   different copies.
3. Redeploy so Vercel picks up the new value, and re-run one scheduled workflow
   manually to confirm it writes.
4. Revoke the old key in Supabase.
5. If you are rotating because of a suspected leak, also check
   `workflow_runs` for rows you do not recognise before revoking, since after
   revocation you lose the ability to tell what the old key did.

**`RESEND_API_KEY` and `RESEND_WEBHOOK_SECRET`** — rotate every 90 days, or
immediately if a subscriber address appears anywhere it should not.

1. Create a new key in the Resend dashboard.
2. Update Vercel Production. Resend keys are not mirrored into GitHub.
3. Send one test message before deleting the old key.
4. For the webhook secret, update the value in Resend and in Vercel in the same
   sitting: a mismatched secret rejects every inbound webhook, and the failure
   is silent from the sender's side.

**Workflow tokens** (`GITHUB_TOKEN` scopes and any PAT used by a workflow) —
prefer the built-in `GITHUB_TOKEN`, which rotates per run and needs no
management. If a PAT exists, rotate it every 90 days and record why a PAT was
needed at all, since the built-in token covers most cases.

**After any rotation**, confirm the secret has not entered the repository:

```
git log -p -S'<first 8 characters of the old secret>' -- . | head
```

An empty result is the expected one. A hit means the old key must be treated as
public regardless of revocation, and the history rewritten.

## Release

- Bump the version in `package.json`, mirror it to `apps/web/package.json` and
  `packages/*/package.json` if applicable, and add a section to `CHANGELOG.md`
  under the new version heading.
- Run `corepack pnpm check` and `python -m pytest`. Both must be green.
- Update `FPL_USER_AGENT` in `api/_lib/fpl-proxy.ts` to the new version so
  outgoing FPL requests carry an honest agent.
- Open a PR, wait for CI + dependency review + CodeQL to pass, fast-forward
  merge into `main`, then tag `vX.Y.Z` annotated with the CHANGELOG entry.

## Supply chain

- `pnpm audit --prod` runs with the `pnpm.auditConfig.ignoreGhsas` list in
  `package.json`. The current list contains only
  `GHSA-qwww-vcr4-c8h2` (React Router unstable RSC APIs — this SPA does not
  import them).
- `pip-audit` runs against the Python environment before every release.
- Dependabot proposes weekly updates for npm, pip and GitHub Actions.
- CodeQL scans on every PR and every Monday morning.
- `actions/dependency-review-action` fails PRs that introduce high-severity
  advisories, with the same allowlist.

## Live canary

Team ID `212279` is the smoke-test target. It is a public FPL Team ID, not a
credential. During preseason it returns `no_processed_event`, which is the
correct outcome; the canary is only a network + shape check.
