# Zero-Config Default VM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `machine up` works with no `projects.toml` — bare `machine up` launches a base VM named `default`, and `machine up <unknown-name>` offers to create an ad-hoc base VM after a confirm prompt.

**Architecture:** All changes live in the single-file CLI `bin/machine`. `load_projects()` stops dying on a missing config; a new `resolve_up_target(cfg, name)` helper computes `(urls, profiles)` for `cmd_up`, gating ad-hoc creation behind a y/N prompt (skipped for the name `default` and for VMs that already exist — re-running `up` on an existing ad-hoc VM must stay non-interactive). The `project` positional defaults to `"default"` on every command except `run`.

**Tech Stack:** Python 3 stdlib (`argparse`, `tomllib`), `unittest` for host-side tests (no VM needed).

**Spec:** `docs/superpowers/specs/2026-06-02-zero-config-default-vm-design.md`

**Conventions for this repo:**
- Commit messages: imperative sentence case, no `feat:`-style prefixes (match `git log`).
- Commit with `--no-gpg-sign` (1Password-backed signing fails non-interactively).
- Run tests with `tests/unit.sh` from the repo root. Run `tests/lint.sh` before each commit.
- `bin/machine` has no `.py` suffix; tests import it via the `load_machine()` helper already in `tests/unit/test_machine.py`, which honors the `PROJECTS_FILE` env var.

**Out of scope (decided in the spec):**
- No writes to `projects.toml`, ever.
- `completions/` need **no changes** — all three scripts complete project names dynamically from the TOML file, they don't enumerate positionals statically.
- `cmd_list` needs **no code change** — it works once Task 1 makes `load_projects()` return `{}` (its `cfg.items()` loop just produces nothing).
- `cmd_secrets` keeps its hard error for unknown projects via `get_project()`.

---

### Task 1: `load_projects()` returns `{}` when the config file is missing

**Files:**
- Modify: `bin/machine:92-98` (`load_projects`)
- Test: `tests/unit/test_machine.py`

- [ ] **Step 1: Write the failing test**

Add a new test class at the end of `tests/unit/test_machine.py`. It points `PROJECTS_FILE` at a path that does not exist:

```python
class TestZeroConfig(unittest.TestCase):
    """Behavior with no projects.toml at all (zero-config mode)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = load_machine({
            "PROJECTS_FILE": str(Path(self.tmp.name) / "projects.toml"),
            "MACHINE_STATE_DIR": str(Path(self.tmp.name) / "state"),
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_projects_missing_file_returns_empty(self):
        self.assertEqual(self.m.load_projects(), {})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `tests/unit.sh 2>&1 | tail -5`
Expected: `test_load_projects_missing_file_returns_empty` FAILs with `SystemExit: 1` (the current `die()` call).

- [ ] **Step 3: Implement**

In `bin/machine`, replace the body of `load_projects()` (currently lines 92-98):

```python
def load_projects() -> dict[str, Any]:
    if not PROJECTS_FILE.is_file():
        return {}
    return tomllib.loads(PROJECTS_FILE.read_text())
```

(The "run `machine init`" hint moves nowhere: unknown-project errors still come from `get_project()`, whose message includes the `PROJECTS_FILE` path.)

- [ ] **Step 4: Run the full suite to verify it passes**

Run: `tests/unit.sh 2>&1 | tail -5`
Expected: all tests PASS (`OK`).

- [ ] **Step 5: Lint and commit**

```bash
tests/lint.sh
git add bin/machine tests/unit/test_machine.py
git commit --no-gpg-sign -m "Return empty config when projects.toml is missing"
```

---

### Task 2: `default_profiles()` helper, reused by `project_profiles()`

**Files:**
- Modify: `bin/machine:112-119` (`project_profiles`)
- Test: `tests/unit/test_machine.py`

- [ ] **Step 1: Write the failing test**

Add to the `TestHelpers` class (the one whose `setUp` writes a populated `projects.toml`):

```python
    def test_default_profiles(self):
        self.assertEqual(self.m.default_profiles({}), [])
        self.assertEqual(
            self.m.default_profiles({"default_profile": "cypress"}), ["cypress"])
        self.assertEqual(self.m.default_profiles({"default_profile": ""}), [])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `tests/unit.sh 2>&1 | tail -5`
