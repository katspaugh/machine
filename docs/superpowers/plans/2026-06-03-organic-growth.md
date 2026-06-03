# Organic Growth (Trust-First Maturity) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `machine` adoption-ready for organic visitors: a macOS CI job that boots a real Lima VM, changelog-driven releases, contributor surface, one "Sandboxing Claude Code" content page, and an ecosystem-listings pass.

**Architecture:** No product code changes. Five independent workstreams: a new `smoke.yml` GitHub Actions workflow (macOS runner, real `machine up` + the existing in-VM smoke suite), CHANGELOG.md wired into the existing `scripts/release.sh`, `.github/` contributor files, a static HTML page under `docs/` (GitHub Pages → runmachine.dev), and external listing PRs.

**Tech Stack:** GitHub Actions (macOS arm64 runner, Lima/vz), bash, Keep-a-Changelog, static HTML reusing the site's existing `tokens.css`/`components.css`/`manual.css`.

**Spec:** `docs/superpowers/specs/2026-06-03-organic-growth-design.md`

---

## Context for the engineer (read first)

- `bin/machine` is a Python CLI driving `limactl`. Key env knobs (read in `bin/machine` ~lines 33–46): `PROJECTS_FILE` (path to projects.toml), `GIT_NAME`, `GIT_EMAIL`, `GIT_SIGNING_KEY` (a **literal pubkey string** — resolution priority #1, no 1Password/file lookup needed).
- The in-VM smoke suite is `tests/smoke-*.sh`, each targeting the VM named by `$MACHINE_NAME` via `limactl shell`. `tests/run-all.sh <name>` runs lint + all smokes. **The suite assumes all profiles are provisioned**: `smoke-cypress.sh` needs the `cypress` profile; `smoke-clis.sh` checks `supabase`/`flyctl` (profile `supabase-fly`) and `batcat`/`fzf`/`delta`/`lazygit`/`hx` (profile `modern`).
- `smoke-git-sign.sh` makes a commit inside the VM and asserts a *Good* SSH signature against the rendered `allowed_signers`. This works with a throwaway key: the VM only needs (a) the pubkey passed at create time via `GIT_SIGNING_KEY`, and (b) an SSH agent holding the matching private key, forwarded by Lima. **No GitHub account/registration is involved** — no smoke needs gating in CI.
- `templates/base.yaml:14` hardcodes `vmType: vz`. GitHub's arm64 macOS runners support nested virtualization only on newer images; if `vz` fails on the chosen runner, the fallback is QEMU (`brew install qemu` + sed the template) — see Task 1 Step 6.
- `scripts/release.sh` already automates the whole release (flake bump → tag → SHA256 → both formula bumps → tap push → `gh release create --generate-notes`). Task 3 only adds: lint+unit preflight, CHANGELOG promotion, and `--notes-file` instead of `--generate-notes`.
- `tests/lint.sh` shellchecks `bin provision tests` — **not** `scripts/`. Task 3 fixes that.
- The website is GitHub Pages from `docs/`: `docs/index.html` (landing), `docs/docs/index.html` (manual). Shared styles: `docs/styles/{tokens,components,manual}.css`. A page at `docs/sandboxing-claude-code/index.html` serves at `https://runmachine.dev/sandboxing-claude-code/`.
- Tasks 1–4 are independent of each other. Task 5 needs Task 4's repo metadata only conceptually; Task 6 (listings) is strictly last and **outward-facing — every action in it needs explicit user sign-off at execution time**.

---

### Task 1: macOS CI smoke workflow

**Files:**
- Create: `.github/workflows/smoke.yml`
- Modify: `README.md` (badges, top of file)

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/smoke.yml`:

```yaml
name: Smoke

# Boots a real Lima VM on a macOS runner, provisions every profile, and runs
# the full in-VM smoke suite (tests/run-all.sh). Heavy (~30-60 min), so it
# runs on pushes to main and nightly — not on PRs. `workflow_dispatch` is for
# manual runs while iterating.
#
# No untrusted inputs are interpolated into `run:` steps; all values are
# workflow-literal or come from checked-in files.
on:
  workflow_dispatch:
  push:
    branches: [main]
  schedule:
    - cron: "17 3 * * *" # nightly 03:17 UTC

permissions:
  contents: read

concurrency:
  group: smoke-${{ github.ref }}
  cancel-in-progress: true

jobs:
  smoke-macos:
    runs-on: macos-26
    timeout-minutes: 90
    steps:
      - uses: actions/checkout@v4

      - name: Install Lima
        run: |
          brew install lima
          limactl --version
          python3 --version

      - name: Throwaway SSH identity (agent forwarding + git signing)
        run: |
          mkdir -p ~/.ssh
          ssh-keygen -t ed25519 -N "" -C "ci@runmachine.dev" -f ~/.ssh/ci_ed25519
          eval "$(ssh-agent -s)"
          ssh-add ~/.ssh/ci_ed25519
          {
            echo "SSH_AUTH_SOCK=$SSH_AUTH_SOCK"
            echo "SSH_AGENT_PID=$SSH_AGENT_PID"
            echo "GIT_NAME=machine CI"
            echo "GIT_EMAIL=ci@runmachine.dev"
            echo "GIT_SIGNING_KEY=$(cat ~/.ssh/ci_ed25519.pub)"
            echo "PROJECTS_FILE=$GITHUB_WORKSPACE/ci-projects.toml"
          } >> "$GITHUB_ENV"

      - name: Write CI projects.toml (all profiles, no repos)
        run: |
          cat > ci-projects.toml <<'EOF'
          [ci]
          profiles = ["cypress", "playwright", "supabase-fly", "modern"]
          repos = []
          EOF

      - name: machine up
        run: ./bin/machine up ci

      - name: Smoke suite
        run: bash tests/run-all.sh ci

      - name: Provision log on failure
        if: failure()
        run: limactl shell ci -- sudo tail -200 /var/log/cloud-init-output.log || true

      - name: Destroy VM
        if: always()
        run: ./bin/machine destroy -y ci || true
```

- [ ] **Step 2: Validate the YAML parses**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/smoke.yml').read()); print('ok')"`
(Install pyyaml first if needed: `pip3 install pyyaml`.)
Expected: `ok`

- [ ] **Step 3: Commit and push to a branch**

```bash
git checkout -b ci-smoke-macos
git add .github/workflows/smoke.yml
git commit -m "Add macOS smoke workflow: boot a real Lima VM in CI"
git push -u origin ci-smoke-macos
```

- [ ] **Step 4: Dispatch a verification run**

```bash
gh workflow run smoke.yml --ref ci-smoke-macos
sleep 10
gh run list --workflow=smoke.yml --limit 1
gh run watch "$(gh run list --workflow=smoke.yml --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status
```

Expected: the run completes green in roughly 30–60 minutes. While it runs, check the `machine up` step logs to confirm the VM boots under `vz`.

- [ ] **Step 5 (only if Step 4 fails on virtualization): QEMU fallback**

If `limactl start` fails with a virtualization/`vz` error (nested virt unsupported on the runner image), add this step to `smoke.yml` immediately **before** the `machine up` step, then commit/push/re-dispatch:

```yaml
      - name: Fall back to QEMU (runner lacks nested virtualization)
        run: |
          brew install qemu
          sed -i '' 's/^vmType: vz$/vmType: qemu/' templates/base.yaml
          grep -n 'vmType' templates/base.yaml
```

Also try the alternative first: change `runs-on: macos-26` to `runs-on: macos-15` (and vice versa) before resorting to QEMU — image support for nested virt varies. QEMU is markedly slower; if the run then exceeds the 90-minute timeout, raise `timeout-minutes` to 120 and trim the CI profile list to `["modern"]` plus replace `bash tests/run-all.sh ci` with an explicit list that skips the heaviest smoke:

```yaml
      - name: Smoke suite
        run: |
          export MACHINE_NAME=ci
          for t in tests/smoke-boot.sh tests/smoke-docker.sh tests/smoke-node.sh \
                   tests/smoke-git-sign.sh tests/smoke-tmux.sh tests/smoke-agents.sh \
                   tests/smoke-claude-plugins.sh tests/smoke-port-forward.sh; do
            echo "=== $t ==="; bash "$t"
          done
```

(That subset drops `smoke-cypress.sh` and the profile-tool checks in `smoke-clis.sh`; keep `run-all.sh` if the full run fits.)

- [ ] **Step 6: Add badges to the README**

In `README.md`, insert directly under the `# machine — one isolated Lima VM per project` heading (line 1):

```markdown
[![CI](https://github.com/katspaugh/machine/actions/workflows/ci.yml/badge.svg)](https://github.com/katspaugh/machine/actions/workflows/ci.yml)
[![Smoke](https://github.com/katspaugh/machine/actions/workflows/smoke.yml/badge.svg)](https://github.com/katspaugh/machine/actions/workflows/smoke.yml)
```

- [ ] **Step 7: Commit, merge to main, verify the main run**

```bash
git add README.md
git commit -m "Add CI + smoke badges to README"
git push
gh pr create --title "macOS CI smoke: boot a real Lima VM nightly and on main" \
  --body "Adds .github/workflows/smoke.yml (workflow_dispatch + push-to-main + nightly cron) and README badges. Verified green via workflow_dispatch run."
```

Merge after review. After merge, confirm the push-triggered run on `main` goes green: `gh run list --workflow=smoke.yml --limit 1`.

---

### Task 2: CHANGELOG.md

**Files:**
- Create: `CHANGELOG.md`

- [ ] **Step 1: Verify what belongs in each section**

```bash
git log v0.2.1..origin/main --oneline   # → Unreleased
git log v0.2.0..v0.2.1 --oneline        # → 0.2.1
git log v0.1.6..v0.2.0 --oneline        # → 0.2.0
```

Cross-check the drafted content below against the output; adjust if commits have landed since this plan was written.

- [ ] **Step 2: Create CHANGELOG.md**

```markdown
# Changelog

All notable changes to `machine` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org/). Release notes are generated from this file
by `scripts/release.sh`.

## [Unreleased]

### Added
- `modern` opt-in profile: bat, delta, fzf, lazygit, helix (rg stays in base).
- macOS CI smoke workflow: boots a real Lima VM on every push to main and
  nightly, runs the full in-VM smoke suite.

### Fixed
- `machine down` is idempotent when the VM is already stopped.

## [0.2.1] — 2026-06-03

### Added
- `machine claude` runs inside a tmux session in the VM — detach with
  `ctrl-b d`, re-run to reattach.
- Nix flake: `nix profile install github:katspaugh/machine`.
- Zero-config default VM: bare `machine up` launches a base VM named
  `default`; unknown names offer an ad-hoc base VM.

### Changed
- SSH agent is auto-detected (1Password socket if present, else
  `SSH_AUTH_SOCK`); `MACHINE_USE_1PASSWORD` is gone.

### Fixed
- Deps-install warnings, guest workdir resolution, and secrets reachability.

## [0.2.0] — 2026-06-02

### Added
- `playwright` profile: OS deps for Playwright's browsers.
- Supabase CLI installed from its `.deb` release artifact.

[Unreleased]: https://github.com/katspaugh/machine/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/katspaugh/machine/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/katspaugh/machine/compare/v0.1.6...v0.2.0
```

(History before 0.2.0 is left to the compare links — backfilling six 0.1.x patch tags adds noise, not trust.)

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "Add CHANGELOG.md (Keep a Changelog format)"
```

---

### Task 3: Wire CHANGELOG into scripts/release.sh + lint scripts/

**Files:**
- Modify: `scripts/release.sh`
- Modify: `tests/lint.sh` (add `scripts` to the find list)
- Modify: `docs/TAP.md` (release steps mention CHANGELOG)

- [ ] **Step 1: Extend lint coverage to scripts/**

In `tests/lint.sh`, change:

```bash
done < <(find bin provision tests -type f -name '*.sh')
```

to:

```bash
done < <(find bin provision tests scripts -type f -name '*.sh')
```

- [ ] **Step 2: Run lint to get a baseline**

Run: `bash tests/lint.sh`
Expected: either `lint OK`, or shellcheck findings in `scripts/release.sh`. Fix any findings minimally (quote variables, etc.) before proceeding, and re-run until `lint OK`.

- [ ] **Step 3: Add preflight + changelog extraction to release.sh**

In `scripts/release.sh`, after the existing preflight block (the `gh auth status` check) and **before** the `# 1. Bump flake.nix version` section, insert:

```bash
# Preflight: lint + unit must be green before anything is tagged.
echo "==> preflight: lint + unit"
bash tests/lint.sh
bash tests/unit.sh

# CHANGELOG: require a non-empty Unreleased section; it becomes the
# release notes and is promoted to a versioned heading below.
NOTES_FILE="${TMPDIR:-/tmp}/machine-release-notes.$$"
trap 'rm -f "$NOTES_FILE"' EXIT
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
assert "## [Unreleased]" in text
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
```

Note the existing `trap 'rm -rf "$TAP_DIR"' EXIT` set later in the script (step 5, tap mirror) — **change that line** to also clean the notes file, since a later `trap` replaces the earlier one:

```bash
trap 'rm -rf "$TAP_DIR" "$NOTES_FILE"' EXIT
```

- [ ] **Step 4: Use the notes file for the GitHub Release**

In `scripts/release.sh` section `# 6. GitHub Release`, change:

```bash
gh release create "$TAG" --title "$TAG" --generate-notes
```

to:

```bash
gh release create "$TAG" --title "$TAG" --notes-file "$NOTES_FILE"
```

- [ ] **Step 5: Test the extraction + promotion logic on a fixture**

The release script itself can't be run end-to-end without cutting a real release, so test the new logic in isolation:

```bash
tmp=$(mktemp -d) && cp CHANGELOG.md "$tmp/" && cd "$tmp"

# extraction
awk '/^## \[Unreleased\]/{f=1; next} /^## \[/{f=0} f' CHANGELOG.md > notes.txt
grep -q '[^[:space:]]' notes.txt && echo "extraction OK"
cat notes.txt   # eyeball: only the Unreleased bullets, no other versions

# promotion (same python as in release.sh, version 9.9.9)
python3 - 9.9.9 <<'EOF'
import datetime, pathlib, re, sys
version = sys.argv[1]
p = pathlib.Path("CHANGELOG.md")
text = p.read_text()
today = datetime.date.today().isoformat()
assert "## [Unreleased]" in text
text = text.replace(
    "## [Unreleased]",
    f"## [Unreleased]\n\n## [{version}] — {today}", 1)
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
grep -n '## \[9.9.9\]' CHANGELOG.md && grep -n 'v9.9.9...HEAD' CHANGELOG.md && echo "promotion OK"
cd - && rm -rf "$tmp"
```

Expected: `extraction OK`, then `promotion OK`, with the eyeballed notes containing exactly the Unreleased bullets. (An empty-Unreleased CHANGELOG should make the `grep -q` fail — verify by emptying the section in the fixture and re-running the extraction check; expected: no `extraction OK`.)

- [ ] **Step 6: Lint and syntax-check the edited script**

Run: `bash tests/lint.sh && bash -n scripts/release.sh && echo OK`
Expected: `lint OK` then `OK`

- [ ] **Step 7: Update TAP.md**

In `docs/TAP.md`, replace the "Cutting a release" intro:

```markdown
## Cutting a release

1. Make sure `CHANGELOG.md` has the release notes under `## [Unreleased]`
   (the script refuses to release an empty section).
2. Run the one-shot script:

```sh
scripts/release.sh 0.1.1
```

It runs lint + unit, promotes the Unreleased changelog section to the new
version, tags, computes sha256, bumps both formulas, pushes both repos, and
creates a GitHub Release whose notes are that changelog section. Requires a
clean working tree and `gh auth status` healthy.
```

(Keep the existing "Or by hand" section as-is.)

- [ ] **Step 8: Commit**

```bash
git add scripts/release.sh tests/lint.sh docs/TAP.md
git commit -m "release.sh: lint+unit preflight, changelog-driven release notes"
```

---

### Task 4: Contributor surface + repo metadata

**Files:**
- Create: `CONTRIBUTING.md`
- Create: `.github/ISSUE_TEMPLATE/bug_report.md`
- Create: `.github/ISSUE_TEMPLATE/feature_request.md`
- Create: `.github/pull_request_template.md`
- Modify: `README.md` (link CONTRIBUTING)

- [ ] **Step 1: Create CONTRIBUTING.md**

```markdown
# Contributing to machine

## Dev setup

Run from a clone — no Homebrew install needed:

```sh
git clone git@github.com:katspaugh/machine.git
cd machine
bin/machine doctor          # verifies lima, SSH agent, git identity
```

In dev mode `projects.toml` lives at the repo root
(`cp projects.toml.example projects.toml`) and generated state goes to
`.build/`.

## Tests

| Command | Needs | What |
|---|---|---|
| `bash tests/lint.sh` | shellcheck (optional) | Shellcheck + Python parse check |
| `bash tests/unit.sh` | nothing | Host-side unit tests for `bin/machine` |
| `bash tests/run-all.sh <project>` | a provisioned VM | Full in-VM smoke suite |

CI runs lint + unit on every PR. The VM smoke suite runs on pushes to main
and nightly (`.github/workflows/smoke.yml`) — it boots a real Lima VM, so
it's not on the PR path. Please run lint + unit locally before pushing.

## Writing a profile (the most useful contribution)

A profile is a pair: `templates/<name>.yaml` + `provision/<name>.sh`.

1. Copy an existing pair, e.g. `templates/playwright.yaml` +
   `provision/playwright.sh`, to your profile's name.
2. The template's `provision:` entry points at your script via the
   `provision/` symlink (Lima v2 forbids `../` in `file:` locators).
3. Scripts run as root by default (`mode: system`); use `mode: user` for
   per-user steps. **They re-run on every boot — keep them idempotent**
   (guard installs with `command -v` checks, use `apt-get install -y`,
   never append blindly to dotfiles).
4. Test it: add the profile to a project in `projects.toml`, then
   `bin/machine destroy <p> && bin/machine up <p>`, and check
   `limactl shell <p> sudo tail -100 /var/log/cloud-init-output.log`.
5. Add a smoke test `tests/smoke-<name>.sh` mirroring an existing one
   (target the VM via `$MACHINE_NAME`, `limactl shell`), and a row in the
   README's Provisioning section.

## Pull requests

- One logical change per PR.
- `bash tests/lint.sh && bash tests/unit.sh` green.
- Update `CHANGELOG.md` under `## [Unreleased]` if the change is user-visible.
```

- [ ] **Step 2: Create the bug report template**

`.github/ISSUE_TEMPLATE/bug_report.md`:

```markdown
---
name: Bug report
about: Something broke
labels: bug
---

**What happened**

**What you expected**

**Environment**

- `machine doctor` output:
- `limactl --version`:
- macOS version:
- Install method (brew / nix / clone):

**Provision log (if the VM failed to come up)**

Output of `limactl shell <vm> sudo tail -100 /var/log/cloud-init-output.log`:
```

- [ ] **Step 3: Create the feature/profile request template**

`.github/ISSUE_TEMPLATE/feature_request.md`:

```markdown
---
name: Feature or profile request
about: A new capability or tool profile
labels: enhancement
---

**What should machine do**

**Why / what workflow it unblocks**

**If it's a profile: which tools, and do they need apt repos, a GUI/Xvfb,
or per-repo installs?**
```

- [ ] **Step 4: Create the PR template**

`.github/pull_request_template.md`:

```markdown
**What changed**

**How it was verified**

- [ ] `bash tests/lint.sh` + `bash tests/unit.sh` green
- [ ] VM smokes run, if the change touches templates/provision (`bash tests/run-all.sh <p>`)
- [ ] `CHANGELOG.md` updated under `## [Unreleased]` (if user-visible)
```

- [ ] **Step 5: Link from the README**

In `README.md`, add at the end of the file:

```markdown
## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — the profile-authoring walkthrough
lives there. Bug reports should include `machine doctor` output.
```

- [ ] **Step 6: Commit**

```bash
git add CONTRIBUTING.md .github/ISSUE_TEMPLATE .github/pull_request_template.md README.md
git commit -m "Add CONTRIBUTING, issue/PR templates"
```

- [ ] **Step 7: Set repo metadata (OUTWARD-FACING — confirm with the user first)**

```bash
gh repo edit katspaugh/machine \
  --description "One isolated Lima VM per GitHub project — sandboxed Claude Code/Codex, Docker, Node, signed git" \
  --homepage "https://runmachine.dev" \
  --add-topic lima --add-topic claude-code --add-topic sandbox \
  --add-topic ai-agents --add-topic developer-tools --add-topic vm --add-topic macos
```

Verify: `gh repo view katspaugh/machine --json repositoryTopics,description,homepageUrl`

---

### Task 5: "Sandboxing Claude Code" content page

**Files:**
- Create: `docs/sandboxing-claude-code/index.html`
- Modify: `docs/index.html` (footer link), `docs/docs/index.html` (nav link)
- Modify: `README.md` (short section linking the page)

- [ ] **Step 1: Create the page**

`docs/sandboxing-claude-code/index.html`. It reuses the manual page's head/nav/footer pattern verbatim (compare `docs/docs/index.html`) with `../`-relative asset paths. Content below is the complete page; the prose is final copy, not a sketch:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Sandboxing Claude Code — machine</title>
  <meta name="description" content="Run Claude Code and other AI coding agents with full autonomy inside an isolated VM — no host filesystem, no cross-project bleed. An honest comparison of the sandboxing options." />

  <link rel="canonical" href="https://runmachine.dev/sandboxing-claude-code/" />
  <meta property="og:url" content="https://runmachine.dev/sandboxing-claude-code/" />
  <meta property="og:type" content="article" />
  <meta property="og:title" content="Sandboxing Claude Code — machine" />
  <meta property="og:description" content="Run AI coding agents with full autonomy inside an isolated VM — no host filesystem, no cross-project bleed." />
  <meta property="og:image" content="https://runmachine.dev/assets/banner.svg" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:image" content="https://runmachine.dev/assets/banner.svg" />

  <link rel="icon" type="image/svg+xml" href="/favicon.svg" />

  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />

  <link rel="stylesheet" href="../styles/tokens.css" />
  <link rel="stylesheet" href="../styles/components.css" />
  <link rel="stylesheet" href="../styles/manual.css" />
</head>
<body>

<header class="nav is-stuck" id="nav">
  <div class="container nav-inner">
    <a href="../" class="nav-brand" aria-label="machine home">
      <span class="mark" aria-hidden="true"><span></span><span></span><span></span><span></span></span>
      <span class="wordmark">machine</span>
    </a>
    <nav class="nav-links">
      <a href="../docs/">The machinist's manual</a>
      <a class="nav-cta" href="https://github.com/katspaugh/machine" rel="noreferrer">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"/></svg>
        <span>GitHub</span>
      </a>
    </nav>
  </div>
</header>

<main class="container manual-wrap">

  <div class="manual-head">
    <p class="eyebrow">// guide</p>
    <h1>Sandboxing Claude Code (and every other coding agent).</h1>
    <p class="lede">
      An agent that can run shell commands is only as safe as the machine you give it.
      This guide covers what an unsandboxed agent can actually touch, how
      <code>machine</code> isolates it in a per-project VM, and an honest comparison
      with the other options.
    </p>
  </div>

  <div class="manual-layout">

    <aside class="manual-toc" aria-label="Table of contents">
      <div class="toc-label">// contents</div>
      <ol>
        <li><a href="#problem">The problem</a></li>
        <li><a href="#isolation">The isolation model</a></li>
        <li><a href="#quickstart">Three commands</a></li>
        <li><a href="#comparison">Honest comparison</a></li>
        <li><a href="#faq">FAQ</a></li>
      </ol>
    </aside>

    <div class="manual-body">

      <section id="problem">
        <h2><span class="num">01</span>The problem</h2>
        <p>
          Coding agents are most useful when they can act: run the tests, install the
          dependency, fix the config, retry. Claude Code's permission prompts exist
          because every one of those actions runs on <em>your</em> machine — and the
          moment you get tired of approving each command and reach for
          <code>--dangerously-skip-permissions</code>, the agent inherits everything
          your user account can do:
        </p>
        <ul>
          <li>Read your SSH private keys, browser sessions, cloud credentials, and every other project's source and <code>.env</code> files.</li>
          <li>Execute whatever a compromised or hallucinated <code>npm install</code> postinstall script wants — supply-chain attacks don't ask permission either.</li>
          <li>Mutate global state: dotfiles, keychains, crontabs, other repos.</li>
        </ul>
        <p>
          The fix isn't more prompts — it's giving the agent a machine where
          <em>yes to everything</em> is an acceptable answer.
        </p>
      </section>

      <section id="isolation">
        <h2><span class="num">02</span>The isolation model</h2>
        <p>
          <code>machine</code> gives each project its own <a href="https://lima-vm.io/">Lima</a> VM
          with Docker, Node, the agent CLIs (Claude Code, Codex), GitHub CLI, and signed git
          already provisioned. The boundary is a VM, not a container — a different kernel,
          not a namespace.
        </p>
        <ul>
          <li><strong>No host filesystem is mounted.</strong> There is no path from the VM to your home directory. The smoke suite asserts this on every CI run.</li>
          <li><strong>One VM per project.</strong> A compromised dependency in one project cannot read another project's code or secrets — they're separate machines.</li>
          <li><strong>Keys stay on the host.</strong> Git auth and commit signing use a forwarded SSH agent: the VM can request signatures while it runs, but can never read the private key.</li>
          <li><strong>Secrets are tmpfs-only.</strong> <code>machine secrets</code> renders 1Password Environments into VM tmpfs — never to disk, gone on reboot. A fully compromised VM sees only the secrets a repo explicitly rendered, not your vault.</li>
        </ul>
        <p>
          Inside that boundary, the agent runs with <code>defaultMode: auto</code> —
          full autonomy, because the blast radius is one disposable VM.
          <code>machine claude</code> even keeps it running in tmux after you close your laptop.
          The full model is in the <a href="../docs/#threat-model">threat model</a>.
        </p>
      </section>

      <section id="quickstart">
        <h2><span class="num">03</span>Three commands</h2>
        <pre><div class="head"><span class="dot"></span><span class="dot"></span><span class="dot"></span><span>shell</span></div><code><span class="prompt">$ </span>brew install katspaugh/machine/machine
<span class="prompt">$ </span>machine up                 <span class="cmt"># zero-config sandbox VM, ~/code inside</span>
<span class="prompt">$ </span>machine claude             <span class="cmt"># Claude Code in a tmux session, in the VM</span></code></pre>
        <p>
          Add repos and tool profiles per project in <code>projects.toml</code> when you
          want more than a scratch VM — see the <a href="../docs/#setup">manual</a>.
          Nix users: <code>nix profile install github:katspaugh/machine</code>.
        </p>
      </section>

      <section id="comparison">
        <h2><span class="num">04</span>Honest comparison</h2>
        <p>Where the alternatives genuinely win, the table says so.</p>
        <table>
          <thead>
            <tr><th></th><th>Bare host + permission prompts</th><th>Docker / devcontainers</th><th>machine (Lima VM)</th></tr>
          </thead>
          <tbody>
            <tr>
              <th>Isolation boundary</th>
              <td>None — agent shares your account</td>
              <td>Kernel namespaces; host kernel shared, escapes are rare but real; project dirs are usually bind-mounted in</td>
              <td>Hardware-virtualized VM, separate kernel, no host mounts</td>
            </tr>
            <tr>
              <th>Agent autonomy you can grant</th>
              <td>Low — every skipped prompt is host exposure</td>
              <td>High inside the container, but the mounted workspace is still your working copy</td>
              <td>Full (<code>auto</code> mode) — worst case is a throwaway VM</td>
            </tr>
            <tr>
              <th>Cross-project isolation</th>
              <td>None</td>
              <td>Only if you never share volumes or images between projects</td>
              <td>Default — one VM per project</td>
            </tr>
            <tr>
              <th>Docker workloads inside</th>
              <td>Yes (host Docker)</td>
              <td>Docker-in-Docker or socket mounting — the latter pierces the sandbox</td>
              <td>Yes — real dockerd inside the VM</td>
            </tr>
            <tr>
              <th>Cross-platform &amp; team-shareable config</th>
              <td>—</td>
              <td><strong>Wins:</strong> devcontainer.json is portable, IDE-native, works on Linux/Windows/Codespaces</td>
              <td>macOS hosts only; config is a TOML you share, but VMs are local</td>
            </tr>
            <tr>
              <th>Weight</th>
              <td>None</td>
              <td><strong>Wins:</strong> containers are lighter and faster to start</td>
              <td>~GBs of disk per VM, seconds-to-minutes to boot (cached base disk)</td>
            </tr>
          </tbody>
        </table>
        <p class="muted">
          If you need Linux/Windows hosts or team-distributed environments, use
          devcontainers. If you want the strongest practical boundary for autonomous
          agents on a Mac, use a VM.
        </p>
      </section>

      <section id="faq">
        <h2><span class="num">05</span>FAQ</h2>
        <h3>Does the agent get internet access?</h3>
        <p>Yes — the VM has normal outbound networking (it needs npm, apt, GitHub). The boundary protects your host and other projects, not the network.</p>
        <h3>How do I see the app the agent is building?</h3>
        <p>Lima auto-forwards listening guest ports to <code>127.0.0.1</code> on the host. Your browser just works.</p>
        <h3>What if the agent wrecks the VM?</h3>
        <p><code>machine destroy &amp;&amp; machine up</code> — a fresh, fully provisioned VM in about a minute from the cached base disk.</p>
        <h3>Is my code safe from the agent?</h3>
        <p>The code in the VM is the agent's working copy — push protection comes from review and the forwarded-agent model (it can't approve its own GitHub credentials beyond what the agent socket allows while you're connected).</p>
      </section>

    </div>
  </div>
</main>

<footer>
  <div class="container">
    <div class="foot-grid">
      <div>
        <div class="nav-brand" style="margin-bottom: var(--s-4)">
          <span class="mark" aria-hidden="true"><span></span><span></span><span></span><span></span></span>
          <span class="wordmark">machine</span>
        </div>
        <p class="foot-tag">Built by people who got tired of cleaning up after their machines.</p>
      </div>
      <div class="foot-col">
        <h5>// docs</h5>
        <ul>
          <li><a href="../docs/">The machinist's manual</a></li>
          <li><a href="../docs/#quickstart">Quickstart</a></li>
          <li><a href="../docs/#threat-model">Threat model</a></li>
        </ul>
      </div>
      <div class="foot-col">
        <h5>// project</h5>
        <ul>
          <li><a href="https://github.com/katspaugh/machine">GitHub</a></li>
          <li><a href="https://github.com/katspaugh/machine/blob/main/CHANGELOG.md">Changelog</a></li>
          <li><a href="https://github.com/katspaugh/machine/blob/main/CONTRIBUTING.md">Contributing</a></li>
        </ul>
      </div>
    </div>
  </div>
</footer>

</body>
</html>
```

Before committing, open `docs/docs/index.html` and diff your nav/footer against it — if the live markup has drifted from this plan, follow the live markup. Check `docs/styles/manual.css` for a `table` style; if tables aren't styled, add a minimal block to the **end** of `manual.css`:

```css
/* comparison tables (guide pages) */
.manual-body table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
.manual-body th, .manual-body td { border: 1px solid var(--border, #333); padding: var(--s-2, 8px) var(--s-3, 12px); text-align: left; vertical-align: top; }
.manual-body thead th { background: var(--bg-2, rgba(255,255,255,0.04)); }
```

(Use the token names actually present in `tokens.css` — inspect it and substitute.)

- [ ] **Step 2: Render-check locally**

```bash
python3 -m http.server 8080 --directory docs &
open http://localhost:8080/sandboxing-claude-code/
```

Eyeball: nav sticks, fonts load, code blocks render with the dot-header chrome, the table is readable, footer matches the manual page. Kill the server after.

- [ ] **Step 3: Link the page from the site and README**

In `docs/index.html` footer's `// docs` column (around line 512), add:

```html
          <li><a href="/sandboxing-claude-code/">Sandboxing Claude Code</a></li>
```

In `docs/docs/index.html` nav (`<nav class="nav-links">`), add before the GitHub CTA:

```html
      <a href="../sandboxing-claude-code/">Sandboxing guide</a>
```

In `README.md`, after the intro paragraphs (before `## Install`), add:

```markdown
## Why

AI coding agents are most useful with full autonomy — and full autonomy on
your host means access to your keys, your other projects, and everything
`npm install` drags in. `machine` gives each project a disposable VM where
"yes to everything" is a safe answer: no host filesystem mount, keys stay on
the host behind a forwarded agent, secrets live in tmpfs.
Read the guide: [Sandboxing Claude Code](https://runmachine.dev/sandboxing-claude-code/).
```

- [ ] **Step 4: Commit**

```bash
git add docs/sandboxing-claude-code/index.html docs/index.html docs/docs/index.html docs/styles/manual.css README.md
git commit -m "Add 'Sandboxing Claude Code' guide page"
```

- [ ] **Step 5: Verify the deployed page**

After the commit reaches `main` and Pages deploys (a few minutes):

```bash
curl -fsS https://runmachine.dev/sandboxing-claude-code/ | grep -o '<title>[^<]*</title>'
```

Expected: `<title>Sandboxing Claude Code — machine</title>`

---

### Task 6: Listings pass (ALL OUTWARD-FACING — get user sign-off per item)

No repo files change in this task except where noted. Every item publishes content externally; present each to the user before executing.

- [ ] **Step 1: awesome-claude-code entry**

Find the canonical list (`gh search repos awesome-claude-code --sort stars`), read its CONTRIBUTING for entry format, then fork + PR adding (adapt to the list's format):

> [machine](https://github.com/katspaugh/machine) — One isolated Lima VM per project: run Claude Code with full autonomy in a sandbox with no host filesystem mount; Docker, Node, signed git, and tool profiles provisioned.

Show the user the exact PR diff before `gh pr create`.

- [ ] **Step 2: Lima ecosystem listing**

Check where Lima lists downstream projects (https://lima-vm.io — look for an "ecosystem", "adopters", or community page; the source is the `lima-vm/lima-vm.github.io` or `lima-vm/lima` repo `website/` directory). If such a page exists, PR a one-line entry mirroring the format of existing entries (e.g. colima). If none exists, skip — do not invent a venue.

- [ ] **Step 3: Other agent-tooling lists**

Search for actively-maintained lists (`gh search repos "awesome ai coding agents" --sort stars`, `gh search repos "awesome codex"`). Apply the same entry text as Step 1 to at most 2–3 lists with recent commit activity. Skip stale lists (no commits in 6 months) — a merged PR there helps nobody.

- [ ] **Step 4 (optional, defer by default): nixpkgs submission**

Larger effort (package review process, maintainer commitment). Recommend deferring until the smoke workflow has a few weeks of green nightly history — note it in a GitHub issue instead:

```bash
gh issue create --repo katspaugh/machine \
  --title "Submit machine to nixpkgs" \
  --body "The flake exists; package it in nixpkgs once the nightly smoke has a green track record. Needs: pkgs/by-name entry, maintainer entry, ofborg-clean build."
```

---

## Execution order

Tasks 1–4 are independent (1 is the longest pole — start its verification run early, it's mostly waiting). Task 5 any time. Task 6 strictly after 1–5 are merged and the deployed page is verified.
