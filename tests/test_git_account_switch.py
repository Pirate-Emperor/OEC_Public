import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "git_account_switch.py"
spec = importlib.util.spec_from_file_location("git_account_switch", MODULE_PATH)
git_account_switch = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(git_account_switch)


class RemoteParsingTests(unittest.TestCase):
    def test_https_remote(self):
        self.assertEqual(
            git_account_switch.remote_details_from_url("https://github.com/xflexwork/OEC.git"),
            ("https", "xflexwork/OEC"),
        )

    def test_ssh_remote(self):
        self.assertEqual(
            git_account_switch.remote_details_from_url("git@github.com:xflexwork/OEC.git"),
            ("ssh", "xflexwork/OEC"),
        )

    def test_ssh_scheme_remote(self):
        self.assertEqual(
            git_account_switch.remote_details_from_url("ssh://git@github.com/xflexwork/OEC.git"),
            ("ssh", "xflexwork/OEC"),
        )

    def test_embedded_credentials_rejected(self):
        with self.assertRaises(git_account_switch.SwitchError):
            git_account_switch.remote_details_from_url("https://user:secret@github.com/xflexwork/OEC.git")

    def test_non_github_remote_rejected(self):
        with self.assertRaises(git_account_switch.SwitchError):
            git_account_switch.remote_details_from_url("https://example.com/xflexwork/OEC.git")

    def test_invalid_repo_path_rejected(self):
        with self.assertRaises(git_account_switch.SwitchError):
            git_account_switch.remote_details_from_url("https://github.com/xflexwork/not/a/repo.git")


if __name__ == "__main__":
    unittest.main()
