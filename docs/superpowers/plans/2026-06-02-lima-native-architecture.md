# Lima-Native Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the GUI and replace the self-written provisioning system (provision.toml DSL + run.py + log_view.py) with Lima-native composable templates, shrinking `bin/machine` to a ~400-line remote control around `limactl`.

**Architecture:** Per-project VMs are created from a generated 4-line template that stacks `templates/base.yaml` + one template per profile via Lima's `base:` composition. Provisioning is idempotent bash referenced from templates (`provision:` with `file:`), run by cloud-init on every boot. Dotfiles are `mode: data` entries; host values (git identity, signing key, shell) flow in via `param:` + `--set`. Spec: `docs/superpowers/specs/2026-06-02-lima-native-architecture-design.md`.

**Tech Stack:** Python 3.12 stdlib (single-file CLI), Lima ≥ 2.x templates, bash, Homebrew formula.

**Spec deviation to flag:** the old `bin/machine` also maintained a managed block in `~/.ssh/config` (`refresh_ssh_config`, ~250 lines incl. doctor checks). This plan deletes it and documents Lima's native equivalent in the README instead: `Include ~/.lima/*/ssh.config` gives `ssh lima-<project>` for free.

**Verification environment note:** Tasks 1–7 are host-only (lint + unit tests + `limactl validate`, no VM boot). Task 8 boots real VMs and takes ~20–30 min; it is the integration gate.

---

## File structure (end state)

```
machine/
├── bin/machine                  # rewritten, single file, stdlib only
├── templates/
│   ├── base.yaml                # NEW — replaces lima.yaml + provision.toml + files push
│   ├── cypress.yaml             # NEW — replaces profiles/cypress.toml
│   └── supabase-fly.yaml        # NEW — replaces profiles/supabase-fly.toml
├── provision/
│   ├── base.sh                  # NEW — root provisioning (apt, docker, node, gh)
│   ├── base-user.sh             # NEW — user provisioning (claude + plugins)
│   ├── cypress.sh               # NEW
│   └── supabase-fly.sh          # NEW
├── files/                       # kept: zsh/, fish/, direnv/, ssh/, profile.d/
│                                # deleted: git/*.tpl (now inline in base.yaml)
├── tests/
│   ├── unit/                    # rewritten: test_projects.py, test_render.py
│   └── smoke-*.sh               # kept as-is
├── completions/                 # regenerated (3 files)
├── projects.toml.example        # unchanged
└── Formula/machine.rb           # unchanged
DELETED: gui/, Casks/, .github/workflows/release.yml, provision/run.py,
         provision/log_view.py, provision.toml, profiles/, schemas/, lima.yaml,
         files/git/*.tpl, .pnpm-store/, bin/__pycache__/
```

---

### Task 1: Delete the GUI and its scaffolding

**Files:**
- Delete: `gui/` (entire tree), `Casks/machine-gui.rb`, `.github/workflows/release.yml`, `docs/superpowers/specs/2026-05-26-gui-design.md`, `docs/superpowers/specs/2026-05-27-add-project-button-design.md`, `docs/superpowers/plans/2026-05-26-gui-plan-*.md` (4 files), `docs/superpowers/plans/2026-05-27-add-project-button.md`
- Delete (untracked junk): `.pnpm-store/`, `bin/__pycache__/`, `tests/__pycache__/`, `tests/unit/__pycache__/`
- Modify: `.gitignore` (drop the 6 `gui/` lines, lines 17–22)
- Modify: `scripts/release.sh` (drop GUI cask bump)
- Modify: `docs/TAP.md` (drop "Releasing the GUI cask" section, lines 72–94)

- [ ] **Step 1: Remove tracked GUI artifacts**

```bash
cd /Users/ivan/Sites/machine
git rm -r --quiet gui Casks .github/workflows/release.yml \
  docs/superpowers/specs/2026-05-26-gui-design.md \
  docs/superpowers/specs/2026-05-27-add-project-button-design.md \
  docs/superpowers/plans/2026-05-26-gui-plan-1-cli-json.md \
  docs/superpowers/plans/2026-05-26-gui-plan-2a-foundation.md \
  docs/superpowers/plans/2026-05-26-gui-plan-2b-ui.md \
  docs/superpowers/plans/2026-05-26-gui-plan-3-packaging.md \
  docs/superpowers/plans/2026-05-27-add-project-button.md
rm -rf .pnpm-store bin/__pycache__ tests/__pycache__ tests/unit/__pycache__
```

- [ ] **Step 2: Edit `.gitignore`** — delete these lines:

```
# gui/ (Tauri + SvelteKit) build artifacts
gui/node_modules/
gui/build/
gui/.svelte-kit/
gui/src-tauri/target/
gui/src-tauri/gen/schemas/
```

- [ ] **Step 3: Edit `scripts/release.sh`** — delete the `DMG_URL=` assignment (line ~23), the whole `bump_cask()` function (lines ~25–55), and the trailing call (comment `# 6. Bump the GUI cask…` + `bump_cask`, lines ~111–112). Run `bash -n scripts/release.sh` to confirm it still parses.

- [ ] **Step 4: Edit `docs/TAP.md`** — delete the entire `## Releasing the GUI cask` section (line 72 to end of file).

- [ ] **Step 5: Verify and commit**

```bash
bash tests/lint.sh        # expect: lint OK
git add -A
git commit -m "Remove the GUI, cask, and DMG release workflow"
```

---

### Task 2: Create `templates/base.yaml`

**Files:**
- Create: `templates/base.yaml`
- Note: references `provision/base.sh` + `provision/base-user.sh` which Task 3 creates — `limactl validate` of this template will only fully pass after Task 3. Create placeholder scripts in this task (see Step 2) so validation passes immediately.

- [ ] **Step 1: Write `templates/base.yaml`** with exactly this content:

```yaml
# Base VM template. `bin/machine up <p>` generates .build/<p>/lima.yaml with
# `base: [this file, one per profile]`; Lima merges them (profile provision
# entries append after ours). Provision scripts run on EVERY boot via
# cloud-init scripts-per-boot — they must stay idempotent.
#
# Host values arrive as params (`limactl create --set '.param.X = "..."'`):
#   gitName / gitEmail / signingKey — rendered into ~/.gitconfig and
#   ~/.config/git/allowed_signers below; shell — applied by provision/base.sh.
vmType: vz

cpus: 4
memory: 8GiB
disk: 30GiB

images:
- location: "https://cloud-images.ubuntu.com/releases/24.04/release/ubuntu-24.04-server-cloudimg-arm64.img"
  arch: aarch64
- location: "https://cloud-images.ubuntu.com/releases/24.04/release/ubuntu-24.04-server-cloudimg-amd64.img"
  arch: x86_64

# No host filesystem visible to the guest. Each project gets its own VM.
mounts: []

ssh:
  forwardAgent: true
  loadDotSSHPubKeys: false

# No portForwards block: Lima auto-forwards listening guest ports to
# 127.0.0.1 via the guest agent.

hostResolver:
  enabled: true

param:
  shell: zsh
  gitName: ""
  gitEmail: ""
  signingKey: ""

provision:
# --- Dotfiles (rewritten every boot; known_hosts only written once) --------
- mode: data
  file: ../files/zsh/zshrc
  path: "{{.Home}}/.zshrc"
  owner: "{{.User}}:{{.User}}"
  permissions: 644
- mode: data
  file: ../files/fish/config.fish
  path: "{{.Home}}/.config/fish/config.fish"
  owner: "{{.User}}:{{.User}}"
  permissions: 644
- mode: data
  file: ../files/direnv/op_env.sh
  path: "{{.Home}}/.config/direnv/direnvrc"
  owner: "{{.User}}:{{.User}}"
  permissions: 644
# Pre-seeded known_hosts so first clone uses strict host key checking instead
# of TOFU. overwrite:false → user-appended entries survive reboots.
- mode: data
  file: ../files/ssh/known_hosts
  path: "{{.Home}}/.ssh/known_hosts"
  owner: "{{.User}}:{{.User}}"
  permissions: 644
  overwrite: false
# Login-shell snippets (root-owned, defaults are fine).
- mode: data
  file: ../files/profile.d/node.sh
  path: /etc/profile.d/node.sh
- mode: data
  file: ../files/profile.d/direnv.sh
  path: /etc/profile.d/direnv.sh
- mode: data
  file: ../files/profile.d/local-bin.sh
  path: /etc/profile.d/local-bin.sh
# Git identity + SSH signing, rendered from params (replaces files/git/*.tpl).
- mode: data
  path: "{{.Home}}/.gitconfig"
  owner: "{{.User}}:{{.User}}"
  permissions: 644
  content: |
    [user]
      name = {{.Param.gitName}}
      email = {{.Param.gitEmail}}
      signingkey = {{.Param.signingKey}}

    [gpg]
      format = ssh

    [gpg "ssh"]
      program = ssh-keygen
      allowedSignersFile = ~/.config/git/allowed_signers

    [commit]
      gpgsign = true
    [tag]
      gpgsign = true

    [init]
      defaultBranch = main
    [pull]
      rebase = true
    [fetch]
      prune = true
- mode: data
  path: "{{.Home}}/.config/git/allowed_signers"
  owner: "{{.User}}:{{.User}}"
  permissions: 644
  content: |
    {{.Param.gitEmail}} {{.Param.signingKey}}
# --- Provision scripts ------------------------------------------------------
- mode: system
  file: ../provision/base.sh
- mode: user
  file: ../provision/base-user.sh

# `limactl start` blocks until probes pass — a failed provision script leaves
# cloud-init in "error" and start fails with the hint below.
probes:
- description: provisioning finished
  script: |
    #!/bin/bash
    set -eu
    cloud-init status 2>/dev/null | grep -q "status: done"
  hint: |
    Provisioning is still running or failed. Inspect with:
      limactl shell <vm> sudo tail -100 /var/log/cloud-init-output.log
```

