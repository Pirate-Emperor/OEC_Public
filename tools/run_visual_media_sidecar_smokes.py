#!/usr/bin/env python3
"""Sequential, cache-only live acceptance for OEC TRELLIS and LTX JSON sidecars.

This script never downloads model weights or installs Python packages. It starts
only its own loopback service processes, sends one bounded request per ready
provider, validates the returned GLB/MP4, and terminates only those processes.
Missing runtime dependencies or checkpoints are reported as BLOCKED/SKIPPED.
"""
from __future__ import annotations

import base64
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "tools" / "media_services"
ENV_ROOT = Path.home() / "Conda" / "envs"
PROVIDERS = {
    "trellis": {
        "environment": "phase2_3d",
        "script": MEDIA / "trellis_api.py",
        "port": 17868,
        "startup_timeout_seconds": 900,
        "job_timeout_seconds": 1500,
    },
    "ltx": {
        "environment": "phase1_ltx",
        "script": MEDIA / "ltx_api.py",
        "port": 17869,
        "startup_timeout_seconds": 1200,
        "job_timeout_seconds": 1800,
    },
}


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _local_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _request(url: str, method: str = "GET", payload: dict[str, Any] | None = None,
             timeout: float = 15.0) -> tuple[int, bytes, dict[str, str]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _local_opener().open(req, timeout=timeout) as response:
            return int(response.status), response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(), dict(exc.headers.items())


def _probe_health(url: str) -> tuple[bool, dict[str, Any]]:
    try:
        code, raw, _ = _request(url + "/health", timeout=4)
        body = json.loads(raw.decode("utf-8"))
        return code == 200 and body.get("status") == "ok" and body.get("api_version") == 1 \
            and body.get("ready") is True and body.get("model_loaded") is True, body
    except Exception as exc:
        return False, {"error": type(exc).__name__, "detail": str(exc)[:300]}


def _port_is_free(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def _run_preflight_trellis(python: Path, env: dict[str, str], log_dir: Path) -> dict[str, Any]:
    log = log_dir / "trellis-cache-preflight.log"
    command = [str(python), str(ROOT / "pipeline_trellis_3d.py"), "--mode", "check", "--offline"]
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True,
                            timeout=240, check=False)
    log.write_text("COMMAND " + json.dumps(command) + "\n\nSTDOUT:\n" + result.stdout
                   + "\nSTDERR:\n" + result.stderr, encoding="utf-8")
    combined = result.stdout + "\n" + result.stderr
    if result.returncode == 0 and "TRELLIS_READY=PASS" in combined:
        return {"status": "PASS", "command": command, "log": str(log),
                "reason": "runtime dependencies and cached model are present"}
    if "DEPENDENCY_CHECK_PASS_MODEL_CACHE_MISS" in combined or "TRELLIS_MODEL_CACHE=MISS" in combined:
        return {"status": "SKIPPED", "command": command, "log": str(log),
                "reason": "model checkpoint is not complete in the existing cache; downloads disabled"}
    return {"status": "BLOCKED", "command": command, "log": str(log),
            "returncode": result.returncode, "reason": (combined[-2500:] or "no diagnostic output")}


def _run_preflight_ltx(python: Path, env: dict[str, str], log_dir: Path) -> dict[str, Any]:
    log = log_dir / "ltx-cache-preflight.log"
    probe = r'''
import os, sys, json
from pathlib import Path
try:
    import core_config
    root = Path(os.environ.get(
        "AIEROS_LTX_REPO_DIR",
        str(Path(core_config.SYSTEM_DIRS["cache"]) / "third_party" / "LTX-2")
    )).expanduser().resolve()
    if not (root / "packages" / "ltx-core").is_dir() or not (root / "packages" / "ltx-pipelines").is_dir():
        print("LTX_PREFLIGHT=SOURCE_MISSING path=" + str(root))
        raise SystemExit(21)
    try:
        import xformers
        from huggingface_hub import hf_hub_download, snapshot_download
    except Exception as exc:
        print("LTX_PREFLIGHT=DEPENDENCY_MISSING " + type(exc).__name__ + ": " + str(exc))
        raise SystemExit(22)
    try:
        a = hf_hub_download(repo_id="Lightricks/LTX-2.3",
            filename="ltx-2.3-22b-distilled-1.1.safetensors", local_files_only=True)
        b = hf_hub_download(repo_id="Lightricks/LTX-2.3",
            filename="ltx-2.3-spatial-upscaler-x2-1.1.safetensors", local_files_only=True)
        c = snapshot_download(repo_id="google/gemma-3-12b-it-qat-q4_0-unquantized",
            local_files_only=True)
    except Exception as exc:
        print("LTX_PREFLIGHT=CACHE_MISS " + type(exc).__name__ + ": " + str(exc))
        raise SystemExit(23)
    print("LTX_PREFLIGHT=PASS source=" + str(root))
    print(json.dumps({"distilled": a, "upscaler": b, "gemma": c}))
except SystemExit:
    raise
except Exception as exc:
    print("LTX_PREFLIGHT=BLOCKED " + type(exc).__name__ + ": " + str(exc))
    raise SystemExit(24)
'''
    command = [str(python), "-c", probe]
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True,
                            timeout=240, check=False)
    combined = result.stdout + "\n" + result.stderr
    log.write_text("COMMAND " + json.dumps(command) + "\n\nSTDOUT:\n" + result.stdout
                   + "\nSTDERR:\n" + result.stderr, encoding="utf-8")
    if "LTX_PREFLIGHT=PASS" in combined and result.returncode == 0:
        return {"status": "PASS", "command": command, "log": str(log),
                "reason": "pinned source, xformers and all required model checkpoints are present"}
    if "LTX_PREFLIGHT=CACHE_MISS" in combined:
        return {"status": "SKIPPED", "command": command, "log": str(log),
                "reason": "one or more LTX/Gemma checkpoints are missing; downloads disabled",
                "diagnostic": combined[-1800:]}
    if "LTX_PREFLIGHT=SOURCE_MISSING" in combined or "LTX_PREFLIGHT=DEPENDENCY_MISSING" in combined:
        return {"status": "BLOCKED", "command": command, "log": str(log),
                "reason": combined[-1800:]}
    return {"status": "BLOCKED", "command": command, "log": str(log),
            "returncode": result.returncode, "reason": combined[-2500:] or "no diagnostic output"}


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def _write_test_png(path: Path, width: int = 256, height: int = 256) -> None:
    """Write a deterministic RGB gradient with simple shapes using only stdlib."""
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # PNG filter type 0
        for x in range(width):
            if 32 < x < 224 and 32 < y < 224 and ((x - 128) ** 2 + (y - 128) ** 2) < 58 ** 2:
                raw.extend((225, 158, 70))
            elif 64 < x < 192 and 64 < y < 192:
                raw.extend((55, 115, 155))
            else:
                raw.extend((18 + x // 16, 24 + y // 16, 38))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header) \
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), level=6)) + _png_chunk(b"IEND", b"")
    path.write_bytes(png)


