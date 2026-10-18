#!/usr/bin/env python3
"""Inspect or purge exact OEC model-owned cache paths; never touches reserve files."""
from __future__ import annotations
import argparse
import json
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
for entry in (str(ROOT), str(TOOLS_ROOT)):
    if entry not in sys.path: sys.path.insert(0, entry)
from media_services.model_cache import MODELS_ROOT, cache_status, lock_path, model_targets, read_lock

def _size_bytes(path: Path) -> int:
    if path.is_file() and not path.is_symlink(): return path.stat().st_size
    total = 0
    for folder, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(folder) / name).is_symlink()]
        for name in files:
            item = Path(folder) / name
            if item.is_symlink(): continue
            try: total += item.stat().st_size
            except OSError: pass
    return total

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show exact configured model folders, disk usage and runtime locks")
    purge = sub.add_parser("purge", help="delete only one listed model folder")
    purge.add_argument("model", choices=tuple(model_targets()))
    purge.add_argument("--confirm", action="store_true", help="required explicit confirmation")
    args = parser.parse_args()
    if args.command == "status":
        print(json.dumps(cache_status(), indent=2))
        return 0
    if not args.confirm: parser.error("purge requires --confirm; this deletes cached model weights")
    lock = read_lock(args.model)
    if lock:
        state = lock.get("state", "unknown")
        if state != "stale" or lock.get("host") != socket.gethostname():
            print(json.dumps({"purged": False, "model": args.model, "blocked_by_runtime_lock": state,
                "lock_path": str(lock_path(args.model)), "message": "stop service and inspect lock before purging"}, indent=2))
            return 2
        lock_path(args.model).unlink(missing_ok=True)
    from purge_manager import DiskPurgeManager
    results = []
    root = MODELS_ROOT.expanduser().resolve()
    for target in model_targets()[args.model]:
        resolved = target.expanduser().resolve()
        if resolved == root or root not in resolved.parents or target.is_symlink():
            print(f"Refusing unsafe model-cache path: {target}", file=sys.stderr)
            return 2
        if not target.exists():
            results.append({"path": str(target), "status": "not_present", "bytes_removed": 0})
            continue
        before = _size_bytes(target)
        ok = DiskPurgeManager.purge_directory(str(target), label=f"OEC model cache {args.model}")
        results.append({"path": str(target), "status": "purged" if ok else "failed", "bytes_removed": before if ok else 0})
        if not ok:
            print(json.dumps({"purged": False, "model": args.model, "results": results}, indent=2))
            return 1
    print(json.dumps({"purged": True, "model": args.model, "results": results,
        "note": "only named model paths targeted; the reserve file was not read or modified"}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
