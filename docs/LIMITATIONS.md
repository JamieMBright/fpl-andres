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

## Injuries

The primary evidence is FPL's status, chance of playing, news timestamp and official
club source link. The product does not scrape Premier Injuries or republish third-party
injury lists.

## Prices

FPL does not publish the exact price-change mechanism. Outputs are calibrated movement
probabilities backed by timestamped transfer and price observations. Exact thresholds,
reset rules and protection claims are excluded.

## Rivals and consensus

Rival picks are used only after a deadline. Banked free transfers and pre-deadline
intentions are not public. FPL50 is a separate contextual view of revealed public
choices and does not alter player projections in v1.

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
