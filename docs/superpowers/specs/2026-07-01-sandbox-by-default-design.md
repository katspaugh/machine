# Enable Claude Code's built-in sandbox by default

**Date:** 2026-07-01
**Status:** Approved

## Problem

The default guest image lacks the two packages Claude Code's built-in Bash
sandbox needs on Linux (`bubblewrap`, `socat`), and the sandbox is not enabled
in the provisioned `~/.claude/settings.json`. As a result the second
defense-in-depth layer the README promises ("the built-in sandbox keeps working
inside the VM") is not actually present in a freshly-baked VM.

Enabling it is not just "flip a flag": the guest is Ubuntu 24.04, where the
default AppArmor policy blocks `bwrap` from creating the unprivileged user
namespaces it needs. With deps installed but no AppArmor profile,
`sandbox.enabled: true` **silently falls back to unsandboxed** — which is why
the sandbox appears "not enabled" even after turning it on.

## Goal

Full defense-in-depth: every baked VM boots with the built-in sandbox actually
engaged, as a real second layer inside the already-isolating VM. No manual
`/sandbox` step.

## References

- Sandboxing guide: https://code.claude.com/docs/en/sandboxing
- Settings schema: https://json.schemastore.org/claude-code-settings.json

## Design

### 1. `provision/base.sh` — install deps + Ubuntu 24.04 AppArmor fix

- Add `bubblewrap socat` to the `apt-get install` list.
- After package install, an idempotent AppArmor step: if
  `sysctl -n kernel.apparmor_restrict_unprivileged_userns` returns `1`, write
  `/etc/apparmor.d/bwrap` (the profile from Anthropic's docs, granting `bwrap`
  the `userns` capability) and `systemctl reload apparmor`. Skip when the key
  is absent or `0`. Non-fatal on offline re-boots, matching the file's existing
  best-effort convention.

The seccomp filter (`@anthropic-ai/sandbox-runtime`, optional, adds Unix-domain
socket blocking) is out of scope — `git`/`docker` are excluded from the sandbox
anyway (see below), so it buys little here.

### 2. `provision/base-user.sh` — enable in settings.json

Add a `sandbox` block to the generated `~/.claude/settings.json`:

```json
"sandbox": {
  "enabled": true,
  "excludedCommands": ["git", "docker"],
  "failIfUnavailable": true
}
```

- `enabled: true` — turn the sandbox on for all projects (user-scope setting).
- `excludedCommands: ["git", "docker"]` — run these outside the sandbox:
  - `docker` is documented as incompatible with the sandbox, and this VM
    installs and leans on Docker.
  - `git` depends on the forwarded SSH-agent unix socket (blocked by default)
    for gpg-signed commits and on outbound SSH for push; excluding it keeps
    signing and push working through the existing `auto` permission flow.
    Matches the docs' own `["git", "docker"]` example.
- `failIfUnavailable: true` — since we install the deps and the AppArmor
  profile, make a missing sandbox a hard startup failure rather than a silent
  unsandboxed fallback. This is what makes "enabled" a guarantee.
- `autoAllowBashIfSandboxed` is left at its default (`true`), preserving the
  zero-prompt feel for sandboxed commands alongside `permissions.defaultMode:
  "auto"`.

The current script hand-builds `settings.json` with `printf`. A nested object
is error-prone that way, so regenerate the file via `python3` (already a base
dependency) from the same `PLUGINS` list. Output keys (`permissions`,
`enabledPlugins`) are unchanged, so `tests/smoke-claude-plugins.sh` still
passes.

### 3. `tests/smoke-sandbox.sh` (new)

Assert, over `limactl shell "$NAME"`:
- `bubblewrap` and `socat` are on `PATH`.
- `/etc/apparmor.d/bwrap` exists (only meaningful when the sysctl is `1`; the
  test guards on that so it does not false-fail on kernels without the
  restriction).
- A real `bwrap --unshare-user --unshare-net --dev-bind / / true` succeeds —
  proving the AppArmor profile actually lets bwrap create namespaces.
- `sandbox.enabled == true` in `~/.claude/settings.json`.

`tests/run-all.sh` globs `smoke-*.sh`, so no runner change is needed.

### 4. Docs

- README: update the "Claude Code already has a sandbox — why a VM?" section to
  state the built-in sandbox is now pre-enabled inside the VM (not merely "keeps
  working"), and note git/docker run outside it. Update the `base.sh` file-tree
  comment to mention the sandbox deps.
- CHANGELOG: add an `[Unreleased] → Added` entry.

## Out of scope

- Pre-allowing network domains (`allowedDomains`). First-hit domain prompts are
  acceptable for the "full defense-in-depth" choice; can revisit if noisy.
- The optional seccomp helper package.
- macOS host (the sandbox runs in the Linux guest only).
