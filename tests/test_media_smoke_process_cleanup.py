"""Tests for fail-closed cleanup of model-service processes created by the smoke runner."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import cleanup_test_model_caches as cache_cleanup
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

    def test_explicit_orphan_recovery_stops_prior_run_only_when_command_matches(self):
        self.write_owner(run_id="previous-run")
        with mock.patch.dict(os.environ, {"GITHUB_RUN_ID": "test-run"}), \
             mock.patch.object(smoke, "_pid_alive", side_effect=[True, False]), \
             mock.patch.object(smoke, "_owner_matches_running_process", return_value=True), \
             mock.patch.object(smoke.os, "kill") as kill:
            result = smoke._cleanup_owned_service(self.provider, self.root, allow_foreign_run=True)
        self.assertEqual(result["status"], "STOPPED")
        self.assertTrue(result["recovered_prior_run"])
        self.assertEqual(result["owner_run_id"], "previous-run")
        kill.assert_called_once_with(43210, smoke.signal.SIGTERM)
        self.assertFalse(self.owner_path.exists())

    def test_explicit_orphan_recovery_still_refuses_foreign_host(self):
        self.write_owner(run_id="previous-run", host="different-node")
        with mock.patch.dict(os.environ, {"GITHUB_RUN_ID": "test-run"}), \
             mock.patch.object(smoke.os, "kill") as kill:
            result = smoke._cleanup_owned_service(self.provider, self.root, allow_foreign_run=True)
        self.assertEqual(result["status"], "BLOCKED_OWNER_MISMATCH")
        kill.assert_not_called()

    def test_explicit_recovery_finds_verified_prior_acceptance_marker(self):
        search_root = self.root / "runner-temp"
        prior_dir = search_root / "oec-demo-notebook-acceptance-123" / "speech"
        current_dir = search_root / "oec-demo-notebook-acceptance-456" / "preflight-recovery"
        prior_dir.mkdir(parents=True)
        current_dir.mkdir(parents=True)
        marker = smoke._service_owner_path(self.provider, prior_dir)
        original = self.owner_path
        self.owner_path = marker
        self.write_owner(run_id="previous-run")
        self.owner_path = original
        with mock.patch.dict(os.environ, {"RUNNER_TEMP": str(search_root), "GITHUB_RUN_ID": "current-run"}), \
             mock.patch.object(smoke, "_pid_alive", side_effect=[True, False]), \
             mock.patch.object(smoke, "_owner_matches_running_process", return_value=True), \
             mock.patch.object(smoke.os, "kill") as kill:
            rows = smoke._cleanup_owned_services_for_provider(self.provider, current_dir, allow_foreign_run=True)
        self.assertIn("STOPPED", [row["status"] for row in rows])
        self.assertFalse(marker.exists())
        kill.assert_called_once_with(43210, smoke.signal.SIGTERM)

    def test_explicit_recovery_ignores_prior_marker_from_other_host(self):
        search_root = self.root / "runner-temp"
        prior_dir = search_root / "oec-demo-notebook-acceptance-123" / "speech"
        current_dir = search_root / "oec-demo-notebook-acceptance-456" / "preflight-recovery"
        prior_dir.mkdir(parents=True)
        current_dir.mkdir(parents=True)
        marker = smoke._service_owner_path(self.provider, prior_dir)
        original = self.owner_path
        self.owner_path = marker
        self.write_owner(run_id="previous-run", host="different-host")
        self.owner_path = original
        with mock.patch.dict(os.environ, {"RUNNER_TEMP": str(search_root), "GITHUB_RUN_ID": "current-run"}), \
             mock.patch.object(smoke.os, "kill") as kill:
            rows = smoke._cleanup_owned_services_for_provider(self.provider, current_dir, allow_foreign_run=True)
        self.assertEqual([row["status"] for row in rows], ["NOT_FOUND"])
        self.assertTrue(marker.exists())
        kill.assert_not_called()
    def test_orphan_recovery_scans_default_media_smoke_log_directory(self):
        runner_temp = self.root / "runner-temp"
        marker_dir = runner_temp / "oec-media-smoke-logs"
        marker_dir.mkdir(parents=True)
        recovery_dir = runner_temp / "oec-demo-notebook-acceptance-current" / "preflight-recovery"
        recovery_dir.mkdir(parents=True)
        owner = self.write_owner(run_id="prior-run")
        marker_path = smoke._service_owner_path(self.provider, marker_dir)
        marker_path.write_text(json.dumps(owner), encoding="utf-8")
        with mock.patch.dict(os.environ, {"RUNNER_TEMP": str(runner_temp), "GITHUB_RUN_ID": "current-run"}), \
             mock.patch.object(smoke, "_pid_alive", side_effect=[True, False]), \
             mock.patch.object(smoke, "_owner_matches_running_process", return_value=True), \
             mock.patch.object(smoke.os, "kill") as kill:
            rows = smoke._cleanup_owned_services_for_provider(self.provider, recovery_dir, allow_foreign_run=True)
        recovered = [row for row in rows if row["status"] == "STOPPED"]
        self.assertEqual(len(recovered), 1)
        self.assertTrue(recovered[0]["recovered_prior_run"])
        self.assertEqual(recovered[0]["owner_run_id"], "prior-run")
        kill.assert_called_once_with(43210, smoke.signal.SIGTERM)
        self.assertFalse(marker_path.exists())
    def test_recovery_cli_does_not_scan_or_load_models(self):
        argv = ["run_media_model_smokes.py", "--providers", "ace-step", "--cleanup-owned-services", "--recover-orphan-services", "--log-dir", str(self.root)]
        with mock.patch.object(smoke, "_conda_prefixes", side_effect=AssertionError("cleanup must not probe environments")), \
             mock.patch.object(smoke.sys, "argv", argv):
            result = smoke.main()
        self.assertEqual(result, 0)




class ModelCacheCleanupWaitTests(unittest.TestCase):
    def setUp(self):
        self.initial = {"model": "trellis-2-4b", "cache_paths": ["/tmp/cache"], "disk_bytes": 12, "present": True, "runtime_lock": "active"}
        self.final = {"model": "trellis-2-4b", "cache_paths": ["/tmp/cache"], "disk_bytes": 0, "present": False, "runtime_lock": "unlocked"}
        self.lock = {"state": "active", "host": "node-a", "pid": 1234}

    def test_waits_for_lock_release_then_purges_through_manager(self):
        with mock.patch.object(cache_cleanup, "cache_status", side_effect=[[self.initial], [self.final]]), \
             mock.patch.object(cache_cleanup, "read_lock", side_effect=[self.lock, None]), \
             mock.patch.object(cache_cleanup.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "ok", "")) as run, \
             mock.patch.object(cache_cleanup.time, "sleep") as sleep:
            result = cache_cleanup.purge_one("trellis-2-4b", wait_for_unlocked_seconds=2, poll_interval_seconds=0.01)
        self.assertEqual(result["status"], "PURGED")
        run.assert_called_once()
        sleep.assert_called_once()

    def test_zero_wait_preserves_cache_while_lock_is_live(self):
        with mock.patch.object(cache_cleanup, "cache_status", return_value=[self.initial]), \
             mock.patch.object(cache_cleanup, "read_lock", return_value=self.lock), \
             mock.patch.object(cache_cleanup.subprocess, "run") as run, \
             mock.patch.object(cache_cleanup.time, "sleep") as sleep:
            result = cache_cleanup.purge_one("trellis-2-4b")
        self.assertEqual(result["status"], "BLOCKED_BY_RUNTIME_LOCK")
        run.assert_not_called()
        sleep.assert_not_called()

    def test_cli_rejects_wait_longer_than_900_seconds(self):
        with self.assertRaises(SystemExit) as raised:
            cache_cleanup.main(["--models", "trellis-2-4b", "--wait-for-unlocked-seconds", "901"])
        self.assertEqual(raised.exception.code, 2)

if __name__ == "__main__":
    unittest.main()
