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
- Historical corpus loaded 2026-07-30: seasons 2019-20 through 2025-26,
  185,954 player-gameweek rows, 380 fixtures and 20 clubs per season. Verified
  against the hosted project on 2026-07-31. Re-dispatch
  `historical-ingest.yml` only to refresh a season, never to fill a gap.

## Decisions taken (2026-07-30)

- **Historical source**: [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League),
  pinned commit SHAs. No paid provider for the beta.
- **Ingest window**: originally 2023/24 onward; widened at dispatch to 2019-20
  through 2025-26, which is what actually landed.
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

Nothing mechanical is outstanding. What is left is judgement, and none of it can
be answered by me. Nothing here blocks the site running; each one blocks a
specific capability.

### Advanced statistics

- [ ] **Confirm the scraping position.** You have said this is a hobby project
      and not commercial for at least a year. I have taken that as licence for
      **Understat** and **FBref** through `soccerdata`, which rate-limits and
      caches. I have **not** written a WhoScored scraper: you noted yourself it
      is against their terms, and non-commercial use does not cure that. Say so
      explicitly if you want that decision revisited.
- [ ] **Approve `soccerdata` as a dependency.** It is the practical path to
      FBref and Understat. It is not yet in `pyproject.toml`.
- [ ] **Accept the mapping risk.** FPL, FBref and Understat use different player
      ids and there is no official crosswalk. Community maps drift with
      transfers. A silent mis-map corrupts a player's whole history without
      erroring, so I will report mapping coverage rather than assume it.

### Data that would change the model most

- [ ] **`fplcache`** (github.com/Randdalf/fplcache) holds six-hourly bootstrap
      snapshots. This would retroactively give ownership and price history that
      my own `crowd_snapshots` table only starts collecting from now. Highest
      value per unit of effort of anything on this list.

### Benchmarks

- [ ] **Decide whether to benchmark against published projections.** FPL
      Review's free model and FPL Kiwi both publish. Comparing against them
      would be the strongest possible validation, and it may not flatter us.

### Mini-league

- [ ] **Supply the mini-league id you actually care about.** Rival ownership is
      built and tested but has nothing to point at. Individual rival picks are
      only legal to read after a deadline, so this cannot run before 21 August.

### Chips

- [ ] **Confirm the bench boost rule.** You specified triple captain, free hit
      and wildcard. Bench boost currently takes the second-largest double
      gameweek by inference, not by instruction.

---

## Know before you read the site

No action. These are the things most likely to look like bugs.

- **2026/27 gameweek 1 deadline is 21 August 2026, 17:30 UTC.** Until a gameweek
  is played there is no squad to read and no form to measure, so the site shows
  your record and prices the market rather than inventing a forecast.
- **220 of the 564 players in the 2026/27 game have no Premier League record.**
  Promoted-club regulars, arrivals from abroad, and anyone who played too little
  of 2025-26 to describe. They are listed with blank figures on purpose.
- **A player who changed club keeps his record.** The record follows the
  footballer, not the shirt. Nothing adjusts it for the side he has joined.
- **Assistant Manager has been removed for 2026/27.** The live bootstrap
  publishes four positions and no `element_type` 5 players. Any strategy note
  mentioning the chip is out of date.
- **Republish the projection artifact once the new season has some evidence.**
  `python -m fpl_andres.cli.publish_projections --season 2026-27`. Until then
  the page correctly shows the 2025-26 record, and says so.

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
- **Model promotion run.** The corpus has landed, but `evaluate_promotion` is
  currently reachable only from its own tests, so nothing promotes a model yet.
  Recorded in `LIMITATIONS.md` under "Built but not wired".

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
