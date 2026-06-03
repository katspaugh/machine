# Organic growth: trust-first maturity + one content page

**Date:** 2026-06-03
**Status:** Approved

## Goal

Grow adoption of `machine` among AI-agent power users (devs running Claude
Code/Codex who want agent autonomy without risking their host) under an
**organic-only** posture — no launch posts. Strategy: close the trust &
maturity gaps first so every organic visitor sees a maintained project, plant
one high-value content page, then do a listings pass.

## Current state (gaps)

- CI runs lint + unit + YAML validation on Ubuntu only — the actual product
  path (`machine up` → Lima boot → provision → smoke) is never CI-tested.
- Releases are the manual TAP.md runbook with three hand-edited version pins
  (`Formula/machine.rb` here, the tap repo, `flake.nix`). No CHANGELOG, no
  GitHub Releases.
- No CONTRIBUTING.md, issue templates, or PR template. Repo topics unset.
- runmachine.dev is a single landing page — nothing to rank for the searches
  the target audience makes.
- Not listed in any ecosystem directory (awesome-claude-code, Lima ecosystem,
  nixpkgs).

## Design

### 1. CI smoke job (Linux + KVM)

*(Amended 2026-06-03 after empirical verification: GitHub's Apple-silicon
macOS runners do not support nested virtualization — Lima's vz backend dies
instantly at "Starting VZ". User-approved decision: run the smoke on
`ubuntu-latest`, which exposes `/dev/kvm`, booting the same Ubuntu guest via
qemu/KVM with a CI-only `vmType` sed. The vz path is exercised by developers
on real Macs.)*

New `smoke-linux-kvm` job in `.github/workflows/smoke.yml`:

- Runs on `ubuntu-latest`: enable /dev/kvm (udev rule), install qemu + a
  pinned Lima release tarball, write a minimal `projects.toml` (one project,
  **no repos** — avoids needing SSH keys in CI), `machine up ci`, run the
  in-VM smoke suite, then `machine destroy -y ci`.
- The git-signing smoke runs for real in CI: a throwaway ed25519 key in an
  ssh-agent plus `GIT_SIGNING_KEY=<literal pubkey>` is enough — signing
  verifies against the rendered `allowed_signers`, no GitHub account
  involved. No smoke needs gating.
- **Triggers:** push to `main` + nightly cron. Not on PRs (10–20 min VM boot
  would slow contributor feedback; a PR label opt-in can come later).
- **Risk:** nested-virt support on arm64 macOS runners is image-dependent.
  First implementation step is a throwaway workflow run to verify `vz` works
  on the pinned image; fall back to QEMU/TCG (slow but functional — Lima's
  own CI approach) if not.
- Add the CI badge to the README.

### 2. Release automation

*(Amended 2026-06-03: `scripts/release.sh` already automates tagging, SHA256,
both formula bumps, the tap push, and the GitHub Release. The original
tag-driven `release.yml` design was based on the false premise that releases
were fully manual. Decision: enhance the existing local script — no PAT
secrets, no Actions pushing to main.)*

- **CHANGELOG.md** in Keep-a-Changelog format, hand-maintained under an
  `## Unreleased` heading as features land. No release-drafter machinery.
- **Enhance `scripts/release.sh`:**
  1. Preflight additionally runs `tests/lint.sh` + `tests/unit.sh` and
     requires a non-empty `## Unreleased` section in CHANGELOG.md.
  2. Promotes `Unreleased` → `## vX.Y.Z — YYYY-MM-DD` (committed alongside
     the flake version bump, so the tag carries it).
  3. Creates the GitHub Release with that changelog section as the notes
     body (`--notes-file`) instead of `--generate-notes`.
- **TAP.md** updated: cutting a release = update CHANGELOG, run
  `scripts/release.sh <version>`.

### 3. Contributor & repo-maturity surface

- **CONTRIBUTING.md** — dev-mode setup, how to run lint/unit/VM smokes, and a
  "writing a profile" walkthrough (template + provision script pair).
  Profiles are the natural contribution surface.
- **Issue templates** — bug report (asks for `machine doctor` output, Lima
  version, macOS version, `cloud-init-output.log` tail) and feature/profile
  request. Minimal PR template (what changed, how verified).
- **Repo metadata** — description, website, topics: `lima`, `claude-code`,
  `sandbox`, `ai-agents`, `developer-tools`, `vm`, `macos`.

### 4. Content page: "Sandboxing Claude Code"

One static guide page on runmachine.dev, matching the existing site style (no
site generator):

- Problem (agents with shell access; what `--dangerously-skip-permissions`
  exposes) → isolation model (per-project VM, no host mounts, narrow
  SSH-agent + tmpfs-secrets channels, distilled from the README threat model)
  → 3-command quickstart → **honest** comparison table (machine vs
  devcontainers vs bare host vs Docker sandboxes, naming where the others
  win).
- Placed under `docs/` wherever GitHub Pages routing wants it; linked from
  the landing-page nav and a short new README section.
- SEO basics only: title/description/OpenGraph, semantic headings.

### 5. Listings pass (last, ~1 day)

After 1–4 land: PR to awesome-claude-code (and similar agent-tooling lists),
PR to Lima's ecosystem/adopters page, and an optional nixpkgs submission
(flake already exists; defer until the nightly smoke has a green track
record). *(Amended: dropped the "Homebrew analytics opt-in" item — install
analytics only exist for homebrew-core, not third-party taps.)*

## Order of work

1 (CI smoke) → 2 (release automation) → 3 (contributor surface) → 4 (content
page) → 5 (listings). Sections 3 and 4 can proceed in parallel with 1–2 if
desired; 5 is strictly last.

## Non-goals

- No launch posts (HN/Reddit/X) — organic-only by explicit choice.
- No site generator / docs framework for one page.
- No PR-triggered VM CI initially.
- No automated changelog generation.

## Success criteria

- CI badge on README reflects a green macOS smoke job running nightly.
- A release is: edit CHANGELOG, run `scripts/release.sh <version>` —
  everything else is automated.
- GitHub Releases page shows real notes per version.
- "Sandboxing Claude Code" page live and linked; repo topics set.
- Project listed on at least awesome-claude-code and Lima's ecosystem page.
