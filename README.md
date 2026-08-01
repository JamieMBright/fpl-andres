# FPL Andres

FPL Andres is an evidence-gated Fantasy Premier League analyst. It is being built
to answer the next deadline's practical questions first: whether to transfer or bank,
who to captain, how to order the bench, and how today's move affects a rolling
6–8 gameweek plan.

The project is independent and is not affiliated with Fantasy Premier League, the
Premier League, Leeds United, or any player or club.

## Current status

The public Team-ID workflow is complete for the current milestone. A bounded same-origin
API now assembles exact-byte entry, picks and deadline evidence into strict public
last-deadline state. The browser renders ready, stale, unavailable, degraded and error
states, preserves only validated cache entries, exposes source timestamps/hashes, and
stores manager corrections locally against the exact team and public deadline.

The repository also contains optimal single-event and rolling HiGHS solvers, a bounded
TypeScript quick solver with measured regret/latency, immutable plan artifacts, and an
evidence-gated Lord Lundstram out-of-position signal. Recommendations are not yet live,
no projection candidate is promoted, and unsupported objective/chip modes fail closed.

## Evidence policy

- Live state comes from public FPL endpoints.
- Historical model evaluation uses timestamped, pinned public archives.
- Every output will be labelled `observed`, `inferred`, `experimental`, or
  `unavailable`.
- Public Team-ID state reflects the last processed deadline; pre-deadline corrections
  must be supplied by the manager.
- The product does not invent price thresholds, rival intentions, or matchup detail
  unsupported by its sources.

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md) for the binding capability boundary.
See [docs/DATA_CONTRACTS.md](docs/DATA_CONTRACTS.md) for source and normalization
contracts. See [docs/MODEL_CARDS.md](docs/MODEL_CARDS.md) for projection identities,
inputs, failure modes and promotion rules. See
[docs/OPTIMIZER.md](docs/OPTIMIZER.md) for team-state, solver, benchmark and audit
contracts.

## Architecture

```text
Browser -> Vercel React app + TypeScript API -> public FPL API
                                      |       -> Supabase
GitHub Actions -> Python projections + optimizer -> Supabase -> Resend
```

- `apps/web`: Vite, React and TypeScript product.
- `api`: same-origin Vercel functions.
- `packages/contracts`: shared runtime schemas.
- `packages/quick-solver`: bounded interactive next-deadline solver.
- `python/fpl_andres`: rules, ingestion, models, backtests and optimizer.
- `supabase`: local configuration and forward-only migrations.

## Local development

Prerequisites: Node 20.19+, Python 3.12+, and Docker Desktop for the local database.
No global pnpm or Supabase installation is required.

```powershell
corepack pnpm install
python -m pip install -e ".[dev]"
corepack pnpm dev
```

Run the complete available validation suite:

```powershell
corepack pnpm check
```

Run the deterministic browser matrix separately. It covers desktop/mobile Chromium,
360 px reflow, keyboard navigation, reduced motion, forced colors, stale/error states,
and automated axe checks without calling live FPL:

```powershell
corepack pnpm test:e2e
```

Start Supabase after Docker Desktop is running:

```powershell
corepack pnpm exec supabase start
```

`docs/DEVELOPMENT.md` covers the parts that go wrong: seeding a database that
starts empty, inspecting local data, debugging an API route that only exists as a
serverless function in production, and why a build passes locally and fails in
CI. `docs/TESTING.md` covers the test loops and the seeding strategy.

The Windows Supabase executable may be blocked by local application-control policy.
CI uses Linux; local SQL policy tests continue to run without the CLI, and the project
can use the official CLI container where machine policy permits it.

## Secrets

Copy [.env.example](.env.example) to `.env.local` only when provider-backed work
begins. Values without `VITE_` are server-only. Never put a Supabase secret key or
Resend key in a `VITE_` variable.

Owner-only external setup is intentionally short and lives in
[docs/OWNER_SETUP.md](docs/OWNER_SETUP.md).

## License

Project-authored code is currently all rights reserved while the source-code license
is selected. Vendored development guidance retains its own licenses; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
