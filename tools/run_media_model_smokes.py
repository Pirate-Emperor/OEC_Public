#!/usr/bin/env python3
"""Run sequential live media-model smoke jobs in pre-existing Conda environments."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
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
    inventory = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,name,uuid,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=12, check=False,
    )
    apps = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=12, check=False,
    )
    if inventory.returncode or apps.returncode:
        raise RuntimeError("GPU/process telemetry unavailable; refusing ACE-Step launch")
    busy_uuids = set()
    for line in apps.stdout.splitlines():
        fields = [part.strip() for part in line.split(",")]
        if len(fields) >= 2 and fields[0] and fields[1].isdigit():
            busy_uuids.add(fields[0])
    candidates = []
    for line in inventory.stdout.splitlines():
        fields = [part.strip() for part in line.split(",")]
        if len(fields) < 5 or not fields[0].isdigit() or "A100" not in fields[1].upper():
            continue
        try:
            memory_used, utilization = float(fields[3]), float(fields[4])
        except ValueError:
            continue
        if fields[2] not in busy_uuids and memory_used <= 1024 and utilization <= 5:
            candidates.append((int(fields[0]), memory_used, utilization))
    if not candidates:
        raise RuntimeError("no idle A100 available; no ACE-Step process was started")
    selected = str(min(candidates)[0])
    print(f"ACE_STEP_PHYSICAL_GPU={selected}", flush=True)
    return selected


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


def _run_provider(provider: str, python: Path, audio_path: Path | None, log_dir: Path) -> tuple[dict[str, Any], Path | None]:
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
    selected_physical_gpu = None
    if provider == "ace-step":
        try:
            selected_physical_gpu = _free_a100_gpu()
            env["CUDA_VISIBLE_DEVICES"] = selected_physical_gpu
        except Exception as exc:
            return {"provider": provider, "status": "FAIL",
                    "reason": f"GPU admission failed: {type(exc).__name__}: {exc}"}, None
    command = [str(python), str(MEDIA / "audio_api.py"), "--model", provider, "--host", "127.0.0.1", "--port", str(port)]
    print(f"SMOKE_START provider={provider} environment_python={python} port={port}", flush=True)
    started = time.monotonic()
    with service_log.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
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
            time.sleep(4)
        else:
            raise TimeoutError(f"service did not become ready in {LOAD_TIMEOUT[provider]} seconds: {ready_payload}")

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
            print(f"--- tail {service_log} ---\n" + "\n".join(service_log.read_text(encoding="utf-8", errors="replace").splitlines()[-100:]), flush=True)
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
        print(f"SMOKE_STOP provider={provider} returncode={process.returncode}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--providers", default="kokoro,whisper,qwen3-asr,ace-step",
                        help="Comma-separated provider order; ACE-Step uses only its dedicated isolated venv.")
    parser.add_argument("--require-pass", action="store_true",
                        help="Treat a requested provider skip as failure for required acceptance.")
    args = parser.parse_args()
    available = set(REQUIRED)
    order = tuple(item.strip() for item in args.providers.split(",") if item.strip())
    if not order or len(order) != len(set(order)) or any(item not in available for item in order):
        parser.error(f"--providers must be unique entries from: {', '.join(sorted(available))}")
    temp_dir = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "oec-media-smoke-logs"
    temp_dir.mkdir(parents=True, exist_ok=True)
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
        result, artifact = _run_provider(provider, python, kokoro_wav, temp_dir)
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
