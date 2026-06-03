#!/usr/bin/env bash
# Cut a new release of machine and bump the Homebrew tap in one shot.
#
# Usage: scripts/release.sh <version>
#   e.g. scripts/release.sh 0.1.1   (leading 'v' optional)
#
# What it does:
#   1. Bumps version in flake.nix and commits (the tag must carry it — the
#      flake builds from its own source tree).
#   2. Tags vX.Y.Z in this repo and pushes the tag.
#   3. Downloads the tagged tarball from GitHub, computes its sha256.
#   4. Rewrites url + sha256 in this repo's Formula/machine.rb, commits, pushes main.
#   5. Clones katspaugh/homebrew-machine, mirrors the formula, commits, pushes.
#   6. Creates a GitHub Release with auto-generated notes.

set -euo pipefail

[ $# -eq 1 ] || { echo "usage: $(basename "$0") <version>" >&2; exit 2; }
VERSION="${1#v}"
TAG="v$VERSION"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TAP_REMOTE="git@github.com:katspaugh/homebrew-machine.git"
TAP_DIR="${TMPDIR:-/tmp}/release-homebrew-machine.$$"
TAR_URL="https://github.com/katspaugh/machine/archive/refs/tags/$TAG.tar.gz"
cd "$REPO_DIR"

# Preflight
[ -z "$(git status --porcelain)" ] \
  || { echo "working tree dirty; commit or stash first" >&2; exit 1; }
git rev-parse --verify "$TAG" >/dev/null 2>&1 \
  && { echo "tag $TAG already exists locally" >&2; exit 1; }
command -v gh >/dev/null \
  || { echo "gh not found (brew install gh)" >&2; exit 1; }
gh auth status >/dev/null 2>&1 \
  || { echo "gh not authenticated (gh auth login)" >&2; exit 1; }

# 1. Bump flake.nix version — must land before the tag so the tagged
#    commit builds with the right version (the flake's src is `self`).
if grep -q "version = \"$VERSION\";" flake.nix; then
  echo "==> flake.nix already at $VERSION"
else
  echo "==> updating flake.nix version to $VERSION"
  sed -i.bak -E \
    "s|^([[:space:]]*version = \")[0-9]+\\.[0-9]+\\.[0-9]+(\";)|\\1$VERSION\\2|" \
    flake.nix
  rm -f flake.nix.bak
  git add flake.nix
  git commit -m "Bump flake version to $TAG"
fi

# 2. Tag + push
echo "==> tagging $TAG"
git tag -a "$TAG" -m "$TAG"
git push origin "$TAG"

# 3. Compute tarball sha256
echo "==> fetching $TAR_URL to compute sha256"
SHA=$(curl -fsSL "$TAR_URL" | shasum -a 256 | awk '{print $1}')
[ -n "$SHA" ] || { echo "failed to compute sha256" >&2; exit 1; }
echo "    sha256=$SHA"

# 4. Bump this repo's reference formula
echo "==> updating $REPO_DIR/Formula/machine.rb"
sed -i.bak -E \
  -e "s|(archive/refs/tags/)v[0-9]+\\.[0-9]+\\.[0-9]+(\\.tar\\.gz)|\\1$TAG\\2|" \
  -e "s|(sha256[[:space:]]+\")[a-f0-9]{64}|\\1$SHA|" \
  Formula/machine.rb
rm -f Formula/machine.rb.bak
git add Formula/machine.rb
git commit -m "Pin Formula/machine.rb to $TAG SHA256"
git push origin HEAD

# 5. Mirror into the tap
echo "==> updating tap $TAP_REMOTE"
trap 'rm -rf "$TAP_DIR"' EXIT
git clone --depth 1 "$TAP_REMOTE" "$TAP_DIR"
cp Formula/machine.rb "$TAP_DIR/Formula/machine.rb"
(
  cd "$TAP_DIR"
  if git diff --quiet; then
    echo "    tap already up to date, skipping commit"
  else
    git add Formula/machine.rb
    git commit -m "machine $TAG"
    git push origin HEAD
  fi
)

# 6. GitHub Release with auto notes
echo "==> creating GitHub release $TAG"
gh release create "$TAG" --title "$TAG" --generate-notes

echo
echo "✓ released $TAG"
echo "  brew update && brew upgrade machine"
