"""Regression tests for TRELLIS offline pipeline config resolution."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.trellis_offline import (
    BUNDLED_CONFIG,
    MODEL_ID,
    PINNED_CONFIG_REVISION,
    is_valid_pipeline_config,
    offline_hub_mode,
    prepare_local_trellis_snapshot,
)


class TrellisOfflineConfigTests(unittest.TestCase):
    def test_vendored_config_is_well_formed_and_has_expected_models(self):
        payload = json.loads(BUNDLED_CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(payload["name"], "Trellis2ImageTo3DPipeline")
        self.assertEqual(len(payload["args"]["models"]), 8)
        self.assertTrue(is_valid_pipeline_config(BUNDLED_CONFIG))

    def test_pinned_weight_snapshot_gets_config_in_tmp_overlay_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            snapshot = root / PINNED_CONFIG_REVISION
            snapshot.mkdir()
            (snapshot / "model.safetensors").write_bytes(b"fixture-weights")
            temp_root = root / "tmp"
            temp_root.mkdir()
            original_files = {p.name for p in snapshot.iterdir()}
            overlay_path, owner = prepare_local_trellis_snapshot(
                snapshot, repo_id=MODEL_ID, temp_root=temp_root
            )
            try:
                overlay = Path(overlay_path)
                self.assertNotEqual(overlay.resolve(), snapshot.resolve())
                self.assertTrue((overlay / "pipeline.json").is_file())
                self.assertTrue(is_valid_pipeline_config(overlay / "pipeline.json"))
                self.assertTrue((overlay / "model.safetensors").is_symlink())
                self.assertEqual((overlay / "model.safetensors").read_bytes(), b"fixture-weights")
                self.assertEqual({p.name for p in snapshot.iterdir()}, original_files)
                self.assertFalse((snapshot / "pipeline.json").exists())
            finally:
                owner.cleanup()

    def test_unknown_snapshot_without_config_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            snapshot = root / "other-revision"
            snapshot.mkdir()
            with self.assertRaisesRegex(RuntimeError, "BLOCKED_TRELLIS_CONFIG"):
                prepare_local_trellis_snapshot(snapshot, repo_id=MODEL_ID, temp_root=root)

    def test_existing_valid_config_is_copied_without_mutating_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            snapshot = root / "custom-revision"
            snapshot.mkdir()
            (snapshot / "pipeline.json").write_text(
                BUNDLED_CONFIG.read_text(encoding="utf-8"), encoding="utf-8"
            )
            (snapshot / "weight.bin").write_bytes(b"x")
            overlay_path, owner = prepare_local_trellis_snapshot(
                snapshot, repo_id="my/local-model", temp_root=root
            )
            try:
                overlay = Path(overlay_path)
                self.assertNotEqual(overlay.resolve(), snapshot.resolve())
                self.assertTrue(is_valid_pipeline_config(overlay / "pipeline.json"))
                self.assertTrue((overlay / "weight.bin").is_symlink())
                self.assertTrue((snapshot / "pipeline.json").is_file())
            finally:
                owner.cleanup()

    def test_offline_hub_mode_sets_and_restores_environment(self):
        names = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
        original = {name: os.environ.get(name) for name in names}
        try:
            os.environ.pop("HF_HUB_OFFLINE", None)
            os.environ.pop("TRANSFORMERS_OFFLINE", None)
            with offline_hub_mode():
                self.assertEqual(os.environ["HF_HUB_OFFLINE"], "1")
                self.assertEqual(os.environ["TRANSFORMERS_OFFLINE"], "1")
            self.assertNotIn("HF_HUB_OFFLINE", os.environ)
            self.assertNotIn("TRANSFORMERS_OFFLINE", os.environ)
        finally:
            for name, value in original.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_cache_metadata_is_mirrored_to_tmp_not_shared(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            temp_root = root / "tmp"
            temp_root.mkdir()
            cache_root = root / "cache"
            repo = cache_root / "models--example--model"
            snapshot = repo / "snapshots" / "rev123"
            snapshot.mkdir(parents=True)
            (snapshot / "config.json").write_text("{}", encoding="utf-8")
            (repo / "refs").mkdir()
            (repo / "refs" / "main").write_text("rev123\n", encoding="utf-8")
            main_snapshot = root / PINNED_CONFIG_REVISION
            main_snapshot.mkdir()
            (main_snapshot / "weight.safetensors").write_bytes(b"dummy")
            overlay_path, owner = prepare_local_trellis_snapshot(
                main_snapshot, repo_id=MODEL_ID, cache_roots=(cache_root,),
                temp_root=temp_root
            )
            try:
                overlay = Path(overlay_path)
                mirrored_cache = Path(owner.name) / "hf-hub"
                mirrored_snapshot = mirrored_cache / "models--example--model" / "snapshots" / "rev123"
                self.assertTrue(mirrored_snapshot.is_symlink())
                self.assertEqual(mirrored_snapshot.resolve(), snapshot.resolve())
                self.assertEqual(
                    (mirrored_cache / "models--example--model" / "refs" / "main").read_text(encoding="utf-8"),
                    "rev123\n",
                )
                self.assertTrue((Path(owner.name) / "hf-home").is_dir())
                self.assertTrue((Path(owner.name) / "hf-hub").is_dir())
                self.assertFalse((main_snapshot / "pipeline.json").exists())
                self.assertTrue((overlay / "pipeline.json").is_file())
            finally:
                owner.cleanup()


if __name__ == "__main__":
    unittest.main()
