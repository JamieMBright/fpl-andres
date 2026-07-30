# Owner Setup — Outstanding

Only items still needing an owner decision or action live in this file. Completed
work is pruned. Never send a password, access token, database password, secret
key or webhook secret through chat, an issue, a PR or a committed file.

## Baseline (do not edit)

- Public smoke-test FPL Team ID: `212279`.
- Hosted Supabase project: `fpl-andres-production` (ref `qpmlfbuouporvwebjxhk`).
- One hosted project only. No staging. Migrations must pass local policy tests
  and Linux CI before touching production.
- Vercel project `prj_SVGVMksXtLPebuLfEH8Xh1CJyIGz`, production branch `main`,
  Framework Preset `Other`, Node.js 24.x.
- `SUPABASE_URL` and `SUPABASE_SECRET_KEY` present in Vercel Production, the
  GitHub `production` environment, and GitHub Actions repository secrets.
- Foundation, evidence, projection, optimization and FK-index migrations applied
  to the hosted project. RLS forced; no browser policy.

## Decisions taken (2026-07-30)

- **Historical source**: [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League),
  pinned commit SHAs. No paid provider for the beta.
- **Ingest window**: 2023/24 + 2024/25 + 2025/26.
- **Ingest execution**: GitHub Actions manual dispatch (`historical-ingest.yml`),
  reading the `production` environment. No local key handling.
- **Model promotion**: auto-promote a candidate that beats its baseline at
  paired-bootstrap `p < 0.05` on the 2024/25 holdout. No manual override during
  the beta.

## Security constraints (unchanged)

- Never introduce a `VITE_`-prefixed secret name. `VITE_*` is inlined into the
  browser bundle at build time.
- Server routes and jobs read unprefixed `SUPABASE_URL` and
  `SUPABASE_SECRET_KEY` via `process.env`.
- Do not run `supabase db push` against the hosted project. Migrations go
  through a controlled deployment workflow (not yet built).

---

## Open decisions

### Paywall stance for the beta

Documented in [`docs/PAYWALL.md`](PAYWALL.md): beta ships everything open;
post-beta free tier is context-less advice + `+1 GW ahead`; paid tier is
"buy me half a pint at the stadium" £3/month for planner, OOP, DefCon,
FPL50, p100 stats and groupthink.

- [ x] CONFIRMED. Do not proceed to paywall without my explicit say so. I might leave it free for a year. Confirm. Not blocking — the gating shim ships last, at v1.0.0.

---

## Next action — dispatch the historical ingest

The ingest code, schema and workflow are built and tested. Nothing has written a
real row yet because the workflow has never been dispatched. Two steps:

### 1. Apply the history migration

- [ ] Open the Supabase SQL Editor for `fpl-andres-production` and run
      [`20260801120000_history_corpus.sql`](../supabase/migrations/20260801120000_history_corpus.sql).
      Creates `seasons`, `teams`, `elements`, `fixtures`,
      `element_gameweek_stats` and `element_price_observations`. All forced RLS,
      no policy, no grant. Safe to run once; it has no `IF NOT EXISTS` guards, so
      re-running will error rather than duplicate.

### 2. Dispatch the ingest, one season at a time

- [ ] Find the current commit SHA of
      [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League)
      (Actions → any commit → copy the full 40-character SHA). Pinning is what
      makes the ingest reproducible.
- [ ] Run **Actions → Historical Ingest → Run workflow** once per season, with
      `gameweeks` left at `1-38`, for `2023-24`, then `2024-25` (the holdout
      season the promotion gate uses), then `2025-26` (the first season carrying
      DefCon labels).
- [ ] Report back the row counts the job prints, or the failure text. Header
      drift between archive seasons is expected and the ingest deliberately
      fails loudly on it rather than defaulting a column; if a season errors
      with a missing-column message, paste it and the column map gets extended.

---

### Live smoke test once FPL processes GW1

- [ ] Open the rendered team snapshot for `212279` after GW1 has been
      processed. Confirm public last-deadline state is clearly separated from
      any private corrections you have entered.

### Live OOP evidence source

Free prototype selected (Hudl StatsBomb Open Data + SkillCorner). Neither
covers live 2026/27 Premier League, so live OOP stays `unavailable` until a
paid provider is signed off. Deferred; not blocking.

---

## Before real email

Not blocking algo work. Do these when the mailing list matters.

1. [ ] Choose or register the public domain and a sending subdomain such as
       `updates.<domain>`.
2. [ ] Create the Resend account, verify the subdomain via DNS.
3. [ ] Create a domain-scoped send-only key.
4. [ ] Enter `RESEND_API_KEY` into Vercel Production when the email route ships.
5. [ ] Enter `RESEND_WEBHOOK_SECRET` into Vercel Production when the webhook
       ships.
6. [ ] Never put either Resend value in a `VITE_` variable or Git-tracked file.

## Before public v1.0.0

- [ ] Choose the source-code license.
- [ ] Approve the first production model promotion after its release-candidate
      report passes.

---

Everything else — SQL authoring, migration ordering, RLS, CI, tests, runtime
code, deployment configuration, monitoring, backups, release mechanics —
remains implementation work owned by the agent.
