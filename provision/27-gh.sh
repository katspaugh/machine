#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=/dev/null  # path exists only inside the VM
source /opt/dev-vm/lib/_lib.sh

NAME=27-gh
is_done "$NAME" && { log "$NAME" "already done"; exit 0; }

# GitHub CLI: install from the official apt repo so future `apt-get upgrade`
# (run by `machine update`) keeps it current.
ARCH=$(dpkg --print-architecture)
KEYRING=/usr/share/keyrings/githubcli-archive-keyring.gpg

curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  | tee "$KEYRING" >/dev/null
chmod go+r "$KEYRING"

echo "deb [arch=$ARCH signed-by=$KEYRING] https://cli.github.com/packages stable main" \
  > /etc/apt/sources.list.d/github-cli.list

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt_install gh

gh --version >/dev/null \
  || { echo "27-gh: install verification failed" >&2; exit 1; }

mark_done "$NAME"
log "$NAME" "ok"
