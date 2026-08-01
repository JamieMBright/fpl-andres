# Operations

What this deployment emits, what to watch, and what is deliberately not covered.

Audit items #72, #85, #92, #93.

---

## The signal

Every serverless handler writes newline-delimited JSON to stdout and stderr.
Vercel drains both to its log stream, and every hosted log service ingests that
format without a client library. No vendor SDK is installed and no vendor is
assumed.

That is a deliberate split. Emitting a line an alert can be written against is
a code decision and it is done. Choosing where the lines are shipped, and what
pages someone, is an infrastructure decision with a bill attached, and it is
the owner's. This document is the handover between the two.

Nothing in these lines carries a payload fragment, an upstream body, a header
value, a manager name or an email. Status codes, durations, counts, route
templates and fixed strings only. The one identifier present is a per-request
UUID minted on the spot, which correlates lines within a request and means
nothing outside it.

### `handler_outcome`

One per request to `/api/team/:id`.

| Field        | Meaning                                                     |
| ------------ | ----------------------------------------------------------- |
| `status`     | HTTP status returned to the client                          |
| `reason`     | Refusal reason, or `null` when the response was `ready`     |
| `totalMs`    | Wall clock for the whole handler                            |
| `upstreamMs` | Time spent waiting on FPL, summed across concurrent fetches |
| `localMs`    | `totalMs - upstreamMs`, floored at zero                     |

`upstreamMs` can exceed `totalMs` because the entry and bootstrap fetches
overlap. That is the intended reading: it is time spent waiting on FPL, not
elapsed time. `localMs` is therefore a lower bound on our own work, which is
the conservative direction — it never blames FPL for time we spent.

The split is the point. A slow handler that spent its time waiting on FPL is a
different problem from one that spent it parsing, and only the second is ours.

### `upstream_outcome`

One per upstream source (`entry`, `bootstrap`, `picks`), with `status`,
`reason` and `durationMs`. `level` is `warn` when the source could not be read.

### `source_contract_failed`

Emitted when an FPL payload no longer matches its schema. Carries
`upstreamStatuses` — the status each source returned — and up to five failing
field paths with their Zod issue codes.

The statuses are what make this diagnosable. A `200` that fails the contract is
a schema change and needs a code fix. A `403` that fails it is a block page
that got past the content-type check and needs a different response entirely.
Before #92 these were indistinguishable in the log, and reproducing either
meant waiting for it to happen again.

### `handler_failure`

An unexpected throw. Carries `requestId`, `route`, `status`, `durationMs`,
message and stack. The client gets only the opaque `requestId`, echoed in the
`x-fpl-andres-request-id` header.

### `rate_limited`

A refusal, with `scope` set to `client` or `global`. A steady trickle is the
limit working. A step change is either an attack or a limit set too low, and
those look identical in a 429 count alone — the `scope` field separates them.

---

## Alerts worth having

These are written as conditions rather than as one vendor's query language.
Windows are suggestions; tune them against a fortnight of real traffic before
paging anyone.

**Sustained upstream failure.** `upstream_outcome` with `level` = `warn`
exceeding a quarter of all `upstream_outcome` lines over fifteen minutes. FPL
is down, rate limiting this deployment, or has moved an endpoint. Page.

**Contract break.** Any `source_contract_failed` line. This should be zero.
One is a coincidence, two in an hour is a schema change and the site is
serving `degraded` to everyone. Page.

**Latency regression, ours.** Ninety-fifth percentile `localMs` over one
second across thirty minutes. Upstream is not the problem; something in
parsing or assembly is. Ticket, not a page.

**Latency regression, theirs.** Ninety-fifth percentile `upstreamMs` over five
seconds across thirty minutes. Nothing to fix here, but it precedes a wave of
`fpl_unreachable` and is worth knowing before the reports arrive.

**Global rate limit tripping.** `rate_limited` with `scope` = `global`. The
per-client limit is not holding and traffic is arriving from many addresses.
Page: this is the shape of an attack, and the ceiling is the last thing between
it and the FPL API.

**Unexpected throw.** Any `handler_failure`. Should be zero.

---

## The request budget

`/api/fpl/*` and `/api/team/*` are unauthenticated proxies onto a third party's
API. Anyone can point a loop at them, and the cost lands twice: on this
deployment's function-seconds, and on the Premier League's servers under this
project's user agent. The second is the one that gets a project blocked.

| Endpoint        | Per client, per minute | Per instance, per minute |
| --------------- | ---------------------- | ------------------------ |
| `/api/fpl/*`    | 60                     | 600                      |
| `/api/team/:id` | 20                     | 200                      |

`/api/team/:id` is lower because one call fans out to three upstream requests,
one of which is the 1.3 MB bootstrap document.

Refusals answer `429` with `Retry-After` and `RateLimit-Limit` /
`RateLimit-Remaining`. Allowed requests carry the same two headers, so a
well-behaved client can slow down before it is refused.

### What it does not cover

The counters are in memory, per instance. With several warm instances a client
gets the per-client budget several times over.

This is a real limitation, not an oversight, and it is written here rather than
implied by silence. A genuinely global limit needs shared state that survives
across instances. The two ways to get it are Vercel's WAF, which is
configuration rather than code, or a Redis this project would have to run. Both
are owner decisions with a bill, and neither is something to adopt by default
on the way past.

What the in-memory version does cover is the case that actually happens: a
script left in a loop, a page re-rendering in a cycle, one person hammering.
Those land on one instance and are stopped there.

The client key comes from `x-vercel-forwarded-for`, falling back to
`x-real-ip`. Both are set by the platform and overwrite any inbound copy.
`x-forwarded-for` is deliberately ignored: it arrives from the caller, so
keying on it would let one client present as a million and never meet the limit
at all. Off-platform, where neither header exists, every caller shares the key
`unattributed` — the per-client limit then behaves as a second global limit
rather than as no limit, which is the safe direction to fail.

The tracking table is capped at five thousand addresses. An unbounded map keyed
by client address is itself a denial of service: a million addresses would
exhaust the function's memory rather than its budget. When the cap is reached
the limiter sweeps expired windows first; if the table is still full it keeps
serving and says so, leaving the global ceiling as the only limit in force.
Refusing instead would turn a memory bound into an outage for whoever arrived
last.

---

## Wiring a sink

Nothing below is installed. It is recorded so the decision starts from the
constraints rather than from a search.

The requirements are: ingests newline-delimited JSON from a Vercel log drain,
supports a numeric threshold over a rolling window, and does not require a
vendor SDK in the function — that last one matters because the bundle has a
size budget enforced in CI, and because an SDK in the request path is another
thing that can fail inside a handler whose job is to report failures.

Vercel's own Log Drains satisfy the transport for any HTTP endpoint. The
alerting layer is the open choice.

Whatever is chosen, the field names above are the contract. They are asserted
in `apps/web/src/api/team-public-state-observability.test.ts` precisely because
a rename that keeps the line but loses a field breaks the alert silently, and
nothing else would notice.
