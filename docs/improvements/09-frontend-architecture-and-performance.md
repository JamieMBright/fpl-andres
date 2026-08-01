# 9. Frontend architecture and performance — work orders

Detailed briefs for items 109–125 of the [improvement audit](../../IMPROVEMENTS.md).
Each brief is self-contained: a sub-agent should be able to implement one item
from its brief alone.

Every brief obeys the repository rules: test-first, follow `DESIGN.md` and the
repository design skills for any visual work, never expose a Supabase secret,
Resend key or subscriber email to browser code or logs, and keep manual
team-state overrides separate from public last-deadline state.

---

## 109 — Add a React error boundary around the router (Impact: H)

**Files**: `apps/web/src/main.tsx` (lines 16–20), new
`apps/web/src/ErrorBoundary.tsx`, new
`apps/web/src/ErrorBoundary.test.tsx`

**Problem**: `main.tsx` renders `<RouterProvider router={router} />` directly
inside `<StrictMode>` with no error boundary. Any render-time exception thrown
by a route component (e.g. a failed JSON parse surfaced as a thrown error,
or a Lucide icon prop mismatch) propagates uncaught and blanks the entire
viewport without any user-facing message.

**Change**:

1. Create `apps/web/src/ErrorBoundary.tsx` exporting a class component
   `ErrorBoundary` that implements `getDerivedStateFromError` and `componentDidCatch`.
   Its fallback render must match the design tokens in `styles.css`
   (`--paper`, `--ink`, `--danger`, `var(--fa-body)`) and display Andres's
   voice for an unexpected failure — short, honest, with a reload affordance.
2. Wrap the `<RouterProvider>` in `main.tsx` with the new `<ErrorBoundary>`
   so the boundary sits outside the router.
3. Do not catch errors intentionally thrown by business logic; the boundary is
   a last-resort safety net only.

**Constraints**: The existing `App.test.tsx` suite and every Playwright journey
in `apps/web/e2e/` must remain green. The fallback UI must use design tokens
from `styles.css`, never hard-coded colours. No Supabase credential or API key
may appear in the fallback.

**Tests first**: Create `apps/web/src/ErrorBoundary.test.tsx`. Assert (a) a
child that throws renders the fallback instead of crashing; (b) a child that
does not throw renders normally; (c) the fallback contains a visible "reload"
or equivalent affordance (query by role `button` or accessible text).

**Done when**:

- `ErrorBoundary` is exported from its own file and imported in `main.tsx`.
- Deliberately throwing inside a route component in tests triggers the fallback
  UI, not an unhandled-error blank screen.
- All existing `App.test.tsx` assertions pass unchanged.
- The fallback contains no hard-coded hex values.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test` then
`corepack pnpm test:e2e`.

---

## 110 — Code-split routes with `React.lazy` and `Suspense` (Impact: H)

**Files**: `apps/web/src/App.tsx` (lines 866–879, the `routes` array), new per-
route files under `apps/web/src/pages/`, `apps/web/src/main.tsx`

**Problem**: Every route component — `HomePage`, `TeamAnalysisRoute`,
`PlayerPoolPage`, `MethodPage`, `CalibrationPage`, `NotFoundPage` — is defined
in `App.tsx` and ships in the initial bundle. Visitors who land on `/` download
the full `ValidationReport`, `TeamStateCorrections` and `PlayerPoolTable`
JavaScript on first paint, even though they need none of it until they navigate.

**Change**:

1. Extract each route-level component (see item 115 for the full list) into its
   own file under `apps/web/src/pages/`, e.g. `pages/HomePage.tsx`,
   `pages/TeamAnalysisPage.tsx`, `pages/PlayerPoolPage.tsx`,
   `pages/MethodPage.tsx`, `pages/CalibrationPage.tsx`,
   `pages/NotFoundPage.tsx`.
2. Replace each static import in the `routes` array with `React.lazy(() =>
import("./pages/…"))`.
3. Wrap the `<RouterProvider>` (or the `<Outlet>` inside `ApplicationFrame`) in
   a `<Suspense fallback={…}>` with a skeleton that respects the Teletext
   aesthetic (see item 121 for the skeleton detail).
4. Name each dynamic chunk via a Vite magic comment (`/* @vite-ignore */` is
   not appropriate; use the `/* webpackChunkName */` / Vite `/* rollupChunk */`
   approach — see item 125 for naming).

**Constraints**: The `routes` export consumed by `main.tsx` must keep its
`RouteObject[]` type. `ApplicationFrame`, `BielsaBucket`, and `RouteHeading`
stay in `App.tsx` (or a shared `components/Shell.tsx`) because they are needed
on every route. Playwright journeys in `apps/web/e2e/` must pass without
modification.

**Tests first**: Add a test in `apps/web/src/App.test.tsx` that verifies each
lazy route renders its expected heading (query by `role="heading"`) after
suspense resolves. Wrap the render in `<Suspense>` in the test.

**Done when**:

- The initial entry chunk contains `ApplicationFrame` but not `ValidationReport`
  or `PlayerPoolTable` (verifiable with `pnpm --filter @fpl-andres/web build
