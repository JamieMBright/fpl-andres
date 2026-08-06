# Platform, API, frontend, testing and operations

Audit E. Everything outside the model. Findings verified against the source
during the audit.

Scores are on the scale in [`IMPROVEMENTS.md`](../../IMPROVEMENTS.md).

---

## E1. The rate limit scales with the thing it is defending against

**Score 7. Do.** `api/_lib/rate-limit.ts`

The limiter is a `Map` on a module-scope instance:

```ts
readonly #clients = new Map<string, Window>();
#global: Window = { count: 0, resetAt: 0 };
```

Vercel runs many instances. The "600 requests a minute global" ceiling on
`/api/fpl/*` is therefore `600 × warm instances`, and warm instances scale up
under load. The only barrier between this site and an FPL block grows in
proportion to the traffic it is meant to stop.

The module doc states the limitation plainly and `docs/OPERATIONS.md` records
the mitigation as an owner decision (Vercel WAF or Redis). Rated 7 because the
consequence is being blocked by the single upstream the whole site depends on,
which is a full outage with no self-service recovery.

**Fix.** Shared state. Upstash Redis is the conventional answer on Vercel and
the limiter's interface already isolates the store well enough to swap it.

---

## E2. Hardcoded numbers in prose, again

**Score 8. Do.** `apps/web/src/components/Methodology.tsx`

Five blocks of quantitative claims are string literals with no link to the
artifact rendered beside them:

| Line ~  | Claim                                                                             |
| ------- | --------------------------------------------------------------------------------- |
| 29      | defensive contribution was `7.5%` of every point awarded                          |
| 34–41   | `34,383` against an actual `34,382`; `27,353 of 27,605` reconcile exactly         |
| 58–74   | within `0.07`; `0.616` and `0.605`; `0.646`; `42%` vs `10%`                       |
| 104–114 | `0.012`, `0.019`, `0.020`; `83%` of the top thirty                                |
| 280–299 | `127` paired gameweeks; `0.15`; `−0.34 to +0.69`; `1.20`; `1.57`; `15.45`; `7.12` |

This is the failure mode `state/validation-verdict.ts` was written to prevent,
reappearing one file over. The calibration page claimed the naive baseline was
winning for months after the artifact reversed; that is what these will do the
next time CI reruns the backtest.

The last block is the worst of them because it was written **in this session**,
citing intervals that CI produced an hour earlier, in prose, by hand.

**Fix.** Derive from `validation.json` at render time, as `ValidationReport`
already does. Where a number genuinely cannot be derived — a one-off measurement
from a session that will not be repeated — stamp it with the date and the commit
it was measured at, so a reader can tell a live number from a historical one.

---

## E3. `/plan` and `/analysis` have no functional browser test

**Score 7. Do.** `apps/web/e2e/`

Six spec files. Coverage by route:

| Route          | Functional coverage                                                                |
| -------------- | ---------------------------------------------------------------------------------- |
| `/`            | yes — form entry, mobile, failure states                                           |
| `/team/:id`    | yes — every envelope status, five stale reasons, three degraded, three unavailable |
| `/methodology` | title and navigation only                                                          |
| `/players`     | title, plus part of the season-price walk                                          |
| `/calibration` | title and navigation only                                                          |
| `/plan`        | **contrast and responsive scans only**                                             |
| `/analysis`    | **contrast and responsive scans only**                                             |
| `/kits`        | **none at all**                                                                    |
| 404            | none                                                                               |

`/plan` runs the beam search in a worker and renders a 38-gameweek plan — the
most complex integration in the application — and nothing asserts that the
output is coherent. The contrast and responsive scans prove only that it renders
without axe violations and without horizontal overflow.

The team-analysis coverage, by contrast, is genuinely thorough and is the model
the other routes should follow.

---

## E4. Corrupt localStorage is swallowed without being cleared

**Score 3. Do.** `apps/web/src/state/declared-transfers.ts`

```ts
const parsed = storedSchema.safeParse(JSON.parse(raw));
return parsed.success ? parsed.data.filter(...) : [];
```

