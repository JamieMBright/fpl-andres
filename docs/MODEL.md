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
| MID      | 0.10     | 0.13       |
| FWD      | 0.22     | 0.12       |

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

| Predictor                                 | Spearman  | Top-N accuracy |
| ----------------------------------------- | --------- | -------------- |
| Season minutes                            | 0.616     | 68.7%          |
| Season starts                             | 0.620     | 68.5%          |
| Closing-six minutes                       | 0.605     | 68.9%          |
| Closing-six starts                        | 0.603     | 68.7%          |
| Starts × closing role                     | 0.627     | 70.0%          |
| **Rank blend of season + closing starts** | **0.646** | **70.2%**      |

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

## 12. What this does not calculate

- **Shot locations.** Understat publishes shot coordinates. Nothing reads them,
  so there is no flank vulnerability, no shot-quality decomposition beyond xG,
  and no positional matchup.
- **Non-penalty xG.** FPL's expected goals include penalties, which flatters a
  penalty taker's open-play rate. Understat's `np_xg` is joined and unused.
- **Shot volume and key passes.** Joined from Understat, unused.
- **Why a player is playing.** A stand-in for an injured first choice reads
  exactly like a man who won his place.
- **Squad restructuring.** Transfers are like-for-like by position.
- **Price movement.** Team value follows observed prices; nothing forecasts a
  rise.
- **Posterior carry.** Models refit on decayed history each week rather than
  updating a posterior forward.

---

## 13. How to check any of this

- Rate basis and weights are in `reason_codes` on every `PlayerRateProjection`.
- Every published figure lives in a committed artifact, so a number on the site
  traces to the commit that produced it.
- `python/tests/test_reachability.py` fails the build if any function stops being
  called, so this document cannot quietly describe dead code.
