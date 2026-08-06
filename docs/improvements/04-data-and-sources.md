# Data, sources and the bookmaker question

Audit D. Where the evidence comes from, what is missing, and the one blocked
source that has a route forward nobody has taken.

Scores are on the scale in [`IMPROVEMENTS.md`](../../IMPROVEMENTS.md).

---

## D1. Bookmaker odds: blocked locally, reachable from CI

**Score 9. Do.**

This deserves its own section because the repository has recorded it as blocked
and the recording is only half true.

### What exists

`python/fpl_andres/models/odds.py` is complete: `implied_probabilities`,
`overround`, and three de-vigging methods — proportional (the biased baseline,
kept to argue against), power, and Shin. Both bisections were checked during
this audit and are correct. There is also a documented join from an
odds-derived goal expectation to the FPL scoring model.

Every function is in `KNOWN_ORPHANS`. Nothing fetches a price.

### What is actually blocked

Re-measured during this audit, 2026-08-06, from this machine:

```
FAIL  https://www.football-data.co.uk/englandm.php   ConnectError 10054
FAIL  https://api.the-odds-api.com/v4/sports         ConnectError 10054
FAIL  https://www.oddsportal.com/robots.txt          ConnectError 10054
200   https://fantasy.premierleague.com/api/bootstrap-static/
```

All three price hosts die at the TLS handshake while the control returns 200.
This is a **content filter on the local network**, not a property of the hosts.
The finding is stable — it matches the 2026-08-01 measurement exactly.

### The part that was never followed up

The backtest has exactly the same shape of problem and it was solved months ago.
`validate` needs the Supabase corpus, cannot run on this machine, and therefore
runs in `.github/workflows/validate-model.yml` on a GitHub-hosted Linux runner.

**GitHub's runners are not behind this content filter.** The blocker is
"cannot be developed interactively from the owner's desk", not "cannot be done".
The repository already has the pattern for exactly that situation and did not
apply it here.

### What is worth having, and what is not

Ordered by value, and the ordering matters because the two halves have very
different licensing profiles.

**Historical closing odds, for the backtest — worth doing.**
`football-data.co.uk` publishes free CSVs of English league results including
closing prices from several books, going back decades. That is enough to:

- Build a bookmaker-implied clean-sheet and goals-scored prior per fixture.
- Compare it against `estimate_strength` and against Dixon-Coles on the same
  gameweeks — a genuine external check on the team-strength model, which is
  currently checked against nothing.
