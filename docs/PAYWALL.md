# Paywall Plan

FPL Andres is fully free today. This document names the intended free vs paid
shelves, the evidence gates each shelf must respect, and the shipping order.
No gating shim exists in code yet; every listed feature ships as `unavailable`
with an evidence chip that explains what is still missing until the underlying
evidence promotes.

## Shelves

The tool splits into three shelves. A shelf is the surface the user is on, not
the subscription tier.

### Tool — always free with a Team ID

The public snapshot dossier and browser-local corrections. This is the
existing v0.5.x experience:

- Team-ID entry and analysis dossier.
- Manager corrections (bank, free transfers, queued moves, chips) held only in
  the browser.
- Methodology, calibration and source-trail disclosures.

No paywall applies here. It is the working tool.

### Free tier — planned, context-less

League-wide rankings that do not need a Team ID. These require nothing about
the manager's private state and can be computed once and served to everyone.

- **Top xPTS per £.** All eligible outfield players ranked by promoted
  expected points per unit price, filtered by position, availability and
  fixture window.
- **Top xPTS per £ for goalkeepers.** Same, restricted to GKP.

### Paid tier — planned, evidence-gated aggregate views

Aggregate analytical panels that layer promoted evidence on top of the free
rankings. These do not consume a Team ID either, but their inputs are more
expensive to generate and require additional evidence promotion.

- **OOP player rankings.** Ranked view of players with a `lord_lundstram_effect`
  or `reverse_oop` signal that has passed the promotion contract, sorted by
  xPTS per £ over the promoted attacking projection. Requires per-event role
  observations, the recency contract in
  [`docs/MODEL_CARDS.md`](MODEL_CARDS.md#deployment-signal--1), and a promoted
  attacking-return projection.
- **DefCon beasts.** Players with the highest probability of stable DefCon
  returns per £, over a rolling window. Requires promoted DefCon models
  (which are unavailable today because they rely on 2025/26+ observed defensive
  actions per [`docs/LIMITATIONS.md`](LIMITATIONS.md)).

## Evidence gates each paid panel must clear

Before a paid panel is enabled, every entry must:

1. Cite an underlying promoted model. Experimental or unpromoted forecasts are
   never surfaced under the paid shelf.
2. Attach source hashes and evidence timestamps in the same way the current
   dossier does.
3. Show `unavailable` for players who do not clear the sample floor or whose
   recency contract emits a regime change (per the deployment classifier).
4. Refuse to invent placeholder ranks. If no player clears the gate, the panel
   ships an honest `no eligible players yet` message.

## Shipping order (proposed)

1. **v0.6.0 — Free tier layout.** Ship the top xPTS/£ panels behind an
   evidence chip that says `unavailable — awaiting promoted xPTS model`. No
   real data yet; the surface is present so the paywall design can settle.
2. **v0.7.0 — Promoted xPTS model.** Once the xPTS candidate clears its
   walk-forward evaluation and paired-improvement gate, the free tier panels
   flip from `unavailable` to `observed` and paid panels become buildable.
3. **v0.8.0 — OOP paid panel.** Recency-weighted deployment classifier
   consumes live per-event observations, promoted attacking projections
   attach, panel opens.
4. **v0.9.0 — DefCon paid panel.** Only reachable after the 2025/26 DefCon
   corpus has enough games to promote at least one model.
5. **v1.0.0 — Gating shim.** Auth and entitlement come last. Until then, both
   free and paid shelves are visible to everyone; the paywall label warns
   users that access will change at a stated future date.

## What is deliberately out of scope

- Any teaser number, price or rank that would appear on the paid shelf before
  its underlying model has promoted. The design contract already rejects
  "decorative statistics without a decision consequence".
- Any per-user recommendation on the free or paid shelf. Both shelves are
  league-wide; per-Team-ID recommendations remain the Tool shelf and do not
  paywall.
- Ownership of past predictions inside a paid archive. Owner has not asked
  for it yet.

## Owner decisions still open

- Pricing tier structure (monthly, seasonal, single-payment, none). Not
  needed until v1.0.0.
- Payments provider. Not needed until v1.0.0.
- Whether the paid shelf shows on the Team-ID dossier as inline sidebars or
  as a separate route. Design will pin this once the mockup direction is
  chosen (see [`docs/design/mockups/`](design/mockups/README.md)).
