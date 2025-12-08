#!/usr/bin/env bash
set -euo pipefail

ruff check . --fix
ruff format .

python -m pytest -q -vv

echo "✅ All green. Pushing…"
git add -A
git commit -m "push-on-green: lint+tests green"
git push
