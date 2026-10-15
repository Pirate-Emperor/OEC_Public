#!/usr/bin/env python3
"""Read-only inventory for the three OEC self-hosted A100 Action runners."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone

REPOS = {
    "flux": "models--black-forest-labs--FLUX.2-klein-4B",
    "trellis": "models--microsoft--TRELLIS.2-4B",
}
PACKAGES = ("torch", "diffusers", "huggingface-hub", "transformers", "xformers", "gradio", "safetensors", "accelerate", "Pillow")


def command(args, timeout=20):
    try:
        p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        return {"returncode": p.returncode, "stdout": p.stdout[-10000:]}
    except Exception as exc:
        return {"returncode": None, "error": f"{type(exc).__name__}: {exc}"}


def env_paths():
    result = {}
    path = Path.home() / ".env"
    if path.is_file():
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip("'").strip('"')
            if key in {"AIEROS_BASE_DIR", "AIEROS_MODELS_DIR", "AIEROS_QUOTA_SNAPSHOT"}:
                result.setdefault(key, value)
    return result


def models_root():
    env = env_paths()
    value = os.environ.get("AIEROS_MODELS_DIR") or env.get("AIEROS_MODELS_DIR")
    if not value:
        base = os.environ.get("AIEROS_BASE_DIR") or env.get("AIEROS_BASE_DIR") or str(Path.home())
        value = str(Path(base).expanduser() / "aireos_models")
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def mount(path):
    findmnt = shutil.which("findmnt")
    if not findmnt:
        return {"status": "FINDMNT_MISSING"}
    result = command([findmnt, "-T", str(path), "-n", "-o", "TARGET,SOURCE,FSTYPE"])
    pieces = result.get("stdout", "").strip().split()
    return {"target": pieces[0], "source": pieces[1], "fstype": pieces[2]} if result["returncode"] == 0 and len(pieces) >= 3 else {"status": "UNKNOWN"}


def cache_probe(root, repo):
    found = []
    for cache in (root, root / "hub", Path.home() / ".cache" / "huggingface" / "hub"):
        snaps = cache / repo / "snapshots"
        if not snaps.is_dir():
            continue
        for snap in sorted(snaps.iterdir()):
            if not snap.is_dir():
                continue
            try:
                weights = [p for p in snap.rglob("*.safetensors") if p.is_file()]
                total = sum(p.stat().st_size for p in weights)
            except OSError:
                weights, total = [], 0
            marker = "pipeline.json" if "TRELLIS.2" in repo else "model_index.json"
            found.append({"revision": snap.name, "weight_files": len(weights), "weight_bytes": total,
                          "config_marker_present": (snap / marker).is_file(), "cache_root": str(cache)})
    return {"status": "HIT" if any(s["weight_files"] for s in found) else "MISS", "snapshots": found}


def package_inventory(python):
    if not Path(python).is_file():
        return {"status": "PHASE2_3D_PYTHON_MISSING", "python": python}
    names = repr(PACKAGES)
    code = (
        "import importlib.metadata as m,json,sys\n"
        f"names={names}\n"
        "result={}\n"
        "for name in names:\n"
        " try: result[name]=m.version(name)\n"
        " except m.PackageNotFoundError: result[name]=None\n"
        "print(json.dumps({'python':sys.executable,'version':sys.version.split()[0],'packages':result},sort_keys=True))\n"
    )
    return command([str(python), "-c", code], timeout=20)


def gpu_inventory():
    nvsmi = shutil.which("nvidia-smi")
    if not nvsmi:
        return {"status": "NVIDIA_SMI_MISSING", "devices": []}
    gpu = command([nvsmi, "--query-gpu=index,uuid,name,memory.free,memory.total,utilization.gpu", "--format=csv,noheader,nounits"])
    proc = command([nvsmi, "--query-compute-apps=gpu_uuid,used_memory", "--format=csv,noheader,nounits"])
    if gpu["returncode"] != 0:
        return {"status": "GPU_QUERY_FAILED", "error": gpu.get("stdout", "")}
    counts = {}
    if proc["returncode"] == 0:
        for line in proc.get("stdout", "").splitlines():
            fields = [p.strip() for p in line.split(",")]
            if fields and fields[0] and not fields[0].lower().startswith("no running"):
                counts[fields[0]] = counts.get(fields[0], 0) + 1
    devices = []
    for line in gpu.get("stdout", "").splitlines():
        fields = [p.strip() for p in line.split(",")]
        if len(fields) < 6:
            continue
        idx, uuid, name, free, total, util = fields[:6]
        devices.append({"index": idx, "uuid": uuid, "name": name,
            "free_mib": int(free) if free.isdigit() else None,
            "total_mib": int(total) if total.isdigit() else None,
            "utilization_percent": int(util) if util.isdigit() else None,
            "active_compute_process_count": counts.get(uuid, 0)})
    return {"status": "PASS" if devices else "NO_GPU_VISIBLE", "devices": devices}


def quota_inventory(env):
    candidates = []
    explicit = os.environ.get("AIEROS_QUOTA_SNAPSHOT") or env.get("AIEROS_QUOTA_SNAPSHOT")
    if explicit:
        candidates.append(Path(os.path.expandvars(os.path.expanduser(explicit))))
    candidates.append(Path.home() / ".cache" / "aieros" / "quota_snapshot.json")
    found = next((p for p in candidates if p.is_file()), None)
    return {"snapshot_status": "PRESENT" if found else "MISSING",
        "snapshot_path": str(found or candidates[0]),
        "snapshot_age_seconds": max(0, int(datetime.now().timestamp() - found.stat().st_mtime)) if found else None,
        "quota_check_available": shutil.which("quota_check") is not None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-runner", default=os.environ.get("OEC_EXPECTED_RUNNER", ""))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    env = env_paths()
    root = models_root()
    python = os.environ.get("OEC_PYTHON") or str(Path.home() / "Conda" / "envs" / "phase2_3d" / "bin" / "python")
    runner = os.environ.get("RUNNER_NAME", "unknown")
    gpus = gpu_inventory()
    a100s = [g for g in gpus.get("devices", []) if "A100" in g.get("name", "").upper()]
    identity_ok = bool(args.expected_runner) and runner.casefold() == args.expected_runner.casefold()
    report = {
        "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "expected_runner_label": args.expected_runner or None, "runner_name": runner,
        "runner_os": os.environ.get("RUNNER_OS", "unknown"), "runner_arch": os.environ.get("RUNNER_ARCH", "unknown"),
        "host": socket.gethostname(), "workspace": os.environ.get("GITHUB_WORKSPACE"),
        "git_ref": os.environ.get("GITHUB_REF"), "git_sha": os.environ.get("GITHUB_SHA"),
        "identity_match": identity_ok, "models_root": str(root),
        "models_filesystem": mount(root), "tmp_filesystem": mount(Path("/tmp")),
        "phase2_3d_python": package_inventory(python), "gpu_inventory": gpus,
        "visible_a100_count": len(a100s), "flux_cache": cache_probe(root, REPOS["flux"]),
        "trellis_cache": cache_probe(root, REPOS["trellis"]), "quota_telemetry": quota_inventory(env),
        "network_downloads_performed": False, "packages_installed": False,
        "shared_cache_mutated": False, "active_processes_signalled": False,
    }
    passed = identity_ok and bool(a100s) and gpus["status"] == "PASS"
    report["status"] = "PASS_RUNNER_IDENTITY_AND_A100" if passed else "FAIL_RUNNER_IDENTITY_OR_A100"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("OEC_RUNNER_INVENTORY=" + report["status"] + " " + json.dumps({
        "runner": runner, "expected": args.expected_runner, "host": report["host"],
        "a100_count": len(a100s), "flux_cache": report["flux_cache"]["status"],
        "trellis_cache": report["trellis_cache"]["status"],
        "quota_snapshot": report["quota_telemetry"]["snapshot_status"]}, sort_keys=True), flush=True)
    print("OEC_RUNNER_REPORT=" + str(args.output), flush=True)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
