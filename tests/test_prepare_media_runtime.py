"""Offline acceptance tests for output budgeting without reserve mutation."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tools.prepare_media_runtime as runtime


class PrepareMediaRuntimeTests(unittest.TestCase):
    def _setup(self, actual_outputs: float = 0.29):
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
            "models": {"state": "WARNING", "actual_gb": 250.30, "target_gb": 280.0, "reserve_gb": 29.83},
            "outputs": {"state": "WARNING", "actual_gb": actual_outputs, "target_gb": 1.0, "reserve_gb": 0.7172},
        }
        return temp, root, rows

    def test_existing_reserve_is_preserved_and_no_manager_resize_is_attempted(self):
        temp, root, rows = self._setup()
        self.addCleanup(temp.cleanup)
        with mock.patch.object(runtime, "ROOT", root), \
             mock.patch.object(runtime, "_read_status", return_value=rows), \
             mock.patch.object(runtime, "_run") as run:
            result = runtime._prepare_output_reserve()
        run.assert_not_called()
        self.assertFalse(result["output_reserve_resized"])
        self.assertFalse(result["reserve_mutation_attempted"])
        self.assertEqual(result["outputs"]["reserve_gb"], 0.7172)
        self.assertEqual(rows["outputs"]["reserve_gb"], 0.7172)
        self.assertAlmostEqual(result["projected_output_usage_with_artifacts_gb"], 0.44, places=3)

    def test_280gb_models_target_accepts_existing_29_83gb_reserve_without_resize(self):
        temp, root, rows = self._setup()
        self.addCleanup(temp.cleanup)
        rows["models"].update(actual_gb=250.30, target_gb=280.0, reserve_gb=29.83)
        with mock.patch.object(runtime, "ROOT", root), \
             mock.patch.object(runtime, "_read_status", return_value=rows), \
             mock.patch.object(runtime, "_run") as run:
            result = runtime._prepare_output_reserve()
        run.assert_not_called()
        self.assertEqual(result["models"]["reserve_gb"], 29.83)
        self.assertEqual(result["models_reserve_minimum_gb"], 1.0)
        self.assertFalse(result["reserve_mutation_attempted"])

    def test_model_reserve_below_configured_minimum_fails_without_resize(self):
        temp, root, rows = self._setup()
        self.addCleanup(temp.cleanup)
        rows["models"]["reserve_gb"] = 0.50
        with mock.patch.object(runtime, "ROOT", root), \
             mock.patch.object(runtime, "_read_status", return_value=rows), \
             mock.patch.object(runtime, "_run") as run:
            with self.assertRaisesRegex(RuntimeError, "below the configured minimum"):
                runtime._prepare_output_reserve()
        run.assert_not_called()

    def test_artifact_budget_still_fails_if_content_exceeds_target(self):
        temp, root, rows = self._setup(actual_outputs=0.90)
        self.addCleanup(temp.cleanup)
        with mock.patch.object(runtime, "ROOT", root), \
             mock.patch.object(runtime, "_read_status", return_value=rows), \
             mock.patch.object(runtime, "_run") as run:
            with self.assertRaisesRegex(RuntimeError, "outputs artifact budget denied"):
                runtime._prepare_output_reserve()
        run.assert_not_called()

    def test_below_floor_reserve_fails_closed_without_resize(self):
        temp, root, rows = self._setup()
        self.addCleanup(temp.cleanup)
        rows["outputs"]["reserve_gb"] = 0.10
        with mock.patch.object(runtime, "ROOT", root), \
             mock.patch.object(runtime, "_read_status", return_value=rows), \
             mock.patch.object(runtime, "_run") as run:
            with self.assertRaisesRegex(RuntimeError, "below the configured"):
                runtime._prepare_output_reserve()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
