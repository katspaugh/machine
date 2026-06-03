#!/usr/bin/env bash
# Verify auxiliary CLIs (supabase, flyctl, gh) are on PATH and runnable.
set -euo pipefail
NAME="${MACHINE_NAME:?set MACHINE_NAME}"

limactl shell "$NAME" -- bash -lc 'command -v supabase && supabase --version'
limactl shell "$NAME" -- bash -lc 'command -v flyctl && flyctl version'
limactl shell "$NAME" -- bash -lc 'command -v gh && gh --version'

# Base CLI tools (provision/base.sh).
limactl shell "$NAME" -- bash -lc 'command -v rg && rg --version'
limactl shell "$NAME" -- bash -lc 'command -v batcat && batcat --version'
limactl shell "$NAME" -- bash -lc 'command -v fzf && fzf --version'
limactl shell "$NAME" -- bash -lc 'command -v delta && delta --version'
limactl shell "$NAME" -- bash -lc 'command -v lazygit && lazygit --version'
limactl shell "$NAME" -- bash -lc 'command -v hx && hx --version'

echo "clis OK"
