# Improvement audit

A full-repository audit taken after model `2.5`. Every entry was found by
reading the code or by measuring, not by pattern-matching against a checklist of
generic advice. Where a finding was additionally confirmed by grep or by a live
network probe during the audit it is marked **verified**.

This replaces the previous 204-item audit, which is in the git history.

**The old numbering still resolves.** One hundred and twenty-five comments
across the codebase cite it — `# Audit item #67`, `Audit item #202` — as the
reason a piece of code exists. Those citations are provenance and are worth more
than the consistency of renumbering them, so the old audit is not gone: it is at
commit `4cb3730`, readable with

```
git show 4cb3730:IMPROVEMENTS.md
git show 4cb3730:docs/improvements/01-correctness-and-modelling.md
```

Items in this audit are lettered rather than numbered, so the two schemes cannot
be confused.

Nothing here overrides [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md). Where an
item touches a controlling FPL rule or a sourced parameter, the fix must still
fail the source contract visibly rather than default a value.

## How items are scored

The score is **value only**. Implementation effort is deliberately excluded: it
is not a constraint here, so including it would only smuggle a second axis into
a number meant to answer one question — _does this matter?_

| Score | Meaning                                                                                                          |
| ----- | ---------------------------------------------------------------------------------------------------------------- |
| 9–10  | A published number is wrong, or the thing being optimised is the wrong thing. Everything downstream inherits it. |
| 7–8   | A model input is biased, or a real decision is made on evidence that does not support it.                        |
| 5–6   | A defensible choice that is probably wrong, or a correct thing that nothing can reach.                           |
| 3–4   | Latent: wrong in principle, currently harmless. Fix before it is load-bearing.                                   |
| 1–2   | Recorded so it is not rediscovered. Acting on it would be waste.                                                 |

## Verdicts

- **Do** — the finding stands and the work is worth doing.
- **Owner decision** — the finding stands; whether to act depends on a
  preference or a cost only the owner can weigh.
- **Don't** — recorded deliberately. Acting would be waste, or would make things
  worse. The reason is written down so it is not relitigated.

## The four that change what the site is allowed to claim

If nothing else is done, these four. Each one means a currently published number
does not mean what the page says it means.

1. **[A2](docs/improvements/01-methodology.md)** — the backtest grades a
   different model from the one that ships. Four of six pipeline stages differ.
   Every metric on the calibration page describes a projection no user receives.
2. **[A1](docs/improvements/01-methodology.md)** — the objective is expected
   points; the game is rank. The module that fixes this already exists and is
   orphaned.
3. **[A4](docs/improvements/01-methodology.md)** — every tuning constant was
   chosen by someone who had seen all four scored seasons. There is no holdout.
4. **[B1](docs/improvements/02-model-correctness.md)** — **verified** — the
   club-change rate discount is unreachable from every production path. A
   transferred player carries his old club's rate at full weight.

---

## A. The methodology

Full detail: [`docs/improvements/01-methodology.md`](docs/improvements/01-methodology.md)

