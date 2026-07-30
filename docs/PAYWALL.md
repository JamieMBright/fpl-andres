# Paywall Plan

FPL Andres is in **beta**. Every feature listed on this page is fully open
today. This document is the forward plan for what happens when the beta
label comes off — three tiers, each gated by evidence rather than by an
arbitrary lock.

## Owner decision (2026-07-30): nothing is charged for in 2026/27

No paid element ships during the 2026/27 season. The only circumstance that
would revisit this is the product going viral, which is not expected before the
social accounts are properly linked and weekly content is actually being
produced.

Consequences for the build:

- The gating shim is written last and stays dormant. Nothing is gated until the
  owner says so explicitly, and it may stay free indefinitely.
- Every tier below is a layout and evidence contract, not a billing plan. Paid
  panels ship visible and free, labelled `beta — free during beta`.
- No payment provider, entitlement store or upgrade prompt is integrated until
  that instruction arrives. Building one now would be speculative work against a
  decision that has not been taken.

## Beta (current)

- All features free, all shelves open to everyone.
- No entitlement check, no upgrade prompt, no paywall label anywhere in
  the UI.
- Every future paid feature ships first as `unavailable` behind an
  evidence chip so the layout can settle while the underlying model
  progresses through the promotion contract.

## Free tier (post-beta)

Context-less advice and short-horizon planning that never needs a Team ID.
Fast to compute, cheap to serve, honest about its limits.

- **Context-less top calls.** League-wide xPTS/£ tables for outfield
  players and goalkeepers, filtered by position, availability and fixture
  window. Nothing about the manager's private state is consumed.
- **+1 GW ahead strategy.** A single-gameweek-ahead recommendation
  layered on the tool: "given your current public snapshot, here is the
  captain, one transfer and lineup call for next deadline." Explicitly
  bounded to one gameweek; the multi-gameweek roll is paid.

## Paid tier — "buy me half a pint at the stadium" (post-beta)

The tier name and price are the product's own voice. Owner writes the
copy verbatim on any pricing surface:

> **Buy me half a pint at the stadium — £3/month.**

Content unlocked at the paid tier:

- **Full future fixture planner.** The multi-gameweek rolling plan the
  optimiser is already capable of producing, exposed to the user with
  bank and free-transfer flow across the horizon.
- **OOP player analysis.** Ranked view of players with a promoted
  `lord_lundstram_effect` or `reverse_oop` signal, sorted by xPTS/£ over
  the promoted attacking projection. Requires the per-event recency
  contract in
  [`docs/MODEL_CARDS.md`](MODEL_CARDS.md#deployment-signal--1).
- **DefCon beasts.** Players with the highest probability of stable
  DefCon returns per £, over a rolling window. Requires a promoted
  DefCon model, which depends on 2025/26+ observed defensive-actions
  data (see [`docs/LIMITATIONS.md`](LIMITATIONS.md)).
- **FPL100.** What the top 100 ranked teams are actually doing: revealed
  ownership, captaincy and transfers across that cohort, post-deadline.
  Contextual, not a projection input. Answers "what does the top 100 look
  like right now" without altering the tool's own player projections.
- **Groupthink.** What people are _saying_ - the prevailing community and
  pundit opinion, as a sentiment reading rather than republished content.
  Distinct from FPL100, which is what people actually _did_.
- **Divergence and track record.** The panel that makes the other two worth
  paying for: where our projection disagrees with FPL100 and with
  groupthink, and our historical hit rate on those disagreements. A
  recommendation that matches the field is worth little; a recommendation
  that beats it, with a measured record, is the product.

Each paid panel must still respect the promotion contract:

1. Cite an underlying promoted model. Experimental or unpromoted
   forecasts are never surfaced under the paid shelf.
2. Attach source hashes and evidence timestamps in the same way the
   current dossier does.
3. Show `unavailable` for players who do not clear the sample floor or
   whose recency contract emits a regime change.
4. Refuse to invent placeholder ranks. If no player clears the gate, the
   panel ships an honest `no eligible players yet` message rather than
   filler entries.

## Shipping order (proposed)

1. **v0.6.0 — Free-tier layout.** Ship the context-less top-calls
   panels and the +1 GW panel behind an evidence chip that says
   `unavailable — awaiting promoted xPTS model`. Layout only, no numbers.
2. **v0.7.0 — Promoted xPTS model.** Once the xPTS candidate clears its
   walk-forward evaluation and paired-improvement gate, the free-tier
   panels flip from `unavailable` to `observed`. Paid-tier panels remain
   in preview.
3. **v0.8.0 — Fixture planner + OOP paid panels.** Multi-gameweek roll
   and the recency-weighted deployment classifier consume live per-event
   observations.
4. **v0.9.0 — FPL100, groupthink and divergence.** FPL100 requires the
   post-deadline top-100 cohort pull. Groupthink requires the Reddit and
   YouTube API adapters. Divergence requires both, plus a backtest
   record of past disagreements, and renders `unavailable` until that
   record exists.
5. **v0.10.0 — DefCon beasts.** Reachable once the 2025/26 DefCon
   corpus has enough games to promote at least one model.
6. **v1.0.0 — Gating shim.** Auth and entitlement come last. Until
   then, both free and paid shelves remain visible to everyone; the paid
   surface shows a `beta — free during beta` label with the intended
   post-beta pricing so users are not surprised at cutover.

## Explicitly out of scope

- Any teaser number, price or rank that would appear on the paid shelf
  before its underlying model has promoted. The design contract already
  rejects "decorative statistics without a decision consequence".
- Per-user tailored recommendations on the free or paid shelf other than
  the +1 GW panel. Deep Team-ID recommendations remain the Tool shelf
  and do not paywall.
- Ownership of past predictions inside a paid archive. Owner has not
  asked for it yet.
- Monthly billing beyond the £3 line while beta is active. Payment
  provider selection and billing model land in v1.0.0.

## Owner decisions still open

- Payments provider (Stripe Checkout, GoCardless, Buy Me a Coffee /
  Ko-fi for a lower-friction "half a pint" flow, etc.). Not needed until
  v1.0.0.
- Whether the paid shelf shows on the Team-ID dossier as inline sidebars
  or as a separate route. Design will pin this once the mockup direction
  is chosen (see [`docs/design/mockups/`](design/mockups/README.md)).
