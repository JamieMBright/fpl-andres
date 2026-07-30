# FPL Andres Design Contract

## Product posture

FPL Andres is a calm, meticulous analyst used under deadline pressure. It is not a
fan page, a marketing site, or a chat persona. The interface leads with a decision,
then lets evidence, uncertainty and provenance unfold beneath it.

The subject vocabulary is a 1990s UK matchday scouting dossier: source timestamps,
annotations, ruled sections, formation sheets, compact verdicts and margin notes,
borrowing rhythm from Subbuteo team cards, Teletext page-number grids and the loud
goalkeeper kits of the period. Palette hexes may be drawn from period kit
references held in [`docs/design/inspiration/`](docs/design/inspiration/README.md).
Crest, wordmark, sponsor and literal kit templates remain out of scope: no Leeds
crest, white rose, slogan, sponsor mark, kit graphic recreation, or claim of
endorsement may appear.

## Signature

The durable signature is a recommendation dossier in which every verdict has a
visible evidence state and an expandable source trail. The visual signature is the
**Bielsa bucket** — an original, owner-authored abstract mark evoking the
upturned bucket the Argentine manager famously sat on during matches, paired with
the `@fpl_andres` handle. The mark is not traced from any specific photograph and
does not carry a club crest, sponsor or kit graphic. The mark links to the owner's
social handles. Any earlier player-pose mark proposal is retired.

Secondary signature elements the tool leans on:

- A Subbuteo-style base ring around every evidence chip so the source of a verdict
  is legible at a glance.
- Teletext-inspired monospace numerics for xPTS, prices, bank and confidence
  intervals, in a bounded set of six primary hues on the dark base.
- A goalkeeper-kit hot accent (drawn from the 1994 Leeds home keeper kit) reserved
  strictly for GKP surfaces and the goalkeeper row in tables. It never appears on
  outfield content and never carries semantic meaning outside the keeper role.

## Tokens

Two palettes ship, toggled by user preference and defaulting to dark. Both derive
their green + blue values from period Leeds kits held in
[`docs/design/inspiration/`](docs/design/inspiration/README.md); the hex values
below are provisional until owner-provided kit references land, at which point the
frontend picks them up from `--fa-*` custom properties.

### Dark (default) — after the 1994 third kit

| Token           | Value       | Use                                          |
| --------------- | ----------- | -------------------------------------------- |
| Surface         | `#16123a`   | App frame background                         |
| Surface deep    | `#0d0a26`   | Ruled ground behind stripes                  |
| Surface rise    | `#221a55`   | Elevated surfaces and ruled headers          |
| Stripe green    | `#00a13e`   | Third-kit stripe A, brand accent, ready      |
| Stripe blue     | `#2b2065`   | Third-kit stripe B, structural rules         |
| Cream           | `#f6f4ea`   | Primary copy                                 |
| Cream deep      | `#d5cfba`   | Secondary copy                               |
| Focus blue      | `#3b357e`   | Focus rings, links, mark bucket body         |
| Amber           | `#e5a02a`   | Stale and watch states                       |
| Red             | `#d64545`   | Errors and negative outcomes only            |

### Light (toggle) — after the 1994 home kit

| Token           | Value       | Use                                          |
| --------------- | ----------- | -------------------------------------------- |
| Paper           | `#f6f4ea`   | App frame background                         |
| Paper deep      | `#ede8d3`   | Ruled ground                                 |
| Paper rise      | `#fbf9f0`   | Elevated surfaces and ruled headers          |
| Home yellow     | `#f2c33a`   | Home-kit stripe A, brand accent              |
| Home blue       | `#3b357e`   | Home-kit stripe B, structural rules, ink     |
| Slate           | `#2b2065`   | Primary copy                                 |
| Slate deep      | `#4a4a6b`   | Secondary copy                               |
| Amber           | `#a6621b`   | Stale and watch states                       |
| Red             | `#a2433b`   | Errors and negative outcomes only            |

### Goalkeeper-kit signature (both modes)

Drawn from the 1994 Leeds home keeper kit — the loudest surface in the whole
colour system. Reserved for the GKP row, the paid "DefCon beasts" heading, and
the six-hue Teletext strip that anchors the top of every page. Never used for
semantic state or for outfield content.

