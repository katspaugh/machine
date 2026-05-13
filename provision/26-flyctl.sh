#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=/dev/null  # path exists only inside the VM
source /opt/dev-vm/lib/_lib.sh

NAME=26-flyctl
is_done "$NAME" && { log "$NAME" "already done"; exit 0; }

# fly.io CLI (flyctl): use upstream installer. FLYCTL_INSTALL=/usr/local
# diverts it from the default $HOME/.fly/ so flyctl lands at
# /usr/local/bin/flyctl, matching the rest of the toolchain. The installer
# resolves the latest version and the correct arch automatically.
curl -fsSL https://fly.io/install.sh | FLYCTL_INSTALL=/usr/local bash

/usr/local/bin/flyctl version >/dev/null \
  || { echo "26-flyctl: install verification failed" >&2; exit 1; }

mark_done "$NAME"
log "$NAME" "ok"
