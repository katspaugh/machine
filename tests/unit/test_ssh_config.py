"""Unit tests for the SSH config helpers in bin/machine."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path as _Path
from unittest import mock as _mock

from .test_machine import m  # reuses the bin/machine importer


class TestHostAlias(unittest.TestCase):
    def test_lowercase_passthrough(self):
        self.assertEqual(m.host_alias("blog"), "machine-blog")

    def test_hyphens_preserved(self):
        self.assertEqual(m.host_alias("my-app"), "machine-my-app")

    def test_digits_allowed(self):
        self.assertEqual(m.host_alias("a1"), "machine-a1")

    def test_non_alnum_becomes_dash(self):
        # Project keys are already validated by validate_name(), so we don't
        # see uppercase or whitespace here; but underscores etc. would be
        # sanitized if they ever leak in.
        self.assertEqual(m.host_alias("a_b.c"), "machine-a-b-c")


class TestParseLimaSshOptions(unittest.TestCase):
    def test_parses_quoted_and_unquoted(self):
        out = (
            'IdentityFile="/Users/example/.lima/_config/user"\n'
            "User=example.linux\n"
            "Hostname=127.0.0.1\n"
            "Port=60022\n"
            "StrictHostKeyChecking=no\n"
        )
        got = m.parse_lima_ssh_options(out)
        self.assertEqual(got["IdentityFile"], "/Users/example/.lima/_config/user")
        self.assertEqual(got["User"], "example.linux")
        self.assertEqual(got["Hostname"], "127.0.0.1")
        self.assertEqual(got["Port"], "60022")

    def test_ignores_blank_and_comments(self):
        out = "\n# comment\nUser=bob\n   \n"
        self.assertEqual(m.parse_lima_ssh_options(out), {"User": "bob"})

    def test_value_with_equals_sign(self):
        # ProxyCommand-like values can contain '=' inside.
        out = 'ProxyCommand=ssh -W %h:%p user=foo bastion\n'
        self.assertEqual(
            m.parse_lima_ssh_options(out)["ProxyCommand"],
            "ssh -W %h:%p user=foo bastion",
        )

    def test_empty_input(self):
        self.assertEqual(m.parse_lima_ssh_options(""), {})


class TestRenderBlock(unittest.TestCase):
    def _opts(self, port: str) -> dict:
        return {
            "Hostname": "127.0.0.1",
            "Port": port,
            "User": "user.linux",
            "IdentityFile": "/Users/u/.lima/_config/user",
        }

    def test_empty_entries_returns_empty_string(self):
        self.assertEqual(m.render_block([]), "")

    def test_single_entry(self):
        got = m.render_block([("blog", self._opts("60123"))])
        expected = (
            f"{m.SSH_SENTINEL_OPEN}\n"
            "Host machine-blog\n"
            "    HostName 127.0.0.1\n"
            "    Port 60123\n"
            "    User user.linux\n"
            "    IdentityFile /Users/u/.lima/_config/user\n"
            "    IdentitiesOnly yes\n"
            "    StrictHostKeyChecking no\n"
            "    UserKnownHostsFile /dev/null\n"
            "    ForwardAgent yes\n"
            f"{m.SSH_SENTINEL_CLOSE}\n"
        )
        self.assertEqual(got, expected)

    def test_multiple_entries_separated_by_blank_line(self):
        got = m.render_block([
            ("blog", self._opts("60123")),
            ("wallet", self._opts("60127")),
        ])
        # exactly one blank line between the two Host blocks
        self.assertIn("ForwardAgent yes\n\nHost machine-wallet\n", got)
        self.assertTrue(got.startswith(m.SSH_SENTINEL_OPEN + "\n"))
        self.assertTrue(got.endswith(m.SSH_SENTINEL_CLOSE + "\n"))

    def test_entries_use_host_alias_sanitization(self):
        got = m.render_block([("my_proj.x", self._opts("60001"))])
        self.assertIn("Host machine-my-proj-x\n", got)

    def test_missing_option_is_omitted(self):
        # If Lima didn't report a field (shouldn't happen in practice),
        # render_block must not crash and must skip that line.
        partial = {"Hostname": "127.0.0.1", "Port": "60001"}
        got = m.render_block([("p", partial)])
        self.assertIn("HostName 127.0.0.1", got)
        self.assertIn("Port 60001", got)
        self.assertNotIn("User ", got)
        self.assertNotIn("IdentityFile ", got)


class TestSpliceBlock(unittest.TestCase):
    def _block(self, body: str = "Host machine-blog\n    Port 60022\n") -> str:
        return f"{m.SSH_SENTINEL_OPEN}\n{body}{m.SSH_SENTINEL_CLOSE}\n"

    def test_empty_existing_block_only(self):
        new = self._block()
        self.assertEqual(m.splice_block("", new), new)

    def test_existing_no_block_appends_with_blank_line(self):
        existing = "Host foo\n    HostName 1.2.3.4\n"
        new = self._block()
        got = m.splice_block(existing, new)
        # original content preserved verbatim, then one blank line, then block.
        self.assertEqual(got, existing + "\n" + new)

    def test_existing_no_block_no_trailing_newline(self):
        existing = "Host foo\n    HostName 1.2.3.4"  # no trailing newline
        new = self._block()
        got = m.splice_block(existing, new)
        # the original is preserved, exactly one blank line separates.
        self.assertEqual(got, existing + "\n\n" + new)

    def test_replaces_existing_block(self):
        old_block = self._block("Host machine-old\n    Port 60011\n")
        new_block = self._block("Host machine-new\n    Port 60022\n")
        existing = "Host foo\n    HostName 1.2.3.4\n\n" + old_block
        got = m.splice_block(existing, new_block)
        self.assertEqual(got, "Host foo\n    HostName 1.2.3.4\n\n" + new_block)

    def test_replaces_block_in_middle(self):
        old_block = self._block("Host machine-old\n    Port 60011\n")
        new_block = self._block("Host machine-new\n    Port 60022\n")
        suffix = "\nHost bar\n    HostName 5.6.7.8\n"
        existing = "Host foo\n\n" + old_block + suffix
        got = m.splice_block(existing, new_block)
        self.assertEqual(got, "Host foo\n\n" + new_block + suffix)

    def test_empty_new_block_removes_existing(self):
        existing = "Host foo\n    HostName 1.2.3.4\n\n" + self._block()
        got = m.splice_block(existing, "")
        # No trailing blank-line orphan.
        self.assertEqual(got, "Host foo\n    HostName 1.2.3.4\n")

    def test_empty_new_block_no_existing_is_noop(self):
        existing = "Host foo\n    HostName 1.2.3.4\n"
        self.assertEqual(m.splice_block(existing, ""), existing)

    def test_duplicate_open_sentinels_raises(self):
        existing = self._block() + "\n" + self._block()
        with self.assertRaises(m.DuplicateSentinelError):
            m.splice_block(existing, self._block("Host x\n"))

    def test_only_close_sentinel_raises(self):
        existing = f"random\n{m.SSH_SENTINEL_CLOSE}\nmore\n"
        with self.assertRaises(m.DuplicateSentinelError):
            m.splice_block(existing, self._block("Host x\n"))

    def test_only_open_sentinel_raises(self):
        existing = f"{m.SSH_SENTINEL_OPEN}\nrandom\n"
        with self.assertRaises(m.DuplicateSentinelError):
            m.splice_block(existing, self._block("Host x\n"))


class TestRefreshSshConfig(unittest.TestCase):
    """Integration-ish: mocks limactl + projects.toml, but writes a real file."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = _Path(self._tmp.name)
        (self.home / ".ssh").mkdir()
        self._patch_path = _mock.patch.object(
            m, "SSH_CONFIG_PATH", self.home / ".ssh" / "config"
        )
        self._patch_path.start()

    def tearDown(self):
        self._patch_path.stop()
        self._tmp.cleanup()

    def _fake_show_ssh(self, by_vm: dict[str, str]):
        def fake(cmd, *args, **kwargs):
            if cmd[:3] == ["limactl", "show-ssh", "--format=options"]:
                vm = cmd[-1]
                stdout = by_vm.get(vm)
                if stdout is None:
                    return _mock.Mock(returncode=1, stdout="", stderr="no instance")
                return _mock.Mock(returncode=0, stdout=stdout, stderr="")
            raise AssertionError(f"unexpected subprocess call: {cmd}")
        return fake

    def test_writes_block_for_existing_vms(self):
        config = self.home / ".ssh" / "config"
        with _mock.patch.object(m, "load_projects", return_value={
            "default_profile": "cypress",
            "blog": {"repos": ["git@github.com:x/y.git"]},
            "wallet": {"repos": ["git@github.com:x/z.git"]},
        }), _mock.patch("subprocess.run", side_effect=self._fake_show_ssh({
            "blog": "Hostname=127.0.0.1\nPort=60123\nUser=u.linux\nIdentityFile=/p/u\n",
            "wallet": "Hostname=127.0.0.1\nPort=60127\nUser=u.linux\nIdentityFile=/p/u\n",
        })):
            m.refresh_ssh_config()
        content = config.read_text()
        self.assertIn("Host machine-blog", content)
        self.assertIn("Port 60123", content)
        self.assertIn("Host machine-wallet", content)
        self.assertEqual(oct(config.stat().st_mode & 0o777), "0o600")

    def test_skips_projects_with_no_vm(self):
        config = self.home / ".ssh" / "config"
        with _mock.patch.object(m, "load_projects", return_value={
            "blog": {"repos": []},
            "ghost": {"repos": []},
        }), _mock.patch("subprocess.run", side_effect=self._fake_show_ssh({
            "blog": "Hostname=127.0.0.1\nPort=60123\nUser=u.linux\nIdentityFile=/p/u\n",
        })):
            m.refresh_ssh_config()
        content = config.read_text()
        self.assertIn("Host machine-blog", content)
        self.assertNotIn("Host machine-ghost", content)

    def test_preserves_unrelated_entries(self):
        config = self.home / ".ssh" / "config"
        original = "Host github.com\n    User git\n"
        config.write_text(original)
        with _mock.patch.object(m, "load_projects", return_value={
            "blog": {"repos": []},
        }), _mock.patch("subprocess.run", side_effect=self._fake_show_ssh({
            "blog": "Hostname=127.0.0.1\nPort=60123\nUser=u.linux\nIdentityFile=/p/u\n",
        })):
            m.refresh_ssh_config()
        content = config.read_text()
        self.assertTrue(content.startswith(original))
        self.assertIn("Host machine-blog", content)

    def test_no_vms_removes_existing_block(self):
        config = self.home / ".ssh" / "config"
        original = "Host github.com\n    User git\n"
        config.write_text(
            original
            + "\n"
            + f"{m.SSH_SENTINEL_OPEN}\nHost machine-old\n    Port 60001\n{m.SSH_SENTINEL_CLOSE}\n"
        )
        with _mock.patch.object(m, "load_projects", return_value={
            "blog": {"repos": []},
        }), _mock.patch("subprocess.run", side_effect=self._fake_show_ssh({})):
            m.refresh_ssh_config()
        content = config.read_text()
        self.assertEqual(content, original)

    def test_swallows_errors_with_warning(self):
        # When load_projects raises an unexpected error, refresh must warn
        # but not raise.
        with _mock.patch.object(m, "load_projects", side_effect=PermissionError("nope")):
            m.refresh_ssh_config()  # must not raise

    def test_writes_through_symlink_inside_home(self):
        # SSH_CONFIG_PATH is a symlink pointing at another file inside the
        # tmp HOME. The symlink must survive and the real file must be
        # updated.
        real = self.home / ".ssh" / "config.real"
        real.write_text("")
        link = self.home / ".ssh" / "config"
        link.symlink_to(real)
        with _mock.patch.object(m, "load_projects", return_value={
            "blog": {"repos": []},
        }), _mock.patch("subprocess.run", side_effect=self._fake_show_ssh({
            "blog": "Hostname=127.0.0.1\nPort=60123\nUser=u\nIdentityFile=/p\n",
        })):
            m.refresh_ssh_config()
        self.assertTrue(link.is_symlink(), "symlink must survive")
        self.assertIn("Host machine-blog", real.read_text())

    def test_skips_symlink_outside_home(self):
        # Symlink points outside $HOME — refresh must warn and not write.
        outside = _Path(tempfile.mkdtemp())
        try:
            real = outside / "ssh_config"
            real.write_text("preserved\n")
            link = self.home / ".ssh" / "config"
            link.symlink_to(real)
            with _mock.patch.object(m, "load_projects", return_value={
                "blog": {"repos": []},
            }), _mock.patch("subprocess.run", side_effect=self._fake_show_ssh({
                "blog": "Hostname=127.0.0.1\nPort=60123\nUser=u\nIdentityFile=/p\n",
            })):
                m.refresh_ssh_config()
            self.assertEqual(real.read_text(), "preserved\n")
            self.assertTrue(link.is_symlink())
        finally:
            import shutil as _shutil
            _shutil.rmtree(outside, ignore_errors=True)


