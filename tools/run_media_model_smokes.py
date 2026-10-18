#!/usr/bin/env python3
"""Run sequential live media-model smoke jobs in pre-existing Conda environments."""
from __future__ import annotations

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


def _env_for(provider: str, envs: dict[str, Path]) -> tuple[str | None, Path | None, dict[str, bool]]:
    report: dict[str, bool] = {}
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
        with urllib.request.urlopen(url, timeout=4) as response:
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
    try:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    except OSError:
        return {"provider": provider, "status": "SKIPPED", "reason": f"loopback port {port} is occupied; no process was stopped"}, None

    service_log = log_dir / f"{provider}-service.log"
    smoke_log = log_dir / f"{provider}-smoke.log"
    env = os.environ.copy()
    env["PATH"] = str(python.parent) + os.pathsep + env.get("PATH", "")
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + str(MEDIA) + os.pathsep + env.get("PYTHONPATH", "")
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
    temp_dir = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "oec-media-smoke-logs"
    temp_dir.mkdir(parents=True, exist_ok=True)
    envs = _conda_prefixes()
    results: list[dict[str, Any]] = []
    kokoro_wav: Path | None = None
    errors = 0
    order = ("kokoro", "whisper", "qwen3-asr", "ace-step")
    for provider in order:
        name, python, report = _env_for(provider, envs)
        if python is None:
            summary = {"provider": provider, "status": "SKIPPED",
                       "reason": "none of phase1, phase1_ltx, phase2_3d has all runtime packages; no packages were installed",
                       "environment_checks": report}
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
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
