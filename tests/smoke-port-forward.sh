#!/usr/bin/env bash
# Start a Python HTTP server in the VM (foreground, time-bounded), then poll
# it from the host. While the limactl SSH session is alive, python is alive,
# and Lima auto-forwards listening guest ports to 127.0.0.1 on the host.
set -euo pipefail
NAME="${MACHINE_NAME:?set MACHINE_NAME}"
PORT=3007
EXPECT='<h1>hi from VM</h1>'
SERVER_LIFETIME=30

limactl shell "$NAME" -- bash -lc "pkill -f 'python3 -m http.server $PORT' 2>/dev/null || true" </dev/null >/dev/null 2>&1 || true

limactl shell "$NAME" -- bash -lc "
  cd /tmp && printf '%s\n' '$EXPECT' > index.html
  timeout ${SERVER_LIFETIME}s python3 -m http.server $PORT --bind 0.0.0.0
" </dev/null >/dev/null 2>&1 &
SSH_PID=$!
# shellcheck disable=SC2317,SC2329  # invoked via trap
cleanup() {
  kill "$SSH_PID" 2>/dev/null || true
  limactl shell "$NAME" -- bash -lc "pkill -f 'python3 -m http.server $PORT' 2>/dev/null || true" </dev/null >/dev/null 2>&1 || true
}
trap cleanup EXIT

for _ in $(seq 1 50); do
  body=$(curl -fs --max-time 1 "http://127.0.0.1:$PORT/" 2>/dev/null || true)
  if [ "$body" = "$EXPECT" ]; then
    echo "port-forward OK"
    exit 0
  fi
  sleep 0.5
done

echo "host could not reach VM port $PORT after 25s" >&2
exit 1
