#!/usr/bin/env python3
"""Safe per-user supervisor for OEC background model services.

The supervisor records only processes it launches, uses isolated POSIX process
groups, and refuses to signal a group unless /proc confirms that the recorded
script is still a member. It never uses pkill or matches generic "python" names.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
HOST = socket.gethostname()
DEFAULT_CONDA_ROOT = Path(os.environ.get("CONDA_ROOT", str(Path.home() / "Conda"))).expanduser()
STATE_ROOT = Path(os.environ.get(
    "OEC_SERVICE_STATE_DIR",
    str(Path.home() / ".local" / "state" / "oec-services" / HOST),
)).expanduser()
LOG_ROOT = STATE_ROOT / "logs"
SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _emit(message: str) -> None:
    print(f"[OEC-SERVICES] {message}", flush=True)


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.")
    if not safe:
        raise ValueError("service identifier must contain letters or numbers")
    return safe


def _python_prefix(env_name: str, conda_root: Path, python_override: str | None = None) -> list[str]:
    if python_override:
        candidate = Path(python_override).expanduser()
        if not candidate.is_file():
            raise FileNotFoundError(f"Python override does not exist: {candidate}")
        return [str(candidate.resolve())]
    env_python = conda_root / "envs" / env_name / "bin" / "python"
    if env_python.is_file():
        return [str(env_python.resolve())]
    conda_candidates = [conda_root / "bin" / "conda", conda_root / "condabin" / "conda"]
    conda = next((str(p) for p in conda_candidates if p.is_file()), None) or shutil.which("conda")
    if conda:
        return [conda, "run", "-n", env_name, "--no-capture-output", "python"]
    raise FileNotFoundError(
        f"Cannot locate Python for Conda environment {env_name!r}. Expected "
        f"{env_python} or a conda executable. Set CONDA_ROOT or pass --conda-root."
    )


def _available_physical_gpus() -> list[str]:
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
            encoding="utf-8", stderr=subprocess.STDOUT, timeout=10,
        )
    except Exception as exc:
        raise RuntimeError(f"Unable to verify local physical GPUs with nvidia-smi: {type(exc).__name__}: {exc}") from exc
    ids = [str(int(line.strip())) for line in output.splitlines() if line.strip().isdigit()]
    if not ids:
        raise RuntimeError("nvidia-smi reported no physical GPU IDs.")
    return ids


def _resolve_worker_gpus(requested: str | None) -> set[str]:
    available = _available_physical_gpus()
    if requested is None or not requested.strip():
        selected = [gpu for gpu in available if gpu != "0"] or available
    else:
        parts = [part.strip() for part in requested.split(",") if part.strip()]
        if not parts or any(not part.isdigit() for part in parts):
            raise ValueError("--gpus must contain comma-separated non-negative integer IDs.")
        selected = [str(int(part)) for part in parts]
        if len(selected) != len(set(selected)):
            raise ValueError(f"--gpus contains duplicates: {selected}")
        missing = [part for part in selected if part not in available]
        if missing:
            raise ValueError(f"Requested GPU IDs {missing}, but this node reports {available}.")
    if not selected:
        raise RuntimeError("No worker GPUs selected.")
    return set(selected)


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["no_proxy"] = "localhost,127.0.0.1,::1,0.0.0.0"
    env["NO_PROXY"] = env["no_proxy"]
    return env


def _state_path(instance_id: str) -> Path:
    return STATE_ROOT / f"{_safe_id(instance_id)}.json"


def _read_state(path: Path) -> dict[str, Any] | None:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _all_states() -> list[dict[str, Any]]:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    out = []
    for path in sorted(STATE_ROOT.glob("*.json")):
        obj = _read_state(path)
        if obj:
            obj["_state_path"] = str(path)
            out.append(obj)
    return out


def _proc_entry(pid: int) -> dict[str, Any] | None:
    """Read a single Linux process without invoking shell tools."""
    try:
        raw_stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        # comm is parenthesized and may contain spaces; split after the last ')'.
        tail = raw_stat[raw_stat.rfind(")") + 2:].split()
        if len(tail) < 20:
            return None
        state = tail[0]
        pgid = int(tail[2])  # proc stat field 5: pgrp
        sid = int(tail[3])  # proc stat field 6: session
        start_time = int(tail[19])  # field 22: starttime, after fields 3..22
        cmdline_raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        cmdline = cmdline_raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
        return {"pid": pid, "pgid": pgid, "sid": sid, "state": state, "start_time": start_time, "cmdline": cmdline}
    except (OSError, ValueError, IndexError):
        return None


def _group_members(pgid: int) -> list[dict[str, Any]]:
    if not Path("/proc").is_dir():
        return []
    members = []
    try:
        pids = [int(item.name) for item in Path("/proc").iterdir() if item.name.isdigit()]
    except OSError:
        return []
    for pid in pids:
        info = _proc_entry(pid)
        if info and info["pgid"] == int(pgid):
            members.append(info)
    return members


def _matching_members(state: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        pgid = int(state["pgid"])
        script = str(Path(state["script_path"]).resolve())
    except (KeyError, TypeError, ValueError, OSError):
        return []
    if not script:
        return []
    # A managed command must still be present; generic python/conda names do not count.
    return [p for p in _group_members(pgid) if script in p["cmdline"]]


def _managed_group_members(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return live descendants in the exact isolated session started by this supervisor."""
    try:
        pgid = int(state["pgid"])
        expected_start = state.get("leader_start_time")
    except (KeyError, TypeError, ValueError):
        return []
    members = [
        p for p in _group_members(pgid)
        if p.get("sid") == pgid and p.get("state") not in ("Z", "X")
    ]
    # Guard against a recycled leader PID if it is currently occupied by a different process.
    leader = next((p for p in members if p["pid"] == pgid), None)
    if leader is not None and expected_start is not None and leader["start_time"] != expected_start:
        return []
    return members


