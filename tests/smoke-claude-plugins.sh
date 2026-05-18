#!/usr/bin/env bash
# Smoke: every plugin listed in provision.toml's [claude] section is installed,
# and Claude's permission defaultMode is "auto".
set -euo pipefail
NAME="${MACHINE_NAME:?set MACHINE_NAME}"

EXPECTED=(
  frontend-design
  superpowers
  github
  typescript-lsp
  security-guidance
  commit-commands
  chrome-devtools-mcp
  supabase
)

list=$(limactl shell "$NAME" -- bash -lc 'claude plugin list 2>&1')

for p in "${EXPECTED[@]}"; do
  echo "$list" | grep -q "$p" \
    || { echo "missing plugin: $p"; echo "$list"; exit 1; }
done

# Verify auto-mode is the default in user settings.
mode=$(limactl shell "$NAME" -- bash -lc "python3 -c 'import json,sys; print(json.load(open(\"/home/$USER.linux/.claude/settings.json\"))[\"permissions\"][\"defaultMode\"])'")
[ "$mode" = "auto" ] || { echo "defaultMode is '$mode', expected 'auto'"; exit 1; }

echo "claude-plugins OK"
