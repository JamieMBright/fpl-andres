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

python -m fpl_andres.cli.publish_season_inputs
pnpm --filter @fpl-andres/web publish:canonical-opening

# Fixture and player prices can change every transfer, captain and chip without
# changing the canonical fifteen. The static plan therefore belongs to the
# complete derived chain, not only to opening-squad changes.
weekly_free_transfers="$(node -e "const p=require('./apps/web/src/data/season-inputs.json'); process.stdout.write(String(p.rules.weeklyFreeTransfers))")"
transfer_cost_points="$(node -e "const p=require('./apps/web/src/data/season-inputs.json'); process.stdout.write(String(p.rules.transferCostPoints))")"
rules_reference="$(node -e "const p=require('./apps/web/src/data/season-inputs.json'); process.stdout.write(p.rules.sourceReference)")"
python -m fpl_andres.cli.publish_season_plan \
  --weekly-free-transfers "$weekly_free_transfers" \
  --transfer-cost-points "$transfer_cost_points" \
  --rules-reference "$rules_reference"

# prettier owns these and Python does not write them that way. Formatting before
# the caller's staged-diff check also stops a rewrite that is only formatting
# from reaching `git commit` and failing it empty.
npx --yes prettier@3 --write \
  apps/web/src/data/season-inputs.json \
  apps/web/src/data/opening-squad.json \
  apps/web/src/data/season-plan.json

# The CLI selects the first event whose deadline is still ahead, from the full
# deadline ledger. Using `season-inputs.deadlines[0]` after GW1 paired GW2's
# deadline with the default event 1 and rewrote a supposedly frozen historical
# manifest.
python -m fpl_andres.cli.freeze_prospective \
  --frozen-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --code-revision "${GITHUB_SHA:-$(git rev-parse HEAD)}"
npx --yes prettier@3 --write data/prospective/*.json
