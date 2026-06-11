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
# integration flags the rc files rely on). Version-pinned with per-arch sha256
# of the release assets; the guards make re-boots cheap and offline-safe.
# Bump the *_VERSION/*_SHA256 pairs together to upgrade.

# fetch <url> <sha256> <dest> — download a release asset and verify its hash.
fetch() {
  curl -fsSL -o "$3" "$1"
  echo "$2  $3" | sha256sum -c -
}

FZF_VERSION=0.73.1
case "$ARCH" in
  amd64) FZF_SHA256=f3252c2c366bc1700d3c85781ec8c9695998927ac127870eb049ceea2d540f8a ;;
  arm64) FZF_SHA256=a408b0b6c08d486307b8f1554f967b8b50ee1b3ea8b4035e3161bab31fdfc28d ;;
esac
if ! /usr/local/bin/fzf --version 2>/dev/null | grep -q "^$FZF_VERSION"; then
  tmp=$(mktemp -d)
  fetch "https://github.com/junegunn/fzf/releases/download/v${FZF_VERSION}/fzf-${FZF_VERSION}-linux_${ARCH}.tar.gz" \
    "$FZF_SHA256" "$tmp/fzf.tar.gz"
  tar -xz -C "$tmp" -f "$tmp/fzf.tar.gz"
  install -m 0755 "$tmp/fzf" /usr/local/bin/fzf
  rm -rf "$tmp"
fi

# delta — wired up as git's pager below. The .deb assets use dpkg arch names,
# so no mapping needed.
DELTA_VERSION=0.19.2
case "$ARCH" in
  amd64) DELTA_SHA256=ea4f0222950ee750a3d38dd80d03bce4cee07a3f63928fc47548383bcaf23093 ;;
  arm64) DELTA_SHA256=0edc36cf514f1bd84becac3e94ee8ae9f8818c6a1f99f7b2ee67b362afa253d3 ;;
esac
if ! delta --version 2>/dev/null | grep -q "delta $DELTA_VERSION"; then
  tmp=$(mktemp -d)
  fetch "https://github.com/dandavison/delta/releases/download/${DELTA_VERSION}/git-delta_${DELTA_VERSION}_${ARCH}.deb" \
    "$DELTA_SHA256" "$tmp/delta.deb"
  apt-get install -y "$tmp/delta.deb"
  rm -rf "$tmp"
fi

# lazygit + helix release assets use x86_64/aarch64-style arch names.
case "$ARCH" in
  amd64) GH_ARCH=x86_64 ;;
  arm64) GH_ARCH=arm64 ;;
esac

LAZYGIT_VERSION=0.62.1
case "$ARCH" in
  amd64) LAZYGIT_SHA256=99d78cce8883b24150c2f4ba151f6a0443644f63f63794f18d6643e99f75be09 ;;
  arm64) LAZYGIT_SHA256=22a19e4790323dfe0363a876d1f76738ee9722a3086ef27c9e4503c3c1d962ac ;;
esac
if ! lazygit --version 2>/dev/null | grep -q "version=$LAZYGIT_VERSION"; then
  tmp=$(mktemp -d)
  fetch "https://github.com/jesseduffield/lazygit/releases/download/v${LAZYGIT_VERSION}/lazygit_${LAZYGIT_VERSION}_linux_${GH_ARCH}.tar.gz" \
    "$LAZYGIT_SHA256" "$tmp/lazygit.tar.gz"
  tar -xz -C "$tmp" -f "$tmp/lazygit.tar.gz"
  install -m 0755 "$tmp/lazygit" /usr/local/bin/lazygit
  rm -rf "$tmp"
fi

# Helix is a multi-file install: hx looks for its runtime/ (grammars, themes)
# next to the binary, so the whole tree goes to /opt/helix with a symlink on
# PATH. (The .deb asset is amd64-only, hence the tarball.)
HELIX_VERSION=25.07.1
HX_ARCH=$GH_ARCH; [ "$ARCH" = arm64 ] && HX_ARCH=aarch64
case "$ARCH" in
  amd64) HELIX_SHA256=3f08e63ecd388fff657ad39722f88bb03dcf326f1f2da2700d99e1dc40ab2e8b ;;
  arm64) HELIX_SHA256=ce23fa8d395e633e3e54c052012f11965d91d8d5c2bfa659685f50430b4f8175 ;;
esac
if ! /opt/helix/hx --version 2>/dev/null | grep -q "helix $HELIX_VERSION"; then
  tmp=$(mktemp -d)
  fetch "https://github.com/helix-editor/helix/releases/download/${HELIX_VERSION}/helix-${HELIX_VERSION}-${HX_ARCH}-linux.tar.xz" \
    "$HELIX_SHA256" "$tmp/helix.tar.xz"
  tar -xJ -C "$tmp" -f "$tmp/helix.tar.xz"
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
