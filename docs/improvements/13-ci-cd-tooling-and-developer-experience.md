# 13. CI/CD, tooling and developer experience — work orders

Detailed briefs for items 168–184 of the [improvement audit](../../IMPROVEMENTS.md).
Each brief is self-contained: a sub-agent should be able to implement one item
from its brief alone.

Every brief obeys the repository rules: test-first where code is involved, treat
`docs/LIMITATIONS.md` as a hard capability boundary, never expose a Supabase
secret, Resend key or subscriber email, and never iterate directly on the hosted
production Supabase project.

---

## 168 — Cache the pnpm store and Playwright browser in CI (Impact: H)

**Files**: `.github/workflows/ci.yml` (job `validate`, lines 24–57)

**Problem**: The single `validate` job caches only the pip download store (via
`actions/setup-python`'s `cache: pip` at line 38). Every CI run reinstalls the
pnpm store from the network (`pnpm install --frozen-lockfile`, line 33) and
downloads the Chromium binary fresh (`playwright install --with-deps chromium`,
line 54). On a cold runner this adds three to five minutes of network I/O that is
identical between consecutive runs touching unrelated code.

**Change**:

1. After the "Enable pnpm" step, add an `actions/cache` step that saves and
   restores the pnpm store directory (`~/.local/share/pnpm/store` on Linux).
   Use a cache key composed of the runner OS and a hash of `pnpm-lock.yaml`, with
   a restore key of just the OS prefix so a lock-file change still gets a warm
   cache for unchanged packages.
2. After the "Install JavaScript dependencies" step (or combined with the cache
   step), add a separate `actions/cache` step for the Playwright browser cache
   directory (`~/.cache/ms-playwright`). Key on a hash of the Playwright version
   pin found in `apps/web/package.json` so a browser-version bump triggers a
   fresh download.
3. Use the `actions/cache` action pinned to its current full commit SHA (check
   the SHA used in other workflows for consistency). Do not tag-reference it.
4. Confirm the `actions/setup-node` step does not already activate pnpm-level
   caching by double-checking its `with:` block (line 25–27); if it does, remove
   the duplicate manual step.

**Constraints**: The single `validate` job and its required-status-check name
must not change (branch protection references `validate`). All new action
references must use full commit SHAs. The `cache: pip` parameter on
`actions/setup-python` (line 38) stays as-is. Secrets must not appear in cache
keys or log output.

**Tests first**: There is no local equivalent for cache hits; validation is a CI
run. Before opening the PR, run `pnpm install --frozen-lockfile` and
`pnpm --filter @fpl-andres/web exec playwright install --with-deps chromium`
locally and record their wall times as a baseline. After the PR lands, compare
the "Install JavaScript dependencies" and "Install browser" step durations across
two runs.

**Done when**:

1. The "Install JavaScript dependencies" step on a second consecutive run with no
   lock-file change reports a cache hit in its log.
2. The "Install browser" step on a second consecutive run with no Playwright
   version change reports a cache hit.
3. All existing steps in the `validate` job remain and pass.
4. No new action reference uses a mutable tag instead of a full SHA.
5. The required-status-check name `validate` is unchanged.

**Validate**: CI run on the pull request. Inspect step logs for "Cache restored
from key" messages on both new cache steps.

---

## 169 — Run CodeQL on pull requests (Impact: H)

> **⚠ Audit claim is false today.** `.github/workflows/codeql.yml` lines 4–9
> already include a `pull_request: branches: [main]` trigger. CodeQL _does_ run
> on every pull request targeting `main`. The claim that it runs "only on pushes
> to `main` and the weekly schedule" is stale.

**Actual gap**: The `pull_request` trigger runs CodeQL on every PR regardless of
the files changed, including documentation-only PRs. There is no path filter to
skip pure-doc changes, nor is there a `merge_group` trigger for the merge queue
(if one is later enabled). Additionally, the `codeql.yml` job `analyze` uses a
matrix over `[javascript-typescript, python]`; a PR that only changes Python
files still triggers the JavaScript-TypeScript analysis, doubling analysis time
unnecessarily.

**Change**:

1. Add `paths-ignore` to the `pull_request` trigger in `codeql.yml` to skip
   runs for changes confined to `docs/**`, `*.md` and `*.txt` files.
2. Evaluate adding a `merge_group` trigger so CodeQL also covers the merge-queue
   leg if branch protection is later upgraded to require it.
3. Document in a comment inside `codeql.yml` that both the `push` and
   `pull_request` triggers are intentional and that the weekly schedule covers
   the case where new query packs arrive between code changes.

**Constraints**: The `security-events: write` permission must remain. The
`fail-fast: false` matrix strategy must remain so a Python analysis failure does
not suppress the JavaScript report. All action SHAs are already pinned; do not
alter them without a separate dependency-review pass.

**Tests first**: Verify the current state by opening a draft PR and confirming
CodeQL runs appear in the "Checks" tab before applying path filters. After
adding `paths-ignore`, open a PR that changes only `docs/` and confirm the CodeQL
check is skipped.

**Done when**:

1. A PR whose diff is confined to `docs/**` files does not trigger the CodeQL
   workflow.
2. A PR that changes any file in `python/` or `api/` or `apps/` triggers both
   CodeQL matrix legs.
3. The workflow file carries a comment explaining the trigger rationale.

**Validate**: CI run on a documentation-only pull request (CodeQL skipped) and a
code-change pull request (CodeQL runs both legs).

---

## 170 — Split the monolithic `validate` job into parallel jobs (Impact: H)

**Files**: `.github/workflows/ci.yml` (job `validate`, lines 17–60)

**Problem**: All validation runs sequentially inside a single `validate` job with
a 20-minute timeout. A Playwright browser-journey failure surfaces only after
lint, typecheck, migrations and `pnpm check` have all completed, so a flaky E2E
test blocks the signal from fast checks. A lint failure similarly makes
contributors wait for the Supabase container to start. Parallelising the job
matrix would shorten the critical path from roughly 20 minutes to the duration
of the longest individual stage.

**Change**:

1. Create a `lint-and-typecheck` job that runs: `pnpm format:check`,
   `pnpm lint`, `pnpm typecheck`, `python -m ruff check python`,
   `python -m ruff format --check python`, `python -m mypy`. This job needs
   only Node and Python setup — no Supabase container, no browsers.
2. Create a `unit-tests` job that runs: `pnpm test` (JavaScript unit tests) and
   `python -m pytest` (Python unit tests). Also needs only Node and Python.
3. Create a `migrations` job that runs the Supabase steps:
   `pnpm exec supabase db start`, `pnpm exec supabase db reset --local`,
   `pnpm exec supabase db lint --local --level warning`.
4. Create a `browser-journeys` job that depends on `migrations` (or runs
   independently if migrations are not a prerequisite for E2E) and runs
   `pnpm --filter @fpl-andres/web exec playwright install --with-deps chromium`
   followed by `pnpm test:e2e`.
5. Update branch-protection required-status-check contexts to name each new job.
   **Call this out explicitly in the PR description** — removing the `validate`
   context and adding the four new names is a repository-settings change that
   must accompany the code change.
6. Remove the old `validate` job.

**Constraints**: Every job must set `permissions: contents: read`. Each job
must pin all action SHAs. The `pnpm check` omnibus command already calls most of
these steps; in the new structure each job calls the individual commands so each
stage can fail independently. Secrets are not used in `lint-and-typecheck` or
`unit-tests` jobs.

**Tests first**: Locally run each new job's command sequence in isolation to
confirm no implicit ordering dependency is hidden in `pnpm check`. In particular,
confirm `pnpm test` passes without `supabase db start` having run.

**Done when**:

1. All four new jobs appear as separate check contexts on a pull request.
2. A lint failure fails only `lint-and-typecheck`; E2E failures fail only
   `browser-journeys`.
3. The old `validate` context is removed from branch protection.
4. Total wall time on a green PR is lower than the previous 20-minute single job.
5. No job references a mutable action tag.

**Validate**: CI run on the pull request. Confirm parallel job execution in the
Actions tab timeline view.

---

## 171 — Run format check and lint before expensive steps (Impact: H)

**Files**: `.github/workflows/ci.yml` (steps "Check formatting" at line 59,
"Validate repository" at line 50)

**Problem**: "Check formatting" (`pnpm format:check`) is the very last step in
the `validate` job (line 59–60). A trivial formatting error — a missing trailing
newline or an extra space — causes the job to spin up a Supabase container,
install pip dependencies, run migrations, run `pnpm check` (which itself runs
lint, typecheck, tests and a full build), install Chromium and run browser
journeys before finally reporting the formatting failure. That wastes five to ten
minutes of runner time per PR.

**Change** (if item 170 is not yet implemented — otherwise defer to 170's
`lint-and-typecheck` job):

1. Move the "Check formatting" step to immediately after "Install JavaScript
   dependencies" (currently line 33) and before "Set up Python" (line 35). This
   requires no Python or Supabase.
2. Move ruff format check (`python -m ruff format --check python`) and ruff lint
   (`python -m ruff check python`) to immediately after "Install Python
   dependencies" (line 42), before the Supabase steps.
3. Move mypy (`python -m mypy`) to the same early block — it also needs no
   database.
4. Leave the Supabase steps, `pnpm check` and browser journeys in their current
   positions but after all format/lint steps.

**Constraints**: The `validate` job name must not change (required status check).
Step order changes must not break any step that depends on a previous step's side
effects; confirm `pnpm format:check` requires no build output by running it
locally on a clean checkout. The `pnpm check` command at line 50 internally calls
`contracts:check`, `lint`, `typecheck`, `test`, `build`, ruff, and mypy — the
early standalone calls become redundant fast-fail guards; `pnpm check` remains as
the authoritative gate.

**Tests first**: On a branch, intentionally introduce a formatting error and
confirm the job fails at the new earlier step rather than after migrations.

**Done when**:

1. A formatting-only failure causes the job to fail before the "Validate database
   migrations" step begins.
2. The `validate` job still ends with `pnpm check` and `pnpm test:e2e` as the
   authoritative gates.
3. CI is green on a correctly-formatted PR.

**Validate**: CI run on the pull request; additionally run `pnpm format:check`
locally to confirm no false positives.

---

## 172 — Written policy for full-SHA action pinning (Impact: M)

**Files**: `.github/workflows/ci.yml`, `codeql.yml`, `historical-ingest.yml`,
`capture-crowd.yml`, `live-contracts.yml`, `dependency-review.yml`

**Problem**: All six workflow files already pin every action to a full 40-character
commit SHA (verified: `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683`,
`actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020`, etc.). The current
pinning is correct but there is no written policy — no `CONTRIBUTING.md`, no
comment in the workflow files, no ADR — explaining the requirement. A new
contributor or Dependabot merge could introduce a mutable tag reference without
realising it violates the convention.

**Change**:

1. Add a comment block near the top of each workflow file (below the `on:` block,
   above `permissions:`) stating: "All action references in this file must use
   full 40-character commit SHAs, never mutable version tags. Dependabot keeps
   them current."
2. Add a `jobs.<job>.steps` note in the first workflow that acquires actions
   (e.g. `ci.yml`) to point contributors at the policy comment.
3. When `CONTRIBUTING.md` is created (item 190), add a "Workflow actions" section
   there that restates the rule and explains the supply-chain rationale.

**Constraints**: This is a documentation and comment change only; no action SHAs
may be altered as part of this item. Do not conflate with Dependabot updates
(item 178). The comment must not place a secret or any sensitive value inline.

**Tests first**: After adding comments, run `grep -r "uses:.*@v[0-9]"
.github/workflows/` to confirm no mutable-tag references exist. This grep command
serves as the ongoing enforcement check.

**Done when**:

1. Each of the six workflow files contains a SHA-pinning policy comment.
2. `grep -r "uses:.*@v[0-9]" .github/workflows/` returns no matches.
3. The policy is referenced from (or ready to be cross-referenced by)
   `CONTRIBUTING.md`.

**Validate**: `grep -rn "uses:.*@v[0-9]" .github/workflows/` (must return
nothing). CI run on the pull request.

---

## 173 — Per-step timeouts in long-running scheduled workflows (Impact: M)

**Files**: `.github/workflows/historical-ingest.yml` (job `ingest`, step
"Ingest seasons"), `.github/workflows/capture-crowd.yml` (job `capture`, step
"Capture crowd signal"), `.github/workflows/live-contracts.yml` (job
`validate-live-contracts`, step "Validate current FPL schema")

**Problem**: Both `historical-ingest.yml` and `capture-crowd.yml` set a
job-level `timeout-minutes` (120 and 15 respectively), but the most expensive
step in each — the Python CLI invocation — has no individual step timeout.
GitHub's `timeout-minutes` at the step level caps that step alone; without it, a
hung network request inside `fpl_andres.cli.capture_crowd` can consume the full
15-minute job budget before the runner kills it, delaying the failure signal for
other queued jobs. The `live-contracts.yml` job has a 10-minute job timeout but
its single CLI step also lacks a step-level timeout.

**Change**:

1. In `historical-ingest.yml`, add `timeout-minutes: 110` to the "Ingest
   seasons" step (leaving 10 minutes of headroom within the 120-minute job
   timeout for setup steps).
