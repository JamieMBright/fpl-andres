# Design Inspiration

Owner-provided reference images that anchor the visual language of FPL Andres.
Drop images here whenever they come to mind. The agent uses them only as
reference for deriving colour, type and motif tokens; nothing in this folder is
shipped verbatim to the browser bundle.

## What lives here

Anything that helps pin down the intended feel. Categories the owner has
mentioned so far:

- **Kit palettes.** Photographs or scans of the specific kits whose colours
  anchor the palette. The current brief anchors on the 1994 Leeds United third
  kit (dark scheme) with a light-mode variant drawn from the yellow/blue home
  kit of the same era.
- **Subbuteo.** Base rings, painted figure stances, and printed team card
  typography.
- **Teletext.** Block-cell letterforms, the 40 × 25 character grid, the six
  primary hues (red, green, yellow, blue, magenta, cyan) on black.
- **Goalkeeper kits.** The deliberately outrageous 1990s goalkeeper kits.
  These will drive a signature accent colour on the goalkeeper role and the
  keeper cards, in contrast to the outfield palette.
- **Logo.** Owner-provided original artwork saved as `logo.png`. The agent
  will knock out the background if needed and retint to match the shipped
  palette, but will not trace, derive from, or ship an actual club crest.

## File naming and size

- kebab-case filenames, so `kit-leeds-1994-third.png`, not
  `IMG_20260730_1122.png`.
- PNG or WebP, ideally under 500 KB. Larger files inflate clones without any
  gain over a good crop.
- No filename that mentions a club, sponsor or trademark in a way that would
  suggest endorsement; describe what the image _is_, not who it belongs to
  (`kit-third-1994.png`, not `leeds-official-third.png`).

## Licensing and shipping rules

- Images here are treated as owner-provided reference. The agent will not
  scrape additional images from the web, will not upscale traced photographs
  and will not ship any image from this folder as part of the deployed bundle
  without explicit owner sign-off.
- Any final mark or illustration that ships must have a documented derivative
  route (owner-authored, licensed clip art, or original abstract construction
  by the agent). Traced press photography and kit recreation remain blocked by
  the top-level `DESIGN.md`.
- Add a short one-line source note next to each image in
  [`SOURCES.md`](SOURCES.md) when you add it — enough to remember where it
  came from and whether it is safe to ship a derivative.
