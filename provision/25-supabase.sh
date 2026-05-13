#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=/dev/null  # path exists only inside the VM
source /opt/dev-vm/lib/_lib.sh

NAME=25-supabase
is_done "$NAME" && { log "$NAME" "already done"; exit 0; }

# Supabase CLI: prebuilt binary from GitHub releases. npm global install is
# deprecated; brew is mac-only. The release artifact is a tarball containing
# a single `supabase` binary.
ARCH=$(dpkg --print-architecture)   # amd64 | arm64
case "$ARCH" in
  amd64|arm64) ;;
  *) echo "25-supabase: unsupported arch $ARCH" >&2; exit 1 ;;
esac

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

curl -fsSL "https://github.com/supabase/cli/releases/latest/download/supabase_linux_${ARCH}.tar.gz" \
  | tar -xz -C "$TMP"
install -m 0755 "$TMP/supabase" /usr/local/bin/supabase

/usr/local/bin/supabase --version >/dev/null \
  || { echo "25-supabase: install verification failed" >&2; exit 1; }

mark_done "$NAME"
log "$NAME" "ok"
