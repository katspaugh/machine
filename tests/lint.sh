#!/usr/bin/env bash
# Static checks for the repo's shell scripts.
# Uses shellcheck if installed (`brew install shellcheck`); else `bash -n`.
set -euo pipefail
cd "$(dirname "$0")/.."

scripts=()
while IFS= read -r f; do
  scripts+=("$f")
done < <(find bin provision tests scripts -type f -name '*.sh')

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck -x "${scripts[@]}"
else
  echo "lint: shellcheck not installed — falling back to bash -n syntax checks"
  for f in "${scripts[@]}"; do
    bash -n "$f"
  done
fi

# Python sources: ruff if installed (`brew install ruff`); else a bare
# syntax check so the script at least parses.
if command -v ruff >/dev/null 2>&1; then
  ruff check .
else
  echo "lint: ruff not installed — falling back to ast.parse syntax checks"
  python3 -c "import ast; ast.parse(open('bin/machine').read())"
fi

echo "lint OK"
