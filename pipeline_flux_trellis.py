#!/usr/bin/env python3
"""Run a serial FLUX→TRELLIS pipeline or process an existing image folder."""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess, sys, time, uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core_config import SYSTEM_DIRS  # noqa: E402
import pipeline_flux_image  # noqa: E402
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work-dir", type=Path)
    p.add_argument("--source-mode", choices=("flux", "images"), default="flux")
    p.add_argument("--image-dir", type=Path)
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--gpu", type=int, default=None)
    p.add_argument("--prompt", default="A photorealistic amber glass sphere on a clean studio surface")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--width", type=int, default=512)
    p.add_argument("--height", type=int, default=512)
    p.add_argument("--steps", type=int, default=4)
    p.add_argument("--guidance-scale", type=float, default=1.0)
    p.add_argument("--max-image-size", type=int, default=1024)
    p.add_argument("--decimation-target", type=int, default=30000)
    p.add_argument("--texture-size", type=int, default=1024)
    p.add_argument("--max-images", type=int, default=20)
    p.add_argument("--report-output", type=Path)
    return p


def _safe_work_dir(requested: Path | None) -> Path:
    if requested is None:
        requested = Path("/tmp") / f"oec-flux-trellis-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    path = requested.expanduser().resolve()
    if not pipeline_flux_image._under(path, Path("/tmp")):
        raise ValueError("work directory must be below /tmp")
    if path.exists():
        raise FileExistsError(f"refusing to reuse existing work directory: {path}")
    path.mkdir(parents=True, exist_ok=False)
    return path


def _image_files(image_dir: Path, recursive: bool, maximum: int) -> list[Path]:
    root = image_dir.expanduser().resolve()
    if image_dir.is_symlink() or not root.is_dir():
        raise ValueError(f"image input directory is not a real directory: {root}")
    candidates = root.rglob("*") if recursive else root.iterdir()
    result = sorted((p for p in candidates if p.is_file() and not p.is_symlink() and p.suffix.lower() in IMAGE_SUFFIXES),
                    key=lambda p: str(p.relative_to(root)).casefold())
    if not result:
        raise ValueError(f"no PNG/JPEG/WebP images found under {root}")
    if len(result) > maximum:
        raise ValueError(f"found {len(result)} images, exceeding bounded maximum {maximum}")
    return result


