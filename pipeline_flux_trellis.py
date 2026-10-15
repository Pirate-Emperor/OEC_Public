#!/usr/bin/env python3
"""Offline, sequential FLUX.2 Klein -> TRELLIS.2 pipeline for OEC.

The two model stages run in separate subprocesses so their GPU allocations do not
overlap. Both use cache-only mode; this orchestrator never installs packages or
downloads weights. Output artifacts are restricted to isolated temporary storage.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import selectors
import socket
import struct
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_LOCK = Path("/tmp/oec-flux-inference.lock")
FLUX_SCRIPT = REPO_ROOT / "pipeline_flux_image.py"
TRELLIS_SCRIPT = REPO_ROOT / "pipeline_trellis_3d.py"
GPU_ADMISSION_SCRIPT = REPO_ROOT / "tools" / "flux_gpu_admission.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a FLUX.2 Klein image, then pass that exact PNG to TRELLIS.2 for a validated GLB."
    )
    parser.add_argument("--work-dir", type=Path, required=True,
                        help="New run-specific scratch directory (for example /tmp/oec-flux-trellis-$GITHUB_RUN_ID).")
    parser.add_argument("--python", default=sys.executable, help="phase2_3d Python interpreter used by both model CLIs.")
    parser.add_argument("--model-cache", type=Path, help="Optional FLUX model-cache root.")
    parser.add_argument("--trellis-model-cache", type=Path, help="Optional TRELLIS Hub-cache root.")
    parser.add_argument("--trellis-repo-dir", type=Path, help="Optional TRELLIS.2 source checkout.")
    parser.add_argument("--attention-backend", choices=("xformers", "flash_attn"), default="xformers")
    parser.add_argument("--source-mode", choices=("flux", "images"), default="flux",
                        help="flux (default) generates an image first; images sends a folder of existing images straight to TRELLIS.")
    parser.add_argument("--image-dir", type=Path, help="Input image folder when --source-mode images is selected.")
    parser.add_argument("--recursive", action="store_true", help="Include supported images in nested folders when --source-mode images.")
    parser.add_argument("--prompt", default="A polished red ceramic tea kettle on a quiet studio table, soft natural window light, realistic product photography")
    parser.add_argument("--seed", type=int, default=2048)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--guidance-scale", type=float, default=1.0)
    parser.add_argument("--max-image-size", type=int, default=1024)
    parser.add_argument("--decimation-target", type=int, default=100_000)
    parser.add_argument("--texture-size", type=int, default=2048)
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--lock-timeout", type=int, default=1500)
    parser.add_argument("--flux-timeout", type=int, default=840)
    parser.add_argument("--trellis-timeout", type=int, default=1800)
    return parser


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _list_source_images(image_dir: Path | None, recursive: bool = False) -> list[Path]:
    if image_dir is None:
        raise ValueError("--image-dir is required with --source-mode images.")
    root = image_dir.expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Input image directory does not exist: {root}")
    candidates = root.rglob("*") if recursive else root.iterdir()
    images = []
    for candidate in candidates:
        try:
            if candidate.is_symlink() or not candidate.is_file():
                continue
        except OSError:
            continue
        if candidate.suffix.lower() in IMAGE_EXTENSIONS:
            images.append(candidate.resolve())
    images.sort(key=lambda item: item.relative_to(root).as_posix().casefold())
    if not images:
        raise FileNotFoundError(f"No supported image files in {root}; supported: {', '.join(sorted(IMAGE_EXTENSIONS))}")
    return images


def _emit(event: str, **fields: Any) -> None:
    payload = {"event": event, "time": datetime.now(timezone.utc).isoformat(), **fields}
    print("OEC_PIPELINE " + json.dumps(payload, sort_keys=True, default=str), flush=True)


@contextlib.contextmanager
def _gpu_lock(path: Path, timeout: int) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        started = time.monotonic()
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                elapsed = time.monotonic() - started
                if elapsed >= timeout:
                    raise RuntimeError(f"BLOCKED_GPU_LOCK_TIMEOUT: {path} after {timeout}s")
                if int(elapsed) % 15 == 0:
                    _emit("gpu_lock_wait", lock=str(path), elapsed_seconds=int(elapsed))
                time.sleep(1)
        _emit("gpu_lock_acquired", lock=str(path), waited_seconds=round(time.monotonic() - started, 2))
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            _emit("gpu_lock_released", lock=str(path))


def _select_gpu(python: str, env: dict[str, str], stage: str) -> str:
    cmd = [python, str(GPU_ADMISSION_SCRIPT), "--print-index-only",
           "--wait-seconds", "180", "--poll-interval", "5"]
    _emit("stage_start", stage=stage, command=cmd, admission_wait_seconds=180)
    proc = subprocess.run(cmd, cwd=REPO_ROOT, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=240, check=False)
    output = proc.stdout or ""
    for line in output.splitlines():
        print(f"[{stage}] {line}", flush=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{stage}: GPU admission blocked (exit={proc.returncode}); no process was signalled.")
    choices = [line.strip() for line in output.splitlines() if line.strip().isdigit()]
    if not choices:
        raise RuntimeError(f"{stage}: admission returned no physical GPU index.")
    selected = choices[-1]
    _emit("stage_pass", stage=stage, gpu=selected)
    return selected


def _run_stage(stage: str, cmd: list[str], env: dict[str, str], timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + timeout
    _emit("stage_start", stage=stage, command=cmd, timeout_seconds=timeout)
    lines: list[str] = []
    partial = b""
    proc = subprocess.Popen(
        cmd, cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, bufsize=0,
    )
    assert proc.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    timed_out = False
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = proc.poll() is None
                if timed_out:
                    proc.kill()
                break
            events = selector.select(min(remaining, 1.0))
            if not events:
                # The selector also reports EOF; keep reading through it so a
                # short final burst of child output cannot be discarded.
                if proc.poll() is not None:
                    continue
                continue
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                break
            partial += chunk
            while b"\n" in partial:
                raw_line, partial = partial.split(b"\n", 1)
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r")
                print(f"[{stage}] {line}", flush=True)
                lines.append(line)
        if partial:
            line = partial.decode("utf-8", errors="replace").rstrip("\r")
            print(f"[{stage}] {line}", flush=True)
            lines.append(line)
        if timed_out:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            detail = "\n".join(lines[-80:])
            raise RuntimeError(f"BLOCKED_TIMEOUT: {stage} exceeded {timeout}s\n{detail}")
        code = proc.wait(timeout=10)
    finally:
        selector.close()
        proc.stdout.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    result = {
        "stage": stage,
        "return_code": code,
        "duration_seconds": round(time.monotonic() - started, 3),
        "command": cmd,
        "tail": lines[-100:],
    }
    if code != 0:
        _emit("stage_fail", stage=stage, return_code=code, duration_seconds=result["duration_seconds"])
        tail = "\n".join(lines[-80:])
        blocked = any("BLOCKED_" in line or "=BLOCKED" in line for line in lines[-100:])
        prefix = "BLOCKED_STAGE_FAILURE" if blocked else "PIPELINE_STAGE_FAILED"
        raise RuntimeError(f"{prefix}: {stage} exited {code}. Last output:\n" + tail)
    _emit("stage_pass", stage=stage, return_code=code, duration_seconds=result["duration_seconds"])
    return result


def _validate_png(path: Path, metadata_path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 8:
        raise RuntimeError(f"FLUX PNG missing or empty: {path}")
    with path.open("rb") as handle:
        if handle.read(8) != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError(f"FLUX output has no PNG signature: {path}")
    from PIL import Image
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        width, height = image.size
        image_format = image.format
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if image_format != "PNG" or (width, height) != (metadata.get("width"), metadata.get("height")):
        raise RuntimeError("FLUX PNG dimensions/format disagree with its metadata.")
    if metadata.get("image_path") != str(path.resolve()) and metadata.get("image_path") != str(path):
        raise RuntimeError("FLUX PNG metadata points at a different image path.")
    if metadata.get("seed") is None or metadata.get("image_bytes") != path.stat().st_size:
        raise RuntimeError("FLUX PNG metadata is missing the seed or correct byte count.")
    return {
        "path": str(path), "bytes": path.stat().st_size, "sha256": _sha256(path),
        "width": width, "height": height, "format": image_format,
        "seed": metadata["seed"], "model_id": metadata.get("model_id"),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inspect_glb_container(path: Path) -> dict[str, Any]:
    """Validate the GLB header and mesh accessors without loading renderer libraries."""
    if not path.is_file() or path.stat().st_size < 20:
        raise RuntimeError(f"TRELLIS GLB missing or too small: {path}")
    raw = path.read_bytes()
    if raw[:4] != b"glTF":
        raise RuntimeError("TRELLIS output is not a GLB (missing glTF magic).")
    version, declared_length = struct.unpack_from("<II", raw, 4)
    if version != 2 or declared_length != len(raw):
        raise RuntimeError(f"Invalid GLB header: version={version}, declared={declared_length}, actual={len(raw)}")
    json_length, json_type = struct.unpack_from("<II", raw, 12)
    if json_type != 0x4E4F534A or 20 + json_length > len(raw):
        raise RuntimeError("Invalid GLB JSON chunk.")
    try:
        gltf = json.loads(raw[20:20 + json_length].decode("utf-8").rstrip(" \t\r\n\x00"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("GLB JSON chunk cannot be parsed.") from exc
    accessors = gltf.get("accessors", [])
    primitives = [p for mesh in gltf.get("meshes", []) for p in mesh.get("primitives", [])]
    vertex_counts, index_counts = [], []
    for primitive in primitives:
        attrs = primitive.get("attributes", {})
        position_id, index_id = attrs.get("POSITION"), primitive.get("indices")
        if isinstance(position_id, int) and 0 <= position_id < len(accessors):
            vertex_counts.append(int(accessors[position_id].get("count", 0)))
        if isinstance(index_id, int) and 0 <= index_id < len(accessors):
            index_counts.append(int(accessors[index_id].get("count", 0)))
    if not primitives or not any(vertex_counts) or not any(index_counts):
        raise RuntimeError("TRELLIS GLB has no non-empty POSITION/index accessors.")
    return {
        "path": str(path), "bytes": len(raw), "sha256": _sha256(path),
        "gltf_version": version, "mesh_count": len(gltf.get("meshes", [])),
        "primitive_count": len(primitives), "vertex_accessor_counts": vertex_counts,
        "index_accessor_counts": index_counts, "_gltf": gltf,
    }


def _validate_glb(path: Path) -> dict[str, Any]:
    container = _inspect_glb_container(path)
    import trimesh
    loaded = trimesh.load(str(path), force="scene", process=False)
    mesh_stats = []
    for geometry in loaded.geometry.values():
        vertices = getattr(geometry, "vertices", ())
        faces = getattr(geometry, "faces", ())
        vertex_count, face_count = len(vertices), len(faces)
        if vertex_count and face_count:
            mesh_stats.append({"vertices": vertex_count, "faces": face_count,
                               "geometry_type": type(geometry).__name__})
    if not mesh_stats:
        raise RuntimeError("TRELLIS GLB reopened but contained no usable non-empty mesh geometry.")
    container.pop("_gltf", None)
    container.update({
        "reopened_geometry": mesh_stats,
        "reopened_vertices": sum(m["vertices"] for m in mesh_stats),
        "reopened_faces": sum(m["faces"] for m in mesh_stats),
    })
    return container



def _optional_path_args(cmd: list[str], flag: str, value: Path | None) -> None:
    if value is not None:
        cmd.extend([flag, str(value.expanduser().resolve())])


def _stage_commands(args: argparse.Namespace, work_dir: Path, gpu: str) -> dict[str, list[str]]:
    flux = [args.python, str(FLUX_SCRIPT), "--mode", "generate", "--offline",
            "--scratch-output", "--gpu", gpu, "--output", str(work_dir / "flux2_klein.png"),
            "--prompt", args.prompt, "--seed", str(args.seed), "--width", str(args.width),
            "--height", str(args.height), "--steps", str(args.steps),
            "--guidance-scale", str(args.guidance_scale)]
    _optional_path_args(flux, "--model-cache", args.model_cache)
    trellis = [args.python, str(TRELLIS_SCRIPT), "--mode", "generate", "--offline",
               "--scratch-output", "--attention-backend", args.attention_backend,
               "--gpu", gpu, "--input", str(work_dir / "flux2_klein.png"),
               "--output", str(work_dir / "trellis_asset.glb"),
               "--max-image-size", str(args.max_image_size),
               "--decimation-target", str(args.decimation_target),
               "--texture-size", str(args.texture_size)]
    _optional_path_args(trellis, "--model-cache", args.trellis_model_cache)
    _optional_path_args(trellis, "--repo-dir", args.trellis_repo_dir)
    return {"flux_generate": flux, "trellis_generate": trellis}


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    python = str(Path(args.python).expanduser().resolve())
    work_dir = args.work_dir.expanduser().resolve()
    # Keep all combined-run artifacts on the explicit local /tmp filesystem.
    # TMPDIR can be redirected by core_config to shared model/cache storage and
    # must not be trusted as an output root for this pipeline.
    temp_root = Path("/tmp").resolve()
    if not _is_relative_to(work_dir, temp_root):
        raise RuntimeError("BLOCKED_WORKDIR: combined pipeline artifacts must remain under local /tmp.")
    if work_dir.exists():
        raise FileExistsError(f"Refusing to reuse an existing run directory: {work_dir}")
    work_dir.mkdir(parents=True, mode=0o700)
    report_path = work_dir / "pipeline_report.json"
    started = time.monotonic()
    report: dict[str, Any] = {
        "schema_version": 1,
        "pipeline": "FLUX.2 Klein -> TRELLIS.2",
        "status": "IN_PROGRESS",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "runner_name": os.environ.get("RUNNER_NAME", "unknown"),
        "host": socket.gethostname(),
        "git_ref": os.environ.get("GITHUB_REF"),
        "git_sha": os.environ.get("GITHUB_SHA"),
        "work_dir": str(work_dir),
        "model_ids": {"flux": "black-forest-labs/FLUX.2-klein-4B", "trellis": "microsoft/TRELLIS.2-4B"},
        "cache_only": True,
        "network_downloads_allowed": False,
        "package_installs_allowed": False,
        "shared_output_writes_allowed": False,
        "stages": {},
    }
    report["source_mode"] = args.source_mode
    report["result_artifacts"] = {
        "source_mode": args.source_mode,
        "input_dir": str(args.image_dir.expanduser().resolve()) if args.source_mode == "images" and args.image_dir else None,
        "png": str(work_dir / "flux2_klein.png") if args.source_mode == "flux" else None,
        "png_metadata": str(work_dir / "flux2_klein_info.json") if args.source_mode == "flux" else None,
        "glb": str(work_dir / "trellis_asset.glb") if args.source_mode == "flux" else None,
        "glb_dir": str(work_dir / "trellis_outputs") if args.source_mode == "images" else None,
        "glbs": [],
        "report": str(report_path),
    }
    env = os.environ.copy()
    env.update({
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    try:
        with _gpu_lock(args.lock_file.expanduser(), args.lock_timeout):
            if args.source_mode == "flux":
                flux_gpu = _select_gpu(python, env, "flux_gpu_admission")
                report["stages"]["flux_gpu_admission"] = {"status": "PASS", "gpu": flux_gpu}
                env_flux = env | {"CUDA_VISIBLE_DEVICES": flux_gpu, "AIEROS_GPU": flux_gpu}
                flux_check = [python, str(FLUX_SCRIPT), "--mode", "check", "--offline", "--gpu", flux_gpu]
                _optional_path_args(flux_check, "--model-cache", args.model_cache)
                report["stages"]["flux_check"] = {"status": "PASS", **_run_stage("flux_check", flux_check, env_flux, 300)}
                cmds = _stage_commands(args, work_dir, flux_gpu)
                report["stages"]["flux_generate"] = {"status": "PASS", **_run_stage(
                    "flux_generate", cmds["flux_generate"], env_flux, args.flux_timeout)}
                png_info = _validate_png(work_dir / "flux2_klein.png", work_dir / "flux2_klein_info.json")
                report["stages"]["png_validation"] = {"status": "PASS", **png_info}
                _emit("png_validation_pass", **png_info)
                input_files = [work_dir / "flux2_klein.png"]
            else:
                input_files = _list_source_images(args.image_dir, args.recursive)
                report["stages"]["input_folder_validation"] = {
                    "status": "PASS", "count": len(input_files),
                    "files": [str(item) for item in input_files],
                    "recursive": bool(args.recursive),
                }
                _emit("input_folder_validation_pass", count=len(input_files), recursive=bool(args.recursive))

            # FLUX must be fully exited before TRELLIS is admitted. In folder mode,
            # only TRELLIS is run and no FLUX model is loaded.
            trellis_gpu = _select_gpu(python, env, "trellis_gpu_admission")
            report["stages"]["trellis_gpu_admission"] = {"status": "PASS", "gpu": trellis_gpu}
            env_trellis = env | {
                "CUDA_VISIBLE_DEVICES": trellis_gpu,
                "AIEROS_TRELLIS_GPU": trellis_gpu,
                "ATTN_BACKEND": args.attention_backend,
                "SPARSE_ATTN_BACKEND": args.attention_backend,
            }
            trellis_check = [python, str(TRELLIS_SCRIPT), "--mode", "check", "--offline",
                             "--gpu", trellis_gpu, "--attention-backend", args.attention_backend]
            _optional_path_args(trellis_check, "--model-cache", args.trellis_model_cache)
            _optional_path_args(trellis_check, "--repo-dir", args.trellis_repo_dir)
            report["stages"]["trellis_check"] = {"status": "PASS", **_run_stage(
                "trellis_check", trellis_check, env_trellis, 300)}

            # The final generation command rechecks attention and cached weights itself.
            if args.source_mode == "flux":
                cmds = _stage_commands(args, work_dir, trellis_gpu)
                trellis_cmd = cmds["trellis_generate"]
                output_dir = work_dir
                expected_glbs = [work_dir / "trellis_asset.glb"]
            else:
                output_dir = work_dir / "trellis_outputs"
                output_dir.mkdir(parents=True, exist_ok=False)
                trellis_cmd = [
                    python, str(TRELLIS_SCRIPT), "--mode", "generate-batch", "--offline",
                    "--scratch-output", "--input-dir", str(args.image_dir.expanduser().resolve()),
                    "--output-dir", str(output_dir), "--gpu", trellis_gpu,
                    "--attention-backend", args.attention_backend,
                    "--max-image-size", str(args.max_image_size),
                    "--decimation-target", str(args.decimation_target),
                    "--texture-size", str(args.texture_size),
                ]
                if args.recursive:
                    trellis_cmd.append("--recursive")
                _optional_path_args(trellis_cmd, "--model-cache", args.trellis_model_cache)
                _optional_path_args(trellis_cmd, "--repo-dir", args.trellis_repo_dir)
                expected_glbs = []

            stage_timeout = args.trellis_timeout * len(input_files) if args.source_mode == "images" else args.trellis_timeout
            report["stages"]["trellis_generate"] = {"status": "PASS", **_run_stage(
                "trellis_generate", trellis_cmd, env_trellis, stage_timeout)}
            if args.source_mode == "flux":
                glb_paths = [work_dir / "trellis_asset.glb"]
            else:
                glb_paths = sorted(output_dir.glob("*.glb"))
                if len(glb_paths) != len(input_files):
                    raise RuntimeError(
                        f"TRELLIS batch output count mismatch: expected {len(input_files)}, found {len(glb_paths)}"
                    )
            glb_infos = []
            for glb_path in glb_paths:
                glb_infos.append(_validate_glb(glb_path))
            report["result_artifacts"]["glbs"] = [str(p) for p in glb_paths]
            report["stages"]["glb_validation"] = {
                "status": "PASS", "count": len(glb_infos), "items": glb_infos,
            }
            if args.source_mode == "flux":
                report["stages"]["glb_validation"].update(glb_infos[0])
            _emit("glb_validation_pass", count=len(glb_infos), glbs=report["result_artifacts"]["glbs"])
        report["status"] = "PASS"
        report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["duration_seconds"] = round(time.monotonic() - started, 3)
        _emit("pipeline_pass", duration_seconds=report["duration_seconds"],
              png=report["result_artifacts"]["png"], glb=report["result_artifacts"]["glb"])
        return report
    except Exception as exc:
        report["status"] = "FAIL" if not str(exc).startswith("BLOCKED_") else "BLOCKED"
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc(limit=15)
        report["failed_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["duration_seconds"] = round(time.monotonic() - started, 3)
        _emit("pipeline_fail", status=report["status"], error=report["error"])
        raise
    finally:
        # Preserve a machine-readable report even if a stage fails.
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["duration_seconds"] = round(time.monotonic() - started, 3)
        try:
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
                                   encoding="utf-8")
            _emit("report_written", path=str(report_path), status=report.get("status"))
        except Exception as report_exc:
            print(f"OEC_PIPELINE_REPORT_WRITE=FAIL {type(report_exc).__name__}: {report_exc}", file=sys.stderr)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not Path(args.python).expanduser().is_file():
        build_parser().error(f"--python is not a file: {args.python}")
    if args.source_mode == "images":
        try:
            _list_source_images(args.image_dir, args.recursive)
        except (ValueError, NotADirectoryError, FileNotFoundError, OSError) as exc:
            build_parser().error(str(exc))
    elif args.image_dir is not None or args.recursive:
        build_parser().error("--image-dir/--recursive require --source-mode images.")
    for name, value, minimum, maximum in (
        ("width", args.width, 256, 1024), ("height", args.height, 256, 1024),
        ("steps", args.steps, 1, 12), ("max-image-size", args.max_image_size, 64, 4096),
        ("decimation-target", args.decimation_target, 1000, 16_000_000),
        ("texture-size", args.texture_size, 256, 8192),
    ):
        if value < minimum or value > maximum:
            build_parser().error(f"--{name} must be in {minimum}..{maximum}")
    if args.width % 64 or args.height % 64:
        build_parser().error("--width and --height must be multiples of 64")
    if args.lock_timeout < 1 or args.flux_timeout < 1 or args.trellis_timeout < 1:
        build_parser().error("timeouts must be positive")
    try:
        report = run_pipeline(args)
        print(json.dumps({"status": report["status"], "report": report["result_artifacts"]["report"],
                          "png": report["result_artifacts"]["png"], "glb": report["result_artifacts"]["glb"]},
                         sort_keys=True), flush=True)
        return 0
    except Exception as exc:
        print(f"OEC_PIPELINE_EXIT=FAIL type={type(exc).__name__} error={exc}", file=sys.stderr, flush=True)
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
