"""Regression tests for safe core_config trash cleanup behavior."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CoreConfigCleanupTests(unittest.TestCase):
    def test_cleanup_is_opt_in_and_never_deletes_jupyter_workspaces(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            trash_files = home / ".local/share/Trash/files"
            trash_info = home / ".local/share/Trash/info"
            workspaces = home / ".jupyter/lab/workspaces"
            for directory in (trash_files, trash_info, workspaces):
                directory.mkdir(parents=True)
            (trash_files / "recoverable.txt").write_text("keep until explicit consent")
            (trash_info / "recoverable.trashinfo").write_text("[Trash Info]")
            (workspaces / "workspace.json").write_text('{"workspace": "keep"}')

            repo_root = Path(__file__).resolve().parents[1]
            script = r"""
from pathlib import Path
import core_config

home = Path.home()
trash_file = home / ".local/share/Trash/files/recoverable.txt"
trash_info = home / ".local/share/Trash/info/recoverable.trashinfo"
workspace = home / ".jupyter/lab/workspaces/workspace.json"

assert trash_file.exists()
assert trash_info.exists()
assert workspace.exists()

assert core_config.clear_system_trash() is False
assert trash_file.exists(), "default call must not delete recoverable trash"
assert trash_info.exists(), "default call must not delete trash metadata"
assert workspace.exists(), "Jupyter workspace must never be deleted"

assert core_config.clear_system_trash(confirm=True) is True
assert not trash_file.exists(), "explicit confirmation should clear trash files"
assert not trash_info.exists(), "explicit confirmation should clear trash metadata"
assert workspace.exists(), "even explicit trash cleanup must preserve Jupyter workspace data"
print("CORE_CONFIG_CLEANUP_REGRESSION=PASS")
"""
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["AIEROS_BASE_DIR"] = str(root / "aireos")
            env["PYTHONPATH"] = str(repo_root)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run(
                [sys.executable, "-c", script],
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            self.assertIn("CORE_CONFIG_CLEANUP_REGRESSION=PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
