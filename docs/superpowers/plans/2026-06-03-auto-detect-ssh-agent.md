# Auto-detect SSH Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drop the `MACHINE_USE_1PASSWORD` flag — `machine` forwards 1Password's SSH agent automatically when its socket exists, otherwise the macOS Keychain agent.

**Architecture:** `configure_ssh_agent()` in `bin/machine` becomes a pure auto-detect: if the 1Password agent socket (path from `ONEPASS_SOCK` or the well-known default) is a live unix socket, point `SSH_AUTH_SOCK` at it; otherwise leave the environment untouched. The flag is removed from code, doctor hints, and docs. `close_lima_ssh_master()` behavior is unchanged (its docstring is updated).

**Tech Stack:** Python 3 (single-file CLI `bin/machine`), `unittest` (run via `./tests/unit.sh`), Markdown/HTML docs.

**Spec:** `docs/superpowers/specs/2026-06-03-auto-detect-ssh-agent-design.md`

---

### Task 1: Auto-detect in `configure_ssh_agent()` (TDD)

**Files:**
- Modify: `bin/machine:78-88` (`configure_ssh_agent`)
- Test: `tests/unit/test_machine.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_machine.py`. Add `import socket` and `from unittest import mock` to the imports at the top of the file:

```python
import socket
from unittest import mock
```

Then add these test methods inside `class TestHelpers`:

```python
    def test_configure_ssh_agent_uses_1password_socket_when_present(self):
        sock_path = Path(self.tmp.name) / "agent.sock"
        srv = socket.socket(socket.AF_UNIX)
        self.addCleanup(srv.close)
        srv.bind(str(sock_path))
        with mock.patch.dict(os.environ, {
            "ONEPASS_SOCK": str(sock_path),
            "SSH_AUTH_SOCK": "/orig/agent.sock",
        }):
            self.m.configure_ssh_agent()
            self.assertEqual(os.environ["SSH_AUTH_SOCK"], str(sock_path))

    def test_configure_ssh_agent_keeps_default_when_socket_missing(self):
        with mock.patch.dict(os.environ, {
            "ONEPASS_SOCK": str(Path(self.tmp.name) / "nope.sock"),
            "SSH_AUTH_SOCK": "/orig/agent.sock",
        }):
            self.m.configure_ssh_agent()
            self.assertEqual(os.environ["SSH_AUTH_SOCK"], "/orig/agent.sock")

    def test_configure_ssh_agent_ignores_non_socket_path(self):
        not_a_socket = Path(self.tmp.name) / "plain-file"
        not_a_socket.write_text("")
        with mock.patch.dict(os.environ, {
            "ONEPASS_SOCK": str(not_a_socket),
            "SSH_AUTH_SOCK": "/orig/agent.sock",
        }):
            self.m.configure_ssh_agent()
            self.assertEqual(os.environ["SSH_AUTH_SOCK"], "/orig/agent.sock")
```

Notes for the implementer:
- `mock.patch.dict(os.environ, ...)` restores the environment after the
  `with` block — required because `configure_ssh_agent` mutates `os.environ`
  and other tests in this class read it.
- A real `AF_UNIX` socket is bound in the temp dir so `Path.is_socket()` is
  exercised for real. macOS caps unix socket paths at ~104 bytes;
  `tempfile.TemporaryDirectory()` paths are well under that.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./tests/unit.sh`
Expected: the first test FAILS. With the current code, `MACHINE_USE_1PASSWORD` is unset so `configure_ssh_agent()` returns early and `SSH_AUTH_SOCK` stays `/orig/agent.sock` — the assertion `assertEqual(..., str(sock_path))` fails. The other two tests pass already (early return) — that's expected; they pin the fallback behavior so it survives the rewrite.

- [ ] **Step 3: Rewrite `configure_ssh_agent`**

In `bin/machine`, replace the whole function (currently lines 78–88):

```python
def configure_ssh_agent() -> None:
    """Pick the SSH agent to forward into the VM. If the 1Password agent
    socket exists (path from ONEPASS_SOCK, default the well-known app
    location), prefer it; otherwise leave SSH_AUTH_SOCK alone so the macOS
    Keychain agent is forwarded. ONEPASS_SOCK pointed at a non-socket path
    (e.g. /dev/null) forces the Keychain fallback."""
    sock = Path(os.environ.get("ONEPASS_SOCK") or ONEPASS_SOCK_DEFAULT)
    if sock.is_socket():
        os.environ["SSH_AUTH_SOCK"] = str(sock)