&& grep` on the dist manifest).
- Each route renders its heading correctly in the test suite.
- No Playwright journey fails.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test` then
`corepack pnpm test:e2e`.

---

## 111 — Load large JSON artifacts on demand (Impact: H)

**Files**: `apps/web/src/state/fixture-run.ts` (line 1, static
`projections.json` import), `apps/web/src/state/squad-projection.ts` (line 1,
static `projections.json` import), `apps/web/src/components/ValidationReport.tsx`
(line 1, static `validation.json` import), `apps/web/src/components/OpeningSquad.tsx`
(line 1, static `opening-squad.json` import),
`apps/web/src/components/StatusStrip.tsx` (line 1, static
`opening-squad.json` import), `apps/web/src/data/`

**Problem**: All three large JSON artifacts — `projections.json`,
`validation.json`, and `opening-squad.json` — are statically imported at module
evaluation time. They ship in the initial bundle even for visitors who only use
the home-page Team ID form. `projections.json` is the heaviest because it
carries every player's projection record.

**Change**:

1. Replace the static `import projections from "../data/projections.json"` in
   `fixture-run.ts` and `squad-projection.ts` with an async loader function
   (e.g. `loadProjections(): Promise<ProjectionsShape>`) that calls
   `import("../data/projections.json")` and caches the result in a module-level
   variable on first call.
2. Update every call-site inside `fixture-run.ts` and `squad-projection.ts`
   that currently reads the synchronous import to `await loadProjections()`.
   Expose the loader in the module's public API if callers outside the module
   need it.
3. Replace the static `import validation from "../data/validation.json"` in
   `ValidationReport.tsx` with `React.lazy` / `Suspense` or a `useEffect`
   loader that fetches the JSON at mount time.
4. Unify the two imports of `opening-squad.json` (`OpeningSquad.tsx` and
   `StatusStrip.tsx`) behind a shared async loader in
   `state/opening-squad.ts` (new file), and update both components to call it.
5. Ensure loading states are shown while async data resolves (loading skeleton
   or existing `"Reading your history…"` pattern).

**Constraints**: The inferred TypeScript types of the JSON shapes must be
preserved — derive them from Zod schemas if the shapes are validated, or use
`typeof import(…)` where they are not. The `squad-projection.test.ts` and
`fixture-run.test.ts` suites must continue to pass; mock the dynamic import in
tests if needed.

**Tests first**: Add a test in `apps/web/src/state/squad-projection.test.ts`
(and `fixture-run.test.ts`) that mocks `import("../data/projections.json")` and
asserts the loader resolves to the mocked value without reading the real file.

**Done when**:

- `projections.json`, `validation.json`, and `opening-squad.json` are absent
  from the initial entry chunk (verifiable via `pnpm build` dist manifest).
- All existing unit tests in `squad-projection.test.ts` and
  `fixture-run.test.ts` pass.
- No Playwright journey fails.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test` then
`corepack pnpm test:e2e`.

---

## 112 — Use `AbortController` for the fetch in `ManagerHistory` (Impact: H)

**Files**: `apps/web/src/components/ManagerHistory.tsx` (lines 38–57, the
`useEffect` hook)

**Problem**: The `useEffect` in `ManagerHistory` (lines 38–57) sets a `let
cancelled = false` flag and skips the `setLoaded` call on unmount, but the
`fetch("/api/fpl/entry/${entryId}/history/")` itself is never aborted. If the
user changes the Team ID quickly or navigates away, the browser continues
maintaining the in-flight HTTP connection until it resolves, burning network
budget and potentially causing a state-update error if React's strict-mode
double-invocation fires.

**Change**:

1. Create an `AbortController` inside the `useEffect`, passing
   `controller.signal` as the `signal` option of the `fetch` call.
2. In the `useEffect` cleanup, call `controller.abort()` instead of setting a
   `cancelled` flag; remove the `cancelled` variable entirely.
3. Wrap the `fetch` in a `try/catch` that ignores `AbortError` (check
   `error instanceof DOMException && error.name === "AbortError"`) and treats
   all other errors as a null profile.

**Constraints**: The `ManagerHistory` component's rendered output and prop
interface must not change. No new props, no new context. The existing
Playwright journey in `apps/web/e2e/feature-walk.spec.ts` that exercises the
team-analysis route must continue to pass.

**Tests first**: In a new `apps/web/src/components/ManagerHistory.test.tsx`,
assert (a) the fetch is called with a signal; (b) when the component unmounts
before the fetch resolves, the signal is aborted (`signal.aborted === true`);
(c) an aborted fetch does not call `setLoaded` (verify by checking no state
update occurs after unmount).

**Done when**:

- `ManagerHistory.tsx` contains no `cancelled` variable.
- The `fetch` call passes `{ signal: controller.signal }`.
- `useEffect` cleanup calls `controller.abort()`.
- The new `ManagerHistory.test.tsx` assertions pass.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test`.

