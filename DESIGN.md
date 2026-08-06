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
upturned drinks cooler the Argentine manager famously sat on during matches,
paired with the `@fpl_andres` handle. The silhouette is traced from the local
reference in `docs/design/inspiration/mask.png`: narrow arched top (the base
the manager sits on), wide bottom (the cooler's actual lid resting on the
grass), gently bowed sides. The bucket body is locked to the owner-specified
brand purple `#5308DC` in both themes so the mark reads identically regardless
of kit toggle. The sponsor plate is a fixed off-white rectangle with the
home-kit deep purple wordmark. The mark links to the owner's social handles.
Any earlier player-pose or teal-tinted mark proposal is retired.

Secondary signature elements the tool leans on:

- A Subbuteo-style base ring around every evidence chip so the source of a verdict
  is legible at a glance.
- Teletext-inspired monospace numerics for xPTS, prices, bank and confidence
  intervals, in a bounded set of six primary hues on the dark base.
- A goalkeeper-kit hot accent (drawn from the 1994 Leeds home keeper kit) reserved
  strictly for GKP surfaces and the goalkeeper row in tables. It never appears on
  outfield content and never carries semantic meaning outside the keeper role.

## Voice

Every string on the site is Andres speaking. He is the product's only narrator,
so copy is written in his voice or not written at all.

### Who he is

An analyst who was pulled into the spotlight under Bielsa, picked for the job
because he happened to speak Spanish. He knew it was luck, took the chance, and
repaid it: his analysis helped a Championship-quality squad finish ninth in the
Premier League.

That backstory sets the register. He is confident because the work earned it,
never because of the title. He assumes you are clever and busy. He is cheeky.
He likes a Leeds reference and keeps it so subtle most readers miss it — an
allusion to intensity, to being underestimated, to going again. Never a chant,
never a slogan, never "MOT".

### How he writes

- **First person.** "I've pulled your squad", not "the system retrieved".
- **Short.** Most sentences under twelve words. A verdict comes before its
  reasoning, never after.
- **The number leads.** "Salah, 6.4 xPTS. Captain him." Not "our model suggests
  that Salah may represent a strong captaincy option."
- **A glint, not a routine.** Personality lives in the phrasing, never in extra
  words. If a joke costs clarity, it goes.
- **He never hedges to protect himself.** He hedges only when the evidence
  genuinely does not support a claim, and then he says exactly why.

### Saying "I don't know"

This product renders `unavailable` constantly and by design, so admitting
ignorance is one of Andres's most frequent jobs. He treats it as the credential
it is, never as an apology.

His anchor line, used sparingly and never more than once per screen:

> All forecasts are wrong. Some are useful.

Around it he states the gap plainly and what would close it: "No DefCon read
yet. One season of labels is not enough, and I would rather say nothing than
guess." He never says "coming soon", never apologises, never pads.

### The reference bank

A closed set. Andres draws on these and nothing else, so the world stays small
and consistent rather than becoming a stream of Leeds trivia.

| Reference                                                   | What it means when he reaches for it            |
| ----------------------------------------------------------- | ----------------------------------------------- |
| A pint in **The Peacock** before kick-off                   | Steadying the nerves before a big call          |
| Walking out through the **Lowfields** tunnel                | Anticipation; the moment before a deadline      |
| **The Square Ball**                                         | Received wisdom, what the crowd is saying       |
| **Moylan's blisters by Sycamore Gap**                       | Something genuinely painful and self-inflicted  |
| **Batty in the Cheese Wedge**, kicking lumps out of Ronaldo | Defensive contribution before anyone counted it |

Rules:

- **At most one per screen, and most screens carry none.** Aim for roughly one
  in ten strings. They are seasoning.
- **Never explained.** No parenthetical gloss, no tooltip. If you know, you
  know; if you don't, the sentence still reads.
- **Never at the cost of clarity.** A number, a verdict or a warning is never
  wrapped in one.
- **Never in an error, an empty state, or anything a stuck user is reading.**

Batty is the exception worth leaning on: he is the natural shorthand for
defensive contribution, and the DefCon surfaces may lean on him more than the
one-in-ten rule allows.

### Banned

- FPL-Twitter filler: "differential", "set and forget", "bandwagon", "punt",
  "eyeing up", "must-have", "essential".
- Machine register: "delve", "leverage", "unlock", "seamless", "utilise",
  "robust", "powerful", "revolutionise".
- System-speak in user-facing copy: "observed state", "public state review",
  "deadline-bound updates", "source contract". These are correct internally and
  meaningless to a reader.
- Stacked labels that restate each other. One idea per line.
- Exclamation marks.

## Tokens

