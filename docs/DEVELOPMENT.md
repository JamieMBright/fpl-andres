# Local development

Audit item #198. The README covers install and the two test commands. This covers
the parts that go wrong: seeding a database that starts empty, looking at data
you are not allowed to look at in production, and debugging an API route that
only exists as a serverless function in production.

`docs/TESTING.md` covers the test loops and the seeding strategy.

---

## First contribution

Audit item #203. Read these four, in this order. They take about twenty minutes
together and they are the four that make the rest of the repository make sense.

| Read                  | Why it is on the list                                          |
| --------------------- | -------------------------------------------------------------- |
| `docs/THESIS.md`      | What the project claims and how it intends to prove it.        |
| `docs/LIMITATIONS.md` | What it refuses to do. This is a hard boundary, not a backlog. |
| `CONTRIBUTING.md`     | Test first, measure before asserting, never default a rule.    |
| `docs/ERRORS.md`      | Refuse, degrade or retry — the decision behind every failure.  |

Then prove your environment works:

```powershell
corepack pnpm check
```

That single command exercises everything: contract drift, lint, typecheck, all
four test suites, the production build with its size budget, ruff, mypy and
coverage. It takes about a minute. If it passes, your environment is correct and
you can ignore every other setup instruction until something breaks.

If it does not pass, the FAQ below covers what it is usually.

---

## Setup FAQ

Audit item #201. These are the failures that stop someone before they have
written anything.

**`corepack: command not found`, or pnpm runs the wrong version.**
Corepack ships with Node but is disabled by default on some installs. Run
`corepack enable`. If the pinned pnpm still does not activate, run
`corepack prepare pnpm@9.15.9 --activate` — the version is pinned in
`package.json` under `packageManager` and CI uses exactly that one.

**`pnpm install` fails on a frozen lockfile.**
`pnpm install --frozen-lockfile` refuses when `package.json` and
`pnpm-lock.yaml` disagree. That is the point: it means someone edited a
dependency without committing the lock. Run a plain `pnpm install` locally and
commit the lockfile change with the reason.

**`supabase start` hangs or fails to pull an image.**
It needs Docker running, and the first start pulls several gigabytes. On Windows
that means Docker Desktop with the WSL2 backend actually started, not just
installed. `docker ps` should answer without error before you try.

**`supabase db reset` fails with `42P01: relation does not exist`.**
A migration references a table created by a later-sorting file. Migrations apply
in filename order, so the timestamp prefix is load-bearing.
`python/tests/test_migrations.py` catches this without a database.

**The Python commands cannot find `fpl_andres`.**
`pythonpath = ["python"]` is set in `pyproject.toml` for pytest, but not for a
bare `python -c`. Run from the repository root, or use `python -m pytest`.

**mypy or ruff behave differently from CI.**
Both read their config from `pyproject.toml`, so the usual cause is a different
interpreter. CI pins the Python version; check yours matches.

**Everything passes locally and CI fails.**
Almost always a case-sensitive path, or a directory that exists on your machine
because something created it at runtime. CI is Linux and starts from a clean
clone.

---

## The loop

```powershell
corepack pnpm fast     # ruff, non-slow Python tests, JS tests. ~25s.
corepack pnpm check    # everything, including build, mypy and coverage. ~55s.
corepack pnpm test:e2e # browser journeys. Needs a build.
```

`fast` while working, `check` before committing. If `check` passes and CI does
not, the difference is almost always a case-sensitive path or a runtime-created
directory — CI is Linux.

---

## Where code runs

Two places, and no third:

|            | Runs                                      | Serves    |
| ---------- | ----------------------------------------- | --------- |
| Local      | `pnpm dev` (Vite) + local Docker Postgres | Nobody    |
| Production | Vercel, on push to `main`                 | Everybody |

There is no staging, no preview environment and no dev deployment. A merge to
`main` is a release.

The gap that matters: **Vite does not read `vercel.json`.** Headers, rewrites,
function budgets and the Content-Security-Policy are all inert locally, so a
mistake in that file cannot fail on your machine — it can only fail in front of
users. Two outages have come from exactly this. The defence is that
`python/tests/test_vercel_functions.py` and
`apps/web/src/deployment-config.test.ts` parse `vercel.json` in the normal test
run and assert it against the files it claims to configure, so the gate catches
what the dev server cannot.

The same reasoning covers dependencies: a package that is installed in your
environment transitively is not a declared dependency, and CI installs from the
manifest. `python/tests/test_declared_dependencies.py` walks every import and
fails on anything absent from `pyproject.toml`.

---

## The local database

The hosted project is production and there is no staging. Everything below is
the local Docker Postgres, which starts empty and is safe to destroy.

```powershell
corepack pnpm exec supabase start   # needs Docker Desktop running
corepack pnpm exec supabase status  # urls, keys, and the DB_URL
corepack pnpm exec supabase db reset --local
```

`db reset` drops the local database and re-applies every migration in filename
order. It is the only thing that catches a migration referencing a table created
by a later-sorting file, which is why CI runs it on every change.

### Inspecting local data

```powershell
$url = corepack pnpm exec supabase status --output json | ConvertFrom-Json | ForEach-Object { $_.DB_URL }
psql $url -c "\dt public.*"
psql $url -c "select season, count(*) from element_gameweek_stats group by season order by season"
```

Supabase Studio is at the URL `supabase status` prints, usually
`http://127.0.0.1:54323`.

**This applies to the local database only.** Inspecting application rows in the
hosted project through tooling is prohibited, and the AI agents working in this
repository are instructed not to do it. The sanctioned view of production data is
the published artifact in `apps/web/src/data/`.

