"""Offline path and checkpoint-layout tests for the isolated ACE-Step bootstrap."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import prepare_ace_step_runtime as runtime


class AceStepRuntimeTests(unittest.TestCase):
    def test_pristine_no_checkout_clone_allows_only_empty_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ACE-Step-1.5"
            root.mkdir()
            (root / ".git").mkdir()
            (root / "examples" / "simple_mode").mkdir(parents=True)
            status = "D  examples/simple_mode/example.json\nD  pyproject.toml\nD  uv.lock"
            self.assertTrue(runtime._is_pristine_no_checkout_tree(root, status))
            (root / "examples" / "simple_mode" / "local-note.txt").write_text(
                "preserve me", encoding="utf-8"
            )
            self.assertFalse(runtime._is_pristine_no_checkout_tree(root, status))

    def test_preexisting_dirty_no_checkout_is_never_reclassified_as_recoverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ACE-Step-1.5"
            root.mkdir()
            (root / ".git").mkdir()
            (root / "examples" / "simple_mode").mkdir(parents=True)
            status = "D  examples/simple_mode/example.json\nD  pyproject.toml\nD  uv.lock"
            with mock.patch.object(runtime, "_run") as run:
                with mock.patch.object(runtime, "_git", side_effect=[
                    "https://github.com/ace-step/ACE-Step-1.5.git", status
                ]):
                    with self.assertRaisesRegex(RuntimeError, "dirty; refusing"):
                        runtime._ensure_source_checkout(root)
            run.assert_not_called()

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

    @staticmethod
    def _small_checkpoint_layout():
        return {
            name: {**spec, "min_weight_bytes": 8}
            for name, spec in runtime.CHECKPOINT_LAYOUT.items()
        }

    @staticmethod
    def _write_component(root: Path, name: str, weight_bytes: int = 8) -> Path:
        layout = runtime.CHECKPOINT_LAYOUT[name]
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / layout["weight_file"]).write_bytes(b"x" * weight_bytes)
        for required_file in layout["required_files"]:
            (folder / required_file).write_text("{}", encoding="utf-8")
        return folder

    def test_checkpoint_status_requires_all_four_complete_model_groups(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            runtime.CHECKPOINT_LAYOUT, self._small_checkpoint_layout()
        ):
            root = Path(tmp) / "ace-step-1.5"
            for folder in runtime.REQUIRED_CHECKPOINT_DIRS:
                self._write_component(root, folder)
            status = runtime.checkpoint_status(root)
            self.assertTrue(status["complete"])
            self.assertEqual(status["missing"], [])
            (root / "vae" / runtime.CHECKPOINT_LAYOUT["vae"]["weight_file"]).unlink()
            status = runtime.checkpoint_status(root)
            self.assertFalse(status["complete"])
            self.assertEqual(status["missing"], ["vae"])

    def test_partial_turbo_checkpoint_is_not_marked_complete(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            runtime.CHECKPOINT_LAYOUT, self._small_checkpoint_layout()
        ):
            root = Path(tmp) / "ace-step-1.5"
            for folder in runtime.REQUIRED_CHECKPOINT_DIRS:
                self._write_component(root, folder)
            self._write_component(root, "acestep-v15-turbo", weight_bytes=7)
            status = runtime.checkpoint_status(root)
            self.assertFalse(status["complete"])
            self.assertEqual(status["missing"], ["acestep-v15-turbo"])

    def test_selected_main_components_do_not_require_unused_bundled_17b_lm(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            runtime.CHECKPOINT_LAYOUT, self._small_checkpoint_layout()
        ):
            root = Path(tmp) / "ace-step-1.5"
            for folder in runtime.SELECTED_MAIN_COMPONENT_DIRS:
                self._write_component(root, folder)
            self.assertTrue(runtime.selected_main_components_complete(root))
            self.assertFalse((root / "acestep-5Hz-lm-1.7B").exists())

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

    def test_ensure_reuses_a_complete_pinned_runtime_without_storage_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home, cache, models = root / "home", root / "cache", root / "models"
            paths = runtime.build_paths(home, cache, models)
            paths["source_root"].mkdir(parents=True)
            (paths["source_root"] / ".git").mkdir()
            paths["python"].parent.mkdir(parents=True)
            paths["python"].write_text("# verified fixture interpreter", encoding="utf-8")
            dirs = {"cache": str(cache), "models": str(models)}
            runtime_report = {"source_commit": runtime.SOURCE_COMMIT,
                              "runtime": {"torch_cuda": "fixture", "cuda_available": True}}
            output = io.StringIO()
            with mock.patch.object(Path, "home", return_value=home), \
                 mock.patch.object(runtime, "_system_dirs", return_value=dirs), \
                 mock.patch.object(runtime, "_git", return_value=runtime.SOURCE_COMMIT), \
                 mock.patch.object(runtime, "checkpoint_status", return_value={"complete": True, "missing": []}), \
                 mock.patch.object(runtime, "_verify_runtime", return_value=runtime_report) as verify, \
                 mock.patch.object(runtime, "_admit_runtime_writes", side_effect=AssertionError("must not request writes")), \
                 mock.patch.object(runtime, "install", side_effect=AssertionError("must not reinstall")):
                with contextlib.redirect_stdout(output):
                    result = runtime.ensure()
            self.assertEqual(result, 0)
            verify.assert_called_once_with(paths, require_models=True)
            record = json.loads(output.getvalue().split("ACE_STEP_RUNTIME_ACCEPTANCE ", 1)[1])
            self.assertEqual(record["action"], "reused_existing_verified_runtime")
            self.assertFalse(record["storage_write_admission_required"])
            self.assertFalse(record["reserve_file_accessed"])

    def test_ensure_falls_back_to_guarded_install_when_existing_source_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home, cache, models = root / "home", root / "cache", root / "models"
            paths = runtime.build_paths(home, cache, models)
            paths["source_root"].mkdir(parents=True)
            (paths["source_root"] / ".git").mkdir()
            paths["python"].parent.mkdir(parents=True)
            paths["python"].write_text("# fixture interpreter", encoding="utf-8")
            dirs = {"cache": str(cache), "models": str(models)}
            with mock.patch.object(Path, "home", return_value=home), \
                 mock.patch.object(runtime, "_system_dirs", return_value=dirs), \
                 mock.patch.object(runtime, "_git", return_value="0" * 40), \
                 mock.patch.object(runtime, "checkpoint_status", return_value={"complete": True, "missing": []}), \
                 mock.patch.object(runtime, "install", return_value=0) as install, \
                 mock.patch.object(runtime, "_verify_runtime") as verify:
                result = runtime.ensure()
            self.assertEqual(result, 0)
            install.assert_called_once_with()
            verify.assert_not_called()

    def test_ensure_fails_closed_if_existing_candidate_fails_runtime_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home, cache, models = root / "home", root / "cache", root / "models"
            paths = runtime.build_paths(home, cache, models)
            paths["source_root"].mkdir(parents=True)
            (paths["source_root"] / ".git").mkdir()
            paths["python"].parent.mkdir(parents=True)
            paths["python"].write_text("# fixture interpreter", encoding="utf-8")
            dirs = {"cache": str(cache), "models": str(models)}
            with mock.patch.object(Path, "home", return_value=home), \
                 mock.patch.object(runtime, "_system_dirs", return_value=dirs), \
                 mock.patch.object(runtime, "_git", return_value=runtime.SOURCE_COMMIT), \
                 mock.patch.object(runtime, "checkpoint_status", return_value={"complete": True, "missing": []}), \
                 mock.patch.object(runtime, "_verify_runtime", side_effect=RuntimeError("CUDA verification failed")), \
                 mock.patch.object(runtime, "install") as install:
                with self.assertRaisesRegex(RuntimeError, "CUDA verification failed"):
                    runtime.ensure()
            install.assert_not_called()



if __name__ == "__main__":
    unittest.main()
