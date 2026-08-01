# 1. Forced row level security with no policies

- **Status**: accepted
- **Date**: 2026-08-01 (recording a decision already encoded in the migrations)

## Context

Every table in `supabase/migrations/` is created with both
`enable row level security` and `force row level security`, and none of them
carries a single `create policy` statement.

To anyone reading the schema fresh, that looks like an unfinished job. Postgres
with RLS forced and no policies denies every row to every role except one that
bypasses RLS entirely. It is indistinguishable, in the SQL, from a developer who
turned RLS on and then forgot to write the policies.

It was deliberate, and the reasoning was never written down.

## Decision

Keep the deny-all posture. Add named policies only when a table genuinely needs
to be readable by an untrusted client, and never as a blanket enabling step.

## Consequences

**The browser reads nothing from Postgres.** Everything the site displays comes
from one of two places: a committed JSON artifact built by a CLI, or the
serverless proxy in `api/`, which talks to the public FPL API and never to the
database. There is no anon-key path from the browser to a table, so there is no
policy to get wrong.

**Writes go through the service role only**, from Python jobs that hold
`SUPABASE_SECRET_KEY`. That key bypasses RLS, which is why the tables are
`force`d rather than merely `enable`d: forcing means even the table owner is
subject to policies, so a future migration that accidentally runs as owner
cannot quietly read rows the posture is meant to deny.

**A missing policy fails closed.** If someone later exposes a table to the anon
key without writing a policy, the result is an empty result set and a visible
bug, not a leak. The failure mode points the right way.

**The cost is that adding a browser-readable table is not a one-line change.**
It requires a policy, a test that the policy denies what it should, and a
deliberate decision that the data is public. That friction is the point.

## Alternatives considered

**Enable RLS without forcing it.** Rejected: the owner role would bypass
policies, so a migration or a psql session running as owner would see
everything, and the protection would depend on nobody making that mistake.

**Leave RLS off and rely on not exposing the anon key.** Rejected: it makes the
security property a deployment configuration rather than a schema property. A
single environment variable in the wrong place would expose every table, and
nothing in the repository would have changed to warn anyone.

**Write permissive policies now, in anticipation.** Rejected: a policy written
before there is a reader is a policy nobody can test against a real access
pattern, and it converts a deny-all default into an allow-something default for
no present benefit.
