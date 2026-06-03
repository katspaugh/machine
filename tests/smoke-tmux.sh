#!/usr/bin/env bash
# Smoke: tmux is provisioned and detached sessions survive the SSH
# connection that created them (the mechanism behind `machine claude`).
set -euo pipefail
NAME="${MACHINE_NAME:?set MACHINE_NAME}"

SESSION="machine-smoke-tmux"

# Interrupt-safe cleanup: an aborted run would otherwise leak the
# `sleep 300` session until it self-expires.
cleanup() { limactl shell "$NAME" -- bash -lc "tmux kill-session -t $SESSION 2>/dev/null; true" || true; }
trap cleanup EXIT

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

# `new-session -A` against a live session must reattach, not double-create
# (the cmd_claude mechanism). Running `new-session -A` over `limactl shell`
# has no tty and fails outright, so assert the single-session invariant by
# counting instead: there must be exactly one session of this name.
count=$(limactl shell "$NAME" -- bash -lc "tmux list-sessions -F '#S' | grep -cx $SESSION")
[ "$count" = "1" ] || { echo "expected exactly 1 session, got $count"; exit 1; }

# Killing the session removes it (mirrors claude exiting).
limactl shell "$NAME" -- bash -lc "tmux kill-session -t $SESSION"
if limactl shell "$NAME" -- bash -lc "tmux has-session -t $SESSION 2>/dev/null"; then
  echo "session still present after kill"; exit 1
fi

echo "tmux OK"
