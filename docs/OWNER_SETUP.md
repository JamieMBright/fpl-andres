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

## Decisions waiting on you (added 31 July 2026)

Nothing below blocks the site running. Each one blocks a specific capability,
and none of them can be answered by me.

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

- [ ] **Decide whether to benchmark against published projections.** FPL Review's
      free model and FPL Kiwi both publish. Comparing against them would be the
      strongest possible validation, and it may not flatter us.

### Mini-league

- [ ] **Supply the mini-league id you actually care about.** Rival ownership is
      built and tested but has nothing to point at. Individual rival picks are
      only legal to read after a deadline, so this cannot run before 21 August.

### Chips

- [ ] **Confirm the bench boost rule.** You specified triple captain, free hit
      and wildcard. Bench boost currently takes the second-largest double
      gameweek by inference, not by instruction.

### Season start

- [ ] **2026/27 gameweek 1 deadline is 21 August 2026, 17:30 UTC.** Until a
      gameweek is played, transfer advice is projected from last season's record
      for returning players only. Promoted-club debutants and new arrivals get
      no projection at all, by design.

---

Everything else — SQL authoring, migration ordering, RLS, CI, tests, runtime
code, deployment configuration, monitoring, backups, release mechanics —
remains implementation work owned by the agent.
