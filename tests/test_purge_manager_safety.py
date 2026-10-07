import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import purge_manager


class PurgeManagerSafetyTests(unittest.TestCase):
    def test_allows_descendant_of_oec_root(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            models = base / "models"
            target = models / "hub" / "models--example--model"
            target.mkdir(parents=True)
            (target / "weights.bin").write_bytes(b"x" * 100)

            with mock.patch.object(
                purge_manager,
                "SYSTEM_DIRS",
                {"models": str(models), "cache": str(base / "cache"), "outputs": str(base / "outputs"), "inputs": str(base / "inputs")},
            ):
                self.assertTrue(purge_manager.DiskPurgeManager.purge_directory(target, "test"))
                self.assertFalse(target.exists())

    def test_refuses_oec_root_itself(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            models = base / "models"
            models.mkdir()
            (models / "important.bin").write_bytes(b"safe")

            with mock.patch.object(
                purge_manager,
                "SYSTEM_DIRS",
                {"models": str(models), "cache": str(base / "cache"), "outputs": str(base / "outputs"), "inputs": str(base / "inputs")},
            ):
                self.assertFalse(purge_manager.DiskPurgeManager.purge_directory(models, "root"))
                self.assertTrue((models / "important.bin").exists())

    def test_refuses_path_outside_oec_roots(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            models = base / "models"
            outside = base / "outside"
            models.mkdir()
            outside.mkdir()
            marker = outside / "important.bin"
            marker.write_bytes(b"do-not-delete")

            with mock.patch.object(
                purge_manager,
                "SYSTEM_DIRS",
                {"models": str(models), "cache": str(base / "cache"), "outputs": str(base / "outputs"), "inputs": str(base / "inputs")},
            ):
                self.assertFalse(purge_manager.DiskPurgeManager.purge_directory(outside, "outside"))
                self.assertTrue(marker.exists())

    def test_refuses_symlink_target(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            models = base / "models"
            outside = base / "outside"
            models.mkdir()
            outside.mkdir()
            marker = outside / "important.bin"
            marker.write_bytes(b"do-not-delete")
            link = models / "link"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks unavailable")

            with mock.patch.object(
                purge_manager,
                "SYSTEM_DIRS",
                {"models": str(models), "cache": str(base / "cache"), "outputs": str(base / "outputs"), "inputs": str(base / "inputs")},
            ):
                self.assertFalse(purge_manager.DiskPurgeManager.purge_directory(link, "symlink"))
                self.assertTrue(marker.exists())


if __name__ == "__main__":
    unittest.main()
