#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=/dev/null  # path exists only inside the VM
source /opt/dev-vm/lib/_lib.sh

NAME=00-base
is_done "$NAME" && { log "$NAME" "already done"; exit 0; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get -y upgrade

apt_install \
  build-essential ca-certificates curl gnupg jq xz-utils unzip \
  git zsh ripgrep fd-find tmux less file python3

LIMA_USER="$(lima_user)"
chsh -s /usr/bin/zsh "$LIMA_USER" || true

mark_done "$NAME"
log "$NAME" "ok"
