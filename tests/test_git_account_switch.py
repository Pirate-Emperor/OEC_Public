import importlib.util
import os
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "git_account_switch.py"
spec = importlib.util.spec_from_file_location("git_account_switch", MODULE_PATH)
git_account_switch = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(git_account_switch)
HELPER_PATH = MODULE_PATH.with_name("git-credential-gh-account.sh")


class RemoteParsingTests(unittest.TestCase):
    def test_https_remote(self):
        self.assertEqual(git_account_switch.remote_details_from_url("https://github.com/xflexwork/OEC.git"),
                         ("https", "xflexwork/OEC"))

    def test_git_scp_remote(self):
        self.assertEqual(git_account_switch.remote_details_from_url("git@github.com:xflexwork/OEC.git"),
                         ("ssh", "xflexwork/OEC"))

    def test_ssh_scheme_remote(self):
        self.assertEqual(git_account_switch.remote_details_from_url("ssh://git@github.com/xflexwork/OEC.git"),
                         ("ssh", "xflexwork/OEC"))

    def test_embedded_https_credentials_rejected(self):
        with self.assertRaises(git_account_switch.SwitchError):
            git_account_switch.remote_details_from_url("https://user:secret@github.com/xflexwork/OEC.git")

    def test_nonstandard_ssh_user_rejected(self):
        with self.assertRaises(git_account_switch.SwitchError):
            git_account_switch.remote_details_from_url("ssh://other@github.com/xflexwork/OEC.git")

    def test_non_github_remote_rejected(self):
        with self.assertRaises(git_account_switch.SwitchError):
            git_account_switch.remote_details_from_url("https://example.com/xflexwork/OEC.git")

    def test_invalid_repo_path_rejected(self):
        with self.assertRaises(git_account_switch.SwitchError):
            git_account_switch.remote_details_from_url("https://github.com/xflexwork/not/a/repo.git")


class CredentialHelperTests(unittest.TestCase):
    def test_get_returns_selected_account_token_only_on_stdout(self):
        with tempfile.TemporaryDirectory() as temp:
            fake_gh = Path(temp) / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\n"
                "test \"$1\" = auth && test \"$2\" = token && "
                "test \"$5\" = --user && test \"$6\" = expected-account || exit 3\n"
                "printf 'fake-test-token\\n'\n",
                encoding="utf-8",
            )
            fake_gh.chmod(0o700)
            env = os.environ.copy()
            env["PATH"] = temp + os.pathsep + env.get("PATH", "")
            proc = subprocess.run(
                ["bash", str(HELPER_PATH), "--account", "expected-account", "get"],
                input="protocol=https\nhost=github.com\n\n", text=True, capture_output=True,
                env=env, check=False, timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("username=x-access-token", proc.stdout)
            self.assertIn("password=fake-test-token", proc.stdout)
            self.assertEqual(proc.stderr, "")

    def test_get_does_not_supply_credentials_for_other_host(self):
        with tempfile.TemporaryDirectory() as temp:
            fake_gh = Path(temp) / "gh"
            fake_gh.write_text("#!/usr/bin/env bash\necho SHOULD_NOT_RUN >&2\nexit 3\n", encoding="utf-8")
            fake_gh.chmod(0o700)
            env = os.environ.copy()
            env["PATH"] = temp + os.pathsep + env.get("PATH", "")
            proc = subprocess.run(
                ["bash", str(HELPER_PATH), "--account", "expected-account", "get"],
                input="protocol=https\nhost=example.com\n\n", text=True, capture_output=True,
                env=env, check=False, timeout=10,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, "")
            self.assertEqual(proc.stderr, "")

    def test_store_and_erase_are_noops(self):
        for action in ("store", "erase"):
            proc = subprocess.run(
                ["bash", str(HELPER_PATH), "--account", "expected-account", action],
                input="protocol=https\nhost=github.com\nusername=x-access-token\npassword=not-a-real-token\n\n",
                text=True, capture_output=True, check=False, timeout=10,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, "")
            self.assertEqual(proc.stderr, "")



class RepositoryPermissionTests(unittest.TestCase):
    def test_push_permission_must_be_true(self):
        with mock.patch.object(
            git_account_switch, "run",
            side_effect=["ephemeral-fake-token", "true"],
        ) as mocked:
            self.assertTrue(
                git_account_switch.verify_repository_push_permission(
                    "gh", "expected-account", "xflexwork/OEC"
                )
            )
        self.assertEqual(mocked.call_count, 2)
        self.assertNotIn("ephemeral-fake-token", str(mocked.call_args_list))

    def test_missing_push_permission_is_rejected(self):
        with mock.patch.object(
            git_account_switch, "run",
            side_effect=["ephemeral-fake-token", "false"],
        ):
            with self.assertRaises(git_account_switch.SwitchError):
                git_account_switch.verify_repository_push_permission(
                    "gh", "expected-account", "xflexwork/OEC"
                )

    def test_write_check_uses_git_push_dry_run(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="dry-run", stderr=""
        )
        with mock.patch.object(
            git_account_switch, "credential_helper_command", return_value="helper-command"
        ), mock.patch.object(
            git_account_switch.subprocess, "run", return_value=completed
        ) as mocked:
            git_account_switch.test_remote_write_access(
                "/tmp/oec-test",
                "https://github.com/xflexwork/OEC.git",
                "expected-account",
            )
        command = mocked.call_args.args[0]
        self.assertIn("--dry-run", command)
        self.assertIn("https://github.com/xflexwork/OEC.git", command)

if __name__ == "__main__":
    unittest.main()
