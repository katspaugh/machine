# Plan 3: GUI Packaging & Distribution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `machine.app` to users: configure the Tauri bundle for a universal macOS `.dmg`, build it in CI on every `v*` tag and attach it to the GitHub Release, and add a `Casks/machine-gui.rb` Homebrew cask (depending on the existing `machine` formula) so `brew install --cask machine-gui` drops the app in `/Applications`.

**Architecture:** A new macOS-only GitHub Actions job (alongside the existing Ubuntu lint/unit job) triggers on tag pushes, builds the universal (`x86_64` + `aarch64`) app via `tauri-action`, and uploads the `.dmg` to the tag's GitHub Release. The app is ad-hoc signed for v1 (Developer ID signing + notarization deferred until an Apple Developer account exists); Homebrew casks strip the quarantine flag on install, so an ad-hoc DMG is still launchable. The cask lives in the same tap repo as the formula and is bumped as part of the release runbook.

**Tech Stack:** Tauri 2.x bundler (`dmg` target), GitHub Actions (`macos-14` runner, `tauri-apps/tauri-action`), Homebrew Cask DSL, the existing `scripts/release.sh`.

---

## Prerequisites

- **Plans 2a + 2b must be merged** — there must be a buildable `gui/` app whose `pnpm tauri build` produces a `.app`. Verify locally on a Mac: `cd gui && pnpm tauri build` succeeds and emits a `.dmg` under `gui/src-tauri/target/release/bundle/dmg/` before wiring CI.
- **macOS for all verification.** DMG building, `brew install --cask`, and launching from `/Applications` are macOS-only. The CI job runs on a GitHub `macos-14` runner; local verification needs a Mac.
- **Tap repo access.** The cask is published to `katspaugh/homebrew-machine` (the same tap as the formula — see `docs/TAP.md`). You need push access to update it.
- Commits are signed; the signing agent is intermittently flaky — retry on `communication with agent failed`, never `--no-gpg-sign`.

## Decisions

