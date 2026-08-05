# Evidence and Capability Limits

These limits are product behavior. A missing source disables or downgrades a feature;
it never licenses a plausible estimate.

## Quick reference

What each limit costs you, so a missing feature can be told from a bug.

| Limit                       | What it disables or downgrades                                                                                              |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Public team state           | No live draft. Bank, free transfers and chips are as of the last deadline.                                                  |
| Matchups                    | Five scoring routes, each bent separately by a fixture. No flank or set-piece splitting — [tested and refused](ROADMAP.md). |
| Out of position             | No fixed OOP bonus. An attacking defender is flagged, not repriced.                                                         |
| Defensive contributions     | Nothing before 2025/26: the route did not exist, so the column is absent rather than zero.                                  |
| Historical data             | Backtests span 2019-20 onward; expected values exist only from 2022-23.                                                     |
| Historical manager state    | No past bank or chip state, so a replayed season cannot honour real budgets.                                                |
| Injuries                    | Availability comes from FPL's own flags. No scraped team news.                                                              |
| Prices                      | No live price-change prediction. Ownership history only from the archive.                                                   |
| Squad numbers               | FPL publishes the field and leaves it empty for all 567 players, so every shirt is blank.                                   |
| Season start and cold start | Promoted-club debutants are `unavailable`, not estimated.                                                                   |
| Rivals and consensus        | Individual rival picks are post-deadline only. Aggregate ownership is legal earlier.                                        |
| Planning horizon            | Seven gameweeks by default. Longer works but no surface asks for it.                                                        |
| Team goal projections       | Dixon-Coles, fitted on the completed season. A single home advantage shared by every club.                                  |
| Execution                   | No automated transfers. Every recommendation is advisory.                                                                   |
| Suspensions                 | Accumulation bans are priced. A disciplinary hearing at twenty yellows is a judgement, so it is not modelled.               |
| Bookmaker odds              | De-vigging is built; no price source is reachable from the build network.                                                   |
| Rate limiting               | The public proxies are unmetered per client.                                                                                |

Each is expanded below.

## Public team state

An FPL Team ID exposes the last processed deadline, not a manager's private current
draft. Bank, available free transfers, pending moves, chips and selling prices can be
stale before the next deadline. Recommendations must show `state_as_of` and apply
explicit manager corrections separately.

## Matchups

The approved public sources do not establish exact flank assignments, natural foot,
sprint speed, tracking runs, touch heatmaps, individual marking, aerial weakness or
high-line exposure. FPL Andres may use team, position and role evidence with a label;
it may not claim a specific player-v-player matchup without licensed event data.
Heatmap-derived role inference is accepted only from rights-cleared data with model
version, confidence, sample size and timestamps. Screenshots and unlicensed heat maps
are not scraped.

## Out of position

The Lord Lundstram effect identifies an officially listed defender with evidence of a
midfield/attacking deployment. The official FPL position retains defender goal and
clean-sheet scoring; the observed role is a separate attacking-potential signal.
Reverse-OOP is also recorded. No role is inferred from listed position alone, and OOP
does not receive an arbitrary points bonus that would double-count attacking features.

Live OOP evidence must be recency-weighted. Tactics change between gameweeks, so a
player deployed OOP last week may revert this week. The deployment classifier
therefore treats role evidence as a sequence of per-event observations with an
exponential recency decay, not a fixed-window average. The last few played gameweeks
dominate the weighted starts count. If the most recent contiguous run of role
observations disagrees with the prior window (for example, three consecutive
in-position starts after a spell of attacking-OOP starts), the classifier emits
`unavailable` rather than the older classification. The exact decay half-life and
regime-change threshold are sourced parameters, not agent defaults. Historical
open-data corpora used only to validate the classifier are exempt because they cover
completed seasons rather than the live sequence.

## Defensive contributions

Observed defensive-contribution labels begin in 2025/26. Older public archives do not
contain the underlying defensive actions required to reconstruct those labels.
DefCon models therefore use observed 2025/26+ data and expose small-sample limits.

## Historical data

Historical archive revisions are pinned. Same-gameweek `xP`, post-match snapshots and
any feature whose availability timestamp is after the decision cutoff are rejected by
the walk-forward runner.

FPL Andres does not crawl Understat directly.

## Historical manager state

FPL does not retain manager state across a season rollover. Verified against the
live API: `entry/{id}/event/{gw}/picks/` returns 404 for every gameweek of a
completed season, and `leagues-classic/314/standings/` serves only the current
season, returning zero results in preseason.

Two consequences, both permanent for seasons already gone:

- A manager's own gameweek-by-gameweek squad history cannot be replayed. Only
  the season summary in `entry/{id}/history/` survives, which carries
  `season_name`, `total_points` and `rank` per past season.
- The final top-100 finishers of a completed season cannot be reconstructed.
  There is no endpoint that enumerates them, and 11 million entry ids cannot be
  swept to find them.