2. In `capture-crowd.yml`, add `timeout-minutes: 10` to the "Capture crowd
   signal" step (leaving 5 minutes for setup within the 15-minute job timeout).
3. In `live-contracts.yml`, add `timeout-minutes: 7` to the "Validate current
   FPL schema" step (leaving 3 minutes for setup within the 10-minute job
   timeout).
4. Do not add step timeouts to checkout, setup-python or pip-install steps; those
   already complete quickly and the job timeout covers them.

**Constraints**: Job-level `timeout-minutes` values must not be reduced. The step
timeout on "Ingest seasons" must be less than the job timeout (120 minutes) so
the job can still clean up. Secrets are passed as environment variables and must
not appear in any new log output.

**Tests first**: There is no local simulation for a step timeout. Verify by
reading the GitHub Actions documentation for `timeout-minutes` at the step level
to confirm the behaviour: the step is killed with exit code 1 and the job
reports failure. After the PR, confirm a deliberate slow step (e.g. `sleep 700`
in a test branch) is killed within the configured step timeout.

**Done when**:

1. Each of the three named steps carries an explicit `timeout-minutes` value.
2. The step timeout is strictly less than the parent job timeout.
3. CI on the PR is green (the `ci.yml` validate job is unaffected by these
   changes).

**Validate**: CI run on the pull request. Manual inspection of the three workflow
files to confirm step-level `timeout-minutes` keys are present.