---

## 113 — Add bounded retry with backoff for transient API failures (Impact: H)

**Files**: `apps/web/src/state/team-analysis.ts` (lines 91–155,
`refreshTeamAnalysis`), `apps/web/src/state/team-analysis.test.ts`

**Problem**: `refreshTeamAnalysis` (lines 91–155) makes a single attempt at
`/api/team/:entryId`. Any network blip — a transient 503, a momentary DNS
hiccup, a flaky mobile connection — immediately resolves to a terminal
`{ status: "error", reason: "network_error" }` state, forcing the user to
manually press "Retry analysis". A brief automatic retry is standard practice
for recoverable failures.

**Change**:

1. Add a `maxAttempts` parameter (default 3) and a `delayMs` parameter (default 500) to `RefreshDependencies` (or accept them as top-level arguments with
   defaults).
2. Wrap the `fetchApi` call in a retry loop: on a network catch or a non-2xx
   response that is clearly transient (5xx), wait `delayMs * attempt` ms before
   the next attempt (linear backoff is sufficient).
3. Only promote to the terminal error/stale state after all attempts are
   exhausted.
4. Pass the `AbortSignal` through each attempt; stop retrying immediately if the
   signal is aborted.
5. Keep the existing fast-path: 4xx (e.g. 404 `entry_unavailable`) is not
   retried because it is not transient.

**Constraints**: The `TeamAnalysisState` union and `TeamAnalysisAction` types
must not gain new members for this item. The `team-analysis.test.ts` suite
must remain fully green. The `signal` abort must be respected between retry
attempts (do not sleep after abort).

**Tests first**: In `apps/web/src/state/team-analysis.test.ts`, add cases: (a)
two consecutive network failures followed by a success resolves to `"ready"`;
(b) three network failures resolves to `"error"`; (c) aborting the signal
during a retry sleep stops further attempts.

**Done when**:

- `refreshTeamAnalysis` retries up to three times on network error before
  returning terminal state.
- Retry delay is observable in tests via a mocked `setTimeout` or clock.
- Aborting via `AbortController` cancels remaining retries.
- All existing `team-analysis.test.ts` assertions pass.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test`.

---

## 114 — Break up `TeamStateCorrections` into focused sub-components (Impact: H)

**Files**: `apps/web/src/components/TeamStateCorrections.tsx` (720 lines),
new `apps/web/src/components/TransferDraftRow.tsx`,
new `apps/web/src/components/CorrectionForm.tsx`,
new `apps/web/src/components/CorrectionConfirmation.tsx`

**Problem**: `TeamStateCorrections.tsx` is the densest interactive surface in
the application at 720 lines. It handles the transfer-draft list rendering,
inline editing of each transfer row, form validation, and the save/confirm
dialogue all in one file. This makes targeted testing of any sub-behaviour
difficult and review surface disproportionately large.

**Change**:

1. Extract the per-row transfer draft edit surface into
   `TransferDraftRow.tsx`. Its props interface should include: the
   `TransferDraft` value, an `onChange` callback typed to `(draft:
TransferDraft) => void`, and an `onRemove` callback. It should own the
   four field inputs (`elementOutId`, `elementInId`, `sellingPrice`,
   `purchasePrice`) and the remove button.
2. Extract the summary confirmation panel (the save affordance and the
   displayed computed overrides) into `CorrectionConfirmation.tsx`. Its props:
   `overrides: TeamStateOverrides`, `onSave: () => void`, `onDiscard: () =>