class TestLifecycleHooks(unittest.TestCase):
    def test_cmd_up_calls_refresh_on_success(self):
        with _mock.patch.object(m, "refresh_ssh_config") as ref, \
             _mock.patch.object(m, "validate_name"), \
             _mock.patch.object(m, "project_urls", return_value=[]), \
             _mock.patch.object(m, "project_profiles", return_value=[]), \
             _mock.patch.object(m, "project_shell", return_value="zsh"), \
             _mock.patch.object(m, "verify_repos_reachable"), \
             _mock.patch.object(m, "vm_exists", return_value=True), \
             _mock.patch.object(m, "run"), \
             _mock.patch.object(m, "push_files_to_vm"), \
             _mock.patch.object(m, "render_git_templates"), \
             _mock.patch.object(m, "run_provision_in_vm"):
            ns = _mock.Mock(project="blog", dry_run=False)
            rc = m.cmd_up(ns)
        self.assertEqual(rc, 0)
        ref.assert_called_once()

    def test_cmd_up_does_not_call_refresh_on_failure(self):
        with _mock.patch.object(m, "refresh_ssh_config") as ref, \
             _mock.patch.object(m, "validate_name"), \
             _mock.patch.object(m, "project_urls", return_value=["git@github.com:x/y.git"]), \
             _mock.patch.object(m, "project_profiles", return_value=[]), \
             _mock.patch.object(m, "project_shell", return_value="zsh"), \
             _mock.patch.object(m, "verify_repos_reachable"), \
             _mock.patch.object(m, "vm_exists", return_value=True), \
             _mock.patch.object(m, "run"), \
             _mock.patch.object(m, "push_files_to_vm"), \
             _mock.patch.object(m, "render_git_templates"), \
             _mock.patch.object(m, "run_provision_in_vm"), \
             _mock.patch.object(m, "clone_repo",
                                side_effect=__import__("subprocess").CalledProcessError(1, "git")):
            ns = _mock.Mock(project="blog", dry_run=False)
            rc = m.cmd_up(ns)
        self.assertNotEqual(rc, 0)
        ref.assert_not_called()

    def test_cmd_destroy_calls_refresh_on_success(self):
        with _mock.patch.object(m, "refresh_ssh_config") as ref, \
             _mock.patch("subprocess.run"), \
             _mock.patch.object(m, "run") as run_mock:
            ns = _mock.Mock(project="blog", force=True)
            rc = m.cmd_destroy(ns)
        self.assertEqual(rc, 0)
        ref.assert_called_once()
        delete_calls = [c for c in run_mock.call_args_list
                        if c.args and c.args[0][:2] == ["limactl", "delete"]]
        self.assertTrue(delete_calls)


