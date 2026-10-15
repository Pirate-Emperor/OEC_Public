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
        start_time = int(tail[19])  # field 22: starttime, after fields 3..22
        cmdline_raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        cmdline = cmdline_raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
        return {"pid": pid, "pgid": pgid, "state": state, "start_time": start_time, "cmdline": cmdline}
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


def _is_running(state: dict[str, Any]) -> bool:
    return bool(_matching_members(state))


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

    state = {
        "schema_version": 1,
        "instance_id": instance_id,
        "service": instance_id,
        "group": group,
        "host": HOST,
        "pid": proc.pid,
        "pgid": proc.pid,
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
        if not _matching_members(state):
            _emit(f"STOPPED service={state.get('instance_id')} gracefully")
            return True
        time.sleep(0.25)
    # Escalate only while the exact recorded script remains in this exact managed group.
    members = _matching_members(state)
    if members:
        _emit(f"GRACE_EXPIRED service={state.get('instance_id')}; verified members remain; sending SIGKILL to managed group only")
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
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
                {"AIEROS_QA_GPU": gpu, "CUDA_VISIBLE_DEVICES": None}, {gpu},
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conda-root", type=Path, default=DEFAULT_CONDA_ROOT,
                        help="Conda root (default: $CONDA_ROOT or ~/Conda).")
    parser.add_argument("--python", help="Optional explicit Python executable override for smoke tests or custom environments.")
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("start", "stop", "status", "logs"):
        child = sub.add_parser(action)
        child.add_argument("service", choices=("ltx-control", "ltx-worker", "qa", "flux-image", "flux-ui", "trellis-ui", "flux-trellis"))
        if action == "start":
            child.add_argument("--gpus", help="Physical GPU IDs for an LTX worker, e.g. 1,2,3.")
            child.add_argument("--cluster-gpus", type=int, default=11)
            child.add_argument("--gpu", default="0", help="Single physical GPU for QA/FLUX/TRELLIS Gradio.")
            child.add_argument("--port", type=int, default=7864, help="Gradio port (FLUX default 7864; override TRELLIS to 7862).")
            child.add_argument("--source-mode", choices=("flux", "images"), default="flux",
                               help="Combined pipeline input source; defaults to FLUX, or existing image folder.")
            child.add_argument("--image-dir", type=Path, help="Image folder used when --source-mode images.")
            child.add_argument("--recursive", action="store_true", help="Use nested input images in folder mode.")
            child.add_argument("--prompt", default="A polished red ceramic tea kettle on a quiet studio table, soft natural window light, realistic product photography.")
            child.add_argument("--seed", type=int, default=2048)
            child.add_argument("--width", type=int, default=512)
            child.add_argument("--height", type=int, default=512)
            child.add_argument("--steps", type=int, default=4)
            child.add_argument("--guidance-scale", type=float, default=1.0)
            child.add_argument("--output", type=Path, help="FLUX-only output PNG path (must be under /tmp).")
        if action == "stop":
            child.add_argument("--grace-seconds", type=float, default=25.0)
        if action == "logs":
            child.add_argument("--tail", type=int, default=60)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == "start":
            start_service(args)
        elif args.action == "stop":
            stop_service(args.service, args.grace_seconds)
        elif args.action == "status":
            print_status(args.service)
        elif args.action == "logs":
            show_logs(args.service, args.tail)
        return 0
    except Exception as exc:
        _emit(f"ERROR {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