Three palettes ship, toggled by user preference and defaulting to dark. They derive
their values from period Leeds kits held in
[`docs/design/inspiration/`](docs/design/inspiration/README.md). The green and navy
shirt in that folder is the **away** kit — the yellow and blue one is the third,
which the toggle used to have the wrong way round.

### Dark (default) — after the 1994 away kit

| Token        | Value     | Use                                    |
| ------------ | --------- | -------------------------------------- |
| Surface      | `#16123a` | App frame background                   |
| Surface deep | `#0d0a26` | Ruled ground behind stripes            |
| Surface rise | `#221a55` | Elevated surfaces and ruled headers    |
| Stripe green | `#00a13e` | Away-kit stripe A, brand accent, ready |
| Stripe navy  | `#2b2065` | Away-kit stripe B, structural rules    |
| Cream        | `#f6f4ea` | Primary copy                           |
| Cream deep   | `#d5cfba` | Secondary copy                         |
| Focus blue   | `#3b357e` | Focus rings, links, mark bucket body   |
| Amber        | `#e5a02a` | Stale and watch states                 |
| Red          | `#d64545` | Errors and negative outcomes only      |

### Light (toggle) — after the 1994 home kit

| Token          | Value     | Use                                       |
| -------------- | --------- | ----------------------------------------- |
| Paper          | `#f7f5ea` | App frame background (warm off-white)     |
| Paper deep     | `#ffffff` | Elevated surfaces (tables, panels)        |
| Paper rise     | `#ffffff` | Elevated surfaces and ruled headers       |
| Stripe silver  | `#e4e3eb` | Home-kit stripe A (owner-specified white) |
| Stripe yellow  | `#e5da15` | Home-kit stripe B                         |
| Home blue      | `#4a008e` | Primary copy, structural rules, buttons   |
| Home blue rise | `#6a3aa8` | Hover / focus tint on the blue accent     |
| Slate deep     | `#6a3aa8` | Secondary copy                            |
| Amber          | `#a6621b` | Stale and watch states                    |
| Red            | `#a2433b` | Errors and negative outcomes only         |

### Brand mark (both modes)

The Bielsa bucket sits outside both kit palettes and holds its own hue so the
mark reads identically in every theme.

| Token         | Value     | Use                                        |
| ------------- | --------- | ------------------------------------------ |
| Bucket purple | `#5308DC` | Bucket body (`--fa-bucket`)                |
| Plate cream   | `#f8f6ea` | Fixed sponsor-plate background             |
| Plate ink     | `#4a008e` | Fixed sponsor-plate `@fpl_andres` wordmark |

### Goalkeeper-kit signature (both modes)

Drawn from the 1994 Leeds home keeper kit — the loudest surface in the whole
colour system. Reserved for the GKP row, the paid "DefCon beasts" heading, and
the six-hue Teletext strip that anchors the top of every page. Never used for
semantic state or for outfield content.

| Token         | Value     | Use                                      |
| ------------- | --------- | ---------------------------------------- |
| Keeper lime   | `#e7f24a` | Teletext strip primary; ready alt on GKP |
| Keeper hot    | `#e6338c` | Teletext strip primary; GKP row accent   |
| Keeper teal   | `#2ec9c0` | Teletext strip primary                   |
| Keeper purple | `#5b2ca8` | Teletext strip primary                   |
| Keeper black  | `#0a0a0a` | Teletext strip ground                    |
| Keeper white  | `#ffffff` | Teletext strip contrast text             |

Every semantic state also carries text or an icon. Green/red alone never carries
meaning. Contrast pairs are validated at WCAG 2.2 AA against the tokens above; if a
refinement drops any pair below 4.5 : 1 for body copy or 3 : 1 for large display,
the token itself is changed rather than exemption granted.

### Stripe motif

Vertical green + navy stripes drawn from the away kit form a background rhythm on
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

## Component inventory

Audit item #202. Thirty-five components in `apps/web/src/components`. The column
that matters is the last one: what a browser journey already proves about each,
so a review knows what it does not have to check by hand.

