# Owner Setup

This is the complete owner-only checklist. It contains account, OAuth, DNS, secret-entry
and approval steps that cannot be completed safely by the coding agent. Do not send a
password, access token, database password, secret key or webhook secret in chat, an
issue, a pull request or a committed file.

## Confirmed project facts

- [x] Public smoke-test FPL Team ID: `212279`.
- [x] Hosted Supabase project: `fpl-andres-production`.
- [x] Supabase project ref: `qpmlfbuouporvwebjxhk`.
- [x] Expected API URL: `https://qpmlfbuouporvwebjxhk.supabase.co`.
- [x] The free-plan deployment uses this one hosted production project. There is no
      hosted staging project. Migrations must pass the local policy tests and Linux CI
      Supabase reset/lint before they touch production.
- [x] VS Code MCP is disabled by organization policy. Production bootstrap therefore
      uses the Supabase Dashboard SQL Editor steps below; no editor setting or policy
      bypass is required.

The project ref and API URL are identifiers, not credentials. They may be recorded in
the repository. All keys remain outside the repository.

## Do now: bootstrap production in Supabase SQL Editor

No API key, database password, PAT or application secret is needed for these manual
steps. Sign in to Supabase Dashboard, open project `fpl-andres-production`, then open
**SQL Editor > New query**.

Run each complete file in the order below. Use a fresh SQL Editor query for each file.
After pressing **Run**, wait for a successful result before continuing. If any file
fails, stop immediately, keep the full error text, and tell Copilot which numbered step
failed. Do not edit the SQL in the Dashboard and do not continue to later files.

1. [x] Run
       [`20260729180000_foundation.sql`](../supabase/migrations/20260729180000_foundation.sql).
       This creates `workflow_runs` and the `pgcrypto` dependency used by later files.
2. [x] Run
       [`20260729183000_evidence_snapshots.sql`](../supabase/migrations/20260729183000_evidence_snapshots.sql).
       This creates immutable source/rules evidence tables and the `private` schema.
3. [x] Run
       [`20260730120000_projection_artifacts.sql`](../supabase/migrations/20260730120000_projection_artifacts.sql).
       This creates projection and model-promotion artifacts plus the immutable-model
       trigger function used by the final file.
4. [x] Run
       [`20260731120000_optimization_artifacts.sql`](../supabase/migrations/20260731120000_optimization_artifacts.sql).
       This creates immutable optimization runs/event plans and database-level array
       integrity helpers.
5. [x] Open one final SQL Editor query, run the verification query below, and confirm
       every `exists` value is `true`:

```sql
select expected_object, to_regclass(expected_object) is not null as exists
from (
    values
        ('public.workflow_runs'),
        ('public.source_snapshots'),
        ('public.rules_snapshots'),
        ('public.projection_runs'),
        ('public.team_goal_projections'),
        ('public.model_promotion_decisions'),
        ('public.optimization_runs'),
        ('public.optimization_event_plans')
) as expected(expected_object)
order by expected_object;
```

6. [x] Run this RLS verification query and confirm every row shows
       `rls_enabled = true` and `rls_forced = true`:

```sql
select
    c.relname as table_name,
    c.relrowsecurity as rls_enabled,
    c.relforcerowsecurity as rls_forced
from pg_catalog.pg_class as c
join pg_catalog.pg_namespace as n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname in (
      'workflow_runs',
      'source_snapshots',
      'rules_snapshots',
      'projection_runs',
      'team_goal_projections',
      'model_promotion_decisions',
      'optimization_runs',
      'optimization_event_plans'
  )
order by c.relname;
```

7. [x] Confirm to Copilot that all four SQL files succeeded and table/RLS verification
       passed. No key, password or database row was shared.

**Migration-history warning:** SQL Editor executes the schema but does not record these
files in the Supabase CLI migration ledger. Do not run `supabase db push` against this
project after the manual bootstrap. Copilot will add a controlled migration-history
reconciliation/deployment workflow before the next production schema change, so these
four files are not applied twice.

The official Supabase `supabase` and `supabase-postgres-best-practices` agent skills
remain installed project-locally under `.agents/skills` and pinned by
`skills-lock.json`; they are still useful for local migration, RLS and schema review
without MCP.

## Supabase app values: add only when requested by the runtime milestone

The MCP OAuth above is separate from application credentials. No app secret is needed
just to apply migrations.