Every other reader in the codebase — `team-state-overrides.ts`,
`declared-squad.ts`, `team-analysis.ts` — calls `storage.removeItem(key)` when
the schema fails, so the same corrupt value is not re-parsed forever. This one
returns `[]` and leaves it.

Self-heals on the next write, so the consequence is small. Listed because the
inconsistency is the kind that gets copied.

---

## E5. Two timeout budgets that add up to more than the platform allows

**Score 4. Do.** `api/_lib/team-public-state-response.ts`, `vercel.json`

`PICKS_BUDGET_MS = FPL_PROXY_BUDGET_MS` (12 s). A request that has already spent
11 seconds on entry and bootstrap can still hand `picks/` a fresh 12-second
budget — 23 seconds of wall clock against a `maxDuration: 15` on
`api/team/*.ts`.

The result is a `FUNCTION_INVOCATION_TIMEOUT` rather than the degraded envelope
the code was written to return, so a slow upstream produces a platform error
instead of an honest "degraded" response.

**Fix.** Deduct elapsed time from the remaining budget before the second fetch.

---

## E6. The error boundary renders exception text to the page

**Score 3. Owner decision.** `apps/web/src/components/ErrorBoundary.tsx`

```tsx
<span className="error-detail-kind">{error.name}</span>;
{
  error.message;
}
```

Production React minifies component names, but explicitly constructed messages
survive — Zod issue strings, contract errors, anything thrown with a formatted
message. Those can name internal fields.

Whether that matters is a judgement about how much internal structure the owner
minds exposing. It is not a security hole; the API side is careful and returns
only an opaque `requestId`.

---

## E7. Property-based testing covers five files; the riskiest are not among them

**Score 5. Do.**

Hypothesis is used in `test_ingest_properties.py`, `test_statistical_invariants.py`,
and one invariant each in the HiGHS, horizon and minutes tests.

Not property-tested: `rules.py`, `bootstrap.py`, `team_state.py`,
`backtesting/score.py`, `optimization/contracts.py`, `persistence/supabase.py`.
Mutation testing covers the first and fourth — 63 of 63 mutants killed, which is
a strong result — leaving `bootstrap.py`, `team_state.py`,
`optimization/contracts.py` and `persistence/supabase.py` with neither.

`rules.py` and `bootstrap.py` are where a wrong bounds check silently mispays
points, which makes them the highest-value targets for generated inputs.

---

## E9. The canary's stated policy was unimplementable — fixed

**Score 8. Done.** `.github/workflows/canary.yml`

The workflow said, in its own comment:

> A degraded response is FPL being unreachable, which is worth knowing but is
> not this deployment failing. Reported, not alarmed.

It could not do that. `degradedResponse` in
`api/_lib/team-public-state-response.ts` serves the envelope with **HTTP 503**,
and the probe checked the status code first:

```bash
if [ "$team_code" != "200" ]; then
  failures="${failures}- /api/team returned ${team_code}\n"
elif ! printf '%s' "$team_body" | grep -qE '"status":"(ready|unavailable|degraded)"'; then
```

So a degraded body never reached the branch written to tolerate it. Every FPL
blip opened an incident: **seven of the first thirty-eight scheduled runs
failed this way**, at 7–16 seconds each. The workflow's other comment — "an
alert that floods is an alert people mute" — describes what it did to itself.