---

## 174 — Cache Python dependencies in scheduled workflows (Impact: M)

> **⚠ Audit claim is false today.** All three scheduled workflows already cache
> pip dependencies. `historical-ingest.yml` uses
> `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065` with
> `cache: pip`. `capture-crowd.yml` and `live-contracts.yml` do the same. The
> claim that "only pip is cached in CI" and absent elsewhere is stale.

**Actual gap**: The scheduled workflows install the package with
`python -m pip install -e .` (without `[dev]`) so the pip cache key differs from
CI's `pip install -e ".[dev]"`. The cache is hit only when the same
`requirements.txt`-equivalent hash is present. Because the packages are different
(dev extras are absent), the scheduled workflow cache and the CI cache are
separate entries, which is correct — but this may not be obvious to contributors
who see two separate pip cache sizes in the Actions cache UI.

**Change**:

1. Add a comment to the `setup-python` step in each scheduled workflow explaining
   that `cache: pip` is active and that the cache key differs from CI because
   dev extras are not installed.
2. Optionally add `pip-requirements` pointing to `pyproject.toml` to make the
   cache key deterministic without a `requirements.txt` file — evaluate whether
   `actions/setup-python` supports `pyproject.toml` as a requirements file and,
   if so, add `pip-requirements: pyproject.toml` to all four `setup-python`
   usages (CI and the three scheduled workflows).

