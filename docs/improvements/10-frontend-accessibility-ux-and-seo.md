# 10. Frontend accessibility, UX and SEO — work orders

Detailed briefs for items 126–137 of the [improvement audit](../../IMPROVEMENTS.md).
Each brief is self-contained: a sub-agent should be able to implement one item
from its brief alone.

Every brief obeys the repository rules: test-first, follow `DESIGN.md` and the
repository design skills for any visual work, never expose a Supabase secret,
Resend key or subscriber email to browser code or logs, and keep manual
team-state overrides separate from public last-deadline state.

---

## 126 — Extend axe-core journeys to the analysis ready-state and remaining routes (Impact: H)

**Files**: `apps/web/e2e/feature-walk.spec.ts` (lines 294–399)

**Audit correction**: The audit states that "nothing enforces" the contrast
standard claimed in `DESIGN.md` and `styles.css` (lines 58–72). This is
**partially false**. `feature-walk.spec.ts` already imports `AxeBuilder` from
`@axe-core/playwright` (line 1) and runs `scan.violations` assertions for the
home page in both dark and light themes (lines 294–298 and 339–346) and for the
calibration page (lines 375–379) and the degraded state (lines 381–399). The
gap is that no axe scan covers the analysis route in its `ready` state (team
data fully loaded), the `/players` page (with the full player table), or the
`/methodology` page.

**Problem**: WCAG 2.2 AA requires a minimum contrast ratio of 4.5:1 for normal
text (criterion 1.4.3) and 3:1 for large text. The `styles.css` comment on
line 5 asserts "every foreground/background pair below is verified at WCAG 2.2
AA against surface, surface-deep and surface-rise", but this claim is only
machine-checked for three page states. The analysis ready-state, players table,
and methodology page each add distinct colour pairings (`--fa-gk-lime`,
`--fa-gk-hot`, evidence chips, source-trail disclosure) that are not yet
covered by an axe scan.

**Change**:

1. In `apps/web/e2e/feature-walk.spec.ts`, add an axe scan after the analysis
   route reaches the `ready` state (after `await page.getByRole("heading",
{ name: /Analysis for team/ }).waitFor()`).
2. Add an axe scan on the `/players` page after the player table is visible
   (`await page.getByRole("table", { name: /players/i }).waitFor()`).
3. Add an axe scan on the `/methodology` page.
4. For each new scan, assert `scan.violations` is empty — the same pattern as
   existing scans.

**Constraints**: WCAG 1.4.3 (contrast) and 4.1.2 (name, role, value) are the
primary criteria to enforce. `axe-core`'s `color-contrast` rule covers 1.4.3
automatically. Do not disable any axe rules unless a violation is a documented
false positive with a comment explaining why.

**Tests first**: The test additions _are_ the deliverable for this item.

**Done when**:

- Three new axe-scan assertions exist: analysis ready-state, players page, and
  methodology page.
- All four existing axe-scan assertions continue to pass.
- `scan.violations` is empty for all seven scans in both themes (dark
  and light axe scans already exist for home; add light-theme variants for
  the new pages if any light-theme-only colour pairing is untested).
- `corepack pnpm test:e2e` exits zero.

**Validate**: `corepack pnpm test:e2e`.

---

## 127 — Set per-route document titles and meta description (Impact: H)

**Files**: `apps/web/index.html` (line 33, static `<title>FPL Andres</title>`),
`apps/web/src/pages/TeamAnalysisPage.tsx` (to be extracted per item 115;
currently inside `App.tsx`), `apps/web/src/pages/HomePage.tsx`,
`apps/web/src/pages/PlayerPoolPage.tsx`, `apps/web/src/pages/MethodPage.tsx`,
`apps/web/src/pages/CalibrationPage.tsx`

**Problem**: Every route shares the static `<title>FPL Andres</title>` defined
in `index.html`. Screen-reader users relying on document title to identify the
active page (WCAG 2.4.2 — Page Titled), and search engines that use the title
for indexing, receive no per-route information. A team-analysis URL
(`/team/212279`) is indistinguishable by title from the home page.

