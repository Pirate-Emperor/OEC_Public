#!/usr/bin/env python3
"""Execute the actual final UI cell from an OEC Jupyter notebook on a live node.

The parent process launches the selected notebook cell in a clean child process,
waits for a real Gradio HTTP response, and issues a real FLUX or TRELLIS request.
The child is the isolated kernel-like process that owns the model and Gradio app.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time
import traceback
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MODE_CONFIG = {
    "flux": {
        "notebook": "pipeline_flux_only.ipynb",
        "selector": "FLUX_PIPELINE_READY=PASS",
        "default_timeout": 180,
        "kind": "flux",
    },
    "trellis-only": {
        "notebook": "pipeline_trellis_3d_only.ipynb",
        "selector": "TRELLIS_GRADIO_LAUNCH=START",
        "default_timeout": 420,
        "kind": "trellis",
    },
    "trellis-combined": {
        "notebook": "pipeline_trellis_3d.ipynb",
        "selector": "TRELLIS_GRADIO_LAUNCH=START",
        "default_timeout": 420,
        "kind": "trellis-startup",
    },
    "trellis-combined-flux": {
        "notebook": "pipeline_trellis_3d.ipynb",
        "selector": "FLUX_GRADIO_START=",
        "default_timeout": 180,
        "kind": "flux-service",
    },
}


def _tail(path: Path, lines: int = 100) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError as exc:
        return f"<unable to read {path}: {exc}>"


def execute_cell(notebook_path: Path, selector: str, kind: str) -> None:
    """Run a notebook's source cell under a fresh process with its expected globals."""
    os.chdir(ROOT)
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    matches = []
    for index, cell in enumerate(notebook.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        if selector in source:
            matches.append((index, source))
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one code cell containing {selector!r} in {notebook_path.name}; "
            f"found {len(matches)}"
        )
    index, source = matches[0]

    namespace = {
        "__name__": "__main__",
        "__file__": str(notebook_path),
        "ENABLE_DISK_PURGE": False,
        "os": os,
    }
    if kind == "flux":
        # core_config resolves the configured model/output paths and does not import Torch.
        import core_config
        namespace["SYSTEM_DIRS"] = core_config.SYSTEM_DIRS
        gpu = os.environ.get("AIEROS_GPU")
        if not gpu:
            raise RuntimeError("AIEROS_GPU was not set before executing the FLUX notebook cell")
        namespace["target_gpu"] = gpu

    print(
        f"NOTEBOOK_FINAL_CELL_EXEC=START notebook={notebook_path.name} "
        f"cell_index={index} selector={selector}",
        flush=True,
    )
    try:
        exec(compile(source, f"{notebook_path.name}:cell-{index}", "exec"), namespace, namespace)
    except BaseException as exc:
        print(
            f"NOTEBOOK_FINAL_CELL_EXEC=FAIL notebook={notebook_path.name} "
            f"cell_index={index} error={type(exc).__name__}: {exc}",
            flush=True,
        )
        traceback.print_exc()
        raise
    print(
        f"NOTEBOOK_FINAL_CELL_EXEC=PASS notebook={notebook_path.name} cell_index={index}",
        flush=True,
    )
    # prevent_thread_lock=True returns control after starting Gradio. Keep this
    # kernel-like process alive so the parent can exercise the real callback.
    while True:
        time.sleep(30)


def _wait_for_health(process: subprocess.Popen, url: str, log_path: Path, timeout: int) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Notebook final-cell process exited with code {process.returncode}.\n"
                f"--- child log tail ---\n{_tail(log_path)}"
            )
        try:
            with opener.open(url, timeout=3) as response:
                if response.status == 200:
                    print(f"NOTEBOOK_FINAL_CELL_HTTP=PASS url={url} status=200", flush=True)
                    return
                last_error = f"HTTP {response.status}"
        except Exception as exc:
            last_error = repr(exc)
        time.sleep(1)
    raise TimeoutError(
        f"Gradio did not become healthy within {timeout}s at {url}; last_error={last_error}.\n"
        f"--- child log tail ---\n{_tail(log_path)}"
    )


