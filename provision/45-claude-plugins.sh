#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=/dev/null  # path exists only inside the VM
source /opt/dev-vm/lib/_lib.sh

# Always-run (idempotent): re-installing a plugin that's already at the latest
# version is a no-op, and `claude plugin marketplace add` short-circuits if
# the marketplace already exists. Keeping this un-sentinelled means a fresh
# `machine up` picks up any plugin additions to this script.

LIMA_USER="$(lima_user)"

PLUGINS=(
  frontend-design
  superpowers
  github
  typescript-lsp
  security-guidance
  commit-commands
  chrome-devtools-mcp
  supabase
)

# Add the official marketplace (idempotent — exits 0 if already added).
sudo -u "$LIMA_USER" -i bash -lc '
  claude plugin marketplace add anthropics/claude-plugins-official 2>&1 \
    | grep -vi "already" || true
'

for p in "${PLUGINS[@]}"; do
  sudo -u "$LIMA_USER" -i bash -lc "
    claude plugin install '$p@claude-plugins-official' 2>&1 \
      | grep -vi 'already installed' || true
  "
done

# Settings: enable each plugin + default permission mode = auto.
USER_HOME=$(getent passwd "$LIMA_USER" | cut -d: -f6)
install -d -m 0755 -o "$LIMA_USER" -g "$LIMA_USER" "$USER_HOME/.claude"

SETTINGS_TMP=$(mktemp)
cat > "$SETTINGS_TMP" <<'EOF'
{
  "permissions": {
    "defaultMode": "auto"
  },
  "enabledPlugins": {
    "frontend-design@claude-plugins-official": true,
    "superpowers@claude-plugins-official": true,
    "github@claude-plugins-official": true,
    "typescript-lsp@claude-plugins-official": true,
    "security-guidance@claude-plugins-official": true,
    "commit-commands@claude-plugins-official": true,
    "chrome-devtools-mcp@claude-plugins-official": true,
    "supabase@claude-plugins-official": true
  }
}
EOF
install -m 0644 -o "$LIMA_USER" -g "$LIMA_USER" "$SETTINGS_TMP" "$USER_HOME/.claude/settings.json"
rm -f "$SETTINGS_TMP"

log "45-claude-plugins" "ok"
