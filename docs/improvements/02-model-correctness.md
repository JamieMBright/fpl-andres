# Suspected errors in the algorithms

Audit B. Findings that are wrong in the code rather than wrong in the approach.
Each was read out of the source; the four marked **verified** were additionally
confirmed by grep during the audit rather than taken on inspection.

Scores are on the scale in [`IMPROVEMENTS.md`](../../IMPROVEMENTS.md).

---

## B1. The club-change discount can never fire — verified

**Score 9. Do.** `python/fpl_andres/backtesting/rates.py`,
`python/fpl_andres/models/player_rates.py`

`project_element_rates` accepts `team_id`, `prior_team_id` and `prior_position`,
all defaulting to `None`. `_carried_context` uses them to decide whether a
carried season was produced at the same club in the same role, and applies
`evidence.carried_context_weight` (0.6) when it was not.

**No caller ever passes them.** Verified by grep: all three call sites in
`backtesting/projector.py` — lines ~184, ~331 and ~448 — stop at `position`,
`prior_rows` and `prior_season`:

```python
rates = project_element_rates(
    element_id, corpus.season, gameweek, rows, cutoff, config, position
)
```

So `_carried_context` sees `team_id=None` on every observation, returns
`"unknown"`, and the discount branch is unreachable in every production path. A
striker who moved from Liverpool to Bournemouth carries his full Liverpool rate
into the new club at full weight.

The unit tests pass because `test_carried_context.py` constructs
`RateObservation` directly and never goes through the projector. This is the
exact failure mode `test_reachability.py` was built to catch, arriving through a
gap the orphan check cannot see: the function is _called_, it just always takes
the null branch.

**Fix.** Thread `corpus.team_by_element[element_id]`, the prior season's team id
and the prior season's position into all three call sites. Then add a test that
goes _through the projector_, not through the dataclass, and asserts the
discount fires for a transferred player.

**Handoff.** The prior-season team id needs `previous.team_by_element`, which
`project_gameweek` already has in scope as `previous`. `project_horizon` and
`project_next_match` have no prior corpus and should pass the current team id
with `prior_team_id=None`, which correctly yields `"unknown"` rather than a
false `"same"`.

---

## B2. Clean sheets and bonus are the only unshrunk routes — verified

**Score 8. Do.** `python/fpl_andres/backtesting/scoring.py` ~line 168–184

Inside `supporting_breakdown`, every route is shrunk toward a league prior
through a local helper:

```python
def rate(events: float, prior: float) -> float:
    return shrunk_rate(events, nineties_played, prior, prior_nineties)
```

Two routes bypass it:

```python
clean_sheet_rate = sum(row.clean_sheets for row in appearances) / played
...
bonus = ninety * (sum(row.bonus for row in appearances) / played)
```

The saves route three lines below carries the comment _"Shrunk like every other
route"_, which makes the omission look like an oversight rather than a decision.

**Consequence.** A defender with three appearances and two clean sheets is
projected at a 67% clean-sheet rate with no pull toward the league mean. A
player with one 3-bonus in three matches is projected at 1.0 bonus per match
indefinitely. Both errors are largest exactly where the model is used most —
early season and after a transfer, when `played` is small. Clean sheets are 13%
of all points awarded and bonus 6.4%, so this is not a corner.

**Fix.** Route both through `rate()` with a league prior. `league.clean_sheets`
and a bonus-per-90 prior need adding to the `LeagueRates` structure in
`backtesting/rates.py`, which already computes per-position league rates for
every other route.

---

## B3. Double-gameweek minutes are truncated in training but used per fixture

**Score 8. Do.** `python/fpl_andres/backtesting/rates.py` ~line 157,
`python/fpl_andres/models/minutes.py` ~line 52 and ~line 128

Training combines a double gameweek's two rows into one observation and caps it:

```python
combined[row.gameweek] = (min(minutes + row.minutes, 120), ...)
```

`MinutesEvidence.observations` enforces `le=120` and `MinutesProjection`
enforces `expected_minutes <= 120`.

