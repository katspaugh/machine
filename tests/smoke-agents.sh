#!/usr/bin/env bash
# Smoke: agent CLIs (claude, codex) are installed and runnable.
set -euo pipefail
NAME="${MACHINE_NAME:?set MACHINE_NAME}"

limactl shell "$NAME" -- bash -lc 'command -v claude && claude --version'
limactl shell "$NAME" -- bash -lc 'command -v codex && codex --version'

echo "agents OK"
