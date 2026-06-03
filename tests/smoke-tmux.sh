#!/usr/bin/env bash
# Smoke: tmux is provisioned and detached sessions survive the SSH
# connection that created them (the mechanism behind `machine claude`).
set -euo pipefail
NAME="${MACHINE_NAME:?set MACHINE_NAME}"

SESSION="machine-smoke-tmux"

# tmux present (provision/base.sh apt list).
limactl shell "$NAME" -- bash -lc 'command -v tmux >/dev/null' \
  || { echo "tmux not installed"; exit 1; }

# Clean slate, then create a detached session the way cmd_claude does
# (new-session with a command), over a connection that immediately closes.
limactl shell "$NAME" -- bash -lc "tmux kill-session -t $SESSION 2>/dev/null; true"
limactl shell "$NAME" -- bash -lc "tmux new-session -d -s $SESSION 'sleep 300'"

# The session outlives the connection that created it.
limactl shell "$NAME" -- bash -lc "tmux has-session -t $SESSION" \
  || { echo "detached session did not survive"; exit 1; }

# Killing the session removes it (mirrors claude exiting).
limactl shell "$NAME" -- bash -lc "tmux kill-session -t $SESSION"
if limactl shell "$NAME" -- bash -lc "tmux has-session -t $SESSION 2>/dev/null"; then
  echo "session still present after kill"; exit 1
fi

echo "tmux OK"
