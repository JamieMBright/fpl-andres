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
FPL100 and groupthink.

- [x] **Confirmed, with a hard condition: no paywall ships without the owner's
      explicit instruction.** It may stay free indefinitely. The gating shim is
      built last and stays dormant until told otherwise.

---

## Your queue

Exactly one job is outstanding.

### Dispatch the historical ingest

Both migrations are applied. The ingest is one dispatch, not one per season.

- [ ] **Actions → Historical Ingest → Run workflow**, with `commit` =
      `f2090d378ebd1b0c3d14884770dde95f38c50a0d` and everything else left at its
      default (`seasons` = `all`, `gameweeks` = `1-38`, `data_available_at`
      blank).
- [ ] Paste back the per-season OK/FAIL list the job prints, or the failure
      text, so the column map can be extended if a season drifted.

The run covers 2019-20 through 2025-26, roughly 180k player-gameweek rows. Each
season opens its own `workflow_runs` row, so a season that fails can be re-run
alone without redoing the others.
---

## Waiting on an external gate

Nothing to do until the gate opens.

### Live smoke test once FPL processes GW1

- [ ] Open the rendered team snapshot for `212279` after GW1 has been
      processed. Confirm public last-deadline state is clearly separated from
      any private corrections you have entered. GW1 deadline is
      2026-08-21T17:30Z.

### Live OOP evidence source

Free prototype selected (Hudl StatsBomb Open Data + SkillCorner). Neither
covers live 2026/27 Premier League, so live OOP stays `unavailable` until a
paid provider is signed off. Deferred; not blocking.

---

## Agent backlog — no owner action

Listed so the queue is visible, not because anything is needed from you. None
of these require a credential, a click or a decision.

- **FPL100, two cohorts.** Live top-100 from the overall league post-deadline,
  plus a proven cohort built from `entry/{id}/history` past ranks. Both blocked
  until GW1 populates standings.
- **Groupthink, Tier 1.** Official crowd signal only: ownership share, transfer
  momentum, `most_captained`. No third-party credential needed. Tier 2
  (Reddit/YouTube sentiment) would need free API keys and is **not** planned
  unless you ask for it.
- **Scheduled snapshot jobs.** Weekly squad picks and the end-of-season top 100. These are `schedule:`-triggered, so they use the built-in Actions token
  and need no PAT. They are the compounding assets that make a genuine personal
  replay possible next season.
- **Player enrichment.** Replace `"FPL element 101"` in the dossier with real
  names, prices, positions and clubs.
- **Model promotion run** once the corpus lands, under the confirmed
  auto-promotion policy.

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
