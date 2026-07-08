#!/usr/bin/env bash
# Smoke: Claude Code's built-in Bash sandbox is actually usable in the VM —
# deps present, the 24.04 AppArmor allowance works, and it's enabled in settings.
set -euo pipefail
NAME="${MACHINE_NAME:?set MACHINE_NAME}"

# bubblewrap + socat: the two Linux sandbox deps installed by provision/base.sh.
limactl shell "$NAME" -- bash -lc 'command -v bwrap && command -v socat' >/dev/null

# When Ubuntu 24.04's userns restriction is on, provision/base.sh must have
# written the AppArmor profile that lets bwrap create user namespaces. Guard on
# the sysctl so kernels without the restriction don't false-fail.
# shellcheck disable=SC2016  # $(sysctl ...) must expand in the guest shell, not here
limactl shell "$NAME" -- bash -lc '
  set -eu
  if [ "$(sysctl -n kernel.apparmor_restrict_unprivileged_userns 2>/dev/null || echo 0)" = "1" ]; then
    [ -f /etc/apparmor.d/bwrap ] || { echo "missing /etc/apparmor.d/bwrap"; exit 1; }
  fi
  # The real proof: bwrap can create the namespaces the sandbox needs.
  bwrap --unshare-user --unshare-net --dev-bind / / true
'

# sandbox.enabled must be true in the provisioned user settings. HOME must
# resolve in the guest, so let the guest shell expand it.
enabled=$(limactl shell "$NAME" -- bash -lc \
  'python3 -c "import json,os; print(json.load(open(os.path.expanduser(\"~/.claude/settings.json\")))[\"sandbox\"][\"enabled\"])"')
[ "$enabled" = "True" ] || { echo "sandbox.enabled is '$enabled', expected True"; exit 1; }

echo "sandbox OK"
