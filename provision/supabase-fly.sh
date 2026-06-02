#!/bin/bash
# Supabase CLI (GitHub release tarball) + flyctl (vendor installer).
# Idempotent; runs on every boot. Verify runs only at install time.
set -eu -o pipefail

ARCH=$(dpkg --print-architecture)

if [ ! -x /usr/local/bin/supabase ]; then
  tmp=$(mktemp -d)
  curl -fsSL "https://github.com/supabase/cli/releases/latest/download/supabase_linux_${ARCH}.tar.gz" \
    | tar -xz -C "$tmp"
  install -m 0755 "$tmp/supabase" /usr/local/bin/supabase
  rm -rf "$tmp"
  /usr/local/bin/supabase --version
fi

if [ ! -x /usr/local/bin/flyctl ]; then
  curl -fsSL https://fly.io/install.sh | FLYCTL_INSTALL=/usr/local bash
  /usr/local/bin/flyctl version
fi