**Change**:

1. In each route-level component, add a `useEffect` that sets
   `document.title` to a descriptive, Andres-voiced string on mount and
   resets to `"FPL Andres"` on unmount:
   - `HomePage`: `"FPL Andres — Let me look at your squad"`
   - `TeamAnalysisPage`: `"Analysis for team ${entryId} — FPL Andres"` (update
     when `entryId` changes)
   - `PlayerPoolPage`: `"2026/27 player pool — FPL Andres"`
   - `MethodPage`: `"How I work — FPL Andres"`
   - `CalibrationPage`: `"I keep score on myself — FPL Andres"`
   - `NotFoundPage`: `"Nothing here — FPL Andres"`
2. Optionally create a `useDocumentTitle(title: string)` hook in
   `apps/web/src/utils/useDocumentTitle.ts` to avoid repeating the
   `useEffect` pattern.
3. Update the `<meta name="description">` in `index.html` to a site-level
   default. Add route-specific `<meta name="description">` updates in the same
   `useEffect` (via `document.querySelector('meta[name="description"]')?.setAttribute`),
   or use a head-management library if one is already in `package.json`.

**Constraints**: WCAG 2.4.2 (Page Titled). Title strings must be in Andres's
voice (`DESIGN.md`). The `<title>` must update on client-side navigation, not
only on hard load. No new npm packages without a security advisory check.

**Tests first**: In each page's `.test.tsx`, assert `document.title` has the
expected value after the component mounts (use `vi.spyOn(document, 'title',
'set')` or read `document.title` directly).

**Done when**:

- Navigating to each route sets a distinct, non-empty `document.title`.
- The title for `/team/:teamId` includes the team ID.
- `document.title` reverts to the site default when navigating away.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test` then
`corepack pnpm test:e2e`.

---

## 128 — Announce analysis state transitions via a persistent `aria-live` region (Impact: M)

**Files**: `apps/web/src/App.tsx` (lines 412–442, `TeamAnalysisPage` JSX
region, and lines 450–532, `AnalysisResult`), `apps/web/src/App.test.tsx`

**Problem**: `AnalysisResult` renders banners with `role="status"` and
`role="alert"` for different `analysis.status` values (lines 450–532). However,
these elements are _conditionally mounted and unmounted_ as the status changes
(e.g. the `role="status"` loading banner is replaced by the `EvidenceBanner`
with a different `role="status"` div when the request resolves). Some screen
readers — particularly JAWS and NVDA on Windows — do not reliably announce
content that enters a newly mounted `role="status"` element; they only announce
updates to a _persistent_ live region that was already in the DOM.

**Change**:

1. Add a single persistent `<div aria-live="polite" aria-atomic="true">`
   element to `TeamAnalysisPage` (rendered unconditionally inside the analysis
   section, positioned off-screen with a visually-hidden utility class from
   `styles.css`).
2. Derive a short announcement string from `analysis.status` and update the
   live region's text content via a `useEffect` that runs whenever
   `analysis.status` changes. Examples: `"Loading team state"`,
   `"Ready — observed snapshot loaded"`, `"Stale — showing cached data"`,
   `"FPL cannot be reached"`.
3. The visual banners (`AnalysisResult` children) remain unchanged — the live
   region is supplementary, not a replacement.

**Constraints**: The live region must use `aria-live="polite"`, not `"assertive"`,
to avoid interrupting reading. It must not be visible on-screen (use the
existing visually-hidden pattern from `styles.css` if present, or
`position: absolute; left: -9999px`). WCAG 4.1.3 (Status Messages).

**Tests first**: In `apps/web/src/App.test.tsx`, after dispatching a status
transition (by resolving a mocked API call), assert that the live region
(`getByRole("status", { name: /evidence/i })` or equivalent) contains text
that describes the new state.

**Done when**:

- A single persistent `aria-live="polite"` region exists in `TeamAnalysisPage`.
- Its text updates on every `analysis.status` transition.
- The region is not visually rendered.
- All existing `App.test.tsx` assertions pass.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test`.

