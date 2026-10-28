"""Guarded recovery tests: only a dead local owner without a lease can be resumed."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tools.recover_dead_storage_locks import recover_area


class RecoverDeadStorageLocksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="oec-dead-lock-test-")
        self.root = Path(self.temp.name)
        self.reserve = self.root / ".storage_reserve.bin"
        self.reserve.write_bytes(b"reserve-sample")
        self.system_dirs = {"outputs": str(self.root)}
        self.lock = self.root / ".storage_pause.lock"
        self.lease = self.root / ".storage_lease.json"
        self.lock.write_text(f"pid=42424242\ntime=1000\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, **kwargs):
        return recover_area(
            "outputs",
            system_dirs=self.system_dirs,
            runner_name="oec-train",
            hostname="scn30-mn",
            now=2000.0,
            pid_is_alive=lambda pid: False,
            **kwargs,
        )

    def _resume(self, command):
        self.lock.unlink(missing_ok=True)
        return {"returncode": 0, "stdout_tail": "resumed", "stderr_tail": ""}

    def test_dead_local_owner_uses_manager_and_keeps_reserve_unchanged(self):
        before = self.reserve.stat().st_size
        report = self._run(resume=self._resume)
        self.assertEqual(report["status"], "RECOVERED")
        self.assertTrue(report["reserve_unchanged"])
        self.assertFalse(self.lock.exists())
        self.assertEqual(self.reserve.stat().st_size, before)

    def test_unresolved_lease_is_never_removed(self):
        self.lease.write_text('{"state":"active"}', encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "unresolved"):
            self._run(resume=self._resume)
        self.assertTrue(self.lease.exists())
        self.assertTrue(self.lock.exists())

    def test_live_owner_is_never_resumed(self):
        with self.assertRaisesRegex(RuntimeError, "alive"):
            recover_area("outputs", system_dirs=self.system_dirs, runner_name="oec-train",
                         hostname="scn30-mn", now=2000.0,
                         pid_is_alive=lambda pid: True, resume=self._resume)
        self.assertTrue(self.lock.exists())

    def test_unknown_runner_or_host_is_never_resumed(self):
        with self.assertRaisesRegex(RuntimeError, "restricted"):
            recover_area("outputs", system_dirs=self.system_dirs, runner_name="oec-train-2",
                         hostname="worker2", now=2000.0,
                         pid_is_alive=lambda pid: False, resume=self._resume)
        self.assertTrue(self.lock.exists())


if __name__ == "__main__":
    unittest.main()