def _launch_cell(mode: str, port: int, timeout: int, artifact_dir: Path, run_root: Path):
    config = MODE_CONFIG[mode]
    notebook_path = ROOT / config["notebook"]
    selector = config["selector"]
    log_path = artifact_dir / "notebook-final-cell.log"
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"

    if config["kind"] == "flux":
        env["AIEROS_FLUX_GRADIO_PORT"] = str(port)
        env["AIEROS_FLUX_GRADIO_HOST"] = "127.0.0.1"
        env["AIEROS_FLUX_UI_OUTPUT_MODE"] = "scratch"
        env["AIEROS_FLUX_UI_SCRATCH_DIR"] = str(run_root / "flux-scratch")
        env.setdefault("AIEROS_GPU", env.get("CUDA_VISIBLE_DEVICES", "0").split(",")[0])
    elif config["kind"] == "flux-service":
        env["AIEROS_FLUX_GRADIO_PORT"] = str(port)
        env["AIEROS_FLUX_UI_OUTPUT_MODE"] = "scratch"
        env["AIEROS_FLUX_UI_SCRATCH_DIR"] = str(run_root / "flux-combined-scratch")
        flux_gpu = os.environ.get("AIEROS_GPU", env.get("CUDA_VISIBLE_DEVICES", "0").split(",")[0]).strip()
        if not flux_gpu.isdigit():
            raise RuntimeError(f"Invalid physical FLUX GPU selected for combined notebook: {flux_gpu!r}")
        try:
            probe = subprocess.run(
                ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"Cannot enumerate physical GPUs for combined notebook acceptance: {exc}") from exc
        available_gpus = [line.strip() for line in probe.stdout.splitlines() if line.strip().isdigit()]
        if flux_gpu not in available_gpus:
            raise RuntimeError(f"Selected FLUX GPU {flux_gpu} is not present in nvidia-smi inventory {available_gpus}")
        other_gpus = [gpu for gpu in available_gpus if gpu != flux_gpu]
        if not other_gpus:
            raise RuntimeError("Combined notebook requires distinct physical GPU IDs for FLUX and TRELLIS.")
        env["AIEROS_FLUX_UI_GPU"] = flux_gpu
        env["AIEROS_TRELLIS_UI_GPU"] = other_gpus[0]
        env.pop("CONDA_ROOT", None)
    else:
        env["AIEROS_TRELLIS_GRADIO_PORT"] = str(port)
        env["AIEROS_TRELLIS_GRADIO_HOST"] = "127.0.0.1"
        env["AIEROS_TRELLIS_UI_OUTPUT_MODE"] = "scratch"
        env["AIEROS_TRELLIS_ATTN_BACKEND"] = os.environ.get("AIEROS_TRELLIS_ATTN_BACKEND", "xformers")

    child_args = [
        sys.executable, "-u", str(Path(__file__).resolve()),
        "--execute-cell",
        "--notebook", str(notebook_path),
        "--selector", selector,
        "--kind", config["kind"],
    ]
    with log_path.open("w", encoding="utf-8") as log_stream:
        process = subprocess.Popen(
            child_args, cwd=ROOT, env=env, stdout=log_stream,
            stderr=subprocess.STDOUT, start_new_session=True,
        )
    print(
        f"NOTEBOOK_FINAL_CELL_PROCESS=START mode={mode} pid={process.pid} "
        f"port={port} timeout_seconds={timeout} log={log_path}",
        flush=True,
    )
    try:
        _wait_for_health(process, f"http://127.0.0.1:{port}/", log_path, timeout)
        return process, log_path
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        print("NOTEBOOK_FINAL_CELL_LOG_TAIL_BEGIN\n" + _tail(log_path) + "\nNOTEBOOK_FINAL_CELL_LOG_TAIL_END", flush=True)
        raise


def _artifact_report(artifact_dir: Path, report: dict) -> None:
    report_path = artifact_dir / "notebook-final-cell-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("NOTEBOOK_FINAL_CELL_RESULT=" + json.dumps(report, sort_keys=True), flush=True)


