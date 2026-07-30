# Owner Setup — Remaining Checklist

Completed account, OAuth, DNS and secret-entry steps have been removed. This file now
tracks only what still needs an owner decision. Never send a password, access token,
database password, secret key or webhook secret in chat, an issue, a pull request or a
committed file.

## Confirmed project facts

- [x] Public smoke-test FPL Team ID: `212279`.
- [x] Hosted Supabase project: `fpl-andres-production` (ref `qpmlfbuouporvwebjxhk`,
      URL `https://qpmlfbuouporvwebjxhk.supabase.co`).
- [x] The free-plan deployment uses this one hosted production project. There is no
      hosted staging project. Migrations must pass local policy tests and Linux CI
      Supabase reset/lint before they touch production.
- [x] VS Code MCP remains disabled by organization policy. Any future schema change
      goes through a controlled migration-history/deployment workflow, not the
      Dashboard SQL Editor.
- [x] Vercel project imported (`prj_SVGVMksXtLPebuLfEH8Xh1CJyIGz`), production branch
      `main`, Framework Preset `Other`, Root Directory empty, Node.js 24.x.
- [x] `SUPABASE_URL` and `SUPABASE_SECRET_KEY` present in Vercel Production and the
      GitHub `production` environment.
- [x] Foundation, evidence, projection and optimization migrations applied to the
      hosted project via SQL Editor. Table and RLS verification passed.

The project ref and API URL are identifiers, not credentials. All keys remain outside
the repository.

## Ongoing security constraints

- Never introduce a `VITE_`-prefixed Supabase, Resend or upstream secret name.
  Anything named `VITE_*` is inlined into the browser bundle at build time.
- Server routes and scheduled jobs read `SUPABASE_URL` and `SUPABASE_SECRET_KEY`
  unprefixed via `process.env`. The publishable key is not needed while browser code
  stays away from private tables.
- Do not run `supabase db push` against the hosted project. The four applied
  migrations were manually bootstrapped and are not in the CLI ledger. A controlled
  migration-history reconciliation/deployment workflow will be added before the next
  production schema change; `SUPABASE_ACCESS_TOKEN` and the database password will be
  entered directly into that workflow's environment at that point, not sooner.

## Open owner items

### Ready to verify once FPL processes a live gameweek

- [ ] Open the rendered team snapshot for team `212279` and confirm that public
      last-deadline state is clearly separated from private current corrections.
      This can only be exercised once FPL has processed at least one event; the
      preseason canary correctly returned `no_processed_event`.

### Optional — heatmap-derived out-of-position (OOP)

- [ ] Provide a rights-cleared role/event or heatmap data source, or confirm that
      heatmap inference should remain unavailable.
- [ ] Enter any provider credential directly into the approved server/worker
      environment.
- [ ] Confirm the licence permits derived role classifications such as the
      Lord Lundstram effect. Screenshots and unlicensed heat maps are not scraped.

### Before real email

1. [ ] Choose or register the public domain and a sending subdomain such as
       `updates.<domain>`.
2. [ ] Create the Resend account, add that subdomain and copy Resend's DNS records
       at the registrar.
3. [ ] After verification, create a domain-scoped send-only key.
4. [ ] Enter `RESEND_API_KEY` directly into Vercel Production when the email route
       is ready.
5. [ ] After the webhook route exists, enter `RESEND_WEBHOOK_SECRET` directly into
       Vercel Production.
6. [ ] Never put either Resend value in a `VITE_` variable or Git-tracked file.

### Before public release

- [ ] Provide the requested player-pose reference and confirm either licensed
      derivative brand use or an independently constructed original pose.
- [ ] Choose the source-code license before `v1.0.0`.
- [ ] Approve the first production model promotion after the release-candidate
      report passes. Until then, candidate models remain experimental/unavailable.

Everything else — SQL authoring, migration ordering, RLS, CI, tests, runtime code,
deployment configuration, monitoring, backups and release mechanics — remains
implementation work.
