# FPL Andres Design Contract

## Product posture

FPL Andres is a calm, meticulous analyst used under deadline pressure. It is not a
fan page, a marketing site, or a chat persona. The interface leads with a decision,
then lets evidence, uncertainty and provenance unfold beneath it.

The subject vocabulary is the scouting dossier: source timestamps, annotations,
ruled sections, formation sheets, compact verdicts and margin notes. Heritage cues
remain subtle. No Leeds crest, white rose, slogan, sponsor, kit recreation, or claim
of endorsement may appear.

## Signature

The durable signature is a recommendation dossier in which every verdict has a
visible evidence state and an expandable source trail. The temporary brand mark is
an abstract folded report page. A player-pose mark is blocked until its source and
derivative-use route are documented.

## Tokens

| Token       | Value     | Use                                    |
| ----------- | --------- | -------------------------------------- |
| Paper       | `#f7f8f2` | Primary surface                        |
| Paper deep  | `#e9eee8` | App frame and ruled ground             |
| Ink         | `#13263a` | Primary copy                           |
| Navy        | `#142d4c` | Commands and structural rules          |
| Field green | `#38634c` | Brand accent and observed evidence     |
| Signal blue | `#4f91c2` | Focus, links and analytical annotation |
| Amber       | `#b8752d` | Stale and watch states                 |
| Red         | `#a2433b` | Errors and negative outcomes only      |

Every semantic state also has text or an icon. Green/red alone never carries meaning.

## Type

- `Newsreader`: restrained display headings and verdicts.
- `IBM Plex Sans`: body copy, controls and navigation.
- `IBM Plex Mono`: timestamps, IDs, prices, model versions and tabular metadata.

Use tabular numerals for comparison. Do not scale text directly with viewport width;
responsive type uses bounded `clamp()` values. Letter spacing remains `0`.

## Structure

- The root is the working Team-ID experience, never a promotional landing page.
- Use full-width ruled sections instead of stacked floating cards.
- Number only genuine workflow stages or ordered plan steps.
- Inside compact surfaces, headings remain compact; reserve large type for the first
  decision question and major route titles.
- Tables retain comparison on mobile through horizontal scroll and sticky identity
  columns; do not turn every row into a card.
- Controls have stable dimensions and minimum 44 px targets.

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
- Decorative statistics without a decision consequence.
- Overt football-club heraldry or a traced press photograph.

## Review gates

Before a frontend milestone merges, run the local frontend-design and
web-design-guidelines skills, keyboard navigation, 200% zoom, reduced motion, 360 px
mobile, wide desktop, long content, empty data, and stale/error screenshots.
