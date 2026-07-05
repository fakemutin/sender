#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 https://github.com/USER/REPO.git"
  exit 1
fi

REPO_URL="$1"

git init -b main 2>/dev/null || git checkout -B main
git add -A
git diff --cached --quiet && echo "Nothing to commit" || git commit -m "Initial commit: TG Broadcast"
git remote remove origin 2>/dev/null || true
git remote add origin "$REPO_URL"
git push -u origin main

echo "Done: $REPO_URL"
