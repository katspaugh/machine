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
  ripgrep fd-find bat tmux less file python3 direnv \
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

# --- CLI tools from GitHub releases -------------------------------------------
# Not packaged in Ubuntu 24.04 (fzf is, but predates the `fzf --zsh/--fish`
# integration flags the rc files rely on). Version-pinned; the guards make
# re-boots cheap and offline-safe. Bump the *_VERSION lines to upgrade.
FZF_VERSION=0.73.1
if ! /usr/local/bin/fzf --version 2>/dev/null | grep -q "^$FZF_VERSION"; then
  tmp=$(mktemp -d)
  curl -fsSL "https://github.com/junegunn/fzf/releases/download/v${FZF_VERSION}/fzf-${FZF_VERSION}-linux_${ARCH}.tar.gz" \
    | tar -xz -C "$tmp"
  install -m 0755 "$tmp/fzf" /usr/local/bin/fzf
  rm -rf "$tmp"
fi

# delta — the git pager set in the gitconfig that templates/base.yaml renders.
# The .deb assets use dpkg arch names, so no mapping needed.
DELTA_VERSION=0.19.2
if ! delta --version 2>/dev/null | grep -q "delta $DELTA_VERSION"; then
  tmp=$(mktemp -d)
  curl -fsSL -o "$tmp/delta.deb" \
    "https://github.com/dandavison/delta/releases/download/${DELTA_VERSION}/git-delta_${DELTA_VERSION}_${ARCH}.deb"
  apt-get install -y "$tmp/delta.deb"
  rm -rf "$tmp"
fi

# lazygit + helix release assets use x86_64/aarch64-style arch names.
case "$ARCH" in
  amd64) GH_ARCH=x86_64 ;;
  arm64) GH_ARCH=arm64 ;;
esac

LAZYGIT_VERSION=0.62.1
if ! lazygit --version 2>/dev/null | grep -q "version=$LAZYGIT_VERSION"; then
  tmp=$(mktemp -d)
  curl -fsSL "https://github.com/jesseduffield/lazygit/releases/download/v${LAZYGIT_VERSION}/lazygit_${LAZYGIT_VERSION}_linux_${GH_ARCH}.tar.gz" \
    | tar -xz -C "$tmp"
  install -m 0755 "$tmp/lazygit" /usr/local/bin/lazygit
  rm -rf "$tmp"
fi

# Helix is a multi-file install: hx looks for its runtime/ (grammars, themes)
# next to the binary, so the whole tree goes to /opt/helix with a symlink on
# PATH. (The .deb asset is amd64-only, hence the tarball.)
HELIX_VERSION=25.07.1
HX_ARCH=$GH_ARCH; [ "$ARCH" = arm64 ] && HX_ARCH=aarch64
if ! /opt/helix/hx --version 2>/dev/null | grep -q "helix $HELIX_VERSION"; then
  tmp=$(mktemp -d)
  curl -fsSL "https://github.com/helix-editor/helix/releases/download/${HELIX_VERSION}/helix-${HELIX_VERSION}-${HX_ARCH}-linux.tar.xz" \
    | tar -xJ -C "$tmp"
  rm -rf /opt/helix
  mv "$tmp/helix-${HELIX_VERSION}-${HX_ARCH}-linux" /opt/helix
  ln -sf /opt/helix/hx /usr/local/bin/hx
  rm -rf "$tmp"
fi

# --- Default login shell ------------------------------------------------------
TARGET_SHELL="{{.Param.shell}}"
case "$TARGET_SHELL" in
  zsh|fish|bash) chsh -s "/usr/bin/$TARGET_SHELL" "$LIMA_USER" || true ;;
  *) echo "unknown shell: $TARGET_SHELL" >&2; exit 1 ;;
esac
