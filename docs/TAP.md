# Homebrew tap — release runbook

`machine` is distributed through the **`katspaugh/machine`** Homebrew tap. Users install with:

```sh
brew install katspaugh/machine/machine
```

The tap is a separate repo from this one. `Formula/machine.rb` here is the source of truth — copy it into the tap on every release.

## One-time setup

Create the tap repo on GitHub. Homebrew expects the name to be `homebrew-<tap>`:

```sh
gh repo create katspaugh/homebrew-machine --public \
  --description "Homebrew tap for machine"
git clone git@github.com:katspaugh/homebrew-machine.git
mkdir -p homebrew-machine/Formula
cp Formula/machine.rb homebrew-machine/Formula/
cd homebrew-machine && git add . && git commit -m "Initial formula" && git push
```

## Cutting a release

The one-shot way:

```sh
scripts/release.sh 0.1.1
```

It tags, computes sha256, bumps both formulas, pushes both repos, and creates a GitHub Release with auto-generated notes. Requires a clean working tree and `gh auth status` healthy.

### Or by hand

1. Tag this repo and push the tag:
   ```sh
   git tag v0.X.0 && git push origin v0.X.0
   ```
2. Compute the tarball SHA256:
   ```sh
   curl -fsSL https://github.com/katspaugh/machine/archive/refs/tags/v0.X.0.tar.gz \
     | shasum -a 256
   ```
3. In `homebrew-machine/Formula/machine.rb`, update:
   - `url` → the new tag's tarball URL
   - `sha256` → the digest from step 2
4. Commit + push the tap. Users get the new version on `brew upgrade`.

## Why a tap (and not the curl|sh in the landing page)

A tap is the most-trusted install path on macOS:

- **Auditable**: the formula lives in a public repo; users can read it before installing.
- **Pinned**: each release ties to an immutable tagged tarball + SHA256. Drift between what was tested and what gets installed is impossible without a tap-repo commit.
- **Reversible**: `brew uninstall` removes the binary and the formula's tracked files cleanly.
- **No root**: the formula installs under `$HOMEBREW_PREFIX`, never `/usr`.

The `curl https://runmachine.dev/install | sh` path is kept as a fallback for users who prefer it, but the landing page should put `brew install` first.

## Verifying provenance (optional, recommended)

For extra legitimacy, sign release tarballs with [GitHub artifact attestations](https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations) in CI. Users can then run:

```sh
gh attestation verify --owner katspaugh \
  $(brew --cache)/downloads/*machine*.tar.gz
```

This proves the tarball was built by the `katspaugh/machine` GitHub Actions runner from a specific commit. Worth setting up before announcing the tap publicly.

