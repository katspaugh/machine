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

# bin/machine is Python; sanity-check it parses.
python3 -c "import ast; ast.parse(open('bin/machine').read())"

echo "lint OK"
