#!/usr/bin/env python3
"""Execute AudioGen notebook top-to-bottom, then test its actual Gradio HTTP callback."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import shutil
import socket
import sys
import time
import traceback
import urllib.request
from pathlib import Path
from typing import Any

from IPython.core.interactiveshell import InteractiveShell

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
NOTEBOOK = ROOT / "pipeline_audiocraft.ipynb"


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_gradio(url: str, timeout_seconds: float = 30.0) -> int:
    deadline = time.monotonic() + timeout_seconds
    last_error = "not attempted"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        try:
            with opener.open(url, timeout=3) as response:
                body = response.read(4096).decode("utf-8", errors="replace")
                if response.status != 200 or "<html" not in body.lower():
                    raise RuntimeError(f"Gradio root returned HTTP {response.status} without HTML")
                return int(response.status)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.25)
    raise TimeoutError(f"Gradio UI did not return HTTP 200 HTML: {last_error}")


def normalize_gradio_file(value: object) -> Path:
    if isinstance(value, dict):
        for key in ("path", "name"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return Path(candidate).expanduser().resolve()
        raise ValueError(f"Gradio returned a file object without a path: {value}")
    if hasattr(value, "path") and isinstance(getattr(value, "path"), str):
        return Path(getattr(value, "path")).expanduser().resolve()
    if not isinstance(value, (str, Path)):
        raise ValueError(f"Gradio audio output is not a path: {type(value).__name__}")
    return Path(value).expanduser().resolve()


def validate_audio(path: Path, *, label: str) -> dict[str, Any]:
    import numpy as np
    import soundfile as sf

    if not path.is_file() or path.stat().st_size <= 64:
        raise RuntimeError(f"{label} artifact is missing or too small: {path}")
    info = sf.info(str(path))
    samples, rate = sf.read(str(path), dtype="float32", always_2d=True)
    duration = float(samples.shape[0] / rate) if rate else 0.0
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
    if not np.isfinite(samples).all():
        raise RuntimeError(f"{label} WAV contains NaN or infinite samples")
    if info.frames <= 0 or rate <= 0 or info.channels <= 0 or not (0.5 <= duration <= 6.0):
        raise RuntimeError(
            f"{label} WAV has invalid stream metadata: frames={info.frames}, rate={rate}, "
            f"channels={info.channels}, duration={duration:.3f}s"
        )
    if peak < 1e-5 or rms < 1e-7:
        raise RuntimeError(f"{label} WAV is silent or near-silent: peak={peak:.8g}, rms={rms:.8g}")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "sample_rate_hz": int(rate),
        "channels": int(samples.shape[1]),
        "duration_seconds": round(duration, 4),
        "peak_amplitude": peak,
        "rms_amplitude": rms,
        "format": info.format,
        "subtype": info.subtype,
    }


def patch_gradio_client_boolean_schema() -> bool:
    """Process-local compatibility fix for old gradio_client's boolean-schema crash."""
    try:
        from gradio_client import utils
    except Exception:
        return False
    original = utils.get_type

    def safe_get_type(schema):
        if isinstance(schema, bool):
            return "boolean"
        return original(schema)

    utils.get_type = safe_get_type
    return True