def run_acceptance(mode: str, port: int, timeout: int, artifact_dir: Path, run_root: Path) -> int:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    tmp_root = Path("/tmp").resolve()
    run_root = run_root.expanduser().resolve()
    try:
        relative = run_root.relative_to(tmp_root)
    except ValueError as exc:
        raise RuntimeError(f"Refusing notebook scratch outside /tmp: {run_root}") from exc
    run_id = os.environ.get("GITHUB_RUN_ID")
    expected_root_name = f"oec-notebook-final-cell-run-{run_id}" if run_id else ""
    if not relative.parts or not expected_root_name or relative.parts[0] != expected_root_name:
        raise RuntimeError(f"Refusing non-run-scoped notebook scratch path: {run_root}")
    if run_root.exists():
        raise FileExistsError(f"Refusing to reuse notebook scratch path: {run_root}")
    import core_config
    model_root = Path(core_config.SYSTEM_DIRS["models"]).expanduser().resolve()
    model_probe = model_root
    while not model_probe.exists() and model_probe.parent != model_probe:
        model_probe = model_probe.parent
    if not model_probe.exists():
        raise RuntimeError(f"Cannot resolve existing model-cache filesystem for {model_root}")
    if tmp_root.stat().st_dev == model_probe.stat().st_dev:
        raise RuntimeError("NOTEBOOK_FINAL_CELL=BLOCKED_TMP_SAME_FILESYSTEM_AS_MODEL_STORAGE")
    free_bytes = shutil.disk_usage(tmp_root).free
    if free_bytes < 4 * 1024**3:
        raise RuntimeError(f"NOTEBOOK_FINAL_CELL=BLOCKED_TMP_LOW_SPACE free_bytes={free_bytes} required_bytes={4 * 1024**3}")
    print(f"NOTEBOOK_FINAL_CELL_PREFLIGHT=PASS model_root={model_root} tmp_free_bytes={free_bytes}", flush=True)
    (tmp_root / expected_root_name).mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=False)
    process = None
    log_path = artifact_dir / "notebook-final-cell.log"
    started = time.time()
    try:
        process, log_path = _launch_cell(mode, port, timeout, artifact_dir, run_root)
        from gradio_client import Client, handle_file

        root_url = f"http://127.0.0.1:{port}"
        client = Client(root_url, verbose=True)
        if mode == "flux":
            result = client.predict(
                "A small red ceramic teapot on a clean studio table, soft window light, commercial product photography",
                None, 512, 512, 4, 1.0, 2048, False,
                api_name="/generate",
            )
            from pipeline_flux_image import validate_png_file

            scratch = run_root / "flux-scratch"
            pngs = sorted(scratch.glob("flux2_klein_*.png"), key=lambda p: p.stat().st_mtime)
            if not pngs:
                raise RuntimeError(f"Notebook final cell returned {result!r}, but no FLUX PNG appeared in {scratch}")
            png = pngs[-1]
            metadata_path = png.with_name(png.stem + "_info.json")
            png_info = validate_png_file(png)
            if not metadata_path.is_file():
                raise RuntimeError(f"FLUX sidecar missing after notebook final-cell request: {metadata_path}")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if (metadata.get("width"), metadata.get("height")) != (512, 512):
                raise RuntimeError(f"FLUX metadata has incorrect dimensions: {metadata}")
            shutil.copy2(png, artifact_dir / "flux-notebook-final-cell.png")
            shutil.copy2(metadata_path, artifact_dir / "flux-notebook-final-cell-info.json")
            report = {
                "mode": mode, "status": "PASS", "notebook": MODE_CONFIG[mode]["notebook"],
                "port": port, "http": 200, "api_name": "/generate",
                "response_types": [type(x).__name__ for x in result],
                "png_bytes": png_info["bytes"], "width": metadata["width"],
                "height": metadata["height"], "seed": metadata.get("seed"),
                "steps": metadata.get("num_inference_steps", metadata.get("steps")),
                "output_mode": metadata.get("output_mode"),
                "generation_seconds": metadata.get("generation_seconds"),
                "artifact_png": str(artifact_dir / "flux-notebook-final-cell.png"),
            }
        elif mode == "trellis-combined-flux":
            result = client.predict(
                "A small red ceramic teapot on a clean studio table, soft window light, commercial product photography",
                None, 512, 512, 4, 1.0, 2048, False,
                api_name="/generate",
            )
            from pipeline_flux_image import validate_png_file

            scratch = run_root / "flux-combined-scratch"
            pngs = sorted(scratch.glob("flux2_klein_*.png"), key=lambda p: p.stat().st_mtime)
            if not pngs:
                raise RuntimeError(f"Combined notebook FLUX cell returned {result!r}, but no PNG appeared in {scratch}")
            png = pngs[-1]
            metadata_path = png.with_name(png.stem + "_info.json")
            png_info = validate_png_file(png)
            if not metadata_path.is_file():
                raise RuntimeError(f"Combined notebook FLUX sidecar is missing: {metadata_path}")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if (metadata.get("width"), metadata.get("height")) != (512, 512):
                raise RuntimeError(f"Combined notebook FLUX metadata has incorrect dimensions: {metadata}")
            if metadata.get("output_mode") != "local_scratch_only":
                raise RuntimeError(f"Combined notebook FLUX did not use scratch output: {metadata}")
            shutil.copy2(png, artifact_dir / "flux-combined-notebook-final-cell.png")
            shutil.copy2(metadata_path, artifact_dir / "flux-combined-notebook-final-cell-info.json")
            report = {
                "mode": mode, "status": "PASS", "notebook": MODE_CONFIG[mode]["notebook"],
                "port": port, "http": 200, "api_name": "/generate",
                "response_types": [type(x).__name__ for x in result],
                "png_bytes": png_info["bytes"], "width": metadata["width"],
                "height": metadata["height"], "seed": metadata.get("seed"),
                "steps": metadata.get("num_inference_steps", metadata.get("steps")),
                "output_mode": metadata.get("output_mode"),
                "generation_seconds": metadata.get("generation_seconds"),
                "flux_gpu": os.environ.get("AIEROS_GPU", os.environ.get("CUDA_VISIBLE_DEVICES")),
                "manager_conda_root_default": str(Path.home() / "Conda"),
                "artifact_png": str(artifact_dir / "flux-combined-notebook-final-cell.png"),
            }
        elif mode == "trellis-only":
            from PIL import Image, ImageDraw
            import trimesh

            input_image_path = run_root / "trellis-notebook-input.png"
            image = Image.new("RGB", (512, 512), (245, 245, 245))
            draw = ImageDraw.Draw(image)
            draw.rectangle((160, 140, 350, 360), fill=(45, 110, 190), outline=(20, 45, 80), width=8)
            draw.ellipse((160, 110, 350, 175), fill=(70, 145, 220), outline=(20, 45, 80), width=8)
            draw.ellipse((160, 325, 350, 380), fill=(30, 80, 150), outline=(20, 45, 80), width=8)
            image.save(input_image_path)
            result = client.predict(handle_file(str(input_image_path)), 100000, api_name="/generate_3d")

            safe_user = "".join(ch for ch in os.environ.get("USER", "user") if ch.isalnum() or ch in "-_") or "user"
            output_dir = Path("/tmp") / f"oec-trellis-ui-{safe_user}-{process.pid}"
            deadline = time.monotonic() + 30
            glbs = []
            while time.monotonic() < deadline:
                glbs = sorted(output_dir.glob("standalone_t2_*.glb"), key=lambda p: p.stat().st_mtime) if output_dir.is_dir() else []
                if glbs:
                    break
                time.sleep(0.5)
            if not glbs:
                raise RuntimeError(f"TRELLIS UI API returned {result!r}, but no GLB appeared under {output_dir}")
            glb_path = glbs[-1]
            scene = trimesh.load(str(glb_path), force="scene")
            geometries = list(scene.geometry.values())
            vertices = sum(len(g.vertices) for g in geometries if hasattr(g, "vertices"))
            faces = sum(len(g.faces) for g in geometries if hasattr(g, "faces"))
            if not geometries or vertices <= 0 or faces <= 0:
                raise RuntimeError(f"TRELLIS notebook GLB failed geometry reopen: geometries={len(geometries)} vertices={vertices} faces={faces}")
            artifact_glb = artifact_dir / "trellis-notebook-final-cell.glb"
            shutil.copy2(glb_path, artifact_glb)
            report = {
                "mode": mode, "status": "PASS", "notebook": MODE_CONFIG[mode]["notebook"],
                "port": port, "http": 200, "api_name": "/generate_3d",
                "response_type": type(result).__name__, "glb_bytes": artifact_glb.stat().st_size,
                "glb_sha256": hashlib.sha256(artifact_glb.read_bytes()).hexdigest(),
                "geometry_count": len(geometries), "vertices": vertices, "faces": faces,
                "server_output": str(glb_path), "artifact_glb": str(artifact_glb),
            }
        else:
            report = {
                "mode": mode, "status": "PASS", "notebook": MODE_CONFIG[mode]["notebook"],
                "port": port, "http": 200, "api_request": "startup-only",
                "purpose": "Verify the combined notebook's actual final TRELLIS cell including its Gradio 6 app-level theme parameter.",
            }
        report["runner"] = os.environ.get("RUNNER_NAME")
        report["host"] = os.uname().nodename
        report["gpu"] = os.environ.get("AIEROS_GPU", os.environ.get("CUDA_VISIBLE_DEVICES"))
        report["offline_cache_only"] = True
        report["elapsed_seconds"] = round(time.time() - started, 3)
        report["run_root"] = str(run_root)
        _artifact_report(artifact_dir, report)
        return 0
    except BaseException as exc:
        report = {
            "mode": mode, "status": "FAIL", "notebook": MODE_CONFIG[mode]["notebook"],
            "port": port, "error_type": type(exc).__name__, "error": str(exc),
            "runner": os.environ.get("RUNNER_NAME"), "host": os.uname().nodename,
            "elapsed_seconds": round(time.time() - started, 3),
        }
        _artifact_report(artifact_dir, report)
        raise
    finally:
        active_error = sys.exc_info()[0]
        if mode == "trellis-combined-flux" and log_path.is_file():
            try:
                cell_log = log_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                cell_log = ""
            if "FLUX_GRADIO_START=PASS" in cell_log:
                manager = ROOT / "tools" / "oec_service_manager.py"
                conda_root = Path.home() / "Conda"
                try:
                    stopped = subprocess.run(
                        [sys.executable, str(manager), "--conda-root", str(conda_root), "stop", "flux-ui"],
                        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, timeout=30,
                    )
                    print(stopped.stdout, end="" if stopped.stdout.endswith("\n") else "\n", flush=True)
                    if stopped.returncode == 0:
                        print("COMBINED_FLUX_SERVICE_CLEANUP=PASS", flush=True)
                    else:
                        print(f"COMBINED_FLUX_SERVICE_CLEANUP=FAIL exit={stopped.returncode}", flush=True)
                        if active_error is None:
                            raise RuntimeError(f"Failed to stop the test-owned combined FLUX service: exit={stopped.returncode}")
                except (OSError, subprocess.SubprocessError) as exc:
                    print(f"COMBINED_FLUX_SERVICE_CLEANUP=FAIL error={type(exc).__name__}: {exc}", flush=True)
                    if active_error is None:
                        raise
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        # Keep the exact child log adjacent to the machine-readable result.


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=tuple(MODE_CONFIG))
    parser.add_argument("--execute-cell", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--notebook", type=Path)
    parser.add_argument("--selector")
    parser.add_argument("--kind", choices=("flux", "trellis", "trellis-startup", "flux-service"))
    parser.add_argument("--port", type=int, default=7864)
    parser.add_argument("--timeout-seconds", type=int)
    parser.add_argument("--artifact-dir", type=Path, default=Path("notebook-final-cell-artifacts"))
    parser.add_argument("--run-root", type=Path, default=Path("/tmp/oec-notebook-final-cell-local"))
    args = parser.parse_args()
    if args.execute_cell:
        if args.notebook is None or args.selector is None or args.kind is None:
            parser.error("--execute-cell requires --notebook, --selector and --kind")
        execute_cell(args.notebook.resolve(), args.selector, args.kind)
        return 0
    if args.mode is None:
        parser.error("--mode is required")
    timeout = args.timeout_seconds or MODE_CONFIG[args.mode]["default_timeout"]
    artifact_dir = args.artifact_dir if args.artifact_dir.is_absolute() else ROOT / args.artifact_dir
    run_root = args.run_root if args.run_root.is_absolute() else ROOT / args.run_root
    return run_acceptance(args.mode, args.port, timeout, artifact_dir, run_root)


if __name__ == "__main__":
    raise SystemExit(main())
