# What the model actually calculates

Written so the arithmetic can be argued with. Every number below is either a
constant in the source or a figure measured from the corpus, and each says which
it is. Where the code and this document disagree, the code is right and this
document is a bug.

Source of truth for each section is named in `backticks`.

---

## 1. The unit of projection

`backtesting/projector.py`

A projection is **one player, one fixture**. Gameweek totals are sums over that
player's fixtures in the week, so a blank contributes nothing and a double
contributes twice. Nothing is scaled by "games per week" as an average.

```
expected_points(player, fixture)
    = appearance_points
    + attacking_points
    + supporting_points
```

The three terms are built separately because they respond to opponent strength
in opposite directions.

---

## 2. Minutes, before anything else

`models/minutes.py`, `projector._project_minutes`

A player who does not play scores nothing, so minutes are modelled first and
everything else is conditioned on them. The model emits four figures:

| Figure                      | Meaning                                  |
| --------------------------- | ---------------------------------------- |
| `probability_appear`        | plays at all                             |
| `probability_sixty_minutes` | reaches the hour, so takes the 2nd point |
| `probability_start`         | named in the starting eleven             |
| `expected_minutes`          | minutes expected in this fixture         |

Appearance points fall out of the first two directly:

```
appearance_points = (P(appear) - P(60)) * 1 + P(60) * 2
```

**Recency.** Observations are exponentially decayed with a **four-gameweek
half-life** (`decay_half_life_events = 4.0`), so a month ago counts half of last
week. There is no minutes cutoff anywhere: see §9 for why.

**Effective sample size.** Shrinkage weights use the Kish effective sample size
`(Σw)² / Σw²`, not the raw weight sum. Using the raw sum understates a nailed
starter badly once decay is applied.

**Calibration.** Measured across the corpus, predicted `P(appear)` sits within
**0.07** of the observed rate and `P(60)` is close to exact.

---

## 3. Attacking rate — and which xG it uses

`models/player_rates.py`

This is the part most likely to be assumed naive, so it is spelled out.

**Measurement basis.** The model prefers **expected** goals and assists over
realised ones, and says which it used in `reason_codes` as
`basis=expected` or `basis=actual`. The basis is decided **once across both
seasons of evidence** — mixing an expected value with an actual one would be
averaging two different measurements.

The basis is `expected` only when _every_ observation carries both columns.
Measured coverage in the corpus:

| Seasons            | `expected_goals` and `expected_assists` | Basis resolved |
| ------------------ | --------------------------------------- | -------------- |
| 2019-20 to 2021-22 | **0%**                                  | `actual`       |
| 2022-23 to 2025-26 | **100%**                                | `expected`     |

FPL did not publish expected values before 2022-23. **This means a backtest
spanning all seven seasons is scoring two different models**, and any comparison
across that boundary has to say so. The xG is FPL's own column, which they source
from Opta.

**Two-season blend.** Current-season evidence displaces the carried prior season
progressively, by minutes:

```
current_weight = min(1, current_minutes / 900)      # blend_full_weight_minutes
carried_weight = 1 - current_weight
```

At 900 current-season minutes the prior season is fully displaced. With no
current minutes the projection is entirely carried, and the evidence level drops
to `inferred` naming the season it came from.

**Shrinkage.** The blended rate is pulled toward a positional prior, weighted by
minutes played:

```
rate_per_90 = (events + prior_rate * 450/90) / (minutes/90 + 450/90)
```

`prior_strength_minutes = 450`, so a player with 450 minutes sits halfway between
his own record and the positional prior. Priors by position:

| Position | goals/90 | assists/90 |
| -------- | -------- | ---------- |
| GKP      | 0.00     | 0.00       |
| DEF      | 0.05     | 0.06       |
| MID      | 0.12     | 0.13       |
| FWD      | 0.28     | 0.12       |

This table listed MID at 0.10 and FWD at 0.22 until 2026-08-01, against the
code's 0.12 and 0.28. Nothing compared the two, so it had been describing a
different model from the one running. `docs/PARAMETERS.md` records where every
number comes from, and a test now fails if this table and the code disagree.

