#!/usr/bin/env python3
"""Select a safe A100 for cache-only image inference; never signals existing processes."""
from __future__ import annotations
import argparse
import csv
import json
import shutil
import subprocess
import sys
import time

MIN_IDLE_FREE_MIB = 30000
MIN_SHARED_FREE_MIB = 36000
MAX_SHARED_UTIL_PERCENT = 5
MAX_SHARED_PROCESS_MIB = 1024


def select_gpu(devices, min_idle_free_mib=MIN_IDLE_FREE_MIB,
               min_shared_free_mib=MIN_SHARED_FREE_MIB,
               max_shared_util_percent=MAX_SHARED_UTIL_PERCENT,
               max_shared_process_mib=MAX_SHARED_PROCESS_MIB):
    """Return (device, policy) for idle GPU or a verified tiny/shared context."""
    idle = [
        d for d in devices
        if d.get("active_compute_process_count") == 0
        and d.get("active_compute_memory_known") is True
        and isinstance(d.get("free_mib"), int)
        and d["free_mib"] >= min_idle_free_mib
        and isinstance(d.get("utilization_percent"), int)
        and d["utilization_percent"] <= max_shared_util_percent
    ]
    if idle:
        return max(idle, key=lambda d: d["free_mib"]), "IDLE"

    shared = [
        d for d in devices
        if d.get("active_compute_process_count", 0) > 0
        and isinstance(d.get("free_mib"), int)
        and d["free_mib"] >= min_shared_free_mib
        and isinstance(d.get("utilization_percent"), int)
        and d["utilization_percent"] <= max_shared_util_percent
        and d.get("active_compute_memory_known") is True
        and isinstance(d.get("active_compute_process_mib"), int)
        and d["active_compute_process_mib"] <= max_shared_process_mib
    ]
    if shared:
        return max(shared, key=lambda d: d["free_mib"]), "LOW_FOOTPRINT_SHARED"
    return None, "NO_ELIGIBLE_GPU"


def _run(args):
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15, check=False)
    return p.returncode, p.stdout


def probe_devices():
    nvsmi = shutil.which("nvidia-smi")
    if not nvsmi:
        raise RuntimeError("BLOCKED_GPU_PROBE: nvidia-smi is unavailable.")
    rc, raw = _run([nvsmi, "--query-gpu=index,uuid,name,memory.free,memory.total,utilization.gpu",
                    "--format=csv,noheader,nounits"])
    if rc:
        raise RuntimeError("BLOCKED_GPU_PROBE: " + raw[-2000:])
    gpu_rows = list(csv.reader(raw.splitlines()))
    rc, raw = _run([nvsmi, "--query-compute-apps=gpu_uuid,pid,used_memory", "--format=csv,noheader,nounits"])
    if rc:
        raise RuntimeError("BLOCKED_GPU_PROBE: cannot verify running compute processes.")
    active = {}
    for row in csv.reader(raw.splitlines()):
        if not row or not row[0].strip() or row[0].strip().lower().startswith("no running"):
            continue
        uid = row[0].strip()
        mem = None
        if len(row) >= 3:
            try:
                mem = int(row[2].strip().replace("MiB", "").strip())
            except ValueError:
                mem = None
        active.setdefault(uid, []).append(mem)

    devices = []
    for row in gpu_rows:
        if len(row) < 6:
            continue
        idx, uid, name, free, total, util = [x.strip() for x in row[:6]]
        processes = active.get(uid, [])
        known = all(p is not None for p in processes)
        devices.append({
            "index": idx, "uuid": uid, "name": name,
            "free_mib": int(free) if free.isdigit() else None,
            "total_mib": int(total) if total.isdigit() else None,
            "utilization_percent": int(util) if util.isdigit() else None,
            "active_compute_process_count": len(processes),
            "active_compute_process_memory_mib": processes,
            "active_compute_memory_known": known,
            "active_compute_process_mib": sum(p for p in processes if p is not None),
        })
    if not devices:
        raise RuntimeError("BLOCKED_GPU_PROBE: no GPU devices were returned.")
    return devices


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-idle-free-mib", type=int, default=MIN_IDLE_FREE_MIB)
    parser.add_argument("--min-shared-free-mib", type=int, default=MIN_SHARED_FREE_MIB)
    parser.add_argument("--max-shared-util-percent", type=int, default=MAX_SHARED_UTIL_PERCENT)
    parser.add_argument("--max-shared-process-mib", type=int, default=MAX_SHARED_PROCESS_MIB)
    parser.add_argument("--wait-seconds", type=int, default=0,
                        help="Wait for a genuinely eligible GPU, then fail closed (default: no wait).")
    parser.add_argument("--poll-interval", type=float, default=5.0,
                        help="Seconds between GPU re-samples while waiting.")
    parser.add_argument("--print-index-only", action="store_true",
                        help="Emit only the physical GPU index on stdout for shell substitution.")
    args = parser.parse_args(argv)
    if args.wait_seconds < 0 or args.poll_interval <= 0:
        parser.error("--wait-seconds must be non-negative and --poll-interval positive")
    deadline = time.monotonic() + args.wait_seconds
    try:
        while True:
            devices = probe_devices()
            selected, policy = select_gpu(
                devices, args.min_idle_free_mib, args.min_shared_free_mib,
                args.max_shared_util_percent, args.max_shared_process_mib,
            )
            if selected is not None:
                print("FLUX_GPU_ADMISSION=PASS " + json.dumps({
                    "policy": policy, "selected_gpu": selected["index"],
                    "free_mib": selected["free_mib"], "utilization_percent": selected["utilization_percent"],
                    "active_compute_process_count": selected["active_compute_process_count"],
                    "active_compute_process_mib": selected["active_compute_process_mib"],
                    "processes_signalled": False,
                }, sort_keys=True), file=sys.stderr, flush=True)
                if args.print_index_only:
                    print(selected["index"], flush=True)
                else:
                    print(json.dumps({"selected": selected, "policy": policy}, sort_keys=True), flush=True)
                return 0

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print("FLUX_GPU_ADMISSION=BLOCKED " + json.dumps({"devices": devices,
                    "policy": {"idle_free_mib": args.min_idle_free_mib,
                               "shared_free_mib": args.min_shared_free_mib,
                               "shared_util_max_percent": args.max_shared_util_percent,
                               "shared_process_max_mib": args.max_shared_process_mib},
                    "waited_seconds": args.wait_seconds}, sort_keys=True),
                    file=sys.stderr, flush=True)
                return 20

            print("FLUX_GPU_ADMISSION=WAIT " + json.dumps({
                "devices": devices, "remaining_seconds": max(0, round(remaining, 1)),
                "reason": "No GPU has sufficient free memory, verified process state and low utilization."
            }, sort_keys=True), file=sys.stderr, flush=True)
            time.sleep(min(args.poll_interval, remaining))
    except Exception as exc:
        print(f"FLUX_GPU_ADMISSION=BLOCKED error={type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