- **Ad-hoc signing for v1.** `tauri.conf.json` `macOS.signingIdentity: "-"` (ad-hoc). No notarization. Rationale: no paid Apple Developer account yet. Homebrew casks run `xattr -dr com.apple.quarantine` on install, so a cask-installed ad-hoc app opens without the Gatekeeper "unidentified developer" block. (Users who download the DMG manually from the Release page WILL hit Gatekeeper — the Release notes should say "install via `brew install --cask machine-gui`".) Upgrade path to Developer ID + notarization is noted in Task 5.
- **Universal binary.** Build `--target universal-apple-darwin` so one DMG runs on both Intel and Apple Silicon. Slightly larger, but one artifact and one cask sha256.
- **Version source.** The app version = the git tag (`vX.Y.Z` → `X.Y.Z`). `tauri.conf.json`'s `version` is set from the tag at build time (or kept in sync manually via `release.sh`). The cask `version` matches.
- **Cask depends on the formula.** `depends_on formula: "katspaugh/machine/machine"` guarantees the CLI is present (the GUI shells out to it).

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `gui/src-tauri/tauri.conf.json` | Modify | DMG bundle target, macOS category/min-version, ad-hoc signing. |
| `.github/workflows/release.yml` | Create | macOS tag-triggered job: build universal DMG, upload to the Release. |
| `Casks/machine-gui.rb` | Create | Reference cask (mirrors `Formula/machine.rb`'s "reference copy" pattern). |
| `docs/TAP.md` | Modify | Extend the release runbook with the cask bump steps. |
| `scripts/release.sh` | Modify | After the DMG is built+uploaded, compute its sha256 and bump the cask. |
| `README.md` | Modify | Add the `brew install --cask machine-gui` install line. |

There is no TDD here — packaging correctness is verified by: a successful local `tauri build`, a green CI run on a throwaway tag, `brew audit`/`brew style` on the cask, and a real `brew install --cask` + launch. Each task's verification step states the exact check.

---

## Task 1: Configure the Tauri bundle for a macOS DMG

**Files:** Modify `gui/src-tauri/tauri.conf.json`.

- [ ] **Step 1.1: Set the bundle config**

In `gui/src-tauri/tauri.conf.json`, under `bundle`, ensure:

```json
{
  "bundle": {
    "active": true,
    "targets": ["app", "dmg"],
    "icon": ["icons/32x32.png", "icons/128x128.png", "icons/128x128@2x.png", "icons/icon.icns", "icons/icon.ico"],
    "macOS": {
      "minimumSystemVersion": "12.0",
      "signingIdentity": "-"
    },
    "category": "DeveloperTool"
  }
}
```

(`signingIdentity: "-"` is ad-hoc. The `icons/` list is whatever `create-tauri-app` generated — keep its real filenames. `tauri icon path/to/icon.png` can regenerate the set from a single source PNG if you want a custom icon; the starter icons are fine for v1.)

- [ ] **Step 1.2: Confirm the product name + identifier**

Verify (from plan 2a Task 1): `productName` is `machine`, `identifier` is `dev.runmachine.gui`, window `title` is `machine`. The DMG and `.app` are named from `productName`.

- [ ] **Step 1.3: Local build verification (on a Mac)**

```bash
cd gui
rustup target add x86_64-apple-darwin aarch64-apple-darwin
pnpm tauri build --target universal-apple-darwin
```

Expected: a `.dmg` appears under `gui/src-tauri/target/universal-apple-darwin/release/bundle/dmg/machine_<version>_universal.dmg`. Open it, drag to Applications, launch — the window opens and the project list loads (the CLI must be installed/on PATH, or run from a dev checkout with `MACHINE_BIN` exported in your shell).

> If `tauri build` fails on the universal target with a linker error, confirm both rust targets are installed (`rustup target list --installed`). On a single-arch dev machine you can sanity-check with a plain `pnpm tauri build` first (native arch only), then add the universal target.

- [ ] **Step 1.4: Commit**

```bash
cd /home/ivan.guest/code/machine
git add gui/src-tauri/tauri.conf.json
git commit -m "$(cat <<'EOF'
Configure macOS DMG bundle for the gui

Adds the dmg target, DeveloperTool category, minimum macOS 12, and
ad-hoc signing (Developer ID + notarization deferred until there's an
Apple Developer account).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Release workflow — build the universal DMG on tag

**Files:** Create `.github/workflows/release.yml`.

A separate workflow from `ci.yml` (which stays Ubuntu/Python). Triggers on `v*` tags, builds the app on macOS, and uploads the DMG to the GitHub Release for that tag.

- [ ] **Step 2.1: Write `.github/workflows/release.yml`**

```yaml
name: Release GUI

# Builds the macOS app on tag pushes and attaches the universal DMG to the
# GitHub Release. The CLI release (tap formula bump) is handled separately by
# scripts/release.sh — this only produces the GUI artifact.
on:
  push:
    tags: ["v*"]

permissions:
  contents: write   # needed to create/update the Release and upload assets

jobs:
  build-macos:
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Set up pnpm
        uses: pnpm/action-setup@v4
        with:
          version: "9"

      - name: Set up Rust (with universal targets)
        uses: dtolnay/rust-toolchain@stable
        with:
          targets: x86_64-apple-darwin,aarch64-apple-darwin

      - name: Install frontend deps
        working-directory: gui
        run: pnpm install --frozen-lockfile

      - name: Build + upload DMG to the Release
        uses: tauri-apps/tauri-action@v0
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          projectPath: gui
          args: --target universal-apple-darwin
          tagName: ${{ github.ref_name }}
          releaseName: ${{ github.ref_name }}
          releaseDraft: false
          prerelease: false
```

> **Notes / verification points:**
> - `tauri-action@v0` builds the app and attaches the bundle to a Release named after the tag, creating the Release if it doesn't exist. If `scripts/release.sh` already created the Release for the CLI, `tauri-action` uploads into the existing one (matched by `tagName`).
> - `secrets.GITHUB_TOKEN` is auto-provided; `contents: write` permission is required for the upload.
> - Pin action versions to the latest available majors when implementing; the `@v0`/`@v4` tags above are the current majors but confirm.
> - This job does NOT run on PRs or `main` pushes — only tags — so it won't slow the normal CI loop.

- [ ] **Step 2.2: Lint the workflow locally (optional but cheap)**

```bash
# If actionlint is available:
actionlint .github/workflows/release.yml
```

Expected: no errors. (If `actionlint` isn't installed, a YAML syntax check via `python3 -c 'import yaml,sys; yaml.safe_load(open(sys.argv[1]))' .github/workflows/release.yml` at least catches malformed YAML.)

- [ ] **Step 2.3: Commit**

```bash
cd /home/ivan.guest/code/machine
git add .github/workflows/release.yml
git commit -m "$(cat <<'EOF'
Add release workflow building the universal macOS DMG on tag

macos-14 job triggered on v* tags; tauri-action builds the universal
app and uploads the DMG to the tag's GitHub Release. Independent of
the Ubuntu CI job and the CLI tap-formula bump.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2.4: End-to-end verification on a throwaway tag** (do this once, after Tasks 1–2 are merged)

```bash
git tag v0.0.0-gui-test && git push origin v0.0.0-gui-test
# Watch the run:
gh run watch
# Confirm the DMG attached to the release:
gh release view v0.0.0-gui-test
# Clean up:
gh release delete v0.0.0-gui-test --yes && git push --delete origin v0.0.0-gui-test && git tag -d v0.0.0-gui-test
```

Expected: the workflow goes green and `machine_0.0.0-gui-test_universal.dmg` (or similar) is attached to the release. If the build fails, fix it here before relying on it for a real release. **This step is the real acceptance test for Tasks 1–2.**

---

## Task 3: The Homebrew cask

**Files:** Create `Casks/machine-gui.rb`.

Mirrors the `Formula/machine.rb` "reference copy in the main repo" pattern (per `docs/TAP.md`): the source of truth lives here and is copied into the tap on release. The cask installs the `.app` from the released DMG and depends on the `machine` formula.

- [ ] **Step 3.1: Write `Casks/machine-gui.rb`**

```ruby
# This cask lives in the main repo as a reference. The published tap is
# katspaugh/homebrew-machine — copy this file into its Casks/ dir and bump
# version/sha256 on each release. See docs/TAP.md.
cask "machine-gui" do
  version "0.1.2"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"

  url "https://github.com/katspaugh/machine/releases/download/v#{version}/machine_#{version}_universal.dmg"
  name "machine"
  desc "Desktop GUI for machine — manage per-project Lima VMs"
  homepage "https://runmachine.dev"

  # The GUI shells out to the `machine` CLI for every action.
  depends_on formula: "katspaugh/machine/machine"
  depends_on macos: ">= :monterey"

  app "machine.app"

  zap trash: [
    "~/Library/Application Support/dev.runmachine.gui",
    "~/Library/Caches/dev.runmachine.gui",
    "~/Library/Preferences/dev.runmachine.gui.plist",
    "~/Library/Saved Application State/dev.runmachine.gui.savedState",
  ]
end
```

> **Verify the DMG asset name** against what `tauri-action` actually uploaded in Task 2.4 (it may be `machine_0.1.2_universal.dmg`, or include an `aarch64`/`x64` suffix if the universal flag wasn't honored). The `url` must match exactly. If the artifact name differs, either adjust the `url` template or set Tauri's bundle naming. The `app "machine.app"` stanza name must match `productName`.

- [ ] **Step 3.2: Style + audit the cask**

After the first real release populates a valid `sha256` (Task 4), run against the tap copy:

```bash
brew style --fix Casks/machine-gui.rb || brew style Casks/machine-gui.rb
# (audit requires the cask to be in a tap; run in the tap repo after copying)
brew audit --cask --new katspaugh/homebrew-machine/machine-gui
```

Expected: `brew style` clean; `brew audit` passes (a placeholder sha256 will fail audit — that's expected until Task 4 fills it in).

- [ ] **Step 3.3: Commit**

```bash
cd /home/ivan.guest/code/machine
git add Casks/machine-gui.rb
git commit -m "$(cat <<'EOF'
Add machine-gui Homebrew cask (reference copy)

Installs machine.app from the released universal DMG and depends on
the machine formula so the CLI is always present. sha256 is a
placeholder until the first GUI release fills it in.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Extend the release runbook + `scripts/release.sh`

**Files:** Modify `docs/TAP.md`, `scripts/release.sh`.

The cask sha256 depends on the DMG, which CI builds *after* the tag is pushed. So the release order is: tag → CI builds + uploads DMG → compute DMG sha256 → bump cask → push tap. Capture this; optionally automate the cask bump in `release.sh`.

- [ ] **Step 4.1: Read the current `scripts/release.sh`** to understand its structure (it tags, computes the tarball sha256, bumps the formula, pushes both repos, creates the Release). Identify where to add the cask step.

- [ ] **Step 4.2: Add a cask-bump section to `docs/TAP.md`**

Append a section after the existing "Cutting a release" content:

```markdown
## Releasing the GUI cask

The GUI DMG is built by `.github/workflows/release.yml` when the `v*` tag is
pushed (same tag as the CLI release). Because the cask's `sha256` is the DMG's
digest, the cask is bumped *after* CI finishes building it:

1. Push the release tag as usual (`scripts/release.sh X.Y.Z` or by hand).
2. Wait for the **Release GUI** workflow to finish and attach
   `machine_X.Y.Z_universal.dmg` to the GitHub Release:
   ```sh
   gh run watch
   gh release view vX.Y.Z   # confirm the DMG asset is present
   ```
3. Compute the DMG's sha256:
   ```sh
   curl -fsSL https://github.com/katspaugh/machine/releases/download/vX.Y.Z/machine_X.Y.Z_universal.dmg \
     | shasum -a 256
   ```
4. In both `Casks/machine-gui.rb` (this repo, reference) and the tap's
   `homebrew-machine/Casks/machine-gui.rb`, update `version` and `sha256`.
5. Commit + push the tap. Users get the GUI via:
   ```sh
   brew install --cask katspaugh/machine/machine-gui
   ```

The cask lags the formula by the CI build time (a few minutes) — that's
expected. The CLI is installable immediately; the GUI once the DMG is built.
```

- [ ] **Step 4.3: Optionally automate the cask bump in `scripts/release.sh`**

Add a function (guarded so it's skippable if CI hasn't finished) that, after the Release exists and the DMG is attached, computes the digest and rewrites the cask. Pattern (adapt to the script's existing style — read it first):

```sh
bump_cask() {
  local version="$1"
  local dmg_url="https://github.com/katspaugh/machine/releases/download/v${version}/machine_${version}_universal.dmg"
  echo "waiting for GUI DMG at ${dmg_url} ..."
  # Poll up to ~10 min for CI to upload the asset.
  local sha=""
  for _ in $(seq 1 60); do
    if sha="$(curl -fsSL "$dmg_url" 2>/dev/null | shasum -a 256 | awk '{print $1}')" \
       && [ -n "$sha" ]; then
      break
    fi
    sleep 10
  done
  [ -n "$sha" ] || { echo "DMG not available yet; bump the cask manually (see docs/TAP.md)"; return 1; }

  # Reference copy in this repo:
  sed -i.bak -E "s/^  version \".*\"/  version \"${version}\"/" Casks/machine-gui.rb
  sed -i.bak -E "s/^  sha256 \".*\"/  sha256 \"${sha}\"/" Casks/machine-gui.rb
  rm -f Casks/machine-gui.rb.bak
  echo "bumped Casks/machine-gui.rb → ${version} / ${sha}"
  echo "now copy it into the tap and push (see docs/TAP.md), or extend this"
  echo "function to do the tap commit like the formula bump does."
}
```

Wire a call to `bump_cask "$VERSION"` after the existing formula bump, but make it non-fatal (the GUI build may legitimately still be running). Match the script's error-handling conventions.

> **Decision:** keeping `bump_cask` as "compute + bump the local reference, print next steps" (rather than fully pushing the tap) is the conservative choice — it avoids `release.sh` blocking on a long CI build and avoids pushing a cask with a stale/empty sha. Full tap automation can come later once the GUI release cadence is proven.

- [ ] **Step 4.4: Verify the script still parses**

```bash
bash -n scripts/release.sh
bash tests/lint.sh   # shellcheck the script if lint covers scripts/
```

Expected: no syntax errors; lint clean.

- [ ] **Step 4.5: Commit**

```bash
cd /home/ivan.guest/code/machine
git add docs/TAP.md scripts/release.sh
git commit -m "$(cat <<'EOF'
Document + script the GUI cask bump in the release runbook

The cask sha256 is the DMG digest, which CI builds after the tag is
pushed, so the cask is bumped post-build. Adds a TAP.md section and a
non-fatal bump_cask helper to release.sh that polls for the DMG and
rewrites the reference cask.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: README install line + Developer-ID note

**Files:** Modify `README.md`.

- [ ] **Step 5.1: Add the GUI install option**

In `README.md`, under the existing `## Install` section (after the `brew install katspaugh/machine/machine` block), add:

```markdown
### Desktop app (optional)

A macOS GUI is available as a cask (it installs the CLI as a dependency):

```sh
brew install --cask katspaugh/machine/machine-gui
```

This drops `machine.app` in `/Applications` — a Docker-Desktop-style dashboard
for your projects (status, up/down/update/rebuild/destroy, live provisioning
logs). The CLI remains the primary interface; the GUI is a convenience surface
over it.
```

- [ ] **Step 5.2: Add a one-line Gatekeeper note** (since the app is ad-hoc signed)

Add a short note under the install line:

```markdown
> The app is ad-hoc signed (no paid Apple Developer account yet). Installing via
> the cask is the supported path — Homebrew clears the quarantine flag so it
> opens normally. Downloading the DMG manually from the Releases page will trip
> Gatekeeper (right-click → Open, or `xattr -dr com.apple.quarantine /Applications/machine.app`).
```

- [ ] **Step 5.3: Commit**

```bash
cd /home/ivan.guest/code/machine
git add README.md
git commit -m "$(cat <<'EOF'
Document the GUI cask install in the README

Adds the brew install --cask line and a Gatekeeper note (ad-hoc
signed; cask install clears quarantine).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-review checklist (for the implementer)

- [ ] `cd gui && pnpm tauri build --target universal-apple-darwin` produces a `.dmg` locally (on a Mac).
- [ ] A throwaway `v0.0.0-gui-test` tag triggers `release.yml`, the job goes green, and the universal DMG is attached to the Release (Task 2.4). Tag/release cleaned up afterward.
- [ ] `Casks/machine-gui.rb` `url` exactly matches the uploaded DMG asset name; `app` stanza matches `productName`.
- [ ] After a real release: `brew install --cask katspaugh/machine/machine-gui` installs the app to `/Applications`, it launches without a Gatekeeper block, and `brew uninstall --cask machine-gui` + `--zap` removes it cleanly.
- [ ] `brew style Casks/machine-gui.rb` is clean; `brew audit --cask --new` passes against the tap copy (with a real sha256).
- [ ] The cask `depends_on formula: "katspaugh/machine/machine"` — installing the cask on a clean machine also installs the CLI.
- [ ] `docs/TAP.md` describes the tag → CI build → cask bump ordering; `scripts/release.sh` parses (`bash -n`) and `bump_cask` is non-fatal.
- [ ] README shows the cask install line + the Gatekeeper note.
- [ ] Commits signed (retry on agent failure; never `--no-gpg-sign`).

## Roadmap complete

With plans 1, 2a, 2b, and 3 implemented, the GUI is shipped end-to-end:
- Plan 1: CLI `--json` surface + `config add-project` (**done**).
- Plan 2a: Tauri scaffold + Rust backend + wired slice.
- Plan 2b: full Svelte component UI.
- Plan 3: universal DMG CI + Homebrew cask.

**Deferred beyond v1** (tracked, not in these plans): Developer ID signing + notarization (needs an Apple account), Linux/Windows builds, the in-app `projects.toml` editor for existing projects, a menu-bar status widget, and a `machine profiles --json` command to replace the cask/`BUNDLED_PROFILES` hardcoding. The plan-1 carry-forward notes in the design spec also list contract gaps (no `Provisioning` status from the CLI, `doctor --json` dropping WARN-level findings) that a future CLI pass could close.
```
