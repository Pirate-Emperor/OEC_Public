#!/usr/bin/env python3
"""Launch one model's real Gradio notebook and invoke its callback against a live worker."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path

from IPython.core.interactiveshell import InteractiveShell

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NOTEBOOKS = {
    "audiogen": ("pipeline_audiogen_gradio.ipynb", "phase1", "generate_sound_effect"),
    "flux": ("pipeline_flux_only.ipynb", "phase2_3d", "generate_flux"),
    "flux-combined": ("pipeline_trellis_3d.ipynb", "phase2_3d", "generate_concept"),
    "trellis-only": ("pipeline_trellis_3d_only.ipynb", "phase2_3d", "generate_3d"),
    "trellis-combined": ("pipeline_trellis_3d.ipynb", "phase2_3d", "generate_3d"),
    "musicgen": ("pipeline_musicgen_gradio.ipynb", "phase1", "generate_music"),
    "ace-step": ("pipeline_acestep_gradio.ipynb", "phase2_3d", "generate_music"),
    "kokoro": ("pipeline_kokoro_gradio.ipynb", "phase2_3d", "synthesize_speech"),
    "whisper": ("pipeline_whisper_gradio.ipynb", "phase2_3d", "transcribe_audio"),
    "qwen3-asr": ("pipeline_qwen3_asr_gradio.ipynb", "phase2_3d", "transcribe_audio"),
    "ltx-text-video": ("pipeline_ltx_video.ipynb", "phase1_ltx", "generate_video"),
    "ltx-image-video": ("pipeline_ltx_video.ipynb", "phase1_ltx", "generate_video"),
}
AUDIO_PROVIDERS = {"audiogen", "musicgen", "ace-step", "kokoro"}
IMAGE_PROVIDERS = {"flux", "flux-combined"}
MODEL3D_PROVIDERS = {"trellis-only", "trellis-combined"}
NOTEBOOK_CELL_SELECTION = {
    # Run combined notebook read-only setup/diagnostics plus the chosen model
    # client's dependencies and UI cells. No in-kernel model is loaded.
    "flux-combined": {1, 2, 3, 4, 8, 12},
    "trellis-only": {1, 2},
    "trellis-combined": {1, 2, 3, 4, 6, 10},
    # Execute every non-empty code cell in pipeline_ltx_video.ipynb, including
    # core_config checks and read-only nvidia-smi/ps cells, before the live callback.
    "ltx-text-video": {1, 2, 3, 4, 5, 6, 7},
    "ltx-image-video": {1, 2, 3, 4, 5, 6, 7},
}
DEMO_VARIABLES = {
    "flux-combined": "demo_flux",
    "trellis-only": "demo_trellis",
    "trellis-combined": "demo_trellis",
    "ltx-text-video": "demo_ltx",
    "ltx-image-video": "demo_ltx",
}
ASR_PROVIDERS = {"whisper", "qwen3-asr"}
VIDEO_PROVIDERS = {"ltx-text-video", "ltx-image-video"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def patch_gradio_client_boolean_schema() -> bool:
    """Work around gradio_client 1.3.0 crashing on legal boolean JSON-schema nodes.

    Gradio 4.44.x calls get_type(False) for schemas such as
    additionalProperties=false while rendering /; older gradio_client versions
    test string membership on a bool and raise TypeError. This process-local
    compatibility shim leaves all Conda packages untouched.
    """
    try:
        from gradio_client import utils as client_utils
    except Exception:
        return False
    original = client_utils.get_type

    def safe_get_type(schema):
        if isinstance(schema, bool):
            return "boolean"
        return original(schema)

    client_utils.get_type = safe_get_type
    return True


def wait_for_ui(url: str, timeout: float = 20.0) -> tuple[int, str]:
    deadline = time.monotonic() + timeout
    last_error = "not attempted"
    while time.monotonic() < deadline:
        try:
            # Do not route loopback health checks through the runner's outbound proxy.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(url, timeout=2) as response:
                body = response.read(2048).decode("utf-8", errors="replace")
                if response.status != 200 or "<html" not in body.lower():
                    raise RuntimeError(f"Gradio root returned HTTP {response.status} without HTML")
                return response.status, body[:256]
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.25)
    raise TimeoutError(f"Gradio UI did not return HTTP 200 HTML: {last_error}")


def execute_notebook(path: Path, *, code_cell_indexes: set[int] | None = None, demo_name: str = "demo") -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("nbformat") != 4 or not isinstance(document.get("cells"), list):
        raise ValueError(f"invalid notebook structure: {path}")
    shell = InteractiveShell()
    scope = {
        "__name__": "__main__",
        "__file__": str(path),
        "get_ipython": lambda: shell,
    }
    code_cells = 0
    for index, cell in enumerate(document["cells"]):
        if cell.get("cell_type") != "code":
            continue
        if code_cell_indexes is not None and index not in code_cell_indexes:
            continue
        source = "".join(cell.get("source", []))
        if not source.strip():
            continue
        transformed = shell.transform_cell(source)
        compiled = compile(transformed, f"{path.name}:cell-{index}", "exec")
        exec(compiled, scope, scope)
        code_cells += 1
    if demo_name not in scope:
        raise RuntimeError(f"{path.name} did not construct the expected Gradio app {demo_name!r}")
    return {"scope": scope, "code_cells": code_cells}


def invoke_via_gradio_client(provider: str, ui_url: str, audio_file: Path | None, reference_file: Path | None = None):
    """Submit a real prediction request through Gradio's HTTP/event API."""
    from gradio_client import Client, handle_file

    client = Client(ui_url, verbose=True)
    if provider in MODEL3D_PROVIDERS:
        if reference_file is None or not reference_file.is_file():
            raise ValueError(f"{provider} requires the synthetic reference image created by the smoke harness")
        return client.predict(
            handle_file(str(reference_file)),
            "OEC synthetic reference image: generate a clean, watertight 3D asset",
            512, 512, 100000, False,
            fn_index=0
        )
    if provider == "ltx-text-video":
        return client.predict(
            "text_to_video",
            "A miniature brass robot walks across a studio table; smooth camera movement",
            None, 1, 12, 42, False, False, "768x512",
            fn_index=0
        )
    if provider == "ltx-image-video":
        if reference_file is None or not reference_file.is_file():
            raise ValueError("ltx-image-video requires a synthetic reference image")
        return client.predict(
            "image_to_video",
            "A small brass robot slowly turns toward the camera; preserve the reference subject",
            handle_file(str(reference_file)), 1, 12, 42, False, False, "768x512",
            fn_index=0
        )
    if provider == "flux":
        return client.predict(
            "A photorealistic amber glass sphere on a clean studio background", 42, 512, 512, 4, 1.0,
            fn_index=0
        )
    if provider == "flux-combined":
        return client.predict(
            "A photorealistic amber glass sphere on a clean studio background", 42, False,
            fn_index=0
        )
    if provider == "audiogen":
        return client.predict(
            "Short OEC acceptance sound: soft rain with distant thunder", 3, 42,
            fn_index=0
        )
    if provider == "musicgen":
        return client.predict(
            "Short calm instrumental acceptance cue, warm piano and soft strings", 3, 42,
            fn_index=0
        )
    if provider == "ace-step":
        return client.predict(
            "A ten-second warm ambient game soundtrack with soft strings and flute",
            "", True, 10, 42, 8, None, "unknown", fn_index=0
        )
    if provider == "kokoro":
        return client.predict(
            "OEC notebook callback acceptance test. The worker should return a valid speech WAV.",
            "af_heart", fn_index=0
        )
    if provider in ASR_PROVIDERS:
        if audio_file is None or not audio_file.is_file() or audio_file.stat().st_size == 0:
            raise ValueError(f"{provider} needs a non-empty WAV generated by the Kokoro smoke")
        return client.predict(
            handle_file(str(audio_file)), "en", "OEC notebook callback acceptance test", fn_index=0
        )
    raise ValueError(f"unsupported provider: {provider}")