**Constraints**: The `[dev]` extras must not be installed in the scheduled
workflows; they pull in mypy, pytest and hypothesis which are not needed at
runtime and would bloat the production environment. Do not change the installed
package set.

**Tests first**: Confirm `cache: pip` is active by inspecting the "Set up Python"
step log in a recent workflow run for a "Cache restored from key" message.

**Done when**:

1. Each scheduled workflow's `setup-python` step log shows a cache hit on the
   second run with no `pyproject.toml` change.
2. The distinction between the CI cache key (with dev extras) and the scheduled
   workflow cache key (without) is documented in a comment.

**Validate**: Inspect GitHub Actions cache entries in the repository's
Settings → Actions → Caches tab after a scheduled workflow run.

---

## 175 — Validate dispatch inputs before shell array construction (Impact: M)

**Files**: `.github/workflows/capture-crowd.yml` (job `capture`, step "Capture
crowd signal"), `.github/workflows/historical-ingest.yml` (job `ingest`, step
"Ingest seasons")

**Problem**: Both workflows already pass `workflow_dispatch` inputs as environment
variables rather than direct shell substitutions (the files contain the comment
"Passed as env rather than inlined, so no input reaches the shell as code").
This prevents direct shell injection. However, neither workflow validates the
_format_ of the inputs before they reach the Python CLI. A malformed `season`
input (e.g. `"2026-27; rm -rf /"`) passed as an env var would be handed to the
Python CLI's argument parser, which must then reject it. If the CLI's validation
is incomplete, the malformed value could trigger unexpected behavior in the
database write path. The Python CLI's input validation has not been audited for
this flow.

**Change**:

1. In `capture-crowd.yml`, before the "Capture crowd signal" step, add a
   "Validate dispatch inputs" step that uses a `run:` block to check
   `$CAPTURE_SEASON` against a regex (e.g. `^[0-9]{4}-[0-9]{2}$` or empty) and
   `$CAPTURE_EVENT` against `^[0-9]{1,2}$` or empty, exiting with a non-zero
   code and a descriptive message if either fails.
2. Apply the same pattern in `historical-ingest.yml` for `INGEST_SEASONS` (allow
   `all` or comma-separated season strings) and `INGEST_GAMEWEEKS` (allow
   `1-47`, comma-separated integers, or the `all` shorthand).
3. In the Python CLI modules `fpl_andres.cli.capture_crowd` and
   `fpl_andres.cli.ingest_historical`, add argument-level validation using
   Python's `argparse` `type=` parameter or a custom validator that raises
   `argparse.ArgumentTypeError` for malformed values.
4. Add unit tests in `python/tests/` for the CLI validators: at least one valid
   input, one empty input (should be accepted), and one malformed input (should
   raise).

**Constraints**: Secrets (`SUPABASE_URL`, `SUPABASE_SECRET_KEY`) must not appear
in any validation log output. The shell validation step must use only POSIX
shell constructs (no Bash-only `=~` unless `bash` is the shell). The production
Supabase project must not be touched during testing.

**Tests first**: Write the Python unit tests for the CLI validators first. Run
with `python -m pytest python/tests/test_cli_validators.py -q` (or the
appropriate test file name). Then add the workflow validation steps.

**Done when**:

1. Python tests for both CLI validators pass.
2. A `workflow_dispatch` run with an invalid `season` input (e.g. `"2026;bad"`)
   fails at the "Validate dispatch inputs" step before the Python CLI runs.
3. A run with valid or blank inputs succeeds normally.
4. Validation log output contains no secret values.

**Validate**: `python -m pytest python/tests/ -q -k "cli"` (adjust selector to
the new test file). CI run on the pull request.

---

## 176 — Add a CODEOWNERS file (Impact: M)

**Files**: `.github/CODEOWNERS` (create new)

**Problem**: No `CODEOWNERS` file exists in the repository. Changes to the
database schema (`supabase/`), the API layer (`api/`) and the rules module
(`python/fpl_andres/rules.py`) can land on `main` without a designated reviewer
being automatically requested. These three areas carry the highest consequence for
correctness: schema changes modify production data structure, API changes affect
the public contract, and rules changes alter scored points calculations.

**Change**:

1. Create `.github/CODEOWNERS` with the following ownership groups:
   - `supabase/` → the repository owner (use the GitHub username, not an
     email).
   - `api/` → the repository owner.
   - `python/fpl_andres/rules.py` → the repository owner.
   - `python/fpl_andres/models/` → the repository owner.
   - `.github/workflows/` → the repository owner (to gate workflow edits).
   - A catch-all `*` entry for the owner so all other changes also request
     their review.
