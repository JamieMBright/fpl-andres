# Player markets: which sources exist, and what each returns

`football-data.co.uk` prices matches. FPL scores players, and most of what it
pays for — a goal, an assist, a save, a card, a defensive contribution — is
priced somewhere as a player prop. This document is the shortlist and the
method for comparing it. It decides nothing: choosing a source needs the actual
column lists side by side, and those come from a run, not from memory.

Nothing here emits or implies a betting recommendation. A price is read as a
probability and used as evidence about a footballer.

## The answer

`docs/PLAYER_MARKET_CATALOGUE.md` is generated: which source prices which
scoring route, what each one answered, and whether anything at all can price a
player's chance to score. It is refreshed every Monday and on any manual run,
and committed, so a key that expired or a market that opened shows up as a
diff. Do not edit it by hand.

## Running the survey

The owner's network fails at the TLS handshake for every price host behind a
gambling-category filter, so this runs on a GitHub runner and nowhere else.

**Actions → Survey Player Markets → Run workflow.**

Leave both inputs blank to catalogue every source. The run uploads
`player-props-catalogue.json`, which carries every field name each source
returned, as a build artifact — never committed, because half of it changes
whenever a book opens or closes a market.

**Reading The Odds API's entry.** It answered far more thinly than the sources
beside it, and that was the probe's fault rather than the source's. Player props
open days before kickoff, and the probe asked about whichever fixture the host
happened to list first — often one in December, which has none. It now asks
about the soonest fixture, and its note names the tie, how many books answered,
how many outcomes they carried, which of the asked-for markets did not arrive
and what the request cost. That is what separates a shut market from a wrong
request, and neither can be told from an empty `markets` list.

Every probe reports what its host says is left of the day's or month's
allowance. None of these hosts warns before an allowance runs out — the request
that crosses the line simply fails, and a failed request looks exactly like a
market nobody has opened.

Locally, on a network that permits it:

```bash
python -m fpl_andres.cli.survey_player_props --json catalogue.json
```

## Credentials

Every one is optional. A source with no key configured reports `no key` and
the run continues; "not signed up yet" is an answer, not a bug. Add these as
secrets to have a source probed. A **variable** of the same name does not
count: `secrets` and `vars` are separate namespaces, and only a secret is
masked in the log.

| Secret                  | Source           | Cost                            |
| ----------------------- | ---------------- | ------------------------------- |
| `THE_ODDS_API_KEY`      | The Odds API     | Free tier, 500 requests a month |
| `API_FOOTBALL_API_KEY`  | API-Football     | Free tier, 100 requests a day   |
| `BETFAIR_APP_KEY`       | Betfair Exchange | Delayed application key is free |
| `BETFAIR_SESSION_TOKEN` | Betfair Exchange | Expires; refresh before a run   |

### Getting `THE_ODDS_API_KEY`, and where it goes

This is the one the ingest actually needs. Without it **Ingest Player Odds**
fails on its first step and says so, rather than committing an empty artifact.

1. Go to <https://the-odds-api.com> and click **Get API key**.
2. Enter an email. The free tier is 500 requests a month and needs no card.
   The key arrives by email and is shown on the dashboard.
3. In this repository: **Settings → Environments → production → Environment
   secrets → Add environment secret**. A repository secret under **Settings →
   Secrets and variables → Actions** works as well. What does not work is the
   **Variables** tab beside it, or the **Environment variables** box below —
   `${{ secrets.X }}` cannot see either, and the run fails saying the key is
   not set.
4. Name it exactly `THE_ODDS_API_KEY`. Paste the key as the value. Save.
5. **Actions → Ingest Player Odds → Run workflow** to confirm. A good run
   prints how many fixtures were priced, how many players were quoted and how
   many joined onto an FPL element, then commits
   `apps/web/src/data/player-odds.json`.

Never put the key in a file. Nothing here reads it from anywhere but the
environment, and a key in a commit is a key that has to be rotated.

