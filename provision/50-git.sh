#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=/dev/null  # path exists only inside the VM
source /opt/dev-vm/lib/_lib.sh

LIMA_USER="$(lima_user)"
USER_HOME=$(getent passwd "$LIMA_USER" | cut -d: -f6)

install -m 0644 -o "$LIMA_USER" -g "$LIMA_USER" \
  /opt/dev-vm/files/git/gitconfig "$USER_HOME/.gitconfig"

install -d -m 0755 -o "$LIMA_USER" -g "$LIMA_USER" "$USER_HOME/.config/git"
install -m 0644 -o "$LIMA_USER" -g "$LIMA_USER" \
  /opt/dev-vm/files/git/allowed_signers "$USER_HOME/.config/git/allowed_signers"

log "50-git" "ok"