def _output_path(value: object) -> Path:
    """Normalize Gradio Client's filepath result to a local path."""
    if isinstance(value, dict):
        for key in ("path", "name"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return Path(candidate).expanduser().resolve()
        raise ValueError(f"Gradio output dictionary has no local path: {value}")
    if hasattr(value, "path") and isinstance(getattr(value, "path"), str):
        return Path(getattr(value, "path")).expanduser().resolve()
    if not isinstance(value, (str, Path)):
        raise ValueError(f"Gradio output is not a file path: {type(value).__name__}")
    return Path(value).expanduser().resolve()

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=tuple(NOTEBOOKS), required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--audio-file", type=Path, help="Required for Whisper/Qwen3-ASR callbacks.")
    args = parser.parse_args()
    provider = args.provider
    report_dir = args.report_dir.expanduser().resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    notebook_name, expected_env, callback_name = NOTEBOOKS[provider]
    notebook_path = ROOT / notebook_name
    report_path = report_dir / f"{provider}-gradio-notebook-smoke.json"
    result = {
        "provider": provider,
        "notebook": notebook_name,
        "expected_ui_environment": expected_env,
        "python_executable": sys.executable,
        "python_prefix": sys.prefix,
        "media_api_url": (
            os.environ.get("OEC_TRELLIS_API_URL") if provider in MODEL3D_PROVIDERS
            else os.environ.get("OEC_FLUX_API_URL") if provider == "flux-combined"
            else os.environ.get("OEC_LTX_SERVICE_URL", os.environ.get("OEC_MEDIA_API_URL")) if provider in VIDEO_PROVIDERS
            else os.environ.get("OEC_MEDIA_API_URL")
        ),
        "started_unix": time.time(),
        "status": "FAIL",
    }
    os.environ["OEC_GRADIO_HEADLESS_SMOKE"] = "1"
    # Hosted A100 runners inherit an outbound HTTP proxy. Explicitly bypass it for
    # loopback so Gradio's internal localhost-health check and local API clients
    # never try to reach 127.0.0.1 through that proxy.
    loopback_hosts = ("localhost", "127.0.0.1", "::1")
    for key in ("NO_PROXY", "no_proxy"):
        existing = [value.strip() for value in os.environ.get(key, "").split(",") if value.strip()]
        os.environ[key] = ",".join(dict.fromkeys([*existing, *loopback_hosts]))
    os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
    demo = None
    try:
        if not notebook_path.is_file():
            raise FileNotFoundError(f"notebook missing: {notebook_path}")
        if provider == "flux-combined" and not os.environ.get("OEC_FLUX_API_URL"):
            os.environ["OEC_FLUX_API_URL"] = os.environ.get("OEC_MEDIA_API_URL", "http://127.0.0.1:7867")
        if provider in VIDEO_PROVIDERS and not os.environ.get("OEC_LTX_SERVICE_URL"):
            os.environ["OEC_LTX_SERVICE_URL"] = os.environ.get("OEC_MEDIA_API_URL", "http://127.0.0.1:7869")
        if provider in MODEL3D_PROVIDERS and not os.environ.get("OEC_TRELLIS_API_URL"):
            os.environ["OEC_TRELLIS_API_URL"] = os.environ.get("OEC_MEDIA_API_URL", "http://127.0.0.1:7868")
        executed = execute_notebook(
            notebook_path,
            code_cell_indexes=NOTEBOOK_CELL_SELECTION.get(provider),
            demo_name=DEMO_VARIABLES.get(provider, "demo"),
        )
        scope = executed["scope"]
        demo = scope[DEMO_VARIABLES.get(provider, "demo")]
        result["code_cells_executed"] = executed["code_cells"]
        result["gradio_version"] = importlib.metadata.version("gradio")
        result["callback_name"] = callback_name

        # Patch this known Gradio/gradio_client JSON-schema compatibility issue in
        # the smoke process only; do not install/upgrade packages in model envs.
        result["gradio_client_boolean_schema_shim"] = patch_gradio_client_boolean_schema()
        # The real notebook Interface must bind locally and serve HTML. No share URL is allowed.
        port = free_port()
        ui_url = f"http://127.0.0.1:{port}/"
        allowed_paths = sorted({
            str(Path("/tmp/oec-notebook-results").resolve()),
            str((Path(tempfile.gettempdir()) / "oec-notebook-results").resolve()),
            str(report_dir.resolve()),
        })
        demo.queue(max_size=1).launch(
            server_name="127.0.0.1", server_port=port, share=False, inline=False,
            prevent_thread_lock=True, show_error=True, allowed_paths=allowed_paths,
        )
        result["ui_http_status"], result["ui_html_prefix"] = wait_for_ui(ui_url)
        result["ui_launch"] = "PASS"

        # Generate a small local input only for image-conditioned model callbacks.
        callback_input = args.audio_file.expanduser().resolve() if args.audio_file else None
        if provider in MODEL3D_PROVIDERS or provider == "ltx-image-video":
            from PIL import Image, ImageDraw
            callback_input = report_dir / f"{provider}-reference.png"
            image = Image.new("RGB", (256, 256), (245, 241, 232))
            draw = ImageDraw.Draw(image)
            draw.ellipse((64, 54, 192, 182), fill=(70, 125, 180), outline=(25, 55, 85), width=5)
            draw.rectangle((98, 170, 158, 210), fill=(90, 95, 105))
            image.save(callback_input, format="PNG")
            result["input_image_path"] = str(callback_input)
        # Exercise the actual Gradio HTTP/event API, not a direct Python callback call.
        raw_output = invoke_via_gradio_client(
            provider, ui_url,
            callback_input if provider in ASR_PROVIDERS else args.audio_file,
            reference_file=callback_input if provider in MODEL3D_PROVIDERS or provider == "ltx-image-video" else None,
        )
        expected_outputs = 3 if provider == "flux-combined" else 2
        if not isinstance(raw_output, (tuple, list)) or len(raw_output) != expected_outputs:
            actual_shape = len(raw_output) if isinstance(raw_output, (tuple, list)) else type(raw_output).__name__
            raise RuntimeError(
                f"Gradio /predict returned an unexpected result shape: expected {expected_outputs}, got {actual_shape}"
            )
        output, details = raw_output[0], raw_output[-1]
        result["callback"] = "PASS"
        result["callback_transport"] = "gradio_client HTTP/event API /predict"
        result["details"] = str(details)[:10000]
        if provider in AUDIO_PROVIDERS:
            source = _output_path(output)
            if not source.is_file() or source.stat().st_size < 64:
                raise RuntimeError(f"callback did not generate a non-empty audio artifact: {source}")
            header = source.read_bytes()[:16]
            if source.suffix.lower() == ".wav" and not (header[:4] == b"RIFF" and header[8:12] == b"WAVE"):
                raise RuntimeError("WAV header validation failed")
            if source.suffix.lower() in {".flac", ".fla"} and header[:4] != b"fLaC":
                raise RuntimeError("FLAC signature validation failed")
            import soundfile as sf
            import numpy as np
            audio_info = sf.info(str(source))
            samples, sample_rate = sf.read(str(source), dtype="float32", always_2d=True)
            peak = float(np.max(np.abs(samples))) if samples.size else 0.0
            rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
            if audio_info.frames <= 0 or sample_rate <= 0 or audio_info.channels <= 0:
                raise RuntimeError("audio decoder reported invalid stream metadata")
            if not np.isfinite(samples).all() or peak < 1e-6 or rms < 1e-7:
                raise RuntimeError(f"generated audio is silent/invalid: peak={peak:.8g}, rms={rms:.8g}")
            result["audio_validation"] = {
                "format": audio_info.format, "subtype": audio_info.subtype,
                "sample_rate_hz": int(sample_rate), "channels": int(audio_info.channels),
                "duration_seconds": round(float(audio_info.duration), 4),
                "peak_amplitude": peak, "rms_amplitude": rms,
            }
            destination = report_dir / f"{provider}-gradio-callback-artifact{source.suffix.lower()}"
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)
            result["artifact_path"] = str(destination)
            result["artifact_bytes"] = destination.stat().st_size
            result["artifact_sha256"] = sha256_file(destination)
            # Remove the exact run-scoped API result returned by this callback after preserving it.
            try:
                detail_data = json.loads(str(details))
            except (TypeError, ValueError):
                detail_data = {}
            job_id = detail_data.get("job_id")
            if isinstance(job_id, str) and job_id.startswith("job_"):
                result_root = Path(tempfile.gettempdir()) / "oec-notebook-results"
                for suffix in (".wav", ".flac"):
                    owned = result_root / f"{job_id}{suffix}"
                    try:
                        if owned.is_file() and not owned.is_symlink():
                            owned.unlink()
                    except OSError:
                        pass
            temp_root = Path("/tmp").resolve()
            if temp_root in source.parents and source.name.startswith(("oec-audiogen-", "oec-musicgen-")):
                try:
                    source.unlink()
                    source.with_suffix(".info.json").unlink(missing_ok=True)
                except OSError:
                    pass
        elif provider in MODEL3D_PROVIDERS:
            source = _output_path(output)
            if not source.is_file() or source.is_symlink() or source.stat().st_size < 1024:
                raise RuntimeError(f"TRELLIS callback did not return a non-empty GLB: {source}")
            data = source.read_bytes()
            if data[:4] != b"glTF" or len(data) < 20:
                raise RuntimeError("TRELLIS callback asset does not have a GLB binary header")
            import struct
            version, declared_length = struct.unpack_from("<II", data, 4)
            json_length, chunk_type = struct.unpack_from("<II", data, 12)
            if version != 2 or declared_length != len(data):
                raise RuntimeError(f"invalid GLB header: version={version}, declared={declared_length}, actual={len(data)}")
            if chunk_type != 0x4E4F534A or json_length <= 0 or 20 + json_length > len(data):
                raise RuntimeError("invalid GLB JSON chunk header")
            document = json.loads(data[20:20 + json_length].rstrip(b" \t\r\n\0").decode("utf-8"))
            if not isinstance(document, dict) or "asset" not in document:
                raise RuntimeError("GLB JSON chunk lacks the glTF asset object")
            destination = report_dir / f"{provider}-gradio-callback-artifact.glb"
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)
            result["artifact_path"] = str(destination)
            result["artifact_bytes"] = destination.stat().st_size
            result["artifact_sha256"] = sha256_file(destination)
            result["model3d_validation"] = {
                "format": "GLB", "version": version, "declared_length": declared_length,
                "json_chunk_bytes": json_length, "mesh_count": len(document.get("meshes", [])),
                "node_count": len(document.get("nodes", [])),
            }
            result_root = Path("/tmp/oec-notebook-results").resolve()
            if result_root in source.parents and source.name.startswith("job_"):
                source.unlink(missing_ok=True)
        elif provider in IMAGE_PROVIDERS:
            source = _output_path(output)
            if not source.is_file() or source.stat().st_size <= 64:
                raise RuntimeError(f"callback did not generate a non-empty image artifact: {source}")
            if source.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
                raise RuntimeError("FLUX result does not have a valid PNG signature")
            from PIL import Image
            with Image.open(source) as check:
                check.verify()
            with Image.open(source) as check:
                width, height = check.size
            if width <= 0 or height <= 0:
                raise RuntimeError(f"invalid PNG dimensions: {width}x{height}")
            destination = report_dir / f"{provider}-gradio-callback-artifact.png"
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)
            result["artifact_path"] = str(destination)
            result["artifact_bytes"] = destination.stat().st_size
            result["artifact_sha256"] = sha256_file(destination)
            result["image_validation"] = {"format": "PNG", "width": width, "height": height}
            result_root = Path("/tmp/oec-notebook-results").resolve()
            if result_root in source.parents and source.name.startswith("job_"):
                source.unlink(missing_ok=True)
        elif provider in VIDEO_PROVIDERS:
            source = _output_path(output)
            if not source.is_file() or source.is_symlink() or source.stat().st_size <= 1024:
                raise RuntimeError(f"LTX callback did not return a non-empty MP4: {source}")
            header = source.read_bytes()[:16]
            if len(header) < 12 or header[4:8] != b"ftyp":
                raise RuntimeError("LTX callback result does not have an MP4 ftyp header")
            probe = shutil.which("ffprobe")
            if not probe:
                raise RuntimeError("ffprobe is required to validate LTX-generated MP4 output")
            completed = subprocess.run(
                [probe, "-v", "error", "-count_frames", "-select_streams", "v:0",
                 "-show_entries", "stream=codec_name,width,height,nb_read_frames,r_frame_rate,duration",
                 "-show_entries", "format=duration,format_name", "-of", "json", str(source)],
                text=True, capture_output=True, timeout=60, check=False,
            )
            if completed.returncode:
                raise RuntimeError(f"ffprobe rejected LTX MP4: {completed.stderr[-1200:]}")
            mp4_report = json.loads(completed.stdout)
            streams = mp4_report.get("streams") or []
            if not streams:
                raise RuntimeError("LTX MP4 has no video stream")
            stream = streams[0]
            width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
            frames = int(stream.get("nb_read_frames") or 0)
            duration = float((mp4_report.get("format") or {}).get("duration") or stream.get("duration") or 0.0)
            if width <= 0 or height <= 0 or frames < 5 or duration <= 0:
                raise RuntimeError(f"LTX MP4 metadata is invalid: {stream}")
            destination = report_dir / f"{provider}-gradio-callback-artifact.mp4"
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)
            result["artifact_path"] = str(destination)
            result["artifact_bytes"] = destination.stat().st_size
            result["artifact_sha256"] = sha256_file(destination)
            result["video_validation"] = {
                "format": (mp4_report.get("format") or {}).get("format_name"),
                "codec": stream.get("codec_name"), "width": width, "height": height,
                "frames": frames, "fps": stream.get("r_frame_rate"), "duration_seconds": duration,
            }
            result_root = Path("/tmp/oec-notebook-results").resolve()
            if result_root in source.parents and source.name.startswith("job_"):
                source.unlink(missing_ok=True)
        else:
            transcript = str(output).strip()
            if len(transcript) < 5:
                raise RuntimeError("ASR notebook callback returned an empty/too-short transcript")
            result["transcript_chars"] = len(transcript)
            result["transcript_preview"] = transcript[:300]
            result["artifact_path"] = None
        result["status"] = "PASS"
        result["finished_unix"] = time.time()
        report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("GRADIO_NOTEBOOK_ACCEPTANCE " + json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()[-12000:]
        result["finished_unix"] = time.time()
        report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("GRADIO_NOTEBOOK_ACCEPTANCE " + json.dumps(result, ensure_ascii=False), flush=True)
        return 1
    finally:
        try:
            if demo is not None and hasattr(demo, "close"):
                demo.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
