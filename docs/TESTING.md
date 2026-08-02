# Testing

## The two loops

```bash
corepack pnpm fast    # ruff, fast Python tests, JS tests. Seconds.
corepack pnpm check   # everything, including build, mypy and coverage.
```

Run `fast` while working and `check` before committing a milestone. `fast`
deselects `@pytest.mark.slow`, which is the handful of tests that sleep for real
or run thousands of bootstrap resamples.

Browser journeys are separate because they need a build and a browser:

```bash
corepack pnpm test:e2e
```

## Seeding

Audit items #161 and #162.

**One seed, stated in one place.** `python/tests/conftest.py` defines
`SESSION_SEED = 20260801`. It is printed in the pytest run header, so a failure
log carries the seed that produced it.

**Reseeded before every test, not once per session.** A session-level seed makes
each test depend on how many random numbers the tests before it consumed, so
running one test alone gives a different answer from running the suite — which
is the exact property that makes a failure impossible to reproduce. The autouse
fixture reseeds and then restores the previous state, so nothing leaks either
way.

**`PYTHONHASHSEED=0` in CI.** Set iteration order is otherwise randomised per
process. Most code here sorts before it depends on order; "most" is the problem,
because the failure mode is a test that passes on one hash seed and fails on
another, appearing in CI roughly once a fortnight and never locally.

### Reproducing a failing run

1. The seed is in the pytest header: `session seed: 20260801`.
2. Set the same hash seed: `$env:PYTHONHASHSEED = "0"` (PowerShell) or
   `PYTHONHASHSEED=0` (bash).
3. Run the single test: `python -m pytest path::test_name`.

If it passes alone but failed in the suite, the cause is shared state rather
than the seed — the per-test reseed rules out RNG ordering as the explanation.

### Seeds that are not this one

Anything taking an explicit `seed` argument — `evaluate_promotion`,
`simulate_league` — is passed one by its caller, not by the fixture. Those seeds
belong to the decision being made and are recorded alongside its result, because
a promotion decision has to be attributable to the draw that produced it. The
`seed` fixture exists for tests that want to use the same value.

`evaluate_promotion` additionally takes `seed_replicates`, because a decision
that depends on which seed was passed is not a decision about the model. See
`python/tests/test_promotion_seed_stability.py`.

## Slow tests

A test over one second must carry `@pytest.mark.slow`. The suite reports any
that do not, so the marker cannot quietly fall behind:

```
-------------------- slow tests without @pytest.mark.slow ---------------------
    2.66s  python/tests/test_promotion_seed_stability.py::test_replication...
```

Mark it, or make it faster. Both are fine; leaving it unmarked is not, because
that is how a suite becomes something people stop running.

## Coverage

`pnpm check` enforces 77% line coverage with branch coverage on. The threshold
is a floor to stop regressions, not a target: the number that matters is whether
the failure modes in `docs/ERRORS.md` are exercised, and coverage cannot see
that.

## Does the suite actually catch anything?

Coverage says which lines ran. It does not say whether anything would have
noticed if they ran wrongly. Audit item #166 asked for the stronger measurement.

```bash
python scripts/mutation_trial.py
python scripts/mutation_trial.py --module python/fpl_andres/rules.py
```

The script changes one operator at a time — `>` to `>=`, `and` to `or`, `True`
to `False` — runs the suite, and reports whether anything failed. A surviving
mutant is a change no test objects to, which is either a gap or a line that does
not matter.

**Result, 2026-08-02: 63 mutants across `rules.py` and `backtesting/score.py`,
63 killed. A 100% kill rate.**

Not `mutmut` or `cosmic-ray`. Both are good tools and both are a dependency, a
config file and a cache directory to maintain, for a question asked once a year.
The script is sixty lines and answers it.

Re-run it after substantially reworking either module. A kill rate below 90%
means the suite is executing that code rather than testing it.

## Browser journeys and flakes

`retries: 2` on CI, deliberately: these drive a real browser against a real dev
server, and a cold first paint on a loaded runner is an environmental failure
rather than a defect. Zero retries makes CI a coin flip; more than two hides a
test that fails half the time.

A retry that passes is still recorded. `playwright-report/results.json` carries
every attempt and CI uploads it on success as well as failure — a run that
passed on the second attempt is exactly the one worth inspecting, and
`if: failure()` would never collect it.

**The policy:** a test that appears in the flaky list twice in a fortnight is a
broken test, not an unlucky one. Fix it or delete it. A journey nobody trusts is
worse than no journey, because it trains people to re-run CI without reading the
failure.
