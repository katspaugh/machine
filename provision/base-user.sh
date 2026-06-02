#!/bin/bash
# User provisioning — runs as the lima user on every boot, after base.sh.
# Installs Claude Code + the plugin set. Idempotent: re-runs are no-ops.
set -eu -o pipefail

export PATH="$HOME/.local/bin:$PATH"

if ! command -v claude >/dev/null 2>&1; then
  curl -fsSL https://claude.ai/install.sh | bash
fi
command -v claude >/dev/null

MARKETPLACE="anthropics/claude-plugins-official"
MARKETPLACE_ID="claude-plugins-official"
PLUGINS="frontend-design superpowers github typescript-lsp security-guidance commit-commands chrome-devtools-mcp supabase"

# `claude plugin ...` is noisy when already done: treat "already"/"exists"
# output as success, propagate anything else.
run_claude() {
  local out rc=0
  out=$(claude "$@" 2>&1) || rc=$?
  if [ "$rc" -ne 0 ] && ! printf '%s' "$out" | grep -qi -e "already" -e "exists"; then
    printf '%s\n' "$out" >&2
    return "$rc"
  fi
  printf '%s\n' "$out"
}

# Skip the network-backed marketplace/install work once a prior boot fully
# provisioned the plugin set: settings.json is written last (below), so its
# plugin list doubles as the success marker. Keeps re-boots fast and
# offline-safe; plugin updates ride fresh VMs / `machine bake`.
plugins_provisioned() {
  [ -f "$HOME/.claude/settings.json" ] || return 1
  local p
  for p in $PLUGINS; do
    grep -q "\"$p@$MARKETPLACE_ID\": true" "$HOME/.claude/settings.json" || return 1
  done
}

if ! plugins_provisioned; then
  run_claude plugin marketplace add "$MARKETPLACE"
  for p in $PLUGINS; do
    run_claude plugin install "$p@$MARKETPLACE_ID"
  done
fi

# Settings: defaultMode + the enabled-plugin map.
mkdir -p "$HOME/.claude"
{
  printf '{\n  "permissions": { "defaultMode": "auto" },\n  "enabledPlugins": {\n'
  first=1
  for p in $PLUGINS; do
    [ "$first" -eq 1 ] || printf ',\n'
    printf '    "%s@%s": true' "$p" "$MARKETPLACE_ID"
    first=0
  done
  printf '\n  }\n}\n'
} > "$HOME/.claude/settings.json"
