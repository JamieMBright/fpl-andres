# Suppressed advisories

Audit item #79. `package.json` carries a `pnpm.auditConfig.ignoreGhsas` list.
An entry there silences a real finding, and a silence with no reason attached
becomes permanent by inertia: nobody remembers why it was added, so nobody
removes it.

Every entry must appear below with the reason, the date it was assessed, a
review date, and the specific thing that would make the reason false. The last
one matters most. A justification that cannot become false is not a
justification, and one that can become false silently is worse than none.

`python/tests/test_suppressed_advisories.py` checks that the list here and the
list in `package.json` are the same set, that no review date has passed, and —
where it can — that the stated reason still holds.

---

## GHSA-qwww-vcr4-c8h2

|           |                                                                  |
| --------- | ---------------------------------------------------------------- |
| Package   | `react-router` (via `react-router-dom` 7.18.2)                   |
| Title     | RSC Mode CSRF Bypass Allows Action Execution Before 400 Response |
| Severity  | High, CVSS 7.1                                                   |
| Affected  | `>= 7.12.0, < 8.3.0`                                             |
| Patched   | `8.3.0`                                                          |
| Assessed  | 2026-08-01                                                       |
| Review by | 2026-11-01                                                       |

### Why it is suppressed

The advisory's own text is explicit: "This only affects your application if you
are using the unstable RSC APIs."

This app does not. It is a static single-page build served by Vite. Routing is
`createBrowserRouter` in `apps/web/src/main.tsx`, entirely in the browser.
There is no React Server Components runtime, no server-side router, no loader
or action executing on a server, and therefore no request that could reach an
action before a 400 — the code path the advisory describes does not exist in
this deployment.

The serverless functions under `api/` are plain handlers. They do not import
`react-router` and do not participate in routing.

### What would make this false

Any one of these, and the suppression must be removed and the upgrade taken:

- adopting the RSC APIs, or any `unstable_` router export
- moving to a framework that runs the router on a server (Remix, React Router
  in framework mode, a Next.js port)
- introducing router `action` functions that execute anywhere but the browser

The first and third are checked by the test: it fails if an `unstable_` router
import or a router `action` appears in the source. The second is a decision
large enough that nobody makes it by accident, but the review date is there to
catch it if they do.

### Why not simply upgrade

Version 8.3.0 is a major version of `react-router`. Taking a major upgrade to
close a vulnerability in a code path this project does not execute would be
spending review effort on the wrong thing, and a major upgrade is exactly the
kind of change that needs review effort. It is scheduled rather than refused:
the review date is when this is reconsidered, and by then the 8.x line will
have had time to settle.
