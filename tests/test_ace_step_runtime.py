"""Offline path and checkpoint-layout tests for the isolated ACE-Step bootstrap."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import prepare_ace_step_runtime as runtime


class AceStepRuntimeTests(unittest.TestCase):
    def test_pristine_no_checkout_clone_is_recognized_only_when_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ACE-Step-1.5"
            root.mkdir()
            (root / ".git").mkdir()
            status = "D  examples/example.json\nD  pyproject.toml\nD  uv.lock"
            self.assertTrue(runtime._is_pristine_no_checkout_tree(root, status))
            (root / "local-note.txt").write_text("preserve me", encoding="utf-8")
            self.assertFalse(runtime._is_pristine_no_checkout_tree(root, status))

    def test_no_checkout_recovery_rejects_modified_untracked_or_ambiguous_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ACE-Step-1.5"
            root.mkdir()
            (root / ".git").mkdir()
            self.assertFalse(runtime._is_pristine_no_checkout_tree(root, " M pyproject.toml"))
            self.assertFalse(runtime._is_pristine_no_checkout_tree(root, "?? local-note.txt"))
            self.assertFalse(runtime._is_pristine_no_checkout_tree(root, ""))

    def test_source_revision_is_immutable_and_valid(self):
        self.assertRegex(runtime.SOURCE_COMMIT, r"^[0-9a-f]{40}$")
        self.assertEqual(runtime.SOURCE_URL, "https://github.com/ace-step/ACE-Step-1.5.git")

    def test_code_environment_and_model_weights_use_separate_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = runtime.build_paths(root / "home", root / "cache", root / "models")
            self.assertEqual(paths["source_root"], (root / "cache" / "third_party" / "ACE-Step-1.5").resolve())
            self.assertEqual(paths["venv_root"], (root / "home" / ".local" / "venvs" / "oec-acestep-py311").resolve())
            self.assertEqual(paths["model_root"], (root / "models" / "ace-step-1.5").resolve())
            self.assertNotEqual(paths["source_root"], paths["model_root"])
            self.assertTrue(paths["source_root"].is_relative_to(paths["cache_root"]))
            self.assertTrue(paths["model_root"].is_relative_to(paths["models_root"]))

    def test_checkpoint_status_requires_all_four_model_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ace-step-1.5"
            for folder in runtime.REQUIRED_CHECKPOINT_DIRS:
                target = root / folder
                target.mkdir(parents=True)
                (target / "weights.safetensors").write_bytes(b"checkpoint")
            status = runtime.checkpoint_status(root)
            self.assertTrue(status["complete"])
            self.assertEqual(status["missing"], [])
            (root / "vae" / "weights.safetensors").unlink()
            status = runtime.checkpoint_status(root)
            self.assertFalse(status["complete"])
            self.assertEqual(status["missing"], ["vae"])

    def test_empty_files_do_not_count_as_checkpoint_weights(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "weights"
            folder.mkdir()
            (folder / "empty.safetensors").write_bytes(b"")
            (folder / "readme.txt").write_text("not a checkpoint", encoding="utf-8")
            self.assertFalse(runtime.has_weights(folder))
            (folder / "valid.bin").write_bytes(b"weight")
            self.assertTrue(runtime.has_weights(folder))

    def test_symlinked_checkpoint_folder_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            real.mkdir()
            (real / "weights.safetensors").write_bytes(b"weight")
            link = root / "link"
            link.symlink_to(real, target_is_directory=True)
            self.assertFalse(runtime.has_weights(link))

    def test_missing_model_root_reports_missing_groups_without_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = runtime.checkpoint_status(Path(tmp) / "not-downloaded")
            self.assertFalse(status["complete"])
            self.assertEqual(status["missing"], list(runtime.REQUIRED_CHECKPOINT_DIRS))


if __name__ == "__main__":
    unittest.main()
