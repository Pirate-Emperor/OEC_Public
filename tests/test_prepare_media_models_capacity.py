"""Capacity-gate tests ensure model prep preserves its already-allocated reserve."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import prepare_media_models as models


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


if __name__ == "__main__":
    unittest.main()