**Fixed** by reading the body before the status code, and by splitting the three
degraded reasons rather than treating them alike. That split also closes the
other half of [D2](04-data-and-sources.md#d2-the-live-contract-test-does-not-check-the-field-the-site-depends-on):

| Response                                 | Verdict                        |
| ---------------------------------------- | ------------------------------ |
| 200 `ready` / `unavailable`              | pass                           |
| 503 `degraded`, `fpl_unreachable`        | pass, noted — upstream         |
| 503 `degraded`, `fpl_source_failed`      | pass, noted — upstream         |
| 503 `degraded`, `source_contract_failed` | **alarm** — FPL changed shape  |
| any other non-200                        | **alarm** — the site is broken |
| 200, unrecognised status                 | **alarm** — our shape changed  |

`source_contract_failed` means FPL answered in a shape this deployment does not
understand, so every dossier degrades until the contract is updated. That is
ours, and it is the one worth waking up for.

Pinned by `python/tests/test_canary_probe.py`, which asserts against the real
workflow text — including that the API still serves degraded with a 503, so if
that ever changes the test says so rather than the canary silently reverting to
noise.

**Not fixed, and not fixable here:** runs #37 and #38 failed at 15 minutes with
`The job was not acquired by Runner of type hosted even after multiple
attempts` and an internal-server-error correlation id. That is GitHub
infrastructure, not this repository.

---

## E10. The crowd capture has never once succeeded — diagnosed

**Score 8. Owner decision.** `.github/workflows/capture-crowd.yml`,
`python/fpl_andres/cli/capture_crowd.py`

Three scheduled runs since the job was written. Three failures, each about
twenty-five seconds. It has never worked.

The read half is fine — `--dry-run` returns 570 elements for 2026-27 GW1. The
write half hits a foreign key:

```sql
season text not null references public.seasons(season),
constraint crowd_snapshots_element_fk
    foreign key (season, element_id) references public.elements(season, element_id)
```

`seasons` and `elements` are filled by the historical ingest, which reads a
published archive — and an archive of a season only exists once that season has
been played. **A job whose entire purpose is capturing live pre-deadline
ownership depends on a corpus that cannot yet contain the season it is
capturing.** The corpus holds 2019-20 to 2025-26; the capture writes 2026-27.

This is a design problem rather than a typo, and the fix is an owner decision
because every option touches production data:

1. **Seed the season from the live bootstrap.** The bootstrap is the
   authoritative source for who exists this season, so a small job could insert
   the `seasons` row and the current `elements` before the first capture. It
   means live-derived rows land in tables the backtest reads, which needs
   thinking about.
2. **Drop the two foreign keys.** Cheapest, and it removes a real integrity
   guarantee. Not recommended.
3. **Accept that capture starts once the season is ingested**, and turn the
   schedule off until then. Loses the pre-season ownership series, which is
   part of what the table was for.

**What is fixed here:** the failure now says what is wrong, before anything is
written. It was surfacing as an opaque PostgREST status because the check
happened inside the database, and the old ordering wrote a `source_snapshots`
row _before_ the failing insert — leaving an orphan behind on every run.

---

## E8. Things checked and found sound

Recorded so they are not re-audited.

- **The FPL proxy is not an open proxy and I could not find an SSRF bypass.**
  Six anchored path shapes, bounded integer ranges, percent-encoded traversal
  rejected, `redirect: "error"` so a 302 to another host throws, a
  post-resolution string-equality check against the allow-listed URL, strict
  media-type parsing and a length-bounded body. This is genuinely well built.
- **The Supabase secret cannot reach a browser or a log.** Server-only,
  `Prefer: return=minimal` on insert, and only the HTTP status travels into the
  thrown error — never the response body, which would echo the manager's squad.
- **No route leaks internal detail.** Every failure returns an opaque
  `requestId`; Zod errors expose field paths and never values. The
  `x-fpl-andres-debug` header that used to carry exception text is gone and the
  reason is documented.
- **Both gitleaks allowlists set `condition = "AND"` explicitly**, are anchored
  to one path each, and the config documents the OR-default trap along with the
  planted-secret verification that proves the fix works.
- **Retry, timeout, coalescing and last-known-good are well designed.** Failed
  reads are never cached; stale copies carry `X-FPL-Stale` headers so they are
  never presented as fresh.
- **No floating-point equality bugs** in the frontend. The one rounded value
  used as an index cannot flip an ordering.
- **No tautological tests and no re-implementation of code under test.** One
  conditional skip, environmental and honest. No `xfail` anywhere.
- **Coverage excludes nothing.** `exclude_also` holds three narrow patterns and
  there is no `omit` list, so the 77% branch floor is measured over everything.
