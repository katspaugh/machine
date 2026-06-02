#!/bin/bash
# Supabase CLI (.deb release artifact) + flyctl (vendor installer).
# Idempotent; runs on every boot. Verify runs only at install time.
set -eu -o pipefail

ARCH=$(dpkg --print-architecture)

# The .deb assets are version-stamped (no `latest` filename alias like the
# tarballs), so resolve the latest tag from the release-page redirect —
# plain HTTP, no GitHub API rate limits. `command -v` (not a path test)
# keeps the guard true for older VMs with the tarball-era /usr/local binary.
if ! command -v supabase >/dev/null 2>&1; then
  tag=$(curl -fsSLo /dev/null -w '%{url_effective}' \
    https://github.com/supabase/cli/releases/latest)
  tag=${tag##*/}                  # .../releases/tag/v2.104.0 → v2.104.0
  version=${tag#v}
  tmp=$(mktemp -d)
  curl -fsSL -o "$tmp/supabase.deb" \
    "https://github.com/supabase/cli/releases/download/${tag}/supabase_${version}_linux_${ARCH}.deb"
  apt-get install -y "$tmp/supabase.deb"
  rm -rf "$tmp"
  supabase --version
fi

if [ ! -x /usr/local/bin/flyctl ]; then
  # cloud-init runs provision scripts as root without $HOME set. Both fly.io's
  # install.sh and the flyctl binary itself read $HOME (installer for shell-rc
  # detection, binary for its config dir) and abort when it is undefined. Pin
  # it for the install + verify so this first-boot block runs non-interactively.
  export HOME="${HOME:-/root}"
  curl -fsSL https://fly.io/install.sh | FLYCTL_INSTALL=/usr/local bash
  /usr/local/bin/flyctl version
fi
