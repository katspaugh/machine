#!/usr/bin/env bash
# Usage: MACHINE_NAME=<project> bash tests/run-all.sh
# (or pass the project as arg 1)
set -euo pipefail
cd "$(dirname "$0")"

if [ -n "${1:-}" ]; then
  export MACHINE_NAME="$1"
fi

failed=()
for t in lint.sh smoke-*.sh; do
  [ -f "$t" ] || continue
  echo "=== $t ==="
  if bash "$t"; then
    echo "PASS: $t"
  else
    failed+=("$t")
    echo "FAIL: $t"
  fi
done
if [ ${#failed[@]} -gt 0 ]; then
  echo "Failed: ${failed[*]}" >&2
  exit 1
fi
echo "All smoke tests passed."