Expected: FAIL with `AttributeError: ... has no attribute 'default_profiles'`.

- [ ] **Step 3: Implement**

In `bin/machine`, add `default_profiles` directly above `project_profiles` and refactor `project_profiles` to use it (replacing lines 112-119):

```python
def default_profiles(cfg: dict[str, Any]) -> list[str]:
    """Top-level `default_profile` as a profile list ([] if unset/empty)."""
    default = cfg.get("default_profile")
    return [default] if default else []


def project_profiles(name: str) -> list[str]:
    cfg = load_projects()
    profiles = get_project(cfg, name).get("profiles")
    if profiles is None:
        profiles = default_profiles(cfg)
    return [p for p in profiles if p]
```

- [ ] **Step 4: Run the full suite to verify it passes**

Run: `tests/unit.sh 2>&1 | tail -5`
Expected: all tests PASS, including the pre-existing `test_project_profiles_default_and_explicit` (the refactor must not change behavior).

- [ ] **Step 5: Lint and commit**

```bash
tests/lint.sh
git add bin/machine tests/unit/test_machine.py
git commit --no-gpg-sign -m "Extract default_profiles helper from project_profiles"
```

---

### Task 3: `resolve_up_target()` with confirm prompt; rewire `cmd_up`

**Files:**
- Modify: `bin/machine` (new helpers above `cmd_up`; `cmd_up` lines 450-456)
- Test: `tests/unit/test_machine.py`

- [ ] **Step 1: Write the failing tests**

Add `from unittest import mock` to the imports at the top of `tests/unit/test_machine.py` (after `import unittest`).

Add to `TestHelpers` (config file exists, has `[blog]` with repos and `default_profile = "cypress"`):

```python
    def test_resolve_up_known_project(self):
        urls, profiles = self.m.resolve_up_target(self.m.load_projects(), "blog")
        self.assertEqual(urls, ["git@github.com:me/blog.git"])
        self.assertEqual(profiles, ["cypress"])
```

Add to `TestZeroConfig` (no config file):

```python
    def test_resolve_up_default_never_prompts(self):
        with mock.patch.object(self.m, "vm_exists", return_value=False), \
             mock.patch("builtins.input", side_effect=AssertionError("prompted")):
            urls, profiles = self.m.resolve_up_target({}, "default")
        self.assertEqual((urls, profiles), ([], []))

    def test_resolve_up_unknown_name_accepted(self):
        with mock.patch.object(self.m, "vm_exists", return_value=False), \
             mock.patch("builtins.input", return_value="y"):
            urls, profiles = self.m.resolve_up_target({}, "scratch")
        self.assertEqual((urls, profiles), ([], []))

    def test_resolve_up_unknown_name_declined(self):
        with mock.patch.object(self.m, "vm_exists", return_value=False), \
             mock.patch("builtins.input", return_value=""):
            with self.assertRaises(SystemExit):
                self.m.resolve_up_target({}, "scratch")

    def test_resolve_up_unknown_name_eof_aborts(self):
        with mock.patch.object(self.m, "vm_exists", return_value=False), \
             mock.patch("builtins.input", side_effect=EOFError):
            with self.assertRaises(SystemExit):
                self.m.resolve_up_target({}, "scratch")

    def test_resolve_up_existing_vm_skips_prompt(self):
        with mock.patch.object(self.m, "vm_exists", return_value=True), \
             mock.patch("builtins.input", side_effect=AssertionError("prompted")):
            urls, profiles = self.m.resolve_up_target({}, "scratch")
        self.assertEqual((urls, profiles), ([], []))

    def test_resolve_up_ad_hoc_honors_default_profile(self):
        urls, profiles = self.m.resolve_up_target(
            {"default_profile": "cypress"}, "default")
        self.assertEqual((urls, profiles), ([], ["cypress"]))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `tests/unit.sh 2>&1 | tail -5`
Expected: the new tests FAIL with `AttributeError: ... has no attribute 'resolve_up_target'`.

- [ ] **Step 3: Implement**

In `bin/machine`, add the two helpers directly above `def cmd_up` (after the `# --- Commands ---` divider is fine too, as long as they precede `cmd_up`):

