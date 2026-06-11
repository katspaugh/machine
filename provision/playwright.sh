#!/bin/bash
# Playwright OS deps for its browsers (chromium, firefox, webkit). Browser
# binaries stay per-repo (`npx playwright install` — version-matched, and
# needs no sudo once these deps exist). Idempotent; runs on every boot.
set -eu -o pipefail
export DEBIAN_FRONTEND=noninteractive

# Needs node/npx from base.sh (the generated stack runs base.sh first).
# `install-deps` resolves the package list for the pinned playwright
# release, so we don't hand-maintain ~50 apt names. Version-pinned for
# reproducible provisioning — bump to upgrade. First boot must succeed
# (fail fast while provisioning a new VM); the marker keeps re-boots fast
# and offline-safe (see provision/base.sh for the same pattern).
PLAYWRIGHT_VERSION=1.60.0
marker=/var/lib/machine/playwright-deps
if [ ! -f "$marker" ]; then
  npx -y "playwright@$PLAYWRIGHT_VERSION" install-deps
  install -D /dev/null "$marker"
fi