def _wait_for_service(process: subprocess.Popen, url: str, timeout: int) -> tuple[bool, dict[str, Any]]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False, {"process_exit_code": process.returncode, "last_health": last}
        ready, body = _probe_health(url)
        last = body
        if ready:
            return True, body
        time.sleep(3)
    return False, {"timeout_seconds": timeout, "last_health": last}


def _terminate_owned_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=20)
    except Exception:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            process.kill()
        try:
            process.wait(timeout=10)
        except Exception:
            pass


def _run_job(provider: str, url: str, out_dir: Path, timeout_seconds: int) -> dict[str, Any]:
    if provider == "trellis":
        image_path = out_dir / "oec-synthetic-reference.png"
        _write_test_png(image_path)
        payload = {
            "task": "image_to_3d",
            "filename": image_path.name,
            "prompt": "A simple amber sphere on a blue-grey studio background",
            "image_base64": base64.b64encode(image_path.read_bytes()).decode("ascii"),
            "parameters": {"max_image_size": 512, "texture_size": 1024, "decimation_target": 30000},
        }
        expected_extension = "glb"
    else:
        payload = {
            "task": "text_to_video",
            "prompt": "A short macro shot of amber ink swirling through clear water, fixed camera, soft studio lighting",
            "parameters": {
                "duration_seconds": 2.0, "fps": 12, "seed": 42,
                "randomize_seed": False, "enhance_prompt": False,
                "width": 768, "height": 512,
            },
        }
        expected_extension = "mp4"
    code, raw, _ = _request(url + "/v1/jobs", "POST", payload, timeout=30)
    if code not in {200, 201, 202}:
        raise RuntimeError(f"{provider} submit returned HTTP {code}: {raw[:1000].decode('utf-8', errors='replace')}")
    accepted = json.loads(raw.decode("utf-8"))
    job_id = accepted.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise RuntimeError(f"{provider} submit response has no job_id: {accepted}")
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        code, raw, _ = _request(url + "/v1/jobs/" + urllib.parse.quote(job_id, safe=""), timeout=10)
        if code != 200:
            raise RuntimeError(f"{provider} job status returned HTTP {code}: {raw[:500]!r}")
        last = json.loads(raw.decode("utf-8"))
        status = str(last.get("status", "")).lower()
        if status in {"succeeded", "success", "completed", "complete"}:
            break
        if status in {"failed", "error"}:
            raise RuntimeError(f"{provider} job failed: {json.dumps(last, ensure_ascii=False)[:2000]}")
        time.sleep(2)
    else:
        raise TimeoutError(f"{provider} job did not finish within {timeout_seconds}s; last status={last}")
    code, body, headers = _request(url + "/v1/jobs/" + urllib.parse.quote(job_id, safe="") + "/result",
                                    timeout=60)
    if code != 200:
        raise RuntimeError(f"{provider} result returned HTTP {code}: {body[:1000].decode('utf-8', errors='replace')}")
    if not body or len(body) > 1024 * 1024 * 1024:
        raise RuntimeError(f"{provider} returned an empty or over-1-GiB artifact ({len(body)} bytes)")
    result_path = out_dir / f"{provider}-acceptance.{expected_extension}"
    result_path.write_bytes(body)
    content_type = headers.get("Content-type", headers.get("Content-Type", ""))
    if provider == "trellis":
        from common import validate_glb
        validation = validate_glb(result_path)
    else:
        from common import validate_mp4
        validation = validate_mp4(result_path)
    return {
        "status": "PASS", "job_id": job_id, "artifact_path": str(result_path),
        "artifact_bytes": len(body), "artifact_sha256": __import__("hashlib").sha256(body).hexdigest(),
        "content_type": content_type, "job_terminal_record": last, "artifact_validation": validation,
    }


