# Evidence and Capability Limits

These limits are product behavior. A missing source disables or downgrades a feature;
it never licenses a plausible estimate.

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

The product returns a next-deadline action, a rolling 6–8 gameweek path and a season
fixture/chip roadmap. It does not present an exact 38-gameweek transfer script.

Current solvers support expected value only and require `chip_scenario=none`.
Protect/chase utilities remain unavailable until calibrated outcome distributions
exist. Chip optimization remains unavailable until authoritative multiplier, bench and
transfer behavior is sourced. Rolling plans use provided event prices and conservatively
forbid reselling players acquired inside the horizon.

## Team goal projections

The current candidates use completed scores, venue and recency. They do not yet include
player availability, likely lineups, tactical events, bookmaker markets or licensed
event data. A successful numerical fit does not make a candidate production-ready.
Candidates remain `experimental` until a chronological, leakage-controlled paired
evaluation clears the declared sample floor and confidence gate.

## Execution

FPL Andres never logs into an FPL account and never executes transfers or chips.