def _is_running(state: dict[str, Any]) -> bool:
    return bool(_managed_group_members(state))


def _save_state(state: dict[str, Any]) -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    path = _state_path(str(state["instance_id"]))
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _claimed_gpus(state: dict[str, Any]) -> set[str]:
    vals = state.get("gpus", [])
    if isinstance(vals, str):
        vals = [x.strip() for x in vals.split(",") if x.strip()]
    return {str(x) for x in vals}


def _assert_gpu_available(gpus: set[str], exclude_instance: str | None = None) -> None:
    if not gpus:
        return
    conflicts = []
    for state in _all_states():
        if state.get("instance_id") == exclude_instance or not _is_running(state):
            continue
        overlap = gpus.intersection(_claimed_gpus(state))
        if overlap:
            conflicts.append(f"{state.get('instance_id')} claims GPU(s) {','.join(sorted(overlap))}")
    if conflicts:
        raise RuntimeError("GPU reservation conflict: " + "; ".join(conflicts) + ". Stop the conflicting managed service or select another GPU.")


def _launch(
    instance_id: str,
    group: str,
    script: Path,
    env_name: str,
    script_args: list[str],
    conda_root: Path,
    python_override: str | None,
    env_updates: dict[str, str | None] | None = None,
    gpus: set[str] | None = None,
) -> dict[str, Any]:
    script = script.resolve()
    if not script.is_file():
        raise FileNotFoundError(f"Service script not found: {script}")
    state_path = _state_path(instance_id)
    old = _read_state(state_path)
    if old and _is_running(old):
        raise RuntimeError(f"{instance_id} already has a live managed process (PID {old.get('pid')}).")
    py = _python_prefix(env_name, conda_root, python_override)
    argv = py + [str(script)] + script_args
    env = _base_env()
    if env_updates:
        for key, value in env_updates.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    log_path = LOG_ROOT / f"{_safe_id(instance_id)}.log"
    log_handle = log_path.open("a", encoding="utf-8", buffering=1)
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(REPO_ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        log_handle.close()

    leader_info = _proc_entry(proc.pid)
    state = {
        "schema_version": 1,
        "instance_id": instance_id,
        "service": instance_id,
        "group": group,
        "host": HOST,
        "pid": proc.pid,
        "pgid": proc.pid,
        "leader_start_time": leader_info.get("start_time") if leader_info else None,
        "script_path": str(script),
        "environment": env_name,
        "argv": argv,
        "gpus": sorted(gpus or set()),
        "log_path": str(log_path),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    _save_state(state)
    time.sleep(0.25)
    if proc.poll() is not None and not _is_running(state):
        raise RuntimeError(
            f"{instance_id} exited immediately with code {proc.returncode}. Check log: {log_path}"
        )
    _emit(f"STARTED service={instance_id} pid={proc.pid} env={env_name} log={log_path}")
    return state


def _stop_state(state: dict[str, Any], grace_seconds: float = 25.0) -> bool:
    members = _matching_members(state)
    if not members:
        _emit(f"NOT_RUNNING service={state.get('instance_id')} (no matching script in its recorded process group)")
        return False
    pgid = int(state["pgid"])
    _emit(f"TERM service={state.get('instance_id')} pgid={pgid} matching_pids={','.join(str(x['pid']) for x in members)}")
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not _managed_group_members(state):
            _emit(f"STOPPED service={state.get('instance_id')} gracefully")
            return True
        time.sleep(0.25)
    # After the initial exact-script check and SIGTERM, include spawned multiprocessing
    # children too; their argv often contains multiprocessing.spawn rather than the script.
    members = _managed_group_members(state)
    if members:
        _emit(f"GRACE_EXPIRED service={state.get('instance_id')}; verified managed-session members remain; sending SIGKILL to that isolated group only")
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if not _managed_group_members(state):
                _emit(f"STOPPED service={state.get('instance_id')} after verified escalation")
                return True
            time.sleep(0.2)
    _emit(f"STOP_REQUESTED service={state.get('instance_id')}")
    return True


def _script(name: str) -> Path:
    return REPO_ROOT / name


def _services_for_group(group: str) -> list[dict[str, Any]]:
    return [s for s in _all_states() if s.get("group") == group or s.get("instance_id") == group]


def _select_action_targets(service: str) -> list[dict[str, Any]]:
    # Stop/status a bundle as one logical service; individual children can also be addressed.
    states = _all_states()
    matched = [s for s in states if s.get("instance_id") == service]
    if matched:
        return matched
    return [s for s in states if s.get("group") == service or str(s.get("instance_id", "")).startswith(service + "-")]


def start_service(args: argparse.Namespace) -> None:
    conda_root = args.conda_root.expanduser().resolve()
    service = args.service
    created: list[dict[str, Any]] = []
    try:
        if service == "ltx-control":
            # Brain is deliberately confined to physical GPU 0. Do not place QA here too.
            _assert_gpu_available({"0"})
            common = []
            created.append(_launch(
                "ltx-control-storage", service, _script("storage_manager.py"), "phase1_ltx",
                common, conda_root, args.python, {"CUDA_VISIBLE_DEVICES": None}, set(),
            ))
            created.append(_launch(
                "ltx-control-upload", service, _script("hf_upload_daemon.py"), "phase1_ltx",
                ["--yes"], conda_root, args.python, {"CUDA_VISIBLE_DEVICES": None}, set(),
            ))
            created.append(_launch(
                "ltx-control-brain", service, _script("brain.py"), "phase1_ltx",
                [], conda_root, args.python, {"CUDA_VISIBLE_DEVICES": "0"}, {"0"},
            ))
            _emit("LTX_CONTROL_READY storage/upload/brain launched. QA is intentionally separate: use a free GPU on a worker node.")
            return
        if service == "ltx-worker":
            gpus = _resolve_worker_gpus(args.gpus)
            _assert_gpu_available(gpus)
            resolved_gpu_arg = ",".join(sorted(gpus, key=int))
            cmd_args = ["--no-purge", "--cluster-gpus", str(args.cluster_gpus), "--gpus", resolved_gpu_arg]
            state = _launch(
                "ltx-worker", service, _script("worker_ltx_video.py"), "phase1_ltx",
                cmd_args, conda_root, args.python, {"CUDA_VISIBLE_DEVICES": None}, gpus,
            )
            created.append(state)
            return
        if service == "qa":
            gpu = str(args.gpu)
            if not gpu.isdigit():
                raise ValueError("--gpu must be a non-negative physical GPU index.")
            _assert_gpu_available({gpu})
            state = _launch(
                "qa-worker", service, _script("qa_compliance_worker.py"), "phase1_ltx",
                ["--gpu", gpu, "--no-purge"], conda_root, args.python,
                {"AIEROS_QA_GPU": gpu, "CUDA_VISIBLE_DEVICES": gpu}, {gpu},
            )
            created.append(state)
            return
        if service == "flux-image":
            gpu = str(args.gpu)
            if not gpu.isdigit():
                raise ValueError("--gpu must be a non-negative physical GPU index.")
            _assert_gpu_available({gpu})
            run_tag = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
            output_path = (args.output.expanduser().resolve() if args.output else Path("/tmp") / f"oec-flux-{run_tag}.png")
            try:
                output_path.relative_to(Path("/tmp").resolve())
            except ValueError as exc:
                raise ValueError("flux-image scratch output must be under local /tmp; managed shared-output writes require a separate fresh-quota preflight.") from exc
            if output_path.exists() or output_path.with_name(output_path.stem + "_info.json").exists():
                raise FileExistsError(f"Refusing to overwrite FLUX scratch output: {output_path}")
            cmd_args = [
                "--mode", "generate", "--offline", "--scratch-output", "--gpu", gpu,
                "--output", str(output_path), "--prompt", args.prompt, "--seed", str(args.seed),
                "--width", str(args.width), "--height", str(args.height), "--steps", str(args.steps),
                "--guidance-scale", str(args.guidance_scale),
            ]
            created.append(_launch(
                f"flux-image-{run_tag}", service, _script("pipeline_flux_image.py"), "phase2_3d",
                cmd_args, conda_root, args.python, {"CUDA_VISIBLE_DEVICES": None}, {gpu},
            ))
            _emit(f"FLUX_IMAGE_OUTPUT={output_path}")
            return
        if service == "flux-ui":
            gpu = str(args.gpu)
            if not gpu.isdigit():
                raise ValueError("--gpu must be a non-negative physical GPU index.")
            _assert_gpu_available({gpu})
            created.append(_launch(
                "flux-ui", service, _script("pipeline_flux_image.py"), "phase2_3d",
                ["--mode", "gradio", "--offline", "--gpu", gpu, "--port", str(args.port)],
                conda_root, args.python, {"CUDA_VISIBLE_DEVICES": None}, {gpu},
            ))
            return
        if service == "trellis-ui":
            gpu = str(args.gpu)
            if not gpu.isdigit():
                raise ValueError("--gpu must be a non-negative physical GPU index.")
            _assert_gpu_available({gpu})
            created.append(_launch(
                "trellis-ui", service, _script("pipeline_trellis_3d.py"), "phase2_3d",
                ["--mode", "gradio", "--offline", "--gpu", gpu, "--port", str(args.port)],
                conda_root, args.python, {"CUDA_VISIBLE_DEVICES": None}, {gpu},
            ))
            return
        if service == "trellis-batch":
            gpu = str(args.gpu)
            if not gpu.isdigit():
                raise ValueError("--gpu must be a non-negative physical GPU index.")
            _assert_gpu_available({gpu})
            if args.image_dir is None:
                raise ValueError("--image-dir is required for trellis-batch.")
            input_dir = args.image_dir.expanduser().resolve()
            if not input_dir.is_dir():
                raise NotADirectoryError(f"Image folder not found: {input_dir}")
            run_tag = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
            output_dir = (args.output_dir.expanduser().resolve() if args.output_dir else
                          Path("/tmp") / f"oec-trellis-batch-{run_tag}")
            try:
                output_dir.relative_to(Path("/tmp").resolve())
            except ValueError as exc:
                raise ValueError("trellis-batch scratch output must be under local /tmp; managed output writes require a separate fresh-quota preflight.") from exc
            if output_dir.exists():
                raise FileExistsError(f"Refusing to reuse existing TRELLIS batch output directory: {output_dir}")
            cmd_args = [
                "--mode", "generate-batch", "--offline", "--scratch-output",
                "--gpu", gpu, "--input-dir", str(input_dir),
                "--output-dir", str(output_dir),
                "--max-image-size", str(args.max_image_size),
                "--decimation-target", str(args.decimation_target),
                "--texture-size", str(args.texture_size),
            ]
            if args.recursive:
                cmd_args.append("--recursive")
            run_state = _launch(
                f"trellis-batch-{run_tag}", service, _script("pipeline_trellis_3d.py"), "phase2_3d",
                cmd_args, conda_root, args.python, {"CUDA_VISIBLE_DEVICES": None}, {gpu},
            )
            created.append(run_state)
            _emit(f"TRELLIS_BATCH_OUTPUT_DIR={output_dir}")
            return
        if service == "flux-trellis":
            if args.source_mode == "images":
                if args.image_dir is None:
                    raise ValueError("--image-dir is required with --source-mode images.")
                input_dir = args.image_dir.expanduser().resolve()
                if not input_dir.is_dir():
                    raise NotADirectoryError(f"Image folder not found: {input_dir}")
                cmd_args = ["--source-mode", "images", "--image-dir", str(input_dir)]
                if args.recursive:
                    cmd_args.append("--recursive")
            else:
                if args.image_dir is not None or args.recursive:
                    raise ValueError("--image-dir and --recursive require --source-mode images.")
                cmd_args = []
            run_tag = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
            instance = f"flux-trellis-{run_tag}"
            work = Path("/tmp") / f"oec-flux-trellis-{run_tag}"
            cmd_args = ["--work-dir", str(work)] + cmd_args
            state = _launch(
                instance, service, _script("pipeline_flux_trellis.py"), "phase2_3d",
                cmd_args, conda_root, args.python, {"CUDA_VISIBLE_DEVICES": None}, set(),
            )
            created.append(state)
            return
        raise ValueError(f"Unknown service {service!r}.")
    except Exception:
        for state in reversed(created):
            _stop_state(state, grace_seconds=3)
        raise


def print_status(service: str) -> None:
    targets = _select_action_targets(service)
    if not targets:
        _emit(f"NO_MANAGED_INSTANCE service={service}")
        return
    for state in targets:
        members = _matching_members(state)
        status = "RUNNING" if members else "EXITED/NOT RUNNING"
        print(json.dumps({
            "status": status,
            "service": state.get("instance_id"),
            "group": state.get("group"),
            "pid": state.get("pid"),
            "matching_pids": [x["pid"] for x in members],
            "gpus": state.get("gpus", []),
            "environment": state.get("environment"),
            "host": state.get("host"),
            "log": state.get("log_path"),
            "argv": state.get("argv"),
        }, sort_keys=True))


def stop_service(service: str, grace_seconds: float) -> None:
    targets = _select_action_targets(service)
    if not targets:
        _emit(f"NO_MANAGED_INSTANCE service={service}")
        return
    for state in reversed(targets):
        _stop_state(state, grace_seconds=grace_seconds)


def show_logs(service: str, tail: int) -> None:
    targets = _select_action_targets(service)
    if not targets:
        _emit(f"NO_MANAGED_INSTANCE service={service}")
        return
    for state in targets:
        path = Path(state.get("log_path", ""))
        print(f"\n===== {state.get('instance_id')} | {path} =====")
        if not path.is_file():
            print("Log file is not present.")
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            print("\n".join(lines[-max(1, tail):]))
        except OSError as exc:
            print(f"Unable to read log: {exc}")



CLUSTER_CONFIG_DEFAULT = REPO_ROOT / "tools" / "oec_cluster_services.local.json"
CLUSTER_SERVICES = {"ltx-control", "ltx-worker", "qa", "flux-image", "flux-ui", "trellis-batch", "trellis-ui", "flux-trellis"}


def _cluster_config(path: Path) -> dict[str, Any]:
    try:
        cfg = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Cluster config not found: {path}. Copy tools/oec_cluster_services.example.json to tools/oec_cluster_services.local.json and edit node aliases.") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid cluster JSON: {exc}") from exc
    if not isinstance(cfg, dict) or cfg.get("schema_version") != 1:
        raise ValueError("Cluster config must have schema_version: 1.")
    if not isinstance(cfg.get("nodes"), dict) or not cfg["nodes"]:
        raise ValueError("Cluster config needs a non-empty nodes object.")
    if not isinstance(cfg.get("profiles"), dict) or not cfg["profiles"]:
        raise ValueError("Cluster config needs a non-empty profiles object.")
    for name, node in cfg["nodes"].items():
        if not isinstance(node, dict) or not isinstance(node.get("host"), str) or not node["host"]:
            raise ValueError(f"nodes.{name}.host must be 'local' or an SSH hostname/alias.")
        for key in ("project_dir", "conda_activate"):
            if not isinstance(node.get(key), str) or not node[key]:
                raise ValueError(f"nodes.{name}.{key} must be a non-empty string.")
        if not 1 <= int(node.get("ssh_port", 22)) <= 65535:
            raise ValueError(f"nodes.{name}.ssh_port must be in 1..65535.")
    for name, tasks in cfg["profiles"].items():
        if not isinstance(tasks, list) or not tasks:
            raise ValueError(f"profiles.{name} must be a non-empty array.")
        ids, seen_node_services = set(), set()
        for i, task in enumerate(tasks):
            where = f"profiles.{name}[{i}]"
            if not isinstance(task, dict) or not task.get("id") or not task.get("node") or not task.get("service"):
                raise ValueError(f"{where} requires id, node, and service.")
            if task["id"] in ids:
                raise ValueError(f"Duplicate task id {task['id']} in profile {name}.")
            ids.add(task["id"])
            if task["node"] not in cfg["nodes"]:
                raise ValueError(f"{where}.node does not exist in nodes.")
            if task["service"] not in CLUSTER_SERVICES:
                raise ValueError(f"{where}.service {task['service']!r} is not supported.")
            key = (task["node"], task["service"])
            if key in seen_node_services:
                raise ValueError(f"{where}: a profile may invoke each service at most once per node.")
            seen_node_services.add(key)
            if not isinstance(task.get("args", []), list) or not all(isinstance(a, str) for a in task.get("args", [])):
                raise ValueError(f"{where}.args must be an array of strings.")
    cfg["_config_path"] = str(path.expanduser().resolve())
    return cfg


def _cluster_shell_path(value: str) -> str:
    if value == "~":
        return '"$HOME"'
    if value.startswith("~/"):
        return '"$HOME"/' + shlex.quote(value[2:])
    return shlex.quote(value)


def _cluster_invoke(node: dict[str, Any], cfg: dict[str, Any], action: str, service: str,
                    service_args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    conda_root = node.get("conda_root", cfg.get("conda_root", "~/Conda"))
    if node["host"] == "local":
        argv = [sys.executable, str(_script("tools/oec_service_manager.py")),
                "--conda-root", str(Path(conda_root).expanduser()), action, service, *service_args]
        return subprocess.run(argv, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout, check=False)

    project_dir = node["project_dir"]
    activate = node["conda_activate"]
    manager_env = node.get("manager_env", cfg.get("manager_env", "phase1_ltx"))
    tail = shlex.join([action, service, *service_args])
    remote_script = (
        f"cd {_cluster_shell_path(project_dir)}"
        f" && source {_cluster_shell_path(activate)}"
        f" && conda activate {shlex.quote(manager_env)}"
        f" && python tools/oec_service_manager.py --conda-root {_cluster_shell_path(conda_root)} {tail}"
    )
    target = f"{node['user']}@{node['host']}" if node.get("user") else node["host"]
    ssh = ["ssh", "-T", "-p", str(int(node.get("ssh_port", 22))),
           "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
           target, "bash -lc " + shlex.quote(remote_script)]
    return subprocess.run(ssh, capture_output=True, text=True, timeout=timeout, check=False)


def _cluster_tasks(cfg: dict[str, Any], profile: str, args: argparse.Namespace) -> list[dict[str, Any]]:
    if profile not in cfg["profiles"]:
        raise ValueError(f"Unknown cluster profile {profile!r}; available: {', '.join(sorted(cfg['profiles']))}.")
    tasks = json.loads(json.dumps(cfg["profiles"][profile]))
    for task in tasks:
        task["args"] = list(task.get("args", []))
        if task["service"] != "flux-trellis":
            continue
        mode, image_dir, recursive = args.source_mode, args.image_dir, args.recursive
        if image_dir is not None and mode is None:
            mode = "images"
        if recursive and mode is None:
            mode = "images"
        if mode is not None:
            if mode == "images" and image_dir is None and "--image-dir" not in task["args"]:
                raise ValueError("--source-mode images requires --image-dir or a configured --image-dir in the profile.")
            if mode == "flux":
                image_dir, recursive = None, False
            task["args"] = _set_flag(task["args"], "--source-mode", mode)
        if image_dir is not None:
            task["args"] = _set_flag(task["args"], "--image-dir", str(image_dir.expanduser()))
        if recursive:
            if "--recursive" not in task["args"]:
                task["args"].append("--recursive")
        else:
            task["args"] = [a for a in task["args"] if a != "--recursive"]
    return tasks


def _set_flag(items: list[str], flag: str, value: str) -> list[str]:
    out, i = [], 0
    while i < len(items):
        if items[i] == flag:
            i += 2
            continue
        out.append(items[i])
        i += 1
    out.extend([flag, value])
    return out


def _cluster_preflight(node: dict[str, Any], cfg: dict[str, Any], service: str) -> None:
    # This is a help-only check. It verifies reachability, working tree and CLI
    # syntax on each node without starting a model or touching a GPU.
    result = _cluster_invoke(node, cfg, "start", service, ["--help"], timeout=30)
    if result.returncode:
        detail = (result.stdout + "\n" + result.stderr).strip()[-1600:]
        raise RuntimeError(f"Preflight failed for node {node['host']} service {service}: {detail}")


def _cluster_manifest_dir() -> Path:
    return STATE_ROOT / "clusters"


def _cluster_manifest_path(rid: str) -> Path:
    return _cluster_manifest_dir() / f"{_safe_id(rid)}.json"


def _cluster_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + os.urandom(4).hex()


def _cluster_load_run(run_id: str | None) -> dict[str, Any]:
    folder = _cluster_manifest_dir()
    files = sorted(folder.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True) if folder.exists() else []
    if run_id is None:
        if not files:
            raise ValueError("No cluster run manifest found. Run cluster-start first.")
        path = files[0]
    else:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", run_id):
            raise ValueError("Invalid --run-id.")
        path = _cluster_manifest_path(run_id)
    if not path.is_file():
        raise ValueError(f"Cluster run manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _cluster_save_run(manifest: dict[str, Any]) -> Path:
    folder = _cluster_manifest_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = _cluster_manifest_path(manifest["run_id"])
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def _cluster_print_plan(cfg: dict[str, Any], tasks: list[dict[str, Any]], rid: str) -> None:
    print(f"CLUSTER_RUN_ID={rid} TASKS={len(tasks)}")
    for t in tasks:
        node = cfg["nodes"][t["node"]]
        print(f"{t['id']}: node={t['node']} host={node['host']} service={t['service']} args={shlex.join(t['args'])}")


def _cluster_start(args: argparse.Namespace) -> int:
    cfg = _cluster_config(args.config)
    rid = args.run_id or _cluster_run_id()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", rid):
        raise ValueError("Invalid --run-id.")
    tasks = _cluster_tasks(cfg, args.profile, args)
    _cluster_print_plan(cfg, tasks, rid)
    if args.dry_run:
        print("CLUSTER_DRY_RUN=PASS; no SSH commands or services launched.")
        return 0

    # Check each distinct host and each service-specific CLI before starting
    # the first daemon; prevents stale checkouts from causing avoidable partial starts.
    seen = set()
    for task in tasks:
        key = (task["node"], task["service"])
        if key in seen:
            continue
        seen.add(key)
        _cluster_preflight(cfg["nodes"][task["node"]], cfg, task["service"])

    manifest = {"schema_version": 1, "run_id": rid, "profile": args.profile,
                "config_path": cfg["_config_path"], "created_at_utc": datetime.now(timezone.utc).isoformat(), "tasks": []}
    failed = False
    for task in tasks:
        node = cfg["nodes"][task["node"]]
        try:
            result = _cluster_invoke(node, cfg, "start", task["service"], task["args"], timeout=90)
            detail = (result.stdout + ("\n" + result.stderr if result.stderr else "")).strip()[-3000:]
            owned = result.returncode == 0
            entry = {"id": task["id"], "node": task["node"], "host": node["host"],
                     "service": task["service"], "args": task["args"],
                     "status": "STARTED" if owned else "FAILED", "owned_by_run": owned,
                     "return_code": result.returncode, "detail": detail}
            manifest["tasks"].append(entry)
            print(f"CLUSTER_TASK_STATUS={entry['status']} id={task['id']} node={task['node']} service={task['service']}")
            if not owned:
                failed = True
                if not args.continue_on_error:
                    print("STOP_ON_FIRST_ERROR=1; use --continue-on-error to attempt remaining tasks.")
                    break
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            failed = True
            manifest["tasks"].append({"id": task["id"], "node": task["node"], "host": node["host"],
                                      "service": task["service"], "args": task["args"], "status": "ERROR",
                                      "owned_by_run": False, "detail": f"{type(exc).__name__}: {exc}"})
            print(f"CLUSTER_TASK_STATUS=ERROR id={task['id']} node={task['node']} error={exc}", file=sys.stderr)
            if not args.continue_on_error:
                break
    path = _cluster_save_run(manifest)
    print(f"CLUSTER_RUN_ID={rid}\nCLUSTER_MANIFEST={path}")
    return 1 if failed else 0


def _cluster_action(args: argparse.Namespace) -> int:
    cfg = _cluster_config(args.config)
    manifest = _cluster_load_run(args.run_id)
    filters = getattr(args, "service", None)
    node_filter = getattr(args, "node", None)
    items = manifest["tasks"]
    if filters:
        items = [e for e in items if e["service"] == filters]
    if node_filter:
        items = [e for e in items if e["node"] == node_filter]
    if not items:
        raise ValueError("No cluster tasks match the requested service/node filter.")
    failed = False
    reverse = args.action == "cluster-stop"
    for entry in reversed(items) if reverse else items:
        if args.action == "cluster-stop" and not entry.get("owned_by_run"):
            print(f"{entry['id']}: SKIP (not started by this cluster run)")
            continue
        node = cfg["nodes"].get(entry["node"])
        if node is None:
            raise ValueError(f"Node {entry['node']!r} is missing from the selected config.")
        if args.action == "cluster-status":
            action, task_args = "status", []
        elif args.action == "cluster-stop":
            action, task_args = "stop", ["--grace-seconds", str(args.grace_seconds)]
        else:
            action, task_args = "logs", ["--tail", str(args.tail)]
        result = _cluster_invoke(node, cfg, action, entry["service"], task_args, timeout=90)
        if result.stdout:
            print(f"\n===== {entry['id']} | node={entry['node']} service={entry['service']} =====")
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
        if result.returncode:
            failed = True
    return 1 if failed else 0


def _cluster_profiles(args: argparse.Namespace) -> int:
    cfg = _cluster_config(args.config)
    for name, tasks in sorted(cfg["profiles"].items()):
        print(f"{name}: {len(tasks)} task(s)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=("Examples:\n"
                "  python tools/oec_service_manager.py start ltx-control --help\n"
                "  python tools/oec_service_manager.py start ltx-worker --gpus 2,3 --cluster-gpus 10\n"
                "  python tools/oec_service_manager.py start qa --gpu 1\n"
                "  python tools/oec_service_manager.py start flux-ui --gpu 0 --port 7864\n"
                "  python tools/oec_service_manager.py start trellis-ui --gpu 0 --port 7862\n"
                "  python tools/oec_service_manager.py start trellis-batch --gpu 0 --image-dir /data/images\n"
                "  python tools/oec_service_manager.py start flux-trellis --source-mode images --image-dir /data/images --recursive\n"
                "  python tools/oec_service_manager.py cluster-start ltx-3node --config tools/oec_cluster_services.local.json\n"
                "Every action, including each service-specific start, has its own --help page."),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--conda-root", type=Path, default=DEFAULT_CONDA_ROOT,
                        help="Conda root (default: CONDA_ROOT or ~/Conda). Must precede the action.")
    parser.add_argument("--python", help="Optional explicit Python executable override for local smoke tests or custom environments.")
    sub = parser.add_subparsers(dest="action", required=True)
    services = ("ltx-control", "ltx-worker", "qa", "flux-image", "flux-ui", "trellis-batch", "trellis-ui", "flux-trellis")

    def service_parser(action: str, help_text: str, description: str):
        child = sub.add_parser(action, help=help_text, description=description)
        child.add_argument("service", choices=services, help="Service or service bundle.")
        return child

    child = service_parser("start", "Start a managed service or service bundle.",
                           "Start one local OEC service. Process groups are tracked separately; no package installs or model downloads are performed.")
    child.add_argument("--gpus", help="Comma-separated physical GPU IDs for LTX worker, e.g. 2,3.")
    child.add_argument("--cluster-gpus", type=int, default=11,
                       help="Expected total LTX worker GPU count across nodes; used by the worker's coordinated maintenance logic (default: 11).")
    child.add_argument("--gpu", default="0", help="Single physical GPU for QA, FLUX, TRELLIS; reserved GPUs are checked against managed services.")
    child.add_argument("--port", type=int, default=7864, help="Gradio port (FLUX default 7864; use 7862 for TRELLIS).")
    child.add_argument("--source-mode", choices=("flux", "images"), default="flux",
                       help="Combined FLUX→TRELLIS input mode: generate with FLUX (default) or use existing images.")
    child.add_argument("--image-dir", type=Path, help="Image folder for source-mode images or TRELLIS batch.")
    child.add_argument("--recursive", action="store_true", help="Include supported images in nested folders.")
    child.add_argument("--prompt", default="A polished red ceramic tea kettle on a quiet studio table, soft natural window light, realistic product photography.")
    child.add_argument("--seed", type=int, default=2048)
    child.add_argument("--width", type=int, default=512)
    child.add_argument("--height", type=int, default=512)
    child.add_argument("--steps", type=int, default=4)
    child.add_argument("--guidance-scale", type=float, default=1.0)
    child.add_argument("--output", type=Path, help="FLUX-only PNG output; must be under /tmp.")
    child.add_argument("--output-dir", type=Path, help="TRELLIS batch GLB directory; must be under /tmp and not already exist.")
    child.add_argument("--max-image-size", type=int, default=1024)
    child.add_argument("--decimation-target", type=int, default=100000)
    child.add_argument("--texture-size", type=int, default=2048)

    child = service_parser("stop", "Stop a previously started managed service.",
                           "Stop the recorded service's isolated process group after verifying the specific script identity.")
    child.add_argument("--grace-seconds", type=float, default=25.0,
                       help="Graceful shutdown window before a verified managed process group may be force-stopped (default: 25).")

    service_parser("status", "Show service status and recorded GPU/log details.",
                   "Read-only status report for a service bundle or one managed instance.")
    child = service_parser("logs", "Show service logs.",
                           "Print the tail of the log files associated with a service bundle or one managed instance.")
    child.add_argument("--tail", type=int, default=60, help="Number of trailing log lines (default: 60).")

    def cluster_config_arg(child):
        child.add_argument("--config", type=Path, default=CLUSTER_CONFIG_DEFAULT,
                           help=f"Cluster JSON config (default: {CLUSTER_CONFIG_DEFAULT}).")

    child = sub.add_parser("cluster-profiles", help="List configured multi-node profiles.",
                           description="List cluster profiles from the selected JSON config.")
    cluster_config_arg(child)

    child = sub.add_parser("cluster-plan", help="Print a multi-node launch plan without contacting nodes.",
                           description="Expand a cluster profile and show all node/service assignments without SSH or GPU work.")
    child.add_argument("profile", help="Profile name from the cluster config.")
    child.add_argument("--run-id", help="Run ID used in temporary output paths; generated if omitted.")
    child.add_argument("--source-mode", choices=("flux", "images"), help="Override source mode for flux-trellis tasks.")
    child.add_argument("--image-dir", type=Path, help="Existing image folder passed to flux-trellis image mode.")
    child.add_argument("--recursive", action="store_true", help="Include nested images in folder mode.")
    cluster_config_arg(child)

    child = sub.add_parser("cluster-start", help="Launch a multi-node profile with one command.",
                           description="Preflight node connectivity and service-specific CLI help, then start the configured services over local execution/SSH.")
    child.add_argument("profile", help="Profile name from the cluster config, e.g. ltx-3node or mixed-stack.")
    child.add_argument("--run-id", help="Optional run ID; generated otherwise.")
    child.add_argument("--dry-run", action="store_true", help="Print the profile only; do not connect to nodes or start processes.")
    child.add_argument("--continue-on-error", action="store_true", help="Attempt later services after a launch failure.")
    child.add_argument("--source-mode", choices=("flux", "images"), help="Override source mode for flux-trellis tasks.")
    child.add_argument("--image-dir", type=Path, help="Existing image folder passed to flux-trellis image mode.")
    child.add_argument("--recursive", action="store_true", help="Include nested images in folder mode.")
    cluster_config_arg(child)

    for action, help_text, desc in (
        ("cluster-status", "Check services for a cluster run.", "Query each recorded service on its owning node."),
        ("cluster-stop", "Stop services launched by a cluster run.", "Stop only services marked as started by the selected cluster run, in reverse startup order."),
        ("cluster-logs", "Read logs for a cluster run.", "Fetch service logs from the appropriate local/SSH node."),
    ):
        child = sub.add_parser(action, help=help_text, description=desc)
        child.add_argument("--run-id", help="Cluster run ID; defaults to the latest run recorded on this control node.")
        child.add_argument("--service", choices=services, help="Limit operation to one service type.")
        child.add_argument("--node", help="Limit operation to a configured node key.")
        cluster_config_arg(child)
        if action == "cluster-stop":
            child.add_argument("--grace-seconds", type=float, default=25.0,
                               help="Grace period before existing manager's verified escalation (default: 25).")
        if action == "cluster-logs":
            child.add_argument("--tail", type=int, default=60, help="Number of trailing log lines (default: 60).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == "start":
            start_service(args)
            return 0
        if args.action == "stop":
            stop_service(args.service, args.grace_seconds)
            return 0
        if args.action == "status":
            print_status(args.service)
            return 0
        if args.action == "logs":
            show_logs(args.service, args.tail)
            return 0
        if args.action == "cluster-profiles":
            return _cluster_profiles(args)
        if args.action in {"cluster-plan", "cluster-start"}:
            cfg = _cluster_config(args.config)
            if args.action == "cluster-plan":
                rid = args.run_id or _cluster_run_id()
                tasks = _cluster_tasks(cfg, args.profile, args)
                _cluster_print_plan(cfg, tasks, rid)
                return 0
            return _cluster_start(args)
        if args.action in {"cluster-status", "cluster-stop", "cluster-logs"}:
            return _cluster_action(args)
        raise ValueError(f"Unsupported action: {args.action}")
    except Exception as exc:
        _emit(f"ERROR {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