def _run_provider(provider: str, python: Path, preflight: dict[str, Any],
                  report_root: Path) -> dict[str, Any]:
    cfg = PROVIDERS[provider]
    base = {"provider": provider, "environment": cfg["environment"], "python": str(python),
            "cache_preflight": preflight, "port": cfg["port"]}
    if preflight.get("status") != "PASS":
        return {**base, "status": preflight.get("status", "BLOCKED"),
                "reason": preflight.get("reason", "cache/dependency preflight did not pass; no service was started")}
    if not _port_is_free(cfg["port"]):
        return {**base, "status": "BLOCKED",
                "reason": f"loopback port {cfg['port']} is already occupied; no existing process was touched"}
    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["OEC_USE_MANAGER_DIRECTORY_ONLY"] = "0"
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(MEDIA), env.get("PYTHONPATH", "")])
    command = [str(python), str(cfg["script"]), "--host", "127.0.0.1", "--port", str(cfg["port"])]
    service_log = report_root / f"{provider}-service.log"
    started = time.monotonic()
    process = None
    try:
        with service_log.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        ready, health = _wait_for_service(process, f"http://127.0.0.1:{cfg['port']}",
                                          cfg["startup_timeout_seconds"])
        if not ready:
            tail = service_log.read_text(encoding="utf-8", errors="replace").splitlines()[-100:]
            return {**base, "status": "FAIL", "command": command, "health_at_failure": health,
                    "service_log": str(service_log), "log_tail": tail,
                    "reason": "cache was present but the real service failed to become ready"}
        result = _run_job(provider, f"http://127.0.0.1:{cfg['port']}", report_root,
                          cfg["job_timeout_seconds"])
        return {**base, **result, "command": command, "health": health,
                "service_log": str(service_log),
                "startup_plus_job_seconds": round(time.monotonic() - started, 3)}
    except Exception as exc:
        tail = service_log.read_text(encoding="utf-8", errors="replace").splitlines()[-100:] if service_log.exists() else []
        return {**base, "status": "FAIL", "command": command,
                "service_log": str(service_log), "log_tail": tail,
                "reason": f"{type(exc).__name__}: {exc}"}
    finally:
        _terminate_owned_process(process)