Scoring calls `fixture_points` **once per fixture** and divides by 90:

```python
ninety = minutes.expected_minutes / _MINUTES_PER_90
```

So `expected_minutes` is trained on a per-_event_ basis where doubles are summed
and clipped at 120, then consumed on a per-_fixture_ basis. A nailed 90-minute
player whose history contains doubles trains toward something between 90 and
120 and is then applied to each fixture separately.

**Consequence.** Single-gameweek projections are inflated for any player whose
training window contained a double; double-gameweek projections are
correspondingly wrong in the other direction. Magnitude scales with double
frequency, which is highest in exactly the weeks people plan hardest around.

**Fix.** Keep the two fixtures as separate observations. They already have
distinct kickoff times, so the `(event_id, kickoff_time)` uniqueness constraint
still holds. The 120 cap then means what it says — one match plus extra time.

---

## B4. The yellow-card prior is pooled across positions

**Score 6. Do.** `python/fpl_andres/backtesting/projector.py` ~lines 307–317

```python
league_booking_rate = (
    sum(row.yellow_cards for row in history) / league_matches if league_matches else 0.0
)
booking_rate = (yellows + league_booking_rate * _BOOKING_PRIOR_MATCHES) / (
    played + _BOOKING_PRIOR_MATCHES
)
```

One league booking rate, pooled across defenders and forwards, used as the
shrinkage prior for every player. `_BOOKING_PRIOR_MATCHES = 19.0` — half a
season — so the pull is strong.

Defenders are booked roughly four times as often as forwards. Pooling
over-projects forward bookings and under-projects defender bookings, and the
booking rate feeds the suspension multiplier, which is a live-path input.

Everywhere else in `backtesting/rates.py`, league rates are stored per position
as `Mapping[int, float]`. This one place breaks that convention without saying
why.

---

## B5. `estimate_strength` charges a club for its fixture draw

**Score 7. Do.** `python/fpl_andres/backtesting/fixtures.py` ~lines 92–152

```python
_MIN_MULTIPLIER = 0.4
_MAX_MULTIPLIER = 2.2
_PRIOR_MATCHES = 10.0

def _shrink(scored, matches, league_mean):
    total = scored + league_mean * _PRIOR_MATCHES
    played = matches + _PRIOR_MATCHES
    return _bounded((total / played) / league_mean)
```

Goals scored and conceded, shrunk toward the league mean, with **no opponent
adjustment**. The repo already says so, in the docstring of the _other_ strength
function: "That charges a side for the fixtures it happened to draw: a team who
played the top four early looks leakier than it is."

Two further problems in the same function:

- `_PRIOR_MATCHES = 10.0` means a side ten matches in is shrunk 50/50 toward the
  league mean. Early-season strength differences are largely erased in exactly
  the period where fixture swings decide most transfers.
- The `[0.4, 2.2]` clamp truncates the top of the distribution. A dominant side
  at home is capped, which systematically under-projects premium home captains —
  the exact population the 25-man captaincy shortlist is made of.

This is the function the **backtest** uses (A2). Every published metric inherits
all three problems.

---

## B6. DefCon points are shrunk twice

**Score 6. Do.** `python/fpl_andres/backtesting/scoring.py` ~lines 260–281

```python
rate = shrunk_rate(hits, seen, league.defcon_hits.get(position, 0.0), prior_nineties)
adjusted = min(1.0, rate * adjustment)
coverage = min(1.0, seen / nineties_played) if nineties_played > 0 else 0.0
return ninety * adjusted * _DEFCON_POINTS[position] * coverage
```

`shrunk_rate` already pulls a thin sample toward the league mean — that is what
shrinkage is for. The `coverage` term then multiplies again by the fraction of
the player's minutes for which the column exists.

Because `defensive_contribution` is null before 2025/26, a veteran with 500 of
his 3,000 corpus minutes in 2025/26 has his DefCon points scaled by 1/6 _on top
of_ being shrunk for having only 500 minutes of evidence. The same missing data
is charged twice.

