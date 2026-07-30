# Design Mockups

Three static HTML mockups showing the same content at three depths of 90s
nostalgia. Open each file directly in a browser (double-click, or drag onto
Chrome / Edge / Safari) — they are self-contained and require no build or
server.

**Owner picked Ceefax Third Kit on 2026-07-30.** `mockup-ceefax.html` has been
refreshed with palette hexes eyedropped from `docs/design/inspiration/` and now
carries a working dark/light toggle. The two other mockups are kept as
historical reference at the earlier provisional palette.

| Mockup                                     | Depth of nostalgia | What signals it                                                                                                     |
| ------------------------------------------ | ------------------ | ------------------------------------------------------------------------------------------------------------------- |
| [`mockup-newsprint.html`](mockup-newsprint.html) | Subtle             | Clean scouting dossier on the third-kit palette; Subbuteo ring on the evidence chip; monospace Teletext numerics.   |
| [`mockup-matchday.html`](mockup-matchday.html) | Medium             | Adds a chunky programme-cover display face, a green/blue stripe rhythm behind the hero, and a loud GKP keeper accent. |
| [`mockup-ceefax.html`](mockup-ceefax.html) — **selected** | Bold               | Teletext keeper-kit primary strip; third-kit stripes across the whole content area; toggle between third-kit dark and home-kit light modes. |

## What's the same across all three

- The exact tokens from [`DESIGN.md`](../../../DESIGN.md) (`--fa-*` custom
  properties) so palette differences are pinned to the contract.
- The same content: hero with the Team-ID form, evidence chip, dossier squad
  snippet, an evidence-gated paid-shelf preview.
- The Bielsa-bucket logo drawn as inline SVG at the current owner-signed-off
  placeholder level; it will be refined once the owner drops the real
  reference at `docs/design/inspiration/logo.png`.

## What differs

Only the surface treatment: type stack, background rhythm, chip shape,
keeper-accent intensity. The information architecture is identical so the
pick is purely aesthetic.

## How to feed back

Note the mockup filename plus a short comment per element (`hero background`,
`evidence chip`, `keeper accent`, `paid panel treatment`, `logo`). The agent
will roll the winner into a token-only refactor of the existing web app; no
new components ship until a mockup is picked and the tokens are eyedropped
from real kit references.
