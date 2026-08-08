# FPL Andres Repository Instructions

- Read `README.md` first. It is the working brief: capability boundaries, the
  migration ledger, retention and the conventions that bite.
- Treat the capability boundaries in `README.md` as hard.
- Implement behavior through a failing focused test, minimal code, then refactor.
- Never default a missing controlling FPL rule; fail its source contract visibly.
- Keep `EvidenceLevel` and source timestamps attached to recommendations.
- Do not copy optimizer code from external FPL solvers.
- Never expose a Supabase secret, Resend key or subscriber email to browser code or logs.
- The sole hosted Supabase project is production. VS Code MCP is disabled by organization
  policy; do not bypass that policy or add alternate interactive database connectors.
- Apply only tracked migrations that pass local policy tests and Linux CI. The initial
  production bootstrap is the ordered SQL Editor checklist in `README.md`.
  Never iterate directly on production schema or inspect application rows through AI tools.
- Keep manual team-state overrides separate from public last-deadline state.
- Use the repository's design skills and `DESIGN.md` for frontend work.
- Preserve the two original untracked strategist documents unless the owner explicitly
  asks to adopt them into Git.
- Run focused validation immediately after each substantive edit and `pnpm check`
  before committing a milestone.
- Never hand-format a file prettier owns. Run `corepack pnpm format` and commit its
  output; if prettier will not run, say so instead of guessing the column widths.
