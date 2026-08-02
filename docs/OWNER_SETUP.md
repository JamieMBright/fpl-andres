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

## Migration checklist

The production bootstrap is this list, pasted into the SQL Editor **in filename
order**. There is no CLI migration ledger for the hosted project, so this file is
the ledger.

The migrations are **not idempotent** — 17 `create table`, 26 `create index`,
10 `create trigger` and 6 `create function` statements are written without a
guard — so a file cannot be safely re-run after a partial paste. If one fails
part-way, follow the recovery procedure in `docs/RUNBOOK.md`; it uses
`supabase/rollback/down.sql` to return to empty before re-applying.

Mark each one applied, with the date, as it lands.

| #   | Migration                                          | Applied                        |
| --- | -------------------------------------------------- | ------------------------------ |
| 1   | `20260729180000_foundation.sql`                    | yes                            |
| 2   | `20260729183000_evidence_snapshots.sql`            | yes                            |
| 3   | `20260730120000_projection_artifacts.sql`          | yes                            |
| 4   | `20260731120000_optimization_artifacts.sql`        | yes                            |
| 5   | `20260731130000_foreign_key_indexes.sql`           | yes                            |
| 6   | `20260801120000_history_corpus.sql`                | yes — corpus loaded 2026-07-30 |
| 7   | `20260801130000_defensive_components.sql`          | **owner to confirm**           |
| 8   | `20260801140000_fixture_grain_and_event_range.sql` | **owner to confirm**           |
| 9   | `20260801150000_backtest_artifacts.sql`            | **owner to confirm**           |
| 10  | `20260801160000_crowd_snapshots.sql`               | **owner to confirm**           |
| 11  | `20260801170000_access_path_indexes.sql`           | no                             |
| 12  | `20260801180000_backtest_corpus_fingerprint.sql`   | no                             |
| 13  | `20260801190000_promotion_lineage.sql`             | no                             |
| 14  | `20260801200000_workflow_run_audit.sql`            | no                             |
| 15  | `20260802120000_snapshot_path_integrity.sql`       | no                             |

Rows 7–10 are marked for confirmation rather than guessed: this file did not
list them, so their state was never recorded and cannot be inferred from the
repository. Check the hosted project's `information_schema.tables` for
`crowd_snapshots` and `backtest_runs`, and `information_schema.columns` for
`element_gameweek_stats.clearances_blocks_interceptions`, then update this table.

`python/tests/test_migration_checklist.py` fails if a migration file exists that
this table does not name.

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

### Decide whether promoted-club debutants stay unavailable

- [ ] Your rule marks a promoted club's debutants `unavailable`, and the model
      obeys it. Measured across six promotion cohorts, that may be stricter than
      it needs to be: promoted-club players who appeared at all took a median
      1121 minutes against 1316 for everyone else, p90 2795 against 2916, and
      an identical median of 3 starts. A promoted squad is modestly compressed,
      not unpredictable.
- [ ] If you want them ranked at reduced evidence instead of hidden, say so and
      the measured prior above can be wired. Nothing has been changed on the
      strength of this measurement, because the rule is yours.

---

### Verify the yellow card accumulation rule

- [ ] **I could not source the thresholds, so nothing assumes them.** The
      suspension model is built and tested, but `SuspensionRules` has no default
      and refuses to construct without a `source_reference`. That is deliberate:
      the standing rule here is that a controlling rule which cannot be sourced
      fails visibly rather than being guessed, and these thresholds have changed
      before.
- [ ] What is needed is the ladder from the published handbook: how many
      cautions trigger a ban, how long each ban lasts, and **the gameweek at
      which the lower rungs are wiped**. The reset is the part that matters most
      to a projection, because a player four cards deep in November is a very
      different proposition from the same player in March.

---

### The FPL100 cohort does not survive verification

- [ ] **Decide whether to ship it at all.** Of the 84 entry ids extracted from
      `fpl.html`, 78 were readable and 6 returned 404. Best confirmable finishes:
      3 inside the top 1,000, 19 between 1k and 10k, 19 between 10k and 100k, and
      **35 never better than 100,000**. Entry 3190, credited on the source page
      with winning FPL, has five seasons from 2021/22 and a best of 51,918.
      The list does not describe the cohort it claims to. Options: drop it, ship
      it with the verification attached, or replace it with a cohort built from
      the live top-100 once standings populate after gameweek 1.

### Building a real proven cohort

- [ ] **Decide whether a full entry sweep is acceptable load.** I first said this
      was impossible and I was wrong, so here are measured numbers rather than a
      guess. Entry ids currently top out around **2,400,000** (2,400,000 exists,
      2,500,000 does not) and a history call takes **24ms**. A serial sweep is
      therefore about **16 hours**, not the four months I claimed. The ceiling
      will rise as more teams register before the deadline.
- [ ] **A sweep does solve the retroactive problem.** Each
      `/entry/{id}/history/` returns every completed season for that manager, so
      one pass reconstructs who has finished top ten thousand repeatedly, going
      back years. The Overall league only ever shows the current season, which is
      what led me to say it could not be done.
- [ ] **But 2.4 million requests is real load on somebody else's service**, with
      no published rate limit to point at. That is a judgement call and it is
      yours, not mine. If the answer is yes it should be throttled well below
      what the server tolerates, resumable, and cached so it never repeats.
- [ ] **The cheap version needs no sweep at all.** The Overall league, id 314,
      paginates fifty at a time, so the current top ten thousand is **200
      requests**. That gives this season's elite immediately; it just cannot tell
      you who was elite in 2022/23.
- [ ] **Select on recent seasons, not on a career.** Entry 1 is the case that
      settles it: 43% and 93% in his first two seasons, then top 4% from
      2018/19, then five straight seasons at or inside the top 1% including
      **19th in the world** in 2023/24. A career median would rate him on years
      that no longer describe him, and the same filter would keep somebody whose
      good seasons ended in 2016. Whoever is worth following is worth following
      on the last three or four seasons.

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
