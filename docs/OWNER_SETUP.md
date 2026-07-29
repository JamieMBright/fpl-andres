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
- [x] The repository contains a project-scoped connector at `.vscode/mcp.json`. It can
      access only this project and only the Supabase `database`, `docs`, `development`
      and `debugging` tool groups. Account management, Functions, Storage and paid
      branching are excluded.

The project ref and API URL are identifiers, not credentials. They may be recorded in
the repository. The OAuth grant and all keys remain outside the repository.

## Do now: authorize the Supabase migration connector

The connector uses Supabase browser OAuth. It does **not** need a personal access token,
database password, publishable key, secret key or `.env` entry.

1. [ ] In VS Code, open the Command Palette with `Ctrl+Shift+P`.
2. [ ] Run `MCP: List Servers`.
3. [ ] Select `supabase-production-migrations` and choose **Start**. If VS Code asks
       whether to trust the server, review the URL and approve the official
       `https://mcp.supabase.com` server.
4. [ ] Complete the browser OAuth flow with the Supabase account that owns
       `fpl-andres-production`. Choose the organization containing project ref
       `qpmlfbuouporvwebjxhk` if prompted.
5. [ ] Return to VS Code. Run `MCP: List Servers` again and confirm the server is
       running. Use **Show Output** there if authentication failed.
6. [ ] Keep per-tool confirmation enabled. This connector is intentionally write-enabled
       so it can call `apply_migration` against the only hosted project.
7. [ ] Tell Copilot: `Supabase MCP is authenticated; verify project and migrations.`
       Do not include any token or key.

After authorization, Copilot owns the verification sequence:

1. Confirm the connector reports project URL
   `https://qpmlfbuouporvwebjxhk.supabase.co`.
2. List remote migrations and tables before writing anything.
3. Compare the remote migration ledger with tracked files under
   `supabase/migrations`.
4. Apply only missing, reviewed repository migrations in timestamp order with
   `apply_migration`; do not paste ad hoc schema changes into production.
5. Re-list migrations and tables, then run Supabase security/performance advisors.
6. Record the applied migration names without logging database rows or credentials.

Because this connector targets production, disable it between migration sessions once
real subscriber data exists. Routine production reads should later use a separate
`read_only=true` connector; automated deployments should use a controlled workflow,
not a permanently open interactive write connector.

The official Supabase `supabase` and `supabase-postgres-best-practices` agent skills are
installed project-locally under `.agents/skills` and pinned by `skills-lock.json`. The
repository rule above overrides their generic development advice: do not use
`execute_sql` for iterative schema work against this production-only project.

## Supabase app values: add only when requested by the runtime milestone

The MCP OAuth above is separate from application credentials. No app secret is needed
just to apply migrations.

Find runtime values in the Supabase dashboard under the production project's API/Data
API settings. Enter secrets directly into provider dashboards; never copy them into
chat. Use the variable names already declared in `.env.example`.

| Value                      | Secret?        | Destination                                                                         | When needed                                                             |
| -------------------------- | -------------- | ----------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `SUPABASE_URL`             | No             | Vercel Production and GitHub `production` environment                               | When server APIs or scheduled workers first connect to Supabase         |
| `SUPABASE_SECRET_KEY`      | Yes            | Vercel Production server environment; later GitHub `production` environment secrets | Private server writes and scheduled jobs only                           |
| `SUPABASE_PUBLISHABLE_KEY` | No, but scoped | Do not add yet                                                                      | Only if a future approved browser/public Supabase flow requires it      |
| `SUPABASE_ACCESS_TOKEN`    | Yes            | Do not create or add now                                                            | Only if a future automated Supabase CLI deployment workflow is approved |
| Database password          | Yes            | Do not add now                                                                      | Only if a future controlled CLI workflow proves it is required          |

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
- [ ] Before the first live smoke, confirm the ID still resolves through the public FPL
      API. Live calls stay out of ordinary pull-request tests.
- [ ] Review the first rendered team snapshot and confirm that public last-deadline
      state is clearly separated from private current corrections.

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