2. Verify the GitHub username used is the repository owner's login — it can be
   read from the repository URL or the `OWNER_SETUP.md` references.
3. Add a comment at the top of the file explaining why these paths are
   privileged.

**Constraints**: CODEOWNERS entries must use GitHub usernames prefixed with `@`.
GitHub only enforces CODEOWNERS review requirements when branch protection
"Require review from Code Owners" is enabled — note this in the PR description
and in `docs/RUNBOOK.md` under a new "Code review policy" section so the owner
can enable it. This change alone does not enable enforcement without the branch
protection setting.

**Tests first**: After creating the file, open a draft PR that modifies
`python/fpl_andres/rules.py` and confirm the owner appears in the "Reviewers"
section automatically.

**Done when**:

1. `.github/CODEOWNERS` exists and covers `supabase/`, `api/`,
   `python/fpl_andres/rules.py`, `python/fpl_andres/models/` and
   `.github/workflows/`.
2. A PR touching any of those paths shows the owner as a requested reviewer.
3. `docs/RUNBOOK.md` notes that branch protection must enable "Require review
   from Code Owners" to make the requirement mandatory.

**Validate**: Open a draft PR modifying a covered path and inspect the Reviewers
panel. CI run on the pull request for the CODEOWNERS file itself.

---

## 177 — Add pre-commit hooks for format, lint and contract regeneration (Impact: M)

**Files**: `.pre-commit-config.yaml` (create new), `docs/RUNBOOK.md` or
`CONTRIBUTING.md`

**Problem**: No `.pre-commit-config.yaml` exists. A contributor who does not run
`pnpm format:check` or `python -m ruff format --check python` locally will
discover the failure only in CI, after a push and a multi-minute wait. Similarly,
if `packages/contracts/` schemas are edited without regenerating the derived
TypeScript types (`pnpm contracts:generate`), CI fails at `pnpm contracts:check`
— again only after a push.

**Change**:

1. Create `.pre-commit-config.yaml` with three hook groups:
   - A local hook that runs `pnpm format:check` (requires Node and pnpm in
     `PATH`).
   - A local hook that runs `python -m ruff format --check python` and
     `python -m ruff check python` (requires Python 3.12 and ruff in `PATH`).
   - A local hook that runs `pnpm contracts:check` so a schema edit without
     regeneration is caught pre-commit.
2. Configure hooks as `stages: [pre-commit]` and `pass_filenames: false` so they
   run as whole-repository checks rather than per-file.
3. Add installation instructions to `CONTRIBUTING.md` (item 190):
   `pip install pre-commit && pre-commit install`. Note that Node 20+ and
   pnpm 9+ must be on `PATH` for the JS hooks to run.
4. Do not add hooks for mypy or `pnpm check` — those are too slow for a
   pre-commit gate; they belong in CI.

**Constraints**: The hooks must be local (no external `repo:` URLs that could be
compromised) or use pinned-SHA remote hooks only. The `.pre-commit-config.yaml`
format must pass `pre-commit validate-config`. The hooks must not write files
during the check phase — formatters must run in `--check` mode only, not auto-fix
mode (auto-fix on commit is disruptive for staged partial commits).

**Tests first**: Run `pre-commit run --all-files` on a clean checkout and confirm
it passes on the current codebase before committing the configuration file.

**Done when**:

1. `.pre-commit-config.yaml` exists and `pre-commit validate-config` passes.
2. `pre-commit run --all-files` passes on the current codebase.
3. Deliberately introducing a formatting error causes the pre-commit hook to
   fail before the commit is recorded.
4. Installation instructions appear in `CONTRIBUTING.md`.

**Validate**: `pre-commit run --all-files` from the repository root.

---

## 178 — Improve Dependabot grouping for security patches (Impact: M)

**Files**: `.github/dependabot.yml`

**Problem**: The npm ecosystem already has three groups (`dev-dependencies`,
`typescript-tooling`, `react`) and the `open-pull-requests-limit` is 5. However,
the pip ecosystem has no groups and a limit of 5, which means five concurrent pip
bump PRs can queue up and block a critical security patch from opening a slot.
The `github-actions` ecosystem has a limit of 3 and no groups. If Dependabot
opens five routine version bumps (e.g. hypothesis, mypy, pytest, ruff,
scipy-stubs) simultaneously, a security advisory for `httpx` (a runtime
dependency) cannot open a PR until one of the five is merged or closed.

**Change**:

1. Add a `groups:` block to the `pip` ecosystem entry with two groups:
   - `python-dev-tools`: matching `mypy`, `pytest*`, `ruff`, `hypothesis`,
     `respx`, `scipy-stubs` (development-only extras).
   - `python-runtime`: matching `httpx`, `numpy`, `pydantic`, `scipy` (runtime
     dependencies listed under `[project.dependencies]` in `pyproject.toml`).
     This ensures a runtime security bump always gets its own PR slot.
2. Raise `open-pull-requests-limit` for pip from 5 to 10, or explicitly set it
   to a higher value for the `python-runtime` group only (Dependabot v2 supports
   per-group limits via `update-types`).
3. Add a `github-actions` group called `workflow-actions` that matches all
   patterns so the three-PR limit is spent on one group PR rather than three
   individual action bumps.