Find runtime values in the Supabase dashboard under the production project's API/Data
API settings. Enter secrets directly into provider dashboards; never copy them into
chat. Use the variable names already declared in `.env.example`.

| Value                      | Secret?        | Destination                                                                         | When needed                                                        |
| -------------------------- | -------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `SUPABASE_URL`             | No             | Vercel Production and GitHub `production` environment                               | When server APIs or scheduled workers first connect to Supabase    |
| `SUPABASE_SECRET_KEY`      | Yes            | Vercel Production server environment; later GitHub `production` environment secrets | Private server writes and scheduled jobs only                      |
| `SUPABASE_PUBLISHABLE_KEY` | No, but scoped | Do not add yet                                                                      | Only if a future approved browser/public Supabase flow requires it |
| `SUPABASE_ACCESS_TOKEN`    | Yes            | Do not create or add now                                                            | Future controlled migration-history/deployment workflow only       |
| Database password          | Yes            | Do not add now                                                                      | Future controlled migration-history/deployment workflow only       |

`SUPABASE_SECRET_KEY` must never have a `VITE_` prefix, appear in browser code, or be
stored in repository settings files. The current architecture keeps browser code away
from private Supabase tables, so the publishable key is not needed today.

## When Phase 5 requests Vercel setup

1. [ ] Import `JamieMBright/fpl-andres` into Vercel.
2. [ ] Confirm the production branch is `main`, framework preset is Vite, and Vercel
       reads the committed `vercel.json`.
3. [ ] Share only the Vercel project/team IDs and generated deployment URL in chat.
4. [ ] In **Project Settings > Environment Variables**, add `SUPABASE_URL` for
       **Production** when requested.
5. [ ] Add `SUPABASE_SECRET_KEY` for **Production** only when a reviewed server route
       first requires private database access. Enter it directly in Vercel.
6. [ ] Do not create `VITE_SUPABASE_SECRET_KEY` or expose the secret to Preview/browser
       builds.

## When scheduled production jobs are added

1. [ ] In GitHub, open **Settings > Environments** and create an environment named
       `production`.
2. [ ] Add `SUPABASE_URL` as an environment variable or secret as requested by the
       workflow.
3. [ ] Add `SUPABASE_SECRET_KEY` as a `production` environment secret. Do not use a
       repository-wide secret if only production jobs need it.
4. [ ] Approve the first production workflow run after Copilot shows the exact job,
       migration/command and redaction behavior.

No production GitHub secret is needed for current pull-request CI; CI starts its own
isolated local Supabase instance.

## Smoke-test team

- [x] Team ID `212279` may be used in controlled live canaries and production smoke
      tests. An FPL Team ID is public and is not an account credential.
- [x] Controlled live canary confirmed the ID resolves through the public FPL API. On
      2026-07-29 it returned the valid preseason result `no_processed_event`; live calls
      remain outside ordinary pull-request tests.
- [ ] Review the first rendered team snapshot and confirm that public last-deadline
      state is clearly separated from private current corrections once FPL has processed
      an event.

## Before heatmap-derived OOP is enabled

- [ ] Provide a rights-cleared role/event or heatmap data source, or confirm that
      heatmap inference should remain unavailable.
- [ ] Enter any provider credential directly into the approved server/worker environment.
      Do not send it in chat.
- [ ] Confirm the licence permits derived role classifications such as the Lord
      Lundstram effect. Screenshots and unlicensed heat maps are not scraped.

## Before real email

1. [ ] Choose or register the public domain and a sending subdomain such as
       `updates.<domain>`.
2. [ ] Create the Resend account, add that subdomain and copy Resend's DNS records at
       the registrar.
3. [ ] After verification, create a domain-scoped send-only key.
4. [ ] Enter `RESEND_API_KEY` directly into Vercel Production when the email route is
       ready.
5. [ ] After the webhook route exists, enter `RESEND_WEBHOOK_SECRET` directly into
       Vercel Production.
6. [ ] Never put either Resend value in a `VITE_` variable or Git-tracked file.

## Before public release

- [ ] Provide the requested player-pose reference and confirm either licensed
      derivative brand use or an independently constructed original pose.
- [ ] Choose the source-code license before `v1.0.0`.
- [ ] Approve the first production model promotion after the release-candidate report
      passes. Until then, candidate models remain experimental/unavailable.

Everything else, including SQL authoring, migration ordering, RLS, CI, tests, runtime
code, deployment configuration, monitoring, backups and release mechanics, remains
implementation work.
