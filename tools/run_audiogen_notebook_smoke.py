#!/usr/bin/env python3
"""Execute the AudioGen notebook top-to-bottom in phase1 and validate one WAV in runner temp."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import sys
import time
import traceback
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


def main() -> int:
    run_temp = Path(os.environ.get("RUNNER_TEMP", "/tmp")).resolve()
    report_root = Path(os.environ.get("OEC_AUDIOGEN_SMOKE_DIR", str(run_temp / "oec-audiogen-smoke"))).resolve()
    report_root.mkdir(parents=True, exist_ok=True)
    output_root = report_root / "output"
    os.environ["OEC_AUDIOGEN_HEADLESS_SMOKE"] = "1"
    os.environ["OEC_AUDIOGEN_OUTPUT_DIR"] = str(output_root)
    os.environ.setdefault(
        "OEC_AUDIOGEN_SMOKE_PROMPT",
        "A short cinematic metallic sci-fi impact with a low bass resonance",
    )

    report: dict[str, Any] = {
        "test": "OEC AudioGen notebook live smoke",
        "notebook": str(NOTEBOOK),
        "started_unix": time.time(),
        "started_monotonic": time.monotonic(),
        "runner_name": os.environ.get("RUNNER_NAME"),
        "hostname": __import__("socket").gethostname(),
        "output_root": str(output_root),
        "mode": "headless; output is run-scoped runner temp",
        "status": "FAIL",
        "model_download_path": "notebook-managed StorageManager admission; no bypass in this harness",
    }
    try:
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

        outputs = sorted(output_root.glob("*.wav")) if output_root.is_dir() else []
        if len(outputs) != 1:
            raise RuntimeError(f"expected exactly one smoke WAV under runner temp, found {len(outputs)}")
        wav_path = outputs[0]
        import numpy as np
        import soundfile as sf

        samples, rate = sf.read(str(wav_path), dtype="float32", always_2d=True)
        duration = float(samples.shape[0] / rate) if rate else 0.0
        peak = float(np.max(np.abs(samples))) if samples.size else 0.0
        rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
        if wav_path.stat().st_size <= 64:
            raise RuntimeError(f"generated WAV is too small: {wav_path.stat().st_size} bytes")
        if not np.isfinite(samples).all():
            raise RuntimeError("generated WAV contains NaN or infinite samples")
        if not (0.5 <= duration <= 6.0):
            raise RuntimeError(f"generated WAV duration outside smoke acceptance range: {duration:.3f}s")
        if peak < 1e-5 or rms < 1e-7:
            raise RuntimeError(f"generated WAV is silent or near-silent: peak={peak:.8g}, rms={rms:.8g}")

        digest = hashlib.sha256(wav_path.read_bytes()).hexdigest()
        report.update({
            "status": "PASS",
            "executed_code_cells": executed_cells,
            "notebook_execution_seconds": round(time.monotonic() - started, 3),
            "model_id": "facebook/audiogen-medium",
            "snapshot_path": str(namespace.get("AUDIOGEN_SNAPSHOT", "")),
            "audio_path": str(wav_path),
            "audio_sha256": digest,
            "audio_bytes": wav_path.stat().st_size,
            "sample_rate_hz": int(rate),
            "channels": int(samples.shape[1]),
            "duration_seconds": round(duration, 4),
            "peak_amplitude": peak,
            "rms_amplitude": rms,
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
        report["finished_unix"] = time.time()
        report_path = report_root / "report.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"AUDIOGEN_REPORT={report_path}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
