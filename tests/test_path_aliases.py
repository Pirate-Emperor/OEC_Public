"""Safe alias creation tests for OEC's singular canonical paths."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.ensure_path_aliases import ensure_alias


class EnsurePathAliasesTests(unittest.TestCase):
    def test_report_only_does_not_create_filesystem_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "aireos_dataset"
            target.mkdir()
            alias = root / "aireos_datasets"
            result = ensure_alias(alias, target, apply=False)
            self.assertTrue(result.startswith("PLAN_CREATE"))
            self.assertFalse(alias.exists())
            self.assertFalse(alias.is_symlink())

    def test_apply_creates_a_verified_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "aireos_dataset"
            target.mkdir()
            alias = root / "aireos_datasets"
            result = ensure_alias(alias, target, apply=True)
            self.assertTrue(result.startswith("ALIAS_CREATED"))
            self.assertTrue(alias.is_symlink())
            self.assertEqual(alias.resolve(), target.resolve())

    def test_existing_real_directory_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "aireos_dataset"
            target.mkdir()
            alias = root / "aireos_datasets"
            alias.mkdir()
            marker = alias / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            result = ensure_alias(alias, target, apply=True)
            self.assertTrue(result.startswith("REFUSED existing_non_symlink"))
            self.assertTrue(marker.is_file())
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_wrong_symlink_is_not_repointed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "canonical"
            wrong = root / "wrong"
            target.mkdir()
            wrong.mkdir()
            alias = root / "alias"
            alias.symlink_to(wrong, target_is_directory=True)
            result = ensure_alias(alias, target, apply=True)
            self.assertTrue(result.startswith("REFUSED wrong_symlink"))
            self.assertEqual(alias.resolve(), wrong.resolve())

    def test_missing_target_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = ensure_alias(root / "alias", root / "missing", apply=True)
            self.assertTrue(result.startswith("REFUSED target_not_directory"))
            self.assertFalse((root / "alias").exists())


if __name__ == "__main__":
    unittest.main()
