"""Regression tests for the quota snapshot CLI."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class QuotaSnapshotCliTests(unittest.TestCase):
    def test_cli_records_usage_above_admission_limit(self):
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "tools" / "quota_snapshot.py"
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "quota.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--used-bytes", "101",
                    "--limit-bytes", "100",
                    "--source", "test soft quota exceeded",
                    "--output", str(output),
                ],
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["used_bytes"], 101)
            self.assertEqual(payload["limit_bytes"], 100)
            self.assertIn("zero available bytes", result.stdout)


if __name__ == "__main__":
    unittest.main()
