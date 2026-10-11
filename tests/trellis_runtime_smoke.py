"""Offline TRELLIS.2 image-to-3D smoke test; outputs and caches stay in node-local scratch."""
from __future__ import annotations

import gc
import os
from pathlib import Path
import sys
import traceback


def load_path_env() -> dict[str, str]:
    path_keys = {
        "AIEROS_BASE_DIR", "AIEROS_MODELS_DIR", "AIEROS_DATASETS_DIR",
        "AIEROS_CACHE_DIR", "AIEROS_OUTPUTS_DIR", "AIEROS_INPUTS_DIR",
        "AIEROS_LOGS_DIR",
    }
    result: dict[str, str] = {}
    env_path = Path.home() / ".env"
    if env_path.is_file():
        for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in path_keys:
                value = value.strip().strip("'").strip('"')
                result[key] = os.path.expanduser(os.path.expandvars(value))
    return result


def main() -> int:
    path_env = load_path_env()
    base_dir = path_env.get("AIEROS_BASE_DIR", str(Path.home()))
    model_root = Path(os.environ.get(
        "AIEROS_TEST_MODEL_ROOT",
        path_env.get("AIEROS_MODELS_DIR", str(Path(base_dir) / "aireos_models"))
    )).expanduser().resolve()
    trellis_repo = model_root / "TRELLIS.2"
    if not (trellis_repo / "setup.sh").is_file():
        raise FileNotFoundError(f"TRELLIS.2 repository not found: {trellis_repo}")

    scratch = Path(os.environ.get("TRELLIS_SMOKE_DIR", "/tmp/trellis-runtime-smoke")).resolve()
    if not str(scratch).startswith("/tmp/"):
        raise RuntimeError(f"Smoke output must stay under /tmp: {scratch}")
    scratch.mkdir(parents=True, exist_ok=True)
    outdir = scratch / "output"
    outdir.mkdir(parents=True, exist_ok=True)

    # Keep every inference cache and output outside shared model/output directories.
    os.environ["HF_HOME"] = str(model_root)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(model_root / "hub")
    os.environ["HF_HUB_CACHE"] = str(model_root / "hub")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TRELLIS_CACHE_DIR"] = str(scratch / "trellis-cache")
    os.environ["TORCH_EXTENSIONS_DIR"] = str(scratch / "torch-extensions")
    os.environ["TRITON_CACHE_DIR"] = str(scratch / "triton")
    os.environ["CUDA_CACHE_PATH"] = str(scratch / "cuda-cache")
    os.environ["XDG_CACHE_HOME"] = str(scratch / "xdg-cache")
    os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    os.environ["ATTN_BACKEND"] = "xformers"
    os.environ["SPARSE_ATTN_BACKEND"] = "xformers"
    sys.path.insert(0, str(trellis_repo))

    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available in phase2_3d")
    print(f"TRELLIS_SMOKE_GPU={torch.cuda.get_device_name(0)}")
    print(f"TRELLIS_SMOKE_TORCH={torch.__version__} CUDA={torch.version.cuda}")

    import xformers
    import xformers.ops as xops
    print(f"TRELLIS_SMOKE_XFORMERS={getattr(xformers, '__version__', 'unknown')}")
    probe = torch.zeros((1, 2, 1, 64), device="cuda", dtype=torch.float16)
    xops.memory_efficient_attention(probe, probe, probe)
    del probe
    print("XFORMERS_CUDA_ATTENTION=PASS")

    from huggingface_hub import snapshot_download
    snapshot = snapshot_download(
        repo_id="microsoft/TRELLIS.2-4B",
        cache_dir=str(model_root / "hub"),
        local_files_only=True,
    )
    print(f"TRELLIS_LOCAL_SNAPSHOT={snapshot}")
    from trellis2.pipelines import Trellis2ImageTo3DPipeline
    import o_voxel
    import trimesh
    from PIL import Image, ImageDraw

    print(f"TRELLIS_SMOKE_REPO={trellis_repo}")
    print(f"TRELLIS_SMOKE_HF_CACHE={model_root / 'hub'}")
    print(f"TRELLIS_SMOKE_OUTPUT_DIR={outdir}")

    import time
    started = time.time()
    pipe = Trellis2ImageTo3DPipeline.from_pretrained(snapshot)
    pipe.cuda()
    print(f"TRELLIS_PIPELINE_LOAD_SECONDS={time.time() - started:.1f}")

    image = Image.new("RGB", (512, 512), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((160, 140, 350, 360), fill=(45, 110, 190), outline=(20, 45, 80), width=8)
    draw.ellipse((160, 110, 350, 175), fill=(70, 145, 220), outline=(20, 45, 80), width=8)
    draw.ellipse((160, 325, 350, 380), fill=(30, 80, 150), outline=(20, 45, 80), width=8)

    started = time.time()
    with torch.inference_mode():
        meshes = pipe.run(image)
    print(f"TRELLIS_INFERENCE_SECONDS={time.time() - started:.1f}")
    if not meshes:
        raise RuntimeError("TRELLIS pipeline returned no mesh")
    mesh = meshes[0]
    print(f"TRELLIS_MESH_VERTICES={len(mesh.vertices)}")
    print(f"TRELLIS_MESH_FACES={len(mesh.faces)}")

    started = time.time()
    glb = o_voxel.postprocess.to_glb(
        vertices=mesh.vertices, faces=mesh.faces, attr_volume=mesh.attrs,
        coords=mesh.coords, attr_layout=mesh.layout, voxel_size=mesh.voxel_size,
        aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
        decimation_target=100000, texture_size=512,
        remesh=True, remesh_band=1, remesh_project=0, verbose=False,
    )
    output_path = outdir / "trellis-generated-asset.glb"
    glb.export(str(output_path), extension_webp=True)
    print(f"TRELLIS_GLB_EXPORT_SECONDS={time.time() - started:.1f}")
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise RuntimeError("GLB output is missing or empty")

    loaded_scene = trimesh.load(str(output_path), force="scene")
    if not loaded_scene.geometry:
        raise RuntimeError("Exported GLB contains no geometry when reopened")
    vertices = sum(len(g.vertices) for g in loaded_scene.geometry.values() if hasattr(g, "vertices"))
    faces = sum(len(g.faces) for g in loaded_scene.geometry.values() if hasattr(g, "faces"))
    if vertices <= 0 or faces <= 0:
        raise RuntimeError(f"Invalid reopened GLB geometry: vertices={vertices}, faces={faces}")
    print(f"TRELLIS_GLB_BYTES={output_path.stat().st_size}")
    print(f"TRELLIS_GLB_REOPEN_GEOMETRIES={len(loaded_scene.geometry)}")
    print(f"TRELLIS_GLB_REOPEN_VERTICES={vertices}")
    print(f"TRELLIS_GLB_REOPEN_FACES={faces}")
    print("TRELLIS_IMAGE_TO_3D_SMOKE=PASS")

    del loaded_scene, glb, mesh, meshes, pipe
    gc.collect()
    torch.cuda.empty_cache()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"TRELLIS_IMAGE_TO_3D_SMOKE=FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        raise
