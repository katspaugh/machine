#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=/dev/null  # path exists only inside the VM
source /opt/dev-vm/lib/_lib.sh

NAME=20-node
is_done "$NAME" && { log "$NAME" "already done"; exit 0; }

curl -fsSL https://mise.run | MISE_INSTALL_PATH=/usr/local/bin/mise sh

cat > /etc/profile.d/mise.sh <<'EOF'
if command -v mise >/dev/null 2>&1; then
  eval "$(mise activate bash --shims)"
fi
# Let corepack download project-pinned package managers without prompting.
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
EOF
chmod 0644 /etc/profile.d/mise.sh

LIMA_USER="$(lima_user)"

sudo -u "$LIMA_USER" -i mise use --yes --global node@lts
sudo -u "$LIMA_USER" -i mise exec -- corepack enable
sudo -u "$LIMA_USER" -i mise exec -- corepack prepare pnpm@latest --activate
sudo -u "$LIMA_USER" -i mise exec -- corepack prepare yarn@stable --activate

sudo -u "$LIMA_USER" -i bash -lc 'npm install -g typescript typescript-language-server'

mark_done "$NAME"
log "$NAME" "ok"
