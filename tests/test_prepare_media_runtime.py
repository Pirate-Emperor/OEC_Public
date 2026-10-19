"""Offline acceptance tests for output reserve inspection and speech runtime preflight."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tools.prepare_media_runtime as runtime


class PrepareMediaRuntimeTests(unittest.TestCase):
    def _setup(self, actual_outputs=0.29):
        temp = tempfile.TemporaryDirectory(prefix="oec-prepare-audio-runtime-")
        root = Path(temp.name)
        (root / "storage_config.json").write_text(json.dumps({
            "minimum_reserve_gb": 0.25,
            "directories": [
                {"name": "models", "minimum_reserve_gb": 1.0, "reserve_target_gb": 5.0},
                {"name": "outputs", "minimum_reserve_gb": 0.25, "reserve_target_gb": 0.5},
            ],
        }), encoding="utf-8")
        rows = {
            "models": {"state": "WARNING", "actual_gb": 219.97, "target_gb": 280.0, "reserve_gb": 60.043},
            "outputs": {"state": "WARNING", "actual_gb": actual_outputs, "target_gb": 1.0, "reserve_gb": 0.7172},
        }
        reserve_reports = {
            "models": {"area": "models", "path": "/tmp/models/.storage_reserve.bin",
                       "size_bytes": int(60.043 * 1024**3), "allocated_bytes": int(60.043 * 1024**3),
                       "sample_bytes": 16, "sample_prefix_hex": "00" * 16, "reserve_gb": 60.043},
            "outputs": {"area": "outputs", "path": "/tmp/outputs/.storage_reserve.bin",
                        "size_bytes": int(0.7172 * 1024**3), "allocated_bytes": int(0.7172 * 1024**3),
                        "sample_bytes": 16, "sample_prefix_hex": "00" * 16, "reserve_gb": 0.7172},
        }
        return temp, root, rows, reserve_reports

    def test_existing_reserve_is_read_but_never_resized(self):
        temp, root, rows, reserves = self._setup()
        self.addCleanup(temp.cleanup)
        with mock.patch.object(runtime, "ROOT", root), \
             mock.patch.object(runtime, "_read_status", return_value=rows), \
             mock.patch.object(runtime, "inspect_managed_reserve", side_effect=lambda area, reported, dirs: reserves[area]), \
             mock.patch.object(runtime, "_run") as run:
            result = runtime._prepare_output_reserve()
        run.assert_not_called()
        self.assertFalse(result["output_reserve_resized"])
        self.assertFalse(result["reserve_mutation_attempted"])
        self.assertEqual(result["reserve_files"]["outputs"]["sample_bytes"], 16)
        self.assertAlmostEqual(result["projected_output_usage_with_artifacts_gb"], 0.44, places=3)

    def test_artifact_budget_still_fails_if_actual_content_exceeds_target(self):
        temp, root, rows, reserves = self._setup(actual_outputs=0.90)
        self.addCleanup(temp.cleanup)
        with mock.patch.object(runtime, "ROOT", root), \
             mock.patch.object(runtime, "_read_status", return_value=rows), \
             mock.patch.object(runtime, "inspect_managed_reserve", side_effect=lambda area, reported, dirs: reserves[area]), \
             mock.patch.object(runtime, "_run") as run:
            with self.assertRaisesRegex(RuntimeError, "outputs artifact budget denied"):
                runtime._prepare_output_reserve()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
