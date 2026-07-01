#!/bin/bash
# User provisioning — runs as the lima user on every boot, after base.sh.
# Installs Claude Code + the plugin set. Idempotent: re-runs are no-ops.
set -eu -o pipefail

export PATH="$HOME/.local/bin:$PATH"

# Version-pinned (`install.sh <version>` instead of the floating default);
# the installer verifies the downloaded binary's sha256 against the release
# manifest, so the pin is what makes the install reproducible. Bump to upgrade.
CLAUDE_VERSION=2.1.173
if ! command -v claude >/dev/null 2>&1; then
  curl -fsSL https://claude.ai/install.sh | bash -s "$CLAUDE_VERSION"
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

# Settings: defaultMode + enabled-plugin map + built-in sandbox.
# The sandbox is a real defense-in-depth layer inside the VM: git and docker
# run outside it (git needs the forwarded SSH-agent socket for signing/push;
# docker is sandbox-incompatible). failIfUnavailable makes a missing sandbox a
# hard failure rather than a silent unsandboxed fallback — base.sh installs the
# bubblewrap/socat deps and the 24.04 AppArmor profile that back that promise.
# Generated via python3 (a base dep) so the nested object stays valid JSON.
mkdir -p "$HOME/.claude"
MARKETPLACE_ID="$MARKETPLACE_ID" PLUGINS="$PLUGINS" python3 - > "$HOME/.claude/settings.json" <<'EOF'
import json, os
mid = os.environ["MARKETPLACE_ID"]
plugins = os.environ["PLUGINS"].split()
settings = {
    "permissions": {"defaultMode": "auto"},
    "enabledPlugins": {f"{p}@{mid}": True for p in plugins},
    "sandbox": {
        "enabled": True,
        "excludedCommands": ["git", "docker"],
        "failIfUnavailable": True,
    },
}
print(json.dumps(settings, indent=2))
EOF
