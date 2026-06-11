#!/usr/bin/env bash
# Cut a new release of machine and bump the Homebrew tap in one shot.
#
# Usage: scripts/release.sh <version>
#   e.g. scripts/release.sh 0.1.1   (leading 'v' optional)
#
# What it does:
#   1. Preflight: clean tree, tag absent locally and on origin, gh authed,
#      lint + unit green, tap clone works (so credential/network problems
#      surface before anything is pushed).
#   2. Promotes the CHANGELOG Unreleased section to a versioned heading and
#      bumps the flake.nix version; commits both locally.
#   3. Tags vX.Y.Z and pushes the tag — the first remote write.
#   4. Downloads the tagged tarball from GitHub, computes its sha256.
#   5. Rewrites url + sha256 in Formula/machine.rb, commits, then pushes main
#      once with all release commits (so CI never sees flake.nix and the
#      formula disagreeing).
#   6. Mirrors the formula into katspaugh/homebrew-machine, commits, pushes.
#   7. Creates a GitHub Release with the promoted CHANGELOG notes.
#
# Failure handling: if anything fails after the tag push but before main is
# pushed, the tag is deleted (remote and local) so re-running this script just
# works — the local CHANGELOG/flake commits are kept and reused. If a failure
# happens after main is pushed (tap mirror or release creation), the tag stays
# put and the remaining manual steps are printed instead.

set -euo pipefail

[ $# -eq 1 ] || { echo "usage: $(basename "$0") <version>" >&2; exit 2; }
VERSION="${1#v}"
TAG="v$VERSION"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TAP_REMOTE="git@github.com:katspaugh/homebrew-machine.git"
TAP_DIR="${TMPDIR:-/tmp}/release-homebrew-machine.$$"
TAR_URL="https://github.com/katspaugh/machine/archive/refs/tags/$TAG.tar.gz"
NOTES_FILE="${TMPDIR:-/tmp}/machine-release-notes.$$"
cd "$REPO_DIR"

# Set by the steps below so cleanup knows how far the release got.
TAG_PUSHED=0
MAIN_PUSHED=0

cleanup() {
  status=$?
  rm -rf "${TAP_DIR:-}"
  if [ "$status" -ne 0 ] && [ "$TAG_PUSHED" -eq 1 ]; then
    if [ "$MAIN_PUSHED" -eq 1 ]; then
      # main already references the tag — keep it and finish by hand.
      echo >&2
      echo "release $TAG is partially published (tag and main are pushed)." >&2
      echo "finish whichever of these did not complete:" >&2
      echo "  - mirror Formula/machine.rb into $TAP_REMOTE and push" >&2
      echo "  - gh release create $TAG --title $TAG --notes-file $NOTES_FILE" >&2
      echo "release notes kept at $NOTES_FILE" >&2
      return
    fi
    echo >&2
    echo "==> failure after tag push — rolling back tag $TAG" >&2
    git push --delete origin "$TAG" \
      || echo "warning: could not delete remote tag $TAG; delete it manually before re-running" >&2
    git tag -d "$TAG" 2>/dev/null || true
    echo "    local release commits kept; re-run scripts/release.sh $VERSION to retry" >&2
  fi
  rm -f "${NOTES_FILE:-}"
}
trap cleanup EXIT

# Preflight
[ -z "$(git status --porcelain)" ] \
  || { echo "working tree dirty; commit or stash first" >&2; exit 1; }
git rev-parse --verify "$TAG" >/dev/null 2>&1 \
  && { echo "tag $TAG already exists locally (git tag -d $TAG to retry)" >&2; exit 1; }
command -v gh >/dev/null \
  || { echo "gh not found (brew install gh)" >&2; exit 1; }
command -v python3 >/dev/null \
  || { echo "python3 not found" >&2; exit 1; }
gh auth status >/dev/null 2>&1 \
  || { echo "gh not authenticated (gh auth login)" >&2; exit 1; }
git ls-remote --exit-code origin "refs/tags/$TAG" >/dev/null 2>&1 \
  && { echo "tag $TAG already exists on origin (stranded release? git push --delete origin $TAG to retry)" >&2; exit 1; }

# Preflight: lint + unit must be green before anything is tagged.
echo "==> preflight: lint + unit"
bash tests/lint.sh
bash tests/unit.sh

# Preflight: clone the tap now so a bad remote/credentials fail the release
# before any commit or push, not after the tag is already up.
echo "==> preflight: cloning tap $TAP_REMOTE"
git clone --depth 1 "$TAP_REMOTE" "$TAP_DIR"

# CHANGELOG: the Unreleased section becomes the release notes and is promoted
# to a versioned heading. If this version's heading already exists (a previous
# run promoted it and was rolled back), reuse its section as the notes.
if grep -q "^## \[$VERSION\]" CHANGELOG.md; then
  echo "==> CHANGELOG already has $TAG; reusing its notes"
  awk -v v="$VERSION" \
    'index($0, "## [" v "]") == 1 {f=1; next} /^## \[/{f=0} f' \
    CHANGELOG.md > "$NOTES_FILE"
else
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
fi
if ! grep -q '[^[:space:]]' "$NOTES_FILE"; then
  echo "CHANGELOG.md section for $VERSION is empty — write the release notes first" >&2
  exit 1
fi

# Bump flake.nix version — must land before the tag so the tagged commit
# builds with the right version (the flake's src is `self`).
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

# Tag + push. First remote write — from here cleanup() rolls the tag back if
# any later step fails before main is pushed.
echo "==> tagging $TAG"
git tag -a "$TAG" -m "$TAG"
TAG_PUSHED=1
git push origin "$TAG"

# Compute tarball sha256 — GitHub generates the tag tarball on demand, so
# retry a couple of times in case it is not ready immediately.
echo "==> fetching $TAR_URL to compute sha256"
SHA=""
for attempt in 1 2 3; do
  if SHA=$(curl -fsSL "$TAR_URL" | shasum -a 256 | awk '{print $1}') && [ -n "$SHA" ]; then
    break
  fi
  SHA=""
  echo "    tarball not ready (attempt $attempt/3), retrying in 5s"
  sleep 5
done
[ -n "$SHA" ] || { echo "failed to compute sha256" >&2; exit 1; }
echo "    sha256=$SHA"

# Bump this repo's reference formula; push main once with all release commits
# so CI's version-agreement check never sees a half-bumped state.
echo "==> updating $REPO_DIR/Formula/machine.rb"
sed -i.bak -E \
  -e "s|(archive/refs/tags/)v[0-9]+\\.[0-9]+\\.[0-9]+(\\.tar\\.gz)|\\1$TAG\\2|" \
  -e "s|(sha256[[:space:]]+\")[a-f0-9]{64}|\\1$SHA|" \
  Formula/machine.rb
rm -f Formula/machine.rb.bak
git add Formula/machine.rb
git commit -m "Pin Formula/machine.rb to $TAG SHA256"
git push origin HEAD
MAIN_PUSHED=1

# Mirror into the tap (cloned during preflight)
echo "==> updating tap $TAP_REMOTE"
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

# GitHub Release with notes from the promoted CHANGELOG section
echo "==> creating GitHub release $TAG"
gh release create "$TAG" --title "$TAG" --notes-file "$NOTES_FILE"

echo
echo "✓ released $TAG"
echo "  brew update && brew upgrade machine"