Neither limit affects player-level backtesting, which depends only on the
per-gameweek player corpus and is unimpaired. What is lost is replaying a
specific manager's past decisions and reconstructing historical rival cohorts.

Both become available prospectively by snapshotting them while a season is live.
Squad snapshots and the end-of-season top-100 are therefore captured from
2026/27 onward, and any cohort or personal-replay feature that depends on an
earlier season renders `unavailable` rather than substituting a proxy.

## Injuries

The primary evidence is FPL's status, chance of playing, news timestamp and official
club source link. The product does not scrape Premier Injuries or republish third-party
injury lists.

## Prices

FPL does not publish the exact price-change mechanism. Outputs are calibrated movement
probabilities backed by timestamped transfer and price observations. Exact thresholds,
reset rules and protection claims are excluded.

## Squad numbers

FPL's bootstrap carries a `squad_number` field on every element and leaves it null.
Measured 2026-08-05: 0 of 570 players have one. The field is read and published where
it exists, so a shirt prints the number the day FPL starts filling it in; until then
every shirt is blank and the player card says so in words rather than leaving a reader
to guess. No other approved source publishes squad numbers, and putting a number on a
shirt that the source does not give would be inventing one.

## Season start and cold start

Before a ball is kicked there is no current-season evidence. Gameweek 1 projections
therefore carry forward the previous season's observed per-90 rates, minutes and
start patterns rather than speculating on the new season. Carry-forward is evidence,
not prophecy, and it is labelled as such: every gameweek 1 projection is emitted at a
reduced `EvidenceLevel` that names the source season.

Carry-forward is only valid where a comparable prior observation exists. It is
unavailable, not estimated, for:

- players at promoted clubs with no Premier League minutes,
- signings arriving from outside the Premier League,
- debutants and academy promotions,
- any player whose prior-season minutes fall below the declared sample floor.

A player who changed club retains their own per-90 rates but inherits the new club's
team-level context. Team strength is never carried forward for a promoted side; that
side's baseline comes from the league-level prior until observed fixtures exist.

Current-season observations replace carried-forward priors progressively as fixtures
accumulate. The blend weight is a sourced model parameter, not an agent default. By
the point the declared sample floor is met, the prior no longer contributes.

## Rivals and consensus

Three distinct things, deliberately never merged.

**FPL100** is what the top 100 ranked teams actually did: revealed ownership,
captaincy and transfers within that cohort. Individual rival picks are used only
after a deadline. Banked free transfers and pre-deadline intentions are not
public. FPL100 is a contextual view and does not alter player projections in v1.

**Groupthink** is what people are saying: prevailing community and pundit
opinion. It is a sentiment reading derived from sources that permit automated
access, stored as aggregate signals rather than republished text. FPL Andres
does not scrape sites whose terms prohibit it, and never reproduces paywalled
content. Groupthink does not alter player projections in v1.

**Aggregate crowd signal** is a third source with a different availability
window. Ownership share and event transfer counts are published in the public
bootstrap before the deadline and may be used pre-deadline, including for
gameweek 1, where carried-forward projections are at their weakest. It is
presented as revealed crowd behaviour with its own timestamp. It never silently
modifies a projection, and it is never described as an individual manager's
pick.

Where the product compares its own projection against any of the three, the
comparison must carry a measured historical hit rate on past disagreements. An
unmeasured claim to know better than the field is not shipped.

## Planning horizon

The product returns a next-deadline action and a full 1–38 gameweek plan: squad,
starting eleven, captain, vice-captain, bench order, transfers and chip windows
for every remaining gameweek of the season.

The plan is a projection, not a prediction, and the further out it reaches the
less it is worth. Confidence is therefore attached to every gameweek rather than
implied by the fact that a row exists, and the basis for the decline is stated
where a reader can check it. A plan that presents gameweek 34 with the same
authority as gameweek 2 is lying about what it knows.

Current solvers support expected value only and require `chip_scenario=none`.
Protect/chase utilities remain unavailable until calibrated outcome distributions
exist. Chip optimization remains unavailable until authoritative multiplier, bench and
transfer behavior is sourced, so chip placement is presented as a fixture-derived
window rather than a solved decision. Rolling plans use provided event prices and
conservatively forbid reselling players acquired inside the horizon.

## Team goal projections

Club strength comes from a Dixon-Coles fit on the completed season, which
separates attack, defence and home advantage rather than charging a side for the
fixtures it happened to draw. It fits a single home advantage shared by every
club, so a club's home and away multipliers come out equal: it says clubs differ
in how good they are, not in how much a home crowd is worth.

It does not include player availability, likely lineups, tactical events,
bookmaker markets or licensed event data. A successful numerical fit does not
make a candidate production-ready. Candidates remain `experimental` until a
chronological, leakage-controlled paired evaluation clears the declared sample
floor and confidence gate.

