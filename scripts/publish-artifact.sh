#!/usr/bin/env bash
set -euo pipefail

publish_artifact() {
  local message="$1" rebuild="$2"
  shift 2
  git config user.name "github-actions[bot]"
  git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
  for attempt in 1 2 3 4 5; do
    git add -- "$@"
    if git diff --cached --quiet -- "$@"; then
      echo "artifact unchanged"
      return 0
    fi
    git commit -m "$message"
    if git push; then
      return 0
    fi
    echo "publication attempt $attempt conflicted; rebuilding on the latest base"
    git fetch origin "$GITHUB_REF_NAME"
    git reset --hard "origin/$GITHUB_REF_NAME"
    "$rebuild"
  done
  echo "could not publish the rebuilt artifact after five attempts" >&2
  return 1
}