| Component              | Responsibility                                   | Asserted by                             |
| ---------------------- | ------------------------------------------------ | --------------------------------------- |
| `ApplicationFrame`     | Shell, skip link, kit toggle, offline banner     | `feature-walk`, `contrast`              |
| `RouteHeading`         | The single `h1`, focused on navigation           | `route-metadata`                        |
| `LazyRoute`            | Suspense fallback that still carries an `h1`     | `contrast` (axe `page-has-heading-one`) |
| `ErrorBoundary`        | Last resort, keeps the shell rendering           | unit                                    |
| `OfflineBanner`        | Says the connection dropped, not that data broke | unit                                    |
| `StatusStrip`          | Corpus freshness and pool size                   | `feature-walk`                          |
| `AnalysisResult`       | Dispatches on the seven analysis states          | `failure-states`                        |
| `SnapshotDossier`      | The verified squad, evidence and provenance      | `team-entry`                            |
| `PitchView`            | Formation, chips, captaincy                      | `feature-walk`, unit render cost        |
| `CeefaxShirt`          | Club kit as a teletext block graphic             | `contrast` (`/kits`), unit (palette)    |
| `PlayerAvatar`         | Lazy headshot, silhouette when there is none     | `contrast` (`/kits`)                    |
| `PlayerDetail`         | One player in full, with what each number means  | `feature-walk`                          |
| `FixtureBreakdown`     | Every fixture ahead, and last season's totals    | unit (via `PinnedPlayers`)              |
| `Countdown`            | Deadline cell at the end of the index bar        | `feature-walk`                          |
| `RangeSlider`          | One track, two thumbs, for a band                | `feature-walk` (ownership band)         |
| `HighlightPicker`      | Typeahead for names and clubs, chosen as chips   | `feature-walk`                          |
| `DeclaredTransferForm` | A swap FPL has not published yet, kept locally   | unit (`declared-transfers.test.ts`)     |
| `DeclaredSquadBuilder` | Your pre-season fifteen, rule-checked and locked | unit (`declared-squad.test.ts`)         |
| `SquadRecord`          | Per-player projection table                      | `feature-walk`                          |
| `ManagerHistory`       | Past seasons, including the empty case           | `team-entry`, unit                      |
| `TeamStateCorrections` | Manager overrides, parsing and conflict          | unit (`parse.test.ts`)                  |
| `TransferPlanPanel`    | What the plan will contain, and the deadline     | unit (`format.test.ts`)                 |
| `OpeningSquad`         | The published opening fifteen                    | `feature-walk`                          |
| `PlayerPoolTable`      | Sortable, filterable pool                        | `feature-walk`, unit render cost        |
| `PlayerScatter`        | Configurable two-axis scatter, drawn by hand     | unit render cost                        |
| `ScatterControls`      | Axis, filter and reference-line pickers          | unit                                    |
| `ScatterLegend`        | What shape, colour and disc size each mean       | `feature-walk`                          |
| `ScatterReadout`       | The scatter as a ranked, pinnable table          | unit                                    |
| `PinnedPlayers`        | Up to four players compared side by side         | unit                                    |
| `ValidationReport`     | Backtest metrics against baselines               | `feature-walk`, `contrast`              |
| `CalibrationCharts`    | Ranked bars and season lines, drawn by hand      | unit, `contrast`                        |
| `CaptainGrid`          | Every armband, method by gameweek, side-scrolled | unit, `contrast`                        |
| `CohortPanel`          | The veteran cohort and its coverage              | `feature-walk`                          |
| `Methodology`          | How the projection is built                      | `route-metadata`                        |
| `BielsaBucket`         | The mark                                         | —                                       |

## Accessibility checklist

Everything here is asserted by a test rather than checked by eye. The point of
writing it down is that a new component has a list to satisfy, not that a
reviewer has one to work through.

| Rule                                                           | Enforced by                    |
| -------------------------------------------------------------- | ------------------------------ |
| Every page has exactly one `h1`, including a Suspense fallback | `contrast.spec.ts`             |
| Every route meets WCAG 2.1 AA in **both** kits                 | `contrast.spec.ts`             |
| The contrast scan is not vacuous — an injected 1.6:1 fails     | `contrast.spec.ts`             |
| Every icon is `aria-hidden` or has an accessible name          | `static-accessibility.test.ts` |
| Every scrollable region is focusable, named and outlined       | `static-accessibility.test.ts` |
| State transitions are announced politely, without re-reading   | `static-accessibility.test.ts` |
| No horizontal overflow at 360, 600, 680, 768 or 1440 px        | `responsive.spec.ts`           |
| The `h1` stays at 20 px or more at 360 px                      | `responsive.spec.ts`           |
| Tap targets clear the WCAG 2.2 AA 24 px minimum                | `responsive.spec.ts`           |
| Keyboard bypass and disclosure controls work                   | `team-entry.spec.ts`           |

Two rules that are deliberately **not** enforced, and why:

- **Colour is never the only signal.** No test can check this, because "the
  chip is red" and "the chip says unavailable" are indistinguishable to a DOM
  query. It stays a review item.
- **Motion respects `prefers-reduced-motion`.** The stylesheet gates every
  animation behind it, but a test asserting the gate exists would pass on a CSS
  rule nobody applied.

## Review gates

Before a frontend milestone merges, run the local frontend-design and
web-design-guidelines skills, keyboard navigation, 200% zoom, reduced motion, 360 px
mobile, wide desktop, long content, empty data, and stale/error screenshots.
