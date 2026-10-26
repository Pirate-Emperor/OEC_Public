#!/usr/bin/env python3
"""Execute pipeline_wan_video.ipynb fully and validate its generated MP4 before cache purge."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from IPython.core.interactiveshell import InteractiveShell

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
NOTEBOOK = ROOT / "pipeline_wan_video.ipynb"


def validate_mp4(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size <= 1024:
        raise RuntimeError(f"Wan notebook did not create a non-empty MP4: {path}")
    probe = shutil.which("ffprobe")
    if not probe:
        raise RuntimeError("ffprobe is required to validate the generated MP4; no fake PASS is reported")
    result = subprocess.run(
        [probe, "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,width,height,nb_read_frames,r_frame_rate,duration",
         "-show_entries", "format=duration,format_name", "-of", "json", str(path)],
        text=True, capture_output=True, timeout=60, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"ffprobe rejected Wan output: {result.stderr[-2000:]}")
    payload = json.loads(result.stdout)
    streams = payload.get("streams") or []
    if not streams:
        raise RuntimeError("Wan MP4 has no video stream")
    stream = streams[0]
    frames = int(stream.get("nb_read_frames") or 0)
    width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
    duration = float((payload.get("format") or {}).get("duration") or stream.get("duration") or 0.0)
    if frames < 5 or width <= 0 or height <= 0 or duration <= 0:
        raise RuntimeError(f"Wan MP4 stream metadata is invalid: {stream}, format={payload.get('format')}")
    return {
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "codec": stream.get("codec_name"),
        "width": width, "height": height, "frames": frames,
        "fps": stream.get("r_frame_rate"), "duration_seconds": duration,
        "format_name": (payload.get("format") or {}).get("format_name"),
    }


def main() -> int:
    report_dir = Path(os.environ.get("OEC_WAN_SMOKE_DIR", str(Path("/tmp") / "oec-wan-notebook-smoke"))).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    output_dir = report_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    os.environ.update({
        "OEC_WAN_HEADLESS_SMOKE": "1",
        "OEC_WAN_NUM_FRAMES": os.environ.get("OEC_WAN_NUM_FRAMES", "9"),
        "OEC_WAN_OUTPUT_DIR": str(output_dir),
        "OEC_WAN_ALLOW_DOWNLOAD": os.environ.get("OEC_WAN_ALLOW_DOWNLOAD", "0"),
        "GRADIO_ANALYTICS_ENABLED": "False",
        "HF_HUB_DISABLE_TELEMETRY": "1",
    })
    report: dict[str, Any] = {
        "test": "Wan video notebook full-code-cell acceptance",
        "notebook": str(NOTEBOOK),
        "started_unix": time.time(),
        "python": sys.executable,
        "status": "FAIL",
        "output_dir": str(output_dir),
    }
    produced: Path | None = None
    try:
        document = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        if document.get("nbformat") != 4:
            raise RuntimeError("invalid notebook format")
        shell = InteractiveShell()
        namespace = {"__name__": "__main__", "__file__": str(NOTEBOOK)}
        executed: list[int] = []
        for index, cell in enumerate(document["cells"]):
            if cell.get("cell_type") != "code":
                continue
            source = "".join(cell.get("source") or [])
            if not source.strip():
                continue
            print(f"WAN_NOTEBOOK_CELL_START={index}", flush=True)
            transformed = shell.transform_cell(source)
            exec(compile(transformed, f"{NOTEBOOK.name}:cell-{index}", "exec"), namespace, namespace)
            executed.append(index)
            print(f"WAN_NOTEBOOK_CELL_PASS={index}", flush=True)
        produced = Path(namespace["WAN_OUTPUT_PATH"]).resolve()
        asset_validation = validate_mp4(produced)
        copied = report_dir / "wan-notebook-generated.mp4"
        if produced != copied.resolve():
            shutil.copy2(produced, copied)
        report.update({
            "status": "PASS",
            "executed_code_cells": executed,
            "asset_path": str(copied),
            "asset_validation": validate_mp4(copied),
            "shared_model_outputs_written": False,
        })
        print("WAN_NOTEBOOK_ACCEPTANCE " + json.dumps(report, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()[-12000:]
        print("WAN_NOTEBOOK_ACCEPTANCE " + json.dumps(report, ensure_ascii=False), flush=True)
        traceback.print_exc()
        return 1
    finally:
        if produced is not None:
            try:
                if output_dir.resolve() in produced.parents and produced.is_file() and not produced.is_symlink():
                    produced.unlink()
            except OSError:
                pass
        report["finished_unix"] = time.time()
        (report_dir / "wan-notebook-report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    raise SystemExit(main())
