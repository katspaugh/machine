#!/bin/bash
# Modern CLI tools: bat, delta, fzf, lazygit, helix. The base zshrc
# already carries guarded integrations (cat->bat, fzf keybindings) that light up
# when these are installed. Idempotent; runs on every boot.
# {{.User}}/{{.Home}} are Lima guest-template variables.
set -eu -o pipefail
export DEBIAN_FRONTEND=noninteractive

ARCH=$(dpkg --print-architecture)
LIMA_USER="{{.User}}"
USER_HOME="{{.Home}}"

# bat is packaged (as `batcat` — name clash with bacula; the rc files alias it).
# Non-fatal apt refresh, same reasoning as base.sh: offline re-boots of an
# already-provisioned VM must not fail the boot probe.
if ! command -v batcat >/dev/null 2>&1; then
  apt-get update -qq || true
  apt-get install -y --no-install-recommends bat
fi

# --- The rest from GitHub releases -------------------------------------------
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

# delta — wired up as git's pager below. The .deb assets use dpkg arch names,
# so no mapping needed.
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

# --- delta as git's pager -----------------------------------------------------
# base.yaml rewrites ~/.gitconfig (without delta) on every boot; this script
# runs after file placement on every boot too, so re-adding here keeps the
# pager config stable across re-boots without base knowing about delta.
git_user() { runuser -u "$LIMA_USER" -- env HOME="$USER_HOME" git "$@"; }
git_user config --global core.pager delta
git_user config --global interactive.diffFilter "delta --color-only"
git_user config --global delta.navigate true
