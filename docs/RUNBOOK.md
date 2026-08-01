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

The production Supabase project was bootstrapped by pasting the four ordered
files under `supabase/migrations/` into the SQL Editor. There is no CLI
migration ledger for those files. New migrations must:

- Be forward-only, idempotent (`CREATE ... IF NOT EXISTS`, `CONCURRENTLY`
  where applicable) and reviewed on the PR.
- Pass local policy tests and Linux CI (`pnpm exec supabase db reset --local`
  plus `supabase db lint`).
- Be applied to production via the SQL Editor, then their line-item added to
  `docs/OWNER_SETUP.md` under `Open owner items` so the owner records it.

Do not run `supabase db push` against the hosted project. Do not iterate on
production schema through AI tools. Row inspection of application rows through
AI tools is also prohibited.

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