void`, and `error: CorrectionError | null`.
3. Extract the full form shell (the outer `<form>`, the "add transfer" button,
   the list of `TransferDraftRow` instances, and the `CorrectionConfirmation`)
   into `CorrectionForm.tsx`.
4. `TeamStateCorrections.tsx` becomes the stateful orchestrator: it manages
   the `TransferDraft[]` array and calls `loadTeamStateOverrides` /
   `saveTeamStateOverrides`, delegating render to `CorrectionForm`.

**Constraints**: The external prop interface of `TeamStateCorrections` — a
single `state: PublicTeamState` prop — must not change. The behaviour tested by
any existing Playwright journey in `apps/web/e2e/` must be identical after the
refactor. No new Zod schemas; existing validation from
`team-state-overrides.ts` is the authority.

**Tests first**: Before splitting, write `apps/web/src/components/TeamStateCorrections.test.tsx`
(if absent) asserting the current save and discard flows by role. After
splitting, add tests in `TransferDraftRow.test.tsx` for field changes and the
remove callback, and in `CorrectionConfirmation.test.tsx` for the save/discard
button roles.

**Done when**:

- `TeamStateCorrections.tsx` is ≤ 200 lines.
- `TransferDraftRow`, `CorrectionForm`, and `CorrectionConfirmation` are each
  independently importable and tested.
- All Playwright journeys pass.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test` then
`corepack pnpm test:e2e`.

---

## 115 — Extract inlined route components from `App.tsx` (Impact: M)

**Files**: `apps/web/src/App.tsx` (lines 109–864), new files under
`apps/web/src/components/` and `apps/web/src/pages/`

**Problem**: `App.tsx` contains thirteen component definitions interleaved with
the route configuration: `BielsaBucket` (line 109), `RouteHeading` (line 153),
`ApplicationFrame` (line 164), `HomePage` (line 244), `TeamAnalysisRoute` (line
365), `TeamAnalysisPage` (line 370), `AnalysisResult` (line 450),
`EvidenceBanner` (line 534), `SnapshotDossier` (line 567), `MethodPage` (line
819), `PlayerPoolPage` (line 829), `CalibrationPage` (line 839), and
`NotFoundPage` (line 853). Each can only be tested as part of the full app
render, and any review of one function requires scrolling past all others.

**Change**:

1. Move `BielsaBucket` and `RouteHeading` to
   `apps/web/src/components/Shell.tsx` (shared presentation primitives).
2. Move `ApplicationFrame` to `apps/web/src/components/ApplicationFrame.tsx`.
3. Move `HomePage` to `apps/web/src/pages/HomePage.tsx`, along with the helper
   functions it alone uses (`parseTeamId`).
4. Move `TeamAnalysisRoute`, `TeamAnalysisPage`, `AnalysisResult`,
   `EvidenceBanner`, `SnapshotDossier`, and the helpers `formatFplMoney`,
   `pickAssignment`, `staleReason`, and `terminalStateMessage` to
   `apps/web/src/pages/TeamAnalysisPage.tsx`.
5. Move `MethodPage`, `PlayerPoolPage`, `CalibrationPage`, and `NotFoundPage`
   each to their own file under `apps/web/src/pages/`.
6. `App.tsx` retains only the `routes` array and its imports; the three
   module-level `Intl` formatter constants move with whichever file exclusively
   uses them (or to a shared `utils/formatters.ts` — see item 117).

**Constraints**: The exported `routes: RouteObject[]` from `App.tsx` must not
change its shape. All existing `App.test.tsx` test imports must resolve after
the move. No behaviour change is permitted; this is a file-boundary refactor
only. The invariant is: every Playwright journey passes before and after.

**Tests first**: For each extracted page, create a minimal `.test.tsx` that
mounts the component in a `MemoryRouter` and asserts the route heading renders
by `role="heading"`.

**Done when**:

