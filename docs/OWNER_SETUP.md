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

- [ ] Confirm. Not blocking — the gating shim ships last, at v1.0.0.

---

## Waiting for external gate (no action needed until then)

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
