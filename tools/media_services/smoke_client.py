#!/usr/bin/env python3
"""Submit one bounded live job to an OEC media sidecar and validate its artifact.

Run on the same A100 host as the sidecar (loopback only). The result is retained
under the configured, StorageManager-managed outputs directory for review.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from core_config import SYSTEM_DIRS  # noqa: E402
from storage_manager import managed_storage_operation  # noqa: E402
from common import require_fresh_quota  # noqa: E402

PORTS = {"ace-step": 7870, "kokoro": 7871, "whisper": 7872, "qwen3-asr": 7873}


def _request(url: str, payload: dict | None = None, timeout: float = 30.0):
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("the smoke client only makes HTTP requests to loopback media services")
    # core_config sets cluster proxies globally; never route a loopback API request through them.
    local_http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with local_http.open(request, timeout=timeout) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            detail = json.loads(body.decode("utf-8"))
        except Exception:
            detail = body[:1000].decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from sidecar: {detail}") from exc


def _validate_artifact(provider: str, raw: bytes) -> dict:
    if not raw:
        raise RuntimeError("result artefact is empty")
    if provider == "kokoro":
        with wave.open(io.BytesIO(raw), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            channels = wav.getnchannels()
            if frames <= 0 or rate <= 0 or channels <= 0:
                raise RuntimeError("WAV header has no usable audio frames")
            return {"format": "WAV", "sample_rate": rate, "channels": channels,
                    "frames": frames, "duration_seconds": round(frames / rate, 3)}
    if provider == "ace-step":
        if not raw.startswith(b"fLaC"):
            raise RuntimeError("ACE-Step result does not have the FLAC signature")
        try:
            import soundfile as sf
            info = sf.info(io.BytesIO(raw))
            if info.frames <= 0 or info.samplerate <= 0:
                raise RuntimeError("FLAC decoder reports no usable audio frames")
            return {"format": "FLAC", "sample_rate": info.samplerate,
                    "channels": info.channels, "frames": info.frames,
                    "duration_seconds": round(info.duration, 3)}
        except ImportError:
            return {"format": "FLAC", "signature_valid": True,
                    "decoder_check": "soundfile not present in smoke-client environment"}
    transcript = raw.decode("utf-8", errors="replace").strip()
    if not transcript:
        raise RuntimeError("transcription result is empty")
    return {"format": "UTF-8 text", "characters": len(transcript), "preview": transcript[:500]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=tuple(PORTS), required=True)
    parser.add_argument("--url", help="loopback sidecar base URL; defaults to provider port on localhost")
    parser.add_argument("--prompt", default="Welcome to OEC. This is a model-service acceptance test.")
    parser.add_argument("--audio-file", type=Path, help="required for Whisper and Qwen3-ASR transcription")
    parser.add_argument("--duration-seconds", type=int, default=10, help="ACE-Step only; 10-180 seconds")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()

    base_url = (args.url or f"http://127.0.0.1:{PORTS[args.provider]}").rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("only loopback HTTP is accepted; use an SSH tunnel instead of a public bind")
    if not args.prompt.strip() and args.provider in {"ace-step", "kokoro"}:
        parser.error("--prompt must be non-empty")
    if args.provider == "ace-step" and not 10 <= args.duration_seconds <= 180:
        parser.error("ACE-Step duration must be between 10 and 180 seconds")
    if args.provider in {"whisper", "qwen3-asr"} and not args.audio_file:
        parser.error("--audio-file is required for transcription providers")
    payload = {"prompt": args.prompt.strip()}
    if args.provider == "ace-step":
        payload["parameters"] = {"duration_seconds": args.duration_seconds, "steps": 8, "seed": 42,
                                 "lyrics": "", "instrumental": True}
    elif args.provider == "kokoro":
        payload["parameters"] = {"voice": "af_heart"}
    else:
        supplied_audio_path = args.audio_file.expanduser()
        if supplied_audio_path.is_symlink():
            parser.error("--audio-file must be an existing regular file, not a symlink")
        audio_path = supplied_audio_path.resolve()
        if not audio_path.is_file():
            parser.error("--audio-file must be an existing regular file, not a symlink")
        raw_audio = audio_path.read_bytes()
        if len(raw_audio) > 12 * 1024 * 1024:
            parser.error("audio input exceeds the sidecar's 12 MiB limit")
        payload = {"task": "transcribe", "parameters": {"temperature": 0.0},
                   "audio_base64": base64.b64encode(raw_audio).decode("ascii")}

    status, _, body = _request(base_url + "/health", timeout=10)
    health = json.loads(body.decode("utf-8"))
    print("HEALTH", json.dumps(health, indent=2), flush=True)
    if status != 200 or not health.get("ready") or not health.get("model_loaded"):
        raise RuntimeError("model service is not ready; see its log and StorageManager status")

    status, _, body = _request(base_url + "/v1/jobs", payload=payload, timeout=30)
    job = json.loads(body.decode("utf-8"))
    if status != 202 or not isinstance(job.get("job_id"), str):
        raise RuntimeError(f"job submission rejected: {job}")
    job_id = job["job_id"]
    print(f"SUBMITTED provider={args.provider} job_id={job_id}", flush=True)
    deadline = time.monotonic() + args.timeout_seconds
    last_status = None
    while time.monotonic() < deadline:
        _, _, current_body = _request(base_url + f"/v1/jobs/{job_id}", timeout=20)
        current = json.loads(current_body.decode("utf-8"))
        state = current.get("status")
        if state != last_status:
            print("JOB", json.dumps(current, ensure_ascii=False), flush=True)
            last_status = state
        if state == "succeeded":
            break
        if state == "failed":
            raise RuntimeError(f"model job failed: {current}")
        time.sleep(max(0.25, args.poll_seconds))
    else:
        raise TimeoutError(f"job {job_id} did not finish within {args.timeout_seconds}s")

    _, headers, raw_result = _request(base_url + f"/v1/jobs/{job_id}/result", timeout=120)
    artifact_check = _validate_artifact(args.provider, raw_result)
    extension = {"ace-step": ".flac", "kokoro": ".wav", "whisper": ".txt", "qwen3-asr": ".txt"}[args.provider]
    outputs = Path(SYSTEM_DIRS["outputs"]).expanduser().resolve() / "media_services" / "smoke"
    filename = f"{args.provider}-{time.strftime('%Y%m%d-%H%M%S')}-{job_id}{extension}"
    target = outputs / filename
    with managed_storage_operation("outputs", required_gb=0.02, require_fresh_quota=require_fresh_quota(), minimum_free_gb=0.05):
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            raise RuntimeError("refusing to overwrite a symbolic-link artifact path")
        target.write_bytes(raw_result)
    report = {"provider": args.provider, "job_id": job_id, "status": "PASS",
              "artifact_path": str(target), "artifact_bytes": len(raw_result),
              "content_type": headers.get("Content-Type"), "artifact_validation": artifact_check}
    print("ACCEPTANCE_REPORT", json.dumps(report, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
