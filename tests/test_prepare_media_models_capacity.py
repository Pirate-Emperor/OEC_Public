"""Capacity-gate tests ensure model prep preserves its already-allocated reserve."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import prepare_media_models as models
import prepare_ace_step_runtime as ace_runtime


class ModelCapacityTests(unittest.TestCase):
    def test_download_budget_excludes_existing_reserve_and_never_resizes_it(self):
        status = {"state": "WARNING", "actual_gb": 219.97, "target_gb": 280.0, "reserve_gb": 60.043}
        reserve = {"area": "models", "path": "/tmp/models/.storage_reserve.bin",
                   "size_bytes": int(60.043 * 1024**3), "allocated_bytes": int(60.043 * 1024**3),
                   "sample_bytes": 16, "sample_prefix_hex": "00" * 16, "reserve_gb": 60.043}
        with mock.patch.object(models, "_read_model_storage_status", return_value=status), \
             mock.patch.object(models, "_effective_reserve_floor", return_value=60.0), \
             mock.patch.object(models, "inspect_managed_reserve", return_value=reserve), \
             mock.patch.object(models.subprocess, "run") as subprocess_run:
            report = models._manager_directory_capacity(15.0, 40.0, resize_reserve=True)
        subprocess_run.assert_not_called()
        self.assertFalse(report["reserve_resized"])
        self.assertFalse(report["reserve_resize_needed"])
        self.assertTrue(report["reserve_resize_requested_but_ignored"])
        self.assertAlmostEqual(report["projected_payload_plus_free_space_gb"], 236.97, places=2)
        self.assertEqual(report["reserve_file"]["sample_bytes"], 16)

    def test_payload_budget_still_respects_configured_models_target(self):
        status = {"state": "WARNING", "actual_gb": 279.0, "target_gb": 280.0, "reserve_gb": 60.043}
        reserve = {"area": "models", "path": "/tmp/models/.storage_reserve.bin",
                   "size_bytes": int(60.043 * 1024**3), "allocated_bytes": int(60.043 * 1024**3),
                   "sample_bytes": 16, "sample_prefix_hex": "00" * 16, "reserve_gb": 60.043}
        with mock.patch.object(models, "_read_model_storage_status", return_value=status), \
             mock.patch.object(models, "_effective_reserve_floor", return_value=60.0), \
             mock.patch.object(models, "inspect_managed_reserve", return_value=reserve), \
             mock.patch.object(models.subprocess, "run") as subprocess_run:
            with self.assertRaisesRegex(RuntimeError, "models payload budget denied"):
                models._manager_directory_capacity(15.0, 40.0, resize_reserve=True)
        subprocess_run.assert_not_called()



    def test_ace_model_cache_completion_rejects_partial_primary_weights(self):
        layout = {
            name: {**spec, "min_weight_bytes": 8}
            for name, spec in ace_runtime.CHECKPOINT_LAYOUT.items()
        }
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.dict(ace_runtime.CHECKPOINT_LAYOUT, layout):
            root = Path(tmp) / "ace-step-1.5"
            main_spec = {**models.MODEL_SPECS["ace-step-main"], "target": root}
            lm_root = root / "acestep-5Hz-lm-0.6B"
            lm_spec = {**models.MODEL_SPECS["ace-step-lm-0.6b"], "target": lm_root}
            with mock.patch.dict(models.MODEL_SPECS, {
                "ace-step-main": main_spec,
                "ace-step-lm-0.6b": lm_spec,
            }):
                def write_component(name, size=8):
                    part = root / name
                    part.mkdir(parents=True, exist_ok=True)
                    component = ace_runtime.CHECKPOINT_LAYOUT[name]
                    (part / component["weight_file"]).write_bytes(b"x" * size)
                    for required in component["required_files"]:
                        (part / required).write_text("{}", encoding="utf-8")

                for component in ace_runtime.SELECTED_MAIN_COMPONENT_DIRS:
                    write_component(component)
                self.assertTrue(models._is_complete("ace-step-main"))
                (root / "acestep-v15-turbo" / "model.safetensors").write_bytes(b"partial")
                self.assertFalse(models._is_complete("ace-step-main"))

                write_component("acestep-5Hz-lm-0.6B")
                self.assertTrue(models._is_complete("ace-step-lm-0.6b"))
                (lm_root / "model.safetensors").write_bytes(b"partial")
                self.assertFalse(models._is_complete("ace-step-lm-0.6b"))

if __name__ == "__main__":
    unittest.main()
