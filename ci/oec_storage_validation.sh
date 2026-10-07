#!/usr/bin/env bash
set -euo pipefail

OEC_DIR="${OEC_DIR:-$HOME/OEC}"
cd "$OEC_DIR"

echo "=== OEC STORAGE VALIDATION ==="
export PYTHONPATH="$OEC_DIR:${PYTHONPATH:-}"
echo "RUNNER_NAME=${RUNNER_NAME:-unknown}"
hostname
whoami

echo "=== PYTHON SYNTAX ==="
python -m py_compile storage_policy.py storage_manager.py tools/quota_snapshot.py tests/test_storage_policy.py tests/test_storage_manager.py

echo "=== UNIT TESTS ==="
python tests/test_storage_policy.py
python tests/test_storage_manager.py

echo "=== QUOTA SNAPSHOT WRITER TEST ==="
python - <<'PY'
import json
import tempfile
from pathlib import Path

from tools import quota_snapshot

with tempfile.TemporaryDirectory() as temp:
    output = Path(temp) / "quota_snapshot.json"
    quota_snapshot.atomic_write(
        output,
        {
            "used_bytes": 40 * 1024**3,
            "limit_bytes": 100 * 1024**3,
            "timestamp": 1.0,
            "source": "test",
        },
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["used_bytes"] == 40 * 1024**3
    assert payload["limit_bytes"] == 100 * 1024**3

print("QUOTA SNAPSHOT WRITER: PASS")
PY

echo "=== RESERVE ALLOCATION TEST ==="

python - <<'PY'
import os
import tempfile
from pathlib import Path

import storage_policy

with tempfile.TemporaryDirectory() as temp:
    path = Path(temp) / ".storage_reserve.bin"
    changed = storage_policy.ensure_reserve_file(path, 8 * storage_policy.BYTES_PER_MB)
    assert changed
    assert path.stat().st_size == 8 * storage_policy.BYTES_PER_MB

    changed_again = storage_policy.ensure_reserve_file(path, 8 * storage_policy.BYTES_PER_MB)
    assert not changed_again, "unchanged reserve should not be reallocated"

    original_fallocate = storage_policy.os.posix_fallocate

    def fail_fallocate(fd, offset, length):
        raise OSError("simulated allocation failure")

    storage_policy.os.posix_fallocate = fail_fallocate
    failed_path = Path(temp) / ".failed_reserve.bin"
    try:
        try:
            storage_policy.ensure_reserve_file(failed_path, 8 * storage_policy.BYTES_PER_MB)
        except OSError:
            pass
        else:
            raise AssertionError("simulated fallocate failure did not propagate")
        assert not failed_path.exists(), "failed new reserve must be removed"
    finally:
        storage_policy.os.posix_fallocate = original_fallocate

print("RESERVE TEST: PASS")
PY

echo "=== WEBHOOK VALIDATION TEST ==="
python - <<'PY'
from storage_manager import _valid_discord_webhook

assert _valid_discord_webhook("https://discord.com/api/webhooks/123/token")
assert _valid_discord_webhook("https://discordapp.com/api/webhooks/123/token")
assert not _valid_discord_webhook("https://example.com/api/webhooks/123/token")
assert not _valid_discord_webhook("http://discord.com/api/webhooks/123/token")
print("WEBHOOK VALIDATION: PASS")
PY

echo "=== STORAGE CLI STATUS (READ ONLY) ==="
python storage_manager.py --status

echo "=== STORAGE PREFLIGHT FALLBACK ==="
python storage_manager.py --preflight-dir models --required-gb 0.01

echo "=== STORAGE PREFLIGHT WITH FRESH QUOTA REQUIRED ==="
set +e
python storage_manager.py --preflight-dir models --required-gb 0.01 --require-fresh-quota
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "Fresh quota snapshot is available on this runner."
elif [ "$rc" -eq 2 ]; then
  echo "Fresh quota snapshot is not available; strict preflight correctly rejected the operation."
else
  echo "Unexpected strict-preflight exit code: $rc"
  exit "$rc"
fi

echo "OEC STORAGE VALIDATION: PASS"