- `App.tsx` is ≤ 30 lines (imports + `routes` export).
- Each extracted file is ≤ 200 lines.
- All `App.test.tsx` assertions and Playwright journeys pass unchanged.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test` then
`corepack pnpm test:e2e`.

---

## 116 — Virtualise long tables in `PlayerPoolTable` and `ValidationReport` (Impact: M)

**Files**: `apps/web/src/components/PlayerPoolTable.tsx` (lines 258–302),
`apps/web/src/components/ValidationReport.tsx` (lines 162, 224, 289, 418 —
each `tabIndex={0}` scrollable table), `apps/web/src/components/PlayerPoolTable.test.tsx` (new)

**Problem**: `PlayerPoolTable.tsx` hard-caps rendering at 200 rows (line 258:
`.slice(0, 200)`) and displays a message telling users to narrow filters instead
of scrolling. This hides data that users legitimately want to see. Rendering
more rows without virtualisation would degrade scroll performance for the ~600
players in the pool; capping arbitrarily is a suboptimal trade-off.

**Change**:

1. Integrate a windowed-list library (e.g. `@tanstack/react-virtual`) for the
   `<tbody>` in `PlayerPoolTable`. Each visible row mounts as before; only the
   visible slice renders to the DOM. The scroll container is the existing
   `.squad-table-wrap` div (already has `tabIndex={0}`).
2. Remove the `.slice(0, 200)` guard and the truncation notice at lines 297–302.
3. Preserve the `aria-label="Scrollable player list"` and
   `role="region"` attributes on the scroll container.
4. Apply the same technique to any `ValidationReport` table that exceeds ~50
   rows at runtime; if none does in practice, add a comment noting it is not
   yet needed and set a threshold test.

**Constraints**: The accessible table structure (`<table>`, `<thead>`, `<tbody>`,
`<th scope>`) must be preserved — virtualisation must not replace the table with
`<div>` rows. The `DESIGN.md` stripe-suppression rule for tabular content
applies. No new fonts or colour tokens.

**Tests first**: In a new `PlayerPoolTable.test.tsx`, assert (a) when more than
200 players are provided, all player names are eventually reachable in the DOM
(virtual scroll exposes them on scroll); (b) the truncation-notice element is
absent.

**Done when**:

- Rows beyond 200 are accessible by scrolling without a hard cap message.
- The table retains semantic `<table>` markup (no `role="row"` on `<div>`).
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test`.

---

## 117 — Share and memoise `Intl` formatters (Impact: M)

**Files**: `apps/web/src/App.tsx` (lines 49–64, three formatter constants),
`apps/web/src/components/PitchView.tsx` (lines 14–19, `moneyFormatter`),
`apps/web/src/components/PlayerPoolTable.tsx` (line 26, `moneyFormatter`),
`apps/web/src/components/SquadRecord.tsx` (line 9, `moneyFormatter`), new
`apps/web/src/utils/formatters.ts`

**Audit correction**: The audit listed `ManagerHistory.tsx` as a fifth file with
a duplicated `Intl` formatter, but inspection shows `ManagerHistory.tsx` contains
no `Intl` instance. The four files above are the correct set.

**Problem**: `moneyFormatter` (`Intl.NumberFormat("en-GB", { style: "currency",
… })`) is defined three times in separate files. `Intl` constructors are
expensive; creating multiple identical instances wastes initialisation time and
maintenance overhead (a locale change must be made in four places).

**Change**:

1. Create `apps/web/src/utils/formatters.ts` exporting `moneyFormatter`,
   `integerFormatter`, and `timestampFormatter` as module-level constants
   (module evaluation is the natural memo boundary).
2. Remove the local `moneyFormatter` definitions from `PitchView.tsx`,
   `PlayerPoolTable.tsx`, `SquadRecord.tsx`, and `App.tsx`.
3. Import from `utils/formatters.ts` in all four files.
4. Move `formatFplMoney` (defined in `App.tsx`) to `utils/formatters.ts` as
   well, since it wraps `moneyFormatter`.

**Constraints**: The formatted output of every call site must be byte-identical
before and after. The `PitchView.test.tsx` and `SquadRecord.test.tsx` suites
must pass unchanged (they exercise formatted money strings).

**Tests first**: In a new `apps/web/src/utils/formatters.test.ts`, assert the
three formatters produce correct locale output (`moneyFormatter.format(100)` →
`"£100.0m"` after division, etc.). These are pure unit tests with no React
dependency.

**Done when**:

- `moneyFormatter` is defined exactly once, in `utils/formatters.ts`.
- All four former definition sites import from that module.
- `PitchView.test.tsx` and `SquadRecord.test.tsx` pass unchanged.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test`.

---

## 118 — Memoise pure leaf components `PlayerChip` and `Jersey` (Impact: M)

**Files**: `apps/web/src/components/PitchView.tsx` (`PlayerChip` at line 42,
`Jersey` at line 26), `apps/web/src/components/PitchView.test.tsx`

**Problem**: `PlayerChip` and `Jersey` are pure presentational components with
stable prop shapes. When `TeamAnalysisPage` re-renders (e.g. during
`analysis.status` transitions from `loading` to `ready`), the entire pitch
re-renders including all fifteen `PlayerChip` instances and their nested
`Jersey` instances, even when the pick data has not changed. This causes
unnecessary DOM diffing for what is typically a 15-chip grid.

**Change**:

1. Wrap `Jersey` with `React.memo` — its sole prop `position` is a string
   union, so shallow equality is exact.
2. Wrap `PlayerChip` with `React.memo` — its sole prop `pick` is a
   `PublicTeamPick` object; because picks are immutable reference values from
   the parsed API response, shallow equality holds for the common case.
3. If `projectionFor` inside `PlayerChip` is recomputed on every render,
   consider wrapping it in `useMemo` with `[identity?.code]` as the dependency
   array.
4. Do not memo `PitchView` itself (the parent may legitimately re-render it
   with new state data).

**Constraints**: The visual output of `PitchView.test.tsx` must be unchanged.
The `SnapshotDossier` and `TeamAnalysisPage` render logic must not be altered.

**Tests first**: In `apps/web/src/components/PitchView.test.tsx`, add a test
that renders `<PitchView>` twice with the same picks (via `rerender`) and
asserts the render count of `PlayerChip` (using `vi.fn()` spy wrapped around
the component) does not increment on the second render.

**Done when**:

- `Jersey` and `PlayerChip` are wrapped in `React.memo`.
- The render-count test passes (no re-render on identical props).
- All existing `PitchView.test.tsx` assertions pass.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test`.

