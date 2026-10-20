from __future__ import annotations

import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

import oec_gpu_admission as admission


class GpuAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.inventory = (
            "0, GPU-0, NVIDIA A100-SXM4-40GB, 1000, 1, 40960\n"
            "1, GPU-1, NVIDIA A100-SXM4-40GB, 8194, 0, 40960\n"
            "2, GPU-2, NVIDIA A100-SXM4-40GB, 1000, 1, 40960\n"
        )

    def _runs(self, apps: str):
        return [
            subprocess.CompletedProcess([], 0, self.inventory, ""),
            subprocess.CompletedProcess([], 0, apps, ""),
        ]

    def test_unknown_active_process_blocks_its_gpu_but_other_idle_card_can_be_selected(self):
        apps = "GPU-0, 1234, /usr/bin/python, 850\n"
        with mock.patch.object(admission.subprocess, "run", side_effect=self._runs(apps)):
            selected = admission.select_idle_a100_gpu(caller="TEST")
        self.assertEqual(selected["index"], "2")

    def test_known_oec_play_context_is_shared_only_with_explicit_opt_in(self):
        pid = str(os.getpid())
        apps = f"GPU-0, {pid}, /nlsasfs/home/user/OEC/oec_deploy/v1/Biome/server-components/.venv/bin/python, 850\n"
        stat_result = SimpleNamespace(st_uid=os.getuid())
        with mock.patch.dict(os.environ, {"OEC_ALLOW_OEC_PLAY_IDLE_GPU_SHARING": "1"}):
            with mock.patch.object(admission.subprocess, "run", side_effect=self._runs(apps)):
                with mock.patch.object(admission.os, "stat", return_value=stat_result):
                    selected = admission.select_idle_a100_gpu(caller="TEST")
        self.assertEqual(selected["index"], "0")
        self.assertEqual(selected["shared_oec_play_context"], "true")

    def test_known_oec_play_context_does_not_share_by_default(self):
        pid = str(os.getpid())
        apps = f"GPU-0, {pid}, /nlsasfs/home/user/OEC/oec_deploy/v1/Biome/server-components/.venv/bin/python, 850\n"
        stat_result = SimpleNamespace(st_uid=os.getuid())
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(admission.subprocess, "run", side_effect=self._runs(apps)):
                with mock.patch.object(admission.os, "stat", return_value=stat_result):
                    inspected = admission.inspect_a100_devices()
        self.assertNotIn("0", [item["index"] for item in inspected["eligible_devices"]])

    def test_unknown_process_blocks_even_when_sharing_opt_in_is_enabled(self):
        pid = str(os.getpid())
        apps = f"GPU-0, {pid}, /usr/bin/python, 850\n"
        stat_result = SimpleNamespace(st_uid=os.getuid())
        with mock.patch.dict(os.environ, {"OEC_ALLOW_OEC_PLAY_IDLE_GPU_SHARING": "1"}):
            with mock.patch.object(admission.subprocess, "run", side_effect=self._runs(apps)):
                with mock.patch.object(admission.os, "stat", return_value=stat_result):
                    inspected = admission.inspect_a100_devices()
        self.assertNotIn("0", [item["index"] for item in inspected["eligible_devices"]])
        self.assertIn("compute process owns GPU", inspected["devices"][0]["reasons"])


if __name__ == "__main__":
    unittest.main()