---

## 129 — Add visible `:focus-visible` outline to scrollable table regions (Impact: M)

**Files**: `apps/web/src/styles.css` (line 1702–1707), `apps/web/src/components/PlayerPoolTable.tsx`
(line 240), `apps/web/src/components/ValidationReport.tsx` (lines 162, 224, 289, 418)

**Audit correction**: The audit's premise is **false as stated**. `.squad-table-wrap:focus-visible`
at `styles.css` line 1704 already applies
`outline: 3px solid var(--signal-blue); outline-offset: 3px` — the same token
and specification as other interactive elements in the design system. All
scrollable regions in `PlayerPoolTable.tsx` (line 237, `className="squad-table-wrap"`)
and `ValidationReport.tsx` (lines ~162, ~224, ~289, ~418, all using
`className="squad-table-wrap"`) inherit this rule.

**Residual work**: Verify the rule is not unintentionally overridden by a
more-specific selector anywhere in `styles.css`. Run the axe scan added in
item 126 and confirm no `focus-visible` violation is reported. Add a Playwright
assertion that, after tabbing to the player pool table, the computed
`outline-style` is not `none`.

**Change**:

1. Add a Playwright step to `apps/web/e2e/feature-walk.spec.ts` (inside the
   players-page test group) that tabs to the player table scroll region and
   asserts `outline-style !== "none"` via `page.evaluate`.
2. If the audit of `styles.css` reveals any specificity override that negates
   the rule (e.g. `.pool-controls + .squad-table-wrap { outline: none }`),
   remove the override.

**Constraints**: WCAG 2.4.7 (Focus Visible). No change to the token values.

**Tests first**: The Playwright step described in "Change" step 1 is the test.

**Done when**:

- A Playwright assertion confirms the focused table outline is visible (not
  none) on the players page.
- No `styles.css` specificity conflict overrides the rule.
- `corepack pnpm test:e2e` passes.

**Validate**: `corepack pnpm test:e2e`.

---

## 130 — Audit every icon for an accessible name or `aria-hidden` (Impact: M)

**Files**: `apps/web/src/App.tsx` (Lucide icons: `AlertTriangle`, `ArrowRight`,
`CheckCircle2`, `ChevronDown`, `Clock3`, `Database`, `RefreshCw`),
`apps/web/src/components/TeamStateCorrections.tsx` (Lucide icons: `CheckCircle2`,
`ChevronDown`, `PencilLine`, `Plus`, `Save`, `Trash2`, `X`),
`apps/web/src/components/StatusStrip.tsx`, `apps/web/src/App.test.tsx`

**Problem**: Lucide React renders `<svg>` elements. An SVG without either an
accessible name (`aria-label`, `<title>`, or `aria-labelledby`) or `aria-hidden="true"`
is announced by screen readers as an unlabelled graphic (WCAG 4.1.2). The
current codebase uses `aria-hidden="true"` on most icons in `App.tsx`, but a
systematic audit is needed to confirm no icon is reachable via the accessibility
tree without a label.

**Change**:

1. Run an automated scan (axe-core, item 126) — it will flag unlabelled
   `<svg>` elements as `image-redundant-alt` or `aria-required-attr` violations.
2. For each icon that is purely decorative and adjacent to a text label (e.g.
   `<RefreshCw aria-hidden="true" />` next to "Refresh"), confirm
   `aria-hidden="true"` is present and the parent button/link has an accessible
   name from its text content.
3. For each icon that _is_ the sole content of an interactive element (e.g. an
   icon-only button), ensure the element carries `aria-label` or
   `aria-labelledby`.
4. Assert the fix in `App.test.tsx`: for each icon-only button, query by
   `role="button"` with an accessible name and assert it is found.

**Constraints**: WCAG 4.1.2 (Name, Role, Value). Do not add visible text where
the design calls for an icon-only control. Follow `DESIGN.md` layout rules.

