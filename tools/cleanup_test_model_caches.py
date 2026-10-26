#!/usr/bin/env python3
"""Purge explicitly named model caches after acceptance, respecting runtime locks.

Only paths listed by tools/media_services/model_cache.py can be purged. The
existing DiskPurgeManager remains the deletion authority; reserves, source
checkouts, outputs and unlisted cache folders are never touched. A live or
remote/unknown runtime lock blocks deletion and makes this command fail.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.media_services.model_cache import cache_status, model_targets, read_lock


def purge_one(key: str) -> dict[str, Any]:
    initial = next(row for row in cache_status() if row["model"] == key)
    result: dict[str, Any] = {
        "model": key,
        "cache_paths": initial["cache_paths"],
        "bytes_before": initial["disk_bytes"],
        "present_before": initial["present"],
        "lock_before": initial["runtime_lock"],
        "status": "NOT_PRESENT",
        "bytes_after": 0,
    }
    if not initial["present"]:
        result["message"] = "model-owned cache was already absent"
        return result

    lock = read_lock(key)
    if lock is not None and lock.get("state") not in {"stale"}:
        result.update({
            "status": "BLOCKED_BY_RUNTIME_LOCK",
            "lock": {k: lock.get(k) for k in ("state", "host", "pid", "reason")},
            "message": "cache preserved because a live or remote/unknown runtime lock exists",
        })
        return result

    command = [
        sys.executable, str(ROOT / "tools" / "model_cache_manager.py"),
        "purge", key, "--confirm",
    ]
    completed = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True, timeout=240, check=False,
    )
    result["purge_command_exit_code"] = completed.returncode
    result["purge_output_tail"] = (completed.stdout + "\nSTDERR:\n" + completed.stderr)[-4000:]
    final = next(row for row in cache_status() if row["model"] == key)
    result.update({
        "present_after": final["present"],
        "bytes_after": final["disk_bytes"],
        "lock_after": final["runtime_lock"],
    })
    if completed.returncode == 0 and not final["present"] and final["disk_bytes"] == 0:
        result["status"] = "PURGED" if initial["present"] else "NOT_PRESENT"
    else:
        result["status"] = "PURGE_FAILED_OR_INCOMPLETE"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models", required=True,
        help="Comma-separated keys from model_cache_manager status (for example flux-klein-4b,trellis-2-4b).",
    )
    parser.add_argument("--report-json", type=Path, help="Optional path for a JSON cleanup report.")
    args = parser.parse_args(argv)
    selected = tuple(item.strip() for item in args.models.split(",") if item.strip())
    valid = set(model_targets())
    if not selected or len(selected) != len(set(selected)) or any(key not in valid for key in selected):
        parser.error("models must be a non-empty, unique comma-separated list of configured cache keys")

    started = time.time()
    results = []
    for key in selected:
        print(f"MODEL_CACHE_CLEANUP_START={key}", flush=True)
        try:
            row = purge_one(key)
        except Exception as exc:
            row = {"model": key, "status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
        results.append(row)
        print("MODEL_CACHE_CLEANUP_ITEM " + json.dumps(row, ensure_ascii=False), flush=True)

    blocked = [row for row in results if row["status"] in {
        "BLOCKED_BY_RUNTIME_LOCK", "PURGE_FAILED_OR_INCOMPLETE", "ERROR",
    }]
    report = {
        "test": "OEC explicit post-acceptance model-cache cleanup",
        "started_unix": started,
        "finished_unix": time.time(),
        "models_requested": list(selected),
        "purged": sum(row["status"] == "PURGED" for row in results),
        "already_absent": sum(row["status"] == "NOT_PRESENT" for row in results),
        "blocked_or_failed": len(blocked),
        "results": results,
        "safety": {
            "uses_existing_model_cache_manager": True,
            "remote_or_unknown_locks_are_preserved": True,
            "reserve_source_checkout_and_outputs_untouched": True,
        },
    }
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print("MODEL_CACHE_CLEANUP_SUMMARY " + json.dumps({
        "purged": report["purged"],
        "already_absent": report["already_absent"],
        "blocked_or_failed": report["blocked_or_failed"],
    }, ensure_ascii=False), flush=True)
    if args.report_json:
        target = args.report_json.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered + "\n", encoding="utf-8")
        print(f"MODEL_CACHE_CLEANUP_REPORT={target}", flush=True)
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