4. Verify the resulting configuration with `yamllint .github/dependabot.yml` or
   similar.

**Constraints**: The schedule (Monday, 06:00 Europe/London) and label assignments
must not change. The `open-pull-requests-limit` increase must not cause the
Dependabot queue to overflow the repository's PR limit. Do not add packages to
the `ignoreGhsas` allowlist in `package.json` as part of this item.

**Tests first**: After committing the updated `dependabot.yml`, wait for the next
Monday trigger (or use the "Trigger Dependabot updates" button in the GitHub UI)
and verify that pip PRs are opened as grouped rather than individual.

**Done when**:

1. The pip ecosystem entry in `dependabot.yml` has a `groups:` block separating
   dev tools from runtime dependencies.
2. The github-actions ecosystem entry has a group that consolidates action bumps
   into a single PR.
3. `yamllint .github/dependabot.yml` (or equivalent schema check) passes.

**Validate**: CI run on the pull request; manual inspection of `dependabot.yml`
YAML structure. Observe next Dependabot run for grouping behavior.

---

## 179 — Bundle-size budget check for `apps/web` in CI (Impact: M)

**Files**: `.github/workflows/ci.yml` (job `validate`), `apps/web/vite.config.ts`
or `apps/web/package.json`

**Problem**: The `pnpm check` step (line 50 of `ci.yml`) runs `pnpm build` which
produces the Vite production bundle, but no CI step compares the bundle size
against a defined budget. The main entry chunk could silently grow — for example
if a static JSON data import is accidentally moved from a lazy-loaded route into
the eager bundle — without any CI signal. The `apps/web` application imports
projection and fixtures data whose size is bounded by the number of active
players (roughly 600–700 FPL elements) and should not grow unboundedly between
releases.

**Change**:

1. After the build step within the `validate` job (or in a dedicated
   `bundle-size` job if item 170 is implemented), add a step that reads the Vite
   build output's `stats.json` or uses `du` / `find` on `apps/web/dist/assets/`
   to sum the compressed size of the main JS chunk.
2. Define a threshold in `apps/web/package.json` under a `bundleSize` key (or a
   `.bundlesize.json` file) specifying the maximum gzipped size of the entry
   chunk in bytes. Start the threshold at 110% of the current measured size so
   the budget check passes immediately and ratchets down over time.
3. The CI step compares the measured size to the threshold and exits with a
   non-zero code if exceeded, printing the current and allowed sizes.
4. Add an npm script `size:check` to `apps/web/package.json` that performs the
   same check locally so contributors can run it before pushing.

**Constraints**: The size check must not require an external service. It must
measure gzipped size (which is what Vercel serves) rather than raw file size.
The threshold must be committed to the repository so it is reviewable. Do not use
proprietary bundle-analysis services. The check must pass on the current bundle
before the PR is opened.

**Tests first**: Build locally with `pnpm --filter @fpl-andres/web build` and
measure the current main chunk gzipped size with
`gzip -c apps/web/dist/assets/index-*.js | wc -c`. Use that figure to set the
initial threshold.

**Done when**:

1. The CI job includes a step that measures and compares bundle size.
2. The threshold is committed in a reviewable file.
3. Deliberately doubling the threshold causes the step to pass (sanity check);
   setting it to 1 byte causes it to fail.
4. A local `pnpm --filter @fpl-andres/web size:check` command produces the same
   result.

**Validate**: `pnpm --filter @fpl-andres/web size:check` locally. CI run on the
pull request.

---

## 180 — Add complexity checking to ruff configuration (Impact: M)

**Files**: `pyproject.toml` (section `[tool.ruff.lint]`, line 51)

**Problem**: The ruff `select` list in `pyproject.toml` (line 51) is
`["E", "F", "I", "UP", "B", "SIM", "RUF"]`. The `C90` code family (McCabe
complexity, enabled by `C` or `C90`) and the `W` family (pycodestyle warnings)
are absent. Without `C90`, the solver (`python/fpl_andres/solver/`) and the
projector (`python/fpl_andres/projector.py`) can accumulate cyclomatic complexity
without any automated gate. High-complexity functions are harder to test
exhaustively and riskier to modify without introducing regressions.

**Change**:

1. Add `"C90"` to the `select` list in `[tool.ruff.lint]`. This enables the
   `mccabe` checker and reports `C901` (function is too complex) violations.
2. Add a `[tool.ruff.lint.mccabe]` section and set
   `max-complexity = 10` as the ceiling. This is the widely used McCabe
   threshold; functions above 10 are flagged.
3. Run `python -m ruff check python` locally and collect all existing `C901`
   violations. For each violation, either: (a) refactor the function to reduce
   complexity, or (b) add a `# noqa: C901` comment with a `TODO` explaining
   why the complexity is acceptable, so the baseline is not silently broken.
4. Optionally add `"W"` for pycodestyle warnings, but evaluate first whether
   any existing warnings would require suppressions — add `"W"` only if the
   current codebase is clean.

**Constraints**: The `pnpm check` command calls `python -m ruff check python`; it
must remain green after this change. No `# type: ignore` comments may be
converted or removed as part of this item (see item 181). The complexity ceiling
must be committed as a configuration value, not left as the implicit default.

