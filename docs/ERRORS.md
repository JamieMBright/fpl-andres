# Error taxonomy

Every exception this package raises falls into one of three classes, and the
class determines what the caller must do. The classes exist because the
repository has one rule that overrides ordinary error handling:

> Never default a missing controlling FPL rule; fail its source contract visibly.

An exception is therefore not an inconvenience to be swallowed. It is a
statement about whether the pipeline is still allowed to publish.

`python/tests/test_error_taxonomy.py` fails if a new exception type is added to
the package without being classified here, so this file cannot go stale.

## Refuse

**A contract is broken, or the answer would be built on information the model
was not entitled to see.** Nothing may be published for the affected subject.
Do not substitute a default, a zero, or a last-known-good value: the whole point
is that the failure stays visible.

| Exception                      | Module                    | Raised when                                                      |
| ------------------------------ | ------------------------- | ---------------------------------------------------------------- |
| `BacktestLeakError`            | `models/backtest.py`      | A prediction depends on evidence from after its cutoff.          |
| `BootstrapElementError`        | `bootstrap.py`            | bootstrap-static carries an element this package cannot read.    |
| `CohortError`                  | `cohorts/veterans.py`     | A history payload cannot support a cohort decision.              |
| `ColumnMappingError`           | `ingest/normalise.py`     | An archive CSV lacks a column the schema depends on.             |
| `CorpusLoadError`              | `backtesting/corpus.py`   | The corpus cannot supply a usable season.                        |
| `CovarianceUnavailable`        | `planning/effective.py`   | A squad's spread cannot be stated without a measured covariance. |
| `FplContractError`             | `adapters/fpl.py`         | FPL responds with a shape unsafe for downstream use.             |
| `FutureInformationError`       | `adapters/vaastav.py`     | Historical evidence was unavailable at decision time.            |
| `FutureMinutesEvidenceError`   | `models/minutes.py`       | Minutes evidence postdates the decision cutoff.                  |
| `FutureRateEvidenceError`      | `models/player_rates.py`  | Rate evidence postdates the decision cutoff.                     |
| `FutureRoleEvidenceError`      | `models/deployment.py`    | Role evidence was unavailable for the requested decision.        |
| `InconsistentObservationBasis` | `models/player_rates.py`  | Expected values were chosen as the basis and one is absent.      |
| `MalformedJsonError`           | `jsonio.py`               | JSON cannot be parsed, naming the source that produced it.       |
| `MissingCredentialsError`      | `persistence/supabase.py` | Service-role credentials are absent or malformed.                |
| `ModelFitError`                | `models/dixon_coles.py`   | Numerical optimization cannot produce a valid model.             |
| `OptimizationError`            | `optimization/highs.py`   | The optimizer cannot prove an optimal valid squad.               |
| `OutOfWindowObservationError`  | `models/minutes.py`       | Recency decay has driven an observation's weight to zero.        |
| `PersistenceNotMeasurable`     | `cohorts/sweep.py`        | A persistence claim would be conditioning on the outcome.        |
| `PositionUnknown`              | `positions.py`            | An element type or code is not one of the four positions.        |
| `RevisionUnavailable`          | `persistence/backtest.py` | The code revision cannot be determined.                          |
| `RulesContractError`           | `rules.py`                | The live FPL payload cannot define a complete rules model.       |
| `StatsbombAdapterError`        | `adapters/statsbomb.py`   | A StatsBomb payload does not match the expected shape.           |
| `TeamStateContractError`       | `team_state.py`           | Public entry evidence cannot form a safe planning snapshot.      |
| `TeamStateResolutionError`     | `team_state.py`           | Manager overrides cannot produce exact current planning state.   |

`OptimizationError` and `ModelFitError` are in this class rather than _Degrade_
on purpose. A squad the solver could not prove optimal, and a fit that did not
converge, are both indistinguishable from a wrong answer at the point of use.

## Degrade

**Evidence is genuinely, legitimately absent.** The caller may continue, but the
result must carry a lower `EvidenceLevel` and a reason code that names what was
missing. A degraded answer that does not say it is degraded is worse than no
answer.

| Exception                  | Module                   | Raised when                                              |
| -------------------------- | ------------------------ | -------------------------------------------------------- |
| `ArchiveFileNotPublished`  | `ingest/historical.py`   | The archive simply does not carry a file.                |
| `BenchmarkUnavailable`     | `models/benchmark.py`    | Two projections cannot be compared honestly.             |
| `CardRateUnavailable`      | `models/suspensions.py`  | Too little evidence to estimate a booking rate.          |
| `FplPicksUnavailable`      | `adapters/fpl.py`        | An entry's picks for an event are not public.            |
| `InsufficientHistoryError` | `models/baselines.py`    | A team-aware estimate lacks its declared sample floor.   |
| `OddsUnavailable`          | `models/odds.py`         | Quoted prices cannot be read as a market.                |
| `PenaltySplitUnavailable`  | `models/penalties.py`    | The penalty and open-play split cannot be trusted.       |
| `ShotProfileUnavailable`   | `models/shot_profile.py` | Too little shooting to read a profile from.              |
| `SquadSelectionError`      | `simulation/squad.py`    | A legal squad cannot be produced from the supplied pool. |

The distinction from _Refuse_ is whether the absence is **expected**. Picks are
private before a deadline; a promoted side has no top-flight shooting history.
Neither is a broken contract. A missing column in a file that claims to have it
is.

## Retry

**Transient. The identical call may succeed later.** Callers should back off and
retry within the bounds the module documents, then escalate to _Refuse_ if the
bound is exhausted. `FplUpstreamDown` is what `FplContractError`'s sibling
becomes after the circuit breaker trips.

| Exception                     | Module                    | Raised when                                                 |
| ----------------------------- | ------------------------- | ----------------------------------------------------------- |
| `ArchiveFetchError`           | `ingest/historical.py`    | The pinned archive cannot be retrieved.                     |
| `FplCacheUnavailable`         | `adapters/fplcache.py`    | An archived snapshot cannot be read or trusted.             |
| `FplUpstreamDown`             | `adapters/fpl.py`         | The adapter has given up on an endpoint that keeps failing. |
| `Refused`                     | `cli/sweep_managers.py`   | FPL has told us to stop often enough that we should.        |
| `SupabaseWriteError`          | `persistence/supabase.py` | PostgREST rejects a write.                                  |
| `WorkflowAlreadyRunningError` | `persistence/workflow.py` | An identical run is already in flight.                      |

`WorkflowAlreadyRunningError` is retryable in the weakest sense: the correct
response is usually to stop, because something else is already doing the work.
It is here rather than in _Refuse_ because nothing is broken.

## Choosing a base class

- `ValueError` — the inputs were wrong.
- `RuntimeError` — the inputs were fine and the world did not cooperate.
- `LookupError` — a specific thing was asked for and does not exist.

These are inherited directly rather than from a package-wide base. A single
`FplAndresError` root would make `except FplAndresError` easy to write, and that
is exactly the reason not to have one: it invites catching _Refuse_ and
_Degrade_ in the same clause, which is the mistake this taxonomy exists to
prevent.

## Adding a new exception

1. Give it a one-line docstring starting `Raised when`.
2. Add a row to the correct table above.
3. Run `pytest python/tests/test_error_taxonomy.py`.

The test enforces 1 and 2. It cannot check that you chose the right table, which
is the only part that requires judgement.
