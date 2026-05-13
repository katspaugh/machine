#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=/dev/null  # path exists only inside the VM
source /opt/dev-vm/lib/_lib.sh

NAME=60-cypress
is_done "$NAME" && { log "$NAME" "already done"; exit 0; }

apt_install libgtk2.0-0 libgtk-3-0 libgbm-dev libnotify-dev libnss3 \
  libxss1 libasound2t64 libxtst6 xauth xvfb fonts-liberation

ARCH=$(dpkg --print-architecture)
if [ "$ARCH" = "amd64" ]; then
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
    | gpg --batch --yes --dearmor -o /etc/apt/keyrings/google.gpg
  echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list
  apt-get update -qq
  apt_install google-chrome-stable
else
  apt_install chromium-browser
fi

mark_done "$NAME"
log "$NAME" "ok"
