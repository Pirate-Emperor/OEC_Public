"""No-GPU tests for conservative sidecar-owned storage-lock cleanup."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "media_services"))
import run_visual_media_sidecar_smokes as smoke


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


if __name__ == "__main__":
    unittest.main()
