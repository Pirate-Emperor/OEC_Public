"""Unit tests for safe OEC background service supervision."""
from __future__ import annotations

from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import oec_service_manager as manager


class OECServiceManagerTests(unittest.TestCase):
    def test_default_worker_gpu_selection_reserves_gpu_zero(self):
        with patch.object(manager, "_available_physical_gpus", return_value=["0", "1", "2", "3"]):
            self.assertEqual(manager._resolve_worker_gpus(None), {"1", "2", "3"})

    def test_worker_gpu_selection_validates_duplicates_and_unavailable_indices(self):
        with patch.object(manager, "_available_physical_gpus", return_value=["0", "1", "2"]):
            with self.assertRaisesRegex(ValueError, "duplicates"):
                manager._resolve_worker_gpus("1,01")
            with self.assertRaisesRegex(ValueError, "reports"):
                manager._resolve_worker_gpus("1,9")
            self.assertEqual(manager._resolve_worker_gpus("2,1"), {"1", "2"})

    def test_python_prefix_prefers_explicit_conda_environment_python(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            python = root / "envs" / "phase1_ltx" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text("#!/bin/sh\nexit 0\n")
            python.chmod(0o755)
            self.assertEqual(manager._python_prefix("phase1_ltx", root), [str(python.resolve())])

    def test_stop_does_not_signal_a_group_without_matching_service_script(self):
        state = {"instance_id": "flux-ui", "pgid": 999999, "script_path": "/repo/pipeline_flux_image.py"}
        with patch.object(manager, "_matching_members", return_value=[]), \
             patch.object(manager.os, "killpg") as killpg:
            self.assertFalse(manager._stop_state(state, grace_seconds=0))
            killpg.assert_not_called()

    def test_gpu_reservations_ignore_dead_and_skip_other_service(self):
        with patch.object(manager, "_all_states", return_value=[
            {"instance_id": "dead-service", "gpus": ["0"], "pgid": -1, "script_path": "/dead.py"},
            {"instance_id": "same-service", "gpus": ["1"], "pgid": -2, "script_path": "/same.py"},
        ]), patch.object(manager, "_is_running", side_effect=[False, True]):
            manager._assert_gpu_available({"0"}, exclude_instance="same-service")

    def test_cli_exposes_start_stop_status_logs_and_pipeline_services(self):
        for action in ("start", "stop", "status", "logs"):
            args = manager.build_parser().parse_args([action, "ltx-worker"])
            self.assertEqual(args.action, action)
            self.assertEqual(args.service, "ltx-worker")
        args = manager.build_parser().parse_args([
            "start", "flux-trellis", "--source-mode", "images", "--image-dir", "/tmp/images", "--recursive"
        ])
        self.assertEqual(args.source_mode, "images")
        self.assertEqual(args.image_dir, Path("/tmp/images"))
        self.assertTrue(args.recursive)

        batch = manager.build_parser().parse_args([
            "start", "trellis-batch", "--gpu", "2", "--image-dir", "/tmp/images",
            "--output-dir", "/tmp/new-trellis-output",
        ])
        self.assertEqual(batch.service, "trellis-batch")
        self.assertEqual(batch.gpu, "2")
        flux = manager.build_parser().parse_args([
            "start", "flux-image", "--gpu", "1", "--prompt", "A ceramic vase",
        ])
        self.assertEqual(flux.service, "flux-image")
        self.assertEqual(flux.prompt, "A ceramic vase")

    def test_supervisor_uses_no_shell_and_records_specific_scripts(self):
        source = (ROOT / "tools" / "oec_service_manager.py").read_text(encoding="utf-8")
        self.assertIn("start_new_session=True", source)
        self.assertIn('{"AIEROS_QA_GPU": gpu, "CUDA_VISIBLE_DEVICES": gpu}', source)
        self.assertIn("_matching_members(state)", source)
        self.assertIn('os.killpg(pgid, signal.SIGTERM)', source)
        self.assertNotIn("os.system(", source)
        self.assertNotIn("shell=True", source)


    def test_shutdown_escalates_to_the_managed_group_after_parent_script_exits(self):
        state = {
            "instance_id": "ltx-worker", "pgid": 12345,
            "script_path": "/repo/worker_ltx_video.py",
            "leader_start_time": 123,
        }
        parent = [{"pid": 12345, "cmdline": "python /repo/worker_ltx_video.py"}]
        child = [{"pid": 12346, "cmdline": "python -c multiprocessing.spawn"}]
        with (
            patch.object(manager, "_matching_members", return_value=parent),
            patch.object(manager, "_managed_group_members", side_effect=[child, []]),
            patch.object(manager.os, "killpg") as killpg,
        ):
            self.assertTrue(manager._stop_state(state, grace_seconds=0))
            self.assertEqual(killpg.call_count, 2)
            self.assertEqual(killpg.call_args_list[0].args, (12345, signal.SIGTERM))
            self.assertEqual(killpg.call_args_list[1].args, (12345, signal.SIGKILL))


if __name__ == "__main__":
    unittest.main()
