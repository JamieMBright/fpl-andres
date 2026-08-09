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

Locally, on a network that permits it:

```bash
python -m fpl_andres.cli.survey_player_props --json catalogue.json
```

## Credentials

Every one is optional. A source with no key configured reports `no key` and
the run continues; "not signed up yet" is an answer, not a bug. Add these as
repository secrets to have a source probed.

| Secret                  | Source           | Cost                            |
| ----------------------- | ---------------- | ------------------------------- |
| `ODDS_API_KEY`          | The Odds API     | Free tier, 500 requests a month |
| `API_FOOTBALL_KEY`      | API-Football     | Free tier, 100 requests a day   |
| `SPORTMONKS_TOKEN`      | Sportmonks       | Odds need a paid plan           |
| `BETFAIR_APP_KEY`       | Betfair Exchange | Delayed application key is free |
| `BETFAIR_SESSION_TOKEN` | Betfair Exchange | Expires; refresh before a run   |

## The shortlist, and why each is on it

| Key                | What it is                                                    | Covers                           |
| ------------------ | ------------------------------------------------------------- | -------------------------------- |
| `the-odds-api`     | Aggregator over UK and EU books, markets named explicitly     | goal, assist, cards              |
| `api-football`     | Aggregator; its `/odds/bets` endpoint _is_ a market catalogue | goal, assist, cards, clean sheet |
| `sportmonks`       | Licensed feed with a published market taxonomy                | goal, assist, save, cards        |
| `betfair-exchange` | An exchange, not a book: two-sided prices, so the least vig   | goal, assist, clean sheet, cards |
| `football-data`    | The baseline already ingested. Match level only, no props     | clean sheet, goals conceded      |
| `understat`        | Not a market. Shot-level rates, the control on any prop       | goal, assist                     |
| `fpl-bootstrap`    | The scoring authority, and therefore the prediction target    | every scoring event              |

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
