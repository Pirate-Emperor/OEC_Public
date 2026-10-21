"""LTX sidecar checkpoint-purge policy regressions; no model/GPU is loaded."""
from __future__ import annotations

import contextlib
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
# Sidecars are launched as scripts; emulate their import path in this test.
sys.path.insert(0, str(ROOT / "tools" / "media_services"))
from ltx_api import LtxProvider, purge_loaded_ltx_caches


class LtxCachePolicyTests(unittest.TestCase):
    def test_load_then_purge_targets_only_ltx_and_gemma_caches(self):
        with mock.patch("purge_manager.DiskPurgeManager.purge_hf_model", side_effect=[True, False]) as purge:
            result = purge_loaded_ltx_caches()
        self.assertEqual(
            purge.call_args_list,
            [
                mock.call("Lightricks/LTX-2.3"),
                mock.call("google/gemma-3-12b-it-qat-q4_0-unquantized"),
            ],
        )
        self.assertEqual(result, {"ltx": True, "gemma": False})

    def test_purge_after_load_is_rejected_for_cache_only_mode(self):
        with self.assertRaisesRegex(ValueError, "requires --allow-download"):
            LtxProvider(allow_download=False, purge_after_load=True)
        self.assertFalse(LtxProvider(allow_download=False).purge_after_load)

    def test_guarded_download_mode_can_enable_purge_but_can_also_keep_cache(self):
        self.assertTrue(LtxProvider(allow_download=True, purge_after_load=True).purge_after_load)
        self.assertFalse(LtxProvider(allow_download=True, purge_after_load=False).purge_after_load)

    def test_runtime_purge_occurs_only_after_pipeline_load_succeeds(self):
        class FakeCuda:
            @staticmethod
            def get_device_name(_index):
                return "NVIDIA A100"

        fake_torch = types.SimpleNamespace(cuda=FakeCuda())
        fake_ltx = types.ModuleType("worker_ltx_video")
        fake_ltx.load_pipeline_instance = mock.Mock(return_value=object())
        fake_ltx.LTX_COMMIT_SHA = "test-revision"
        fake_ltx.torch = fake_torch
        with (
            mock.patch("ltx_api.storage_check", return_value=(True, "ok")),
            mock.patch("ltx_api.managed_write", return_value=contextlib.nullcontext()),
            mock.patch.dict(sys.modules, {"worker_ltx_video": fake_ltx}),
            mock.patch("ltx_api.purge_loaded_ltx_caches", return_value={"ltx": True, "gemma": True}) as purge,
        ):
            provider = LtxProvider(allow_download=True, purge_after_load=True)
            provider.load_runtime()
        self.assertTrue(provider.model_loaded)
        purge.assert_called_once_with()

    def test_runtime_does_not_purge_when_pipeline_loader_raises(self):
        fake_torch = types.SimpleNamespace(cuda=types.SimpleNamespace(get_device_name=lambda _index: "NVIDIA A100"))
        fake_ltx = types.ModuleType("worker_ltx_video")
        fake_ltx.load_pipeline_instance = mock.Mock(side_effect=RuntimeError("load failed"))
        fake_ltx.LTX_COMMIT_SHA = "test-revision"
        fake_ltx.torch = fake_torch
        with (
            mock.patch("ltx_api.storage_check", return_value=(True, "ok")),
            mock.patch("ltx_api.managed_write", return_value=contextlib.nullcontext()),
            mock.patch.dict(sys.modules, {"worker_ltx_video": fake_ltx}),
            mock.patch("ltx_api.purge_loaded_ltx_caches") as purge,
        ):
            with self.assertRaisesRegex(RuntimeError, "load failed"):
                LtxProvider(allow_download=True, purge_after_load=True).load_runtime()
        purge.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
