#!/usr/bin/env bash
# Republish the derived planning chain from whatever inputs are on disk.
#
# Both odds jobs own a different source artifact and the same derived ones:
# season inputs, the canonical fifteen, the static plan and the pre-deadline
# freeze. They are triggered by the same push and run concurrently, so each can
# find the branch moved under it when it goes to push. A rebase cannot settle
# that -- there is no textual merge of two independently regenerated artifacts,
# and `--autostash` just relocates the conflict. The only merge that yields a
# coherent set is to take the base that arrived and rebuild on it, which is why
# this chain is a script both jobs can call twice rather than a block of steps
# either of them can only run once.
set -euo pipefail

before="$(node -e "const p=require('./apps/web/src/data/opening-squad.json'); process.stdout.write(p.picks.map(x=>x.code).sort((a,b)=>a-b).join(','))")"

python -m fpl_andres.cli.publish_season_inputs
pnpm --filter @fpl-andres/web publish:canonical-opening

after="$(node -e "const p=require('./apps/web/src/data/opening-squad.json'); process.stdout.write(p.picks.map(x=>x.code).sort((a,b)=>a-b).join(','))")"

# The static plan is a bounded 38-week solve. It only has to run again when the
# fifteen it starts from actually moved.
if [ "$before" != "$after" ]; then
  weekly_free_transfers="$(node -e "const p=require('./apps/web/src/data/season-inputs.json'); process.stdout.write(String(p.rules.weeklyFreeTransfers))")"
  transfer_cost_points="$(node -e "const p=require('./apps/web/src/data/season-inputs.json'); process.stdout.write(String(p.rules.transferCostPoints))")"
  rules_reference="$(node -e "const p=require('./apps/web/src/data/season-inputs.json'); process.stdout.write(p.rules.sourceReference)")"
  python -m fpl_andres.cli.publish_season_plan \
    --weekly-free-transfers "$weekly_free_transfers" \
    --transfer-cost-points "$transfer_cost_points" \
    --rules-reference "$rules_reference"
else
  echo "canonical fifteen unchanged; static plan remains valid"
fi

# prettier owns these and Python does not write them that way. Formatting before
# the caller's staged-diff check also stops a rewrite that is only formatting
# from reaching `git commit` and failing it empty.
npx --yes prettier@3 --write \
  apps/web/src/data/season-inputs.json \
  apps/web/src/data/opening-squad.json \
  apps/web/src/data/season-plan.json

# Evidence frozen before the outcome is known is the only evidence worth
# freezing, so this stops the moment the deadline passes.
deadline="$(node -e "const p=require('./apps/web/src/data/season-inputs.json'); process.stdout.write(p.deadlines[0])")"
if node -e "process.exit(Date.now() < Date.parse(process.argv[1]) ? 0 : 1)" "$deadline"; then
  python -m fpl_andres.cli.freeze_prospective \
    --deadline "$deadline" \
    --frozen-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --code-revision "${GITHUB_SHA:-$(git rev-parse HEAD)}"
  npx --yes prettier@3 --write data/prospective/gw1-2026-27.json
else
  echo "deadline passed; the pre-deadline freeze stands as it was"
fi
