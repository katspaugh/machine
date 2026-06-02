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
  build-essential ca-certificates curl gnupg jq xz-utils unzip git zsh fish \
  ripgrep fd-find tmux less file python3 direnv \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
  gh nodejs

usermod -aG docker "$LIMA_USER"
systemctl enable --now docker

# --- corepack-managed package managers + npm globals -------------------------
# apt-installed Node keeps globals in /usr/lib/node_modules (root-owned).
# First install must succeed (fail fast while baking); once the probe binary
# exists, refreshes are best-effort so offline re-boots don't fail the boot
# probe. `corepack enable` is a local shim write — always safe.
refresh() { # <probe-bin> <cmd...>
  local probe="$1"; shift
  if command -v "$probe" >/dev/null 2>&1; then
    "$@" || true
  else
    "$@"
  fi
}
corepack enable
refresh pnpm corepack prepare pnpm@latest --activate
refresh yarn corepack prepare yarn@stable --activate
refresh tsc npm install -g typescript typescript-language-server @openai/codex

# --- Default login shell ------------------------------------------------------
TARGET_SHELL="{{.Param.shell}}"
case "$TARGET_SHELL" in
  zsh|fish|bash) chsh -s "/usr/bin/$TARGET_SHELL" "$LIMA_USER" || true ;;
  *) echo "unknown shell: $TARGET_SHELL" >&2; exit 1 ;;
esac