### Seeding

There is no seed file, deliberately: fabricated rows in a corpus whose whole
point is provenance would be indistinguishable from real ones after a week. Get
data the way production does.

```powershell
# One season, from the pinned vaastav archive. Writes to whatever
# SUPABASE_URL points at, so check it is local first.
python -m fpl_andres.cli.ingest_historical --seasons 2024-25 --commit <sha>
```

For model work you rarely need the database at all. The backtest corpus loads
from Supabase, but every model function takes evidence objects directly, and the
test fixtures build those in memory. Reach for the database when you are changing
persistence or migrations; otherwise a test is faster and reproducible.

---

## Debugging an API route

`api/*.ts` are Vercel serverless functions. `pnpm dev` runs Vite, which serves
the frontend and proxies `/api` — so the routes execute as normal Node modules
and a breakpoint works.

```powershell
corepack pnpm dev
curl http://localhost:5173/api/health
curl "http://localhost:5173/api/team/212279"
```

Three things behave differently from production and are worth knowing before you
chase a phantom:

**Failures are deliberately opaque.** A route that throws returns a request id
and nothing else — no message, no stack. That is the point: the upstream error
may contain a connection string. The detail goes to the structured log, keyed by
the same id. Find it in the terminal running `pnpm dev`, or in Vercel's function
logs in production. See the request-id incident procedure in `docs/RUNBOOK.md`.

**The FPL proxy is real.** `/api/fpl/*` calls fantasy.premierleague.com. It is
rate limited and it will refuse you if you loop. The e2e suite never calls it —
every journey intercepts the route — and neither should a debugging loop.

**`maxDuration` is not enforced locally.** `vercel.json` caps health at 5s and
the proxies at 15s. Locally a hanging request hangs forever, so a route that
works locally and times out in production is a real possibility.

---

## When something only fails in CI

In order of likelihood:

1. **Case-sensitive paths.** Windows does not care about `Components/` versus
   `components/`. Linux does.
2. **A directory that exists only on your machine.** Ruff's isort treats a
   folder in the source root as first-party, so a runtime-created directory
   changes import ordering on your machine and not on CI.
3. **Hash ordering.** CI pins `PYTHONHASHSEED=0`; locally it is random. Set it
   and re-run.
4. **Playwright browser version.** CI caches on the resolved version. A stale
   local browser can pass what CI fails.

```powershell
$env:PYTHONHASHSEED = "0"; corepack pnpm check
```

---

## Measuring performance

Audit item #204. `CONTRIBUTING.md` says measure before you assert. This is how,
for the three things anyone is tempted to optimise.

Every number below was measured on this repository. They are here so the next
person does not have to re-derive them before deciding an optimisation is not
worth it — which, four times out of five so far, it was not.

### The projector and the scorer

```powershell
python -c "import cProfile, pstats; cProfile.run('...', 'out'); pstats.Stats('out').sort_stats('tottime').print_stats(10)"
```

Scoring 114,000 outcomes — four seasons of 38 gameweeks and 750 players, the
real corpus shape — takes **0.080 s**, of which sorting is 0.026 s. The backtest
that calls it pages the corpus over the network first, so the sort is not the
thing to fix. Guarded by a slow-marked test bounded at 2.0 s, which catches a
change that makes scoring quadratic without flaking on a loaded runner.

### The solvers

```powershell
python -m pytest python/tests/test_horizon_scale.py -q
```

The constraint matrix was dense and grew quadratically: 700 players over 5
events would have been roughly **2.1 GB**. Built sparsely it grows linearly.
That one was worth doing, and the test that measures it is the reason it stays
done.

Rebuilding the player index per solve costs microseconds against a HiGHS solve
of hundreds of milliseconds. Per-player dictionary lookups over a 700-player
pool: **0.103 ms**, against 0.059 ms for a pre-join. Neither is worth the
change.

### API latency

The handler log carries the split, per request:

```json
{
  "event": "handler_outcome",
  "totalMs": 412,
  "upstreamMs": 380,
  "localMs": 32,
  "stageMs": { "entry": 180, "bootstrap": 200, "picks": 0 }
}
```

`localMs` is ours to fix; `upstreamMs` is FPL's. `stageMs` says which of the
three upstream calls was slow, which the browser cannot see because it makes one
request. A stage that never ran reports zero rather than being omitted, so the
log never implies a fetch that did not happen.

### The bundle

```powershell
corepack pnpm --filter @fpl-andres/web build
```

Prints every chunk against its budget. The entry chunk is **126 kB gzipped**
against a 150 kB budget; the stylesheet is 6.3 kB against 8 kB. The build fails
if either is exceeded, so raising a budget is a deliberate edit with a number
attached.

### The rendering

Measured in jsdom, which is slower than a browser: the whole 15-chip pitch
renders in **4.3 ms** and a 200-row table in **7.4 ms**. Memoisation and
virtualisation were both declined on those numbers, and the tests that record
them assert a ratio against a baseline rather than a wall clock, so they do not
flake under a parallel run.

---

## What not to do

- Do not run `supabase db push` against the hosted project. Migrations go
  through the SQL Editor, tracked in the checklist in `docs/OWNER_SETUP.md`.
- Do not put a secret in anything named `VITE_*`. Vite inlines those into the
  browser bundle at build time.
- Do not commit `.env`. It is gitignored; keep it that way.
- Do not regenerate the published artifacts to make a test pass. They are
  evidence, and a test that disagrees with them is telling you something.
