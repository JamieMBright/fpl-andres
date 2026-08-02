## Behavior

Describe what a user or operator can now do.

## TDD evidence

- Failing check before implementation:
- Focused passing check:
- Affected-suite check:

## Evidence and limitations

- Source freshness or contract changes:
- Model/calibration impact:
- Known unavailable behavior:

## Delivery

- [ ] No unrelated changes
- [ ] Migrations enable and test RLS
- [ ] Browser bundles contain no server secrets
- [ ] Mobile, keyboard and degraded states checked where relevant
- [ ] Changelog and runbook updated where relevant

## If this changed a contract or the schema

Skip this section if neither applies.

- [ ] **Contracts regenerated.** `corepack pnpm contracts:generate`, and the
      diff is in this PR. A Pydantic model edited without regenerating leaves
      the browser validating against the old shape, which is a runtime failure
      no test here would catch.
- [ ] **Round trip still holds.** `python -m pytest python/tests/test_contract_round_trip.py`
- [ ] **Migration reviewed against `docs/SCHEMA.md`.** New tables appear in the
      ERD and follow the naming conventions; a test enforces both.
- [ ] **Migration added to the checklist** in `docs/OWNER_SETUP.md`, so its
      applied state can be recorded. Production is bootstrapped by pasting SQL,
      not by `db push`.
- [ ] **Teardown updated.** `supabase/rollback/down.sql` drops anything the
      migration creates, or the recovery path fails mid-incident.