**Floor.** Below `minimum_minutes = 180` across both seasons the rate is
`unavailable` and the player is not projected at all, rather than being given a
prior and presented as knowledge.

---

## 4. Every scoring route, priced

`projector.py` constants

Fourteen routes, not four. Verified by reconstructing realised points from
component columns: 2025-26 reconciles to **34,383** against an actual **34,382**,
and 27,353 of 27,605 rows in 2024-25 match exactly, the remainder being managers.

| Route                  | GKP      | DEF      | MID     | FWD     |
| ---------------------- | -------- | -------- | ------- | ------- |
| Goal                   | 10       | 6        | 5       | 4       |
| Assist                 | 3        | 3        | 3       | 3       |
| Clean sheet            | 4        | 4        | 1       | 0       |
| Goals conceded         | −1 per 2 | −1 per 2 | 0       | 0       |
| Saves                  | 1 per 3  | –        | –       | –       |
| Defensive contribution | 0        | 2        | 2       | 2       |
| Penalty save           | 5        | –        | –       | –       |
| Penalty miss           | −2       | −2       | −2      | −2      |
| Yellow / red           | −1 / −3  | −1 / −3  | −1 / −3 | −1 / −3 |
| Own goal               | −2       | −2       | −2      | −2      |

Defensive contribution thresholds are on the **raw action count**: 10 for
defenders, 12 for midfielders and forwards, not available to goalkeepers. It is
new for 2025/26 and was **7.5% of all points** that season. Null before 2025/26
is absence-of-rule, not missing data.

The count itself differs by position. A defender's is clearances, blocks,
interceptions and tackles; a midfielder's and a forward's adds recoveries. FPL
publishes one `defensive_contribution` column holding whichever of the two
applied to that player at that time, so the projection re-derives the count from
its three components for the position it is projecting
(`rates.defensive_actions`). This matters only where FPL has reclassified
someone: a wing-back moved to midfield would otherwise carry a count missing
every recovery he had ever made into a bar two actions higher. For everyone
else the re-derived count equals the published one, which was checked against
the live bootstrap rather than assumed. Seasons before 2025/26 publish no
components, and there the published label stands.

---

## 5. Fixtures change routes, not totals

`backtesting/fixtures.py`

A single difficulty number is wrong for this game. A hard fixture suppresses
clean sheets while _raising_ saves and defensive contributions, because a side
under pressure defends more. Each route therefore carries its own multiplier.

Team strength is estimated from results already played, expressed as a
multiplier on the league average goals per side, **split by venue**, shrunk
toward average with a **ten-match prior**, and clamped to `[0.4, 2.2]` so an
early-season freak run cannot produce an absurd figure.

FPL's own 1–5 difficulty rating is deliberately ignored: it is subjective and
null for older seasons.

**Where a bookmaker has priced the fixture, the market's rung is used instead.**
`backtesting/fixtures.market_route_adjustment`. A match market prices two of
these five routes directly — goals for and goals against — and it prices them
for Saturday, with the injuries, the suspensions and the rotation already in
the number. The fitted strength above answers a different question: how these
two clubs have met across a season, shrunk toward average. For the routes both
describe, the market is the better estimate of the same quantity and blending
would only dilute it.

football-data.co.uk remains the first source because one CSV prices a whole
round at no metered cost. If it carries no current Premier League rows, the
team-odds ingest falls back to The Odds API's `h2h` and `totals` markets. It
fetches only uncovered fixtures inside the nearest six-day match window and
retains prior rows, so a round costs at most twenty credits once rather than
twenty credits every daily run. Both sources enter the same de-vigged
independent-Poisson fit below.

The conversion needs a denominator, because a market clean sheet is an absolute
probability and a route takes a multiplier. It is the mean of the fixtures the
same books priced that week, so a market rung and a fitted rung mean the same
shape of thing: this fixture over an average one. Saves combine the goalkeeper's
shrunk historical save-point rate with that opponent pressure. Defensive
contribution applies the same pressure to the odds of clearing the player's
full CBIT/CBIRT threshold, so a harder fixture can raise the route without ever
paying more than its two-point maximum.

