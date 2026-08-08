# Contributing

This project has one maintainer and a small number of rules that are not
negotiable, because each of them exists to stop a specific way of being wrong.

## The loop

```bash
# One focused test while you work
python -m pytest python/tests/test_thing.py -q
corepack pnpm --filter @fpl-andres/web test -- --run thing

# Everything, before you commit
corepack pnpm check
corepack pnpm test:e2e
```

`pnpm check` runs prettier, contract drift, lint, types, unit tests, the build,
ruff, mypy and pytest with a coverage floor. Prettier is the first step because
it is the cheapest and the one most often forgotten. `pnpm check` does **not**
run the browser journeys; CI runs those separately, so a green `check` is
necessary and not sufficient.

## Test first

Write the failing test before the fix. Not as ceremony — the point is to prove
the test can fail, because a test written afterwards often passes for reasons
unrelated to the change.

This has paid for itself repeatedly. The regression test asserting the Supabase
key never reaches a log found a real leak on its first run: upstream error
bodies were passed into exception messages, and a gateway that quotes the
offending `apikey` header back on a 401 put the service-role key into the logs.
The masked `__repr__` everyone trusted did not cover that path.

## Measure before you assert

If you are about to write "this is negligible", "this is faster" or "this is
more accurate", measure it and put the number in the commit message.

The Poisson truncation carried a comment saying the tail beyond it was below
floating-point noise. Measured, it held 33% of the mass at 14 saves a match and
cost 1.88 points. The comment had been true of nothing in particular.

Two tests in this repository assert a property that a first version got wrong
because it was guessed: the de-vig bias widens as a _ratio_ and not as a
difference, and season pairing must be calendar-adjacent rather than
adjacent-in-a-sorted-list. Both were caught by measuring.

## Never default a missing rule

If a controlling FPL rule cannot be sourced, the code must fail visibly rather
than pick a plausible value. `SuspensionRules` will not construct without a
caller supplying the thresholds _and_ naming where they came from, because the
yellow-card accumulation ladder could not be sourced and a guess would have been
indistinguishable from a fact.

The same applies to parameters. A half-life or a shrinkage strength is sourced
and recorded in `docs/MODEL.md`, or it is fitted through the promotion gate in
`models/promotion.py`. It is never chosen because it looked about right.

See the capability boundaries in [`README.md`](README.md#capability-boundaries),
which are a hard boundary rather than a wish list.

## Say what you did not do

A negative result is a result. Record the measurement that closed a line of
work, in the commit message if nowhere else, so nobody spends the effort twice.
An audit item that turns out to be already-correct gets recorded as such rather
than silently skipped.

## What must not happen

- No secret in the browser bundle, a log, an exception or a commit.
- No write to production Supabase outside a tracked migration that passes a
  clean `db reset`. Migration filenames are dependency order; a file
  referencing a table created by a later-sorting file passes on an
  already-migrated environment and fails only on a clean reset.
- No optimizer code copied from another FPL solver.
- No published number without the artifact that produced it.

## Dependencies are pinned exactly

Audit item #184. Every entry in every `package.json` is an exact version — no
`^`, no `~`. That is deliberate and it is not the npm default, so it will look
like an oversight to anyone who has not read this.

Three reasons, in order of how much they cost when ignored:

**`zod` validates the contract shared with Python.** The schemas in
`packages/contracts` are the browser half of a contract whose other half is a
Pydantic model, and `python/tests/test_contract_round_trip.py` asserts the two
agree. A caret range means a `zod` minor release can change coercion behaviour
on a Friday deploy and the two halves stop agreeing, with the Python suite still
green because nothing there moved.

**`typescript` decides whether the code compiles.** A minor release adds
inference rules and new errors. With a range, a build that passed this morning
fails this afternoon on a commit that touched nothing, and the first person to
notice is whoever is trying to ship something unrelated.

**`@vercel/node` is the runtime contract for `api/`.** The handler signature and
the request and response types come from it. A range means the deployed runtime
can differ from the one the types were checked against.

The tradeoff is real: exact pins mean Dependabot opens more PRs, and each needs
a human to look at it. That is the intended trade. Renovate-style auto-merge on
a range makes the upgrade invisible; a PR makes it a decision.

**To upgrade:** change the exact version, run `corepack pnpm check`, and say in
the commit message what the release notes claimed and what you verified. If it
is `zod`, run the round-trip test specifically and say so.

## Commit messages

Say what changed and why it was wrong before. Include the measurement. A reader
six months later needs the reasoning, not the diff — they can already see the
diff.