**The budget.** This repository used to claim one request per fixture. Nobody
had measured it, and it is very likely wrong: the host charges per market per
region. So the dial is written in the unit that actually bills. `budget` is how
many requests a run may spend against the free tier's 500 a month, fixtures are
priced soonest first so a small budget still buys the ones being played, and the
run prints what each request cost and what the key has left. Set the default
from that log.

Three things keep the spend inside the tier, and
`python/tests/test_api_budgets.py` holds all three to the allowance so a raised
cron has to be argued for rather than merged.

- **Eight markets.** Anytime, first and last scorer, assists, to be shown a
  card, to be shown a red, shots and shots on target are all retained. First
  and last scorer overlap anytime scorer, so they corroborate availability but
  are not added as extra goals. Shot counts inform participation and the
  official BPS shot terms when total shots and SOT are paired; an unpaired SOT
  line remains visible but cannot supply a defensible historical BPS delta.
  The host bills only for a market it returns, so a shut market costs nothing.
- **One region.** UK books price a Premier League player deepest, and adding
  Europe doubles the bill for a slightly steadier median.
- **Daily trigger, seven-day gate, eight-credit hard cap.** No provider
  publishes an exact opening hour, so the workflow wakes at 09:00 UTC every
  day. It reads the committed FPL calendar first and exits before reading the
  provider key unless the next deadline is within seven days. Uncovered
  fixtures are visited before an existing quote is refreshed, and still-current
  older rows retain their own observation timestamp. That lets several bounded
  runs cover a gameweek instead of buying the same first fixtures every day.
  Before another fixture is fetched, the run reserves all eight possible market
  credits, so a response cannot overshoot the cap. `test_api_budgets.py` keeps
  the worst-case shared allowance under 500.

The same key pays for the weekly survey, which is why the guard counts both.
It also pays for the team-market fallback when football-data.co.uk has not
opened the current round. That fallback asks for `h2h`, `totals` and
`alternate_totals` on at most ten uncovered fixtures inside the nearest six
days; the live provider also returns and bills `h2h_lay` beside `h2h`, for a
forty-credit worst-case round. Retained fixture rows prevent a daily repeat,
and each Odds API row carries the team-analysis version that consumed it. A
parser/model upgrade refreshes legacy rows once; a market genuinely absent on
that refresh is then retained as absent rather than bought again every day.
`test_api_budgets.py` includes the weekly bound in the shared 500-credit total.

**When nothing is quoted.** Ten fixtures priced and nought players quoted is not
a failure. Each fixture's line names how many books answered, how many outcomes
they carried, which market keys arrived and which of the asked-for keys did not,
which is what separates "the market is shut" from "the keys are wrong". A run
that quotes nobody anywhere exits clean and says the markets are not open; a run
that quotes players but joins none of them to an FPL element fails, because that
one is the crosswalk's fault and wants fixing.

**What the numbers then do.** `docs/MODEL.md` §7b. Anytime prices become event
rates; count lines become expected counts. The fixture is divided back out,
then the matching historical route is blended at `--market-weight`. Goals,
assists, cards, participation, shots and BPS each consume only the evidence
that names them. First/last scorer are overlapping corroboration, not extra
goals. The team markets jointly price one distribution for clean sheets, goals
conceded, save pressure and defensive-action pressure.

## The shortlist, and why each is on it

| Key                | What it is                                                     | Covers                           |
| ------------------ | -------------------------------------------------------------- | -------------------------------- |
| `the-odds-api`     | Aggregator over UK books, markets named explicitly             | goal, assist, cards, shots       |
| `api-football`     | Aggregator; `/odds/bets` is a catalogue, not proof of an offer | goal, assist, cards, clean sheet |
| `betfair-exchange` | An exchange, not a book: two-sided prices, so the least vig    | goal, assist, clean sheet, cards |
| `football-data`    | The baseline already ingested. Match level only, no props      | clean sheet, goals conceded      |
| `understat`        | Not a market. Shot-level rates, the control on any prop        | goal, assist                     |
| `fpl-bootstrap`    | The scoring authority, and therefore the prediction target     | every scoring event              |