DefCon is 7.5% of all points awarded. The players most affected are established
defenders — the ones whose DefCon record is best established.

**Fix.** Pick one. Shrinkage toward the league rate already encodes "we do not
have much evidence"; `coverage` is the redundant term.

---

## B7. `_form` silently returns the projection's pick

**Score 5. Owner decision.** `python/fpl_andres/backtesting/captain_policies.py`
~lines 159–176

```python
eligible = [entry for entry in candidates
            if entry.recent_points is not None and entry.recent_points >= FORM_FLOOR]
if not eligible:
    return _expected_points(candidates)
```

When nobody on the shortlist clears the 2.0 floor, `form` returns exactly what
`expected_points` returns. In those weeks the two policies are identical by
construction, and the paired difference between them is exactly zero.

This is defensible behaviour — a rule has to pick somebody. But it means the
reported `form` mean is a blend of "form's picks" and "the projection's picks",
and the paired-bootstrap interval is narrowed by the tied weeks. `form` measured
at −1.57 against the projection is therefore an _understatement_ of how badly
pure form does.

**Fix.** Count and publish the fallback weeks. If the count is material, report
`form` twice: as-specified, and restricted to weeks where it had an opinion.

---

## B8. A doubtful player with a zero chance of playing is not marked unavailable

**Score 5. Do.** `python/fpl_andres/models/minutes.py` ~lines 225–234

A player with `status="d"` and `chance_of_playing=0` has every probability
scaled to zero, and then:

```python
evidence_level = "inferred"
```

`project_gameweek` filters on `evidence_level == "unavailable"`, so this player
is _not_ filtered. He reaches the projection, the ranking and the captaincy
candidate list carrying zero expected points and an `inferred` evidence chip.

Arithmetically harmless — zero times anything is zero. Semantically wrong: the
site will show a ruled-out player with an evidence level that says the model has
an opinion about him.

---

## B9. Missing recent minutes are read as zero, so new signings get dumped

**Score 5. Do.** `python/fpl_andres/simulation/minileague_policies.py` ~line 107

```python
outgoing = [player for player in manager.squad if minutes.get(player.element_id, 0) == 0]
```

A player absent from the three-gameweek minutes window returns `0` from the
default, and the zombie-clearing policy treats him as inactive. A new signing
who has not yet appeared is indistinguishable from an injured player who has
stopped appearing, and gets sold.

`.get(key, 0)` where absence is meaningful. The distinction the repo makes
everywhere else — refuse rather than default — is not made here.

---

## B10. `_best_replacement` can trigger on a player with no ranking

**Score 4. Do.** `python/fpl_andres/simulation/minileague_policies.py` ~lines 135–162

`current = ranking.get(outgoing)` falls back to `0.0`. The eligibility test then
becomes `score <= 0`, which any ranked candidate passes, so the first affordable
candidate is returned regardless of whether the swap is an improvement.

Triggers whenever the outgoing player is missing from the ranking — a new
signing, or a position edge case. The result is a full-price transfer with no
measured gain.

---

## B11. The Dixon-Coles barrier has a hundredfold gradient discontinuity

**Score 4. Owner decision.** `python/fpl_andres/models/dixon_coles.py` ~lines 133–148

```python
if adjustment <= _MINIMUM_ADJUSTMENT:
    log_adjustment = math.log(_MINIMUM_ADJUSTMENT) - _BARRIER_SLOPE * (_MINIMUM_ADJUSTMENT - adjustment)
else:
    log_adjustment = math.log(adjustment)
```

At the join, `d/dx log(x)` is `1/1e-6 = 1e6` from above and `_BARRIER_SLOPE = 1e4`
from below — a factor of 100. L-BFGS-B assumes a continuous gradient; a kink
this large can produce spurious line-search rejections.

In practice the optimiser rarely visits the region, so this is a latent rather
than an active fault. The comment says "sign and scale matter" without saying
what the scale should be; `_BARRIER_SLOPE = 1 / _MINIMUM_ADJUSTMENT` would make
it C¹.

---

## B12. `predict` refuses events above 38 although `MAX_EVENT` is 47