| #   | Score | Verdict        | Finding                                                                                                                                                                                                                                             |
| --- | ----- | -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A1  | 10    | Do             | The objective is expected points; FPL is a rank game. `planning/effective.py` solves this and is orphaned. The "+16 points a season" that justified shelving it was measured in a 20-manager league, which has no rank distribution to be aware of. |
| A2  | 10    | Do             | Backtest and live differ on team strength, form blend, suspensions and fixture adjustment. Every published metric measures a model that never ships.                                                                                                |
| A3  | 9     | Do             | Player-to-player correlation is never modelled. Two defenders at one club share a clean sheet. `upside` and `robust` are scored on a σ with no covariance term, so neither measures its own thesis.                                                 |
| A4  | 9     | Do             | No held-out season. Half-lives, priors, clamps, blend weight, shortlist size and the ownership coefficient were all chosen against the four seasons they are scored on.                                                                             |
| A5  | 8     | **Done**       | Ten captaincy comparisons, no multiplicity correction. Family-wise error near 40%. Fixed: every interval is widened by the family size, and the size is published so the page can say how many comparisons were made.                               |
| A9  | 8     | Do             | Captaincy is a right-tail bet priced with a point estimate. `ceiling_ratio` is a proxy for a predictive distribution that does not exist.                                                                                                           |
| A11 | 8     | Do             | Transfers are authorised on one gameweek's gain against a four-point hit. `project_horizon` exists and the transfer policy does not call it.                                                                                                        |
| A7  | 7     | Do             | Pooled rank correlation over 600 players is not a decision anybody makes. Top-of-pool precision under a budget constraint would be.                                                                                                                 |
| A10 | 7     | Do             | The 25-most-owned shortlist makes `differential` choose among the most-owned players in the game. Two policies are reported under names they were not tested as.                                                                                    |
| A12 | 7     | Do             | Team value is not modelled, and it compounds across a 38-week plan. Realised price changes are in the corpus already; forecasting them is not required.                                                                                             |
| A6  | 6     | Owner decision | The percentile bootstrap under-covers on skewed paired differences. BCa is correct. Current conclusions are not close enough to the boundary for it to change them.                                                                                 |
| A13 | 6     | Owner decision | Chips are chosen by fixture count. Worth 80–150 points a season. Downstream of A9 — do not start here.                                                                                                                                              |
| A15 | 6     | Do             | The prose is better than the evidence, and hardcoded numbers in `Methodology.tsx` will drift from the artifact beside them.                                                                                                                         |
| A8  | 5     | **Part done**  | The mini-league baselines are weak. Fixed for captaincy: set_and_forget commits to the most-owned player at the first scored gameweek and never revisits it. The mini-league transfer baselines are untouched.                                      |
| A14 | 4     | Owner decision | "Share of ceiling" uses a hindsight ceiling, so it reads as failure by construction. Split skill from variance.                                                                                                                                     |
| A16 | —     | Don't          | What is genuinely good and should not be touched: the reconciliation, fail-closed on missing rules, the orphan ratchet, recording negative results, the evidence-level system.                                                                      |

## B. Errors in the algorithms

Full detail: [`docs/improvements/02-model-correctness.md`](docs/improvements/02-model-correctness.md)

| #   | Score | Verdict        | Finding                                                                                                                                                                                                                                                       |
| --- | ----- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| B1  | 9     | **Done**       | **Verified.** No caller passed eam_id to project_element_rates, so the 0.6 club-change discount was unreachable. Fixed: club and role are threaded through all three projector call sites, with a test that goes through the projector rather than around it. |
| B2  | 8     | **Done**       | **Verified.** clean_sheet_rate and onus were the only unshrunk routes in supporting_breakdown. Fixed: both are shrunk toward a measured per-appearance league rate, like every other route.                                                                   |
| B3  | 8     | Do             | Double-gameweek minutes are summed and capped at 120 in training, then consumed per fixture at scoring time. Single-gameweek projections inflate for anyone whose history contains a double.                                                                  |
| B5  | 7     | Do             | `estimate_strength` has no opponent adjustment, shrinks 50/50 at ten matches, and clamps to `[0.4, 2.2]` — truncating exactly the premium home captains the shortlist is made of. This is the function the backtest uses.                                     |
| B4  | 6     | Do             | The yellow-card shrinkage prior is pooled across positions, then applied to every player with a half-season weight. Defenders are booked about four times as often as forwards.                                                                               |
| B6  | 6     | Do             | DefCon is shrunk toward the league rate and then multiplied by a coverage fraction. The same missing data is charged twice, hardest against established defenders.                                                                                            |
| B7  | 5     | Owner decision | `_form` falls back to `_expected_points` when nobody clears the floor, so the two are identical by construction in those weeks and the measured gap understates pure form's cost.                                                                             |
| B8  | 5     | Do             | A doubtful player with `chance_of_playing = 0` is labelled `inferred`, not `unavailable`, so he is not filtered and reaches the site with an evidence chip claiming an opinion.                                                                               |
| B9  | 5     | Do             | `minutes.get(id, 0)` makes a new signing indistinguishable from an injured player, and the zombie policy sells him.                                                                                                                                           |
| B13 | 5     | Do             | `P(60 given start)` defaults to 1.0 and `P(cameo given benched)` to 0.0, both unshrunk, while the marginal they multiply is properly shrunk.                                                                                                                  |
| B10 | 4     | Do             | `_best_replacement` falls back to `0.0` for an unranked outgoing player, so any ranked candidate passes the improvement test.                                                                                                                                 |
| B11 | 4     | Owner decision | The Dixon-Coles barrier has a hundredfold gradient discontinuity at the join. Latent — the optimiser rarely visits the region.                                                                                                                                |
| B14 | 4     | Owner decision | Blank gameweeks leave recent form untouched; injuries drag it to zero. Defensible, undocumented, and it makes recent form partly a measure of fixture luck.                                                                                                   |
| B15 | 4     | Do             | Missing kickoffs become `datetime(2000, 1, 1) + 7 days × gameweek`. Ordering is preserved but `data_available_at` ships as a fabricated date with no marker.                                                                                                  |
| B12 | 3     | Do             | `DixonColesModel.predict` refuses events above 38 while `MAX_EVENT` is 47, on a parameter that does not affect the prediction.                                                                                                                                |
| B16 | —     | Don't          | Checked and correct: the bootstrap is properly paired, `_quantile` interpolates correctly, Shin and power de-vigging are right, `estimate_strength` does not leak, doubles and blanks are right at fixture level, tie-breaks are consistent.                  |