**Tests first**: Run `python -m ruff check python --select C90` before the PR to
identify which functions currently exceed the ceiling. Refactor or annotate each
one. All existing Python tests must continue to pass.

**Done when**:

1. `pyproject.toml` includes `"C90"` in `select` and a `[tool.ruff.lint.mccabe]`
   section with `max-complexity = 10`.
2. `python -m ruff check python` is clean (exit 0).
3. `python -m pytest` is green.
4. No `C901` violation is silently ignored — every `noqa: C901` has a comment.

**Validate**: `python -m ruff check python` (must exit 0). `python -m pytest`
(must pass). `pnpm check` on the PR.

---

## 181 — Audit and remove `type: ignore` comments (Impact: L)

**Files**: `python/tests/test_expected_points.py`,
`python/tests/test_backtest_persistence.py`, `python/tests/test_minileague.py`,
`python/tests/test_cohorts.py`, `python/tests/test_backtest.py`,
`python/tests/test_minutes_model.py`, `python/tests/test_clean_sheet_bound.py`,
`python/tests/test_deployment_signal.py`, `python/tests/test_rivals.py`

**Problem**: `pyproject.toml` sets `strict = true` for mypy, but 18+ `# type:
ignore` comments exist across nine test files. Each suppresses a real mypy
diagnostic — primarily `arg-type` errors caused by test code passing protocol
stubs or string literals where the production type expects an enum or a
dataclass. While `strict = true` is technically set, these suppressions mean the
claim is qualified: those call sites are not fully checked. The risk is that a
production function signature change would not be caught by mypy at the test
call sites.

**Change**:

1. For each `# type: ignore[arg-type]` in the test files, investigate the
   underlying cause:
   - If the test is passing an invalid literal to exercise error handling, use
     `cast()` or an explicit overloaded type to make the test intention clear
     without suppression.
   - If the production type is too narrow (e.g. a `Literal` type that should
     accept any `str` for testing), consider widening the production type or
     adding a test-only factory that accepts the broader type.
   - If the `type: ignore` is genuinely necessary (e.g. testing that a runtime
     guard catches a wrong type), replace it with a `# type: ignore[arg-type]`
     comment that includes a longer inline explanation, and add a `mypy` override
     in `pyproject.toml` for test files only as a last resort.
2. For `# type: ignore[union-attr]` in `test_cohorts.py` and
   `# type: ignore[arg-type]` in `test_backtest_persistence.py`: trace whether
   the production `Optional` or `Union` type can be narrowed so the guard is
   unnecessary.
3. Aim to reduce the count from 18+ to zero. If any are genuinely unmovable,
   document them in a new `[tool.mypy.overrides]` block scoped to the test
   module.

**Constraints**: `python -m mypy` must remain exit 0 throughout. Production
module types must not be widened just to silence test suppressions — the fix must
be in the test or via a typed test helper. Do not alter business logic in
`python/fpl_andres/` unless the type change is semantically correct.

**Tests first**: The test suite itself is the evidence. Run
`python -m mypy --no-error-summary` before and after each file change to
confirm the suppression count decreases.

**Done when**:

1. `grep -rn "type: ignore" python/` returns zero matches, or every remaining
   match has an inline justification comment and a corresponding `mypy.overrides`
   entry.
2. `python -m mypy` exits 0.
3. `python -m pytest` is green.

**Validate**: `grep -rn "type: ignore" python/` (target: zero). `python -m mypy`.
`python -m pytest`.

---

## 182 — Add contract regeneration and migration review to the PR template (Impact: L)

**Files**: `.github/pull_request_template.md`

**Problem**: The PR template already mentions "Migrations enable and test RLS"
and "Source freshness or contract changes" in its checklist. However, it does not
explicitly prompt contributors to run `pnpm contracts:generate` when they modify
files under `packages/contracts/` or `api/`, and it does not remind them that
migration review requires a local `pnpm exec supabase db reset --local` pass
before the PR is opened. The distinction between "contracts changed" (a source
state fact) and "contracts regenerated" (an action required) is currently absent.

**Change**:

1. Add a new checklist item under "Delivery": `[ ] If contracts schema changed,
\`pnpm contracts:generate\` was run and its output is committed`.
2. Add a new checklist item: `[ ] If a migration was added,
\`pnpm exec supabase db reset --local\` passed locally`.
3. Rename the existing "Source freshness or contract changes" evidence bullet to
   "Data contract or schema change" to make it unambiguous.
4. Keep all existing checklist items; do not remove or reorder them.

**Constraints**: The template is a Markdown file; formatting must pass
`pnpm format:check` (prettier). Do not add project-specific tooling commands
that are not in `package.json` scripts. The template must not reference secrets
or environment-specific configuration.

**Tests first**: No automated test for template content. Validate by reading the
updated template on a draft PR and confirming the new items are visible in the PR
description editor.

**Done when**:

1. The template contains explicit checklist items for contract regeneration and
   local migration validation.
2. `pnpm format:check` passes on the updated file.
3. A draft PR shows the updated checklist in the PR description.

**Validate**: `pnpm format:check`. Open a draft PR and verify the template
renders correctly.

---

## 183 — Add a pnpm alias for the local focused-test loop (Impact: L)

**Files**: `package.json` (root `scripts` section)