def _run_child(command: list[str], timeout: int = 2400) -> str:
    print("PIPELINE_CHILD_COMMAND=" + json.dumps(command), flush=True)
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=timeout, check=False)
    if proc.stdout:
        print(proc.stdout[-8000:], end="" if proc.stdout.endswith("\n") else "\n", flush=True)
    if proc.stderr:
        print(proc.stderr[-4000:], file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n", flush=True)
    if proc.returncode:
        raise RuntimeError(f"child process failed with exit code {proc.returncode}")
    return proc.stdout


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _inspect_glb_header(path: Path) -> dict[str, Any]:
    import struct
    raw = path.read_bytes()
    if len(raw) <= 20 or raw[:4] != b"glTF":
        raise RuntimeError(f"invalid or empty GLB: {path}")
    version, declared = struct.unpack_from("<II", raw, 4)
    length, kind = struct.unpack_from("<II", raw, 12)
    if version != 2 or declared != len(raw) or kind != 0x4E4F534A or 20 + length > len(raw):
        raise RuntimeError("GLB version, declared length, or JSON chunk validation failed")
    gltf = json.loads(raw[20:20+length].decode("utf-8").rstrip(" \t\r\n\x00"))
    primitives = [x for mesh in gltf.get("meshes", []) for x in mesh.get("primitives", [])]
    accessors = gltf.get("accessors", [])
    positions, indices = [], []
    for primitive in primitives:
        p = primitive.get("attributes", {}).get("POSITION")
        i = primitive.get("indices")
        if isinstance(p, int) and 0 <= p < len(accessors):
            positions.append(int(accessors[p].get("count", 0)))
        if isinstance(i, int) and 0 <= i < len(accessors):
            indices.append(int(accessors[i].get("count", 0)))
    if not primitives or not any(positions) or not any(indices):
        raise RuntimeError("GLB has no non-empty mesh primitive and accessors")
    return {"path": str(path), "bytes": len(raw), "sha256": _sha256(path), "glb_version": version,
            "mesh_count": len(gltf.get("meshes", [])), "primitive_count": len(primitives),
            "position_accessor_counts": positions, "index_accessor_counts": indices}


def inspect_glb(path: Path) -> dict[str, Any]:
    report = _inspect_glb_header(path)
    import trimesh
    scene = trimesh.load(str(path), force="scene", process=False)
    geometries = [g for g in scene.geometry.values() if hasattr(g, "vertices")]
    vertices = sum(len(g.vertices) for g in geometries)
    faces = sum(len(g.faces) for g in geometries if hasattr(g, "faces"))
    if not geometries or vertices <= 0 or faces <= 0:
        raise RuntimeError("trimesh reopen found no mesh geometry")
    report.update({"trimesh_reopen": "PASS", "trimesh_vertices": vertices, "trimesh_faces": faces})
    return report


def _make_trellis(image: Path, output: Path, gpu: int, args: argparse.Namespace) -> dict[str, Any]:
    script = ROOT / "pipeline_trellis_3d.py"
    if not script.is_file():
        raise FileNotFoundError(f"TRELLIS CLI missing: {script}")
    command = [sys.executable, str(script), "--mode", "generate", "--input", str(image),
               "--output", str(output), "--gpu", str(gpu), "--offline",
               "--max-image-size", str(args.max_image_size),
               "--decimation-target", str(args.decimation_target), "--texture-size", str(args.texture_size)]
    _run_child(command, timeout=2400)
    if not output.is_file():
        raise RuntimeError(f"TRELLIS did not produce the expected GLB: {output}")
    result = inspect_glb(output)
    print("FLUX_TRELLIS_ARTIFACT=" + json.dumps(result, sort_keys=True), flush=True)
    return result


def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    a = p.parse_args(argv)
    if a.source_mode == "images" and a.image_dir is None:
        p.error("--image-dir is required when --source-mode images")
    if a.source_mode == "flux" and (a.image_dir is not None or a.recursive):
        p.error("--image-dir/--recursive require --source-mode images")
    if not 1 <= a.max_images <= 100:
        p.error("--max-images must be between 1 and 100")
    if not 256 <= a.max_image_size <= 2048 or a.decimation_target < 1000 or not 256 <= a.texture_size <= 8192:
        p.error("image size, decimation target or texture size is outside the allowed range")
    pipeline_flux_image._validate(a.prompt, a.width, a.height, a.steps, a.guidance_scale)
    work = _safe_work_dir(a.work_dir)
    gpu_row = pipeline_flux_image.select_idle_a100_gpu(a.gpu)
    gpu = int(gpu_row["index"])
    start = time.monotonic()
    tag = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    out_root = Path(SYSTEM_DIRS["outputs"]).expanduser().resolve() / "media_services" / "flux-trellis" / "jobs" / tag
    sources: list[dict[str, Any]] = []
    if a.source_mode == "flux":
        image = work / "flux-source.png"
        command = [sys.executable, str(ROOT / "pipeline_flux_image.py"), "--mode", "generate",
                   "--offline", "--scratch-output", "--gpu", str(gpu), "--output", str(image),
                   "--prompt", a.prompt, "--seed", str(a.seed), "--width", str(a.width),
                   "--height", str(a.height), "--steps", str(a.steps), "--guidance-scale", str(a.guidance_scale)]
        _run_child(command, timeout=1800)
        if not image.is_file() or image.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("FLUX exited without a valid PNG")
        inputs = [image]
        sources.append({"provider": "flux", "path": str(image), "bytes": image.stat().st_size,
                        "sha256": _sha256(image), "prompt": a.prompt, "seed": a.seed})
    else:
        inputs = _image_files(a.image_dir, a.recursive, a.max_images)
        sources.extend({"provider": "existing-image", "path": str(x), "bytes": x.stat().st_size, "sha256": _sha256(x)}
                       for x in inputs)
    records = []
    for n, image in enumerate(inputs, start=1):
        stem = re.sub(r"[^A-Za-z0-9_-]+", "-", image.stem).strip("-_")[:48] or "image"
        output = out_root / f"{n:03d}-{stem}.glb"
        records.append({"input": str(image), "output": _make_trellis(image, output, gpu, a)})
    report = {"schema_version": 1, "status": "PASS" if records else "FAIL", "source_mode": a.source_mode,
              "gpu": gpu_row, "model_flux": pipeline_flux_image.MODEL_ID, "model_trellis": "microsoft/TRELLIS.2-4B",
              "elapsed_seconds": round(time.monotonic()-start, 3), "sources": sources, "artifacts": records,
              "output_root": str(out_root), "limitations": [
                  "Bounded inference and artifact integrity only; mesh semantic correctness and watertightness were not measured.",
                  "Existing image inputs are not modified or deleted."]}
    report_path = a.report_output.expanduser().resolve() if a.report_output else work / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print("FLUX_TRELLIS_PIPELINE_REPORT=" + str(report_path), flush=True)
    print("FLUX_TRELLIS_PIPELINE_STATUS=" + report["status"], flush=True)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