def main() -> int:
    report_root = Path(os.environ.get("OEC_VISUAL_SMOKE_DIR",
                                     str(Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "oec-visual-sidecar-smoke"))).resolve()
    report_root.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(MEDIA))
    report: dict[str, Any] = {
        "test": "OEC cache-only live TRELLIS/LTX sidecar acceptance",
        "started_unix": time.time(), "root": str(ROOT),
        "downloads_allowed": False, "package_installs_allowed": False,
        "production_service_urls_changed": False, "status": "IN_PROGRESS",
        "runner": os.environ.get("RUNNER_NAME", "unknown"),
        "hostname": socket.gethostname(),
    }
    try:
        preflight_storage = subprocess.run(
            [sys.executable, str(ROOT / "storage_manager.py"), "--status"],
            cwd=ROOT, text=True, capture_output=True, timeout=45, check=False,
            env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
        )
        (report_root / "storage-status.log").write_text(
            preflight_storage.stdout + "\nSTDERR:\n" + preflight_storage.stderr, encoding="utf-8")
        report["storage_status_returncode"] = preflight_storage.returncode
        report["storage_status_tail"] = preflight_storage.stdout.splitlines()[-24:]
        if preflight_storage.returncode != 0:
            raise RuntimeError("read-only StorageManager status failed; refusing visual model tests")
        try:
            nvidia = subprocess.run(["nvidia-smi"], text=True, capture_output=True, timeout=15, check=False)
            report["nvidia_smi_returncode"] = nvidia.returncode
            report["nvidia_smi"] = (nvidia.stdout + "\n" + nvidia.stderr)[-7000:]
        except Exception as exc:
            report["nvidia_smi_error"] = f"{type(exc).__name__}: {exc}"

        trellis_python = ENV_ROOT / "phase2_3d" / "bin" / "python"
        ltx_python = ENV_ROOT / "phase1_ltx" / "bin" / "python"
        report["environment_paths"] = {"phase2_3d": str(trellis_python), "phase1_ltx": str(ltx_python)}
        if trellis_python.is_file():
            trellis_preflight = _run_preflight_trellis(trellis_python, {
                **os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                "PYTHONPATH": os.pathsep.join([str(ROOT), str(MEDIA), os.environ.get("PYTHONPATH", "")]),
            }, report_root)
        else:
            trellis_preflight = {"status": "BLOCKED", "reason": "phase2_3d Python is not present"}
        if ltx_python.is_file():
            ltx_preflight = _run_preflight_ltx(ltx_python, {
                **os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                "PYTHONPATH": os.pathsep.join([str(ROOT), str(MEDIA), os.environ.get("PYTHONPATH", "")]),
            }, report_root)
        else:
            ltx_preflight = {"status": "BLOCKED", "reason": "phase1_ltx Python is not present"}
        report["providers"] = {
            "trellis": _run_provider("trellis", trellis_python, trellis_preflight, report_root)
                if trellis_python.is_file() else {"provider": "trellis", **trellis_preflight},
            "ltx": _run_provider("ltx", ltx_python, ltx_preflight, report_root)
                if ltx_python.is_file() else {"provider": "ltx", **ltx_preflight},
        }
        provider_statuses = [x.get("status") for x in report["providers"].values()]
        report["passed"] = provider_statuses.count("PASS")
        report["failed"] = provider_statuses.count("FAIL")
        report["blocked"] = provider_statuses.count("BLOCKED")
        report["skipped"] = provider_statuses.count("SKIPPED")
        report["status"] = "PASS" if report["failed"] == 0 and report["passed"] == 2 else \
            "PARTIAL_BLOCKED" if report["failed"] == 0 else "FAIL"
        print("OEC_VISUAL_SIDECAR_ACCEPTANCE " + json.dumps(report, ensure_ascii=False), flush=True)
        return 1 if report["failed"] else 0
    except Exception as exc:
        report["status"] = "FAIL"
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)
        print("OEC_VISUAL_SIDECAR_ACCEPTANCE " + json.dumps(report, ensure_ascii=False), flush=True)
        return 1
    finally:
        report["finished_unix"] = time.time()
        report_path = report_root / "report.json"
        _write_json(report_path, report)
        print(f"OEC_VISUAL_SIDECAR_REPORT={report_path}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