def main() -> int:
    run_temp = Path(os.environ.get("RUNNER_TEMP", "/tmp")).resolve()
    report_root = Path(
        os.environ.get("OEC_AUDIOGEN_SMOKE_DIR", str(run_temp / "oec-audiogen-smoke"))
    ).expanduser().resolve()
    report_root.mkdir(parents=True, exist_ok=True)
    output_root = report_root / "output"
    output_root.mkdir(parents=True, exist_ok=True)

    # The notebook's normal, production-mode output still uses StorageManager.
    # For acceptance only, direct inference writes beneath this run-scoped temp root.
    os.environ["OEC_AUDIOGEN_HEADLESS_SMOKE"] = "1"
    os.environ["OEC_AUDIOGEN_OUTPUT_DIR"] = str(output_root)
    os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
    os.environ.setdefault(
        "OEC_AUDIOGEN_SMOKE_PROMPT",
        "A short cinematic metallic sci-fi impact with a low bass resonance",
    )

    report: dict[str, Any] = {
        "test": "OEC AudioGen full notebook + Gradio HTTP acceptance",
        "notebook": str(NOTEBOOK),
        "started_unix": time.time(),
        "started_monotonic": time.monotonic(),
        "runner_name": os.environ.get("RUNNER_NAME"),
        "hostname": __import__("socket").gethostname(),
        "output_root": str(output_root),
        "mode": "all notebook cells + local Gradio HTTP callback; outputs stay in run temp",
        "status": "FAIL",
        "model_download_path": "notebook-managed StorageManager admission; no bypass in this harness",
        "gradio_ui_launch": "NOT_RUN",
        "gradio_callback": "NOT_RUN",
    }
    demo = None
    try:
        # Select an idle physical A100 before importing torch into this process.
        from pipeline_flux_image import select_idle_a100_gpu
        selected_gpu = select_idle_a100_gpu()
        os.environ["CUDA_VISIBLE_DEVICES"] = selected_gpu["index"]
        report["physical_gpu_selection"] = selected_gpu
        report["physical_gpu_index"] = selected_gpu["index"]

        import torch

        report["torch"] = torch.__version__
        report["torch_cuda"] = torch.version.cuda
        report["cuda_available"] = bool(torch.cuda.is_available())
        report["cuda_device_count_visible"] = torch.cuda.device_count()
        if not torch.cuda.is_available():
            raise RuntimeError("phase1 has no usable CUDA device; refusing to call this a live AudioGen test")
        report["cuda_device_zero"] = torch.cuda.get_device_name(0)

        nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        if nb.get("nbformat") != 4 or not isinstance(nb.get("cells"), list):
            raise ValueError("AudioGen notebook is not a valid nbformat v4 notebook")
        shell = InteractiveShell()
        namespace: dict[str, Any] = {"__name__": "__main__", "__file__": str(NOTEBOOK)}
        executed_cells: list[int] = []
        started = time.monotonic()
        for index, cell in enumerate(nb["cells"]):
            if cell.get("cell_type") != "code":
                continue
            source = cell.get("source", [])
            source_text = "".join(source) if isinstance(source, list) else str(source)
            if not source_text.strip():
                continue
            print(f"AUDIOGEN_NOTEBOOK_CELL_START={index}", flush=True)
            transformed = shell.transform_cell(source_text)
            exec(compile(transformed, f"{NOTEBOOK.name}:cell-{index}", "exec"), namespace, namespace)
            executed_cells.append(index)
            print(f"AUDIOGEN_NOTEBOOK_CELL_PASS={index}", flush=True)

        # First validate the notebook's direct inference step.
        outputs = sorted(output_root.glob("*.wav")) if output_root.is_dir() else []
        if len(outputs) != 1:
            raise RuntimeError(f"expected exactly one direct notebook smoke WAV before Gradio test, found {len(outputs)}")
        direct_audio = validate_audio(outputs[0], label="direct notebook")
        report["direct_notebook_audio"] = direct_audio
        report["direct_notebook_inference"] = "PASS"

        # Then launch the *same notebook's* Blocks UI and call its real HTTP event API.
        # This catches failures that a Python-only callback or syntax check cannot detect.
        if "demo" not in namespace or not hasattr(namespace["demo"], "launch"):
            raise RuntimeError("AudioCraft notebook did not construct its Gradio demo")
        demo = namespace["demo"]
        report["gradio_client_boolean_schema_shim"] = patch_gradio_client_boolean_schema()
        port = free_loopback_port()
        ui_url = f"http://127.0.0.1:{port}/"
        demo.queue(max_size=1).launch(
            server_name="127.0.0.1",
            server_port=port,
            share=False,
            inline=False,
            prevent_thread_lock=True,
            show_error=True,
        )
        report["gradio_ui_http_status"] = wait_for_gradio(ui_url)
        report["gradio_ui_url"] = ui_url
        report["gradio_ui_launch"] = "PASS"

        from gradio_client import Client
        client = Client(ui_url, verbose=True)
        callback_output = client.predict(
            "Short OEC acceptance sound: soft rain with distant thunder",
            3,
            fn_index=0,
        )
        if not isinstance(callback_output, (tuple, list)) or len(callback_output) != 2:
            raise RuntimeError(
                f"AudioGen Gradio /predict returned the wrong shape: {type(callback_output).__name__}"
            )
        callback_path = normalize_gradio_file(callback_output[0])
        callback_validation = validate_audio(callback_path, label="Gradio callback")
        # Preserve a run-scoped copy even if Gradio itself uses a transient cache path.
        callback_artifact = report_root / "audiogen-notebook-gradio-callback.wav"
        if callback_path.resolve() != callback_artifact.resolve():
            shutil.copy2(callback_path, callback_artifact)
        callback_validation.update({
            "path": str(callback_artifact),
            "sha256": hashlib.sha256(callback_artifact.read_bytes()).hexdigest(),
            "bytes": callback_artifact.stat().st_size,
        })
        report["gradio_callback"] = "PASS"
        report["gradio_callback_transport"] = "gradio_client HTTP/event API /predict"
        report["gradio_callback_audio"] = callback_validation
        print("AUDIOGEN_GRADIO_CALLBACK_ACCEPTANCE " + json.dumps(callback_validation, ensure_ascii=False), flush=True)

        report.update({
            "status": "PASS",
            "executed_code_cells": executed_cells,
            "notebook_execution_seconds": round(time.monotonic() - started, 3),
            "model_id": "facebook/audiogen-medium",
            "snapshot_path": str(namespace.get("AUDIOGEN_SNAPSHOT", "")),
            "audiocraft_version": package_version("audiocraft"),
            "torch_version": package_version("torch"),
            "gradio_version": package_version("gradio"),
            "numpy_version": package_version("numpy"),
            "transformers_version": package_version("transformers"),
            "gpu_peak_allocated_gib": round(torch.cuda.max_memory_allocated() / (1024 ** 3), 3),
            "gpu_peak_reserved_gib": round(torch.cuda.max_memory_reserved() / (1024 ** 3), 3),
            "shared_outputs_written": False,
        })
        print("AUDIOGEN_LIVE_ACCEPTANCE " + json.dumps(report, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        report["elapsed_seconds"] = round(time.monotonic() - report["started_monotonic"], 3)
        print("AUDIOGEN_LIVE_ACCEPTANCE " + json.dumps(report, ensure_ascii=False), flush=True)
        traceback.print_exc()
        return 1
    finally:
        if demo is not None and hasattr(demo, "close"):
            try:
                demo.close()
            except Exception:
                pass
        report["finished_unix"] = time.time()
        report_path = report_root / "report.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"AUDIOGEN_REPORT={report_path}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
