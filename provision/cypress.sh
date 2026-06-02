#!/bin/bash
# Cypress system deps + a browser. Chrome on amd64 (no arm64 .deb exists);
# chromium-browser on arm64. Idempotent; runs on every boot.
set -eu -o pipefail
export DEBIAN_FRONTEND=noninteractive

ARCH=$(dpkg --print-architecture)

PKGS=(libgtk2.0-0 libgtk-3-0 libgbm-dev libnotify-dev libnss3 libxss1
      libasound2t64 libxtst6 xauth xvfb fonts-liberation)

if [ "$ARCH" = "amd64" ]; then
  key=/etc/apt/keyrings/google-chrome.gpg
  if [ ! -f "$key" ]; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
      | gpg --batch --yes --dearmor -o "$key"
    chmod a+r "$key"
  fi
  echo "deb [arch=amd64 signed-by=$key] http://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list
  PKGS+=(google-chrome-stable)
else
  PKGS+=(chromium-browser)
fi

# Non-fatal on offline re-boots (see provision/base.sh).
apt-get update -qq || true
apt-get install -y --no-install-recommends "${PKGS[@]}"
