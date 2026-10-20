"""Fail-closed A100 admission with explicit idle OEC-Play context sharing.

Default mode requires no compute process, <=1 GiB used and <=5% utilization.
When OEC_ALLOW_OEC_PLAY_IDLE_GPU_SHARING=1, a recognized OEC-Play context may
coexist only if its PID belongs to the current Unix user, its executable matches
the known OEC-Play server-components venv Python, each process uses <=2 GiB, total
per-GPU memory is <=2 GiB, and GPU utilization is <=5%. Unknown/foreign processes
always exclude that card. This module never terminates or signals a process.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
from typing import Any

OEC_PLAY_EXECUTABLE_FRAGMENT = "/oec_deploy/v1/biome/server-components/.venv/bin/python"
IDLE_MEMORY_LIMIT_MIB = 1024
SHARED_CONTEXT_MEMORY_LIMIT_MIB = 2048
IDLE_UTILIZATION_LIMIT_PERCENT = 5.0


def _is_trusted_oec_play_context(pid_text: str, process_name: str) -> bool:
    if not pid_text.isdigit() or OEC_PLAY_EXECUTABLE_FRAGMENT not in process_name.replace("\\", "/").lower():
        return False
    try:
        owner_uid = os.stat(f"/proc/{int(pid_text)}").st_uid
    except OSError:
        return False
    return owner_uid == os.getuid()


def inspect_a100_devices(*, min_free_mib: int = 0, allow_shared_oec_play: bool | None = None) -> dict[str, Any]:
    """Return a per-card admission audit without mutating GPU/process state."""
    if allow_shared_oec_play is None:
        allow_shared_oec_play = os.environ.get("OEC_ALLOW_OEC_PLAY_IDLE_GPU_SHARING") == "1"
    try:
        inventory = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,uuid,name,memory.used,utilization.gpu,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=12, check=False,
        )
        apps = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=12, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("GPU/process telemetry unavailable; refusing inference") from exc
    if inventory.returncode or apps.returncode:
        raise RuntimeError("nvidia-smi GPU/process telemetry failed; refusing inference")

    by_uuid: dict[str, list[dict[str, Any]]] = {}
    for row in csv.reader(apps.stdout.splitlines()):
        if len(row) < 2:
            continue
        uuid, pid = row[0].strip(), row[1].strip()
        name = row[2].strip() if len(row) > 2 else ""
        try:
            process_mem = float(row[3].strip()) if len(row) > 3 else float("inf")
        except ValueError:
            process_mem = float("inf")
        if uuid and pid.isdigit():
            by_uuid.setdefault(uuid, []).append({
                "pid": pid, "process_name": name, "used_gpu_memory_mib": process_mem,
                "trusted_oec_play": _is_trusted_oec_play_context(pid, name),
            })

    audit: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for row in csv.reader(inventory.stdout.splitlines()):
        if len(row) < 5:
            continue
        idx, uuid, name, raw_used, raw_util = (value.strip() for value in row[:5])
        raw_total = row[5].strip() if len(row) > 5 else "0"
        if not idx.isdigit() or "A100" not in name.upper():
            continue
        try:
            used, util, total = float(raw_used), float(raw_util), float(raw_total)
        except ValueError:
            used = util = total = float("inf")
        free = total - used
        processes = by_uuid.get(uuid, [])
        reasons: list[str] = []
        trusted_shared = False
        if processes:
            all_trusted = all(p["trusted_oec_play"] for p in processes)
            process_memory_ok = all(p["used_gpu_memory_mib"] <= SHARED_CONTEXT_MEMORY_LIMIT_MIB for p in processes)
            if (allow_shared_oec_play and all_trusted and process_memory_ok
                    and used <= SHARED_CONTEXT_MEMORY_LIMIT_MIB):
                trusted_shared = True
            else:
                reasons.append("compute process owns GPU")
                if not all_trusted:
                    reasons.append("compute process is not an approved OEC-Play context")
                elif not process_memory_ok or used > SHARED_CONTEXT_MEMORY_LIMIT_MIB:
                    reasons.append("OEC-Play context exceeds shared-memory limit")
        elif used > IDLE_MEMORY_LIMIT_MIB:
            reasons.append("memory used exceeds 1024 MiB")
        if util > IDLE_UTILIZATION_LIMIT_PERCENT:
            reasons.append("GPU utilization exceeds 5 percent")
        if free < min_free_mib:
            reasons.append(f"free VRAM below required {min_free_mib} MiB")
        item = {
            "index": idx, "uuid": uuid, "name": name, "memory_used_mib": used,
            "memory_total_mib": total, "free_mib": free, "utilization_percent": util,
            "processes": processes, "shared_oec_play_context": trusted_shared,
            "eligible": not reasons, "reasons": reasons,
        }
        audit.append(item)
        if not reasons:
            eligible.append(item)
    eligible.sort(key=lambda d: (d["memory_used_mib"], d["utilization_percent"], int(d["index"])))
    return {
        "policy": {
            "idle_memory_limit_mib": IDLE_MEMORY_LIMIT_MIB,
            "shared_context_memory_limit_mib": SHARED_CONTEXT_MEMORY_LIMIT_MIB,
            "idle_utilization_limit_percent": IDLE_UTILIZATION_LIMIT_PERCENT,
            "min_free_mib": min_free_mib,
            "allow_shared_oec_play": bool(allow_shared_oec_play),
            "unknown_compute_processes_always_block": True,
            "processes_are_never_killed": True,
        },
        "devices": audit,
        "eligible_devices": eligible,
    }


def select_idle_a100_gpu(requested: int | None = None, *, min_free_mib: int = 0,
                         caller: str = "OEC") -> dict[str, str]:
    result = inspect_a100_devices(min_free_mib=min_free_mib)
    devices = result["devices"]
    candidates = [d for d in result["eligible_devices"]
                  if requested is None or int(d["index"]) == requested]
    if not candidates:
        blocked = {"requested_index": requested, "a100_devices": devices, "policy": result["policy"]}
        print(f"{caller.upper()}_GPU_ADMISSION_BLOCKED=" + json.dumps(blocked, sort_keys=True), flush=True)
        raise RuntimeError("no eligible idle A100; detailed per-GPU admission reasons are logged; no process was killed or signalled")
    picked = candidates[0]
    selected = {
        "index": str(picked["index"]), "uuid": str(picked["uuid"]), "name": str(picked["name"]),
        "memory_used_mib": str(picked["memory_used_mib"]),
        "utilization_percent": str(picked["utilization_percent"]), "free_mib": str(picked["free_mib"]),
        "shared_oec_play_context": str(bool(picked["shared_oec_play_context"])).lower(),
    }
    print(f"{caller.upper()}_GPU_ADMITTED=" + json.dumps({"selected": selected, "policy": result["policy"]},
                                                         sort_keys=True), flush=True)
    return selected