---

## 119 — Deduplicate concurrent identical requests with an in-flight promise cache (Impact: M)

**Files**: `apps/web/src/state/player-pool.ts` (fetch calls),
`apps/web/src/state/team-analysis.ts` (`refreshTeamAnalysis`, lines 91–155),
`apps/web/src/state/player-pool.test.ts`,
`apps/web/src/state/team-analysis.test.ts`

**Problem**: If two components mount simultaneously and both trigger a load for
the same resource (e.g. the player bootstrap and fixtures are fetched by
`player-pool.ts`; if two instances mount in StrictMode or a parent re-mounts
quickly), multiple identical HTTP requests are dispatched. React's StrictMode
double-invoke pattern in development exercises this today.

**Change**:

1. In `player-pool.ts`, introduce a module-level `Map<string, Promise<…>>` keyed
   by URL. Before calling `fetch`, check whether an identical URL has an
   in-flight promise; if so, await the existing promise. On resolution or
   rejection, delete the entry so future calls re-fetch.
2. Apply the same pattern to the bootstrap and fixtures URLs inside
   `player-pool.ts`.
3. For `refreshTeamAnalysis` in `team-analysis.ts`, the caller already manages
   an `AbortController` per effect invocation; deduplication at the state-module
   level is less critical but add a comment explaining why it is not needed
   (the `useEffect` cleanup aborts the prior request on re-run).

**Constraints**: The public API of `player-pool.ts` (`loadPlayerPool`,
`PoolPlayer`, etc.) must not change. The deduplication map must be cleared
between test cases — export a `clearInflightCache()` helper for tests only.
Existing `player-pool.test.ts` cases must pass.

**Tests first**: In `apps/web/src/state/player-pool.test.ts`, add a test that
calls the loader twice concurrently with the same URLs and asserts `fetch` was
called exactly once (via `vi.fn()` mock).

**Done when**:

- Concurrent identical requests share the in-flight promise.
- `fetch` is called once per URL per round-trip in the concurrent test.
- `clearInflightCache()` is exported and used in `afterEach` in tests.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test`.

---

## 120 — Add offline detection and a cached-data banner (Impact: M)

**Files**: `apps/web/src/components/ApplicationFrame.tsx` (to be extracted per
item 115; currently `App.tsx` lines 164–242), `apps/web/src/App.test.tsx`

**Problem**: If a user's connection drops after the initial load, any attempt to
navigate or retry an analysis resolves immediately to `{ status: "error",
reason: "network_error" }` with no indication that the device is offline.
Cached state in `localStorage` exists (loaded by `loadCachedPublicTeamState`)
but the offline condition looks identical to a server error, confusing users.

**Change**:

1. In `ApplicationFrame` (currently `App.tsx` lines 164–242), subscribe to
   `window` `"online"` and `"offline"` events in a `useEffect` and maintain
   an `isOnline` boolean state (initialised from `navigator.onLine`).
2. When `isOnline` is false, render a banner above the main content (below the
   `<StatusStrip>`) that uses the `--amber` design token and Andres's voice to
   explain the connection is unavailable and cached data may be shown.
3. Remove the banner when the `"online"` event fires.
4. Clean up both event listeners in the `useEffect` return.

**Constraints**: The banner must use only tokens from `styles.css` (`--amber`,
`--ink`, `--paper`). It must not appear when the user is online. It must not
affect any route's layout. `DESIGN.md`'s calm-analyst posture applies — no
alarming red error styling for a connectivity issue.

**Tests first**: In `apps/web/src/App.test.tsx` (or a new
`ApplicationFrame.test.tsx`), mock `navigator.onLine = false` and fire a
synthetic `"offline"` event; assert the banner is visible by accessible text or
`role="status"`. Then fire `"online"` and assert it is gone.

**Done when**:

- Banner appears on `"offline"` event and disappears on `"online"` event.
- Banner uses only `--amber` / `--ink` tokens.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test`.

