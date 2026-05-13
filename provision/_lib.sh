#!/usr/bin/env bash
# Sourced by every provision script.
set -euo pipefail

SENTINEL_DIR=/var/lib/dev-vm/provisioned
mkdir -p "$SENTINEL_DIR"

log() { printf '[provision %s] %s\n' "$1" "$2" >&2; }
is_done() { [ -f "$SENTINEL_DIR/$1" ]; }
mark_done() { date -u +%FT%TZ > "$SENTINEL_DIR/$1"; }

apt_install() {
  [ "$#" -gt 0 ] || { echo "apt_install: no packages" >&2; return 1; }
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@"
}

# The "real" user inside the Lima VM. Lima 2.x maps the host UID 1:1, which on
# macOS is typically 501 — so any `UID >= 1000` filter excludes it. The
# provision scripts are invoked via `sudo bash` (see bin/machine), so
# $SUDO_USER is reliably the lima user.
lima_user() {
  if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    echo "$SUDO_USER"
    return
  fi
  awk -F: '$1 != "root" && $7 ~ /sh$/ {print $1; exit}' /etc/passwd
}
