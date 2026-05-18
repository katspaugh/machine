#!/usr/bin/env bash
# Smoke: Node major version is current, corepack works, yarn shim is present,
# COREPACK_ENABLE_DOWNLOAD_PROMPT=0 (so pnpm downloads don't prompt).
set -euo pipefail
NAME="${MACHINE_NAME:?set MACHINE_NAME}"

limactl shell "$NAME" -- bash -lc 'node --version | grep -E "^v(20|22|24)\."'
limactl shell "$NAME" -- bash -lc 'corepack --version'
limactl shell "$NAME" -- bash -lc 'corepack pnpm --version'
limactl shell "$NAME" -- bash -lc 'command -v yarn'
# shellcheck disable=SC2016  # body runs inside the VM
limactl shell "$NAME" -- bash -lc '[ "${COREPACK_ENABLE_DOWNLOAD_PROMPT:-}" = "0" ]'

echo "node OK"