class TestDoctorSshConfig(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = _Path(self._tmp.name)
        (self.home / ".ssh").mkdir()
        self._patch_path = _mock.patch.object(
            m, "SSH_CONFIG_PATH", self.home / ".ssh" / "config"
        )
        self._patch_path.start()

    def tearDown(self):
        self._patch_path.stop()
        self._tmp.cleanup()

    def _run(self, projects: dict, vms: dict, list_stdout: str = ""):
        out: list[str] = []
        def fake_run(cmd, *args, **kwargs):
            if cmd[:3] == ["limactl", "show-ssh", "--format=options"]:
                vm = cmd[-1]
                if vm in vms:
                    return _mock.Mock(returncode=0, stdout=vms[vm], stderr="")
                return _mock.Mock(returncode=1, stdout="", stderr="no instance")
            if cmd[:2] == ["limactl", "list"]:
                return _mock.Mock(returncode=0, stdout=list_stdout, stderr="")
            raise AssertionError(f"unexpected: {cmd}")
        state = {"checks": 0, "fails": 0}
        with _mock.patch.object(m, "load_projects", return_value=projects), \
             _mock.patch("subprocess.run", side_effect=fake_run), \
             _mock.patch("builtins.print", side_effect=lambda *a, **k: out.append(" ".join(str(x) for x in a))):
            m.doctor_ssh_config(state)
        return out, state

    def test_warns_when_block_missing_but_vm_exists(self):
        out, _ = self._run(
            projects={"blog": {"repos": []}},
            vms={"blog": "Hostname=127.0.0.1\nPort=60123\nUser=u\nIdentityFile=/p\n"},
            list_stdout="blog\n",
        )
        self.assertTrue(any("WARN" in line and "managed block" in line for line in out), out)

    def test_ok_when_block_matches_lima(self):
        config = self.home / ".ssh" / "config"
        config.write_text(m.render_block([
            ("blog", {"Hostname": "127.0.0.1", "Port": "60123", "User": "u", "IdentityFile": "/p"}),
        ]))
        config.chmod(0o600)
        out, _ = self._run(
            projects={"blog": {"repos": []}},
            vms={"blog": "Hostname=127.0.0.1\nPort=60123\nUser=u\nIdentityFile=/p\n"},
            list_stdout="blog\n",
        )
        self.assertFalse(any("WARN" in line for line in out), out)

    def test_warns_on_stale_port(self):
        config = self.home / ".ssh" / "config"
        config.write_text(m.render_block([
            ("blog", {"Hostname": "127.0.0.1", "Port": "60123", "User": "u", "IdentityFile": "/p"}),
        ]))
        config.chmod(0o600)
        out, _ = self._run(
            projects={"blog": {"repos": []}},
            vms={"blog": "Hostname=127.0.0.1\nPort=60999\nUser=u\nIdentityFile=/p\n"},
            list_stdout="blog\n",
        )
        self.assertTrue(any("port" in line.lower() and "60123" in line for line in out), out)

    def test_warns_on_orphan_entry(self):
        config = self.home / ".ssh" / "config"
        config.write_text(m.render_block([
            ("old", {"Hostname": "127.0.0.1", "Port": "60111", "User": "u", "IdentityFile": "/p"}),
        ]))
        config.chmod(0o600)
        out, _ = self._run(
            projects={"blog": {"repos": []}},
            vms={},
            list_stdout="",
        )
        self.assertTrue(any("orphan" in line.lower() or "no longer exists" in line.lower() for line in out), out)

    def test_warns_on_loose_permissions(self):
        config = self.home / ".ssh" / "config"
        config.write_text(m.render_block([
            ("blog", {"Hostname": "127.0.0.1", "Port": "60123", "User": "u", "IdentityFile": "/p"}),
        ]))
        config.chmod(0o644)
        try:
            out, _ = self._run(
                projects={"blog": {"repos": []}},
                vms={"blog": "Hostname=127.0.0.1\nPort=60123\nUser=u\nIdentityFile=/p\n"},
                list_stdout="blog\n",
            )
            self.assertTrue(any("0600" in line or "permissions" in line.lower() for line in out), out)
        finally:
            config.chmod(0o600)


if __name__ == "__main__":
    unittest.main()