## Execution

FPL Andres never logs into an FPL account and never executes transfers or chips.

## Built but not wired

Found by `python/tests/test_reachability.py`, which fails the build on any new
orphan. These are capabilities the codebase has and does not use. Recorded
rather than hidden, because a reader is entitled to know the difference between
what exists and what runs.

| Orphan                     | State                                                                  |
| -------------------------- | ---------------------------------------------------------------------- |
| `project_expected_points`  | The promoted xPTS model. The backtest projector prices scoring itself. |
| `HighsHorizonOptimizer`    | MILP planner with free-transfer carry. A greedy planner runs instead.  |
| `classify_deployment`      | Out-of-position classifier. No live data source.                       |
| `evaluate_promotion`       | Promotion gate. Nothing promotes a model yet.                          |
| `iter_walk_forward_slices` | Leak-guard slicing. The corpus enforces the cutoff structurally.       |
| `simulate_season`          | Single-manager simulation, superseded by the mini-league.              |
| StatsBomb adapter          | Parsers exist; no ingest path.                                         |

## Not modelled at all

- **Starts are a better marker than minutes, and the model still uses minutes.**
  Measured across six season pairs against next season's opening starts: season
  minutes score 0.616 on rank correlation, season starts 0.620, and a rank blend
  of season starts with closing-six starts 0.646, winning five of the six pairs.
  The minutes model is decay weighted, which captures part of this, but it does
  not count starts separately from minutes. Wiring the blend in is outstanding.
- **Why a player is playing.** The model knows a defender started six of the
  last six. It does not know he started because the first choice was injured,
  so it cannot tell you the minutes will evaporate the moment that man is fit.
  Every appearance is treated as evidence of a role, which over-reads a
  stand-in and under-reads a returning starter.
- **Promoted clubs have no measurement at all.** Three of the twenty come up
  every year and their players carry no Premier League record, so they cannot
  be ranked or picked. Championship minutes exist on FBref but neither
  `soccerdata` nor Understat ships that competition, and scoring rates do not
  transfer across the divisions in any case. Minutes might: for bench cover,
  where the only question is whether a man will be on the pitch, Championship
  appearances would be the right signal and are not currently read.
- **Positional matchups.** Team strength is one attack and one defence figure
  per side. A right-sided forward against a weak left side is a real effect with
  no representation here, and no free source publishes flank splits directly.
- **Squad restructuring.** Transfers are like-for-like by position. A real
  manager can change shape; this cannot.
- **Price change prediction.** Team value moves with observed prices, but
  nothing forecasts a rise or fall, so no value is farmed deliberately.
- **Posterior updating.** Models refit on decayed history each week rather than
  carrying a posterior forward.

## Simulation caveats

- Play begins at gameweek 7, so totals cover 31 or 32 weeks of 38 and are not
  season totals.
- Double gameweeks are confirmed in-season as cup runs resolve. Chip timing
  reads the final fixture list, so it has more notice than a real manager.
- The crowd baseline reads published net transfers, which are a lagging signal:
  the crowd buys after the points have been scored.

## Between seasons

FPL resets every squad when a season ends. From the reset until the first
deadline, `/entry/{id}/` returns `current_event: null` and `/entry/{id}/picks/`
does not exist, so there is no team to analyse for anybody. Verified live on
31 July 2026.

What survives the reset, and is therefore what the site reads in the off-season:

- `/entry/{id}/history/` keeps completed seasons, so a manager's record is real.
- `bootstrap-static` already carries the new season's players, clubs, prices and
  deadlines.

The Players page joins those published prices to last season's measured record.
Both halves are facts; neither is a forecast for a match nobody has played.

A player who moved club in the summer keeps his record here, because the record
follows the footballer. Nothing adjusts it for the side he has joined.

The opening-run rating uses last season's measured club strength, joined on the
permanent club code. Three clubs come up every year and have no measurement, so
any run containing them is rated over the remainder and says how many fixtures
that was. Nothing treats a promoted club as average.

## Rules that changed under us

- **The club limit binds differently on selection and on holding.** You can
  never select a fourth player from a club, but a player moving between clubs
  mid-season can leave you holding four, and the next transfer must correct it.
  Encoded in `transfer_respects_club_limit`: while a squad is over the limit,
  any transfer that leaves the breach standing is refused, because the
  correction is compulsory rather than optional. Sourced from the owner, who
  plays the game; not yet checked against the published rules text.
- **Assistant Manager is gone for 2026/27.** The live bootstrap publishes four
  positions, not five, and zero players of `element_type` 5. Historical
  reconstruction of 2024/25 still has to account for it; forward planning must
  not offer it.
- **Five substitutes since 2022/23.** Sub appearances went from 24.0% to 30.9%
  of appearances and full 90-minute games from 60.3% to 48.7%. This is
  permanent, so seasons before 2022/23 describe a different game.