**Tests first**: In `apps/web/src/App.test.tsx`, add assertions for any
icon-only button: `getByRole("button", { name: /expected label/i })`.

**Done when**:

- Every `<svg>` in the rendered tree has either `aria-hidden="true"` or an
  accessible name.
- The axe scans added in item 126 report zero `aria-required-attr` violations.
- All icon-only buttons are queryable by accessible name in tests.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test` then
`corepack pnpm test:e2e`.

---

## 131 — Add explicit responsive breakpoints and viewport tests (Impact: M)

**Files**: `apps/web/src/styles.css` (existing `@media (max-width: 860px)` at
line 1709 and others), `apps/web/e2e/feature-walk.spec.ts`,
`apps/web/playwright.config.ts` (if it exists) or `apps/web/e2e/setup.ts`

**Problem**: `styles.css` uses `clamp()` for fluid scaling and a primary
breakpoint at `860px`. There are no automated assertions that the layout
remains usable at `360px` (narrow mobile), `768px` (tablet portrait), or
`1440px` (wide desktop). Visual regressions at these widths go undetected. WCAG
1.4.10 (Reflow) requires content to be available at 320px width without
horizontal scrolling (except for content that inherently requires
two-dimensional layout).

**Change**:

1. In `apps/web/e2e/feature-walk.spec.ts` (or a new
   `apps/web/e2e/responsive.spec.ts`), add a `test.describe` block that runs
   the home page and analysis page at `{ width: 360, height: 640 }`,
   `{ width: 768, height: 1024 }`, and `{ width: 1440, height: 900 }` using
   `page.setViewportSize`.
2. At each viewport, assert: (a) the primary navigation links are reachable
   (visible or accessible via a menu); (b) the Team ID input and submit button
   are visible; (c) no horizontal overflow occurs on `<body>` (assert
   `scrollWidth <= clientWidth`).
3. If `styles.css` contains breakpoints that are inconsistent or overlapping,
   consolidate them and document the chosen breakpoint vocabulary in a comment.

**Constraints**: WCAG 1.4.10 (Reflow). The scrollable table regions
(`.squad-table-wrap`) are exempt from the no-horizontal-scroll rule because they
inherently require two-dimensional layout. Every other page region must reflow.

**Tests first**: The Playwright viewport tests described above are the
deliverable.

**Done when**:

- Navigation and form are reachable at 360px width.
- No non-table horizontal overflow at 360px.
- `corepack pnpm test:e2e` exits zero at all three viewports.

**Validate**: `corepack pnpm test:e2e`.

---

## 132 — Split the coarse loading state into bootstrap and entry sub-steps (Impact: M)

**Files**: `apps/web/src/state/team-analysis.ts` (lines 12–28,
`TeamAnalysisState` union type), `apps/web/src/App.tsx` (lines 450–465,
the `AnalysisResult` loading branch), `apps/web/src/state/team-analysis.test.ts`

**Problem**: `TeamAnalysisState` (lines 12–28) uses a single `{ status:
"loading" }` value for the entire bootstrap-then-entry fetch sequence. When the
bootstrap is slow (FPL's `/bootstrap-static/` endpoint), the loading spinner
gives no indication of where the delay is. A user cannot distinguish "waiting
for the first FPL response" from "waiting for the team-specific pick data",
which differ in typical latency and diagnosis.

**Change**:

1. Add `{ status: "loading-bootstrap" }` and `{ status: "loading-entry" }` to
   the `TeamAnalysisState` union in `team-analysis.ts`, replacing the current
   `{ status: "loading" }`.
2. In `refreshTeamAnalysis`, dispatch `"loading-bootstrap"` before the first
   fetch and `"loading-entry"` once the bootstrap resolves and the team-specific
   request begins. Pass these new intermediate states back via a progress
   callback (a new optional `onProgress?: (state: TeamAnalysisState) => void`
   in `RefreshDependencies`) rather than making `refreshTeamAnalysis`
   async-iterable, to minimise the change surface.
3. Update `AnalysisResult` in `App.tsx` to render a different label for each
   sub-step: "Checking FPL snapshot index…" for `"loading-bootstrap"` and
   "Reading team picks…" for `"loading-entry"`.
4. Update `reduceTeamAnalysis` to accept the new action types.

**Constraints**: The existing `"loading"` status may be retained as an alias or
removed — if removed, update every reference in `App.test.tsx` and
`team-analysis.test.ts`. The `TeamAnalysisState` export is consumed by
`App.tsx` only; no other package imports it, so the change is internal.

**Tests first**: In `apps/web/src/state/team-analysis.test.ts`, assert that
the `onProgress` callback is called with `"loading-bootstrap"` before the first
`fetch` mock resolves and with `"loading-entry"` before the second.

**Done when**:

- `TeamAnalysisState` union includes `"loading-bootstrap"` and `"loading-entry"`.
- `AnalysisResult` renders distinct loading messages for each sub-step.
- All existing `team-analysis.test.ts` assertions pass (updated for new type
  names where needed).
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test`.