A double gameweek is left to the fitted strength: the rung is the sum of two
fixtures and one price cannot fill it. So is any week the ingest has not run,
and the whole gap between seasons.

---

## 6. The blend with recent scoring

`projector._blend`

The component reconstruction is indirect and accumulates error across fourteen
routes. A player's recent realised points are direct but noisy. Neither is best
alone:

```
projection = 0.8 * components + 0.2 * recent_mean(last 5)
```

`recent_form_weight = 0.2`. Measured independently in **each of seven seasons**
and landing between 0.7 and 0.8 every time, including the three seasons held back
from the original fit. It is not tuned to the seasons it is reported against.

The weight sits on the model's side of the split, which is the direction
Ramezani and Dinh report for FPL specifically: a hybrid at two-thirds model to
one-third realised points "typically sits above or on top of the original
method's curve", while a 2:1 hybrid favouring realised points "often
underperforms the base method, suggesting that overweighting raw historical
points re-introduces the very noise the predictive model is designed to filter
out" (_A data-driven framework for team selection in Fantasy Premier League_,
[arXiv:2505.02170](https://arxiv.org/abs/2505.02170), §8). Our 0.8/0.2 is further
toward the model than their best 0.67/0.33, and was arrived at by measurement
rather than by copying theirs.

**The blend makes the headline comparison a superset.** `recent_mean` is the
naive baseline _and_ 20% of the projection, so "model beats recent_mean" cannot
fully fail. The backtest therefore scores a fourth method, `components`, which is
the same projection with the blend removed. That is the number that says whether
the route pricing carries itself. Both are published; see `docs/MODEL_CARDS.md`.

---

## 7. The horizon ladder

`projector.project_horizon`

Projections are produced at **+1, +3, +5 and +7** gameweeks from **one fixed
reading of form**. Only the fixture list varies across the ladder — projecting
future form from future results would be a leak.

Measured gain over repeating a one-week projection: **+0.012** at three,
**+0.019** at five, **+0.020** at seven, on rank correlation. It matters less
than it sounds, because 83% of the top thirty is the same either way.

---

## 7b. Where a bookmaker gets a say

`models/market_routes.py`, `models/market_evidence.py`,
`backtesting/bonus.py`, `cli/publish_season_inputs.py`

Everything above reads history. A book reads the team sheet. It knows a striker
has lost his place, that a summer signing has taken it, and what the manager
said on Friday — none of which is in last season's numbers. So where a market
prices a scoring route, its view is blended into that route at a stated weight.

The live ingest reads anytime, first and last goalscorer, assists, bookings,
reds, shots and shots on target. First/last scorer overlap anytime scorer, so
they are retained as corroboration and never added as independent goals. The
team market supplies 1X2, its paired lay view, totals and alternate totals. The
shared artifact records the source timestamp and content hash; individual rows
carry their own observation time because a capped run can retain one fixture
while refreshing another.

Three things make the reading honest rather than convenient.

**A price is a probability and FPL pays per event.** "Anytime goalscorer" is
the chance of at least one; two goals pay twice and the price does not say so.
Goals arrive within a match as a Poisson process, so `P(at least one)` is
`1 − e^−λ` and the rate behind a price is `λ = −ln(1 − P)`. That inversion is
an assumption, it is mild — hardly anybody scores twice — and it fails upward
on the shortest prices, where real scoring is slightly underdispersed against
Poisson. It is stated rather than corrected, because there is nothing measured
here to correct it with.

**A price is for one fixture and this artifact publishes an average one.**
Section 5 sends the browser a per-route base and a per-gameweek multiplier. A
market rate already carries its opponent, so publishing it as the base would
apply that fixture twice — once by the book, once by the solver. The rate is
therefore divided by the multiplier of the gameweek it was quoted in before it
is published. In a double gameweek the rung is the sum of two fixtures while
the book priced one of them, so there is no divisor and the record stands.

**Half a view beats none.** Goals and assists are blended separately against
the projector's own `expectedGoals` and `expectedAssists`, so a fixture with an
anytime-scorer market and no assist market still counts, and leaves the assists
where the record put them.

### Shots and participation

Shots and shots on target are over/under lines, not anytime yes/no prices. The
Over and Under are de-vigged together and the Poisson tail at the quoted line is
inverted to an expected count. Understat supplies the historical shots-per-90
baseline. The market count can then imply minutes at that established event
rate; the estimate is blended and labelled `experimental`, because a changed
price can also mean changed ability or role.

A shots-on-target line without total shots is still published as observed
evidence, but it does not move BPS. Historical BPS already includes the
player's normal shot outcomes, and no retained source supplies a historical
on-target baseline to subtract. Adding the raw future SOT award would therefore
double-count it. Once both shot lines are open, their ratio supplies that
baseline consistently and the paired BPS delta becomes number-moving.

The same evidence is not spent twice. The goals/assists market writes the
attacking route directly. Market-inferred participation scales the other
minutes-dependent routes while attacking is held at its already blended value.
For a new arrival, the baseline is the complete measured route vector of a
player at the same position and FPL price-depth rank, not one undifferentiated
points bucket.

One fixture is not nine forecasts. The player-market deviation from that
historical or role baseline is carried forward with a two-gameweek half-life:
full in the quoted gameweek, half two gameweeks later and one-sixteenth by the
ninth. A quote never leaks backward before its fixture. This lets a market
reveal a new role or stronger scorer without permanently replacing a season of
evidence. Team odds are different: they describe one opponent, so only that
fixture's ladder rung changes. A paired back/lay spread sharpens the same 1X2
goal split; it is not a second match. Complete alternate half-goal lines are
each inverted to a total-goals mean, consolidated by line, then combined with
2.5 into one consensus. Later FDR remains the season-strength estimate until
the later fixture gets its own team markets.

### Bonus and BPS

The history corpus retains observed BPS. For a future match, every component
available here is reconstructed with the official coefficients: minutes,
goals, assists, clean sheets, goals conceded, penalty events, cards, own goals,
shots on target, clearances, blocks, interceptions, tackles and recoveries.
Pass completion, errors, shot location and the other Opta-only inputs are not
set to zero. Their difference from reconstructed historical BPS is retained as
the player's per-appearance residual.

For a market-priced fixture, the expected starting elevens' BPS means and
historical spreads are compared to estimate first-, second- and third-place
probabilities. Those probabilities replace the historical bonus route for that
fixture. The normal approximation does not reproduce integer BPS ties exactly,
so this route is `experimental`; where either expected XI is incomplete, the
historical bonus rate remains.

### Bookings

A book opens "to be shown a card" and does not say which colour, and opens a
separate red-card market on fewer fixtures. FPL pays −1 for a yellow and −3 for
a red, so the split decides the points: putting a booking on the wrong route
triples or thirds the charge. Where both markets are quoted the split is the
market's own. Where only the card market is, the player's own recorded ratio of
reds to cards apportions it — the market says how many bookings, the record says
what colour, and neither source is asked a question it cannot answer. A red
quote with no card quote is refused outright: reds are around a twentieth of
bookings and a rate built from them alone would read as if the player were never
booked otherwise.

What this gives up is the fixture. The attacking route is de-fixtured by its
gameweek's own rung before publishing; the card routes have no rung, because
nothing here has measured how a booking rate moves with the opponent. A derby's
quote is therefore published as if it were an average fixture's, which flatters
a player priced in a hot tie. It is bounded by the blend weight and named here
rather than corrected.

### Who is in the market at all

Everything above reads a price. This reads the list. A book opens a player
market on men it expects to be available, so a player missing from a squad it
otherwise named in full is the market saying he is not playing — a dropped
man, an injury announced on Friday, a rotation nobody has published. Last
season's appearances cannot know any of it.

Absence is read downward: being missing from a complete squad list pulls a
player toward zero at the stated blend weight. Presence alone does not prove a
start. A quoted event count can move participation only through the separate,
experimental rate-to-minutes inference above.

Guarded twice, because absence is only evidence when the list is complete.

- A club counts only where the book priced at least eighteen outfield players.
  The live Arsenal market named seventeen but no goalkeeper; the old floor of
  eleven therefore read Raya as dropped. Books open scorer markets unevenly,
  so anything below a full outfield matchday set is presence evidence only.
- The whole signal is refused for any run where a quoted name failed the
  crosswalk. An unmatched man _was_ priced and is missing from the matched
  rows, so absence would read him as dropped. The one thing worse than not
  using this is using it on the players it is wrong about.

This is not the path 5.0 removed. That path divided an anytime price by a
positional scoring prior and then multiplied the result back into goals and
every other route. Model 7.0 requires the player's own measured event baseline,
keeps the market-written attacking route fixed, labels the minutes consequence
experimental, and publishes counts for every route it actually moved.

The blend lives in `publish_season_inputs` rather than in the projector because
that is where last season's team strength meets this season's clubs and fixture
list, and the divisor cannot be computed without all three. The consequence is
that it reaches the browser's own solve and not the pre-solved
`season-plan.json`, which reads `projections.json` directly. That is deliberate.
A book prices the next few days; the season plan commits thirty-eight gameweeks
and is regenerated rarely, so folding one week's quotes into it would move a
year of chip and transfer structure on evidence that expires by Saturday. The
plan a manager actually solves for their own squad is the one that reads the
market.

Nothing here emits or implies a betting recommendation. A price is read as a
probability and used as evidence about a footballer.

---

## 8. Between seasons

`projector.project_next_match`

Before a ball is kicked there is no form and no fixture, so the only honest
figure is **points per match against an average opponent**, computed with a
neutral route adjustment. It is a record, not a forecast, and is labelled as one
everywhere it appears.

---

## 9. Why there is no minimum-minutes filter

Backtested over six consecutive season pairs against next season's opening
starts, on a common population:

| Predictor                               | Spearman  | Beats the model |
| --------------------------------------- | --------- | --------------- |
| **The minutes model's own `P(start)`**  | **0.547** | —               |
| Season minutes                          | 0.513     | 1 of 6          |
| Season starts                           | 0.514     | 1 of 6          |
| Closing-six starts                      | 0.505     | 0 of 6          |
| Rank blend of season and closing starts | 0.559     | 4 of 6          |

The model beats every crude marker. A rank blend edges it by about **0.012**,
which is real but slight, and it is not wired in.

An earlier version of this table quoted 0.616 against 0.646. Those figures were
measured across every player rather than the model's own population, so they
included fringe players whose non-selection is trivially predictable and who
inflate any correlation. Scoring each method on the population it can actually
rank is the same trap that once made a naive baseline look better than the
projection.

No single cutoff is good. A 900-minute floor rejected a keeper who made seven
appearances and started all six of the closing weeks, while passing a forward who
made thirty-two and started none of them. Among players such a floor rejects,
those who started four of the final six went on to start the next opening six
**42%** of the time against **10%** for the rest — in all six pairs.

**The blend is measured and not yet wired in.** The minutes model uses decay
weighting, which captures part of it, but does not count starts separately from
minutes.

---

## 10. Which seasons are comparable

Two boundaries fall in the same place, which makes 2022-23 a genuine regime
change rather than a convenient cut.

| Boundary                             | When    | Effect                                                                                   |
| ------------------------------------ | ------- | ---------------------------------------------------------------------------------------- |
| Five substitutes replaced three      | 2022-23 | Sub appearances 24.0% → 30.9%, full 90s 60.3% → 48.7%, points per appearance 3.00 → 2.80 |
| FPL began publishing expected values | 2022-23 | Rate basis switches from `actual` to `expected`                                          |
| Defensive contribution introduced    | 2025-26 | A new route worth 7.5% of all points                                                     |

The substitution change is permanent and never reverts, so seasons before
2022-23 describe a different game _and_ are scored by a different model.

**What this means in practice, by use:**

- **Minutes** — pre-2022-23 is actively misleading. A model learning appearance
  behaviour from three-substitute seasons will systematically over-predict full
  matches.
- **Attacking rates** — pre-2022-23 has no expected values at all, so it cannot
  contribute to an expected-basis fit.
- **Robustness checks** — old seasons remain useful for exactly one thing:
  confirming a parameter is not tuned to recent data. The 0.8/0.2 form blend
  landing between 0.7 and 0.8 in all seven seasons independently is worth more
  _because_ three of them are a different regime.

**Recommendation, not yet acted on**: fit on 2022-23 onward, and report older
seasons only as out-of-regime robustness. Anything that quotes a seven-season
average without saying which side of the boundary it sits on is mixing two
populations.

---

## 11. The algorithms, end to end

### xPts — expected points for one player, one fixture

`backtesting/projector.py`

```
xPts(player, fixture):

    # 1. Minutes, from decayed history (4-gameweek half-life)
    m         = minutes_model(player, cutoff)
    if m.evidence == unavailable: return NOTHING     # never guessed

    ninety    = m.expected_minutes / 90
    appear    = (m.P_appear - m.P_60) * 1 + m.P_60 * 2

    # 2. Attacking rate, expected basis where available (§3)
    basis     = expected if every observation has xG and xA else actual
    w         = min(1, current_minutes / 900)
    goals     = w * current_goals(basis) + (1-w) * carried_goals(basis)
    mins      = w * current_minutes     + (1-w) * carried_minutes
    g90       = (goals + prior_g90 * 5) / (mins/90 + 5)        # 450 min prior
    a90       = (assists + prior_a90 * 5) / (mins/90 + 5)

    # 3. Opponent, per route, by venue (§5)
    adj       = route_adjustment(strength, team, opponent, home)

    attack    = ninety * (g90 * GOAL_POINTS[pos] + a90 * 3) * adj.attacking

    # 4. Everything else, each on its own multiplier
    support   = clean_sheet(pos, m, adj.clean_sheet)
              + conceded(pos, m, adj.conceding)
              + saves(pos, m, adj.saves)
              + defensive_contribution(pos, m, adj.defcon)
              + bonus + cards + penalties + own_goals

    components = appear + attack + support

    # 5. Blend against the player's own recent scoring (§6)
    return 0.8 * components + 0.2 * recent_mean_5
```

Gameweek xPts is the sum over that player's fixtures in the week: **zero for a
blank, twice for a double**. Squad xPts is the sum over the best legal eleven,
plus the captain again.

### ExPts — effective points, which is not the same objective

`planning/effective.py`

xPts asks "how many points". ExPts asks "how many **places**". They are
different objectives and conflating them is the most common error in this game.

```
ExPts(player):

    EO     = effective ownership          # share of the field starting him,
                                          # counting captaincy twice
    mine   = 1 if I own him else 0

    swing  = (mine - EO) * xPts           # expected points gained on the field
    cover  = EO * xPts                    # what NOT owning him would cost
    upside = (1 - EO) * xPts              # what owning him gains on those who don't

    places = rank_of(my_total) - rank_of(my_total + swing)
```

where rank comes from a normal model of the field:

```
share_below(points) = Φ((points - field_mean) / field_sd)
rank_of(points)     = (1 - share_below(points)) * field_size
```

**The result that matters, and it is counter-intuitive.** Ownership _cancels out
of a transfer's expected gain_. Swapping player A for player B changes swing by
`(xPts_B - xPts_A)` regardless of what the field owns, because the `-EO * xPts`
terms belong to the field whether you hold the player or not.

So **effective ownership is not a return setting, it is a risk setting**. High
ownership narrows the distribution of outcomes; differentials widen it. Which you
want depends only on whether you are ahead or behind. The module therefore
reports `cover` and `upside` separately rather than collapsing them into one
score that would imply a false certainty.

Measured worth of playing to rank rather than to raw points: **about +16 points
a season**, and it lost in one season of four. That is weak, and it is stated as
weak.

---

## 11b. Four things carried beside the projection

These modules exist, are tested, and were documented nowhere.
None of them changes the expected-points number. All of them change what a
sensible person does with it, which is why they are carried alongside rather
than folded in.

### Shot volume and shot quality, separated

`models/shot_profile.py`. Non-penalty xG per 90 is volume times quality: how
often a player shoots, and how good the chances are. The two behave completely
differently year to year.

Measured across four Understat seasons, on players with 900+ minutes in both:

| Quantity     | Year-to-year repeat |
| ------------ | ------------------- |
| Shot volume  | 0.890               |
| npxG per 90  | 0.860               |
| Shot quality | 0.455               |

Volume is the durable part. Quality is noisy, but it is not noise: replacing a
player's own quality with the league mean makes prediction **worse**, MAE rising
from 0.0561 to 0.0666. Shrinking quality toward the league in proportion to the
shots behind it wins, with the optimum near ten shots of prior — measured, not
chosen.

### Penalty exposure

`models/penalties.py`. FPL's `expected_goals` includes penalties, so projecting a
player's scoring from it quietly assumes he keeps the duty. Duty moves: between
seasons, on a transfer, and sometimes after one miss.

Measured on 2025-26, penalties are **5.9% of league xG** — and **44.5% of Cole
Palmer's**, **38.3% of Bruno Fernandes's**, with 24 regulars above 15%. That is a
concentrated, nameable risk rather than a rounding error.

Nothing here predicts who will take penalties. It measures exposure to an
assumption the projection is already making, which is a different and more
honest job.

### Suspension risk

`models/suspensions.py`. A booking costs one point. The accumulation behind it
costs a whole gameweek, and for a nailed starter that is the difference between
five points and none. A model that prices the card and ignores the ban has
priced the small half.

Thresholds are **sourced, never assumed**. The Premier League resets cautions
partway through the season and the reset point is a rule of the competition, so
`SuspensionRules` must be supplied by a caller who has read the handbook.
Nothing in the module invents one, and it refuses rather than defaulting.

### Return shape

`backtesting/reliability.py`. Two players can share an expected score and be
completely different holdings. A defender who clears the defensive-contribution
threshold most weeks banks two points he will almost certainly get. A defender on
the same expectation who depends on clean sheets is holding a lottery ticket:
larger when it lands, absent most weeks.

Expected points cannot tell those apart, so the distribution is measured
separately — floor, median and ceiling at the 20th, 50th and 90th percentiles —
and kept beside the mean rather than folded into it. Folding it in would produce
a single number that implies a certainty the evidence does not support, which is
the same reason §11 reports `cover` and `upside` separately.

---

## 12. How Understat is meant to change this

Not yet built. Written down so the plan can be argued with before it is, and so
each stage names the thing it would have to beat.

**The standing rule: nothing ships unless it beats the current model on a
held-out basis.** More inputs is not the same as more accuracy, and a richer
model that loses is still a loss.

### Stage 1 — separate penalties from open play

FPL's `expected_goals` **includes penalties**, and a penalty is worth about 0.79
xG. A designated taker therefore carries an inflated rate that has nothing to do
with his open-play threat, and the rate persists in the model after he loses the
job to a new signing or a new manager.

Understat publishes `np_xg` alongside `xg`, so the attacking term splits:

```
g90 = open_play_rate                     # from np_xG, persists with the player
    + penalty_share * penalty_conversion # from role, changes overnight
```

The two behave completely differently and should be shrunk with different
strengths. Open-play threat is a property of the footballer; being on penalties
is a property of the team sheet.

**Beats what:** the current single blended rate, on any season where a penalty
taker changed club or lost the duty.

### Stage 2 — decompose the rate into volume and quality

```
xG_per_90 = shots_per_90 * xG_per_shot
```

This matters because the two halves stabilise at very different speeds. Shot
volume is a high-count signal that settles inside a handful of matches; shot
quality is a low-count average that needs most of a season. Shrinking them
**separately**, each toward its own positional league rate, should cut variance
on exactly the players the current model is worst at — the ones with thin
recent history.

`key_passes` does the same job for assists, and `xg_chain` / `xg_buildup` capture
involvement in moves that end in a shot, which `xA` misses because it only counts
the final pass.

**Beats what:** the current single-rate shrinkage, measured on early-season
gameweeks where history is thinnest.

### Stage 3 — shot locations, and the positional matchup

This is the one that needs coordinates, and the one nothing currently supports.

Understat publishes every shot with `X`, `Y`, situation and result. Two things
fall out:

1. **Where a player shoots from.** A striker taking six-yard-box chances and one
   taking twenty-five-yard efforts can have identical xG per 90 and completely
   different distributions. Only one of them has a realistic ceiling.
2. **Where an opponent leaks.** Aggregate xG conceded by pitch zone per club, and
   a defence that is sound centrally but soft down its left becomes visible.

Combined, the attacking adjustment stops being one number per fixture:

```
adj.attacking = Σ_zone  player_shot_share[zone] * opponent_concession[zone]
```

A left-sided forward against a side that leaks down its right gets an uplift the
current model cannot express, because today every attacker at a club receives the
identical multiplier.

**Beats what:** the single per-fixture attacking multiplier in §5. This is the
largest potential gain on the list and also the least certain, because zone
concession is a thin measurement — twenty clubs times a handful of zones across
one season is not many shots per cell.

### What Understat cannot fix

- It has no bonus points, no defensive contribution, and no saves, so §4's
  supporting routes stay on FPL's own columns.
- It does not cover the Championship, so promoted clubs remain unmeasurable.
- Its ids need the crosswalk in `cohorts`, which verifies **94.9%** of eligible
  2025-26 players by corroborating minutes and goals. The remainder are named
  gaps, not silent ones.

---

## 13. What this does not calculate

- **Shot locations.** Understat publishes shot coordinates. Nothing reads them,
  so there is no flank vulnerability, no shot-quality decomposition beyond xG,
  and no positional matchup.
- **Non-penalty xG.** FPL's expected goals include penalties, which flatters a
  penalty taker's open-play rate. Understat's `np_xg` is joined and unused.
- **Key passes.** Understat's season endpoint used here does not expose them in
  the published artifact. Shot volume is now read; key passes remain in the BPS
  residual.
- **Why a player is playing.** A stand-in for an injured first choice reads
  exactly like a man who won his place.
- **Squad restructuring.** Transfers are like-for-like by position.
- **Price movement.** Team value follows observed prices; nothing forecasts a
  rise.
- **Posterior carry.** Models refit on decayed history each week rather than
  updating a posterior forward.
- **Direct markets for every route.** Own goals, penalty misses and penalty
  saves have no dependable named-player market in the measured catalogue, so
  they remain shrunk historical rates. API-Football lists player tackles and
  goalkeeper saves, but its fixture probe has not yet observed a Premier League
  selection shape that can be crosswalked safely. Tackles alone are never
  presented as DefCon: the model uses FPL's full clearances, blocks,
  interceptions, tackles and recoveries history, then team-market pressure.

---

## 14. How to check any of this

- Rate basis and weights are in `reason_codes` on every `PlayerRateProjection`.
- Every published figure lives in a committed artifact, so a number on the site
  traces to the commit that produced it.
- `python/tests/test_reachability.py` fails the build if any function stops being
  called, so this document cannot quietly describe dead code.
- `python/tests/test_model_document.py` fails if a model module stops being named
  below, or if a measurement quoted here stops matching the module that produced
  it.

### Where each part lives

| Section                               | Module                       |
| ------------------------------------- | ---------------------------- |
| §2 Minutes                            | `models/minutes.py`          |
| §3 Attacking rate, §8 between seasons | `models/player_rates.py`     |
| §4 Scoring routes priced              | `models/expected_points.py`  |
| §5 Fixtures change routes             | `backtesting/fixtures.py`    |
| §7b Bookmaker player prices           | `models/market_routes.py`    |
| §7b Evidence and BPS ranking          | `models/market_evidence.py`  |
| §7b Historical BPS residual           | `backtesting/bonus.py`       |
| §11 Team goals                        | `models/dixon_coles.py`      |
| §11 Out-of-position deployment        | `models/deployment.py`       |
| §11b Shot volume and quality          | `models/shot_profile.py`     |
| §11b Penalty exposure                 | `models/penalties.py`        |
| §11b Suspension risk                  | `models/suspensions.py`      |
| §11b Return shape                     | `backtesting/reliability.py` |

Parameters and their provenance: `docs/PARAMETERS.md`. What the model actually
scored: `docs/MODEL_CARDS.md`. The data it scored over: `docs/CORPUS.md`.