```python
def confirm_create(name: str) -> None:
    """Gate ad-hoc VM creation behind a y/N prompt (typo safety)."""
    try:
        ans = input(f"No project '{name}' in {PROJECTS_FILE} — create a base VM? [y/N] ")
    except EOFError:
        ans = ""
    if ans != "y":
        die("aborted")


def resolve_up_target(cfg: dict[str, Any], name: str) -> tuple[list[str], list[str]]:
    """(urls, profiles) for `machine up`.

    Names not in the config become ad-hoc base VMs: no repos, profiles from
    `default_profile`. Creation is confirmed first, except for the implicit
    'default' VM and VMs that already exist (re-`up` stays non-interactive).
    """
    if isinstance(cfg.get(name), dict):
        return project_urls(name), project_profiles(name)
    if name != "default" and not vm_exists(name):
        confirm_create(name)
    return [], default_profiles(cfg)
```

Then replace the top of `cmd_up` (currently lines 450-456):

```python
def cmd_up(args: argparse.Namespace) -> int:
    name = args.project
    validate_name(name)
    urls, profiles = resolve_up_target(load_projects(), name)
    close_lima_ssh_master(name)
    verify_repos_reachable(urls)
```

The rest of `cmd_up` is unchanged — `verify_repos_reachable([])` and the clone loop are no-ops on empty lists.

- [ ] **Step 4: Run the full suite to verify it passes**

