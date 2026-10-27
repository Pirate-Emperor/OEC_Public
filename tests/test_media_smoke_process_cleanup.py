"""Tests for fail-closed cleanup of model-service processes created by the smoke runner."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import run_media_model_smokes as smoke


class OwnedServiceCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.provider = "ace-step"
        self.owner_path = smoke._service_owner_path(self.provider, self.root)
        self.command = [
            "/home/test/.local/venvs/oec-acestep-py311/bin/python",
            str(smoke.MEDIA / "audio_api.py"), "--model", self.provider,
            "--host", "127.0.0.1", "--port", "7870",
        ]

    def write_owner(self, *, run_id="test-run", host=None, pid=43210):
        owner = {
            "provider": self.provider,
            "pid": pid,
            "host": host or smoke.socket.gethostname(),
            "run_id": run_id,
            "port": 7870,
            "created_unix": 1000.0,
            "expected_cmdline_prefix": self.command,
        }
        self.owner_path.write_text(json.dumps(owner), encoding="utf-8")
        return owner

    def test_missing_owner_marker_is_a_noop(self):
        result = smoke._cleanup_owned_service(self.provider, self.root)
        self.assertEqual(result["status"], "NOT_FOUND")

    def test_foreign_run_marker_never_signals_process(self):
        self.write_owner(run_id="another-run")
        with mock.patch.dict(os.environ, {"GITHUB_RUN_ID": "test-run"}), \
             mock.patch.object(smoke, "_pid_alive") as alive, \
             mock.patch.object(smoke.os, "kill") as kill:
            result = smoke._cleanup_owned_service(self.provider, self.root)
        self.assertEqual(result["status"], "BLOCKED_RUN_ID_MISMATCH")
        alive.assert_not_called()
        kill.assert_not_called()

    def test_command_mismatch_never_signals_process(self):
        self.write_owner()
        with mock.patch.dict(os.environ, {"GITHUB_RUN_ID": "test-run"}), \
             mock.patch.object(smoke, "_pid_alive", return_value=True), \
             mock.patch.object(smoke, "_owner_matches_running_process", return_value=False), \
             mock.patch.object(smoke.os, "kill") as kill:
            result = smoke._cleanup_owned_service(self.provider, self.root)
        self.assertEqual(result["status"], "BLOCKED_COMMAND_MISMATCH")
        kill.assert_not_called()
        self.assertTrue(self.owner_path.exists())

    def test_dead_recorded_pid_removes_stale_marker_without_signalling(self):
        self.write_owner()
        with mock.patch.dict(os.environ, {"GITHUB_RUN_ID": "test-run"}), \
             mock.patch.object(smoke, "_pid_alive", return_value=False), \
             mock.patch.object(smoke.os, "kill") as kill:
            result = smoke._cleanup_owned_service(self.provider, self.root)
        self.assertEqual(result["status"], "ALREADY_EXITED")
        self.assertFalse(self.owner_path.exists())
        kill.assert_not_called()

    def test_matching_owned_process_is_stopped_and_marker_removed(self):
        self.write_owner()
        with mock.patch.dict(os.environ, {"GITHUB_RUN_ID": "test-run"}), \
             mock.patch.object(smoke, "_pid_alive", side_effect=[True, False]), \
             mock.patch.object(smoke, "_owner_matches_running_process", return_value=True), \
             mock.patch.object(smoke.os, "kill") as kill:
            result = smoke._cleanup_owned_service(self.provider, self.root)
        self.assertEqual(result["status"], "STOPPED")
        self.assertEqual(result["signal"], "SIGTERM")
        kill.assert_called_once_with(43210, smoke.signal.SIGTERM)
        self.assertFalse(self.owner_path.exists())

    def test_recovery_cli_does_not_scan_or_load_models(self):
        argv = ["run_media_model_smokes.py", "--providers", "ace-step", "--cleanup-owned-services", "--log-dir", str(self.root)]
        with mock.patch.object(smoke, "_conda_prefixes", side_effect=AssertionError("cleanup must not probe environments")), \
             mock.patch.object(smoke.sys, "argv", argv):
            result = smoke.main()
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
