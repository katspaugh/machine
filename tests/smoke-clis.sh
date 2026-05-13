#!/usr/bin/env bash
# Verify auxiliary CLIs (supabase, flyctl) are on PATH and runnable.
set -euo pipefail
NAME="${MACHINE_NAME:?set MACHINE_NAME}"

limactl shell "$NAME" -- bash -lc 'command -v supabase && supabase --version'
limactl shell "$NAME" -- bash -lc 'command -v flyctl && flyctl version'

echo "clis OK"