**Problem**: The `CONTRIBUTING.md` (item 190) and onboarding docs encourage a
"focused test → `pnpm check`" loop, but there is no single alias for the focused
step. A new contributor must know to run
`pnpm --filter @fpl-andres/web test -- src/path/to.test.ts` for a JavaScript
file or `python -m pytest python/tests/test_foo.py -q` for Python, then escalate
to `pnpm check` for the full gate. Typing these commands repeatedly under
deadline pressure increases the chance of running the wrong scope.

**Change**:

1. Add a `test:focused` script to the root `package.json` that accepts a
   glob or file argument and delegates it to the web workspace's Vitest runner:
   `corepack pnpm --filter @fpl-andres/web test --`. Contributors then run
   `pnpm test:focused src/path/file.test.ts`.
2. Add a `py:test` script: `python -m pytest` with `--no-header -q` flags so
   the output is compact.
3. Add a `py:test:focused` note (not a script, since pytest accepts arguments
   natively): document in `CONTRIBUTING.md` that
   `python -m pytest python/tests/test_foo.py -q` is the focused Python
   equivalent.
4. Add a `loop` script that runs `pnpm test:focused` then `pnpm check` — useful
   for pre-commit validation of a full change. Note it requires a file argument
   be passed before `pnpm check` runs, so it should be documented rather than
   scripted if chaining is awkward.

**Constraints**: Scripts in `package.json` must be valid JSON strings. Do not
wrap `pnpm check` in an alias that hides its output — `pnpm check` must remain
the explicitly named final gate. Script names must not clash with existing entries
(`build`, `check`, `dev`, `format`, `lint`, `test`, `test:e2e`, `typecheck`,
`contracts:check`, `contracts:generate`).

**Tests first**: Run each new script alias on the current codebase to confirm it
works: `pnpm test:focused apps/web/src` should invoke Vitest on the web package.

**Done when**:

1. `pnpm test:focused` is present and delegates correctly to the web Vitest
   runner.
2. `pnpm py:test` runs `python -m pytest` with compact output.
3. Both commands are documented in `CONTRIBUTING.md` (or in the new section
   added by item 190).
4. `pnpm format:check` passes on the updated `package.json`.

**Validate**: `pnpm test:focused apps/web/src` (Vitest runs). `pnpm py:test`
(pytest runs). `pnpm format:check`.

---

## 184 — Document why runtime dependencies are pinned exactly (Impact: L)

**Files**: `package.json` (root `dependencies` and `devDependencies`),
`docs/RUNBOOK.md` or `CONTRIBUTING.md`

**Problem**: The root `package.json` pins three dependencies to exact versions
without a range operator: `zod` at `4.4.3`, `typescript` at `6.0.3`, and
`@vercel/node` at `5.9.0`. A new contributor seeing these alongside the
range-pinned pyproject.toml dependencies (`httpx>=0.28,<1`) might loosen them to
`^4.4.3` on a routine Dependabot update, not realising the exact pins are
intentional. The consequences could be: a zod minor release that changes parsing
behaviour (zod v4 has a history of breaking changes), a TypeScript release that
rejects previously valid code in strict mode, or a `@vercel/node` update that
changes the `VercelRequest`/`VercelResponse` types in an incompatible way.

**Change**:

1. Add a comment block in `package.json` (using a `"//":` comment key or a
   companion `docs/` document, since JSON does not support inline comments)
   explaining the pinning rationale for each of the three packages.
2. Create a section "Dependency pinning policy" in `docs/RUNBOOK.md` (or in
   `CONTRIBUTING.md` once created) that states:
   - `zod` is pinned exactly because its v4 minor releases have changed parse
     semantics that the contracts package relies on. Upgrades must be tested
     against all `packages/contracts/` schema parse round-trips.
   - `typescript` is pinned exactly because TypeScript minor releases sometimes
     tighten assignability rules under `strict: true`. The test is
     `pnpm typecheck` passing with zero errors after the bump.
   - `@vercel/node` is pinned exactly because it provides the `VercelRequest`
     and `VercelResponse` types used by every `api/*.ts` handler; a type-breaking
     minor release would cause `pnpm typecheck` failures on Vercel without local
     warning.
   - Dev tools (`eslint`, `prettier`, `typescript-eslint`) use exact pins for
     reproducible CI output — a minor ESLint release can add new rule triggers.
3. Add a note stating that Dependabot is configured to propose these bumps, and
   that a Dependabot PR for any of these three packages requires an explicit
   `pnpm typecheck` and `pnpm check` pass before merging.

**Constraints**: This is a documentation change only. Do not change any version
pin values. Do not add a `"//":` comment key that breaks JSON parsers — if JSON
comments are used, verify `package.json` still parses with `node -e
"require('./package.json')"`.

**Tests first**: Not applicable for a documentation change. Validate by reading
the section on a PR.

**Done when**:

1. A "Dependency pinning policy" section exists in `docs/RUNBOOK.md` or
   `CONTRIBUTING.md` covering the three exact-pinned packages.
2. The rationale for each pin is tied to a specific test command that proves the
   upgrade is safe.
3. `pnpm format:check` passes.

**Validate**: `pnpm format:check`. Manual review of the section for accuracy
against the current `package.json` versions.
