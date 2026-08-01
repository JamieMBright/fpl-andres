# Local development

Audit item #198. The README covers install and the two test commands. This covers
the parts that go wrong: seeding a database that starts empty, looking at data
you are not allowed to look at in production, and debugging an API route that
only exists as a serverless function in production.

`docs/TESTING.md` covers the test loops and the seeding strategy.

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

## What not to do

- Do not run `supabase db push` against the hosted project. Migrations go
  through the SQL Editor, tracked in the checklist in `docs/OWNER_SETUP.md`.
- Do not put a secret in anything named `VITE_*`. Vite inlines those into the
  browser bundle at build time.
- Do not commit `.env`. It is gitignored; keep it that way.
- Do not regenerate the published artifacts to make a test pass. They are
  evidence, and a test that disagrees with them is telling you something.
