---
name: web-design-guidelines
description: "Use when: reviewing FPL Andres UI, accessibility, responsive behavior, interaction details, forms, motion, typography, or frontend quality before a milestone is merged."
metadata:
  author: fpl-andres
  version: "1.0.0"
---

# Web Design Guidelines

Audit the requested UI files against the frozen local rules in
`references/web-interface-guidelines.md`.

## Workflow

1. Read `DESIGN.md` and the relevant UI files.
2. Read the complete local reference. Do not fetch rules at runtime.
3. Treat `DESIGN.md` as the project-specific authority where generic advice differs.
4. Report concrete defects in `file:line` form, ordered by user impact.
5. Include accessibility, keyboard, mobile, long-content, loading, stale, degraded,
   and error states in the review.
6. If no defects remain, say so and name any browser or device coverage not run.

The reference is vendored from Vercel Labs under MIT at the revision recorded in
`THIRD_PARTY_NOTICES.md`. This wrapper is project-authored and intentionally removes
the upstream skill's network fetch step.
