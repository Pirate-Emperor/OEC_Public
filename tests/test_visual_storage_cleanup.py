"""No-GPU tests for sidecar-owned storage cleanup and model-job lease boundaries."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "media_services"))
import run_visual_media_sidecar_smokes as smoke
import ltx_api
import trellis_api


class FakeProcess:
    pid = 4321
    returncode = -15

    def poll(self):
        return self.returncode


class VisualStorageCleanupTests(unittest.TestCase):
    def setUp(self):
        self.process = FakeProcess()
        self.python = Path(sys.executable)
        self.started = 100.0
        self.env = {"RUNNER_NAME": "oec-1"}

    def test_recovers_only_a_lock_owned_by_the_stopped_sidecar(self):
        present = {"ok": True, "lock_exists": True, "lease_manifest_exists": False,
                   "owner_pid": self.process.pid, "lock_time": self.started + 1}
        absent = {"ok": True, "lock_exists": False, "lease_manifest_exists": False}
        with mock.patch.object(smoke, "_inspect_outputs_storage_lock", side_effect=[present, absent]), \
             mock.patch.object(smoke.subprocess, "run", return_value=mock.Mock(returncode=0, stdout="", stderr="")) as run:
            result = smoke._recover_owned_storage_lock(self.process, self.python, self.env, self.started)
        self.assertEqual(result["status"], "RECOVERED")
        command = run.call_args.args[0]
        self.assertIn("--resume", command)
        self.assertEqual(command[-1], "outputs")

    def test_foreign_owner_is_left_alone(self):
        info = {"ok": True, "lock_exists": True, "lease_manifest_exists": False,
                "owner_pid": self.process.pid + 1, "lock_time": self.started + 1}
        with mock.patch.object(smoke, "_inspect_outputs_storage_lock", return_value=info), \
             mock.patch.object(smoke.subprocess, "run") as run:
            result = smoke._recover_owned_storage_lock(self.process, self.python, self.env, self.started)
        self.assertEqual(result["status"], "BLOCKED")
        run.assert_not_called()

    def test_unresolved_lease_is_left_alone(self):
        info = {"ok": True, "lock_exists": True, "lease_manifest_exists": True,
                "owner_pid": self.process.pid, "lock_time": self.started + 1}
        with mock.patch.object(smoke, "_inspect_outputs_storage_lock", return_value=info), \
             mock.patch.object(smoke.subprocess, "run") as run:
            result = smoke._recover_owned_storage_lock(self.process, self.python, self.env, self.started)
        self.assertEqual(result["status"], "BLOCKED")
        run.assert_not_called()

    def test_live_sidecar_is_not_resumed(self):
        self.process.returncode = None
        info = {"ok": True, "lock_exists": True, "lease_manifest_exists": False,
                "owner_pid": self.process.pid, "lock_time": self.started + 1}
        with mock.patch.object(smoke, "_inspect_outputs_storage_lock", return_value=info), \
             mock.patch.object(smoke.subprocess, "run") as run:
            result = smoke._recover_owned_storage_lock(self.process, self.python, self.env, self.started)
        self.assertEqual(result["status"], "BLOCKED")
        run.assert_not_called()

    def test_trellis_remesh_is_an_explicit_boolean_and_defaults_off_for_api(self):
        provider = trellis_api.TrellisProvider()
        payload = {"task": "image_to_3d", "image_base64": "ZmFrZQ==", "parameters": {}}
        normalized = provider.validate_request(payload)
        self.assertFalse(normalized["parameters"]["remesh"])
        payload["parameters"] = {"remesh": True}
        self.assertTrue(provider.validate_request(payload)["parameters"]["remesh"])
        payload["parameters"] = {"remesh": "false"}
        with self.assertRaisesRegex(trellis_api.RequestError, "remesh must be true or false"):
            provider.validate_request(payload)

    def test_trellis_generation_does_not_hold_outer_storage_lease(self):
        with tempfile.TemporaryDirectory(prefix="oec-test-trellis-") as folder:
            root = Path(folder)
            input_image = root / "input.png"
            smoke._write_test_png(input_image)
            outputs = root / "outputs"
            provider = trellis_api.TrellisProvider()
            provider.model_loaded = True
            provider.pipeline = object()
            provider.runtime = {"system_dirs": {"outputs": str(outputs)}, "o_voxel": object()}
            observed = {}

            def generate_glb(**kwargs):
                observed.update(kwargs)
                path = Path(kwargs["output_path"])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"dummy-glb")
                return str(path)

            provider.module = SimpleNamespace(generate_glb=generate_glb)
            request = provider.validate_request({
                "task": "image_to_3d", "filename": input_image.name,
                "prompt": "fixture", "image_base64": "ZmFrZQ==",
                "parameters": {"max_image_size": 512, "texture_size": 512, "remesh": False},
            })
            with mock.patch.object(trellis_api, "validate_glb", return_value={"meshes": 1}), \
                 mock.patch.object(trellis_api, "managed_write", create=True) as managed:
                result_path, _metadata = provider.run_job("job_trellis123456", request, input_image)
            managed.assert_not_called()
            self.assertEqual(Path(result_path).read_bytes(), b"dummy-glb")
            self.assertFalse(observed["remesh"])

    def test_ltx_generation_runs_after_the_short_directory_lease_is_released(self):
        with tempfile.TemporaryDirectory(prefix="oec-test-ltx-") as folder:
            root = Path(folder)
            outputs = root / "outputs"
            original_output_dir = root / "previous"
            active = {"lease": False}
            lease_calls = []

            @contextmanager
            def tracked_managed_write(area, required_gb, minimum_free_gb=0.05):
                self.assertEqual(area, "outputs")
                self.assertFalse(active["lease"])
                active["lease"] = True
                lease_calls.append((area, required_gb, minimum_free_gb))
                try:
                    yield
                finally:
                    active["lease"] = False

            module = SimpleNamespace(SYSTEM_DIRS={"outputs": str(outputs)}, AIEROS_OUTPUT_DIR=original_output_dir)

            def generate_asset(**kwargs):
                self.assertFalse(active["lease"], "LTX inference must not run under the sidecar's outer lease")
                self.assertEqual(Path(module.AIEROS_OUTPUT_DIR).name, "job_ltx123456789")
                video = Path(module.AIEROS_OUTPUT_DIR) / "smoke.mp4"
                metadata = Path(module.AIEROS_OUTPUT_DIR) / "smoke.json"
                video.write_bytes(b"fixture-mp4")
                metadata.write_text(json.dumps({"test": True}), encoding="utf-8")
                return str(video), str(metadata), kwargs["seed"]

            module.generate_asset = generate_asset
            provider = ltx_api.LtxProvider()
            provider.model_loaded = True
            provider.pipeline = object()
            provider.module = module
            request = {
                "task": "text_to_video", "prompt": "test", "filename": "reference.png",
                "parameters": {"duration_seconds": 2.0, "fps": 12.0, "seed": 42,
                               "randomize_seed": False, "enhance_prompt": False, "width": 768, "height": 512},
            }
            with mock.patch.object(ltx_api, "managed_write", side_effect=tracked_managed_write), \
                 mock.patch.object(ltx_api, "validate_mp4", return_value={"validation": "fixture"}):
                result_path, _metadata = provider.run_job("job_ltx123456789", request, None)
            self.assertEqual(len(lease_calls), 1)
            self.assertFalse(active["lease"])
            self.assertTrue(Path(result_path).is_file())
            self.assertEqual(module.AIEROS_OUTPUT_DIR, original_output_dir)


if __name__ == "__main__":
    unittest.main()
