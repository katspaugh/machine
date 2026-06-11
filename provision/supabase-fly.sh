#!/bin/bash
# Supabase CLI (.deb release artifact) + flyctl (tarball release artifact).
# Idempotent; runs on every boot. Verify runs only at install time.
# Version-pinned with per-arch sha256 of the release assets — bump the
# *_VERSION/*_SHA256 pairs together to upgrade (checksums.txt in each release).
set -eu -o pipefail

ARCH=$(dpkg --print-architecture)

# fetch <url> <sha256> <dest> — download a release asset and verify its hash.
fetch() {
  curl -fsSL -o "$3" "$1"
  echo "$2  $3" | sha256sum -c -
}

SUPABASE_VERSION=2.106.0
case "$ARCH" in
  amd64) SUPABASE_SHA256=5277b538e75fab1429b8b143a71b025308ae4846cd58ad8fef82328a4d080f64 ;;
  arm64) SUPABASE_SHA256=a004217bc9e146e6aede8f7f26138fbd94cfdffa5ed4c6b9983bc8b804e5c928 ;;
esac

# `command -v` (not a path test) keeps the guard true for older VMs with the
# tarball-era /usr/local binary.
if ! command -v supabase >/dev/null 2>&1; then
  tmp=$(mktemp -d)
  fetch "https://github.com/supabase/cli/releases/download/v${SUPABASE_VERSION}/supabase_${SUPABASE_VERSION}_linux_${ARCH}.deb" \
    "$SUPABASE_SHA256" "$tmp/supabase.deb"
  apt-get install -y "$tmp/supabase.deb"
  rm -rf "$tmp"
  supabase --version
fi

FLYCTL_VERSION=0.4.59
case "$ARCH" in
  amd64) FLY_ARCH=x86_64
         FLYCTL_SHA256=1c560d9dbdbfdccf1fe4899ae6e55dd073cc7b5400fc15d9ae4d0176c4eff17d ;;
  arm64) FLY_ARCH=arm64
         FLYCTL_SHA256=33745457758150e500e80fc8d47e2fc68803302c668b1bca845c8b284e17c17e ;;
esac

if [ ! -x /usr/local/bin/flyctl ]; then
  # cloud-init runs provision scripts as root without $HOME set, and the
  # flyctl binary reads $HOME for its config dir — pin it so the version
  # check below runs non-interactively.
  export HOME="${HOME:-/root}"
  tmp=$(mktemp -d)
  fetch "https://github.com/superfly/flyctl/releases/download/v${FLYCTL_VERSION}/flyctl_${FLYCTL_VERSION}_Linux_${FLY_ARCH}.tar.gz" \
    "$FLYCTL_SHA256" "$tmp/flyctl.tar.gz"
  tar -xz -C "$tmp" -f "$tmp/flyctl.tar.gz" flyctl
  install -m 0755 "$tmp/flyctl" /usr/local/bin/flyctl
  rm -rf "$tmp"
  /usr/local/bin/flyctl version
fi
