#!/bin/bash
# Base provisioning — runs as root on EVERY boot (cloud-init scripts-per-boot).
# Everything here must be idempotent and cheap when already applied.
# {{.User}}/{{.Home}}/{{.Param.shell}} are Lima guest-template variables,
# substituted when the instance is created.
set -eu -o pipefail
export DEBIAN_FRONTEND=noninteractive

ARCH=$(dpkg --print-architecture)
# shellcheck source=/dev/null
CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
LIMA_USER="{{.User}}"
USER_HOME="{{.Home}}"

# Heal ownership of dirs that mode:data file placement may have created as
# root (e.g. ~/.config, ~/.ssh on first boot).
chown -R "$LIMA_USER:$LIMA_USER" "$USER_HOME/.config" "$USER_HOME/.ssh" 2>/dev/null || true

# --- Third-party apt repos --------------------------------------------------
install -m 0755 -d /etc/apt/keyrings
add_repo() { # <name> <key_url> <deb_line>
  local key="/etc/apt/keyrings/$1.gpg"
  if [ ! -f "$key" ]; then
    curl -fsSL "$2" | gpg --batch --yes --dearmor -o "$key"
    chmod a+r "$key"
  fi
  echo "deb [arch=$ARCH signed-by=$key] $3" > "/etc/apt/sources.list.d/$1.list"
}
add_repo docker https://download.docker.com/linux/ubuntu/gpg \
  "https://download.docker.com/linux/ubuntu $CODENAME stable"
add_repo github-cli https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  "https://cli.github.com/packages stable main"
add_repo nodesource https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
  "https://deb.nodesource.com/node_22.x nodistro main"

# --- Packages ----------------------------------------------------------------
# Non-fatal: an offline re-boot of an already-provisioned VM must not fail
# the boot probe. If packages are genuinely missing, the install below
# still fails fast.
apt-get update -qq || true
apt-get install -y --no-install-recommends \
  build-essential ca-certificates curl gnupg jq xz-utils unzip git zsh \
  zsh-autosuggestions zsh-syntax-highlighting \
  ripgrep fd-find tmux less file python3 direnv \
  bubblewrap socat \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
  gh nodejs

usermod -aG docker "$LIMA_USER"
systemctl enable --now docker

# --- Claude Code sandbox: Ubuntu 24.04 AppArmor allowance ---------------------
# The built-in Bash sandbox (enabled in base-user.sh) uses bubblewrap, which
# needs unprivileged user namespaces. Ubuntu 24.04's default AppArmor policy
# denies bwrap that capability, so the sandbox would silently fall back to
# unsandboxed. Grant it a profile when — and only when — the restriction is on.
# Idempotent; non-fatal so an offline re-boot never fails the boot probe.
if [ "$(sysctl -n kernel.apparmor_restrict_unprivileged_userns 2>/dev/null || echo 0)" = "1" ]; then
  if [ ! -f /etc/apparmor.d/bwrap ]; then
    cat > /etc/apparmor.d/bwrap <<'EOF'
abi <abi/4.0>,
include <tunables/global>

profile bwrap /usr/bin/bwrap flags=(unconfined) {
  userns,
  include if exists <local/bwrap>
}
EOF
    systemctl reload apparmor || true
  fi
fi

# --- corepack-managed package managers + npm globals -------------------------
# apt-installed Node keeps globals in /usr/lib/node_modules (root-owned).
# First install must succeed (fail fast while baking); once the probe binary
# exists, refreshes are best-effort so offline re-boots don't fail the boot
# probe. `corepack enable` is a local shim write — always safe.
# Version-pinned so every boot installs the same artifacts (npm/corepack
# verify registry integrity hashes themselves). Bump to upgrade.
PNPM_VERSION=11.5.3
YARN_VERSION=4.16.0
TYPESCRIPT_VERSION=6.0.3
TS_LANGSERVER_VERSION=5.3.0
CODEX_VERSION=0.139.0
refresh() { # <probe-bin> <cmd...>
  local probe="$1"; shift
  if command -v "$probe" >/dev/null 2>&1; then
    "$@" || true
  else
    "$@"
  fi
}
corepack enable
refresh pnpm corepack prepare "pnpm@$PNPM_VERSION" --activate
refresh yarn corepack prepare "yarn@$YARN_VERSION" --activate
refresh tsc npm install -g "typescript@$TYPESCRIPT_VERSION" \
  "typescript-language-server@$TS_LANGSERVER_VERSION" "@openai/codex@$CODEX_VERSION"

# --- Default login shell ------------------------------------------------------
TARGET_SHELL="{{.Param.shell}}"
case "$TARGET_SHELL" in
  zsh|bash) chsh -s "/usr/bin/$TARGET_SHELL" "$LIMA_USER" || true ;;
  *) echo "unknown shell: $TARGET_SHELL" >&2; exit 1 ;;
esac
