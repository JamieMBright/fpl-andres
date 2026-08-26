#!/usr/bin/env bash
# Rebuild the ranked cohort and both explicitly based portfolio series from the
# source files on disk. Shared because capture, annotation and the catalogue
# sweep can race while regenerating the same JSON artifacts.
set -euo pipefail

python -m fpl_andres.cli.publish_fpl500

files=(
  data/cohort/fpl500.json
  apps/web/src/data/fpl500.json
)
for directory in data/cohort/portfolio data/cohort/fpl500-membership; do
  if [ ! -d "$directory" ]; then
    continue
  fi
  while IFS= read -r -d '' path; do
    files+=("$path")
  done < <(find "$directory" -type f -name '*.json' -print0)
done

npx --yes prettier@3 --write "${files[@]}"