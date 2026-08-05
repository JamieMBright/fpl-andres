# API surface

Three serverless functions under `api/`. All are same-origin by design: the web
application and the functions ship from one Vercel deployment, so no CORS
headers are sent and none are needed. A cross-origin caller will be refused by
the browser, which is the intent — these proxies exist to serve this site, not
to be a public API.

None of them require authentication, because none of them expose anything that
is not already public. A Team ID is a public identifier.

## `GET /api/health`

Liveness. Returns commit SHA and environment.

| Status | Meaning                  |
| ------ | ------------------------ |
| 200    | The function is running. |

`maxDuration` is 5 seconds: it does no upstream work and should never approach
the limit the proxies need.

## `GET /api/fpl/*`

Allow-listed read-through proxy to `https://fantasy.premierleague.com/api/`.
The path is matched against an allow-list **before** any upstream request is
made; an unrecognised path never reaches FPL.

| Status | Meaning                                                                                                                                                                                                            |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 200    | Upstream returned JSON and it was within the size limit, **or** a retained copy was served.                                                                                                                        |
| 400    | The path is not allow-listed, or a query parameter is not permitted.                                                                                                                                               |
| 502    | A JSON error envelope. For deliberate proxy failures (e.g. upstream unreachable with no retained copy) the body is `{ error, reason }`; for unexpected handler failures the body additionally carries `requestId`. |

### Retained copies

A public document — `bootstrap-static/`, `fixtures/`, `element-summary/` — is
the same for every caller and changes a handful of times an hour, so the proxy
holds two things per warm instance: a short-TTL copy that suppresses duplicate
upstream reads, and the last copy that was known to be good. When FPL does not
answer, the retained copy is served instead of a 502.

It is never disguised as current. A retained copy carries:

- `X-FPL-Stale: 1`
- `X-FPL-Stale-Age` — seconds since capture
- `X-FPL-Captured-At` — ISO 8601 capture instant
- `Cache-Control: public, s-maxage=30, stale-while-revalidate=600`

The site reads these and says, in words, that the list is not current. A per-manager
path (`entry/`, `picks/`, `leagues-classic/`) is never retained and never shared:
it fails as before.

Only a 200 is retained. An error status is never held, so one bad second does
not become a minute of served failure.

Each request logs an `fpl_proxy_tier` line naming which tier answered —
`fresh`, `reused`, `stale` or `failed` — because a page rendered from a
retained copy is indistinguishable from a healthy one from the outside.

Response headers on a failure:

- `x-fpl-andres-request-id` — quote this when reporting. The detail is in the
  server log under the same id, never in the response.
- `Cache-Control: no-store`
- `X-Content-Type-Options: nosniff`

`maxDuration` is 15 seconds against an internal budget of 12 seconds, so the
function returns its own degraded envelope rather than being killed mid-flight
by the platform. A platform kill produces no envelope and no log line.

## `GET /api/team/:id`

Composes the public state of one FPL team: last-deadline picks, bank, value.

| Status | Meaning                                                         |
| ------ | --------------------------------------------------------------- |
| 200    | `{ status: "ready", state }` or a valid `unavailable` envelope. |
| 400    | The id is not a positive integer within range.                  |
| 503    | `{ status: "degraded", reason, requestId }`.                    |

### Degraded and unavailable reasons

| Reason               | Meaning                                                                                                                     | What the site shows                                                                                                                                                                                                                                                             |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fpl_source_failed`  | Upstream did not answer within budget, or answered with something unusable.                                                 | A cached snapshot marked stale if one exists, otherwise a retry prompt.                                                                                                                                                                                                         |
| `no_processed_event` | FPL has not processed a gameweek yet. Normal between seasons: `/entry/{id}/` returns `current_event: null` after the reset. | An explanation that the season has not started, the manager's own record, which is still real, and a rule-checked builder for the fifteen he is starting with. That squad is his own claim, kept in his browser, and the season plan solves from it as if played in gameweek 1. |
| `entry_unavailable`  | The Team ID does not resolve to a manager.                                                                                  | A correction prompt.                                                                                                                                                                                                                                                            |
| `picks_unavailable`  | The manager exists but the picks for the last event cannot be read.                                                         | The dossier without a squad, stated plainly.                                                                                                                                                                                                                                    |

Every reason is a value in the contracts package, so the site cannot render one
it does not understand.

`maxDuration` is 15 seconds for the same reason as the proxy: it makes two
upstream calls and needs headroom over the internal budget.

## What none of them do

- No writes. The database is never touched from `api/`.
- No secrets. The functions hold no Supabase credential.
- No rate limiting yet. Tracked as improvement #72 in `IMPROVEMENTS.md`; both
  proxies are currently unmetered per client.
