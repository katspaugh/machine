#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=/dev/null  # path exists only inside the VM
source /opt/dev-vm/lib/_lib.sh

NAME=10-docker
is_done "$NAME" && { log "$NAME" "already done"; exit 0; }

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --batch --yes --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

# shellcheck source=/dev/null  # path exists only inside the VM
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update -qq
apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

LIMA_USER="$(lima_user)"
usermod -aG docker "$LIMA_USER"

systemctl enable --now docker

mark_done "$NAME"
log "$NAME" "ok"