## C. Built and not wired

Full detail: [`docs/improvements/03-unwired-and-incomplete.md`](docs/improvements/03-unwired-and-incomplete.md)

| #   | Score | Verdict        | Finding                                                                                                                                                                                                                             |
| --- | ----- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| C1  | 10    | Do             | `RankModel`, `effective_points`, `swing_risk`, `effective_ownership` — the whole treatment of the real objective — complete, tested, called by nothing.                                                                             |
| C4  | 8     | Do             | The horizon MILP runs once, offline, for a squad nobody owns. The backtest uses greedy; the site uses a beam search. `test_horizon_scale.py` already retired the tractability objection.                                            |
| C3  | 7     | Do             | Sixteen CLI entry points have no schedule and no runbook entry. Nine of them generate the site's committed artifacts.                                                                                                               |
| C5  | 7     | Do             | The beam search ships at `beamWidth: 12`; regret is only measured at 16, on three fixtures of 4, 6 and 22 elements. Real solves see 500+ players and set `bounded_search_truncated` every time.                                     |
| C7  | 7     | Do             | The starts blend scores 0.646 against minutes' 0.616, winning five of six season pairs, and is not wired. No reason recorded.                                                                                                       |
| C2  | 6     | Do — per table | Six tables with forced RLS, immutability triggers and no writer. Two should be filled, two depend on C4, two are candidates for deletion.                                                                                           |
| C6  | 6     | Do             | `plan_transfers` and `premium_is_justified` are complete and unreachable while the site's transfer panel refuses for lack of them.                                                                                                  |
| C8  | 6     | Owner decision | Understat volume and quality shrinkage measured 3.4% better on MAE, deferred with no recorded reason. Only ~56% of the pool joins the crosswalk.                                                                                    |
| C9  | 6     | Owner decision | Chips picked from fixture counts; the solver refuses them at the schema layer. Downstream of A9.                                                                                                                                    |
| C12 | 3     | Owner decision | Retention policies are documented and unautomated. The reasoning is sound today and expires on a size nothing measures.                                                                                                             |
| C11 | 3     | Don't          | `project_expected_points` should not be wired as a competitor to the projector, which reconciles to one point in 34,383. Mine it for the A9 distribution instead.                                                                   |
| C10 | 2     | Don't          | Blocked outside the repo: StatsBomb, FPL Review (`robots.txt` refuses), FPL Kiwi (domain gone), Championship minutes, OOP data, historical manager journeys, cohort persistence. Keep the harnesses; do not work around the blocks. |

## D. Data and sources

Full detail: [`docs/improvements/04-data-and-sources.md`](docs/improvements/04-data-and-sources.md)