---

## 121 — Add a `Suspense` skeleton for route transitions (Impact: M)

**Files**: `apps/web/src/main.tsx` (or `ApplicationFrame.tsx`), new
`apps/web/src/components/RouteSkeleton.tsx`

**Note**: This item depends on item 110 (code-split routes) landing first. The
skeleton described here is the `fallback` prop for the `<Suspense>` introduced
in that item.

**Problem**: Once code-splitting (item 110) is in place, navigating to a route
that has not yet been fetched will show a blank frame until the chunk loads.
A skeleton that matches the shell layout (header, main content area, footer
dimensions) prevents layout shift and gives users immediate feedback.

**Change**:

1. Create `apps/web/src/components/RouteSkeleton.tsx` rendering a minimal
   placeholder: the site header (`ApplicationFrame` header is outside Suspense
   so it stays visible) and a main area with a pulsing bar or the existing
   `loading-mark` spinner (from `styles.css` line 1889).
2. Use only existing CSS classes and design tokens. Do not introduce new
   animation keyframes; the `rotate-loading-mark` animation in `styles.css`
   suffices.
3. Pass `<RouteSkeleton />` as the `fallback` of the `<Suspense>` wrapping
   the `<Outlet>` in `ApplicationFrame`.

**Constraints**: The skeleton must not alter the DOM structure that Playwright
journeys rely on. It must be purely presentational with no data dependencies.

**Tests first**: In a test that mocks lazy imports to be suspended, assert
`RouteSkeleton` renders the `loading-mark` element (query by `className`
or accessible label).

**Done when**:

