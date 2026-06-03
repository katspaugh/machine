# Snap-based guest provisioning for node and helix

**Date:** 2026-06-03
**Status:** Approved

## Goal

Use snap inside the Ubuntu guest VMs for the two tools where an official (or
upstream-endorsed) classic-confinement snap exists:

- **node** — official OpenJS Foundation snap, channel-pinned per major
  (`22/stable`), replaces the NodeSource third-party apt repo + gpg key in
  `provision/base.sh`.
- **helix** — classic snap linked from Helix's own docs, replaces the
  multi-file `/opt/helix` tarball install in `provision/modern.sh`.

Both snaps ship arm64 + amd64 stable builds (verified against the snapcraft
store API; helix stable is 25.07.1, exactly the version currently pinned).

## Non-goals

Snap was researched for the full toolchain and **rejected everywhere else**.
Recording the reasons so this isn't re-explored:

- **docker** — the snap is Canonical's, not Docker Inc's; strict confinement
  makes bind mounts outside its allowlist *silently fail*
  (canonical/docker-snap#189), which is fatal for VMs whose purpose is
  mounted workspaces. Docker's docs say to uninstall the snap. Keep the
  Docker apt repo.
- **gh** — the snap is community-built; GitHub's stance is "never install gh
  as a snap" (cli/cli#12223). Keep the GitHub CLI apt repo.
- **claude-code, codex, flyctl, delta, lazygit** — no official snaps; only
  community packages (codex's classic-confinement request was rejected by
  the snap review team). Keep current installs.
- **supabase** — deliberately publishes no snap (supabase/cli#63). Keep the
  .deb fetch.
- **chrome/chromium** — the chromium snap breaks Cypress auto-detection and
  the Chrome sandbox under confinement. Keep Google's apt repo in
  `provision/cypress.sh`.
- Distributing the host CLI `machine` itself as a snap — out of scope; the
  install audience is Homebrew/Nix.
- Holding snap auto-refresh (`snap refresh --hold`) — accepted that node
  minors and helix releases update in the background.

## Design

### 1. node via snap (`provision/base.sh`)

Remove the `add_repo nodesource …` line and `nodejs` from the apt install
list. Install instead:

```bash
snap list node >/dev/null 2>&1 || snap install node --classic --channel=22/stable
```

The guard preserves the script's every-boot contract: re-boots of a
provisioned VM are free and offline-safe; a first install on an offline VM
fails fast (same as today's apt behaviour). `22/stable` pins the major;
snapd auto-refreshes minors.

The snap's squashfs is read-only, which changes two downstream steps:

- **corepack shims** — `corepack enable` writes shims next to the corepack
  binary by default, which would be inside the read-only snap. Use
  `corepack enable --install-directory /usr/local/bin`. (If the snap turns
  out not to expose a `corepack` launcher, install it first with
  `npm install -g corepack` — verify during implementation.)
- **npm globals** — `npm install -g` would target the snap prefix. Set
  the prefix once to `/usr/local` (e.g. `npm config set -g prefix
  /usr/local`) so globals land in `/usr/local/lib/node_modules` and bins in
  `/usr/local/bin`. This also retires the root-owned
  `/usr/lib/node_modules` annoyance the current comment in `base.sh`
  documents.
- **PATH** — the snap exposes `node`/`npm`/`npx` in `/snap/bin`, which is
  not reliably on PATH for cloud-init scripts or the bundled zsh/fish rc
  files. Rather than touching every rc file, symlink the snap's launchers
  into `/usr/local/bin`:

  ```bash
  ln -sf /snap/bin/node /snap/bin/npm /snap/bin/npx /usr/local/bin/
  ```

  Provision scripts that call node tooling before the symlinks exist export
  `PATH="/snap/bin:$PATH"` at the top.

Honest trade-off: roughly complexity-neutral in line count. The win is
dropping the NodeSource third-party repo and gpg key, not simplification.

### 2. helix via snap (`provision/modern.sh`)

Replace the whole `/opt/helix` block (version pin, x86_64/aarch64 arch
mapping, tarball extraction, runtime tree, symlink) with:

```bash
snap list helix >/dev/null 2>&1 || snap install --classic helix
```

Plus cleanup of pre-snap installs on existing VMs — required, because
`/usr/local/bin/hx` precedes `/snap/bin` on PATH and would shadow the snap:

```bash
rm -rf /opt/helix
rm -f /usr/local/bin/hx
```

The snap bundles the grammars/themes runtime and exposes both `hx` and
`helix`. Classic confinement gives the full filesystem access an editor
needs. Version pinning is traded for snapd auto-refresh.

The `HELIX_VERSION` pin and the `HX_ARCH` mapping disappear; the
`GH_ARCH` mapping stays (lazygit still uses it).

### 3. Shared assumptions

- snapd is preinstalled and preseeded on the Ubuntu cloud images Lima uses;
  cloud-init orders `runcmd`-stage provisioning after `snapd.seeded`, so no
  ordering race. First boot pays a few extra seconds of seeding.
- `snap install` is **not** idempotent (non-zero exit when already
  installed) and hard-fails offline for a missing snap — hence the
  `snap list` guards, mirroring the existing `command -v` guard pattern.

## Error handling

- Offline re-boot of a provisioned VM: guards skip both installs; boot
  probe unaffected.
- Offline first boot: `snap install` fails fast and the cloud-init probe
  surfaces it — identical failure mode to today's apt/curl installs.
- snapd seeding stall (rare): cloud-init blocks, the existing
  "provisioning finished" probe times out with its existing hint pointing
  at `/var/log/cloud-init-output.log`.

## Testing

1. Bake a fresh scratch VM with the `modern` profile.
2. Verify: `node --version` (22.x), `npm`, `npx` resolve from a zsh and
   fish login shell; `pnpm`, `yarn`, `tsc` resolve (corepack shims + npm
   globals in `/usr/local/bin`); `hx --version` and `helix` resolve;
   `npm install -g` of a scratch package succeeds without touching
   `/snap`.
3. Reboot the VM (`machine down && machine up`): provision re-runs clean
   and fast (guards hit), versions unchanged.
4. Simulate an upgraded VM: pre-create `/opt/helix` and the stale
   `/usr/local/bin/hx` symlink, re-provision, confirm cleanup and that
   `hx` resolves to `/snap/bin/hx`.
5. Run the existing test suite in `tests/`.
