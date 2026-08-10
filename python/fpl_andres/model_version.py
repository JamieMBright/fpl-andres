"""The version of the projection, and the rule for moving it.

A number on the site is only interpretable against the model that produced it.
Two runs of `validate` a month apart are not comparable unless something records
whether the code between them changed, and "look at the commit" is not an answer
when the artifact is regenerated on a schedule.

So the projection carries a version. It is bumped by hand, in the same commit as
the change, and `scripts/model-version-gate.mjs` fails the build if a file under
`MODEL_PATHS` moved without it. That is the same shape as the contracts version
gate, for the same reason: the alternative is a number that silently means
something different from the last one.

## What counts as a change

Anything that can move a projected point. The rate models, the minutes model,
the scoring tables, the fixture adjustment, the blend, and the backtest that
grades them. Not the CLI's output formatting, and not the web app.

## Semantics

`MAJOR.MINOR`. Minor for a change that moves numbers; major for one that changes
what the numbers mean — a new scoring route, a different target, a different
population. There is no patch component because a change that cannot move a
number does not need a version.
"""

from __future__ import annotations

__all__ = ["MODEL_VERSION"]

#: 5.1 lets a bookmaker's match price set the fixture multipliers for the two
#: routes it prices directly. `ingest-odds` had been deriving implied clean
#: sheets and expected goals per club per match for four seasons, committing
#: them, and being read by nothing at all -- while clean sheets and goals
#: conceded between them are about a sixth of every point FPL awards. Where a
#: fixture is priced, its rung is now the market's; where it is not, the fitted
#: Dixon-Coles strength stands exactly as before. Minor: the routes mean what
#: they meant and the multiplier is still this fixture over an average one, but
#: the average is now the average fixture the same books priced that week
#: rather than the average meeting of two clubs over a season. Saves and
#: defensive contribution still come off the conceding term, because no match
#: market prices them.
#:
#: 5.0 lets a bookmaker's player prices move the attacking route itself, and
#: stops them moving the start rate. Major on both counts. `routes.attacking`
#: now means the record and the market weighted together rather than the record
#: alone, and it is built by inverting "chance of at least one" to a Poisson
#: rate and dividing out the fixture the quote already carried -- so a projection
#: with prices present is answering a different question from one without. The
#: start rate goes the other way and means only what the record measured again:
#: reading the same anytime-scorer price as goals and as minutes counted one
#: piece of evidence twice, into the attacking route and into every route that
#: scales with minutes. That path never ran in any case. It looked up an
#: `expectedGoals` field the projector did not publish, returned nothing for
#: everybody and said nothing about it, so 4.0's stated behaviour was never the
#: behaviour. `expectedGoals` and `expectedAssists` are published now, because
#: a book quotes the two halves separately and a route that adds them cannot be
#: taken apart again.
#:
#: 4.2 counts the defensive-contribution bar for the position being projected
#: rather than the one the player held when FPL published the label. FPL sums
#: clearances, blocks, interceptions and tackles for a defender and adds
#: recoveries for everyone else, so a wing-back moved to midfield carried a
#: count that was missing every recovery he had ever made into a bar two actions
#: higher. Minor: for a player FPL has not reclassified the re-derived count is
#: identical to the published one, which was checked against the live bootstrap
#: rather than assumed.
#:
#: 4.1 rates a club with no Premier League record on FPL's own published
#: strength instead of one hand-picked constant for every promoted side. The
#: fields were already ingested and read by nothing, and a constant standing in
#: for a source that exists is the thing this repository says it never does.
#: Minor: the numbers move for fixtures against promoted clubs and mean the
#: same thing they did.
#:
#: 4.0 lets a bookmaker's scoring price move a player's start rate, which is a
#: major because the published `startRate` no longer means only "how often he
#: started last season". It now means the record and the market, weighted, and
#: a projection built on it is answering a different question from one built on
#: the record alone. The weight is a publisher argument rather than a constant,
#: and with no odds artifact present every number is the record's exactly as
#: before -- so a run with no prices is comparable to 3.0 and a run with them
#: is not.
#:
#: 3.0 is the methodology audit, and it is a major because several of these
#: change what a number means rather than only what it is.
#:
#: The backtest and the live publisher no longer describe different models. One
#: read goal averages and the other Dixon-Coles, so `validation.json` measured
#: something other than what produced the projections beside it. `fixtures.py`
#: now owns one strength function and both call it.
#:
#: Shrinkage was against a weighted *mean* of two seasons' minute totals, which
#: is not a sample size: two 900-minute seasons came out as 900, so a player
#: with two full seasons behind him was pulled toward the position prior as hard
#: as one with a single season. It is the effective size now,
#: `(sum w*m)^2 / sum(w^2*m)`, which is the Kish rule written for minutes.
#:
#: Rates had no within-season recency at all, while the minutes model beside
#: them had decayed per event all along: a gameweek 1 goal and a gameweek 37
#: goal weighed the same. Same half-life for both now, because they are the
#: same weekend.
#:
#: Clean sheets and goals conceded were shrunk independently, so a defender
#: could carry a pair no scoreline distribution could produce. Conceding is
#: derived from the clean-sheet probability: `P(CS) = exp(-lambda)` names the
#: lambda, and the deduction is `E[floor(X/2)]` for that same lambda.
#:
#: Bonus was a per-match rate multiplied by expected 90s, charging a player for
#: his minutes twice. It reads the appearance probability now.
#:
#: The horizon solver picked the captain on the mean while the chip planner
#: scored the armband on a mean/ceiling blend, so in any week the two rules
#: disagreed the plan captained the man its own rule called second best. Both
#: use the blend. A transfer hit is charged at full price in a lookahead week
#: rather than at the week's objective weight, which had made a move in the
#: back half of a window cost two points instead of four.
#:
#: The ninetieth-percentile ceiling was the season maximum below ten
#: appearances -- nearest-rank lands on the top element at four or five -- so a
#: single hat-trick set a ratio a third of the captain valuation rested on.
#:
#: Dixon-Coles left every defence free while pinning the attacks, so the
#: likelihood had a flat ridge and the reported home advantage was wherever the
#: optimiser stopped. Both vectors are pinned.
#:
#: The promotion gate read a one-sided decision off a two-sided bound, testing
#: at half its stated alpha. It computes the one-sided quantile it decides on.
#:
#: Recent form averaged per gameweek and was then multiplied by the upcoming
#: fixture count, doubling a double twice. It is per fixture.
#:
#: Three event guards said 38 where the rest of the package said 47, so a 2019/20
#: gameweek that was actually played raised.
#:
#: 2.9 makes a leak guard fire that never could. Both rate models refuse an
#: observation whose kickoff is after the prediction cutoff -- and the backtest
#: built every observation with `kickoff_time=min(row.kickoff_time, cutoff)`, so
#: the value handed to the guard had already been made to satisfy it. What
#: survived was a gameweek-number filter, and a gameweek number is not a date.
#:
#: The case it was written for is a postponement. A fixture labelled gameweek 12
#: and replayed in gameweek 25's week has `gameweek < prediction_event` for
#: everything from 13 onward, so it was training gameweeks it had not been
#: played before. Rows are now filtered on the date they were actually played,
#: and the timestamp reaches the guard unmodified. Expect the metrics to move
#: wherever the corpus contains a rescheduled match.
#:
#: 2.8 closes the rest of the verified input bugs, so every projected point
#: moves again. Double gameweeks were the worst of them: two fixtures were
#: merged into one observation, summed, capped at 120 minutes and then spent
#: per fixture, which both understated a doubled player's ceiling and hid the
#: second match from the evidence count. Splitting them exposed a latent error
#: underneath -- the recency weights were keyed by gameweek, so a doubled week
#: counted once in the denominator and twice in the numerator and a start rate
#: could exceed one.
#:
#: Also: the booking prior was pooled across all four positions, charging
#: goalkeepers a midfielder's card rate; defensive contribution was shrunk
#: twice, once by the rate and again by a coverage multiplier; and four places
#: read a missing value as a confident one. A ruled-out player kept an
#: "inferred" evidence chip, a player who has never started assumed certainty
#: about what he does when he starts, a zombie transfer was inferred from an
#: absent minutes reading, and a replacement was ranked against a player who
#: had no rank. Each now says what it does not know.
#:
#: 2.7 fixes two bugs that moved every projected point, so expect the metrics
#: to move with it. The club-change discount had never fired: no projector call
#: site passed the club or the role, so a transferred player carried his old
#: rate at full weight. Clean sheets and bonus were the only supporting routes
#: with no shrinkage prior, which priced a defender three matches in at whatever
#: his three matches happened to show. Between them those two routes are a fifth
#: of every point FPL awards.
#:
#: The captaincy intervals are also now widened for the number of theses tested
#: at once, so a gap has to clear a higher bar than it did in 2.6.
#:
#: 2.6 adds the set-and-forget baseline -- captain the most-owned player at the
#: first scored gameweek and never think again, with the armband passing to the
#: next most owned when he does not play. Written without Haaland's name in it,
#: because naming him would be hindsight. It is the baseline that matters: no
#: projection, no form, no fixture, and no decision after the opening week. A
#: model that cannot beat it is not earning its complexity.
#:
#: Also publishes the arithmetic behind every armband, so a surprising pick can
#: be read rather than defended.
#:
#: 2.5 retains the captaincy picks themselves rather than only what they
#: returned. No projection and no metric should move: the scorers compute
#: exactly what they always did and now write down which player they named.
#: That is precisely why it gets a version — the scorer signatures changed, so
#: the run needs a label the CI comparison can hold the previous numbers
#: against and show that none of them moved.
#:
#: 2.4 is the first version that actually produces the intervals 2.3 promised.
#: 2.3 refused to score a gameweek where the captain lost points -- a red card
#: or an own goal -- so the backtest raised before writing anything. Nothing
#: 2.3 claimed was ever measured, which is why this is a version and not a
#: patch: the two are not comparable, because one of them has no numbers.
#:
#: 2.3 stopped ranking the captaincy theses and started testing them. A table of
#: ten means always produces a winner, whether or not one exists, and the 2.2
#: ordering inverted on a single arithmetic fix -- which is what a lead inside
#: the noise looks like. Every thesis is now paired week for week against the
#: projection and resampled, so a gap that does not clear zero is reported as
#: not clearing zero. No projection changed; what changed is what may be
#: claimed from it.
MODEL_VERSION = "5.1"
