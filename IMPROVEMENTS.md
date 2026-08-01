# Improvement audit

A full-repository audit taken at `v0.5.1`. Every entry is a candidate improvement
found by reading the code, not a generic recommendation. Items are grouped by
category and ordered by impact within each category (High, then Medium, then Low).

Nothing here overrides [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md). Where an item
touches a controlling FPL rule or a sourced parameter, the fix must still fail the
source contract visibly rather than default a value.

Impact key: **H** high, **M** medium, **L** low.

Contents:

1. [Correctness and modelling](#1-correctness-and-modelling)
2. [Numerical and statistical rigour](#2-numerical-and-statistical-rigour)
3. [Python performance and scalability](#3-python-performance-and-scalability)
4. [Ingestion, adapters and network robustness](#4-ingestion-adapters-and-network-robustness)
5. [Persistence, idempotency and data integrity](#5-persistence-idempotency-and-data-integrity)
6. [Security and secret handling](#6-security-and-secret-handling)
7. [API and serverless functions](#7-api-and-serverless-functions)
8. [Database schema and migrations](#8-database-schema-and-migrations)
9. [Frontend architecture and performance](#9-frontend-architecture-and-performance)
10. [Frontend accessibility, UX and SEO](#10-frontend-accessibility-ux-and-seo)
11. [Contracts, typing and API surface](#11-contracts-typing-and-api-surface)
12. [Testing and reproducibility](#12-testing-and-reproducibility)
13. [CI/CD, tooling and developer experience](#13-cicd-tooling-and-developer-experience)
14. [Documentation and governance](#14-documentation-and-governance)

---

## 1. Correctness and modelling

| #   | Impact | Improvement                                                                                                                                                                                                                                                         |
| --- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | H      | Treat a zero-free-transfer request as a first-class state in `optimization/contracts.py` (~line 188). Zero is accepted at validation but every downstream transfer constraint then depends on hit-taking; the infeasible-versus-hit distinction should be explicit. |
| 2   | H      | Centralise the UTC-awareness guard. `_require_utc`-style checks (`tzinfo is None or utcoffset() != timedelta(0)`) are re-implemented in `contracts.py`, `rules.py`, `models/*` and `team_state.py`; one shared validator removes drift between the copies.          |
| 3   | H      | Validate that gameweeks in a backtest corpus form the expected contiguous set (`backtesting/corpus.py`). A silently missing gameweek changes every aggregate metric without any signal to the caller.                                                               |
| 4   | H      | Cross-validate sourced parameters against each other in `models/player_rates.py` (~lines 86–92): `blend_full_weight_minutes` must exceed `minimum_minutes`, otherwise the blend weight saturates immediately.                                                       |
| 5   | H      | Guard `None` before the `data_available_at > fetched_at` comparison in `contracts.py` (~lines 34–43) so a missing timestamp fails with a contract error rather than a `TypeError`.                                                                                  |
| 6   | M      | Reject observation sequences that are unsorted or contain duplicate event ids in `models/player_rates.py` and `models/minutes.py`; both assume monotonic event ordering when applying recency decay.                                                                |
| 7   | M      | Validate that every `team_id` referenced by an optimisation request exists in the rules snapshot (`optimization/contracts.py` ~lines 173–182); today an unknown club silently escapes the three-per-club constraint.                                                |
| 8   | M      | Make `FutureMinutesEvidenceError` (`models/minutes.py`) part of a documented public error taxonomy; no caller currently handles it, so a leakage guard surfaces as an unhandled traceback in a workflow run.                                                        |
| 9   | M      | Deduplicate the evidence-level ordering constant (`_EVIDENCE_ORDER`) now repeated across `models/expected_points.py`, `models/player_rates.py` and `models/minutes.py`; a single source prevents divergent downgrade rules.                                         |
| 10  | M      | Deduplicate position-name mappings between `models/deployment.py` and `backtesting/score.py`; two literal maps of the same FPL rule is a silent-divergence hazard.                                                                                                  |
| 11  | M      | Make `_BENCH_WEIGHT` (`simulation/season.py`) and `PLAYABLE_START_RATE` (`planning/opening.py`) injectable sourced parameters rather than module constants, so alternatives can be evaluated without editing code.                                                  |
| 12  | M      | Extract sub-problems from `HighsHorizonOptimizer.solve` (`optimization/horizon.py`, ~200 lines of nested indexing) into named builders so constraint blocks can be unit tested individually.                                                                        |
| 13  | M      | Split `backtesting/projector.py` (882 lines) along its natural seams (feature assembly, projection, scoring) — it is the largest module in the repository and the hardest to review.                                                                                |
| 14  | L      | Replace the `Literal` position codes in `models/deployment.py` with an enum so positions can be iterated exhaustively and matched with static checking.                                                                                                             |
| 15  | L      | Name the tie-break coefficients in `optimization/highs.py` (~lines 202–206: `1e-9`, `1e-11`, `1e-13`) and document the lexicographic ordering they encode.                                                                                                          |
| 16  | L      | Document `_optimum_slack` in `optimization/highs.py` (~lines 28–30); the relative-plus-absolute tolerance is load-bearing for every optimality proof but uncommented.                                                                                               |
| 17  | L      | Rename the mixed `*_offset` / `*_index` variables in `optimization/highs.py` (~lines 42–46) so column offsets and variable indices are not conflated.                                                                                                               |
| 18  | L      | Standardise validation message wording in `rules.py` (~lines 418–441) — "must be an integer" and "must be numeric" describe the same class of failure differently.                                                                                                  |

## 2. Numerical and statistical rigour

| #   | Impact | Improvement                                                                                                                                                                                                                   |
| --- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 19  | H      | Replace the `1e12` penalty return in `models/dixon_coles.py` (~lines 97–98) with an explicit infeasibility signal; feeding a sentinel into the optimiser objective distorts the search surface near the boundary.             |
| 20  | H      | Compute bootstrap confidence bounds with an explicit quantile function in `models/promotion.py` (~lines 204–205); the current `ceil(...) - 1` indexing biases the upper bound at small resample counts.                       |
| 21  | H      | Justify or source the Poisson truncation limit in `models/expected_points.py` (~lines 256–260). A fixed cut of 15 discards tail mass for high-rate scenarios and is currently a bare constant.                                |
| 22  | H      | Fail loudly when recency decay underflows to zero in `models/minutes.py` (~line 170); an observation far from the prediction event silently contributes nothing instead of being rejected as out of window.                   |
| 23  | M      | Clamp the normal CDF output in `planning/effective.py` (~line 56); `erf(z / sqrt(2))` can exceed 1 by a float epsilon and produce an effective rank below 1.                                                                  |
| 24  | M      | Handle the degenerate-variance case in rank correlation explicitly (`models/backtest.py` ~lines 222–230); constant prediction and outcome vectors currently return "no correlation" rather than an explicit undefined result. |
| 25  | M      | Weight or report the top-N hit rate when an event has fewer than N scored players (`models/backtest.py` ~lines 247–248); silently skipping short events biases the aggregate towards well-covered gameweeks.                  |
| 26  | M      | Document and test the shrinkage boundary in `models/player_rates.py` (~lines 242–248) where observed minutes are zero and the estimate collapses to the prior.                                                                |
| 27  | M      | Validate the beta-binomial prior strength bounds in `models/minutes.py` (~lines 194–197) so an extreme sourced value fails its contract instead of quietly dominating every posterior.                                        |
| 28  | M      | Model rival-ownership covariance in `planning/effective.py` (~lines 77–90); swing, cover and upside are currently treated as independent, which understates variance in a correlated field.                                   |
| 29  | M      | Carry evidence quality, not only minutes, into the cross-season blend weight in `models/player_rates.py` (~lines 165–175); carried observations from a different club or role deserve a discount.                             |
| 30  | M      | Support multi-seed bootstrap aggregation in `models/promotion.py` (~line 97) so a promotion decision is not conditional on one seed.                                                                                          |
| 31  | L      | Centralise the NaN/validity handling for Spearman correlation duplicated between `models/backtest.py` and `backtesting/score.py`.                                                                                             |
| 32  | L      | Require consistent presence of optional inputs (for example expected goals) across an observation set in `models/player_rates.py` (~lines 220–235) rather than substituting `0.0` for a missing value.                        |

## 3. Python performance and scalability

| #   | Impact | Improvement                                                                                                                                                                   |
| --- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 33  | M      | Pre-sort event outcomes once instead of re-sorting per event in `models/backtest.py` (~lines 250–261); the repeated sorts dominate scoring across a full multi-season corpus. |
| 34  | M      | Build the HiGHS constraint matrix sparsely in `optimization/highs.py` (~lines 97–121); per-position dense construction grows with the whole player pool.                      |
| 35  | M      | Cache the player index and forecast dictionaries in `optimization/horizon.py` (~lines 25–37); they are rebuilt on every solve during a re-planning sweep.                     |
| 36  | M      | Cap crosswalk candidate generation in `crosswalk/resolve.py` (~lines 147–156); shared surnames make the candidate set grow quadratically with no bound.                       |
| 37  | L      | Hoist the decay-weight computation out of the per-observation loop in `models/minutes.py` (~lines 168–172).                                                                   |
| 38  | L      | Replace per-player dictionary lookups with a single pre-join in `optimization/highs.py` (~lines 123–149).                                                                     |
| 39  | L      | Extract the shared constraint-building loops in `optimization/highs.py` and `optimization/horizon.py` into one helper to keep the two solvers behaviourally identical.        |
| 40  | L      | Split `simulation/minileague.py` (813 lines) so the season loop, rival policies and scoring are independently profilable.                                                     |

## 4. Ingestion, adapters and network robustness

| #   | Impact | Improvement                                                                                                                                                                                          |
| --- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 41  | H      | Add a bounded, capped backoff for transport errors in `adapters/fpl.py` (~lines 239–244) so repeated connection failures cannot compound into long unattended waits inside a scheduled workflow.     |
| 42  | H      | Add a circuit breaker or fast-fail after repeated upstream 5xx responses in `adapters/fpl.py` (~lines 224–255); a sweeping job should stop hammering a dead endpoint.                                |
| 43  | H      | Replace the bare `except Exception` in `cli/ingest_historical.py` (~line 176) with typed handling so schema, network and validation failures are distinguishable.                                    |
| 44  | H      | Wrap numeric conversions in `ingest/normalise.py` with explicit parse errors; an archive column that changes type currently raises deep in the pipeline or coerces silently.                         |
| 45  | H      | Guarantee client cleanup with `try`/`finally` or a context manager in `cli/verify_veterans.py` (~line 55) and the JSONL append in `cli/sweep_managers.py` (~line 148); both leak handles on failure. |
| 46  | M      | Unify HTTP timeouts across modules — 30s in `persistence/supabase.py` (~line 81) versus 60s in `cli/ingest_historical.py` (~line 142) — and source them from one config object.                      |
| 47  | M      | Honour FPL rate-limit response headers in `adapters/fpl.py` rather than inferring throttle parameters from refusal counts.                                                                           |
| 48  | M      | Add conditional-request support (ETag / `If-Modified-Since`) for bootstrap in `adapters/fpl.py` (~line 77); bootstrap is stable within a gameweek and is currently refetched per command.            |
| 49  | M      | Configure explicit connection pooling and reuse a single client across a CLI run (`cli/sweep_managers.py` ~line 143, `cli/verify_veterans.py` ~line 55).                                             |
| 50  | M      | Drain or discard the response body deterministically when the size limit trips in `adapters/fpl.py` (~lines 200–209) so the connection is returned cleanly to the pool.                              |
| 51  | M      | Ensure the sweep semaphore is released on inner-task failure in `cli/sweep_managers.py` (~line 159) to remove the stall risk under repeated errors.                                                  |
| 52  | M      | Validate requested gameweeks against archive availability in `cli/ingest_historical.py` (~lines 45–65) instead of skipping unavailable ones silently.                                                |
| 53  | M      | Include season, gameweek and file in `ArchiveFileNotPublished` context (`ingest/historical.py` ~lines 135–137) so a partial ingest is diagnosable from logs alone.                                   |
| 54  | M      | Validate archive column types and detect duplicate or reordered headers in `ingest/normalise.py` (~lines 30–95), not just column presence.                                                           |
| 55  | L      | Handle malformed-JSON `ValueError` consistently across CLI tools; only `cli/sweep_managers.py` (~line 119) currently guards it.                                                                      |
| 56  | L      | Preserve all transport errors, not only the last, when re-raising in `adapters/fpl.py` (~line 254).                                                                                                  |
| 57  | L      | Mark truncation explicitly in `_safe_detail` (`persistence/supabase.py` ~line 226) so a clipped upstream message is not mistaken for the whole message.                                              |

## 5. Persistence, idempotency and data integrity

| #   | Impact | Improvement                                                                                                                                                                                   |
| --- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 58  | H      | Validate that every `on_conflict` column is present in the payload before an upsert in `persistence/supabase.py` (~lines 144–158); a mismatch turns an update into a silent duplicate insert. |
| 59  | H      | Make multi-table season ingest atomic or resumable in `ingest/historical.py` (~lines 104–151); teams, elements, fixtures and stats are written as independent requests with no rollback.      |
| 60  | H      | Retry transient Supabase 5xx writes with backoff in `persistence/supabase.py` (~lines 130–139); today a single blip fails an entire scheduled run.                                            |
| 61  | H      | Write sweep checkpoints atomically (temp file plus rename) in `cli/sweep_managers.py` (~lines 86–88) so a crash mid-write cannot corrupt resume state.                                        |
| 62  | M      | Hash the idempotency key inputs in `persistence/workflow.py` (~line 102) instead of concatenating strings, removing separator-collision risk.                                                 |
| 63  | M      | Detect duplicate workflow runs from the PostgREST error code rather than matching the phrase "duplicate key" (`persistence/workflow.py` ~lines 62–66).                                        |
| 64  | M      | Size upsert batches by serialised payload bytes as well as row count in `persistence/supabase.py` (~lines 22, 129–134) to avoid payload-too-large failures on wide rows.                      |
| 65  | M      | Make the batch size configurable rather than a module constant so it can be tuned per table and per environment.                                                                              |
| 66  | M      | Add optimistic concurrency (version or `updated_at` precondition) to manual team-state overrides in `team_state.py` (~line 166) so a later write cannot silently lose an earlier correction.  |
| 67  | M      | Stamp published JSON artifacts (`cli/publish_projections.py`, `cli/publish_opening_squad.py`) with a schema version so the web app can reject an artifact it does not understand.             |
| 68  | L      | Make `SupabaseRestClient.__exit__` idempotent and safe after partial initialisation (`persistence/supabase.py` ~lines 102–103).                                                               |
| 69  | L      | Round-trip validate ISO timestamps written by `team_state.py` (~lines 99–102) to guarantee UTC normalisation on read-back.                                                                    |

## 6. Security and secret handling

| #   | Impact | Improvement                                                                                                                                                                                                      |
| --- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 70  | H      | Stop returning internal failure detail in the `x-fpl-andres-debug` response header (`api/fpl/[...path].ts` ~lines 27–29, `api/team/[id].ts` ~lines 29–32); keep the detail in server logs keyed by a request id. |
| 71  | H      | Redact user-supplied metadata before it is persisted to `workflow_runs` (`persistence/workflow.py` ~line 116); nothing currently prevents a caller from storing a credential in cleartext.                       |
| 72  | H      | Add rate limiting in front of `/api/fpl/*` and `/api/team/*`. Both are unauthenticated proxies to a third-party API and currently have no request budget per client (`vercel.json`).                             |
| 73  | H      | Assert the Supabase secret is never included in exception context or client repr (`persistence/supabase.py` ~line 85) with a regression test, rather than relying on a masked literal.                           |
| 74  | M      | Normalise the proxy path before pattern matching in `api/_lib/fpl-path.ts` (~line 66) so percent-encoded and dot-segment variants cannot reach the allow-list check in a different form than they are fetched.   |
| 75  | M      | Validate the presence and value of `content-type` before parsing upstream JSON in `api/_lib/fpl-proxy.ts` (~line 74).                                                                                            |
| 76  | M      | Distinguish `private` from `public` caching for entry-specific responses in `api/_lib/fpl-proxy.ts` (~lines 251–262) so a shared CDN cannot serve one manager's state to another.                                |
| 77  | M      | Validate the environment mapping in `persistence/supabase.py` (~lines 47–62) — non-string or transposed values should fail with a named configuration error at startup.                                          |
| 78  | M      | Add secret scanning (for example gitleaks) as a CI gate; `.env.example` documents several live secret names with no automated guard against a real one being committed.                                          |
| 79  | M      | Record and document the justification for the ignored advisory `GHSA-qwww-vcr4-c8h2` in `package.json` (~lines 41–45), with a review date, so the suppression is not permanent by inertia.                       |
| 80  | L      | Reconsider exposing commit SHA and environment from `api/health.ts` (~lines 11–14), or gate that detail behind an authenticated probe.                                                                           |
| 81  | L      | Send `X-Content-Type-Options: nosniff` on all API error responses, including the 502 path in `api/fpl/[...path].ts`.                                                                                             |
| 82  | L      | Reduce version detail in the outbound `FPL_USER_AGENT` (`adapters/fpl.py` ~line 18) to a stable contact string.                                                                                                  |

## 7. API and serverless functions

| #   | Impact | Improvement                                                                                                                                                                                               |
| --- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 83  | H      | Emit structured JSON logs with a request id, route, upstream status and duration instead of `console.error` (`api/fpl/[...path].ts` ~line 23, `api/team/[id].ts` ~line 26).                               |
| 84  | H      | Correlate retries under a single trace id in `api/_lib/fpl-proxy.ts` (~lines 116–175); a request that succeeds on attempt three leaves no evidence of the two failures.                                   |
| 85  | H      | Add error monitoring or an alerting sink for API failures; today a spike in 502s is invisible until a user reports it.                                                                                    |
| 86  | H      | Reconcile the 8.5s internal budget with the 10s `maxDuration` in `vercel.json` (~line 9), and set per-route durations so `/api/health` is not held to the same envelope as team state.                    |
| 87  | M      | Add a short-lived response cache or request coalescing for `/api/team/[id]` (`api/_lib/team-public-state-response.ts` ~lines 80–233); identical concurrent requests currently multiply upstream FPL load. |
| 88  | M      | Give each parallel upstream fetch its own budget in `api/_lib/team-public-state-response.ts` (~lines 102–120); a shared deadline lets one slow response starve the other.                                 |
| 89  | M      | Decode each upstream body once and reuse the parsed value (`api/_lib/team-public-state-response.ts` ~lines 140–141, 290–291).                                                                             |
| 90  | M      | Return a distinct `timeout` reason when `AbortSignal.timeout` fires (`api/_lib/fpl-proxy.ts` ~lines 139–141) instead of collapsing it into `unreachable`.                                                 |
| 91  | M      | Classify upstream failures as retryable or terminal and surface that classification in logs (`api/_lib/fpl-proxy.ts` ~line 12) so operational dashboards can separate FPL outages from contract breaks.   |
| 92  | M      | Log upstream status alongside `TeamPublicStateContractError` (`api/_lib/team-public-state.ts` ~lines 50–59) so an FPL schema change is diagnosable without reproducing it.                                |
| 93  | M      | Measure and record handler latency split between upstream wait and local processing; there is no timing instrumentation in `api/` today.                                                                  |
| 94  | L      | Avoid the extra buffer copy when assembling bounded response bodies (`api/_lib/fpl-proxy.ts` ~lines 105–107).                                                                                             |
| 95  | L      | Indicate truncation explicitly when debug detail is clipped at 300 characters (`api/fpl/[...path].ts` ~lines 27–29).                                                                                      |
| 96  | L      | Document the intended CORS posture for `api/` in one place; the functions are same-origin by design, which is worth stating rather than leaving implicit.                                                 |

## 8. Database schema and migrations

| #   | Impact | Improvement                                                                                                                                                                                                                                                              |
| --- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 97  | H      | Document the deliberate deny-all RLS posture, and add explicit named policies before any browser-readable table is introduced. Every table is `enable`/`force row level security` with no policy, which is correct today but undocumented (`supabase/migrations/*.sql`). |
| 98  | H      | Plan partitioning or an archival strategy for `element_gameweek_stats` (`supabase/migrations/20260801120000_history_corpus.sql` ~lines 82–142); the corpus grows by seasons × gameweeks × players indefinitely.                                                          |
| 99  | H      | Add composite indexes matching the real access paths — `(season, event_id, element_id)` and similar — rather than only single-column indexes (`20260801120000_history_corpus.sql` ~lines 136–141).                                                                       |
| 100 | H      | Add a migration rollback or forward-repair harness and test it locally; CI validates `db reset` but never exercises undoing a single migration (`.github/workflows/ci.yml` ~lines 44–48).                                                                                |
| 101 | M      | Constrain `workflow_runs.event_id` to the real FPL range (`20260729180000_foundation.sql` ~line 8) so an impossible event id cannot be recorded.                                                                                                                         |
| 102 | M      | Add a `(workflow_name, status)` index for run-queue lookups; the existing index covers `status` plus start time only (`20260729180000_foundation.sql` ~lines 20–21).                                                                                                     |
| 103 | M      | Make immutability-trigger errors name the table and operation (`20260730120000_projection_artifacts.sql` ~lines 116–124) so a failed publish is self-explanatory.                                                                                                        |
| 104 | M      | Define a retention and revision policy for `element_price_observations` and other append-only observation tables.                                                                                                                                                        |
| 105 | M      | Add an audit trail for `workflow_runs` status transitions; the current row is overwritten with no history of who or what changed it.                                                                                                                                     |
| 106 | L      | Add referential integrity or a reconciliation job for `source_snapshots.storage_path` (`20260729183000_evidence_snapshots.sql` ~line 10) so deleted objects do not leave orphan rows.                                                                                    |
| 107 | L      | Publish a schema reference (ERD plus column notes) generated from the migrations, since ten migrations now define the model with no single readable view.                                                                                                                |
| 108 | L      | Document naming conventions for tables, indexes, constraints and triggers so future migrations stay uniform.                                                                                                                                                             |

## 9. Frontend architecture and performance

| #   | Impact | Improvement                                                                                                                                                                    |
| --- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 109 | H      | Add a React error boundary around the router in `apps/web/src/main.tsx` (~lines 16–20); any render-time throw currently blanks the whole application.                          |
| 110 | H      | Code-split routes with `React.lazy` and a `Suspense` fallback (`apps/web/src/App.tsx` ~lines 866–879); every route currently ships in the initial bundle.                      |
| 111 | H      | Load the large JSON artifacts (`src/data/projections.json`, `validation.json`, `opening-squad.json`) on demand rather than importing them statically into the main bundle.     |
| 112 | H      | Use `AbortController` for the fetch in `components/ManagerHistory.tsx` (~lines 38–57); the `cancelled` flag prevents the state update but not the in-flight request.           |
| 113 | H      | Add bounded retry with backoff for transient API failures in `state/team-analysis.ts` (~lines 91–150) before showing a terminal error.                                         |
| 114 | H      | Break up `components/TeamStateCorrections.tsx` (720 lines) into transfer-draft, correction-form and confirmation components; it is the densest interactive surface in the app. |
| 115 | M      | Extract the eleven components currently inlined in `App.tsx` (~lines 109–851) into their own files so each can be tested and reviewed independently.                           |
| 116 | M      | Virtualise long tables in `components/PlayerPoolTable.tsx` (~lines 258–294) and `components/ValidationReport.tsx` instead of capping rows at 200.                              |
| 117 | M      | Share and memoise the `Intl` formatters currently redefined in `App.tsx`, `ManagerHistory.tsx`, `PlayerPoolTable.tsx`, `PitchView.tsx` and `SquadRecord.tsx`.                  |
| 118 | M      | Memoise pure leaf components (`PlayerChip`, `Jersey`, fixture-run cells) so unrelated parent state changes do not re-render the whole pitch or table.                          |
| 119 | M      | Deduplicate concurrent identical requests in `state/player-pool.ts` and `state/team-analysis.ts` by caching the in-flight promise per URL.                                     |
| 120 | M      | Add offline detection and a cached-data banner so a dropped connection is not rendered as a hard error (`App.tsx` ~lines 164–242).                                             |
| 121 | M      | Add a `Suspense` boundary for route transitions once code-splitting lands, with a skeleton rather than a blank frame.                                                          |
| 122 | M      | Audit `styles.css` for unused selectors and add a size budget check; the design system ships in full on first paint.                                                           |
| 123 | L      | Consolidate the duplicated stripe/theme custom properties in `styles.css` (~lines 95–132).                                                                                     |
| 124 | L      | Add `will-change` / `contain` hints to the animated loading and disclosure marks in `styles.css`.                                                                              |
| 125 | L      | Name dynamic import chunks once code-splitting exists, so bundle analysis output stays legible.                                                                                |

## 10. Frontend accessibility, UX and SEO

| #   | Impact | Improvement                                                                                                                                                                               |
| --- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 126 | H      | Add automated contrast and a11y checks (axe-core) to the browser journeys for both themes; `DESIGN.md` claims a contrast standard that nothing enforces (`styles.css` ~lines 58–72).      |
| 127 | H      | Set per-route document titles and meta description for `/team/:id` and the other routes; every page currently inherits the static head from `apps/web/index.html`.                        |
| 128 | M      | Announce analysis state transitions to assistive technology with an `aria-live` region (`App.tsx` ~lines 419–434); the ready/stale/degraded switch is currently silent.                   |
| 129 | M      | Add a visible `:focus-visible` outline for scrollable table regions that carry `tabIndex={0}`.                                                                                            |
| 130 | M      | Audit every icon for either an accessible name or `aria-hidden`, and assert it in tests rather than by inspection.                                                                        |
| 131 | M      | Add explicit responsive breakpoints and test 360px, 768px and 1440px; layout currently relies entirely on fluid `clamp()` scaling.                                                        |
| 132 | M      | Split the coarse loading state into the sub-steps the API actually performs so a slow bootstrap fetch is distinguishable from a slow entry fetch (`state/team-analysis.ts` ~lines 12–28). |
| 133 | M      | Add `robots.txt` and a sitemap under `apps/web/public/`.                                                                                                                                  |
| 134 | M      | Complete the PWA manifest with the icon sizes and metadata it declares (`apps/web/public/site.webmanifest`).                                                                              |
| 135 | L      | Give the empty manager-history state the same semantic treatment as the other empty states (`components/ManagerHistory.tsx` ~lines 71–81).                                                |
| 136 | L      | Document keyboard interactions in the interface itself, not only in the Playwright journey that exercises them.                                                                           |
| 137 | L      | Add JSON-LD structured data for the site and route breadcrumbs in `index.html`.                                                                                                           |

## 11. Contracts, typing and API surface

| #   | Impact | Improvement                                                                                                                                                                     |
| --- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 138 | H      | Enable `@typescript-eslint/no-explicit-any` in `eslint.config.js`; the config currently adds only `consistent-type-imports` and `no-unused-vars` on top of the recommended set. |
| 139 | H      | Replace unchecked casts of upstream payload fields such as `int(element["id"])` in `cli/publish_opening_squad.py` (~line 174) with schema-validated access.                     |
| 140 | M      | Replace `dict[str, Any]` return types in `adapters/fpl.py` (~lines 77–107) with `TypedDict` or Pydantic models so mypy can catch contract mismatches at the boundary.           |
| 141 | M      | Model frontend fetch errors as a discriminated union rather than `unknown` (`components/PlayerPoolTable.tsx` ~lines 111–118, `components/ManagerHistory.tsx` ~lines 48–50).     |
| 142 | M      | Require a contracts package version bump whenever the generated schema changes, and assert it in CI (`packages/contracts/package.json`).                                        |
| 143 | M      | Make schema-drift detection a dedicated, clearly named CI gate rather than one step inside `pnpm check`.                                                                        |
| 144 | M      | Add `@typescript-eslint/explicit-module-boundary-types` for the exported helpers in `api/_lib/`.                                                                                |
| 145 | L      | Add `@typescript-eslint/require-await` and `no-floating-promises` to catch async misuse in handlers and effects.                                                                |
| 146 | L      | Define `__all__` consistently across Python packages so the public surface is explicit (only some `__init__.py` files declare it).                                              |
| 147 | L      | Type the sort key callables used in publishing CLIs (`cli/publish_projections.py` ~line 117) so a renamed field fails type checking.                                            |
| 148 | L      | Reduce the remaining `Any` annotations across `persistence/` and `cli/` where the shape is in fact known.                                                                       |

## 12. Testing and reproducibility

| #   | Impact | Improvement                                                                                                                                                                         |
| --- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 149 | H      | Add negative-path tests for the FPL adapter: exhausted retries, malformed JSON, oversized payloads, truncated streams and timeout handling (`python/tests/test_fpl_adapter.py`).    |
| 150 | H      | Add tests that exercise the real PostgREST dialect and batch limits for the persistence layer, not only mocked transports (`python/tests/test_backtest_persistence.py`).            |
| 151 | H      | Extend browser journeys to cover the error, stale, degraded and unavailable states end to end; `apps/web/e2e/` currently covers the happy paths of two flows.                       |
| 152 | H      | Enforce a coverage threshold in CI for both Python and the web workspace; `pytest-cov` is installed with no `--cov-fail-under` and no JS coverage gate.                             |
| 153 | H      | Pin and checksum the historical corpus revision used by backtests, and document a golden backtest run that can be replayed (`docs/BUILD_PLAN.md`, `python/tests/test_backtest.py`). |
| 154 | M      | Add property-based tests for the statistical invariants — shrinkage bounded by prior and observation, monotone recency decay, effective rank within `[1, n]`.                       |
| 155 | M      | Add property-based tests for `ingest/normalise.py` and `crosswalk/resolve.py` tolerance and boundary behaviour.                                                                     |
| 156 | M      | Add fixture builders (`make_player`, `make_observation`, `make_rules`) to replace repeated inline construction across `python/tests/`.                                              |
| 157 | M      | Add fixtures for upstream error responses (429, 500, 503, partial body) so retry and backoff logic is covered by data, not by mocks alone.                                          |
| 158 | M      | Add round-trip serialisation tests between the Pydantic and Zod contracts, extending the existing parity check to real payloads.                                                    |
| 159 | M      | Add tests for CLI argument validation (positive rates, ordered ranges, valid seasons) across `cli/`.                                                                                |
| 160 | M      | Version fixture files in `python/tests/fixtures/` with source, capture date and schema version so a stale fixture is visible.                                                       |
| 161 | M      | Set `PYTHONHASHSEED` and a session-level seed fixture in CI so test ordering and any randomised construction are reproducible.                                                      |
| 162 | M      | Document the seeding strategy: which seeds are used, why, and how to reproduce a failing simulation or bootstrap run.                                                               |
| 163 | M      | Add golden-file tests for the published artifacts (`projections.json`, `opening-squad.json`, `validation.json`) so a format change is a deliberate diff.                            |
| 164 | M      | Add web tests for override edge cases: quota-exceeded storage, corrupted cache entries, and cache entries for a different entry id.                                                 |
| 165 | L      | Mark and separate slow tests (`@pytest.mark.slow`) and add per-test timeouts so a hang fails fast in CI.                                                                            |
| 166 | L      | Trial mutation testing on the rules and scoring modules to measure whether the suite actually catches regressions.                                                                  |
| 167 | L      | Track flaky-test history for the Playwright journeys and set an explicit retry policy rather than leaving it implicit.                                                              |

## 13. CI/CD, tooling and developer experience

| #   | Impact | Improvement                                                                                                                                                                              |
| --- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 168 | H      | Cache the pnpm store and the Playwright browser download in `.github/workflows/ci.yml`; only pip is cached today, so every run reinstalls the JavaScript toolchain and Chromium.         |
| 169 | H      | Run CodeQL on pull requests, not only on pushes to `main` and the weekly schedule (`.github/workflows/codeql.yml` ~lines 4–9).                                                           |
| 170 | H      | Split the single 20-minute `validate` job into parallel jobs (lint/typecheck, unit tests, migrations, browser journeys) so failures are isolated and total wall time drops.              |
| 171 | H      | Run `format:check` and lint before the expensive steps; formatting failures currently surface after migrations, `pnpm check` and browser journeys (`.github/workflows/ci.yml` ~line 60). |
| 172 | M      | Pin every action to a full commit SHA consistently across all six workflows, and add a policy note so future additions follow it.                                                        |
| 173 | M      | Add per-step timeouts to the long workflows (`historical-ingest.yml` ~line 43, `capture-crowd.yml`) so one stuck step cannot consume the whole budget.                                   |
| 174 | M      | Cache Python dependencies in `live-contracts.yml` and the other scheduled workflows as CI does.                                                                                          |
| 175 | M      | Validate dispatch inputs (season, event) in `capture-crowd.yml` (~lines 63–70) and `historical-ingest.yml` (~lines 68–76) before they reach shell array construction.                    |
| 176 | M      | Add a `CODEOWNERS` file so changes to `supabase/`, `api/` and `python/fpl_andres/rules.py` require the right reviewer.                                                                   |
| 177 | M      | Add pre-commit hooks (format, lint, contracts regeneration) so contributors get the same feedback locally that CI enforces.                                                              |
| 178 | M      | Raise the Dependabot open-PR limit or group updates by ecosystem so security patches are not queued behind feature bumps (`.github/dependabot.yml`).                                     |
| 179 | M      | Publish a bundle-size budget check for `apps/web` in CI so the static data imports cannot silently grow the entry chunk.                                                                 |
| 180 | M      | Add `C90` (complexity) and `W` to the ruff `select` list in `pyproject.toml` (~line 50) and set a complexity ceiling for the solver and projector modules.                               |
| 181 | L      | Audit and remove the remaining `type: ignore` comments so the `strict = true` mypy claim is unqualified (`pyproject.toml` ~line 59).                                                     |
| 182 | L      | Mention contract regeneration and migration review explicitly in `.github/pull_request_template.md`.                                                                                     |
| 183 | L      | Add a `make`-style task list or `pnpm` alias for the common local loop (focused tests, then `pnpm check`) to shorten onboarding.                                                         |
| 184 | L      | Document why runtime dependencies are pinned exactly (zod, TypeScript, `@vercel/node`) so future contributors do not loosen them by mistake.                                             |

## 14. Documentation and governance

| #   | Impact | Improvement                                                                                                                                                                                                   |
| --- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 185 | H      | Add `SECURITY.md` with a disclosure route and response expectations; the project proxies a third-party API and holds a production database with none published.                                               |
| 186 | H      | Complete `docs/MODEL.md`: attacking rates, supporting points, cross-season blending and calibration are referenced elsewhere but not documented here.                                                         |
| 187 | H      | Write the missing ADRs for the decisions the code already encodes: forced RLS with no policies, artifact immutability, structural walk-forward leakage guards, and recency-decayed deployment classification. |
| 188 | H      | Document secret rotation for `SUPABASE_SECRET_KEY`, the Resend key and workflow tokens in `docs/RUNBOOK.md`; the secrets are listed but rotation is not.                                                      |
| 189 | H      | Document corpus provenance — archive revision, capture date and row counts — so a backtest claim is reproducible from the docs alone (`docs/BUILD_PLAN.md`, `docs/OWNER_SETUP.md`).                           |
| 190 | M      | Add `CONTRIBUTING.md` covering the test-first workflow, the focused-validation-then-`pnpm check` loop, and the limits that must not be defaulted.                                                             |
| 191 | M      | Document the API surface (`/api/health`, `/api/fpl/*`, `/api/team/:id`): parameters, response shapes, status codes and the meaning of each degraded reason.                                                   |
| 192 | M      | Add a schema reference document for `supabase/` covering table purpose, grain and immutability rules.                                                                                                         |
| 193 | M      | Mark `docs/BUILD_PLAN.md` as historical and point to `docs/ROADMAP.md`, which explicitly supersedes it, to remove the status ambiguity.                                                                       |
| 194 | M      | Add incident playbooks to `docs/RUNBOOK.md` for corrupt ingest, failed promotion and stale public state, alongside the existing deployment and secret sections.                                               |
| 195 | M      | Record measured model performance (MAE, RMSE, rank correlation, calibration) against the documented targets in `docs/MODEL_CARDS.md`.                                                                         |
| 196 | M      | Document parameter provenance in `docs/MODEL.md` — every half-life, threshold and shrinkage strength with its source — so the "no agent defaults" rule is auditable.                                          |
| 197 | M      | Record model lineage on promotion decisions: code version, dependency versions and corpus revision, not just seed and sample floor.                                                                           |
| 198 | M      | Add a local development runbook covering seeding, inspecting the local database and debugging API routes.                                                                                                     |
| 199 | M      | Add a quick-reference table to `docs/LIMITATIONS.md` mapping each limit to the feature it disables or downgrades.                                                                                             |
| 200 | L      | Add issue templates for bug reports, data-source breaks and model regressions.                                                                                                                                |
| 201 | L      | Add a troubleshooting FAQ for Docker, corepack and Supabase CLI setup failures.                                                                                                                               |
| 202 | L      | Extend `DESIGN.md` with a component inventory and an accessibility checklist that the browser journeys can assert.                                                                                            |
| 203 | L      | Add a first-contribution checklist naming the documents to read in order and a verification command to prove the environment works.                                                                           |
| 204 | L      | Add a performance-debugging note covering profiling the projector, timing the solvers and measuring API latency.                                                                                              |

---

## Summary

| Category                           | Items | High | Medium | Low |
| ---------------------------------- | ----- | ---- | ------ | --- |
| Correctness and modelling          | 18    | 5    | 8      | 5   |
| Numerical and statistical rigour   | 14    | 4    | 8      | 2   |
| Python performance and scalability | 8     | 0    | 4      | 4   |
| Ingestion, adapters and network    | 17    | 5    | 9      | 3   |
| Persistence and data integrity     | 12    | 4    | 6      | 2   |
| Security and secret handling       | 13    | 4    | 6      | 3   |
| API and serverless functions       | 14    | 4    | 7      | 3   |
| Database schema and migrations     | 12    | 4    | 5      | 3   |
| Frontend architecture and perf     | 17    | 6    | 8      | 3   |
| Frontend accessibility, UX and SEO | 12    | 2    | 7      | 3   |
| Contracts, typing and API surface  | 11    | 2    | 5      | 4   |
| Testing and reproducibility        | 19    | 5    | 11     | 3   |
| CI/CD, tooling and DX              | 17    | 4    | 9      | 4   |
| Documentation and governance       | 20    | 5    | 10     | 5   |
| **Total**                          | 204   | 54   | 103    | 47  |

Suggested first pass, on impact against effort: the debug-header leak (#70), the
API error boundary and route splitting (#109, #110), the pnpm and browser cache in
CI (#168), `SECURITY.md` (#185), the upsert `on_conflict` validation (#58), and the
FPL adapter negative-path tests (#149).
