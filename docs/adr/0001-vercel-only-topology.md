# ADR 0001: Use a single Vercel origin

- Status: accepted
- Date: 2026-07-29

## Context

The original brief split static hosting across GitHub Pages while already requiring
Vercel functions for FPL proxying and subscriptions. That creates two public origins,
CORS policy, two DNS surfaces and separate preview behavior without reducing v1 cost.

## Decision

Deploy the Vite application and TypeScript API together on Vercel. Keep heavy Python
projection and optimization work in GitHub Actions, with artifacts in Supabase.

## Consequences

- Browser/API traffic is same-origin.
- Vercel Git integration supplies pull-request previews.
- Static hosting and APIs share one production promotion.
- Heavy Python packages do not enter a Vercel function bundle.