```

The `die(...)` for a missing socket is deleted — a missing socket is now the normal Keychain case, not an error.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./tests/unit.sh`
Expected: all tests PASS (8 pre-existing + 3 new = 11).

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_machine.py bin/machine
git commit -m "Auto-detect the 1Password SSH agent socket"
```

---

### Task 2: Remove the flag from doctor hint and mux docstring

**Files:**
- Modify: `bin/machine:177` (`close_lima_ssh_master` docstring)
- Modify: `bin/machine:609` (doctor hint)

- [ ] **Step 1: Update the `close_lima_ssh_master` docstring**

In `bin/machine`, the docstring currently reads (around lines 170–178):

```python
    Lima's ssh.config sets `ControlMaster auto` + `ControlPersist yes`, so the
    first `limactl shell` spawns a mux process that subsequent shells reuse.
    Agent forwarding is fixed at the moment the master is created — if the
    host's SSH_AUTH_SOCK changes between runs (e.g. toggling
    MACHINE_USE_1PASSWORD), the mux keeps forwarding the *old* agent. Closing
    the mux forces a fresh master that picks up the current SSH_AUTH_SOCK."""
```

Replace the parenthetical so it describes the auto-detect world:

```python
    Lima's ssh.config sets `ControlMaster auto` + `ControlPersist yes`, so the
    first `limactl shell` spawns a mux process that subsequent shells reuse.
    Agent forwarding is fixed at the moment the master is created — if the
    host's SSH_AUTH_SOCK changes between runs (e.g. the 1Password agent
    appearing or going away), the mux keeps forwarding the *old* agent.
    Closing the mux forces a fresh master that picks up the current
    SSH_AUTH_SOCK."""
```

No behavior change — comment only.

- [ ] **Step 2: Update the doctor hint**

In `bin/machine` (around line 607–609), change:

```python
    agent = subprocess.run(["ssh-add", "-l"], capture_output=True, text=True)
    check("SSH agent has keys", agent.returncode == 0,
          "ssh-add --apple-use-keychain ~/.ssh/id_ed25519 (or MACHINE_USE_1PASSWORD=1)")
```

to:

```python
    agent = subprocess.run(["ssh-add", "-l"], capture_output=True, text=True)
    check("SSH agent has keys", agent.returncode == 0,
          "ssh-add --apple-use-keychain ~/.ssh/id_ed25519, "
          "or enable 1Password's SSH agent")
```

- [ ] **Step 3: Verify no stale references and tests still pass**

Run: `grep -rn MACHINE_USE_1PASSWORD bin/ tests/ provision/ scripts/ templates/ files/`
Expected: no output.

Run: `./tests/unit.sh`
Expected: all 11 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add bin/machine
git commit -m "Drop MACHINE_USE_1PASSWORD from doctor hint and mux docstring"
```

---

### Task 3: Update README.md

**Files:**
- Modify: `README.md:32` (Prerequisites bullet)
- Modify: `README.md:~255-264` (SSH agent section)
- Modify: `README.md:~305` (Override knobs table)

- [ ] **Step 1: Prerequisites bullet**

Change line 32 from:

```markdown
  - **1Password**: enable 1Password → Settings → Developer → *Use the SSH agent*, then run `machine` with `MACHINE_USE_1PASSWORD=1` (see [SSH agent](#ssh-agent) below).
```

to:

```markdown
  - **1Password**: enable 1Password → Settings → Developer → *Use the SSH agent* — `machine` detects the agent socket and forwards it automatically (see [SSH agent](#ssh-agent) below).
```

- [ ] **Step 2: SSH agent section**

The section currently reads:

````markdown
By default the VM forwards whatever the host's `SSH_AUTH_SOCK` points at — on macOS that's launchd's agent, which serves keys you loaded with `ssh-add --apple-use-keychain` (passphrase cached in Keychain).

To use 1Password's agent instead — keys never touch `~/.ssh`, every signature prompts for Touch ID:

```sh
brew install 1password-cli                    # only needed for OP_SIGNING_KEY_REF
# In 1Password: Settings → Developer → "Use the SSH agent"
export MACHINE_USE_1PASSWORD=1                # for the current shell, or your shell rc
machine up <project>
```
````

Replace with:

```markdown
`machine` picks the agent to forward automatically: if 1Password's SSH agent socket exists (Settings → Developer → *Use the SSH agent*), it forwards that — keys never touch `~/.ssh`, every signature prompts for Touch ID. Otherwise it forwards whatever the host's `SSH_AUTH_SOCK` points at — on macOS that's launchd's agent, which serves keys you loaded with `ssh-add --apple-use-keychain` (passphrase cached in Keychain).

To force the Keychain agent while 1Password's agent is enabled, point `ONEPASS_SOCK` at a non-socket path (e.g. `ONEPASS_SOCK=/dev/null machine up <project>`).
```

(The `brew install 1password-cli` line moves nowhere — it was only needed for `OP_SIGNING_KEY_REF`, which is already documented in the signing-pubkey list right below. Delete the whole code block.)

- [ ] **Step 3: Override knobs table**