- [ ] **Step 2: Create placeholder provision scripts** (Task 3 fills them in) so the template's `file:` refs resolve:

```bash
mkdir -p provision
printf '#!/bin/bash\n# placeholder — filled in by Task 3\ntrue\n' > provision/base.sh
printf '#!/bin/bash\n# placeholder — filled in by Task 3\ntrue\n' > provision/base-user.sh
```

- [ ] **Step 3: Validate the template**

```bash
limactl validate templates/base.yaml
```
Expected: exits 0 (warnings about images are OK; errors are not).

```bash
limactl template copy --embed templates/base.yaml /tmp/claude/base-embedded.yaml
grep -c "mode: data" /tmp/claude/base-embedded.yaml
```
Expected: `9` (all data entries embedded). Also eyeball that the provision scripts' content got embedded and `{{.Param.shell}}` survives as-is (params are evaluated at instance create, not embed).

- [ ] **Step 4: Check merge semantics for the golden-image override** — verify that a child template's `images:` wins over the base's:

```bash
cat > /tmp/claude/child.yaml <<'EOF'
images:
- location: "file:///tmp/fake.img"
  arch: aarch64
base:
- /Users/ivan/Sites/machine/templates/base.yaml
EOF
limactl template copy --embed /tmp/claude/child.yaml /tmp/claude/child-embedded.yaml
grep -A1 "^images:" /tmp/claude/child-embedded.yaml | head -4
```
Expected: `file:///tmp/fake.img` appears **first** in the images list (child entries take priority; Lima may append base images after — that's fine, first match per arch wins). If the file:// entry is NOT first, note the actual merge order and adjust `render_template` in Task 5 to use `--set` image injection instead — but verify first; this is the expected behavior.

- [ ] **Step 5: Commit**

```bash
git add templates/base.yaml provision/base.sh provision/base-user.sh
git commit -m "Add Lima-native base template"
```

---

### Task 3: Write the base provision scripts

**Files:**
- Modify: `provision/base.sh` (replace placeholder)
- Modify: `provision/base-user.sh` (replace placeholder)

These translate `provision.toml` + `provision/run.py` semantics into plain idempotent bash. Content sources: apt packages and repos from `provision.toml` lines 21–48, corepack/npm from lines 58–63, shell selection from lines 81–87, claude config from lines 70–75.

- [ ] **Step 1: Write `provision/base.sh`:**

```bash
#!/bin/bash
# Base provisioning — runs as root on EVERY boot (cloud-init scripts-per-boot).
# Everything here must be idempotent and cheap when already applied.
# {{.User}}/{{.Home}}/{{.Param.shell}} are Lima guest-template variables,
# substituted when the instance is created.
set -eu -o pipefail
export DEBIAN_FRONTEND=noninteractive

ARCH=$(dpkg --print-architecture)
CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
LIMA_USER="{{.User}}"
USER_HOME="{{.Home}}"

# Heal ownership of dirs that mode:data file placement may have created as
# root (e.g. ~/.config, ~/.ssh on first boot).
chown -R "$LIMA_USER:$LIMA_USER" "$USER_HOME/.config" "$USER_HOME/.ssh" 2>/dev/null || true

# --- Third-party apt repos --------------------------------------------------
install -m 0755 -d /etc/apt/keyrings
add_repo() { # <name> <key_url> <deb_line>
  local key="/etc/apt/keyrings/$1.gpg"
  if [ ! -f "$key" ]; then
    curl -fsSL "$2" | gpg --batch --yes --dearmor -o "$key"
    chmod a+r "$key"
  fi
  echo "deb [arch=$ARCH signed-by=$key] $3" > "/etc/apt/sources.list.d/$1.list"
}
add_repo docker https://download.docker.com/linux/ubuntu/gpg \
  "https://download.docker.com/linux/ubuntu $CODENAME stable"
add_repo github-cli https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  "https://cli.github.com/packages stable main"
add_repo nodesource https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
  "https://deb.nodesource.com/node_22.x nodistro main"

# --- Packages ----------------------------------------------------------------
apt-get update -qq
apt-get install -y --no-install-recommends \
  build-essential ca-certificates curl gnupg jq xz-utils unzip git zsh fish \
  ripgrep fd-find tmux less file python3 direnv \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
  gh nodejs

usermod -aG docker "$LIMA_USER"
systemctl enable --now docker

# --- corepack-managed package managers + npm globals -------------------------
# apt-installed Node keeps globals in /usr/lib/node_modules (root-owned).
corepack enable
corepack prepare pnpm@latest --activate
corepack prepare yarn@stable --activate
npm install -g typescript typescript-language-server @openai/codex

# --- Default login shell ------------------------------------------------------
TARGET_SHELL="{{.Param.shell}}"
case "$TARGET_SHELL" in
  zsh|fish|bash) chsh -s "/usr/bin/$TARGET_SHELL" "$LIMA_USER" || true ;;
  *) echo "unknown shell: $TARGET_SHELL" >&2; exit 1 ;;
esac
```

- [ ] **Step 2: Write `provision/base-user.sh`:**

```bash
#!/bin/bash
# User provisioning — runs as the lima user on every boot, after base.sh.
# Installs Claude Code + the plugin set. Idempotent: re-runs are no-ops.
set -eu -o pipefail

export PATH="$HOME/.local/bin:$PATH"

if ! command -v claude >/dev/null 2>&1; then
  curl -fsSL https://claude.ai/install.sh | bash
fi
command -v claude >/dev/null

MARKETPLACE="anthropics/claude-plugins-official"
MARKETPLACE_ID="claude-plugins-official"
PLUGINS="frontend-design superpowers github typescript-lsp security-guidance commit-commands chrome-devtools-mcp supabase"

# `claude plugin ...` is noisy when already done: treat "already"/"exists"
# output as success, propagate anything else.
run_claude() {
  local out rc=0
  out=$(claude "$@" 2>&1) || rc=$?
  if [ "$rc" -ne 0 ] && ! printf '%s' "$out" | grep -qi -e "already" -e "exists"; then
    printf '%s\n' "$out" >&2
    return "$rc"
  fi
  printf '%s\n' "$out"
}

run_claude plugin marketplace add "$MARKETPLACE"
for p in $PLUGINS; do
  run_claude plugin install "$p@$MARKETPLACE_ID"
done

# Settings: defaultMode + the enabled-plugin map.
mkdir -p "$HOME/.claude"
{
  printf '{\n  "permissions": { "defaultMode": "auto" },\n  "enabledPlugins": {\n'
  first=1
  for p in $PLUGINS; do
    [ "$first" -eq 1 ] || printf ',\n'
    printf '    "%s@%s": true' "$p" "$MARKETPLACE_ID"
    first=0
  done
  printf '\n  }\n}\n'
} > "$HOME/.claude/settings.json"
```

- [ ] **Step 3: Lint and validate**

```bash
shellcheck provision/base.sh provision/base-user.sh
limactl validate templates/base.yaml
```
Expected: shellcheck clean (SC2154-style warnings about `{{.User}}` won't occur — it's inside quotes; if shellcheck complains about anything, fix it). validate exits 0.

- [ ] **Step 4: Commit**

```bash
git add provision/base.sh provision/base-user.sh
git commit -m "Translate base provisioning to idempotent bash"
```

---

### Task 4: Profile templates + scripts (cypress, supabase-fly)

**Files:**
- Create: `templates/cypress.yaml`, `provision/cypress.sh`
- Create: `templates/supabase-fly.yaml`, `provision/supabase-fly.sh`

Content sources: `profiles/cypress.toml` and `profiles/supabase-fly.toml` (do not delete them yet — Task 6 does).

- [ ] **Step 1: Write `templates/cypress.yaml`:**

```yaml
# Cypress + a Chromium-family browser. Stacks on base.yaml via the generated
# per-project template's `base:` list.
provision:
- mode: system
  file: ../provision/cypress.sh
```

- [ ] **Step 2: Write `provision/cypress.sh`:**

```bash
#!/bin/bash
# Cypress system deps + a browser. Chrome on amd64 (no arm64 .deb exists);
# chromium-browser on arm64. Idempotent; runs on every boot.
set -eu -o pipefail
export DEBIAN_FRONTEND=noninteractive

ARCH=$(dpkg --print-architecture)

PKGS=(libgtk2.0-0 libgtk-3-0 libgbm-dev libnotify-dev libnss3 libxss1
      libasound2t64 libxtst6 xauth xvfb fonts-liberation)

if [ "$ARCH" = "amd64" ]; then
  key=/etc/apt/keyrings/google-chrome.gpg
  if [ ! -f "$key" ]; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
      | gpg --batch --yes --dearmor -o "$key"
    chmod a+r "$key"
  fi
  echo "deb [arch=amd64 signed-by=$key] http://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list
  PKGS+=(google-chrome-stable)
else
  PKGS+=(chromium-browser)
fi

apt-get update -qq
apt-get install -y --no-install-recommends "${PKGS[@]}"
```

- [ ] **Step 3: Write `templates/supabase-fly.yaml`:**

```yaml
# Supabase CLI + fly.io CLI for projects that deploy there.
provision:
- mode: system
  file: ../provision/supabase-fly.sh
```

- [ ] **Step 4: Write `provision/supabase-fly.sh`:**

```bash
#!/bin/bash
# Supabase CLI (GitHub release tarball) + flyctl (vendor installer).
# Idempotent; runs on every boot.
set -eu -o pipefail

ARCH=$(dpkg --print-architecture)

if [ ! -x /usr/local/bin/supabase ]; then
  tmp=$(mktemp -d)
  curl -fsSL "https://github.com/supabase/cli/releases/latest/download/supabase_linux_${ARCH}.tar.gz" \
    | tar -xz -C "$tmp"
  install -m 0755 "$tmp/supabase" /usr/local/bin/supabase
  rm -rf "$tmp"
fi
/usr/local/bin/supabase --version

if [ ! -x /usr/local/bin/flyctl ]; then
  curl -fsSL https://fly.io/install.sh | FLYCTL_INSTALL=/usr/local bash
fi
/usr/local/bin/flyctl version
```

- [ ] **Step 5: Lint, validate composition, commit**

```bash
shellcheck provision/cypress.sh provision/supabase-fly.sh
limactl validate templates/cypress.yaml templates/supabase-fly.yaml
cat > /tmp/claude/stack.yaml <<'EOF'
base:
- /Users/ivan/Sites/machine/templates/base.yaml
- /Users/ivan/Sites/machine/templates/cypress.yaml
- /Users/ivan/Sites/machine/templates/supabase-fly.yaml
EOF
limactl template copy --embed /tmp/claude/stack.yaml /tmp/claude/stack-embedded.yaml
grep -c "mode: system" /tmp/claude/stack-embedded.yaml
```
Expected: `3` system scripts (base, cypress, supabase-fly), with base.sh **first** in the file (base templates prepend). Then:

```bash
git add templates/cypress.yaml templates/supabase-fly.yaml provision/cypress.sh provision/supabase-fly.sh
git commit -m "Add cypress and supabase-fly profile templates"
```

---

### Task 5: Rewrite `bin/machine`

**Files:**
- Rewrite: `bin/machine` (full content below)
- Delete: `tests/unit/test_*.py` (all 11 — they test deleted internals)
- Create: `tests/unit/test_machine.py`
- Keep: `tests/unit/__init__.py`, `tests/__init__.py`

The new CLI keeps these functions **verbatim from the old file** (same names, same behavior): `_env_dir`, `die`, `load_dotenv`, `configure_ssh_agent`, `load_projects`, `get_project`, `project_urls`, `project_profiles`, `project_shell`, `validate_name`, `repo_basename`, `run`, `lima_shell`, `lima_bash`, `vm_exists`, `close_lima_ssh_master`, `git_config`, `read_signing_key`, `extract_env_id`, `sync_one_env`, `cmd_secrets`, `cmd_secrets_clear`, `verify_repos_reachable` (minus the `renderer` parameter), `clone` logic, golden-image helpers. Dropped: everything renderer-related, ps/list/doctor JSON, ssh-config management, `update`, `rebuild`, `status`, `validate`, `config`.

- [ ] **Step 1: Write the failing unit tests** — `tests/unit/test_machine.py`:

```python
"""Unit tests for the host-side helpers in bin/machine. No VM required."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_machine(extra_env: dict[str, str] | None = None):
    """Import bin/machine fresh with a controlled environment."""
    for key, value in (extra_env or {}).items():
        os.environ[key] = value
    spec = importlib.util.spec_from_file_location("machine_cli", ROOT / "bin" / "machine")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestHelpers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        projects = Path(self.tmp.name) / "projects.toml"
        projects.write_text(
            'default_profile = "cypress"\n'
            "[blog]\n"
            'repos = ["git@github.com:me/blog.git"]\n'
            "[wallet]\n"
            'profiles = ["cypress", "supabase-fly"]\n'
            'shell = "fish"\n'
            'repos = ["git@github.com:me/a.git", "git@github.com:me/b.git"]\n'
            "[bare]\n"
            "profiles = []\n"
            'repos = []\n'
        )
        self.m = load_machine({
            "PROJECTS_FILE": str(projects),
            "MACHINE_STATE_DIR": str(Path(self.tmp.name) / "state"),
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_repo_basename(self):
        self.assertEqual(self.m.repo_basename("git@github.com:me/blog.git"), "blog")
        self.assertEqual(self.m.repo_basename("https://github.com/me/x"), "x")

    def test_validate_name_rejects_bad(self):
        with self.assertRaises(SystemExit):
            self.m.validate_name("Bad_Name")
        self.m.validate_name("ok-name-2")  # no raise

    def test_project_profiles_default_and_explicit(self):
        self.assertEqual(self.m.project_profiles("blog"), ["cypress"])
        self.assertEqual(self.m.project_profiles("wallet"), ["cypress", "supabase-fly"])
        self.assertEqual(self.m.project_profiles("bare"), [])

    def test_project_shell(self):
        self.assertEqual(self.m.project_shell("blog"), "zsh")
        self.assertEqual(self.m.project_shell("wallet"), "fish")

    def test_param_set_args_quotes_values(self):
        args = self.m.param_set_args(
            {"gitName": 'Ivan "K"', "shell": "zsh"})
        self.assertEqual(args[0], "--set")
        self.assertIn('.param.gitName = "Ivan \\"K\\""', args[1])
        self.assertIn('.param.shell = "zsh"', args[3])

    def test_render_template_without_golden(self):
        out = self.m.render_template("wallet", ["cypress"], golden=False)
        text = out.read_text()
        self.assertIn("base:", text)
        self.assertIn("templates/base.yaml", text)
        self.assertIn("templates/cypress.yaml", text)
        self.assertNotIn("file://", text)

    def test_render_template_with_golden(self):
        img = Path(self.tmp.name) / "base-arm64.img"
        img.write_bytes(b"fake")
        out = self.m.render_template("wallet", [], golden=True, golden_image=img)
        text = out.read_text()
        self.assertIn(f"file://{img}", text)
        # images come before base so the cached disk wins
        self.assertLess(text.index("images:"), text.index("base:"))

    def test_render_template_rejects_unknown_profile(self):
        with self.assertRaises(SystemExit):
            self.m.render_template("wallet", ["nope"], golden=False)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Delete the old unit tests and run the new one to verify it fails**

```bash
git rm --quiet tests/unit/test_config_add_project.py tests/unit/test_provision.py \
  tests/unit/test_doctor_json.py tests/unit/test_ps_json.py tests/unit/test_ssh_config.py \
  tests/unit/test_cmd_up_renderer.py tests/unit/test_ps.py tests/unit/test_machine.py \
  tests/unit/test_provision_protocol.py tests/unit/test_log_view.py tests/unit/test_list_json.py
# (then create the new tests/unit/test_machine.py from Step 1)
bash tests/unit.sh
```
Expected: FAIL — `param_set_args` / `render_template` don't exist yet (the old bin/machine also imports `log_view`, which still exists, but lacks the new functions).

- [ ] **Step 3: Rewrite `bin/machine`** with this complete content:

```python
#!/usr/bin/env python3
"""machine — host CLI for one isolated Lima VM per project.

Reads projects.toml, generates a per-project Lima template that stacks
templates/base.yaml plus one template per profile (Lima's `base:`
composition), and drives `limactl create/start/shell`. Provisioning is
Lima-native: provision scripts and dotfiles are declared in the templates
and applied by cloud-init inside the VM on every boot.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, Sequence

REPO = Path(__file__).resolve().parent.parent
# In a git checkout REPO == the cloned tree (config + state colocated).
# Under a Homebrew install user config moves to ~/.config/machine and
# generated state to ~/.local/state.
_IN_CHECKOUT = (REPO / ".git").exists()


def _env_dir(name: str, default: Path) -> Path:
    v = os.environ.get(name)
    return Path(v).expanduser() if v else default


CONFIG_DIR = _env_dir(
    "MACHINE_CONFIG_DIR",
    REPO if _IN_CHECKOUT else Path.home() / ".config" / "machine",
)
STATE_DIR = _env_dir(
    "MACHINE_STATE_DIR",
    REPO / ".build" if _IN_CHECKOUT else Path.home() / ".local" / "state" / "machine",
)
PROJECTS_FILE = Path(os.environ.get("PROJECTS_FILE") or CONFIG_DIR / "projects.toml")
GOLDEN_DIR = Path.home() / ".cache" / "machine"
ONEPASS_SOCK_DEFAULT = (
    Path.home()
    / "Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock"
)
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


# --- Errors ----------------------------------------------------------------
def die(msg: str, code: int = 1) -> "Any":
    print(f"machine: {msg}", file=sys.stderr)
    raise SystemExit(code)


# --- Bootstrap -------------------------------------------------------------
def load_dotenv() -> None:
    """Load CONFIG_DIR/.env as KEY=value pairs. Gitignored, optional."""
    env = CONFIG_DIR / ".env"
    if not env.is_file():
        return
    for raw in env.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        v = value.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            v = v[1:-1]
        os.environ.setdefault(key.strip(), v)


def configure_ssh_agent() -> None:
    """If MACHINE_USE_1PASSWORD=1, point SSH_AUTH_SOCK at 1Password's agent."""
    if os.environ.get("MACHINE_USE_1PASSWORD") != "1":
        return
    sock = Path(os.environ.get("ONEPASS_SOCK") or ONEPASS_SOCK_DEFAULT)
    if not sock.is_socket():
        die(
            f"MACHINE_USE_1PASSWORD=1 but 1Password agent socket not found at {sock}\n"
            f"  Open 1Password → Settings → Developer → 'Use the SSH agent'."
        )
    os.environ["SSH_AUTH_SOCK"] = str(sock)


# --- Projects TOML helpers -------------------------------------------------
def load_projects() -> dict[str, Any]:
    if not PROJECTS_FILE.is_file():
        die(
            f"{PROJECTS_FILE} not found. "
            f"Run `machine init` (or copy {REPO / 'projects.toml.example'} to {PROJECTS_FILE} and edit)."
        )
    return tomllib.loads(PROJECTS_FILE.read_text())


def get_project(cfg: dict[str, Any], name: str) -> dict[str, Any]:
    p = cfg.get(name)
    if not isinstance(p, dict):
        die(f"project '{name}' not in {PROJECTS_FILE}")
    return p  # type: ignore[return-value]


def project_urls(name: str) -> list[str]:
    return list(get_project(load_projects(), name).get("repos", []))


def project_profiles(name: str) -> list[str]:
    cfg = load_projects()
    project = get_project(cfg, name)
    profiles = project.get("profiles")
    if profiles is None:
        default = cfg.get("default_profile")
        profiles = [default] if default else []
    return [p for p in profiles if p]


def project_shell(name: str) -> str:
    if not PROJECTS_FILE.is_file():
        return "zsh"
    cfg = tomllib.loads(PROJECTS_FILE.read_text())
    project = cfg.get(name) or {}
    shell = project.get("shell") if isinstance(project, dict) else None
    if shell is None:
        shell = cfg.get("default_shell", "zsh")
    if shell not in ("zsh", "fish", "bash"):
        die(f"invalid shell '{shell}' for project '{name}' (use zsh|fish|bash)")
    return shell  # type: ignore[return-value]


def validate_name(name: str) -> None:
    if not NAME_RE.fullmatch(name):
        die(f"invalid project name '{name}' (use a-z, 0-9, hyphen)")


def repo_basename(url: str) -> str:
    base = url.rsplit("/", 1)[-1]
    return base[:-4] if base.endswith(".git") else base


# --- Subprocess helpers ----------------------------------------------------
def run(cmd: Sequence[str], **kw: Any) -> subprocess.CompletedProcess:
    """Run a host command, propagating non-zero exit by default."""
    kw.setdefault("check", True)
    return subprocess.run(list(cmd), **kw)


def lima_shell(vm: str, cmd: Sequence[str], **kw: Any) -> subprocess.CompletedProcess:
    """Run `limactl shell <vm> -- <cmd...>`. Caller controls check/stdin."""
    return subprocess.run(["limactl", "shell", vm, "--", *cmd], **kw)


def lima_bash(vm: str, script: str, *args: str, **kw: Any) -> subprocess.CompletedProcess:
    """Run a shell script body inside the VM via `bash -lc`. Extra positional
    args become $1..$N inside the script."""
    return lima_shell(vm, ["bash", "-lc", script, "bash", *args], **kw)


def vm_exists(name: str) -> bool:
    out = subprocess.run(
        ["limactl", "list", "-q"], capture_output=True, text=True
    ).stdout
    return name in out.splitlines()


def close_lima_ssh_master(vm: str) -> None:
    """Close any persistent SSH ControlMaster for this VM.

    Lima's ssh.config sets `ControlMaster auto` + `ControlPersist yes`, so the
    first `limactl shell` spawns a mux process that subsequent shells reuse.
    Agent forwarding is fixed at the moment the master is created — if the
    host's SSH_AUTH_SOCK changes between runs (e.g. toggling
    MACHINE_USE_1PASSWORD), the mux keeps forwarding the *old* agent. Closing
    the mux forces a fresh master that picks up the current SSH_AUTH_SOCK."""
    lima_vm_dir = Path.home() / ".lima" / vm
    sock = lima_vm_dir / "ssh.sock"
    cfg = lima_vm_dir / "ssh.config"
    if not (sock.exists() and cfg.is_file()):
        return
    subprocess.run(
        ["ssh", "-F", str(cfg), "-O", "exit", f"lima-{vm}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=5, check=False,
    )


def git_config(key: str) -> str:
    return subprocess.run(
        ["git", "config", "--global", key], capture_output=True, text=True
    ).stdout.strip()


# --- Host params pushed into the VM as Lima template params -----------------
def read_signing_key() -> str:
    """Resolve the SSH signing pubkey. Order:
       1. GIT_SIGNING_KEY       (literal pubkey string)
       2. OP_SIGNING_KEY_REF    (1Password secret reference; requires `op`)
       3. GIT_SIGNING_PUBKEY_FILE  (path to a .pub file)
       4. host `git config --global user.signingkey`  (literal or path)
    """
    if literal := os.environ.get("GIT_SIGNING_KEY"):
        return literal
    if op_ref := os.environ.get("OP_SIGNING_KEY_REF"):
        if not shutil.which("op"):
            die("OP_SIGNING_KEY_REF set but 'op' CLI not found (brew install 1password-cli)")
        out = subprocess.run(
            ["op", "read", op_ref], capture_output=True, text=True, check=True
        )
        return out.stdout.replace("\n", "")
    if path := os.environ.get("GIT_SIGNING_PUBKEY_FILE"):
        p = Path(path)
        if not p.is_file():
            die(f"GIT_SIGNING_PUBKEY_FILE not readable at {p}")
        return p.read_text().replace("\n", "")
    host_key = git_config("user.signingkey")
    if not host_key:
        die(
            "no signing pubkey found\n"
            "  Set one on the host: git config --global user.signingkey 'ssh-ed25519 AAAA...'\n"
            "  Or override per-invocation: GIT_SIGNING_KEY=<literal>, "
            "GIT_SIGNING_PUBKEY_FILE=<path>, OP_SIGNING_KEY_REF=op://..."
        )
    if host_key.startswith("key::"):
        return host_key[5:]
    if re.match(r"^(ssh-|ecdsa-|sk-ssh-|sk-ecdsa-)", host_key):
        return host_key
    p = Path(host_key)
    if p.is_file():
        return p.read_text().replace("\n", "")
    die(f"host user.signingkey is not a literal pubkey and not a readable file: {host_key}")


def resolve_params(name: str) -> dict[str, str]:
    """Host values rendered into the VM via Lima params (see base.yaml)."""
    gname = os.environ.get("GIT_NAME") or git_config("user.name")
    email = os.environ.get("GIT_EMAIL") or git_config("user.email")
    sigkey = read_signing_key()
    if not (gname and email):
        die("missing git identity — set `git config --global user.name/user.email` "
            "or GIT_NAME/GIT_EMAIL")
    return {
        "gitName": gname,
        "gitEmail": email,
        "signingKey": sigkey,
        "shell": project_shell(name),
    }


def param_set_args(params: dict[str, str]) -> list[str]:
    """Build `--set '.param.K = "V"'` args; json.dumps handles quoting."""
    args: list[str] = []
    for key, value in params.items():
        args += ["--set", f".param.{key} = {json.dumps(value)}"]
    return args


# --- Template rendering ------------------------------------------------------
def render_template(
    name: str,
    profiles: Sequence[str],
    *,
    golden: bool,
    golden_image: Path | None = None,
) -> Path:
    """Write .build/<vm>/lima.yaml: a `base:` stack of base.yaml + one template
    per profile, with the cached golden disk prepended as the top-priority
    image when available."""
    templates = [REPO / "templates" / "base.yaml"]
    for p in profiles:
        tpl = REPO / "templates" / f"{p}.yaml"
        if not tpl.is_file():
            die(f"unknown profile '{p}' (no {tpl})")
        templates.append(tpl)

    lines: list[str] = ["# Generated by `machine up` — do not edit."]
    if golden:
        img = golden_image or golden_img()
        lines += [
            "images:",
            f'- location: "file://{img}"',
            f'  arch: "{golden_lima_arch()}"',
        ]
    lines.append("base:")
    lines += [f"- {t}" for t in templates]

    out = STATE_DIR / name / "lima.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    return out


# --- Golden image (cached pre-provisioned base disk) -------------------------
def golden_arch_tag() -> str:
    m = os.uname().machine
    return {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64"}.get(m, m)


def golden_lima_arch() -> str:
    m = os.uname().machine
    return {"arm64": "aarch64", "aarch64": "aarch64", "x86_64": "x86_64"}.get(m, m)


def golden_hash() -> str:
    """Content hash of everything that shapes the baked disk: the base
    template, all provision scripts, and the files/ tree it references."""
    h = hashlib.sha256()
    h.update((REPO / "templates" / "base.yaml").read_bytes())
    for d in (REPO / "provision", REPO / "files"):
        for f in sorted(d.rglob("*")):
            if f.is_file():
                h.update(str(f.relative_to(REPO)).encode())
                h.update(f.read_bytes())
    return h.hexdigest()[:16]


def golden_img() -> Path:
    return GOLDEN_DIR / f"base-{golden_arch_tag()}.img"


def golden_stamp() -> Path:
    return GOLDEN_DIR / f"base-{golden_arch_tag()}.hash"


def golden_fresh() -> bool:
    img, stamp = golden_img(), golden_stamp()
    return (
        img.is_file()
        and stamp.is_file()
        and stamp.read_text().strip() == golden_hash()
    )


def bake(force: bool = False) -> None:
    if not force and golden_fresh():
        print(f"[bake] cache fresh ({golden_hash()}) — use --force to rebuild")
        return
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    vm = "machine-base"
    if vm_exists(vm):
        print(f"[bake] removing stale '{vm}'")
        subprocess.run(["limactl", "stop", "-f", vm],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        run(["limactl", "delete", "-f", vm])
    print("[bake] creating + provisioning base VM (~5 min)")
    run(["limactl", "create", "--tty=false", f"--name={vm}",
         str(REPO / "templates" / "base.yaml")])
    # start blocks until the provisioning probe passes.
    run(["limactl", "start", vm])
    run(["limactl", "stop", vm])
    src = Path.home() / ".lima" / vm / "disk"
    if not src.is_file():
        die(f"[bake] expected disk at {src}")
    img = golden_img()
    print(f"[bake] exporting {src} → {img}")
    tmp = img.with_suffix(img.suffix + ".tmp")
    # APFS clonefile (cp -c) is near-instant + preserves sparseness; fall back
    # to plain cp elsewhere.
    if subprocess.run(["cp", "-c", str(src), str(tmp)],
                      stderr=subprocess.DEVNULL).returncode != 0:
        run(["cp", str(src), str(tmp)])
    tmp.replace(img)
    golden_stamp().write_text(golden_hash() + "\n")
    run(["limactl", "delete", "-f", vm])
    print(f"[bake] done — {img}")


# --- Repo checks + cloning ---------------------------------------------------
def verify_repos_reachable(urls: Sequence[str]) -> None:
    """`git ls-remote` each URL on the host before touching the VM — catches
    typos and missing access while failure is still cheap."""
    if not urls:
        return
    print(f"[machine] checking access to {len(urls)} repo(s)…")
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_SSH_COMMAND":
            "ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes -o ConnectTimeout=10",
    }

    def check(url: str) -> str:
        out = subprocess.run(
            ["git", "ls-remote", url, "HEAD"],
            capture_output=True, text=True, env=env,
        )
        if out.returncode == 0:
            return ""
        return (out.stderr or out.stdout).strip() or f"git ls-remote exit {out.returncode}"

    failures: list[tuple[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(urls)) as pool:
        futs = {pool.submit(check, u): u for u in urls}
        for fut in concurrent.futures.as_completed(futs):
            err = fut.result()
            if err:
                failures.append((futs[fut], err))
    if failures:
        lines = ["cannot reach repo(s) — check projects.toml for typos or access:"]
        for url, err in failures:
            lines.append(f"  {url}\n    {err}")
        die("\n".join(lines))


def clone_repo(vm: str, url: str) -> None:
    """Clone one repo into ~/code/<basename>/ inside the VM. Idempotent.
    JS dependency install is best-effort (non-fatal)."""
    repo_name = repo_basename(url)
    rc = lima_shell(
        vm,
        ["bash", "-lc", f'[ -d "$HOME/code/{shlex.quote(repo_name)}/.git" ]'],
        stdin=subprocess.DEVNULL,
    ).returncode
    if rc == 0:
        print(f"[clone] {repo_name}: already present")
        return
    print(f"[clone] {repo_name}")
    run(["limactl", "shell", vm, "--",
         "env",
         "GIT_SSH_COMMAND=ssh -o StrictHostKeyChecking=accept-new -o UpdateHostKeys=no",
         "bash", "-lc",
         f'mkdir -p "$HOME/code" && cd "$HOME/code" && '
         f'git clone --recurse-submodules -- {shlex.quote(url)}'])
    deps_script = (
        f'cd "$HOME/code/{shlex.quote(repo_name)}" 2>/dev/null || exit 0\n'
        '[ -f package.json ] || exit 0\n'
        'if grep -q \'"packageManager":[[:space:]]*"yarn\' package.json 2>/dev/null; then\n'
        '  echo "[deps] yarn install"; yarn install\n'
        'elif grep -q \'"packageManager":[[:space:]]*"pnpm\' package.json 2>/dev/null; then\n'
        '  echo "[deps] pnpm install"; pnpm install\n'
        'else\n'
        '  echo "[deps] npm install"; npm install\n'
        'fi'
    )
    deps_rc = lima_shell(vm, ["bash", "-lc", deps_script]).returncode
    if deps_rc != 0:
        print(f"[deps] {repo_name}: install failed (continuing)", file=sys.stderr)


# --- Commands ----------------------------------------------------------------
def cmd_up(args: argparse.Namespace) -> int:
    name = args.project
    validate_name(name)
    close_lima_ssh_master(name)
    urls = project_urls(name)
    profiles = project_profiles(name)
    params = resolve_params(name)  # fail fast on missing git identity
    verify_repos_reachable(urls)

    if not vm_exists(name):
        # A previous `limactl create` may have left a half-populated VM dir
        # behind. It blocks the next create, so clear it before retrying.
        leftover = Path.home() / ".lima" / name
        if leftover.exists():
            print(f"[machine] removing stale VM dir {leftover}")
            shutil.rmtree(leftover)
        if not golden_fresh():
            print("[machine] no fresh base image cached — baking "
                  "(one-time per template/provision change)")
            bake(force=False)
        tpl = render_template(name, profiles, golden=golden_fresh())
        run(["limactl", "create", "--tty=false", f"--name={name}",
             *param_set_args(params), str(tpl)])

    # Blocks until the provisioning probe passes (see templates/base.yaml).
    run(["limactl", "start", name])

    for url in urls:
        clone_repo(name, url)
    print(f"✓ {name} ready — run 'machine ssh {name}' to log in.")
    return 0


def cmd_down(args: argparse.Namespace) -> int:
    name = args.project
    if not vm_exists(name):
        die(f"VM '{name}' does not exist")
    run(["limactl", "stop", name])
    return 0


def _primary_repo_workdir(name: str) -> str | None:
    """Resolve cwd at ~/code/<primary-repo> inside the VM, or None."""
    try:
        urls = project_urls(name)
    except SystemExit:
        urls = []
    if not urls:
        return None
    repo_name = repo_basename(urls[0])
    rc = lima_shell(
        name,
        ["bash", "-lc", f'[ -d "$HOME/code/{shlex.quote(repo_name)}" ]'],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode
    if rc != 0:
        return None
    user = os.environ["USER"]
    return f"/home/{user}.linux/code/{repo_name}"


def cmd_ssh(args: argparse.Namespace) -> int:
    name = args.project
    workdir = _primary_repo_workdir(name)
    cmd = ["limactl", "shell"]
    if workdir:
        cmd += ["--workdir", workdir]
    cmd += [name]
    os.execvp("limactl", cmd)


def cmd_claude(args: argparse.Namespace) -> int:
    name = args.project
    workdir = _primary_repo_workdir(name)
    cmd = ["limactl", "shell"]
    if workdir:
        cmd += ["--workdir", workdir]
    # Login+interactive bash so /etc/profile.d/* sets PATH the same way
    # `machine ssh` users see, then hand the tty to claude.
    cmd += [name, "bash", "-lic", "exec claude"]
    os.execvp("limactl", cmd)


def cmd_run(args: argparse.Namespace) -> int:
    if not args.argv:
        die("usage: machine run <project> <cmd>...")
    run(["limactl", "shell", args.project, "--", *args.argv])
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    run(["limactl", "list"])
    cfg = load_projects()
    existing = set(subprocess.run(
        ["limactl", "list", "-q"], capture_output=True, text=True
    ).stdout.splitlines())
    missing = [k for k, v in cfg.items() if isinstance(v, dict) and k not in existing]
    if missing:
        print(f"\nconfigured but not created: {', '.join(sorted(missing))} "
              f"(run 'machine up <project>')")
    return 0


def cmd_destroy(args: argparse.Namespace) -> int:
    name = args.project
    if not args.force:
        ans = input(f"Destroy VM '{name}'? [y/N] ")
        if ans != "y":
            print("aborted")
            return 1
    subprocess.run(["limactl", "stop", "-f", name],
                   stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    run(["limactl", "delete", name])
    return 0


def cmd_bake(args: argparse.Namespace) -> int:
    bake(force=args.force)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    if PROJECTS_FILE.exists():
        die(f"{PROJECTS_FILE} already exists")
    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / "projects.toml.example", PROJECTS_FILE)
    print(f"wrote {PROJECTS_FILE} — edit it, then run 'machine up <project>'.")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Minimal preflight: the checks whose failure would otherwise surface
    minutes into a provision."""
    failures = 0

    def check(label: str, ok: bool, hint: str = "") -> None:
        nonlocal failures
        mark = "ok " if ok else "FAIL"
        print(f"[{mark}] {label}" + (f" — {hint}" if (hint and not ok) else ""))
        if not ok:
            failures += 1

    check("limactl on PATH", shutil.which("limactl") is not None,
          "brew install lima")
    agent = subprocess.run(["ssh-add", "-l"], capture_output=True, text=True)
    check("SSH agent has keys", agent.returncode == 0,
          "ssh-add --apple-use-keychain ~/.ssh/id_ed25519 (or MACHINE_USE_1PASSWORD=1)")
    check("git user.name", bool(os.environ.get("GIT_NAME") or git_config("user.name")),
          "git config --global user.name 'Your Name'")
    check("git user.email", bool(os.environ.get("GIT_EMAIL") or git_config("user.email")),
          "git config --global user.email you@example.com")
    try:
        read_signing_key()
        check("SSH signing key resolves", True)
    except SystemExit:
        check("SSH signing key resolves", False,
              "git config --global user.signingkey 'ssh-ed25519 AAAA...'")
    if shutil.which("op") is None:
        print("[note] 'op' CLI not found — `machine secrets` needs it "
              "(brew install 1password-cli)")
    check("projects.toml present", PROJECTS_FILE.is_file(), "machine init")
    if failures:
        die(f"{failures} check(s) failed")
    print("all checks passed")
    return 0


# --- Secrets (1Password → VM tmpfs) ------------------------------------------
def extract_env_id(vm: str, envrc_path: str) -> str:
    body = (
        f"grep -oE 'use[[:space:]]+op_env[[:space:]]+[a-z0-9]+' "
        f"{shlex.quote(envrc_path)} 2>/dev/null | awk '{{print $3}}' | head -1"
    )
    out = lima_shell(vm, ["bash", "-lc", body], capture_output=True, text=True)
    return out.stdout.strip()


def sync_one_env(vm: str, env_id: str, repo: str) -> bool:
    print(f"[secrets] {repo} ({env_id})")
    op_out = subprocess.run(
        ["op", "environment", "read", env_id, "--no-masking"],
        capture_output=True, text=True,
    )
    if op_out.returncode != 0:
        detail = (op_out.stderr or op_out.stdout).strip()
        print(f"  failed: {detail}", file=sys.stderr)
        return False
    body = (
        'set -e\n'
        'dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/dev-secrets"\n'
        'mkdir -p "$dir"; chmod 700 "$dir"\n'
        'cache="$dir/$1.env"\n'
        'cat > "$cache"\n'
        'chmod 600 "$cache"\n'
    )
    subprocess.run(
        ["limactl", "shell", vm, "--", "bash", "-c", body, "bash", env_id],
        input=op_out.stdout, text=True, check=True,
    )
    return True


def cmd_secrets(args: argparse.Namespace) -> int:
    if args.clear:
        return cmd_secrets_clear(args)
    name = args.project
    if not shutil.which("op"):
        die("'op' CLI required (brew install 1password-cli)")
    find_envrcs = subprocess.run(
        ["limactl", "shell", name, "--", "bash", "-lc",
         "find ~/code -mindepth 2 -maxdepth 3 -name .envrc -type f 2>/dev/null"],
        capture_output=True, text=True,
    )
    count = 0
    for path in find_envrcs.stdout.splitlines():
        path = path.strip()
        if not path:
            continue
        repo = Path(path).parent.name
        if args.repo and repo != args.repo:
            continue
        env_id = extract_env_id(name, path)
        if not env_id:
            if args.repo:
                print(f"no 'use op_env <id>' line in {path}", file=sys.stderr)
            continue
        if sync_one_env(name, env_id, repo):
            count += 1
    if count == 0:
        if args.repo:
            print(
                f"no .envrc found for repo '{args.repo}' in VM '{name}' "
                f"(expected ~/code/{args.repo}/.envrc)",
                file=sys.stderr,
            )
        else:
            print(
                f"no repos with 'use op_env' .envrc found under ~/code in VM '{name}'",
                file=sys.stderr,
            )
        return 1
    print(f"synced {count} environment(s)")
    return 0


def cmd_secrets_clear(args: argparse.Namespace) -> int:
    name = args.project
    if not args.repo:
        body = (
            'dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/dev-secrets"\n'
            'if [ -d "$dir" ]; then\n'
            '  find "$dir" -maxdepth 1 -type f -name "*.env" '
            '-exec sh -c \'head -c $(wc -c <"$1") /dev/zero > "$1" 2>/dev/null; '
            'rm -f "$1"\' _ {} \\;\n'
            '  rmdir "$dir" 2>/dev/null || true\n'
            '  echo "[secrets] cleared $dir"\n'
            'else\n'
            '  echo "[secrets] no cache dir on $(hostname)"\n'
            'fi\n'
        )
        run(["limactl", "shell", name, "--", "bash", "-lc", body])
        return 0
    envrc_path = subprocess.run(
        ["limactl", "shell", name, "--", "bash", "-lc",
         f"ls $HOME/code/{shlex.quote(args.repo)}/.envrc 2>/dev/null || true"],
        capture_output=True, text=True,
    ).stdout.strip()
    if not envrc_path:
        die(f"no .envrc for repo '{args.repo}' in VM '{name}'")
    env_id = extract_env_id(name, envrc_path)
    if not env_id:
        die(f"no 'use op_env <id>' line in {envrc_path}")
    body = (
        'dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/dev-secrets"\n'
        'cache="$dir/$1.env"\n'
        'if [ -f "$cache" ]; then\n'
        '  head -c "$(wc -c <"$cache")" /dev/zero > "$cache" 2>/dev/null || true\n'
        '  rm -f "$cache"\n'
        '  echo "[secrets] cleared $cache"\n'
        'else\n'
        '  echo "[secrets] $cache not present"\n'
        'fi\n'
    )
    run(["limactl", "shell", name, "--", "bash", "-c", body, "bash", env_id])
    return 0


# --- Entry point ---------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="machine",
        description="One isolated Lima VM per project.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("up", help="Create (if needed) + start + provision + clone the project repo(s)")
    up.add_argument("project")

    sub.add_parser("down", help="Stop the VM").add_argument("project")
    sub.add_parser("ssh", help="Open an interactive shell (cwd = ~/code/<primary-repo>)").add_argument("project")
    sub.add_parser("claude", help="Open an SSH session and launch `claude`").add_argument("project")

    run_p = sub.add_parser("run", help="Run a non-interactive command in the VM")
    run_p.add_argument("project")
    run_p.add_argument("argv", nargs=argparse.REMAINDER)

    sub.add_parser("list", help="List VMs (limactl list) + configured-but-missing projects")

    destroy = sub.add_parser("destroy", help="Delete the VM (irreversible)")
    destroy.add_argument("project")
    destroy.add_argument("-y", "--force", action="store_true", help="Skip confirmation")

    bake_p = sub.add_parser("bake", help="Build/refresh the cached base image used by 'up'")
    bake_p.add_argument("--force", action="store_true", help="Rebuild even if the cache is fresh")

    sec = sub.add_parser("secrets", help="Render 1Password Environment(s) into VM tmpfs")
    sec.add_argument("project")
    sec.add_argument("--repo", help="Only this repo (default: all repos with `use op_env` .envrc)")
    sec.add_argument("--clear", action="store_true", help="Wipe rendered secrets from VM tmpfs")

    sub.add_parser("init", help="Create projects.toml in MACHINE_CONFIG_DIR (~/.config/machine)")
    sub.add_parser("doctor", help="Preflight: lima, SSH agent, git identity, signing key")
    return ap


COMMANDS = {
    "up": cmd_up,
    "down": cmd_down,
    "ssh": cmd_ssh,
    "claude": cmd_claude,
    "run": cmd_run,
    "list": cmd_list,
    "destroy": cmd_destroy,
    "bake": cmd_bake,
    "secrets": cmd_secrets,
    "init": cmd_init,
    "doctor": cmd_doctor,
}


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    configure_ssh_agent()
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.cmd](args)
    except subprocess.CalledProcessError as e:
        return e.returncode or 1
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

```bash
bash tests/unit.sh
```
Expected: all tests PASS.

- [ ] **Step 5: Sanity-check the CLI end-to-end on the host (no VM)**

```bash
python3 -c "import ast; ast.parse(open('bin/machine').read())"
PROJECTS_FILE=projects.toml.example bin/machine --help
PROJECTS_FILE=projects.toml.example bin/machine list || true   # limactl list runs; missing-projects line prints
```
Expected: help lists exactly `up down ssh claude run list destroy bake secrets init doctor`.

- [ ] **Step 6: Commit**

```bash
git add bin/machine tests/unit/
git commit -m "Rewrite bin/machine around Lima-native templates"
```

---

### Task 6: Delete the legacy provisioning system; update lint, CI, completions

**Files:**
- Delete: `provision/run.py`, `provision/log_view.py`, `provision.toml`, `profiles/` (all 5 TOMLs), `schemas/` (both), `lima.yaml`, `files/git/gitconfig.tpl`, `files/git/allowed_signers.tpl`
- Modify: `.github/workflows/ci.yml`
- Rewrite: `completions/machine.fish`, `completions/machine.bash`, `completions/_machine`

- [ ] **Step 1: Delete legacy files**

```bash
git rm --quiet provision/run.py provision/log_view.py provision.toml lima.yaml
git rm -r --quiet profiles schemas
git rm --quiet files/git/gitconfig.tpl files/git/allowed_signers.tpl
rmdir files/git 2>/dev/null || true
```

- [ ] **Step 2: Update `.github/workflows/ci.yml`** — replace the `Validate example projects.toml` and three `Dry-run provision` steps (everything after the `Unit tests (host-side)` step) with:

```yaml
      - name: Validate Lima templates (YAML syntax)
        run: |
          pip install pyyaml
          python3 - <<'EOF'
          import sys, yaml
          from pathlib import Path
          for f in sorted(Path("templates").glob("*.yaml")):
              yaml.safe_load(f.read_text())
              print(f"ok {f}")
          EOF
```

- [ ] **Step 3: Rewrite `completions/machine.fish`:**

```fish
# fish completion for `machine`.
# Install:  ln -s "$PWD/completions/machine.fish" ~/.config/fish/completions/machine.fish

function __machine_projects
    set -l projects_file (set -q PROJECTS_FILE; and echo $PROJECTS_FILE; or echo (pwd)/projects.toml)
    if test -f $projects_file
        python3 -c "import tomllib, sys
try: cfg = tomllib.loads(open('$projects_file').read())
except: sys.exit()
for n, v in cfg.items():
    if isinstance(v, dict): print(n)" 2>/dev/null
    end
end

set -l cmds up down ssh claude run list destroy bake secrets init doctor

complete -c machine -n "not __fish_seen_subcommand_from $cmds" -a "$cmds"

for c in up down ssh claude run secrets destroy
    complete -c machine -n "__fish_seen_subcommand_from $c" -a '(__machine_projects)'
end

complete -c machine -n "__fish_seen_subcommand_from destroy" -s y -l force -d "Skip confirmation"
complete -c machine -n "__fish_seen_subcommand_from bake" -l force -d "Rebuild even if cache is fresh"
complete -c machine -n "__fish_seen_subcommand_from secrets" -l clear -d "Wipe rendered secrets from VM tmpfs"
complete -c machine -n "__fish_seen_subcommand_from secrets" -l repo -d "Only this repo"
```

- [ ] **Step 4: Rewrite `completions/machine.bash`:**

```bash
# bash completion for `machine`.
# Install:  source completions/machine.bash  (or drop into bash_completion.d)

_machine_projects() {
  local f="${PROJECTS_FILE:-$PWD/projects.toml}"
  [ -f "$f" ] || return 0
  python3 -c "import tomllib, sys
try: cfg = tomllib.loads(open('$f').read())
except Exception: sys.exit()
for n, v in cfg.items():
    if isinstance(v, dict): print(n)" 2>/dev/null
}

_machine() {
  local cur=${COMP_WORDS[COMP_CWORD]}
  local cmds="up down ssh claude run list destroy bake secrets init doctor"
  if [ "$COMP_CWORD" -eq 1 ]; then
    COMPREPLY=($(compgen -W "$cmds" -- "$cur"))
    return
  fi
  case "${COMP_WORDS[1]}" in
    up|down|ssh|claude|run|secrets|destroy)
      COMPREPLY=($(compgen -W "$(_machine_projects)" -- "$cur")) ;;
    bake)
      COMPREPLY=($(compgen -W "--force" -- "$cur")) ;;
  esac
}
complete -F _machine machine
```

- [ ] **Step 5: Rewrite `completions/_machine`:**

```zsh
#compdef machine
# zsh completion for `machine`.

_machine_projects() {
  local f="${PROJECTS_FILE:-$PWD/projects.toml}"
  [[ -f $f ]] || return 0
  python3 -c "import tomllib, sys
try: cfg = tomllib.loads(open('$f').read())
except Exception: sys.exit()
for n, v in cfg.items():
    if isinstance(v, dict): print(n)" 2>/dev/null
}

_machine() {
  local -a cmds
  cmds=(
    'up:Create + start + provision + clone'
    'down:Stop the VM'
    'ssh:Open an interactive shell'
    'claude:Open a shell and launch claude'
    'run:Run a non-interactive command'
    'list:List VMs'
    'destroy:Delete the VM'
    'bake:Build/refresh the cached base image'
    'secrets:Render 1Password environments into VM tmpfs'
    'init:Create projects.toml'
    'doctor:Preflight checks'
  )
  if (( CURRENT == 2 )); then
    _describe 'command' cmds
    return
  fi
  case $words[2] in
    up|down|ssh|claude|run|secrets|destroy)
      compadd -- $(_machine_projects) ;;
    bake) compadd -- --force ;;
    secrets) compadd -- --clear --repo ;;
  esac
}
_machine "$@"
```

- [ ] **Step 6: Verify and commit**

```bash
bash tests/lint.sh && bash tests/unit.sh
PROJECTS_FILE=projects.toml.example bin/machine --help > /dev/null && echo CLI-OK
```
Expected: `lint OK`, unit tests pass, `CLI-OK`. (lint.sh's `find bin provision tests -name '*.sh'` now picks up the four new provision scripts.)

```bash
git add -A
git commit -m "Delete the TOML provisioning DSL; refresh CI and completions"
```

---

### Task 7: Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/TAP.md` (only if it still references run.py/provision.toml)
- Check: `docs/index.html` (update only if it names deleted commands: ps, validate, update, status, config)

- [ ] **Step 1: Update `README.md`:**
  1. Delete the entire `### Desktop app (optional)` section (cask install, ad-hoc signing note).
  2. In the intro paragraph, change "tool profiles (e.g. Cypress, Supabase + flyctl)" wording only if it names deleted profiles (go/rust/python are gone; cypress + supabase-fly remain).
  3. Replace any description of provisioning internals (`provision.toml`, `run.py`, `--json`, `ps`, `validate`, `update`, `rebuild`, `status`, `config add-project`) with the new model. Add this section after Setup:

```markdown
## How it works

`machine up <project>` generates a tiny Lima template in `.build/<project>/lima.yaml`:

​```yaml
base:
- <repo>/templates/base.yaml        # the whole base VM, declaratively
- <repo>/templates/cypress.yaml     # one entry per profile
​```

Lima merges the stack (`base:` composition), boots the VM, and runs the
provisioning declared in the templates: `provision/*.sh` scripts and
`mode: data` dotfiles, applied by cloud-init on **every boot** — so
re-provisioning is just `machine down && machine up`. Your git identity and
signing key flow in as Lima params (`--set`) and render into `~/.gitconfig`
inside the VM. Ports: Lima auto-forwards any listening guest port to
`127.0.0.1` on the host.

To update the toolchain in place: `machine down <p> && machine up <p>`
(provision scripts re-run; apt picks up new versions). To start truly fresh:
`machine destroy <p> && machine up <p>`.

### SSH config

Lima writes a per-VM SSH config at `~/.lima/<project>/ssh.config`. To use
plain `ssh` / IDE remote extensions, add one line to `~/.ssh/config`:

​```
Include ~/.lima/*/ssh.config
​```

Then `ssh lima-<project>` works everywhere.
```

  4. Update the command list/examples to the surviving set: `up down ssh claude run list destroy bake secrets init doctor`.
  5. Keep: Prerequisites, SSH agent / 1Password, secrets, multi-repo, shell selection docs (`shell = "fish"` still works — it's a Lima param now).

- [ ] **Step 2: Sweep remaining references**

```bash
grep -rn "provision.toml\|run\.py\|machine ps\|machine validate\|machine update\|machine rebuild\|machine status\|config add-project\|--json" \
  README.md docs/TAP.md docs/index.html SECURITY.md || echo CLEAN
```
Fix every hit (reword to the new architecture; for `docs/index.html` keep edits minimal — command names and the provisioning description only).

- [ ] **Step 3: Commit**

```bash
git add README.md docs/ SECURITY.md
git commit -m "Document the Lima-native architecture"
```

---

### Task 8: End-to-end verification (real VMs — the integration gate)

**Files:** none (verification only). Requires macOS host with Lima; takes ~20–30 min. **Run steps sequentially; do not parallelize.**

- [ ] **Step 1: Preflight + bake**

```bash
bin/machine doctor
time bin/machine bake --force
```
Expected: doctor all-ok; bake completes, prints `[bake] done — ~/.cache/machine/base-arm64.img`. If `limactl start machine-base` fails on the probe: `limactl shell machine-base sudo tail -100 /var/log/cloud-init-output.log` — fix the provision script and re-run. **Known risk to check here:** if `mode: data` fails to create parent dirs (e.g. `~/.config/fish/`), switch the affected entries to stage under `/opt/machine/files/` and add `install` commands to `provision/base.sh` (mirroring the old approach), then re-bake.

- [ ] **Step 2: Bring up a real project with a profile stack**

Use an existing entry from `projects.toml` that stacks profiles (e.g. `playground` with `["cypress", "supabase-fly"]`), or temporarily add one. Then:

```bash
time bin/machine up playground
```
Expected: create from cached image (fast), probe passes, repos clone. The golden-image disk must be accepted by `limactl create` (Task 2 Step 4 verified merge order; if the boot image is wrong here, fall back to `--set`-based image injection in `render_template`).

- [ ] **Step 3: Run the smoke suite**

```bash
MACHINE_NAME=playground bash tests/run-all.sh
```
Expected: all PASS. Pay attention to `smoke-port-forward.sh` (now relies on Lima auto-forwarding — if it asserts the old fixed ranges, update the test to start a listener on e.g. 5173 and curl `127.0.0.1:5173` from the host after a few seconds' grace) and `smoke-git-sign.sh` (gitconfig now rendered from params).

- [ ] **Step 4: Verify per-boot idempotency + known_hosts preservation**

```bash
bin/machine run playground -- bash -lc 'echo "test-entry" >> ~/.ssh/known_hosts'
bin/machine down playground && time bin/machine up playground
bin/machine run playground -- bash -lc 'grep -c test-entry ~/.ssh/known_hosts'
```
Expected: second `up` is fast (idempotent re-provision), exit 0, and `grep -c` prints `1` (overwrite:false preserved the appended entry).

- [ ] **Step 5: Verify secrets + claude (if 1Password is configured)**

```bash
bin/machine secrets playground || true   # ok if no op_env .envrc — just must not crash
bin/machine run playground -- bash -lic 'claude --version && jq .permissions.defaultMode ~/.claude/settings.json'
```
Expected: claude version prints; defaultMode is `"auto"`.

- [ ] **Step 6: Clean up + commit any fixes**

```bash
bin/machine destroy -y playground   # only if it was a throwaway
git add -A && git commit -m "Fix issues found in end-to-end verification" || echo "nothing to fix"
```

---

## Plan self-review notes

- **Spec coverage:** GUI removal (T1), base template + params + data files (T2), provision bash (T3), profiles (T4), CLI rewrite incl. doctor/secrets/bake/list (T5), legacy deletion + CI + completions (T6), docs incl. ssh-config Include replacement (T7), risks from spec "open verifications" (T2 S3–4, T8 S1–4). `machine init` kept (T5). Formula untouched (help-text test still passes: "machine", "init").
- **Known deviation:** managed `~/.ssh/config` block deleted in favor of a documented `Include` line (flagged in header).
- **Type consistency:** `render_template(name, profiles, *, golden, golden_image=None)` matches tests; `param_set_args(dict)` matches tests; `resolve_params` only used in `cmd_up`.
