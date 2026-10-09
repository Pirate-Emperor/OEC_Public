import errno
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

from tools import setup_ltx_runtime as setup


@unittest.skipUnless(shutil.which("git"), "Git is required for local checkout tests")
class LTXRuntimeSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="oec-ltx-setup-test-")
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self._git("init", cwd=self.source)
        self._git("config", "user.name", "OEC test", cwd=self.source)
        self._git("config", "user.email", "oec-test@example.invalid", cwd=self.source)

        for relative in setup.REQUIRED_RELATIVE_DIRS:
            path = self.source / relative
            path.mkdir(parents=True, exist_ok=True)
        (self.source / "packages/ltx-core/src/ltx_core.py").write_text(
            "# fixture core package\n", encoding="utf-8"
        )
        (self.source / "packages/ltx-pipelines/src/ltx_pipelines.py").write_text(
            "# fixture pipeline package\n", encoding="utf-8"
        )
        self._git("add", ".", cwd=self.source)
        self._git("commit", "-m", "fixture pinned LTX source", cwd=self.source)
        self.commit = self._git("rev-parse", "HEAD", cwd=self.source)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _git(*args, cwd):
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise AssertionError(result.stderr or result.stdout)
        return result.stdout.strip()

    def test_default_path_uses_core_config_cache_root(self):
        fake_config = types.SimpleNamespace(
            SYSTEM_DIRS={"cache": str(self.root / "configured-cache")}
        )
        with patch.dict("sys.modules", {"core_config": fake_config}):
            with patch.dict(os.environ, {"AIEROS_LTX_REPO_DIR": ""}):
                resolved = setup.resolve_runtime_dir()

        self.assertEqual(
            resolved,
            self.root / "configured-cache" / "third_party" / "LTX-2",
        )

    def test_explicit_path_takes_precedence(self):
        explicit = self.root / "explicit" / "LTX-2"
        with patch.dict(os.environ, {"AIEROS_LTX_REPO_DIR": str(self.root / "env-path")}):
            self.assertEqual(setup.resolve_runtime_dir(str(explicit)), explicit)

    def test_clones_and_validates_pinned_checkout_before_publishing(self):
        target = self.root / "cache" / "third_party" / "LTX-2"
        target.parent.mkdir(parents=True)

        with patch.object(setup.subprocess, "run", wraps=subprocess.run) as git_runner:
            result = setup.prepare_runtime(
                target,
                repo_url=str(self.source),
                commit_sha=self.commit,
                configure_environment=False,
            )

        network_git_calls = [
            call for call in git_runner.call_args_list
            if call.args
            and call.args[0]
            and call.args[0][0] == "git"
            and call.args[0][1] in {"fetch", "checkout"}
        ]
        self.assertEqual(len(network_git_calls), 2)
        for call in network_git_calls:
            self.assertEqual(
                call.kwargs["env"]["GIT_LFS_SKIP_SMUDGE"],
                "1",
                "Fetch/checkout must not download Git LFS media assets.",
            )

        self.assertEqual(result, target)
        self.assertTrue((target / "packages/ltx-core/src").is_dir())
        self.assertTrue((target / "packages/ltx-pipelines/src").is_dir())
        self.assertEqual(self._git("rev-parse", "HEAD", cwd=target), self.commit)
        self.assertEqual(
            self._git("remote", "get-url", "origin", cwd=target),
            str(self.source),
        )
        self.assertEqual(self._git("status", "--porcelain", cwd=target), "")
        self.assertEqual(
            [p.name for p in target.parent.iterdir()],
            ["LTX-2"],
            "The staging directory should be renamed away after success.",
        )

    def test_refuses_to_overwrite_existing_directory(self):
        target = self.root / "cache" / "LTX-2"
        target.mkdir(parents=True)
        sentinel = target / "keep.txt"
        sentinel.write_text("preserve me", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            setup.prepare_runtime(
                target,
                repo_url=str(self.source),
                commit_sha=self.commit,
                configure_environment=False,
            )

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve me")
        self.assertEqual(list(target.parent.iterdir()), [target])

    def test_refuses_existing_symlink_without_following_or_replacing_it(self):
        target = self.root / "cache" / "LTX-2"
        preserved = self.root / "preserved"
        preserved.mkdir()
        sentinel = preserved / "keep.txt"
        sentinel.write_text("preserve symlink target", encoding="utf-8")
        target.parent.mkdir()
        try:
            target.symlink_to(preserved, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symlink creation unavailable: {exc}")

        with self.assertRaises(FileExistsError):
            setup.prepare_runtime(
                target,
                repo_url=str(self.source),
                commit_sha=self.commit,
                configure_environment=False,
            )

        self.assertTrue(target.is_symlink())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve symlink target")

    def test_atomic_publish_does_not_replace_racing_empty_target(self):
        staging = self.root / "prepared-staging"
        staging.mkdir()
        (staging / "keep.txt").write_text("prepared", encoding="utf-8")
        target = self.root / "target"
        target.mkdir()

        with self.assertRaises(FileExistsError):
            setup._publish_without_overwrite(staging, target)

        self.assertTrue(staging.is_dir())
        self.assertEqual((staging / "keep.txt").read_text(encoding="utf-8"), "prepared")
        self.assertEqual(list(target.iterdir()), [])

    def test_fallback_publish_when_filesystem_rejects_renameat2(self):
        staging = self.root / "prepared-staging"
        staging.mkdir()
        (staging / "keep.txt").write_text("prepared", encoding="utf-8")
        target = self.root / "target"

        with patch.object(
            setup, "_renameat2_noreplace", return_value=(-1, errno.EINVAL)
        ):
            setup._publish_without_overwrite(staging, target)

        self.assertFalse(staging.exists())
        self.assertEqual((target / "keep.txt").read_text(encoding="utf-8"), "prepared")

    def test_fallback_rechecks_target_before_normal_rename(self):
        staging = self.root / "prepared-staging"
        staging.mkdir()
        (staging / "keep.txt").write_text("prepared", encoding="utf-8")
        target = self.root / "target"

        def target_appears_during_renameat2(_staging, _target):
            target.mkdir()
            (target / "existing.txt").write_text("preserve", encoding="utf-8")
            return -1, errno.EINVAL

        with patch.object(
            setup,
            "_renameat2_noreplace",
            side_effect=target_appears_during_renameat2,
        ):
            with self.assertRaises(FileExistsError):
                setup._publish_without_overwrite(staging, target)

        self.assertTrue(staging.is_dir())
        self.assertEqual((staging / "keep.txt").read_text(encoding="utf-8"), "prepared")
        self.assertEqual((target / "existing.txt").read_text(encoding="utf-8"), "preserve")

    def test_failed_pinned_checkout_cleans_only_its_staging_directory(self):
        target = self.root / "cache" / "third_party" / "LTX-2"
        target.parent.mkdir(parents=True)
        bad_sha = "0" * 40

        with self.assertRaises(RuntimeError):
            setup.prepare_runtime(
                target,
                repo_url=str(self.source),
                commit_sha=bad_sha,
                configure_environment=False,
            )

        self.assertFalse(target.exists())
        self.assertEqual(list(target.parent.iterdir()), [])

    def test_rejects_checkout_without_required_ltx_packages(self):
        incomplete = self.root / "incomplete"
        incomplete.mkdir()
        self._git("init", cwd=incomplete)
        self._git("config", "user.name", "OEC test", cwd=incomplete)
        self._git("config", "user.email", "oec-test@example.invalid", cwd=incomplete)
        (incomplete / "README.md").write_text("not an LTX package", encoding="utf-8")
        self._git("add", ".", cwd=incomplete)
        self._git("commit", "-m", "incomplete fixture", cwd=incomplete)
        commit = self._git("rev-parse", "HEAD", cwd=incomplete)
        target = self.root / "cache" / "LTX-2"
        target.parent.mkdir(parents=True)

        with self.assertRaisesRegex(RuntimeError, "missing required package directories"):
            setup.prepare_runtime(
                target,
                repo_url=str(incomplete),
                commit_sha=commit,
                configure_environment=False,
            )

        self.assertFalse(target.exists())
        self.assertEqual(list(target.parent.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