The exchange is listed last among the price sources but is first on merit:
its implied probabilities need no de-vigging assumption, because the price is
what someone actually laid rather than what a book offered.

## What the survey cannot tell you

- **Whether a market is liquid.** A quoted price on a thin market is a number,
  not a probability. Depth has to be read separately, and only the exchange
  publishes it honestly.
- **Whether a prop is available at the FPL deadline.** The deadline falls 90
  minutes before the first kickoff. Player markets often open later than match
  markets, and a prop that only exists at kickoff carries team news no manager
  could have had — the same leak the closing-price refusal in
  `adapters/football_data.py` already guards against.
- **Whether coverage extends to promoted clubs and new signings.** This is the
  case that matters most: a keeper who was second choice elsewhere and is now
  first choice here has no useful record, and the market is the only source
  that has already priced the change. Coverage there has to be checked club by
  club, not assumed from a headline market count.

## Field availability audit, 18 August 2026

Three evidence levels must not be collapsed into one:

| Provider            | Documented or catalogued                                                                                                                                                                                                                                                       | Observed on a live 2026/27 fixture                                                                                                                               | Safe model use now                                                                                                                                                                                    |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The Odds API        | Event odds accept explicit player keys for anytime, first and last goal, assists, cards, red cards, shots and shots on target. Responses carry bookmaker, market key, player description, price and count-line point. Team keys include 1X2, lay, totals and alternate totals. | Arsenal–Coventry named all five open player markets and all four team markets. Player shots, cards and red cards remained absent three days before kickoff.      | Anytime goals and assists move routes. First/last scorer corroborate the overlapping goal event. Unpaired SOT stays observed until total shots opens. All four team views feed one goal distribution. |
| API-Football        | `/odds/bets` listed 332 bet types, including anytime scorer, player assists, cards, shots, shots on target, tackles, goalkeeper saves, own goal and penalty miss. `/fixtures` and `/odds?fixture=` must still prove an actual offer with player-named selections.              | The catalogue answered with 96 daily requests left, but no 2026/27 Premier League fixture was available to probe. No player selection payload has been observed. | None yet. Catalogue names are capability hints, not evidence. A tackles line is not direct DefCon: it omits clearances, blocks, interceptions and, outside defence, recoveries.                       |
| football-data.co.uk | Season CSVs publish match-level result, 1X2, totals and Asian-handicap columns from multiple books.                                                                                                                                                                            | Four completed seasons are ingested. The current-season file is unavailable before matches are played, so The Odds API supplies the team-market fallback.        | Team xG, clean-sheet and conceding routes only. It has no player props or lineups.                                                                                                                    |

The provider pages cannot be opened from the owner's network: The Odds API is
reset by the gambling-category filter and API-Football returns a Cloudflare 403.
The tracked catalogue therefore comes from the documented endpoints on a GitHub
runner and records actual market names and response fields rather than relying
on website copy.

### What still needs one capture

No credential should be pasted into chat or committed. The existing
`API_FOOTBALL_API_KEY` is enough. Once API-Football lists a 2026/27 Premier
League fixture, run **Survey Player Markets** once while props are open. The
probe already records the fixture id, bookmaker count, each player-level bet,
selection count and one verbatim selection. That one runner result decides
whether its catalogue is crosswalkable evidence or only a taxonomy. If it
still says `no Premier League fixture scheduled`, the provider cannot help this
GW1 and nothing should be inferred from its 332-name catalogue.

## Reading a catalogue

Each entry carries `status`, `note`, `markets` and `fields`.

- `status: ok` with an empty `markets` means the source answered but names no
  market identifiers — its taxonomy has to be read from `fields` instead.
- `status: refused` with an HTTP status is a live credential problem or a rate
  limit, and is the one outcome worth acting on immediately.
- `status: no_credential` is a sign-up away.
- `status: unreachable` from a runner means the host is genuinely down or
  blocking GitHub's egress; from a laptop it usually means the filter.

Compare `fields` across sources before choosing. Two providers that both claim
"anytime goalscorer" can differ on whether they key players by name only, which
decides whether a crosswalk onto FPL element ids is possible at all.