**Score 3. Do.** `python/fpl_andres/models/dixon_coles.py` ~lines 253–255

`MAX_EVENT = 47` exists because 2019-20 ran to 47 events after the shutdown.
`DixonColesModel.predict` validates `1 <= event <= 38` and raises otherwise —
and `event` is metadata that does not affect the prediction.

Fitting on a 47-event season is allowed; predicting inside it is refused. No
current caller hits this, so it is a latent trap rather than a live bug.

---

## B13. Conditional minutes probabilities default to certainty

**Score 5. Do.** `python/fpl_andres/models/minutes.py` ~lines 206–217

```python
probability_sixty_given_start = _weighted_share(
    starts, weights, lambda o: o.minutes >= _APPEARANCE_POINT_THRESHOLD, default=1.0
)
```

A player with no observed starts is assigned `P(60 | start) = 1.0` — if he
starts, he will certainly play an hour. The mirrored default,
`P(cameo | benched) = 0.0`, says a player with no benched observations will
certainly not appear off the bench.

Both are unshrunk, unlike `probability_start` which is properly Beta-Binomial
shrunk. So the marginal is regularised and the conditionals are not, and
`P(60+) = P(start) × P(60|start)` inherits the unregularised term.

**Fix.** Shrink the conditionals toward their league rates, which are well below
1.0 and well above 0.0 respectively.

---

## B14. Blank and injured gameweeks are treated asymmetrically in recent form

**Score 4. Owner decision.** `python/fpl_andres/backtesting/projector.py` ~line 597

`baseline_recent_mean` iterates `corpus.actual_points(event)`, which returns
nothing for a player whose club blanked. Those weeks leave both numerator and
denominator. An injured player, by contrast, has a zero-minute row and _is_
returned, so his zero drags the mean down.

Two players equally absent are projected very differently: the blanked one is
unaffected, the injured one is penalised. Arguably correct — a blank says
nothing about the player and an injury does — but it is nowhere stated, and it
makes recent form partly a measure of fixture luck.

---

## B15. Synthetic kickoff timestamps rooted in the year 2000

**Score 4. Do.** `python/fpl_andres/backtesting/corpus.py` ~line 347

Where a kickoff time is missing, the corpus substitutes
`datetime(2000, 1, 1) + timedelta(days=7 * gameweek)`.

The _ordering_ is preserved, which is what the leak guards need, so nothing is
currently wrong. But `data_available_at` derived from such a cutoff is a real
field on a published artifact, and it will read as the year 2000. Any consumer
treating it as a timestamp rather than as an ordering gets a fabricated date
with no signal that it is synthetic.

**Fix.** Carry a `synthetic: bool` alongside, or refuse. Refusing is more in
keeping with the rest of the project.

---

## B16. Things checked and found correct

Recorded so a later reader knows they were covered rather than missed.

- **The paired bootstrap is correctly paired.** `models/promotion.py` resamples
  one index vector and applies it to baseline, candidate and observed alike.
  (The percentile-versus-BCa question is A6, a different issue.)
- **`_quantile` interpolates correctly.** The previous `ceil(f·n) − 1` indexing
  bias is fixed and documented.
- **Shin and power de-vigging are correct.** Both bisections are on monotone
  functions and converge; the formulae match the literature.
- **`estimate_strength` does not leak.** Every projector path calls
  `corpus.fixtures_before(gameweek)`. The problem with that function is bias
  (B5), not leakage.
- **Double gameweeks are handled correctly at fixture level.** `_adjustments_for`
  iterates fixtures, and `corpus.actual_points` sums across them. The minutes
  layer is where doubles break (B3).
- **Blank gameweeks correctly produce zero** in `project_horizon` and
  `project_gameweek`, and blanked players are correctly excluded from the
  captaincy shortlist.
- **Tie-breaks are consistent.** `_pick` and `_highest` both break on `-element_id`.
- **The venue tilt shrinkage is well formed**, with a documented one-season prior.
- **The Poisson log-factorial uses `lgamma`**, which is the right call.
