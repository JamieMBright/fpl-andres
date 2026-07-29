# FPL Andres Repository Instructions

- Treat `docs/LIMITATIONS.md` as a hard capability boundary.
- Implement behavior through a failing focused test, minimal code, then refactor.
- Never default a missing controlling FPL rule; fail its source contract visibly.
- Keep `EvidenceLevel` and source timestamps attached to recommendations.
- Do not copy optimizer code from external FPL solvers.
- Never expose a Supabase secret, Resend key or subscriber email to browser code or logs.
- Keep manual team-state overrides separate from public last-deadline state.
- Use the repository's design skills and `DESIGN.md` for frontend work.
- Preserve the two original untracked strategist documents unless the owner explicitly
  asks to adopt them into Git.
- Run focused validation immediately after each substantive edit and `pnpm check`
  before committing a milestone.
