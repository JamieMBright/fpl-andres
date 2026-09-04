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

#: 8.17 holds a player out of new recommendations through his first gameweek
#: after FPL changes his club assignment. The daily season-input publisher
#: compares stable player codes with its previous artifact, preserves the old
#: and new club plus detection time, and expires the hold automatically after
#: that event. Existing owners may keep or sell him; ordinary transfers,
#: Wildcards and Free Hits cannot buy him during the hold. Minor: projected
#: points retain their meaning, but short-term candidate eligibility changes.
#:
#: 8.16 plans from the deadline instead of from FPL's `finished` flag. That
#: flag is set only once the bonus for every match in a round is confirmed,
#: hours after the last whistle and days after the deadline that locked the
#: squad, so the publishers kept solving for a gameweek nobody could act on any
#: more: on 31 August the site was still planning gameweek 2, played out over
#: the previous four days, while gameweek 3 was the one taking transfers. The
#: projected horizon now starts at the first gameweek whose deadline is still
#: ahead. `finished` keeps its own job, which is deciding what the corpus may
#: learn from, and a settled round still waits for confirmed bonus.
#:
#: Because every projected event is now genuinely in the future, `generatedAt`
#: and `dataAvailableAt` go back to the real publishing instant rather than
#: being dated forward to the first deadline to satisfy the causality check.
#: Minor: the horizon shifts by a gameweek and every number on it moves with
#: it, while nothing changes about what a projected point means.
#:
#: 8.15 lets an in-progress gameweek reach the xStart posterior and stops a
#: carried record from outvoting it. A live snapshot now counts once any player
#: in it has minutes or starts, rather than only once `roundComplete` is set, so
#: the week being played informs the plan for it instead of arriving a week late.
#: The prior is also no longer skipped for players with a measured record, and
#: its strength drops from four carried appearances to one. The held-out
#: quantity 8.12 fitted -- a settled current-season lineup is worth four carried
#: appearances -- is unchanged, because `--current-lineup-weight` still defaults
#: to 4.0; what moves is how much total mass the carried estimate starts with.
#: That mass was never separately fitted, and it is not fitted here either: the
#: choice is that after two current-season matches the posterior should follow
#: this season rather than last, which one carried appearance gives (8/9 recent)
#: and four did not (1/2 recent). It gives up prior stability for players whose
#: early sample is unrepresentative -- an injury return or a rotated cup week
#: now moves the number further than it did. Minor: P(start) keeps its target
#: and its meaning; the estimate and the plans built on it move.
#:
#: 8.14 makes the displayed one-to-five fixture rating opponent-only at the
#: opponent's venue, while route-specific xPts still uses both teams. The
#: browser now applies each advised Free Hit/Wildcard squad in a second full-
#: season solve, so temporary changes revert, permanent changes persist and
#: every following gameweek is planned from the state the chip actually leaves.
#: Minor: fixture summaries and manager-specific plans move without changing
#: the route projections they summarize.
#:
#: 8.13 carries the previous season's fitted club strengths by permanent club
#: code until each returning club has five current-season matches. It also
#: makes Free Hit a true one-week xPts1 rental: ten-plus temporary changes,
#: cheapest legal bench, restored squad/bank and one FT next week. Wildcards
#: compare legal xPts3/5/7/9 squads, require five permanent changes and retain
#: only exact whole-season gains. Minor: fixture multipliers, xPts, transfers
#: and chip plans move while their targets stay unchanged.
#:
#: 8.12 gives each settled current-season lineup four times the weight of a
#: carried appearance. Selected on 2022-24 and held out on 2024-26, it lowered
#: paired Brier by 0.0497 with a 95% lower bound of 0.0348 and all three seeds
#: promoting. Cold-start role priors receive the same update before bookmaker
#: participation and FPL availability. Minor: true P(start) keeps its target.
#:
#: 8.11 publishes settled GW1 starts/minutes into the GW2 xStart posterior and
#: rejects an exact Wildcard solve if earlier re-planning shrinks its final
#: turnover below five players. Minor: xStart and affected plans move, while
#: their targets and field meanings stay unchanged.
#:
#: 8.10 reduces the recent-points blend from 0.20 to 0.10 after a predeclared
#: five-weight experiment. Across 64 held-out gameweeks, paired weekly MAE
#: improved by 0.0110 with a family-corrected 98.75% lower bound of 0.00838;
#: both holdout seasons improved Spearman. Minor: xPts keeps the same target.
#:
#: 8.9 promotes current-plus-carried xStart evidence after a held-out GW2
#: comparison over 444 stable players. The selected two-event half-life and
#: four-event prior lowered paired Brier by 0.0244, with a 95% lower bound of
#: 0.0117 and all three bootstrap seeds promoting. Minor: true P(start) keeps
#: the same target, while settled current-season starts now update rather than
#: replace the carried record.
#:
#: 8.8 restricts every advisory captain and vice-captain to midfielders or
#: forwards. Observed manager, rival and cohort armbands remain unchanged.
#: Minor: recommendations and chip valuations move, while each player's xPts
#: and every published projection field keep the same meaning as 8.7.
#:
#: 8.7 keeps every rostered player in the browser planning population even
#: when FPL marks him doubtful, injured or suspended. Availability still
#: scales or zeros his projection and low-start players remain ineligible as
#: transfer targets unless already owned. Minor: xPts keeps the same meaning,
#: while valid manager squads no longer become unsolvable when one player is
#: temporarily unavailable.
#:
#: 8.6 groups scored predictions by what was projected and reports each band's
#: mean projection against its mean outcome. No projected point moves: this is
#: the grading harness, which this file's own rule places in scope because
#: `validation.json` is keyed on the version and now carries a field it did not
#: before. Minor, and the numerical projection is byte-identical to 8.5.
#:
#: 8.5 reconciles the player scoring market against the team scoring market and
#: stops reading two separate selections in one book as a complementary pair.
#: Summing the per-player anytime-scorer prices across a club implied 2.48x the
#: goals the same bookmaker's 1X2 and totals book implied for that club, and 21
#: rows quoted a first-scorer probability above the player's own anytime price,
#: which cannot happen. Attacking routes are now raised to a per-club exponent
#: fitted so the club's routes sum to its priced goals, which takes the margin
#: out of the longshots where it sits rather than spreading it evenly. Minor:
#: attacking numbers move a long way, but the target and the population are
#: unchanged.
#:
#: 8.4 adds explainable xStart evidence fields and changes planner chip
#: semantics: Free Hit is a temporary five-to-fifteen-player rebuild with no
#: transfer cost, and its squad/bank/free-transfer state is restored afterward.
#: Projected player rates and route weights are unchanged. Minor: the
#: recommendation contract and evidence surface changed while the numerical
#: projection retains its meaning.
#:
#: 8.3 restores row-level season-input provenance beside each player after the
#: player-market diagnostic route started reading the slimmer artifact surface.
#: Minor: route values keep their meaning, but the published season-input row
#: again names whether a player is carried by role prior, market participation,
#: attack, shots/BPS or cards.
#:
#: 8.2 removes copied per-player quote disclosure from the browser solver
#: artifact. The authoritative player-odds artifact still retains every quote,
#: and season inputs retain aggregate reach plus every number-moving blend.
#: Minor: projected points are unchanged; the shipped solver payload is smaller
#: and its schema now refuses the duplicated field.
#:
#: 8.1 consumes every market observed on the live Arsenal-Coventry survey.
#: First- and last-scorer prices are retained as overlapping corroboration of
#: anytime scorer rather than added as extra goals. Shots on target remain
#: observed when total shots are shut and become number-moving only when the
#: paired lines identify the BPS delta. At team level, paired h2h lay prices
#: tighten the 1X2 split and every complete alternate half-goal line contributes
#: to one total-goals consensus. Minor: routes keep their meaning, but live lay
#: and alternate-total evidence can move fixture multipliers.
#:
#: 8.0 replaces the crowd's synthetic top-25 captain shortlist with legal
#: model-owned elevens replayed from the season simulation. Every captain rule
#: now publishes chosen points, the ceiling reachable from that same XI and
#: owned-squad regret; significance is paired over those manager-gameweeks.
#: The 2022/23 through 2025/26 seasons are labelled retrospective because all
#: four outcomes were visible during model 7.1 development. Genuine evidence
#: begins with a pre-GW1 2026/27 manifest that freezes the revision, parameter
#: ledger and planning artifacts before the deadline. Major: the projection is
#: unchanged, but the population and meaning of its headline validation metric
#: are not comparable with 7.x.
#:
#: 7.1 keeps one fixture's player market as evidence beyond that fixture
#: without pretending it is a nine-week forecast. The quote-vs-history
#: deviation is full in its anchor gameweek and halves every two gameweeks;
#: before the anchor it carries no weight. Player goals, participation and card
#: evidence therefore inform future recommendations but yield steadily to the
#: completed-season record or depth-role prior. Team markets remain
#: fixture-specific: an unpriced future opponent keeps the season-strength
#: route ladder until its own 1X2 and totals markets open. Minor: routes and
#: start rates retain their meanings, but their horizon values now decay.
#:
#: 7.0 makes market evidence a route-level model rather than two publisher
#: adjustments. Goals, assists, cards, shots and shots on target retain their
#: own evidence and can inform participation without being multiplied into the
#: attacking route twice. Team expected goals continue to price clean sheets
#: and conceding, now explicitly drive goalkeeper-save pressure, and move the
#: odds of clearing the full CBIT/CBIRT defensive-contribution threshold rather
#: than linearly scaling points beyond its cap. Bonus is reconstructed from the
#: official BPS coefficients plus each player's historical residual for Opta
#: actions the corpus cannot source, then ranked against the expected starting
#: elevens for each market-priced fixture. Major: `routes.bonus`, start rates
#: and the route evidence attached to a projection now answer materially richer
#: questions, and debutants carry a complete measured role prior rather than
#: one undifferentiated points bucket.
#:
#: 6.5 stops the recency decay running across the summer break. Inside a season
#: a four-event half-life asks "what is he doing lately", which is the right
#: question in March. In August it is the wrong one and an actively misleading
#: one: the last month of a decided season is rotation, rested legs and dead
#: rubbers, the least representative football anybody plays, and ninety per cent
#: of the weight was sitting on it. A striker who started thirty-five of
#: thirty-eight but five of his last seven was published as a sixty-three per
#: cent starter for a season that had not begun -- a claim about April, not
#: about him -- and minutes scale every route, so it cost him a third of
#: everything. Every premium was suppressed the same way. Across the break the
#: half-life is the whole campaign, because none of it is recent and all of it
#: is his record. Minor: inside a season nothing moves at all, and a player who
#: genuinely lost his place is still marked down. This is also the one
#: configuration the backtest never scores -- it always projects gameweek N from
#: 1..N-1 within a season -- so it shipped unmeasured until now.
#:
#: 6.4 stops last season outvoting this one on defensive contribution. A
#: defender's action count is mostly a property of the arrangement around him --
#: how high the line sits, who screens in front, whether the manager changed,
#: who was signed in August -- and all of those turn over in a summer. The
#: projector used whichever season had rows, so last season was the whole answer
#: until a ball was kicked and then no part of it at all, and one gameweek
#: against the league prior decided the opening month. Now last season displaces
#: at most half the prior, in proportion to how much of it there is, and the
#: shrinkage strength is untouched -- weakening that to make room would have
#: made a thin record more volatile, not less. A completed gameweek of the
#: current arrangement therefore outweighs a gameweek of the last, which is the
#: rule that was asked for. Minor: a player with no previous season, and any
#: player once a season is a dozen matches old, is unchanged.
#:
#: 6.3 pays a defender the league's defensive-contribution rate where nothing is
#: known about his own. The route arrived in 2025/26, so every earlier season in
#: the corpus has a null column, and the code returned zero on an empty
#: observation list -- which is not "nothing is known", it is a claim that he
#: never clears the bar. It landed on exactly the players it should not have: a
#: promoted squad, an arrival from abroad, anyone whose Premier League record
#: predates the route. Defensive contribution is 7.5% of every point FPL awards,
#: more than assists, so a whole population was understated by more than the
#: route it replaced. `shrunk_rate` with no evidence already returns the league
#: rate for the position; the early return was the only thing stopping it.
#: Minor: a player with defcon minutes is unchanged to the last decimal. A
#: keeper is still paid nothing, because there is no bar for him to clear.
#:
#: 6.2 reads the one part of a player market that is not a price: who is in it.
#: A book opens a market on players it expects to be available, so a man missing
#: from a squad it otherwise named in full is the market saying he is not
#: playing -- which last season's appearances cannot know, and which is not the
#: evidence 5.0 removed. That was the anytime-scorer *price*, divided by a
#: scoring rate to infer minutes, counted twice into goals and into everything
#: minutes scale. This is the market's membership, read once, downward only:
#: being quoted proves availability the record already implies, so it changes
#: nothing. Minor. Guarded twice, because absence is only evidence when it is
#: complete: a club counts only where the book priced at least eleven of its
#: players, and the whole signal is refused for a run where any quoted name
#: failed the crosswalk -- an unmatched man was priced and is missing from the
#: matched rows, so absence would read him as dropped.
#:
#: 6.1 lets a bookmaker's card price move the yellow and red routes. The book
#: opens "to be shown a card" without saying which colour and opens a separate
#: red market on fewer fixtures, so the split is the whole question: FPL pays
#: -1 and -3, and putting a booking on the wrong route triples or thirds it.
#: Where both are quoted the split is the market's; where only the card market
#: is, the player's own recorded ratio of reds to cards apportions it -- the
#: market says how many, the record says what colour. Minor: the routes mean
#: what they meant. What it gives up is the fixture. The attacking route is
#: de-fixtured by the gameweek's own rung before publishing; the card routes
#: have no rung, so a derby's booking rate is published as if it were an
#: average fixture's. That flatters a player quoted in a hot tie, is bounded by
#: the blend weight, and is stated rather than corrected because there is no
#: measurement here to correct it with.
#:
#: 6.0 splits `routes.discipline` into yellow cards, red cards, own goals and
#: missed penalties. Major because the published shape changes: a reader that
#: knew eight route names now finds eleven, and the one it knew is gone. The
#: arithmetic does not move -- each of the four was already computed separately
#: and summed at the last line -- so no projection changes by a point. What
#: changes is that a booking has a route of its own. A book prices "to be
#: carded" directly and prices nothing else in that bundle; while the four were
#: one number there was nothing for that price to replace, which is why the
#: card market was fetched, measured and thrown away twice.
#:
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
MODEL_VERSION = "8.17"