Delete the row:

```markdown
| `MACHINE_USE_1PASSWORD` | set `=1` to forward 1Password's SSH agent instead of macOS Keychain |
```

and update the `ONEPASS_SOCK` row's description so the table explains what it does, not just the default:

```markdown
| `ONEPASS_SOCK` | 1Password agent socket path (default `~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock`); auto-forwarded when it exists |
```

- [ ] **Step 4: Verify**

Run: `grep -n MACHINE_USE_1PASSWORD README.md`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "Document automatic SSH agent detection in README"
```

---

### Task 4: Update docs/docs/index.html

**Files:**
- Modify: `docs/docs/index.html:103` (prerequisites bullet)
- Modify: `docs/docs/index.html:~222-228` (SSH agent section)
- Modify: `docs/docs/index.html:~295` (env var table)

- [ ] **Step 1: Prerequisites bullet (line 103)**

Change:

```html
          <li>An SSH key on the host, served by an agent the VM can forward. Either the <strong>macOS Keychain</strong> (default — <code>ssh-add --apple-use-keychain ~/.ssh/id_ed25519</code>) or <strong>1Password</strong> (Settings → Developer → <em>Use the SSH agent</em>, then run with <code>MACHINE_USE_1PASSWORD=1</code>).</li>
```

to:

```html
          <li>An SSH key on the host, served by an agent the VM can forward. Either the <strong>macOS Keychain</strong> (<code>ssh-add --apple-use-keychain ~/.ssh/id_ed25519</code>) or <strong>1Password</strong> (Settings → Developer → <em>Use the SSH agent</em> — detected and forwarded automatically).</li>
```

- [ ] **Step 2: SSH agent section (§09, around lines 222–228)**

Current:

```html
        <p>By default the VM forwards whatever the host's <code>SSH_AUTH_SOCK</code> points at — on macOS that's launchd's agent, which serves keys you loaded with <code>ssh-add --apple-use-keychain</code> (passphrase cached in Keychain).</p>
        <p>To use 1Password's agent instead — keys never touch <code>~/.ssh</code>, every signature prompts for Touch ID:</p>
        <pre><div class="head"><span class="dot"></span><span class="dot"></span><span class="dot"></span><span>shell</span></div><code><span class="prompt">$ </span>brew install 1password-cli                    <span class="cmt"># only needed for OP_SIGNING_KEY_REF</span>
<span class="cmt"># In 1Password: Settings → Developer → "Use the SSH agent"</span>
<span class="prompt">$ </span><span class="kw">export</span> MACHINE_USE_1PASSWORD=<span class="str">1</span>                <span class="cmt"># for the current shell, or your shell rc</span>
<span class="prompt">$ </span>machine up &lt;project&gt;</code></pre>
```

Replace with:

```html
        <p><code>machine</code> picks the agent to forward automatically: if 1Password's SSH agent socket exists (Settings → Developer → <em>Use the SSH agent</em>), it forwards that — keys never touch <code>~/.ssh</code>, every signature prompts for Touch ID. Otherwise it forwards whatever the host's <code>SSH_AUTH_SOCK</code> points at — on macOS that's launchd's agent, which serves keys you loaded with <code>ssh-add --apple-use-keychain</code> (passphrase cached in Keychain).</p>
        <p>To force the Keychain agent while 1Password's agent is enabled, point <code>ONEPASS_SOCK</code> at a non-socket path (e.g. <code>ONEPASS_SOCK=/dev/null machine up &lt;project&gt;</code>).</p>
```

- [ ] **Step 3: Env var table (around line 295)**

Delete the row:

```html
              <tr><td>MACHINE_USE_1PASSWORD</td><td class="desc">Set <code>=1</code> to forward 1Password's SSH agent instead of macOS Keychain.</td></tr>
```

and update the `ONEPASS_SOCK` row:

```html
              <tr><td>ONEPASS_SOCK</td><td class="desc">1Password agent socket path (default <code>~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock</code>); auto-forwarded when it exists.</td></tr>
```

- [ ] **Step 4: Verify**

Run: `grep -rn MACHINE_USE_1PASSWORD . --include='*.md' --include='*.html' --exclude-dir=superpowers`
Expected: no output. (`docs/superpowers/` plans/specs are historical records — leave them.)

Run: `./tests/unit.sh`
Expected: all 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/docs/index.html
git commit -m "Document automatic SSH agent detection on the docs page"
```

---

## Manual verification (after all tasks)

On the host, with 1Password's SSH agent enabled:

```sh
machine up <project>
machine ssh <project> -- ssh-add -l   # expect 1Password keys
```

Quit 1Password, then:

```sh
machine up <project>
machine ssh <project> -- ssh-add -l   # expect Keychain keys
```

`machine doctor` should pass in both states.
