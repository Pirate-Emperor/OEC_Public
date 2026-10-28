#!/usr/bin/env python3
"""Run sequential live media-model smoke jobs in pre-existing Conda environments."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MEDIA = ROOT / "tools" / "media_services"
PYTHON_ENVS = ("phase1", "phase1_ltx", "phase2_3d")
PORTS = {"kokoro": 7871, "whisper": 7872, "qwen3-asr": 7873, "ace-step": 7870}
REQUIRED = {
    "kokoro": ("torch", "kokoro", "soundfile", "numpy", "huggingface_hub"),
    "whisper": ("torch", "whisper", "huggingface_hub"),
    "qwen3-asr": ("torch", "qwen_asr", "huggingface_hub"),
    "ace-step": ("torch", "acestep", "soundfile", "huggingface_hub"),
}
LOAD_TIMEOUT = {"kokoro": 300, "whisper": 420, "qwen3-asr": 600, "ace-step": 900}
JOB_TIMEOUT = {"kokoro": 180, "whisper": 300, "qwen3-asr": 420, "ace-step": 1500}


def _conda_prefixes() -> dict[str, Path]:
    conda = shutil.which("conda")
    if not conda:
        candidate = Path.home() / "Conda" / "bin" / "conda"
        conda = str(candidate) if candidate.is_file() else None
    if not conda:
        print("SMOKE_ENV_AUDIT: conda executable not found", flush=True)
        return {}
    proc = subprocess.run([conda, "env", "list", "--json"], text=True, capture_output=True, timeout=20)
    if proc.returncode:
        print("SMOKE_ENV_AUDIT: could not list Conda envs: " + proc.stderr[-2000:], flush=True)
        return {}
    return {Path(prefix).name: Path(prefix) for prefix in json.loads(proc.stdout).get("envs", [])}


def _configured_path(key: str, default: Path) -> Path:
    value = os.environ.get(key, "").strip()
    if not value:
        try:
            for raw in (Path.home() / ".env").read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    name, item = line.split("=", 1)
                    if name.strip() == key:
                        value = item.strip().strip("'").strip('"')
                        break
        except OSError:
            pass
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve() if value else default.expanduser().resolve()


def _ace_roots() -> tuple[Path, Path]:
    cache_root = _configured_path("AIEROS_CACHE_DIR", Path.home() / "aireos_cache")
    models_root = _configured_path("AIEROS_MODELS_DIR", Path.home() / "aireos_models")
    source_root = Path(os.environ.get(
        "AIEROS_ACE_STEP_SOURCE_ROOT", str(cache_root / "third_party" / "ACE-Step-1.5")
    )).expanduser().resolve()
    model_root = models_root / "ace-step-1.5"
    if not source_root.is_relative_to(cache_root):
        raise RuntimeError("ACE-Step source checkout must remain under AIEROS_CACHE_DIR")
    return source_root, model_root


def _free_a100_gpu() -> str:
    from oec_gpu_admission import select_idle_a100_gpu
    selected = select_idle_a100_gpu(caller="MEDIA")
    print(f"MEDIA_PHYSICAL_GPU={selected['index']}", flush=True)
    return selected["index"]


def _ace_env() -> dict[str, str]:
    source_root, model_root = _ace_roots()
    env = os.environ.copy()
    current_path = env.get("PYTHONPATH", "")
    env.update({
        "AIEROS_ACE_STEP_SOURCE_ROOT": str(source_root),
        "ACESTEP_PROJECT_ROOT": str(source_root),
        "ACESTEP_CHECKPOINTS_DIR": str(model_root),
        "ACESTEP_LM_BACKEND": "pt",
        "TORCH_HOME": str(model_root.parent / "torch_hub"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "PYTHONPATH": os.pathsep.join(str(x) for x in (source_root, ROOT, MEDIA, current_path) if str(x)),
        "PYTHONUNBUFFERED": "1",
    })
    return env


def _env_for(provider: str, envs: dict[str, Path]) -> tuple[str | None, Path | None, dict[str, bool]]:
    report: dict[str, bool] = {}
    if provider == "ace-step":
        # Never fall back to a shared Conda environment for ACE-Step.
        python = Path.home() / ".local" / "venvs" / "oec-acestep-py311" / "bin" / "python"
        if not python.is_file():
            report["oec-acestep-py311"] = False
            print("SMOKE_ENV provider=ace-step environment=oec-acestep-py311 present=false", flush=True)
            return None, None, report
        try:
            env = _ace_env()
            code = r'''
import json, os, sys
from pathlib import Path
import torch
import acestep
prefix = Path(sys.prefix).resolve()
source = Path(os.environ["AIEROS_ACE_STEP_SOURCE_ROOT"]).resolve()
model_root = Path(os.environ["ACESTEP_CHECKPOINTS_DIR"]).resolve()
required = ("acestep-v15-turbo", "vae", "Qwen3-Embedding-0.6B", "acestep-5Hz-lm-0.6B")
def has_weight(folder):
    if folder.is_symlink() or not folder.is_dir(): return False
    for parent, dirs, files in os.walk(folder, followlinks=False):
        base = Path(parent)
        dirs[:] = [d for d in dirs if not (base / d).is_symlink()]
        for name in files:
            p = base / name
            if p.is_symlink() or p.suffix.lower() not in {".safetensors", ".bin", ".pt", ".pth"}: continue
            try:
                if p.stat().st_size > 0: return True
            except OSError: pass
    return False
missing = [name for name in required if not has_weight(model_root / name)]
module = Path(acestep.__file__).resolve()
torch_path = Path(torch.__file__).resolve()
if source not in module.parents: raise SystemExit("ACE-Step import is not from the pinned source checkout")
if prefix not in torch_path.parents: raise SystemExit("Torch import is outside the isolated ACE-Step venv")
if missing: raise SystemExit("ACE-Step checkpoints missing: " + ",".join(missing))
if not torch.cuda.is_available(): raise SystemExit("CUDA is unavailable in the isolated ACE-Step runtime")
gpu = torch.cuda.get_device_name(0)
if "A100" not in gpu.upper(): raise SystemExit("expected A100, got " + gpu)
print(json.dumps({"source":str(source),"model_root":str(model_root),"torch_version":torch.__version__,
 "torch_path":str(torch_path),"gpu":gpu,"cuda_available":True,"missing":missing},sort_keys=True))
'''
            checked = subprocess.run([str(python), "-c", code], cwd=ROOT, env=env,
                                     text=True, capture_output=True, timeout=90, check=False)
            if checked.returncode:
                report["oec-acestep-py311"] = False
                detail = (checked.stdout + "\n" + checked.stderr).strip()[-1200:]
                print(f"SMOKE_ENV provider=ace-step environment=oec-acestep-py311 ready=false detail={detail}", flush=True)
                return None, None, report
            report["oec-acestep-py311"] = True
            print(f"SMOKE_ENV provider=ace-step environment=oec-acestep-py311 ready=true {checked.stdout.strip().splitlines()[-1]}", flush=True)
            return "oec-acestep-py311", python, report
        except Exception as exc:
            report["oec-acestep-py311"] = False
            print(f"SMOKE_ENV provider=ace-step environment=oec-acestep-py311 check_error={type(exc).__name__}: {exc}", flush=True)
            return None, None, report
    if provider in {"kokoro", "whisper", "qwen3-asr"}:
        python = Path.home() / ".local" / "venvs" / "oec-audio-py311" / "bin" / "python"
        if python.is_file():
            code = (
                "import importlib.util as u, json; "
                f"mods={list(REQUIRED[provider])!r}; "
                "print(json.dumps({m: bool(u.find_spec(m)) for m in mods}))"
            )
            try:
                proc = subprocess.run([str(python), "-c", code], cwd=ROOT, text=True,
                                      capture_output=True, timeout=15, check=False)
                available = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.returncode == 0 else {}
                report["oec-audio-venv"] = all(available.get(m, False) for m in REQUIRED[provider])
                print(f"SMOKE_ENV provider={provider} environment=oec-audio-venv packages={json.dumps(available)}", flush=True)
                if report["oec-audio-venv"]:
                    return "oec-audio-venv", python, report
            except Exception as exc:
                report["oec-audio-venv"] = False
                print(f"SMOKE_ENV provider={provider} environment=oec-audio-venv check_error={type(exc).__name__}", flush=True)
    for name in PYTHON_ENVS:
        prefix = envs.get(name)
        python = (prefix / "bin" / "python") if prefix else None
        if not python or not python.is_file():
            report[name] = False
            continue
        code = (
            "import importlib.util as u, json; "
            f"mods={list(REQUIRED[provider])!r}; "
            "print(json.dumps({m: bool(u.find_spec(m)) for m in mods}))"
        )
        try:
            proc = subprocess.run([str(python), "-c", code], cwd=ROOT, text=True,
                                  capture_output=True, timeout=15, check=False)
            available = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.returncode == 0 else {}
            report[name] = all(available.get(m, False) for m in REQUIRED[provider])
            print(f"SMOKE_ENV provider={provider} environment={name} packages={json.dumps(available)}", flush=True)
            if report[name]:
                return name, python, report
        except Exception as exc:
            print(f"SMOKE_ENV provider={provider} environment={name} check_error={type(exc).__name__}", flush=True)
            report[name] = False
    return None, None, report


def _health(url: str) -> tuple[bool, Any]:
    try:
        if not url.startswith(("http://127.0.0.1:", "http://localhost:", "http://[::1]:")):
            raise ValueError("health checks must target a loopback media service")
        local_http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with local_http.open(url, timeout=4) as response:
            return response.status == 200, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return False, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return False, {"http_status": exc.code}
    except Exception as exc:
        return False, {"error": type(exc).__name__}


def _run_provider(provider: str, python: Path, audio_path: Path | None, log_dir: Path, *, ui_python: Path | None = None, check_gradio_notebooks: bool = False) -> tuple[dict[str, Any], Path | None]:
    port = PORTS[provider]
    url = f"http://127.0.0.1:{port}"
    if provider == "whisper" and shutil.which("ffmpeg") is None:
        return {"provider": provider, "status": "SKIPPED", "reason": "ffmpeg executable is not available on PATH"}, None
    try:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    except OSError:
        return {"provider": provider, "status": "SKIPPED", "reason": f"loopback port {port} is occupied; no process was stopped"}, None

    service_log = log_dir / f"{provider}-service.log"
    smoke_log = log_dir / f"{provider}-smoke.log"
    env = _ace_env() if provider == "ace-step" else os.environ.copy()
    env["PATH"] = str(python.parent) + os.pathsep + env.get("PATH", "")
    env["PYTHONUNBUFFERED"] = "1"
    if provider != "ace-step":
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + str(MEDIA) + os.pathsep + env.get("PYTHONPATH", "")
    env["OEC_USE_MANAGER_DIRECTORY_ONLY"] = "0"
    # Select and pin an idle physical A100 for every provider, not just ACE-Step.
    try:
        selected_physical_gpu = _free_a100_gpu()
        env["CUDA_VISIBLE_DEVICES"] = selected_physical_gpu
    except Exception as exc:
        return {"provider": provider, "status": "FAIL",
                "reason": f"GPU admission failed: {type(exc).__name__}: {exc}"}, None
    command = [str(python), str(MEDIA / "audio_api.py"), "--model", provider, "--host", "127.0.0.1", "--port", str(port)]
    print(f"SMOKE_START provider={provider} environment_python={python} port={port}", flush=True)
    started = time.monotonic()
    owner_path = _service_owner_path(provider, log_dir)
    with service_log.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    _write_service_owner(provider, process.pid, command, owner_path)
    try:
        deadline = time.monotonic() + LOAD_TIMEOUT[provider]
        ready_payload: Any = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"service exited during startup with code {process.returncode}")
            ready, payload = _health(url + "/health")
            ready_payload = payload
            if ready and payload.get("ready") and payload.get("model_loaded"):
                break
            if isinstance(payload, dict) and payload.get("error") and not payload.get("loading", True):
                raise RuntimeError(
                    f"service reported a fatal model-loader error: {payload.get('error')}; see {service_log}"
                )
            time.sleep(4)
        else:
            raise TimeoutError(f"service did not become ready in {LOAD_TIMEOUT[provider]} seconds: {ready_payload}")

        if check_gradio_notebooks:
            if ui_python is None or not ui_python.is_file():
                raise RuntimeError("Gradio callback acceptance requested, but the phase2_3d UI Python is missing")
            if provider in {"whisper", "qwen3-asr"} and (audio_path is None or not audio_path.is_file()):
                raise RuntimeError(f"{provider} requires the WAV generated by the preceding Kokoro callback")
            command = [str(ui_python), str(ROOT / "tools" / "run_gradio_model_notebook_smokes.py"),
                       "--provider", provider, "--report-dir", str(log_dir)]
            if provider in {"whisper", "qwen3-asr"}:
                command += ["--audio-file", str(audio_path)]
            ui_env = {**env, "OEC_GRADIO_HEADLESS_SMOKE": "1", "OEC_MEDIA_API_URL": url}
            completed = subprocess.run(command, cwd=ROOT, env=ui_env, text=True, capture_output=True,
                                       timeout=JOB_TIMEOUT[provider] + 180, check=False)
            smoke_log.write_text(completed.stdout + "\nSTDERR:\n" + completed.stderr, encoding="utf-8")
            print(f"GRADIO_CALLBACK provider={provider} returncode={completed.returncode}\n{completed.stdout[-9000:]}", flush=True)
            if completed.stderr:
                print(f"GRADIO_CALLBACK_STDERR provider={provider}\n{completed.stderr[-5000:]}", flush=True)
            if completed.returncode:
                raise RuntimeError(f"Gradio notebook callback smoke failed with code {completed.returncode}; see {smoke_log}")
            callback_report = log_dir / f"{provider}-gradio-notebook-smoke.json"
            if not callback_report.is_file():
                raise RuntimeError("Gradio callback smoke did not create its JSON report")
            callback_data = json.loads(callback_report.read_text(encoding="utf-8"))
            if callback_data.get("status") != "PASS" or callback_data.get("ui_launch") != "PASS" or callback_data.get("callback") != "PASS":
                raise RuntimeError(f"Gradio callback report is not PASS: {callback_data}")
            artifact = Path(callback_data["artifact_path"]) if callback_data.get("artifact_path") else None
        else:
            command = [str(python), str(MEDIA / "smoke_client.py"), "--provider", provider,
                       "--url", url, "--timeout-seconds", str(JOB_TIMEOUT[provider])]
            if provider == "ace-step":
                command += ["--prompt", "A ten-second warm ambient fantasy game soundtrack with soft strings and flute", "--duration-seconds", "10"]
            elif provider in {"whisper", "qwen3-asr"}:
                if audio_path is None or not audio_path.is_file():
                    return {"provider": provider, "status": "SKIPPED", "reason": "no validated WAV file was produced by Kokoro"}, None
                command += ["--audio-file", str(audio_path)]
            completed = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True,
                                       timeout=JOB_TIMEOUT[provider] + 120, check=False)
            smoke_log.write_text(completed.stdout + "\nSTDERR:\n" + completed.stderr, encoding="utf-8")
            print(f"SMOKE_CLIENT provider={provider} returncode={completed.returncode}\n{completed.stdout[-9000:]}", flush=True)
            if completed.stderr:
                print(f"SMOKE_CLIENT_STDERR provider={provider}\n{completed.stderr[-5000:]}", flush=True)
            if completed.returncode:
                raise RuntimeError(f"smoke client exited with code {completed.returncode}; see {smoke_log}")
            match = re.search(r'"artifact_path"\s*:\s*"([^"]+)"', completed.stdout)
            artifact = Path(match.group(1)) if match else None
            if artifact is not None and not artifact.is_file():
                artifact = None
        elapsed = round(time.monotonic() - started, 2)
        report = {"provider": provider, "status": "PASS", "environment_python": str(python),
                  "startup_plus_inference_seconds": elapsed, "smoke_log": str(smoke_log),
                  "service_log": str(service_log), "artifact_path": str(artifact) if artifact else None}
        if selected_physical_gpu is not None:
            report["physical_gpu_index"] = selected_physical_gpu
        print("SMOKE_ACCEPTANCE " + json.dumps(report), flush=True)
        return report, artifact if provider == "kokoro" and artifact and artifact.suffix.lower() == ".wav" else None
    except Exception as exc:
        print(f"SMOKE_FAILURE provider={provider}: {type(exc).__name__}: {exc}", flush=True)
        try:
            lines = service_log.read_text(encoding="utf-8", errors="replace").splitlines()
            useful = [line for line in lines if "GET /health HTTP" not in line and "GET /healthz HTTP" not in line]
            print(f"--- model-loader diagnostics from {service_log} ---\n" + "\n".join((useful[-180:] or lines[:80])), flush=True)
        except OSError:
            pass
        return {"provider": provider, "status": "FAIL", "reason": f"{type(exc).__name__}: {exc}",
                "service_log": str(service_log), "smoke_log": str(smoke_log)}, None
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process.poll() is not None:
            owner_path.unlink(missing_ok=True)
        else:
            print(f"SMOKE_OWNER_MARKER_PRESERVED provider={provider} pid={process.pid}", flush=True)
        print(f"SMOKE_STOP provider={provider} returncode={process.returncode}", flush=True)


def _service_owner_path(provider: str, log_dir: Path) -> Path:
    return log_dir / f"{provider}-service-owner.json"


def _write_service_owner(provider: str, pid: int, command: list[str], path: Path) -> None:
    payload = {
        "provider": provider,
        "pid": int(pid),
        "host": socket.gethostname(),
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "created_unix": time.time(),
        "port": PORTS[provider],
        "expected_cmdline_prefix": [str(part) for part in command],
    }
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.chmod(0o600)
    temp_path.replace(path)


def _process_cmdline(pid: int) -> list[str] | None:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (OSError, ValueError):
        return None
    return [part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part]


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _owner_matches_running_process(owner: dict[str, Any]) -> bool:
    pid = owner.get("pid")
    expected = owner.get("expected_cmdline_prefix")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        return False
    if not isinstance(expected, list) or not expected or any(not isinstance(x, str) for x in expected):
        return False
    actual = _process_cmdline(pid)
    return bool(actual and actual[:len(expected)] == expected)


def _cleanup_owned_service(
    provider: str, log_dir: Path, *, grace_seconds: float = 15.0,
    allow_foreign_run: bool = False,
) -> dict[str, Any]:
    """Stop a recorded provider only when host and exact argv prove ownership.

    Prior-run markers are accepted only during explicit orphan recovery.
    """
    path = _service_owner_path(provider, log_dir)
    if not path.is_file() or path.is_symlink():
        return {"provider": provider, "status": "NOT_FOUND", "message": "no owned-process marker"}
    try:
        owner = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"provider": provider, "status": "BLOCKED_INVALID_MARKER", "message": str(exc)}
    if not isinstance(owner, dict):
        return {"provider": provider, "status": "BLOCKED_INVALID_MARKER", "message": "marker is not an object"}
    if owner.get("provider") != provider or owner.get("host") != socket.gethostname():
        return {"provider": provider, "status": "BLOCKED_OWNER_MISMATCH", "pid": owner.get("pid")}
    current_run_id = os.environ.get("GITHUB_RUN_ID", "local")
    owner_run_id = owner.get("run_id")
    recovered_prior_run = owner_run_id != current_run_id
    if recovered_prior_run and not allow_foreign_run:
        return {"provider": provider, "status": "BLOCKED_RUN_ID_MISMATCH", "pid": owner.get("pid")}
    pid = owner.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        return {"provider": provider, "status": "BLOCKED_INVALID_PID"}
    if not _pid_alive(pid):
        path.unlink(missing_ok=True)
        return {"provider": provider, "status": "ALREADY_EXITED", "pid": pid}
    if not _owner_matches_running_process(owner):
        return {"provider": provider, "status": "BLOCKED_COMMAND_MISMATCH", "pid": pid,
                "message": "recorded PID is alive but argv differs; process was not signalled"}
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + max(0.1, grace_seconds)
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            path.unlink(missing_ok=True)
            return {"provider": provider, "status": "STOPPED", "pid": pid, "signal": "SIGTERM",
                    "recovered_prior_run": recovered_prior_run, "owner_run_id": owner_run_id,
                    "recovery_run_id": current_run_id}
        time.sleep(0.25)
    if not _owner_matches_running_process(owner):
        return {"provider": provider, "status": "BLOCKED_COMMAND_CHANGED", "pid": pid,
                "message": "argv changed while waiting; refusing SIGKILL"}
    os.kill(pid, signal.SIGKILL)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            path.unlink(missing_ok=True)
            return {"provider": provider, "status": "STOPPED", "pid": pid, "signal": "SIGKILL",
                    "recovered_prior_run": recovered_prior_run, "owner_run_id": owner_run_id,
                    "recovery_run_id": current_run_id}
        time.sleep(0.1)
    return {"provider": provider, "status": "STOP_FAILED", "pid": pid,
            "message": "recorded process remained alive after SIGKILL"}


CACHE_KEY_FOR_PROVIDER = {
    "kokoro": "kokoro",
    "whisper": "whisper-turbo",
    "qwen3-asr": "qwen3-asr-0.6b",
    "ace-step": "ace-step",
}


def _purge_tested_model(provider: str) -> dict[str, Any]:
    key = CACHE_KEY_FOR_PROVIDER[provider]
    command = [sys.executable, str(ROOT / "tools" / "model_cache_manager.py"),
               "purge", key, "--confirm"]
    completed = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True, timeout=180, check=False,
    )
    output = completed.stdout + "\nSTDERR:\n" + completed.stderr
    result = {
        "model_cache_key": key,
        "returncode": completed.returncode,
        "status": "PASS" if completed.returncode == 0 else "BLOCKED_OR_FAILED",
        "output_tail": output[-6000:],
    }
    print("MODEL_CACHE_CLEANUP " + json.dumps(result, ensure_ascii=False), flush=True)
    return result




def _cleanup_owned_services_for_provider(
    provider: str, log_dir: Path, *, allow_foreign_run: bool = False
) -> list[dict[str, Any]]:
    """Clean this run and verified prior-run service markers on the same host.

    Service markers can persist in RUNNER_TEMP/oec-media-smoke-logs or below
    RUNNER_TEMP/oec-demo-notebook-acceptance-*. The cleanup routine validates a
    live PID and exact argv before SIGTERM. Foreign-host markers are diagnostic-only
    and are never used to signal a PID.
    """
    current_dir = log_dir.expanduser().resolve()
    directories = [current_dir]
    search_root = Path(os.environ.get("RUNNER_TEMP", "/tmp")).expanduser().resolve()
    if allow_foreign_run and search_root.is_dir():
        marker_name = f"{provider}-service-owner.json"
        # The default runner mode writes markers outside acceptance-run folders.
        # Search this known direct child as well, but never recursively walk all
        # of RUNNER_TEMP or follow symlinks into unrelated data.
        default_smoke_dir = search_root / "oec-media-smoke-logs"
        if default_smoke_dir.is_dir() and not default_smoke_dir.is_symlink():
            resolved = default_smoke_dir.resolve()
            try:
                resolved.relative_to(search_root)
            except ValueError:
                pass
            else:
                if resolved not in directories:
                    directories.append(resolved)
        pattern = f"oec-demo-notebook-acceptance-*/**/{marker_name}"
        for marker in sorted(search_root.glob(pattern)):
            if marker.is_symlink() or not marker.is_file():
                continue
            try:
                owner = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                print(f"SMOKE_OWNER_SCAN_BLOCKED_INVALID_MARKER path={marker}", flush=True)
                continue
            if not isinstance(owner, dict) or owner.get("provider") != provider:
                continue
            if owner.get("host") != socket.gethostname():
                print("SMOKE_OWNER_SCAN_SKIP_FOREIGN_HOST " + json.dumps(
                    {"provider": provider, "host": owner.get("host"), "path": str(marker)},
                    sort_keys=True), flush=True)
                continue
            parent = marker.parent.resolve()
            try:
                parent.relative_to(search_root)
            except ValueError:
                continue
            if parent not in directories:
                directories.append(parent)

    rows: list[dict[str, Any]] = []
    for directory in directories:
        row = _cleanup_owned_service(
            provider, directory, allow_foreign_run=allow_foreign_run
        )
        if row.get("status") != "NOT_FOUND" or directory == current_dir:
            rows.append(row)
    return rows
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--providers", default="kokoro,whisper,qwen3-asr,ace-step",
                        help="Comma-separated provider order; ACE-Step uses only its dedicated isolated venv.")
    parser.add_argument("--require-pass", action="store_true",
                        help="Treat a requested provider skip as failure for required acceptance.")
    parser.add_argument("--check-gradio-notebooks", action="store_true",
                        help="Launch the model-specific Gradio UI on loopback and invoke its real callback while the isolated backend is live.")
    parser.add_argument("--purge-after", action="store_true",
                        help="After each attempted provider stops, purge that provider's exact cache through model_cache_manager.")
    parser.add_argument("--cleanup-owned-services", action="store_true",
                        help="Recovery mode: stop only model-service PIDs recorded by this run and matching exact argv.")
    parser.add_argument("--recover-orphan-services", action="store_true",
                        help="Explicitly recover a prior-run owner marker only when host, PID and exact argv still match.")
    parser.add_argument("--log-dir", type=Path,
                        help="Override the owner/report directory (defaults to $RUNNER_TEMP/oec-media-smoke-logs).")
    args = parser.parse_args()
    available = set(REQUIRED)
    order = tuple(item.strip() for item in args.providers.split(",") if item.strip())
    if not order or len(order) != len(set(order)) or any(item not in available for item in order):
        parser.error(f"--providers must be unique entries from: {', '.join(sorted(available))}")
    temp_dir = (args.log_dir.expanduser().resolve() if args.log_dir else
                Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "oec-media-smoke-logs")
    temp_dir.mkdir(parents=True, exist_ok=True)
    if args.recover_orphan_services and not args.cleanup_owned_services:
        parser.error("--recover-orphan-services requires --cleanup-owned-services")
    if args.cleanup_owned_services:
        cleanup_rows = []
        for provider in order:
            cleanup_rows.extend(
                _cleanup_owned_services_for_provider(
                    provider, temp_dir, allow_foreign_run=args.recover_orphan_services
                )
            )
        for row in cleanup_rows:
            print("OWNED_SERVICE_CLEANUP " + json.dumps(row, ensure_ascii=False), flush=True)
        blocked = [row for row in cleanup_rows if row["status"].startswith("BLOCKED") or row["status"] == "STOP_FAILED"]
        print("OWNED_SERVICE_CLEANUP_SUMMARY " + json.dumps({
            "providers": cleanup_rows, "blocked_or_failed": len(blocked),
            "log_directory": str(temp_dir),
        }, ensure_ascii=False), flush=True)
        return 1 if blocked else 0
    envs = _conda_prefixes()
    results: list[dict[str, Any]] = []
    kokoro_wav: Path | None = None
    errors = 0
    for provider in order:
        name, python, report = _env_for(provider, envs)
        if python is None:
            summary = {"provider": provider, "status": "SKIPPED",
                       "reason": "none of phase1, phase1_ltx, phase2_3d has all runtime packages; no packages were installed",
                       "environment_checks": report}
            if args.require_pass:
                summary["status"] = "FAIL"
                summary["reason"] = "required provider is unavailable; " + summary["reason"]
                errors += 1
            results.append(summary)
            print("SMOKE_ACCEPTANCE " + json.dumps(summary), flush=True)
            continue
        ui_root = envs.get("phase2_3d")
        ui_python = (ui_root / "bin" / "python") if ui_root else None
        result, artifact = _run_provider(provider, python, kokoro_wav, temp_dir,
                                         ui_python=ui_python,
                                         check_gradio_notebooks=args.check_gradio_notebooks)
        # _run_provider stops only its own service before returning. Clean failed
        # attempts too so partial cache downloads cannot silently accumulate.
        if args.purge_after and result.get("status") in {"PASS", "FAIL"}:
            cleanup = _purge_tested_model(provider)
            result["cache_cleanup"] = cleanup
            if cleanup["status"] != "PASS":
                result["status"] = "FAIL"
                result["reason"] = (str(result.get("reason", "")) + " | cache cleanup blocked/failed").strip(" |")
        results.append(result)
        if result["status"] == "FAIL":
            errors += 1
        if artifact is not None:
            kokoro_wav = artifact
    summary = {"providers": results, "passed": sum(x["status"] == "PASS" for x in results),
               "failed": errors, "skipped": sum(x["status"] == "SKIPPED" for x in results),
               "log_directory": str(temp_dir)}
    print("SMOKE_SUITE_SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    # Missing runtimes are an explicit skip; real failures in a discovered runtime fail this acceptance job.
    if args.require_pass and summary["skipped"]:
        return 1
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