| Token           | Value       | Use                                          |
| --------------- | ----------- | -------------------------------------------- |
| Keeper lime     | `#e7f24a`   | Teletext strip primary; ready alt on GKP     |
| Keeper hot      | `#e6338c`   | Teletext strip primary; GKP row accent       |
| Keeper teal     | `#2ec9c0`   | Teletext strip primary; bucket logo default  |
| Keeper purple   | `#5b2ca8`   | Teletext strip primary                       |
| Keeper black    | `#0a0a0a`   | Teletext strip ground                        |
| Keeper white    | `#ffffff`   | Teletext strip contrast text                 |

Every semantic state also carries text or an icon. Green/red alone never carries
meaning. Contrast pairs are validated at WCAG 2.2 AA against the tokens above; if a
refinement drops any pair below 4.5 : 1 for body copy or 3 : 1 for large display,
the token itself is changed rather than exemption granted.

### Stripe motif

Vertical green + blue stripes drawn from the third kit form a background rhythm on
the hero region only, at 6–10% opacity, and never overlay tabular content. On
light mode, the stripes swap to yellow + blue but retain the same rhythm and
opacity ceiling. Stripes are decorative, not structural: they are
`aria-hidden` and never encode meaning.

## Type

- `Newsreader`: restrained display headings and verdicts.
- `IBM Plex Sans`: body copy, controls and navigation.
- `IBM Plex Mono`: timestamps, IDs, prices, model versions and tabular metadata.

Use tabular numerals for comparison. Do not scale text directly with viewport width;
responsive type uses bounded `clamp()` values. Letter spacing remains `0`.

## Structure

- The root remains the working Team-ID experience. Marketing surfaces (feature
  preview panels, paywall banners, social links) live below the fold and never
  delay the tool.
- Use full-width ruled sections instead of stacked floating cards.
- Number only genuine workflow stages or ordered plan steps.
- Inside compact surfaces, headings remain compact; reserve large type for the
  first decision question and major route titles.
- Tables retain comparison on mobile through horizontal scroll and sticky identity
  columns; do not turn every row into a card.
- Controls have stable dimensions and minimum 44 px targets.

## Free vs paid surfaces

FPL Andres is fully free today. Paid tiers are planned but not yet gated in code.
The design contract commits to three shelves:

- **Tool (always free with a Team ID).** The public snapshot dossier, the
  browser-local manager corrections, methodology and calibration.
- **Free tier (planned).** Context-less league-wide views that do not require a
  Team ID, such as top xPTS/£ players ranked across the league.
- **Paid tier (planned).** Aggregate analytical panels including OOP player
  rankings (xPTS/£ over promoted Lord Lundstram + reverse-OOP signals) and
  DefCon beasts (highest probability of stable DefCon returns per £).

Every planned paid feature respects the promotion contract. A paywall never
surfaces experimental or unpromoted forecasts. The gating shim (auth, entitlement
check, upgrade prompt) is out of scope for v0.5.x; the paid panels ship as
`unavailable` placeholders with an evidence chip that explains what is missing.
See [`docs/PAYWALL.md`](docs/PAYWALL.md) for the tier definitions.

## Interaction

- Links navigate and buttons execute commands.
- A route change moves focus to the new page heading.
- Validation names the fix and marks the field invalid.
- A failed refresh preserves the last usable recommendation and marks it stale.
- Motion explains state change only, stays under 250 ms, uses opacity/transform, and
  disappears under `prefers-reduced-motion`.

## Required states

Every remote surface implements idle, loading, ready, stale, degraded and error.
`Unavailable` is a valid evidence result, not an error placeholder.

## Rejected patterns

- Robot heads, brains, sparkles, circuits or conversational AI bubbles.
- Purple/blue neon gradients, glass panels, glows, bokeh and decorative orbs.
- Cards nested inside cards or every section floating on a shadow.
- Oversized marketing copy that delays the actual tool.
- Decorative statistics without a decision consequence, including mocked "STRONG
  BUY" chips or xPTS numbers without an underlying promoted forecast.
- Overt football-club heraldry (crest, wordmark, sponsor, official kit graphic)
  or a traced press photograph.
- Full pastiche of a Teletext page, a Subbuteo board or a matchday programme: the
  motifs are recognisable nods, not recreations.

## Review gates

Before a frontend milestone merges, run the local frontend-design and
web-design-guidelines skills, keyboard navigation, 200% zoom, reduced motion, 360 px
mobile, wide desktop, long content, empty data, and stale/error screenshots.
