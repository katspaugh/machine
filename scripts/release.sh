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
#   6. Creates a GitHub Release with notes from the CHANGELOG Unreleased section.

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
command -v python3 >/dev/null \
  || { echo "python3 not found" >&2; exit 1; }
gh auth status >/dev/null 2>&1 \
  || { echo "gh not authenticated (gh auth login)" >&2; exit 1; }

# Preflight: lint + unit must be green before anything is tagged.
echo "==> preflight: lint + unit"
bash tests/lint.sh
bash tests/unit.sh

# CHANGELOG: require a non-empty Unreleased section; it becomes the
# release notes and is promoted to a versioned heading below.
NOTES_FILE="${TMPDIR:-/tmp}/machine-release-notes.$$"
trap 'rm -f "${NOTES_FILE:-}"; rm -rf "${TAP_DIR:-}"' EXIT
awk '/^## \[Unreleased\]/{f=1; next} /^## \[/{f=0} f' CHANGELOG.md > "$NOTES_FILE"
if ! grep -q '[^[:space:]]' "$NOTES_FILE"; then
  echo "CHANGELOG.md has no entries under '## [Unreleased]' — write the release notes first" >&2
  exit 1
fi

# Promote Unreleased -> [$VERSION] — YYYY-MM-DD and refresh the compare links.
echo "==> promoting CHANGELOG Unreleased to $TAG"
python3 - "$VERSION" <<'EOF'
import datetime, pathlib, re, sys
version = sys.argv[1]
p = pathlib.Path("CHANGELOG.md")
text = p.read_text()
today = datetime.date.today().isoformat()
if "## [Unreleased]" not in text:
    sys.exit("CHANGELOG.md: '## [Unreleased]' heading not found")
text = text.replace(
    "## [Unreleased]",
    f"## [Unreleased]\n\n## [{version}] — {today}", 1)
# [Unreleased]: compare link now starts at the new tag; add the new tag's link.
text = re.sub(
    r"\[Unreleased\]: https://github\.com/katspaugh/machine/compare/v[0-9.]+\.\.\.HEAD",
    f"[Unreleased]: https://github.com/katspaugh/machine/compare/v{version}...HEAD",
    text)
old = re.search(r"\n\[([0-9.]+)\]: ", text)
if old and f"[{version}]: " not in text:
    text = text.replace(
        f"\n[{old.group(1)}]: ",
        f"\n[{version}]: https://github.com/katspaugh/machine/compare/v{old.group(1)}...v{version}\n[{old.group(1)}]: ",
        1)
p.write_text(text)
EOF
git add CHANGELOG.md
git commit -m "CHANGELOG: release $TAG"

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

# 6. GitHub Release with notes from the CHANGELOG Unreleased section
echo "==> creating GitHub release $TAG"
gh release create "$TAG" --title "$TAG" --notes-file "$NOTES_FILE"

echo
echo "✓ released $TAG"
echo "  brew update && brew upgrade machine"