---

## 133 — Add `robots.txt` and a sitemap under `apps/web/public/` (Impact: M)

**Files**: new `apps/web/public/robots.txt`,
new `apps/web/public/sitemap.xml`

**Problem**: `apps/web/public/` contains only `favicon.svg` and
`site.webmanifest`. There is no `robots.txt`, so crawlers apply their default
(crawl everything, no rate hints). There is no sitemap, so search engines
cannot discover the canonical URL set efficiently. The routes are `/`,
`/players`, `/methodology`, and `/calibration`; the `/team/:teamId` routes are
user-specific and should be excluded from the sitemap.

**Change**:

1. Create `apps/web/public/robots.txt`:
   - `User-agent: *` / `Allow: /`
   - `Disallow: /team/` (team-specific pages carry no unique content for
     crawlers)
   - `Sitemap: https://fpl-andres.com/sitemap.xml` (use the production domain
     from `apps/web/index.html` or `OWNER_SETUP.md`; do not hard-code a
     dev URL)
2. Create `apps/web/public/sitemap.xml` as a standard XML sitemap listing the
   four static routes (`/`, `/players`, `/methodology`, `/calibration`) with
   `<lastmod>` set to the current date and `<changefreq>monthly`.

**Constraints**: Do not include `/team/*` URLs in the sitemap. Do not expose
any email address or Supabase URL in either file. The production domain must
come from a documented source (e.g. `OWNER_SETUP.md`), not be invented.

**Tests first**: Add a test in `apps/web/e2e/feature-walk.spec.ts` or a new
`apps/web/e2e/static-assets.spec.ts` that fetches `/robots.txt` and asserts
the response body contains `User-agent: *` and `Disallow: /team/`.

**Done when**:

- `/robots.txt` is served and contains the correct directives.
- `/sitemap.xml` is served and lists exactly the four static routes.
- The Playwright static-assets test passes.
- `pnpm check` passes.

**Validate**: `corepack pnpm test:e2e`.

---

## 134 — Complete the PWA manifest with raster icons and metadata (Impact: M)

**Files**: `apps/web/public/site.webmanifest`, `apps/web/public/` (new icon
files)

**Problem**: `site.webmanifest` declares one icon entry — the SVG favicon
(`/favicon.svg`, `sizes: "any"`, `purpose: "any"`). Android Chrome and iOS
Safari require raster icons at specific sizes (192×192 and 512×512 as a minimum)
for "Add to Home Screen" to produce a full-quality icon. The manifest also lacks
`orientation`, `categories`, and `screenshots` metadata that improve the
install prompt in supporting browsers. The `purpose: "any"` without a
`maskable` variant means adaptive icon shapes clip or pad the icon
unpredictably.

**Change**:

1. Create PNG icons at 192×192 and 512×512 from the `BielsaBucket` SVG mark
   (use the bucket-purple `#5308DC` on a `#0d0a26` background to match the
   dark-theme surface). Place them as `apps/web/public/icon-192.png` and
   `apps/web/public/icon-512.png`.
2. Create a `maskable` variant at 512×512 with appropriate safe-zone padding
   (the icon content must occupy the inner 80% of the canvas per the maskable
   icon spec). Place it as `apps/web/public/icon-512-maskable.png`.
3. Update `site.webmanifest` to add three icon entries: the existing SVG plus
   the two new PNGs (one `"purpose": "any"`, one `"purpose": "maskable"`).
4. Add `"orientation": "portrait-primary"`, `"categories": ["sports",
"utilities"]` to the manifest.

**Constraints**: Icon files must not embed any Supabase URL or email. The SVG
`<title>` inside `BielsaBucket` (inline in `App.tsx`) reads `aria-hidden` —
the raster exports are purely visual and need no accessibility treatment.
Existing `site.webmanifest` fields (`background_color`, `theme_color`) must not
change.

**Tests first**: Add a Playwright test that fetches `/site.webmanifest`, parses
the JSON, and asserts `icons.length >= 3` and that at least one icon has
`"purpose": "maskable"`.

**Done when**:

- `site.webmanifest` contains at least three icon entries including a maskable
  512×512.
- Raster PNG files exist at `apps/web/public/icon-192.png` and
  `apps/web/public/icon-512.png` and `apps/web/public/icon-512-maskable.png`.
- The Playwright manifest test passes.
- `pnpm check` passes.

**Validate**: `corepack pnpm test:e2e`.

---

## 135 — Give the empty manager-history state a semantic CSS class (Impact: L)

**Files**: `apps/web/src/components/ManagerHistory.tsx` (lines 71–82, the null-
profile branch), `apps/web/src/styles.css`

**Problem**: When `loaded.profile === null` (lines 71–82 of `ManagerHistory.tsx`),
the component renders a plain `<p>` inside `<section className="manager-history">`,
with no CSS class on the paragraph marking it as an empty state. Other empty
states in the app use named classes: `squad-record-empty` in `SquadRecord.tsx`
(line 70) and `correction-empty` in `TeamStateCorrections.tsx` (line 371), each
with corresponding `styles.css` rules at lines 1015 and 1496 respectively.
The manager-history empty paragraph lacks the visual treatment (muted
`--ink-soft` colour, consistent margin) that the other empty states receive.

**Change**:

1. Add `className="manager-history-empty"` to the `<p>` element at line 75 of
   `ManagerHistory.tsx`.
2. Add a `.manager-history-empty` rule to `styles.css` (near the existing
   `.squad-record-empty` rule at line 1015) setting `color: var(--ink-soft)`
   and the same `font-size` / `margin` as `.squad-record-empty`.
3. Ensure the class name follows the BEM-ish pattern used by other component
   empty states.

**Constraints**: The rendered text content must not change. The existing
`aria-labelledby="record-title"` on the wrapping `<section>` must be preserved.
No new icons or illustrations — this is a typographic-only change.

**Tests first**: In a new or existing `apps/web/src/components/ManagerHistory.test.tsx`,
mock `fetch` to return a non-ok response and assert that the empty-state paragraph
has the `manager-history-empty` class and is visible by role (`paragraph` or
by text content).

**Done when**:

- The null-profile branch renders a `<p className="manager-history-empty">`.
- `.manager-history-empty` exists in `styles.css` with `color: var(--ink-soft)`.
- The Playwright journey that reaches the `no_processed_event` state (which
  renders `ManagerHistory`) continues to pass.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test` then
`corepack pnpm test:e2e`.

---

## 136 — Document keyboard interactions in the interface itself (Impact: L)

**Files**: `apps/web/src/components/TeamStateCorrections.tsx` (the correction
panel `<details>` with keyboard-navigable fields), `apps/web/src/App.tsx`
(the analysis region with `tabIndex={-1}`, line ~424),
new `apps/web/src/components/KeyboardHint.tsx`

**Problem**: The `feature-walk.spec.ts` Playwright journey exercises keyboard
navigation through the correction panel, the source-trail disclosures, and the
skip-to-content link. However, the interface itself provides no visible cue that
these interactions exist. A sighted keyboard user who has not read the Playwright
test source or a README has no way to discover that Tab, Space/Enter, and the
skip link are available. WCAG 2.4.3 (Focus Order) is satisfied, but discoverability
is a UX gap.

**Change**:

1. Add a compact, visually unobtrusive `<KeyboardHint>` component that renders
   a single line of copy in Andres's voice below the Team ID form on `HomePage`,
   visible only when `:focus-visible` is active anywhere on the page (achieved
   with CSS `:has(:focus-visible) .keyboard-hint { display: block }` and the
   class hidden by default).
2. The hint text should name the key interactions relevant to the form and
   navigation: e.g. "Tab to navigate, Enter to analyse, Shift+Tab to go back."
3. Add a `.keyboard-hint` rule to `styles.css` — `display: none` by default,
   revealed by `:has(:focus-visible)`. Use `--ink-soft` and `var(--fa-body)`.

**Constraints**: The hint must not appear for mouse/pointer users (`:has(:focus-visible)`
handles this). It must not interfere with existing layout. The copy must be in
Andres's voice (`DESIGN.md`).

**Tests first**: In a Playwright test, simulate a `Tab` key press on the home
page and assert the keyboard hint becomes visible (query by text content or
`className`).

**Done when**:

- The `.keyboard-hint` element is hidden on pointer navigation and visible
  after a Tab press.
- Copy is present and Andres-voiced.
- `corepack pnpm test:e2e` passes.

**Validate**: `corepack pnpm test:e2e`.

---

## 137 — Add JSON-LD structured data for the site and route breadcrumbs (Impact: L)

**Files**: `apps/web/index.html` (no JSON-LD currently), new
`apps/web/src/components/JsonLd.tsx`

**Problem**: `index.html` contains Open Graph and Twitter Card meta tags but no
JSON-LD. Search engines use JSON-LD structured data for rich results — sitelinks
search boxes, breadcrumb trails, and `WebSite` entity recognition. Without it,
the pages appear as plain blue links with no enhancement in search results.

**Change**:

1. Create `apps/web/src/components/JsonLd.tsx` that renders a
   `<script type="application/ld+json">` tag via `dangerouslySetInnerHTML`
   (the standard React pattern for inline JSON-LD). The component accepts a
   single `schema` prop typed as `Record<string, unknown>`.
2. In `ApplicationFrame` (or the individual page components), inject a `WebSite`
   JSON-LD object on every page:
   ```
   { "@context": "https://schema.org", "@type": "WebSite",
     "name": "FPL Andres", "url": "https://fpl-andres.com" }
   ```
3. In `CalibrationPage`, inject a `BreadcrumbList` JSON-LD for the calibration
   route.
4. In `PlayerPoolPage`, inject a `BreadcrumbList` for the players route.
5. Do not include any subscriber emails, Supabase URLs, or API keys in the
   JSON-LD output.

**Constraints**: The `dangerouslySetInnerHTML` value must be serialised with
`JSON.stringify` — do not concatenate user-derived strings directly into the
script content (XSS risk). WCAG does not mandate structured data, but the
output must not introduce invalid HTML. The production domain used in `url`
must match the canonical domain documented in `OWNER_SETUP.md`.

**Tests first**: In a unit test for `JsonLd.tsx`, assert that the rendered
`<script>` element contains valid JSON (parseable with `JSON.parse`) and that
the `@type` field matches the supplied schema.

**Done when**:

- A `WebSite` JSON-LD `<script>` is present on every route.
- `BreadcrumbList` JSON-LD is present on `/calibration` and `/players`.
- No Supabase URL or secret appears in the JSON-LD output.
- `pnpm check` passes.

**Validate**: `corepack pnpm --filter @fpl-andres/web test`.