| #   | Score | Verdict | Finding                                                                                                                                                                                                                                                                                                                     |
| --- | ----- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | 9     | Do      | **Verified 2026-08-06.** Odds hosts are blocked by a _local_ content filter, not by the hosts. CI runs on GitHub's runners, which are not. The repo already uses that exact pattern for the backtest and never applied it here. Historical closing odds are free and answer whether a paid live feed would be worth buying. |
| D2  | 8     | Do      | The daily contract test never checks `elements`, the array the whole site reads. A rename degrades every visitor, and the canary is designed not to alarm on `degraded`.                                                                                                                                                    |
| D3  | 8     | Do      | No backup automation and no restore procedure. `crowd_snapshots` is captured from a live endpoint that publishes only the present — every lost row is permanent.                                                                                                                                                            |
| D4  | 6     | Do      | Ownership captures land in a gitignored file while the table built for them has no writer. This is the series A12 needs.                                                                                                                                                                                                    |
| D5  | 5     | Do      | The corpus is mutable and `fingerprint` exists, but nothing compares fingerprints across runs. A silent re-ingest would present as a model change.                                                                                                                                                                          |
| D6  | 1     | Don't   | Season-vintage handling is subtle and correct. Recorded so it is not "simplified" away.                                                                                                                                                                                                                                     |

## E. Platform, frontend, testing, operations

Full detail: [`docs/improvements/05-platform-and-testing.md`](docs/improvements/05-platform-and-testing.md)

| #   | Score | Verdict        | Finding                                                                                                                                                                                                                      |
| --- | ----- | -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| E2  | 8     | Do             | Five blocks of hardcoded numbers in `Methodology.tsx`, including intervals written by hand an hour after CI produced them. This is the exact failure `validation-verdict.ts` exists to prevent.                              |
| E1  | 7     | Do             | The rate limiter is per-instance in memory, so the global ceiling scales with warm instances — it grows with the load it defends against.                                                                                    |
| E3  | 7     | Do             | `/plan` and `/analysis` have contrast and responsive scans only. `/kits` has none. The 38-week beam-search plan has no functional browser test.                                                                              |
| E7  | 5     | Do             | Property tests cover five files. `bootstrap.py`, `team_state.py`, `optimization/contracts.py` and `persistence/supabase.py` have neither property nor mutation coverage.                                                     |
| E5  | 4     | Do             | Two sequential 12-second budgets against a 15-second function cap turn a slow upstream into a platform timeout instead of a degraded envelope.                                                                               |
| E4  | 3     | Do             | Corrupt localStorage is swallowed without clearing the key, inconsistent with the three other readers.                                                                                                                       |
| E6  | 3     | Owner decision | The error boundary renders `error.message` to the page. Not a security hole; a judgement about exposing internal structure.                                                                                                  |
| E8  | —     | Don't          | Checked and sound: the FPL proxy allow-list and SSRF defences, secret handling, error responses, both gitleaks allowlists, retry and caching, no float-equality bugs, no tautological tests, nothing excluded from coverage. |

---

## Suggested order

Dependencies, not priorities. Several of these are worth nothing until the one
above them is done.

1. **B1, B2, B3** — verified errors in the model's inputs. Isolated, and every
   number downstream is measured on top of them.
2. **A2** — one projection path. Until the backtest grades what ships, no
   measurement taken before or after this is comparable to any other.
3. **A4** — declare the holdout before doing anything that tunes a constant, or
   the holdout is already spent.
4. **A5** — multiplicity. Two lines, and it protects every comparison added
   later.
5. **A3 → A9 → A13/C9** — covariance, then a predictive distribution, then
   chips. In that order: chips optimised against point estimates would be
   optimising the wrong object.
6. **A1/C1** — the rank objective, once there is a distribution to compute it
   over.
7. **D1** — bookmaker priors, as an external check on the strength model that
   A2 will have just unified.
8. **D2, D3** — the two operational findings that turn a bad day into a bad
   week.

## Working an item

Each entry in `docs/improvements/` carries the file paths, the quoted code, why
it is wrong, what the consequence is, and where a fix has to start. An agent
picking up a single item should not need to re-derive context from this index or
from the rest of the repository.

Two rules apply to every item without exception:

- A failing focused test first, then the minimal code, then the refactor.
- Where a controlling FPL rule or a sourced parameter is missing, fail its
  source contract visibly. Never default it.
