"""Offline TRELLIS.2 image-to-3D smoke test; writes only to verified node-local scratch."""

from __future__ import annotations

import gc
import os
from pathlib import Path
import sys
import traceback

from PIL import Image, ImageDraw


def main() -> int:
    model_root = Path(os.environ.get("AIEROS_MODELS_DIR", "~/aireos_models")).expanduser()
    trellis_repo = model_root / "TRELLIS.2"
    if not (trellis_repo / "setup.sh").is_file():
        raise FileNotFoundError(f"TRELLIS.2 repository not found: {trellis_repo}")

    scratch = Path(os.environ.get("TRELLIS_SMOKE_DIR", "/tmp/trellis-runtime-smoke")).resolve()
    if not str(scratch).startswith("/tmp/"):
        raise RuntimeError(f"Smoke output must stay under /tmp: {scratch}")
    scratch.mkdir(parents=True, exist_ok=True)
    os.environ["TRELLIS_CACHE_DIR"] = str(scratch / "cache")
    os.environ["HF_HOME"] = str(model_root)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(model_root / "hub")
    os.environ["TRANSFORMERS_CACHE"] = str(model_root)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["ATTN_BACKEND"] = "xformers"
    os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    sys.path.insert(0, str(trellis_repo))

    import torch
    import o_voxel
    from trellis2.pipelines import Trellis2ImageTo3DPipeline

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available in phase2_3d")
    print(f"TRELLIS_SMOKE_GPU={torch.cuda.get_device_name(0)}")
    print(f"TRELLIS_SMOKE_TORCH={torch.__version__} CUDA={torch.version.cuda}")
    print(f"TRELLIS_SMOKE_REPO={trellis_repo}")
    print(f"TRELLIS_SMOKE_HF_CACHE={model_root / 'hub'}")
    print(f"TRELLIS_SMOKE_OUTPUT_DIR={scratch}")

    pipe = Trellis2ImageTo3DPipeline.from_pretrained(
        "microsoft/TRELLIS.2-4B",
        local_files_only=True,
    )
    pipe.cuda()

    # Deterministic synthetic input; no private/user image is required.
    image = Image.new("RGB", (512, 512), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((160, 140, 350, 360), fill=(45, 110, 190), outline=(20, 45, 80), width=8)
    draw.ellipse((160, 110, 350, 175), fill=(70, 145, 220), outline=(20, 45, 80), width=8)
    draw.ellipse((160, 325, 350, 380), fill=(30, 80, 150), outline=(20, 45, 80), width=8)

    with torch.inference_mode():
        meshes = pipe.run(image)
    if not meshes:
        raise RuntimeError("TRELLIS pipeline returned no mesh")
    mesh = meshes[0]
    print(f"TRELLIS_MESH_VERTICES={len(mesh.vertices)}")
    print(f"TRELLIS_MESH_FACES={len(mesh.faces)}")

    glb = o_voxel.postprocess.to_glb(
        vertices=mesh.vertices,
        faces=mesh.faces,
        attr_volume=mesh.attrs,
        coords=mesh.coords,
        attr_layout=mesh.layout,
        voxel_size=mesh.voxel_size,
        aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
        decimation_target=10000,
        texture_size=512,
        remesh=True,
        remesh_band=1,
        remesh_project=0,
        verbose=False,
    )
    output_path = scratch / "trellis-smoke.glb"
    glb.export(str(output_path), extension_webp=True)
    assert output_path.is_file() and output_path.stat().st_size > 0, "GLB output is missing or empty"
    print(f"TRELLIS_GLB_BYTES={output_path.stat().st_size}")
    print("TRELLIS_IMAGE_TO_3D_SMOKE=PASS")

    del glb, mesh, meshes, pipe
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
