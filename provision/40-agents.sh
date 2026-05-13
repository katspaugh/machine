#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=/dev/null  # path exists only inside the VM
source /opt/dev-vm/lib/_lib.sh

# Always-run (idempotent): ensure ~/.local/bin is on PATH in every login shell.
# The standalone Claude Code installer drops its binary there.
cat > /etc/profile.d/local-bin.sh <<'EOF'
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
EOF
chmod 0644 /etc/profile.d/local-bin.sh

NAME=40-agents
is_done "$NAME" && { log "$NAME" "already done"; exit 0; }

LIMA_USER="$(lima_user)"

# Claude Code: standalone installer.
sudo -u "$LIMA_USER" -i bash -c 'curl -fsSL https://claude.ai/install.sh | bash'
sudo -u "$LIMA_USER" -i bash -lc 'command -v claude >/dev/null' \
  || { echo "40-agents: claude install verification failed" >&2; exit 1; }

# Codex: npm global.
sudo -u "$LIMA_USER" -i bash -lc 'npm install -g @openai/codex'
sudo -u "$LIMA_USER" -i bash -lc 'command -v codex >/dev/null' \
  || { echo "40-agents: codex install verification failed" >&2; exit 1; }

mark_done "$NAME"
log "$NAME" "ok"
