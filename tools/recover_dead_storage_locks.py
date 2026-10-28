#!/usr/bin/env python3
"""Conservatively recover a dead local OEC storage lock on the dedicated oec-train runner.

Legacy pause-locks do not contain host metadata. Recovery is therefore limited to
the known oec-train / scn30-mn A100 workflow host, with a dead local PID, no lease
manifest, an aged lock, and StorageManager's own --resume command. This script
never removes or resizes a reserve file and never clears a lease manifest.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from core_config import SYSTEM_DIRS  # noqa: E402
from storage_reserve_probe import inspect_managed_reserve  # noqa: E402

EXPECTED_RUNNER = "oec-train"
EXPECTED_HOST = "scn30-mn"
MINIMUM_LOCK_AGE_SECONDS = 300


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Permission denied means the PID exists, so ownership is not disproved.
        return True
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        raise


def _lock_info(area: str, system_dirs: dict[str, str]) -> dict[str, Any]:
    folder = Path(system_dirs[area]).expanduser()
    lock = folder / ".storage_pause.lock"
    lease = folder / ".storage_lease.json"
    info: dict[str, Any] = {
        "area": area,
        "folder": str(folder),
        "lock_path": str(lock),
        "lock_exists": lock.exists(),
        "lease_manifest_exists": lease.exists() or lease.is_symlink(),
    }
    if lock.is_symlink():
        raise RuntimeError(f"refusing symlinked storage pause lock: {lock}")
    if lock.exists():
        if not lock.is_file():
            raise RuntimeError(f"storage pause lock is not a regular file: {lock}")
        values: dict[str, str] = {}
        for line in lock.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        try:
            info["owner_pid"] = int(values["pid"])
            info["lock_time"] = float(values["time"])
        except (KeyError, ValueError) as exc:
            raise RuntimeError(f"storage pause lock has missing/invalid PID or time: {lock}") from exc
    return info


def recover_area(
    area: str,
    *,
    system_dirs: dict[str, str] | None = None,
    runner_name: str | None = None,
    hostname: str | None = None,
    now: float | None = None,
    pid_is_alive=None,
    resume=None,
) -> dict[str, Any]:
    if system_dirs is None:
        system_dirs = SYSTEM_DIRS
    runner_name = runner_name if runner_name is not None else os.environ.get("RUNNER_NAME", "unknown")
    hostname = hostname if hostname is not None else socket.gethostname()
    now = time.time() if now is None else now
    pid_is_alive = pid_is_alive or _pid_is_alive
    if area not in {"models", "outputs"} or area not in system_dirs:
        raise ValueError("area must be a configured models or outputs directory")
    if runner_name != EXPECTED_RUNNER or hostname != EXPECTED_HOST:
        raise RuntimeError(
            f"legacy lock recovery is restricted to {EXPECTED_RUNNER}/{EXPECTED_HOST}; "
            f"current identity={runner_name}/{hostname}"
        )

    reserve_before = inspect_managed_reserve(area, system_dirs=system_dirs)
    lock = _lock_info(area, system_dirs)
    if lock["lease_manifest_exists"]:
        raise RuntimeError(
            f"{area} has an unresolved .storage_lease.json; automatic recovery is prohibited"
        )
    if not lock["lock_exists"]:
        return {
            "status": "NO_LOCK",
            "area": area,
            "reserve_before": reserve_before,
            "reserve_unchanged": True,
        }

    owner_pid = lock.get("owner_pid")
    lock_time = lock.get("lock_time")
    if not isinstance(owner_pid, int) or owner_pid < 1 or not isinstance(lock_time, (int, float)):
        raise RuntimeError(f"{area} lock owner metadata is invalid")
    age = now - float(lock_time)
    if age < MINIMUM_LOCK_AGE_SECONDS:
        raise RuntimeError(f"{area} pause lock is only {age:.1f}s old; refuse recovery")
    if pid_is_alive(owner_pid):
        raise RuntimeError(
            f"{area} pause lock owner PID {owner_pid} is alive or cannot be disproved; refuse recovery"
        )

    command = [sys.executable, str(ROOT / "storage_manager.py"), "--resume", area]
    if resume is None:
        proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=30, check=False)
        resume_result = {"returncode": proc.returncode, "stdout_tail": proc.stdout[-600:], "stderr_tail": proc.stderr[-600:]}
    else:
        resume_result = resume(command)
    after = _lock_info(area, system_dirs)
    if resume_result.get("returncode") != 0 or after["lock_exists"] or after["lease_manifest_exists"]:
        raise RuntimeError(
            f"StorageManager did not clear the verified dead {area} pause lock: "
            f"{json.dumps({'resume': resume_result, 'after': after}, sort_keys=True)}"
        )
    reserve_after = inspect_managed_reserve(area, system_dirs=system_dirs)
    if reserve_before["size_bytes"] != reserve_after["size_bytes"] or reserve_before["allocated_bytes"] != reserve_after["allocated_bytes"]:
        raise RuntimeError(f"{area} reserve changed during pause-lock recovery")
    return {
        "status": "RECOVERED",
        "area": area,
        "owner_pid": owner_pid,
        "lock_age_seconds": round(age, 1),
        "storage_manager_resume": resume_result,
        "reserve_before": reserve_before,
        "reserve_after": reserve_after,
        "reserve_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("area", choices=("models", "outputs"))
    args = parser.parse_args()
    try:
        result = recover_area(args.area)
        print("OEC_DEAD_LOCK_RECOVERY " + json.dumps(result, sort_keys=True), flush=True)
        return 0
    except Exception as exc:
        print("OEC_DEAD_LOCK_RECOVERY " + json.dumps({
            "status": "BLOCKED", "area": args.area,
            "error_type": type(exc).__name__, "error": str(exc)[:1000],
        }, sort_keys=True), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