- Answer the standing question in [B5](02-model-correctness.md#b5-estimate_strength-charges-a-club-for-its-fixture-draw)
  about how much the opponent-unadjusted strength model costs.

The user's instinct is right and worth stating precisely: a closing price is the
aggregate of everyone who was willing to stake money, marked to market by people
whose livelihood depends on being calibrated. As a **prior on team-level goal
distribution** it is very likely better than anything fittable from 380 matches
a season. The de-vig code in the repo exists because the raw prices are not
probabilities — the overround has to come out first, and Shin's method is the
right tool because it models the favourite-longshot bias rather than assuming it
away.

**Live pre-deadline odds, for the projection — do not start here.**
A live feed means a commercial API and a key. It also means a recurring cost and
a dependency that can be withdrawn. Do the historical backtest question first;
it is free, it is one CSV per season, and it answers whether the live feed would
be worth paying for. If bookmaker priors do not beat Dixon-Coles on four seasons
of history, there is nothing to buy.

**Player-level markets — probably not available at a price worth paying.**
Anytime-scorer and hat-trick prices are what would most directly improve a
captaincy pick, and they are the least freely available. Park this until the
team-level question is settled.

### Constraints that must hold

- Check and honour `robots.txt` and terms for any host before fetching. The repo
  already refused FPL Review on exactly this basis and that precedent governs.
- Odds are _evidence_, so they get an `EvidenceLevel` and a source timestamp
  like everything else, and a missing price must fail closed rather than default.
- Never present a price as a probability without de-vigging; `OddsUnavailable`
  already refuses a book that does not sum above 1.0, which is an arbitrage or a
  corrupt row rather than a market.
- This is a modelling input. Nothing in the project should ever emit a betting
  recommendation, and the site should not link to a bookmaker.

**Handoff.** Add `python/fpl_andres/adapters/football_data.py` with a parser for
the CSV shape and a pinned-URL fetch, mirroring the vaastav adapter's structure.
Add `cli/ingest_odds.py`. Run it from a new workflow, because it cannot run
locally. Store to a new `fixture_odds` table. Then a comparison in the backtest
against `estimate_strength` and `DixonColesModel`.

---

## D2. The live contract test does not check the field the site depends on

**Score 8. Do.**

`.github/workflows/live-contracts.yml` runs `cli/live_contracts.py`, twelve
lines that fetch `bootstrap-static` and call
`validate_published_bootstrap_contract`.

That function checks `game_settings` against `game_config.rules`, the 35 scoring
fields, `element_types` formation bounds, and chip windows. All valuable.

It does **not** check `elements` — the array carrying `web_name`, `now_cost`,
`element_type`, `team` and `status`, every one of which the site consumes on
every dossier. It does not check `teams`, `events`, or any of the six other
endpoints the proxy allows.

The failure this permits: FPL renames a field on `elements`. The daily contract
job passes green because it does not look there. The TypeScript boundary in
`api/_lib/team-public-state-response.ts` rejects the shape, and every visitor
gets `degraded`. And the canary explicitly does not alert on `degraded`:

> "A degraded response is FPL being unreachable, which is worth knowing but is
> not this deployment failing. Reported, not alarmed."

That reasoning is right for an FPL outage and wrong for a schema change, and the
canary cannot tell the two apart. The result is a site-wide outage with no page.

**Fix.** Extend the contract check to the `elements`, `teams` and `events`
shapes the site actually reads, and make a contract failure distinguishable from
an upstream outage so the canary can alarm on one and not the other.

---

## D3. No backup, and one table is not re-ingestible

**Score 8. Do.**

There is no backup automation anywhere in `.github/workflows/`, and no
documented restore procedure. `docs/RUNBOOK.md` tells the operator to "take a
backup before step 2" without saying how or where.

For most tables this is survivable: the corpus can be re-ingested from the
pinned vaastav archive, which is the whole point of pinning it.

`crowd_snapshots` cannot. It is captured three times a week from a live endpoint
that publishes only the current state. Nothing archives historical ownership.
**Every row lost is lost permanently**, and the series is the input to the
crowd, template and effective-ownership work.

One bad migration or one mistaken `truncate` ends that series.

**Fix.** A scheduled `pg_dump` of the small, non-reconstructible tables to a
retained artifact. `crowd_snapshots` first. The corpus tables can be excluded
precisely because they _are_ reconstructible, which keeps the dump small.

---

## D4. Ownership is captured to a gitignored file

**Score 6. Do.**

`cli/ingest_ownership.py` writes JSONL to `data/ownership/`, which is
gitignored. `element_price_observations` exists in the schema with no writer.
`docs/ROADMAP.md` confirms: "Not yet loaded into Supabase or joined to a
projection."

So a capture job runs, produces data, and the data lives only on whichever
machine ran it. This is the price series that
[A12](01-methodology.md#a12-team-value-is-not-modelled-and-it-compounds) needs.

**Fix.** Point the writer at the table that already exists for it.

---

## D5. The corpus is mutable and nothing detects an unintended change

**Score 5. Do.**

Re-ingesting overwrites; `docs/RUNBOOK.md` documents this. `SeasonCorpus` has a
`fingerprint` property and `validate` publishes it per season, which is a good
design and exactly the right primitive.

Nothing compares fingerprints between runs. `compare_validation` reports moved
metrics but does not assert that a metric moved _because the model changed_
rather than because the corpus did. A re-ingest that silently altered history
would present as a model improvement or regression.

**Fix.** `track_model` already stores a history row per run. Store the corpus
fingerprint beside the model version and fail the comparison when both moved at
once without being told to expect it.

---

## D6. Season vintage handling is good and worth protecting

**Score 1. Don't change — recorded as a strength.**

Between seasons, `bootstrap-static` still carries last season's totals while
`finished` events read zero. `state/season-vintage.ts` derives which season the
totals describe, flips automatically at GW1, and refuses in the
wiped-but-unscored window.

This is a subtle trap handled correctly, with a refusal rather than a guess.
Noted here so a future change does not "simplify" it away.