Run: `tests/unit.sh 2>&1 | tail -5`
Expected: all tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
tests/lint.sh
git add bin/machine tests/unit/test_machine.py
git commit --no-gpg-sign -m "Let machine up create config-less base VMs"
```

---

### Task 4: `project` positional defaults to `"default"` (except `run`)

**Files:**
- Modify: `bin/machine:751-786` (`build_parser`)
- Test: `tests/unit/test_machine.py`

- [ ] **Step 1: Write the failing tests**

Add to `TestZeroConfig`:

```python
    def test_parser_defaults_project_to_default(self):
        ap = self.m.build_parser()
        for cmd in ("up", "down", "ssh", "claude", "destroy", "secrets"):
            self.assertEqual(ap.parse_args([cmd]).project, "default", cmd)
        self.assertEqual(ap.parse_args(["up", "blog"]).project, "blog")

    def test_parser_run_still_requires_project(self):
        with self.assertRaises(SystemExit):
            self.m.build_parser().parse_args(["run"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `tests/unit.sh 2>&1 | tail -5`
Expected: `test_parser_defaults_project_to_default` FAILs with `SystemExit: 2` (argparse: required argument missing). `test_parser_run_still_requires_project` already passes — that is fine; it pins current behavior.

- [ ] **Step 3: Implement**

In `build_parser()`, change every `add_argument("project")` EXCEPT `run`'s to `add_argument("project", nargs="?", default="default")`, and extend `up`'s help text:

```python
    up = sub.add_parser("up", help="Create (if needed) + start + provision + clone the project repo(s). "
                                   "With no name, launches a config-less base VM called 'default'.")
    up.add_argument("project", nargs="?", default="default")

    sub.add_parser("down", help="Stop the VM").add_argument("project", nargs="?", default="default")
    sub.add_parser("ssh", help="Open an interactive shell (cwd = ~/code/<primary-repo>)").add_argument("project", nargs="?", default="default")
    sub.add_parser("claude", help="Open an SSH session and launch `claude`").add_argument("project", nargs="?", default="default")
```

`run_p.add_argument("project")` stays as-is (the trailing `argv` remainder makes an optional project ambiguous). Also update:

```python
    destroy.add_argument("project", nargs="?", default="default")
```

and

```python
    sec.add_argument("project", nargs="?", default="default")
```

- [ ] **Step 4: Run the full suite to verify it passes**

Run: `tests/unit.sh 2>&1 | tail -5`
Expected: all tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
tests/lint.sh
git add bin/machine tests/unit/test_machine.py
git commit --no-gpg-sign -m "Default the project argument to 'default'"
```

---

### Task 5: Docs — README and site

**Files:**
- Modify: `README.md` (Setup ~line 38, Quickstart ~line 106, command table ~line 140)
- Modify: `docs/docs/index.html` (Setup shell block ~line 112, Quickstart ~line 143, command table ~line 161)

- [ ] **Step 1: Update README.md**

In the **Setup** section (~line 38), reframe the config as optional. Replace:

```markdown
## Setup

```sh
machine init                  # writes ~/.config/machine/projects.toml from the bundled example
$EDITOR ~/.config/machine/projects.toml
```
```

with:

```markdown
## Setup

No setup needed for a scratch VM — `machine up` launches a base VM named
`default` out of the box (and `machine up <name>` offers to create an empty
VM under any name). Add a config when you want repos cloned or profiles:

```sh
machine init                  # writes ~/.config/machine/projects.toml from the bundled example
$EDITOR ~/.config/machine/projects.toml
```
```

In **Quickstart** (~line 106), add the zero-config line first. Replace:

```markdown
```sh
machine up blog            # creates + starts + provisions VM "blog", clones the repo
machine ssh blog           # interactive shell, cwd = ~/code/blog
```
```

with:

```markdown
```sh
machine up                 # zero-config: creates + starts a base VM named "default"
machine up blog            # creates + starts + provisions VM "blog", clones the repo
machine ssh blog           # interactive shell, cwd = ~/code/blog
```
```

In the command table (~line 140), replace the `machine up <p>` row:

```markdown
| `machine up [p]` | Create if needed, start, provision, clone the repo(s). Idempotent — re-running re-applies the provision scripts. No name → base VM `default`; unknown names offer an ad-hoc base VM. |
```

- [ ] **Step 2: Update docs/docs/index.html**

Same three edits in HTML form:

In the Setup `<pre>` block (~line 112), prepend a paragraph before the `<pre>`:

```html
<p>No setup needed for a scratch VM — <code>machine up</code> launches a base VM named <code>default</code> out of the box. Add a config when you want repos cloned or profiles:</p>
```

In the Quickstart `<pre>` block (~line 143), add before the `machine up blog` line:

```html
<span class="prompt">$ </span>machine up                 <span class="cmt"># zero-config: create + start a base VM named "default"</span>
```

In the command table (~line 161), replace the `machine up &lt;p&gt;` row description:

```html
<tr><td>machine up [p]</td><td class="desc">Create if needed, start, provision (base + profiles), clone the repo(s). Idempotent. No name → base VM <code>default</code>; unknown names offer an ad-hoc base VM.</td></tr>
```

- [ ] **Step 3: Verify**

Run: `tests/unit.sh 2>&1 | tail -3` (docs only, but confirm nothing broke)
Expected: `OK`.

Visually skim the diff: `git diff README.md docs/docs/index.html`

- [ ] **Step 4: Commit**

```bash
git add README.md docs/docs/index.html
git commit --no-gpg-sign -m "Document the zero-config default VM"
```

---

## Final verification (after all tasks)

- [ ] `tests/unit.sh` — full suite green
- [ ] `tests/lint.sh` — clean
- [ ] Manual smoke (optional, needs Lima): `machine up` with `PROJECTS_FILE` pointed at a nonexistent path boots a base VM named `default`; `machine up scratch` prompts; answering `n` aborts.
