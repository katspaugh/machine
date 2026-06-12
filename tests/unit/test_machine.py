"""Unit tests for the host-side helpers in bin/machine. No VM required."""
import argparse
import contextlib
import importlib.util
import io
import os
import socket
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def load_machine(extra_env: dict[str, str] | None = None):
    """Import bin/machine fresh with a controlled environment."""
    for key, value in (extra_env or {}).items():
        os.environ[key] = value
    # bin/machine has no .py suffix, so spec_from_file_location can't infer a
    # loader; build one explicitly via SourceFileLoader.
    loader = SourceFileLoader("machine_cli", str(ROOT / "bin" / "machine"))
    spec = importlib.util.spec_from_loader("machine_cli", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def proc(rc: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    """A fake CompletedProcess for mocked run()/lima_shell() calls."""
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


class _MachineTestCase(unittest.TestCase):
    """Loads bin/machine fresh against a temp projects.toml."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        projects = Path(self.tmp.name) / "projects.toml"
        projects.write_text(
            'default_profile = "cypress"\n'
            "[blog]\n"
            'repos = ["git@github.com:me/blog.git"]\n'
            "[wallet]\n"
            'profiles = ["cypress", "supabase-fly"]\n'
            'shell = "bash"\n'
            'repos = ["git@github.com:me/a.git", "git@github.com:me/b.git"]\n'
            "[bare]\n"
            "profiles = []\n"
            'repos = []\n'
            "[locked]\n"
            "forward_agent = false\n"
            'repos = ["git@github.com:me/locked.git"]\n'
            "[big]\n"
            "repos = []\n"
            "cpus = 8\n"
            'memory = "16GiB"\n'
            'disk = "60GiB"\n'
        )
        self.m = load_machine({
            "PROJECTS_FILE": str(projects),
            "MACHINE_STATE_DIR": str(Path(self.tmp.name) / "state"),
        })

    def tearDown(self):
        self.tmp.cleanup()


class TestHelpers(_MachineTestCase):
    def test_repo_basename(self):
        self.assertEqual(self.m.repo_basename("git@github.com:me/blog.git"), "blog")
        self.assertEqual(self.m.repo_basename("https://github.com/me/x"), "x")

    def test_validate_name_rejects_bad(self):
        with self.assertRaises(SystemExit):
            self.m.validate_name("Bad_Name")
        self.m.validate_name("ok-name-2")  # no raise

    def test_default_profiles(self):
        self.assertEqual(self.m.default_profiles({}), [])
        self.assertEqual(
            self.m.default_profiles({"default_profile": "cypress"}), ["cypress"])
        self.assertEqual(self.m.default_profiles({"default_profile": ""}), [])

    def test_project_profiles_default_and_explicit(self):
        self.assertEqual(self.m.project_profiles("blog"), ["cypress"])
        self.assertEqual(self.m.project_profiles("wallet"), ["cypress", "supabase-fly"])
        self.assertEqual(self.m.project_profiles("bare"), [])

    def test_project_shell(self):
        self.assertEqual(self.m.project_shell("blog"), "zsh")
        self.assertEqual(self.m.project_shell("wallet"), "bash")

    def test_param_set_args_quotes_values(self):
        args = self.m.param_set_args(
            {"gitName": 'Ivan "K"', "shell": "zsh"})
        self.assertEqual(args[0], "--set")
        self.assertIn('.param.gitName = "Ivan \\"K\\""', args[1])
        self.assertIn('.param.shell = "zsh"', args[3])

    def test_render_template_without_golden(self):
        out = self.m.render_template("wallet", ["cypress", "supabase-fly"], golden=False)
        text = out.read_text()
        self.assertIn("base:", text)
        self.assertNotIn("file://", text)
        # Lima prepends each successively merged base, so profiles are listed
        # reversed and base.yaml last → base.sh executes first.
        entries = [line for line in text.splitlines() if line.startswith("- ")]
        self.assertTrue(entries[0].endswith("templates/supabase-fly.yaml"))
        self.assertTrue(entries[1].endswith("templates/cypress.yaml"))
        self.assertTrue(entries[2].endswith("templates/base.yaml"))

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

    def test_configure_ssh_agent_warns_about_removed_flag(self):
        import io
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, {
            "MACHINE_USE_1PASSWORD": "1",
            "ONEPASS_SOCK": str(Path(self.tmp.name) / "nope.sock"),
            "SSH_AUTH_SOCK": "/orig/agent.sock",
        }), mock.patch("sys.stderr", stderr):
            self.m.configure_ssh_agent()
        self.assertIn("MACHINE_USE_1PASSWORD", stderr.getvalue())

    def test_project_forward_agent_defaults_true(self):
        self.assertTrue(self.m.project_forward_agent("blog"))

    def test_project_forward_agent_explicit_false(self):
        self.assertFalse(self.m.project_forward_agent("locked"))

    def test_project_forward_agent_unknown_project_true(self):
        self.assertTrue(self.m.project_forward_agent("no-such-project"))

    def test_render_template_forward_agent_false_overrides_base(self):
        out = self.m.render_template("locked", [], golden=False,
                                     forward_agent=False)
        text = out.read_text()
        self.assertIn("ssh:", text)
        self.assertIn("forwardAgent: false", text)
        # the override must precede the base: stack so it wins the merge
        self.assertLess(text.index("ssh:"), text.index("base:"))

    def test_render_template_default_keeps_base_forwarding(self):
        out = self.m.render_template("blog", [], golden=False)
        self.assertNotIn("forwardAgent", out.read_text())

    def test_resolve_up_known_project(self):
        urls, profiles = self.m.resolve_up_target(self.m.load_projects(), "blog")
        self.assertEqual(urls, ["git@github.com:me/blog.git"])
        self.assertEqual(profiles, ["cypress"])


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

    def test_resolve_up_target_never_prompts(self):
        # Unknown names are routed through the create wizard *before*
        # resolve_up_target; by the time it runs, an entry-less name is an
        # ad-hoc base VM ('default', pre-existing VMs) — no interaction.
        with mock.patch("builtins.input", side_effect=AssertionError("prompted")):
            self.assertEqual(self.m.resolve_up_target({}, "default"), ([], []))
            self.assertEqual(self.m.resolve_up_target({}, "scratch"), ([], []))

    def test_resolve_up_ad_hoc_honors_default_profile(self):
        urls, profiles = self.m.resolve_up_target(
            {"default_profile": "cypress"}, "default")
        self.assertEqual((urls, profiles), ([], ["cypress"]))

    def test_parser_defaults_project_to_default(self):
        ap = self.m.build_parser()
        for cmd in ("down", "ssh", "claude", "destroy", "secrets"):
            self.assertEqual(ap.parse_args([cmd]).project, "default", cmd)

    def test_parser_run_still_requires_project(self):
        with self.assertRaises(SystemExit):
            self.m.build_parser().parse_args(["run"])


class TestCloneWarnings(_MachineTestCase):
    def test_clone_repo_returns_warning_on_deps_failure(self):
        # 1st lima_shell: repo-present probe (rc 1 = absent)
        # run(): git clone (ok)
        # 2nd lima_shell: deps install (rc 1 = failed)
        with mock.patch.object(self.m, "lima_shell",
                               side_effect=[proc(1), proc(1)]) as sh, \
             mock.patch.object(self.m, "run", return_value=proc(0)):
            warning = self.m.clone_repo("blog", "git@github.com:me/blog.git")
        self.assertEqual(warning, "deps install failed for blog — re-run inside the VM")
        self.assertEqual(sh.call_count, 2)

    def test_clone_repo_returns_none_on_success(self):
        with mock.patch.object(self.m, "lima_shell",
                               side_effect=[proc(1), proc(0)]), \
             mock.patch.object(self.m, "run", return_value=proc(0)):
            self.assertIsNone(self.m.clone_repo("blog", "git@github.com:me/blog.git"))

    def test_clone_repo_returns_none_when_already_present(self):
        with mock.patch.object(self.m, "lima_shell", return_value=proc(0)), \
             mock.patch.object(self.m, "run") as run_mock:
            self.assertIsNone(self.m.clone_repo("blog", "git@github.com:me/blog.git"))
        run_mock.assert_not_called()

    def _run_up(self, clone_result):
        """Drive cmd_up with all I/O mocked; return captured stdout."""
        out = io.StringIO()
        with mock.patch.object(self.m, "close_lima_ssh_master"), \
             mock.patch.object(self.m, "verify_repos_reachable"), \
             mock.patch.object(self.m, "vm_exists", return_value=True), \
             mock.patch.object(self.m, "run", return_value=proc(0)), \
             mock.patch.object(self.m, "clone_repo", return_value=clone_result), \
             contextlib.redirect_stdout(out):
            rc = self.m.cmd_up(argparse.Namespace(project="blog"))
        return rc, out.getvalue()

    def test_cmd_up_prints_check_summary_without_warnings(self):
        rc, out = self._run_up(None)
        self.assertEqual(rc, 0)
        self.assertIn("✓ blog ready", out)
        self.assertNotIn("⚠", out)

    def test_cmd_up_prints_warning_summary_and_exits_zero(self):
        rc, out = self._run_up("deps install failed for blog — re-run inside the VM")
        self.assertEqual(rc, 0)
        self.assertIn("⚠ blog ready with warnings:", out)
        self.assertIn("  deps install failed for blog — re-run inside the VM", out)
        self.assertNotIn("✓", out)

    def test_cmd_up_clone_auth_failure_warns_when_forwarding_off(self):
        # With forward_agent = false the in-VM clone has no agent to auth
        # with until the user installs a deploy key — surface a hint instead
        # of dying mid-up.
        err = subprocess.CalledProcessError(128, ["git", "clone"])
        out = io.StringIO()
        with mock.patch.object(self.m, "close_lima_ssh_master"), \
             mock.patch.object(self.m, "verify_repos_reachable"), \
             mock.patch.object(self.m, "vm_exists", return_value=True), \
             mock.patch.object(self.m, "run", return_value=proc(0)), \
             mock.patch.object(self.m, "clone_repo", side_effect=err), \
             contextlib.redirect_stdout(out):
            rc = self.m.cmd_up(argparse.Namespace(project="locked"))
        self.assertEqual(rc, 0)
        self.assertIn("⚠ locked ready with warnings:", out.getvalue())
        self.assertIn("deploy key", out.getvalue())

    def test_cmd_up_clone_failure_still_fatal_when_forwarding_on(self):
        err = subprocess.CalledProcessError(128, ["git", "clone"])
        with mock.patch.object(self.m, "close_lima_ssh_master"), \
             mock.patch.object(self.m, "verify_repos_reachable"), \
             mock.patch.object(self.m, "vm_exists", return_value=True), \
             mock.patch.object(self.m, "run", return_value=proc(0)), \
             mock.patch.object(self.m, "clone_repo", side_effect=err), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError):
                self.m.cmd_up(argparse.Namespace(project="blog"))

    def test_cmd_up_renders_template_with_forward_agent_off(self):
        with mock.patch.object(self.m, "close_lima_ssh_master"), \
             mock.patch.object(self.m, "verify_repos_reachable"), \
             mock.patch.object(self.m, "vm_exists", return_value=False), \
             mock.patch.object(self.m, "resolve_params", return_value={}), \
             mock.patch.object(self.m, "golden_fresh", return_value=True), \
             mock.patch.object(self.m, "render_template",
                               return_value=Path("/dev/null")) as render, \
             mock.patch.object(self.m.Path, "home",
                               return_value=Path(self.tmp.name)), \
             mock.patch.object(self.m, "run", return_value=proc(0)), \
             mock.patch.object(self.m, "clone_repo", return_value=None), \
             contextlib.redirect_stdout(io.StringIO()):
            self.m.cmd_up(argparse.Namespace(project="locked"))
        self.assertFalse(render.call_args.kwargs["forward_agent"])

    def test_cmd_up_closes_ssh_master_after_provisioning(self):
        # Provisioning (`limactl start`) may `chsh` the login shell; the SSH
        # master opened during start stays pinned to the old shell, so it must
        # be closed *after* start or `machine ssh` reuses the wrong shell.
        mgr = mock.Mock()
        mgr.run.return_value = proc(0)
        with mock.patch.object(self.m, "close_lima_ssh_master", mgr.close), \
             mock.patch.object(self.m, "verify_repos_reachable"), \
             mock.patch.object(self.m, "vm_exists", return_value=True), \
             mock.patch.object(self.m, "run", mgr.run), \
             mock.patch.object(self.m, "clone_repo", return_value=None), \
             contextlib.redirect_stdout(io.StringIO()):
            self.m.cmd_up(argparse.Namespace(project="blog"))
        names = [c[0] for c in mgr.mock_calls]
        start_idx = next(
            i for i, c in enumerate(mgr.mock_calls)
            if c[0] == "run" and list(c[1][0][:2]) == ["limactl", "start"]
        )
        self.assertIn("close", names[start_idx:])


class TestPrimaryRepoWorkdir(_MachineTestCase):
    def test_returns_guest_printed_path(self):
        with mock.patch.object(
            self.m, "lima_shell",
            return_value=proc(0, stdout="/home/other.linux/code/blog\n"),
        ) as sh:
            self.assertEqual(self.m._primary_repo_workdir("blog"),
                             "/home/other.linux/code/blog")
        guest_cmd = sh.call_args.args[1]
        self.assertIn('cd "$HOME/code/blog" && pwd', guest_cmd[-1])

    def test_returns_none_when_repo_dir_missing(self):
        with mock.patch.object(self.m, "lima_shell", return_value=proc(1)):
            self.assertIsNone(self.m._primary_repo_workdir("blog"))

    def test_does_not_read_host_user_env(self):
        # Regression: used to KeyError on missing USER and to fabricate
        # /home/$USER.linux/... from the host environment.
        with mock.patch.dict(self.m.os.environ, {}, clear=True), \
             mock.patch.object(
                 self.m, "lima_shell",
                 return_value=proc(0, stdout="/home/whoever/code/blog\n"),
             ):
            self.assertEqual(self.m._primary_repo_workdir("blog"),
                             "/home/whoever/code/blog")

    def test_returns_none_for_project_without_repos(self):
        with mock.patch.object(self.m, "lima_shell") as sh:
            self.assertIsNone(self.m._primary_repo_workdir("bare"))
        sh.assert_not_called()


class TestAgentSelfHeal(_MachineTestCase):
    def test_agent_has_keys_true_on_rc0(self):
        with mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(0, stdout="key\n")):
            self.assertTrue(self.m._agent_has_keys())

    def test_agent_has_keys_false_on_rc1(self):
        with mock.patch.object(self.m.subprocess, "run", return_value=proc(1)):
            self.assertFalse(self.m._agent_has_keys())

    def test_agent_has_keys_false_when_probe_times_out(self):
        # A wedged/locked host agent (e.g. a locked 1Password) accepts the
        # socket connection but never answers `ssh-add -l`. Treat the timeout
        # as "no keys" so the heal step no-ops instead of hanging machine ssh.
        with mock.patch.object(
                self.m.subprocess, "run",
                side_effect=self.m.subprocess.TimeoutExpired(
                    cmd="ssh-add", timeout=5)):
            self.assertFalse(self.m._agent_has_keys())

    def test_agent_has_keys_probe_is_time_boxed(self):
        # Guards against reintroducing the indefinite hang: the host probe
        # MUST pass a finite timeout to subprocess.run.
        with mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(0)) as run:
            self.m._agent_has_keys()
        timeout = run.call_args.kwargs.get("timeout")
        self.assertIsNotNone(timeout, "ssh-add -l probe must set a timeout")
        self.assertGreater(timeout, 0)

    def test_heal_noop_when_no_sock(self):
        with mock.patch.object(self.m.Path, "exists", return_value=False), \
             mock.patch.object(self.m, "_agent_has_keys", return_value=True) as keys, \
             mock.patch.object(self.m, "lima_shell") as sh, \
             mock.patch.object(self.m, "close_lima_ssh_master") as close:
            self.m._heal_stale_agent_master("blog")
        close.assert_not_called()
        sh.assert_not_called()
        keys.assert_not_called()

    def test_heal_noop_when_forwarding_disabled(self):
        # No agent reaches a forward_agent = false VM, so its in-VM probe
        # would always "fail" and thrash the master on every ssh.
        with mock.patch.object(self.m.Path, "exists", return_value=True), \
             mock.patch.object(self.m, "_agent_has_keys", return_value=True), \
             mock.patch.object(self.m, "lima_shell") as sh, \
             mock.patch.object(self.m, "close_lima_ssh_master") as close:
            self.m._heal_stale_agent_master("locked")
        close.assert_not_called()
        sh.assert_not_called()

    def test_heal_noop_when_host_agent_empty(self):
        with mock.patch.object(self.m.Path, "exists", return_value=True), \
             mock.patch.object(self.m, "_agent_has_keys", return_value=False), \
             mock.patch.object(self.m, "lima_shell") as sh, \
             mock.patch.object(self.m, "close_lima_ssh_master") as close:
            self.m._heal_stale_agent_master("blog")
        close.assert_not_called()
        sh.assert_not_called()

    def test_heal_noop_when_vm_has_keys(self):
        with mock.patch.object(self.m.Path, "exists", return_value=True), \
             mock.patch.object(self.m, "_agent_has_keys", return_value=True), \
             mock.patch.object(self.m, "lima_shell", return_value=proc(0)), \
             mock.patch.object(self.m, "close_lima_ssh_master") as close:
            self.m._heal_stale_agent_master("blog")
        close.assert_not_called()

    def test_heal_closes_master_when_vm_empty(self):
        with mock.patch.object(self.m.Path, "exists", return_value=True), \
             mock.patch.object(self.m, "_agent_has_keys", return_value=True), \
             mock.patch.object(self.m, "lima_shell", return_value=proc(1)), \
             mock.patch.object(self.m, "close_lima_ssh_master") as close:
            self.m._heal_stale_agent_master("blog")
        close.assert_called_once_with("blog")

    def test_heal_closes_master_when_probe_times_out(self):
        with mock.patch.object(self.m.Path, "exists", return_value=True), \
             mock.patch.object(self.m, "_agent_has_keys", return_value=True), \
             mock.patch.object(
                 self.m, "lima_shell",
                 side_effect=self.m.subprocess.TimeoutExpired(
                     cmd="ssh-add", timeout=5)), \
             mock.patch.object(self.m, "close_lima_ssh_master") as close:
            self.m._heal_stale_agent_master("blog")
        close.assert_called_once_with("blog")


class TestCommandsSelfHeal(_MachineTestCase):
    def test_cmd_ssh_heals_before_exec(self):
        with mock.patch.object(self.m, "_heal_stale_agent_master") as heal, \
             mock.patch.object(self.m, "_primary_repo_workdir", return_value=None), \
             mock.patch.object(self.m.os, "execvp"):
            self.m.cmd_ssh(argparse.Namespace(project="blog"))
        heal.assert_called_once_with("blog")

    def test_cmd_claude_heals_before_exec(self):
        with mock.patch.object(self.m, "_heal_stale_agent_master") as heal, \
             mock.patch.object(self.m, "_primary_repo_workdir", return_value=None), \
             mock.patch.object(self.m.os, "execvp"), \
             contextlib.redirect_stderr(io.StringIO()):
            self.m.cmd_claude(argparse.Namespace(project="blog"))
        heal.assert_called_once_with("blog")


class TestSecretsReachability(_MachineTestCase):
    def _secrets_args(self, **kw):
        defaults = dict(project="blog", repo=None, clear=False)
        defaults.update(kw)
        return argparse.Namespace(**defaults)

    def test_cmd_secrets_dies_when_vm_unreachable(self):
        with mock.patch.object(self.m.shutil, "which", return_value="/usr/bin/op"), \
             mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(255, stderr="ssh: connect failed")), \
             self.assertRaises(SystemExit), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.m.cmd_secrets(self._secrets_args())
        self.assertIn("cannot reach VM 'blog'", err.getvalue())
        self.assertIn("machine up blog", err.getvalue())

    def test_cmd_secrets_keeps_nothing_found_message(self):
        # Probe succeeds but finds no .envrc files (or ~/code doesn't exist
        # yet — the guest script ends in `|| true`): not an error, exit 1
        # with the existing hint.
        with mock.patch.object(self.m.shutil, "which", return_value="/usr/bin/op"), \
             mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(0, stdout="")), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            rc = self.m.cmd_secrets(self._secrets_args())
        self.assertEqual(rc, 1)
        self.assertIn("no repos with 'use op_env'", err.getvalue())

    def test_cmd_secrets_clear_repo_dies_when_vm_unreachable(self):
        with mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(255, stderr="ssh: connect failed")), \
             self.assertRaises(SystemExit), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.m.cmd_secrets_clear(self._secrets_args(repo="blog", clear=True))
        self.assertIn("cannot reach VM 'blog'", err.getvalue())


class TestProjectResources(_MachineTestCase):
    """Per-project cpus/memory/disk overrides for the generated template.
    Like forward_agent, they apply when the VM is (re)created."""

    def _rewrite_projects(self, body: str) -> None:
        self.m.PROJECTS_FILE.write_text(body)

    def test_project_resources_empty_when_unset(self):
        self.assertEqual(self.m.project_resources("blog"), {})

    def test_project_resources_unknown_project_empty(self):
        self.assertEqual(self.m.project_resources("no-such-project"), {})

    def test_project_resources_returns_configured(self):
        self.assertEqual(
            self.m.project_resources("big"),
            {"cpus": "8", "memory": "16GiB", "disk": "60GiB"})

    def test_project_resources_bare_int_means_gib(self):
        self._rewrite_projects("[big]\nmemory = 16\ndisk = 60\n")
        self.assertEqual(
            self.m.project_resources("big"),
            {"memory": "16GiB", "disk": "60GiB"})

    def test_project_resources_invalid_cpus_dies(self):
        for bad in ('cpus = "lots"', "cpus = 0", "cpus = -2"):
            self._rewrite_projects(f"[big]\n{bad}\n")
            with self.assertRaises(SystemExit), \
                 contextlib.redirect_stderr(io.StringIO()) as err:
                self.m.project_resources("big")
            self.assertIn("cpus", err.getvalue())

    def test_project_resources_invalid_memory_dies(self):
        self._rewrite_projects('[big]\nmemory = "16 gigs"\n')
        with self.assertRaises(SystemExit), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.m.project_resources("big")
        self.assertIn("memory", err.getvalue())
        self.assertIn("16GiB", err.getvalue())  # message shows the format

    def test_render_template_emits_resource_overrides_before_base(self):
        out = self.m.render_template(
            "big", [], golden=False,
            resources={"cpus": "8", "memory": "16GiB", "disk": "60GiB"})
        text = out.read_text()
        for line in ("cpus: 8", "memory: 16GiB", "disk: 60GiB"):
            self.assertIn(line, text)
            # overrides must precede the base: stack so they win the merge
            self.assertLess(text.index(line), text.index("base:"))

    def test_render_template_no_resources_by_default(self):
        text = self.m.render_template("blog", [], golden=False).read_text()
        for key in ("cpus:", "memory:", "disk:"):
            self.assertNotIn(key, text)

    def test_cmd_up_renders_template_with_resources(self):
        with mock.patch.object(self.m, "close_lima_ssh_master"), \
             mock.patch.object(self.m, "verify_repos_reachable"), \
             mock.patch.object(self.m, "vm_exists", return_value=False), \
             mock.patch.object(self.m, "resolve_params", return_value={}), \
             mock.patch.object(self.m, "golden_fresh", return_value=True), \
             mock.patch.object(self.m, "render_template",
                               return_value=Path("/dev/null")) as render, \
             mock.patch.object(self.m.Path, "home",
                               return_value=Path(self.tmp.name)), \
             mock.patch.object(self.m, "run", return_value=proc(0)), \
             mock.patch.object(self.m, "clone_repo", return_value=None), \
             contextlib.redirect_stdout(io.StringIO()):
            self.m.cmd_up(argparse.Namespace(project="big"))
        self.assertEqual(render.call_args.kwargs["resources"],
                         {"cpus": "8", "memory": "16GiB", "disk": "60GiB"})


class TestErrorHandling(_MachineTestCase):
    """First-run failure paths must die with a `machine: ...` message, never
    a raw traceback or a silent nonzero exit."""

    def _projects_path(self) -> Path:
        return self.m.PROJECTS_FILE

    def test_load_projects_invalid_toml_dies_with_message(self):
        self._projects_path().write_text("[blog\nrepos = oops")
        with self.assertRaises(SystemExit), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.m.load_projects()
        self.assertIn("invalid TOML", err.getvalue())
        self.assertIn(str(self._projects_path()), err.getvalue())

    def test_project_shell_invalid_toml_dies_with_message(self):
        self._projects_path().write_text("[blog\nrepos = oops")
        with self.assertRaises(SystemExit), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.m.project_shell("blog")
        self.assertIn("invalid TOML", err.getvalue())

    def test_load_projects_unreadable_file_dies_with_message(self):
        path = self._projects_path()
        path.chmod(0)
        # tearDown removes the tempdir first; restore the mode only if the
        # file is still there.
        self.addCleanup(lambda: path.exists() and path.chmod(0o644))
        if os.access(path, os.R_OK):  # pragma: no cover — root ignores modes
            self.skipTest("running as root; cannot make file unreadable")
        with self.assertRaises(SystemExit), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.m.load_projects()
        self.assertIn("cannot read", err.getvalue())

    def test_main_reports_missing_limactl(self):
        # `machine down` hits vm_exists() first; without limactl installed
        # subprocess.run raises FileNotFoundError, which used to escape main()
        # as a traceback.
        missing = FileNotFoundError(2, "No such file or directory")
        missing.filename = "limactl"
        with mock.patch.object(self.m.subprocess, "run", side_effect=missing), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            rc = self.m.main(["down", "blog"])
        self.assertNotEqual(rc, 0)
        self.assertIn("limactl", err.getvalue())
        self.assertIn("brew install lima", err.getvalue())

    def test_main_reports_other_missing_binary_without_lima_hint(self):
        missing = FileNotFoundError(2, "No such file or directory")
        missing.filename = "git"
        with mock.patch.object(self.m.subprocess, "run", side_effect=missing), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            rc = self.m.main(["doctor"])
        self.assertNotEqual(rc, 0)
        self.assertIn("git", err.getvalue())
        self.assertNotIn("brew install lima", err.getvalue())

    def test_read_signing_key_op_failure_dies_with_message(self):
        # `op read` failing (locked vault, bad ref) used to raise
        # CalledProcessError, which main() swallowed into a bare exit code.
        env = {"OP_SIGNING_KEY_REF": "op://vault/key/public"}
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(self.m.shutil, "which", return_value="/usr/bin/op"), \
             mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(1, stderr="not signed in")), \
             self.assertRaises(SystemExit), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.m.read_signing_key()
        self.assertIn("op read", err.getvalue())
        self.assertIn("not signed in", err.getvalue())

    def test_cmd_destroy_eof_aborts_cleanly(self):
        # Closed stdin (piped/cron use without -y) must abort like an
        # explicit "n", not crash with EOFError.
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=EOFError), \
             contextlib.redirect_stdout(out):
            rc = self.m.cmd_destroy(
                argparse.Namespace(project="blog", force=False))
        self.assertEqual(rc, 1)
        self.assertIn("aborted", out.getvalue())


class TestProjectEntryFormatting(_MachineTestCase):
    def test_single_repo_renders_one_line(self):
        text = self.m.format_project_entry(
            "blog", {"repos": ["git@github.com:me/blog.git"]})
        self.assertEqual(
            text,
            '[blog]\nrepos = ["git@github.com:me/blog.git"]\n')

    def test_multi_repo_renders_multiline(self):
        text = self.m.format_project_entry(
            "wallet", {"repos": ["git@github.com:me/a.git",
                                 "git@github.com:me/b.git"]})
        self.assertIn("repos = [\n", text)
        self.assertIn('  "git@github.com:me/a.git",\n', text)
        self.assertIn('  "git@github.com:me/b.git",\n', text)

    def test_optional_keys_rendered_when_present(self):
        import tomllib
        text = self.m.format_project_entry("p", {
            "repos": [],
            "profiles": ["cypress", "supabase-fly"],
            "shell": "bash",
            "forward_agent": False,
        })
        parsed = tomllib.loads(text)["p"]
        self.assertEqual(parsed["repos"], [])
        self.assertEqual(parsed["profiles"], ["cypress", "supabase-fly"])
        self.assertEqual(parsed["shell"], "bash")
        self.assertIs(parsed["forward_agent"], False)

    def test_optional_keys_omitted_when_absent(self):
        text = self.m.format_project_entry(
            "p", {"repos": ["git@github.com:me/p.git"]})
        self.assertNotIn("profiles", text)
        self.assertNotIn("shell", text)
        self.assertNotIn("forward_agent", text)


class TestUpsertProjectEntry(_MachineTestCase):
    def test_append_to_empty_text(self):
        out = self.m.upsert_project_entry("", "p", "[p]\nrepos = []\n")
        self.assertEqual(out, "[p]\nrepos = []\n")

    def test_append_preserves_existing_content(self):
        original = (
            "# my projects\n"
            'default_profile = "cypress"\n'
            "\n"
            "[blog]\n"
            'repos = ["git@github.com:me/blog.git"]\n'
        )
        out = self.m.upsert_project_entry(original, "new", "[new]\nrepos = []\n")
        self.assertIn("# my projects", out)
        self.assertIn("[blog]", out)
        self.assertTrue(out.endswith("\n[new]\nrepos = []\n"))
        # blank-line separator between the old tail and the new entry
        self.assertIn('repos = ["git@github.com:me/blog.git"]\n\n[new]', out)

    def test_replace_middle_block_preserves_neighbors_and_comments(self):
        import tomllib
        original = (
            "# header comment\n"
            "[blog]\n"
            'repos = ["git@github.com:me/blog.git"]\n'
            "\n"
            "# wallet docs\n"
            "[wallet]\n"
            'repos = ["git@github.com:me/a.git"]\n'
        )
        out = self.m.upsert_project_entry(
            original, "blog", '[blog]\nrepos = ["git@github.com:me/new.git"]\n')
        self.assertIn("# header comment", out)
        self.assertIn("# wallet docs", out)
        parsed = tomllib.loads(out)
        self.assertEqual(parsed["blog"]["repos"], ["git@github.com:me/new.git"])
        self.assertEqual(parsed["wallet"]["repos"], ["git@github.com:me/a.git"])

    def test_replace_last_block_keeps_trailing_comment(self):
        original = (
            "[blog]\n"
            'repos = ["git@github.com:me/blog.git"]\n'
            "\n"
            "# trailing note that must survive\n"
        )
        out = self.m.upsert_project_entry(
            original, "blog", '[blog]\nrepos = ["git@github.com:me/new.git"]\n')
        self.assertIn("# trailing note that must survive", out)
        self.assertIn('repos = ["git@github.com:me/new.git"]', out)

    def test_replace_last_block(self):
        import tomllib
        original = (
            "[blog]\n"
            'repos = ["git@github.com:me/blog.git"]\n'
            "\n"
            "[wallet]\n"
            'repos = ["git@github.com:me/a.git"]\n'
        )
        out = self.m.upsert_project_entry(
            original, "wallet",
            '[wallet]\nrepos = ["git@github.com:me/b.git"]\nshell = "bash"\n')
        parsed = tomllib.loads(out)
        self.assertEqual(parsed["wallet"]["repos"], ["git@github.com:me/b.git"])
        self.assertEqual(parsed["wallet"]["shell"], "bash")
        self.assertEqual(parsed["blog"]["repos"], ["git@github.com:me/blog.git"])


class TestAvailableProfiles(_MachineTestCase):
    def test_lists_stackable_templates_without_base(self):
        profiles = self.m.available_profiles()
        self.assertIn("cypress", profiles)
        self.assertIn("supabase-fly", profiles)
        self.assertNotIn("base", profiles)
        self.assertEqual(profiles, sorted(profiles))


class TestCreateWizard(_MachineTestCase):
    """Drives run_create_wizard with scripted input(). Prompt order:
    [name when not given], repo URLs (blank line ends; first blank keeps
    current in edit mode), profiles, shell, forward_agent."""

    def _wizard(self, inputs, name=None):
        with mock.patch("builtins.input", side_effect=inputs), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            return self.m.run_create_wizard(name)

    def _parsed(self):
        import tomllib
        return tomllib.loads(self.m.PROJECTS_FILE.read_text())

    def test_creates_new_entry(self):
        got = self._wizard(["git@github.com:me/new.git", "", "", "", ""],
                           name="newproj")
        self.assertEqual(got, "newproj")
        cfg = self._parsed()
        self.assertEqual(cfg["newproj"]["repos"], ["git@github.com:me/new.git"])
        # Enter at the profile prompt accepts the default (default_profile)
        self.assertEqual(cfg["newproj"]["profiles"], ["cypress"])
        # zsh is the implicit default, forwarding defaults on — neither written
        self.assertNotIn("shell", cfg["newproj"])
        self.assertNotIn("forward_agent", cfg["newproj"])
        # the rest of the file survives
        self.assertEqual(cfg["default_profile"], "cypress")
        self.assertIn("blog", cfg)

    def test_edit_mode_enter_keeps_current_values(self):
        self._wizard(["", "", "", ""], name="wallet")
        cfg = self._parsed()
        self.assertEqual(cfg["wallet"]["repos"],
                         ["git@github.com:me/a.git", "git@github.com:me/b.git"])
        self.assertEqual(cfg["wallet"]["profiles"], ["cypress", "supabase-fly"])
        self.assertEqual(cfg["wallet"]["shell"], "bash")
        self.assertIn("blog", cfg)

    def test_edit_mode_new_repos_replace_current(self):
        self._wizard(["git@github.com:me/only.git", "", "", "", ""],
                     name="wallet")
        self.assertEqual(self._parsed()["wallet"]["repos"],
                         ["git@github.com:me/only.git"])

    def test_none_clears_profiles_overriding_default(self):
        # default_profile is set, so clearing must write profiles = []
        # (an omitted key would fall back to the default).
        self._wizard(["", "none", "", ""], name="blog")
        self.assertEqual(self._parsed()["blog"]["profiles"], [])

    def test_unknown_profile_reprompts(self):
        self._wizard(["git@github.com:me/p.git", "", "bogus", "cypress",
                      "", ""], name="p2")
        self.assertEqual(self._parsed()["p2"]["profiles"], ["cypress"])

    def test_forward_agent_no_is_written(self):
        self._wizard(["git@github.com:me/p.git", "", "", "", "n"], name="p3")
        self.assertIs(self._parsed()["p3"]["forward_agent"], False)

    def test_explicit_bash_shell_is_written(self):
        self._wizard(["git@github.com:me/p.git", "", "", "bash", ""],
                     name="p4")
        self.assertEqual(self._parsed()["p4"]["shell"], "bash")

    def test_prompts_for_name_and_reprompts_on_invalid(self):
        got = self._wizard(["Bad_Name", "good-name",
                            "git@github.com:me/g.git", "", "", "", ""])
        self.assertEqual(got, "good-name")
        self.assertIn("good-name", self._parsed())

    def test_eof_dies_with_message(self):
        with mock.patch("builtins.input", side_effect=EOFError), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit):
                self.m.run_create_wizard("newproj")
        self.assertIn("machine create", err.getvalue())

    def test_creates_projects_file_when_missing(self):
        self.m.PROJECTS_FILE.unlink()
        self._wizard(["git@github.com:me/solo.git", "", "", "", ""],
                     name="solo")
        cfg = self._parsed()
        self.assertEqual(cfg["solo"]["repos"], ["git@github.com:me/solo.git"])


class TestUpLaunchesWizard(_MachineTestCase):
    def test_parser_up_project_defaults_to_none(self):
        ap = self.m.build_parser()
        self.assertIsNone(ap.parse_args(["up"]).project)
        self.assertEqual(ap.parse_args(["up", "blog"]).project, "blog")

    def test_parser_create_takes_optional_name(self):
        ap = self.m.build_parser()
        self.assertIsNone(ap.parse_args(["create"]).project)
        self.assertEqual(ap.parse_args(["create", "blog"]).project, "blog")

    def test_known_project_skips_wizard(self):
        with mock.patch.object(self.m, "run_create_wizard",
                               side_effect=AssertionError("wizard ran")):
            name = self.m.resolve_up_project(self.m.load_projects(), "blog")
        self.assertEqual(name, "blog")

    def test_unknown_name_launches_wizard_prefilled(self):
        with mock.patch.object(self.m, "vm_exists", return_value=False), \
             mock.patch.object(self.m, "run_create_wizard",
                               return_value="scratch") as wiz:
            name = self.m.resolve_up_project(self.m.load_projects(), "scratch")
        self.assertEqual(name, "scratch")
        wiz.assert_called_once_with("scratch")

    def test_unknown_name_with_existing_vm_skips_wizard(self):
        with mock.patch.object(self.m, "vm_exists", return_value=True), \
             mock.patch.object(self.m, "run_create_wizard",
                               side_effect=AssertionError("wizard ran")):
            name = self.m.resolve_up_project(self.m.load_projects(), "scratch")
        self.assertEqual(name, "scratch")

    def test_bare_up_with_default_vm_keeps_zero_config(self):
        with mock.patch.object(self.m, "vm_exists", return_value=True), \
             mock.patch.object(self.m, "run_create_wizard",
                               side_effect=AssertionError("wizard ran")):
            name = self.m.resolve_up_project(self.m.load_projects(), None)
        self.assertEqual(name, "default")

    def test_bare_up_without_default_launches_wizard(self):
        with mock.patch.object(self.m, "vm_exists", return_value=False), \
             mock.patch.object(self.m, "run_create_wizard",
                               return_value="fresh") as wiz:
            name = self.m.resolve_up_project(self.m.load_projects(), None)
        self.assertEqual(name, "fresh")
        wiz.assert_called_once_with()

    def test_explicit_default_never_launches_wizard(self):
        with mock.patch.object(self.m, "vm_exists", return_value=False), \
             mock.patch.object(self.m, "run_create_wizard",
                               side_effect=AssertionError("wizard ran")):
            name = self.m.resolve_up_project({}, "default")
        self.assertEqual(name, "default")

    def test_cmd_up_uses_config_written_by_wizard(self):
        def fake_wizard(name):
            entry = self.m.format_project_entry(
                name, {"repos": ["git@github.com:me/scratch.git"]})
            text = self.m.PROJECTS_FILE.read_text()
            self.m.PROJECTS_FILE.write_text(
                self.m.upsert_project_entry(text, name, entry))
            return name

        with mock.patch.object(self.m, "run_create_wizard",
                               side_effect=fake_wizard), \
             mock.patch.object(self.m, "vm_exists", return_value=False), \
             mock.patch.object(self.m, "close_lima_ssh_master"), \
             mock.patch.object(self.m, "verify_repos_reachable") as verify, \
             mock.patch.object(self.m, "resolve_params", return_value={}), \
             mock.patch.object(self.m, "golden_fresh", return_value=True), \
             mock.patch.object(self.m, "render_template",
                               return_value=Path("/dev/null")), \
             mock.patch.object(self.m.Path, "home",
                               return_value=Path(self.tmp.name)), \
             mock.patch.object(self.m, "run", return_value=proc(0)), \
             mock.patch.object(self.m, "clone_repo", return_value=None) as clone, \
             contextlib.redirect_stdout(io.StringIO()):
            rc = self.m.cmd_up(argparse.Namespace(project="scratch"))
        self.assertEqual(rc, 0)
        verify.assert_called_once_with(["git@github.com:me/scratch.git"])
        clone.assert_called_once_with("scratch", "git@github.com:me/scratch.git")

    def test_cmd_create_runs_wizard_and_prints_hint(self):
        out = io.StringIO()
        with mock.patch.object(self.m, "run_create_wizard",
                               return_value="newproj") as wiz, \
             contextlib.redirect_stdout(out):
            rc = self.m.cmd_create(argparse.Namespace(project="newproj"))
        self.assertEqual(rc, 0)
        wiz.assert_called_once_with("newproj")
        self.assertIn("machine up newproj", out.getvalue())


class TestSyncOneEnv(_MachineTestCase):
    def test_op_failure_returns_false_and_skips_vm(self):
        with mock.patch.object(self.m.subprocess, "run",
                               return_value=proc(1, stderr="not signed in")) as sp, \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            ok = self.m.sync_one_env("blog", "abc123", "blog")
        self.assertFalse(ok)
        self.assertEqual(sp.call_count, 1)  # op only; limactl never invoked
        self.assertIn("not signed in", err.getvalue())

    def test_success_pipes_secret_via_stdin_not_argv(self):
        secret = "TOKEN=hunter2\n"
        with mock.patch.object(self.m.subprocess, "run",
                               side_effect=[proc(0, stdout=secret), proc(0)]) as sp, \
             contextlib.redirect_stdout(io.StringIO()):
            ok = self.m.sync_one_env("blog", "abc123", "blog")
        self.assertTrue(ok)
        push = sp.call_args_list[1]
        self.assertEqual(push.kwargs.get("input"), secret)
        self.assertNotIn(secret, " ".join(push.args[0]))
        self.assertEqual(push.args[0][:3], ["limactl", "shell", "blog"])


if __name__ == "__main__":
    unittest.main()
