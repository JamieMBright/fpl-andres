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

## Decisions taken (31 July 2026)

All confirmed by the owner in conversation. Recorded here so the reasoning
survives the chat.

- **Scraping**: `soccerdata` approved, rate limited and cached, pulling
  gradually. Understat and FBref only. **No WhoScored scraper** — against their
  terms, and non-commercial use does not cure that.
- **`fplcache`** (github.com/Randdalf/fplcache): approved. Six-hourly bootstrap
  snapshots give retroactive ownership and price history that `crowd_snapshots`
  can only collect going forward. Not yet built.
- **Anonymity**: stay anonymous for the first season.
- **Benchmarks**: compare against the FPL Review free model and the FPL Kiwi
  free model. Not yet built.
- **Mini-leagues that matter**: `34555` and `393774`. Rival picks are only
  legally readable after a deadline, so nothing can run before 21 August.
- **Bench boost**: play it when all fifteen have a reasonable expectation.
  Implemented: the chip is dated by the week the _weakest_ of the fifteen is
  worth most, not by fixture count, because a large double with two players
  blanking is worth less than an ordinary week where everybody plays.
- **Club limit**: four from one club is legal only when a player moves clubs
  mid-season, and the next transfer must correct it. Implemented in
  `transfer_respects_club_limit`. Not yet checked against the published rules
  text.
- **Licence**: all rights reserved, no permission granted. Already in `LICENSE`.
- **FPL100**: build from `docs/design/fpl.html`, and vet the 84 extracted entry
  ids for a track record worth following. Verification already run once and the
  list did **not** survive it — see the open item below.

---

## Your queue

Nothing mechanical is outstanding. What is left is judgement, and none of it can
be answered by me. Nothing here blocks the site running; each one blocks a
specific capability.

### The FPL100 cohort does not survive verification

- [ ] **Decide whether to ship it at all.** Of the 84 entry ids extracted from
      `fpl.html`, 78 were readable and 6 returned 404. Best confirmable finishes:
      3 inside the top 1,000, 19 between 1k and 10k, 19 between 10k and 100k, and
      **35 never better than 100,000**. Entry 3190, credited on the source page
      with winning FPL, has five seasons from 2021/22 and a best of 51,918.
      The list does not describe the cohort it claims to. Options: drop it, ship
      it with the verification attached, or replace it with a cohort built from
      the live top-100 once standings populate after gameweek 1.

### Building a real proven cohort, and why it takes seasons

- [ ] **Approve the season-end capture, or say no.** Scraping every manager is
      not on: FPL had 2,399,644 entries registered for 2026/27 before a ball was
      kicked and around eleven million by season end, so one request each is
      about four months of continuous polling. Nobody should do that.
- [ ] The cheap route is the Overall league, id 314, paginated fifty at a time.
      The top ten thousand is **200 requests**, and their histories another
      10,000 — roughly three hours at one a second, which is polite and
      practical.
- [ ] **The catch is that it cannot be done retroactively.** FPL keeps standings
      for the current season only, so there is no way to discover who finished
      top ten thousand in 2022/23. A cohort of managers with _several_ top-10k
      finishes therefore needs capturing at the end of each season from now on,
      and is two or three seasons away from meaning anything. That is precisely
      why a scraped Reddit list was being used instead, and it does not verify.

### Accept the mapping risk, or ask me to tighten it

- [ ] FPL, FBref and Understat use different player ids and there is no official
      crosswalk. The join is now settled by minutes and goals both sites measured
      independently rather than by name, and it maps 407 of the eligible 2025-26
      players against Understat, refuses two and mis-maps none that could be
      found. That is 94.9% coverage, measured rather than assumed. Say if you
      want the refused ones chased rather than left as gaps.

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