- The Suspense fallback shows a loading indicator, not a blank frame.
- The skeleton uses no hard-coded colours.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test`.

---

## 122 — Audit `styles.css` for unused selectors and add a size budget (Impact: M)

**Files**: `apps/web/src/styles.css` (entire file), `apps/web/vite.config.ts`
(or `package.json` scripts)

**Problem**: `styles.css` ships in full on first paint. The design system
includes selectors for every state and variant of every component. Over time,
as components are refactored or removed, stale selectors accumulate. There is
no automated check preventing the stylesheet from growing unconstrained.

**Change**:

1. Run PurgeCSS or the Vite `rollup-plugin-purgecss` equivalent against the
   built HTML and JS to identify selectors unreferenced by any component.
   Remove confirmed-dead selectors from `styles.css` (verify each removal
   does not break a Playwright journey before committing).
2. Add a `check:css-size` script to `apps/web/package.json` that builds the
   site and asserts the gzipped CSS output is below an agreed budget (e.g. 30
   kB gzipped). Integrate it into the CI workflow step that currently runs
   `pnpm check`.
3. Document the budget value in a comment at the top of `styles.css`.

**Constraints**: No selector may be removed without a passing Playwright journey
confirming the associated UI still renders correctly. The design tokens (`:root`
custom properties) must never be purged. Font-face declarations must be
preserved.

**Tests first**: The Playwright journeys in `apps/web/e2e/` serve as the
regression suite for selector removal. Run `corepack pnpm test:e2e` after each
batch of removals.

**Done when**:

- At least one provably dead selector is removed.
- A size-budget script exists and is run in CI.
- All Playwright journeys pass.
- `pnpm check` passes.

**Validate**: `corepack pnpm test:e2e` then `corepack pnpm --filter @fpl-andres/web check:css-size`.

---

## 123 — Consolidate duplicated stripe custom properties in `styles.css` (Impact: L)

**Files**: `apps/web/src/styles.css` (lines 95–132, two `--fa-stripes` blocks
in separate `:root` rule-sets)

**Problem**: `styles.css` opens with a single `:root` block (lines 6–55)
defining design tokens, then a second bare `:root` block (lines 95–116)
defining `--fa-stripes` and `--fa-stripes-deep`. The light-theme override at
`:root[data-theme="light"]` (lines 120–132) then redefines both stripe
variables. The `--fa-stripes` definitions belong in the same `:root` block as
the stripe-colour tokens (`--fa-stripe-a`, `--fa-stripe-b`) that they
reference, so the relationship is visually obvious and the `:root` selector is
not split across three locations.

**Change**:

1. Move the `--fa-stripes` and `--fa-stripes-deep` variable declarations from
   the second `:root` block (lines 95–116) into the primary `:root` block
   (lines 6–55), immediately after `--fa-stripe-width`.
2. Delete the now-empty second `:root` block.
3. Keep the `:root[data-theme="light"]` overrides where they are (they already
   follow the primary `:root` block and override both stripe variables for
   light mode).
4. Update the comment at the top of `styles.css` if it mentions the block count.

**Constraints**: The rendered gradient output must be byte-identical before and
after. The Playwright journey that asserts both kit themes produce distinct
`repeating-linear-gradient` values (`feature-walk.spec.ts` lines 323–326) must
pass unchanged.

**Tests first**: Run `corepack pnpm test:e2e` before and after the move and
confirm the kit-toggle test passes in both cases.

**Done when**:

- `styles.css` contains exactly one bare `:root` rule-set.
- The kit-toggle Playwright test passes.
- `pnpm check` passes.

**Validate**: `corepack pnpm test:e2e`.

---

## 124 — Add `will-change` and `contain` hints to animated elements (Impact: L)

**Files**: `apps/web/src/styles.css` (`.loading-mark` at line 1889,
`.disclosure-mark` at approximately line 1882)

**Problem**: `.loading-mark` runs a continuous `rotate-loading-mark` CSS
animation (line 1890) on every team-analysis page load. `.disclosure-mark`
transitions on `<details>` open/close. Neither carries `will-change` or
`contain` hints, so the browser cannot promote the layer ahead of time,
potentially causing compositing work on the main thread during the animation.

**Change**:

1. Add `will-change: transform` to `.loading-mark` in `styles.css` so the
   browser can promote it to its own compositor layer during the spin.
2. Add `contain: layout style` to `.squad-table-disclosure` (the wrapping
   `<details>` element at line 814) to isolate the disclosure toggle's layout
   recalculation from the rest of the page.
3. Do not add `will-change: transform` to `.disclosure-mark` itself — the
   rotation is triggered by a class, not a continuous animation, and
   `will-change` on intermittently animated elements wastes GPU memory.
4. Add a comment in `styles.css` explaining each hint and citing the MDN
   rationale.

**Constraints**: The visual output of both elements must be unchanged.
`will-change` must not be applied to static elements (the lint rule from
`stylelint-plugin-no-unsupported-browser-features` if present must not
flag the additions). The Playwright journey that toggles the source-trail
`<details>` must pass.

**Tests first**: No automated test can directly measure compositing layers.
Validate visually with Chrome DevTools Layers panel, then confirm via
Playwright that the disclosure toggle still opens and the loading spinner
still appears during analysis.

**Done when**:

- `will-change: transform` is present on `.loading-mark`.
- `contain: layout style` is present on `.squad-table-disclosure`.
- Comments explain each hint.
- All Playwright journeys pass.
- `pnpm check` passes.

**Validate**: `corepack pnpm test:e2e`.

---

## 125 — Name dynamic import chunks once code-splitting exists (Impact: L)

**Files**: `apps/web/src/pages/*.tsx` (to be created per items 110 and 115),
`apps/web/vite.config.ts`

**Note**: This item depends on items 110 and 115 landing first. It has no
effect until dynamic `import()` calls exist.

**Problem**: Without chunk names, Vite assigns hash-based output filenames
(e.g. `assets/index-BvK3sR2D.js`) to every code-split chunk. Bundle-analysis
output (`rollup-plugin-visualizer` or similar) becomes illegible because no
chunk name corresponds to a recognisable route.

**Change**:

1. Add a Vite magic comment to each `React.lazy(() => import(…))` call (added
   in item 110) to name the chunk: e.g.
   `React.lazy(() => import(/* @vite-chunk-name: "page-team" */ "./pages/TeamAnalysisPage"))`.
2. Confirm in `vite.config.ts` that `build.rollupOptions.output.chunkFileNames`
   does not override the magic-comment names.
3. After a production build, assert that `dist/assets/` contains files named
   `page-team-*.js`, `page-players-*.js`, etc.

**Constraints**: Chunk names must not contain Supabase keys, user data, or any
sensitive string. The magic-comment syntax must be compatible with the Vite
version in `apps/web/package.json`.

**Tests first**: Add a build-output assertion to the CI job (or a Node script
runnable with `node scripts/assert-chunks.mjs`) that globs `dist/assets/` and
asserts each expected chunk name prefix is present.

**Done when**:

- Each route chunk has a human-readable name prefix in `dist/assets/`.
- The bundle-analysis visualiser (if installed) shows named chunks.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web build` then inspect
`dist/assets/`.
