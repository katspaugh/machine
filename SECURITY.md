# Security policy

`machine` is built around a threat model: one Lima VM per project, no host filesystem mount, secrets in tmpfs, and a forwarded SSH agent that never copies private keys into the guest — though while a forwarded connection is open, the guest can *use* every key the agent holds (auth and signing, for any repo the key authorizes). The README's [threat model](README.md#threat-model) spells out exactly what that grants and how to [restrict it](README.md#restricting-the-forwarded-agent). We take reports against that boundary seriously.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security reports.

Use GitHub's private vulnerability reporting:

1. Go to <https://github.com/katspaugh/machine/security/advisories/new>.
2. Describe the issue, an impact estimate, and a minimal reproduction if you have one.

If GitHub's private reporting is unavailable to you, email the maintainer listed in `git log` for `bin/machine` with subject `machine security report`.

## Scope

In scope:

- The host CLI (`bin/machine`) and its interaction with the SSH agent socket and `limactl`.
- The Lima templates (`templates/*.yaml`) and the provision scripts (`provision/*.sh`) cloud-init runs inside the VM.
- `machine secrets` and the 1Password env-injection path (`files/direnv/op_env`), including how rendered envs reach `$XDG_RUNTIME_DIR/dev-secrets`.
- The published Homebrew formula (`Formula/machine.rb`) and the tap repository.

Out of scope:

- Vulnerabilities in upstream dependencies (`lima`, Docker, Node, etc.) — please report those upstream. We will track and ship updates when upstream patches land.
- Issues that require an already-compromised host (root on macOS, write access to `~/.ssh/`).
- Social-engineering of `projects.toml` contents — anything you put in `repos`/`profiles` is trusted by design.

## Response

We aim to acknowledge reports within 72 hours, share a fix or mitigation plan within 14 days, and credit reporters in release notes unless asked not to.
