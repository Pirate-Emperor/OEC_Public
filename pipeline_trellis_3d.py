#!/usr/bin/env python3
"""Standalone TRELLIS.2 image-to-3D entry point for OEC.

Examples:
  python pipeline_trellis_3d.py --mode check --gpu 0
  python pipeline_trellis_3d.py --mode gradio --gpu 0 --port 7862
  python pipeline_trellis_3d.py --mode generate --gpu 0 --input concept.png
"""
from __future__ import annotations

import argparse
import gc
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run TRELLIS.2 as a Gradio 3D viewer or generate a GLB from an image."
    )
    parser.add_argument(
        "--mode", choices=("gradio", "generate", "check"), default="gradio",
        help="gradio launches the UI (default); generate processes --input; check validates runtime without loading model weights.",
    )
    parser.add_argument("--input", type=Path, help="Input image for --mode generate.")
    parser.add_argument("--output", type=Path, help="Exact GLB output path for --mode generate.")
    parser.add_argument("--output-dir", type=Path, help="Output folder; defaults to SYSTEM_DIRS outputs/3d_models.")
    parser.add_argument("--model-id", default="microsoft/TRELLIS.2-4B", help="Hugging Face model repository ID.")
    parser.add_argument("--model-cache", type=Path, help="Hugging Face cache directory; defaults to SYSTEM_DIRS models/hub.")
    parser.add_argument("--repo-dir", type=Path, help="TRELLIS.2 source checkout; defaults to SYSTEM_DIRS models/TRELLIS.2.")
    parser.add_argument("--gpu", default=os.environ.get("AIEROS_TRELLIS_GPU"), help="GPU index to expose before importing torch. Leaves CUDA_VISIBLE_DEVICES unchanged when omitted.")
    parser.add_argument("--attention-backend", choices=("xformers", "flash_attn"), default=os.environ.get("AIEROS_TRELLIS_ATTN_BACKEND", "xformers"))
    parser.add_argument("--offline", action="store_true", help="Do not download a missing model snapshot.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("AIEROS_TRELLIS_PORT", "7862")), help="Gradio port.")
    parser.add_argument("--server-name", default=os.environ.get("AIEROS_TRELLIS_SERVER_NAME", "0.0.0.0"), help="Interface to bind; use an SSH tunnel and keep share disabled on shared nodes.")
    parser.add_argument("--share", action="store_true", help="Explicitly enable a public Gradio share URL. Not recommended on shared compute.")
    parser.add_argument("--inbrowser", action="store_true", help="Ask Gradio to open a browser on the compute node.")
    parser.add_argument("--max-image-size", type=int, default=1024, help="Maximum input dimension before TRELLIS preprocessing.")
    parser.add_argument("--decimation-target", type=int, default=100_000, help="Target triangle count for GLB mesh processing.")
    parser.add_argument("--texture-size", type=int, default=2048, help="GLB texture size; 2048 is a VRAM/time-conscious default.")
    return parser


def _prepare_environment(args: argparse.Namespace) -> None:
    # GPU visibility must be chosen before importing torch or a CUDA extension.
    if args.gpu is not None:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(args.gpu)
        os.environ["AIEROS_TRELLIS_GPU"] = str(args.gpu)
    os.environ.setdefault("no_proxy", "localhost,127.0.0.1,::1")
    os.environ.setdefault("NO_PROXY", os.environ["no_proxy"])
    os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    os.environ["ATTN_BACKEND"] = args.attention_backend
    os.environ["SPARSE_ATTN_BACKEND"] = args.attention_backend


def _imports_and_probe(args: argparse.Namespace) -> dict[str, Any]:
    _prepare_environment(args)

    # Core configuration resolves the user's existing .env paths and proxy/auth setup.
    import core_config
    from core_config import SYSTEM_DIRS
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is not available. Select the phase2_3d kernel/environment and verify nvidia-smi."
        )
    print(f"TRELLIS_DEVICE={torch.cuda.get_device_name(0)}")
    print(f"TRELLIS_TORCH={torch.__version__} CUDA={torch.version.cuda}")

    if args.attention_backend == "xformers":
        try:
            import xformers
            import xformers.ops as xops

            probe = torch.zeros((1, 2, 1, 64), device="cuda", dtype=torch.float16)
            xops.memory_efficient_attention(probe, probe, probe)
            del probe
            print(f"TRELLIS_XFORMERS={getattr(xformers, '__version__', 'unknown')} ATTENTION_PROBE=PASS")
        except Exception as exc:
            raise RuntimeError(
                "xFormers CUDA attention is incompatible with the active torch/CUDA build. "
                "Run the guarded TRELLIS setup cell or install the matching wheel in phase2_3d."
            ) from exc
    else:
        try:
            import flash_attn  # noqa: F401
            print("TRELLIS_FLASH_ATTN_IMPORT=PASS")
        except Exception as exc:
            raise RuntimeError(
                "The requested flash_attn backend is not importable in this environment."
            ) from exc

    repo_dir = Path(
        args.repo_dir
        or os.environ.get(
            "AIEROS_TRELLIS_REPO_DIR",
            str(Path(SYSTEM_DIRS["models"]) / "TRELLIS.2"),
        )
    ).expanduser().resolve()
    if repo_dir.is_dir() and str(repo_dir) not in sys.path:
        sys.path.insert(0, str(repo_dir))

    try:
        from trellis2.pipelines import Trellis2ImageTo3DPipeline  # noqa: F401
        import o_voxel  # noqa: F401
    except Exception as exc:
        raise RuntimeError(
            f"TRELLIS runtime imports failed. Confirm the TRELLIS.2 checkout and its native "
            f"extensions are installed. Expected source path: {repo_dir}"
        ) from exc

    from huggingface_hub import snapshot_download
    try:
        from huggingface_hub.errors import LocalEntryNotFoundError
    except ImportError:
        from huggingface_hub.utils import LocalEntryNotFoundError

    cache_dir = Path(
        args.model_cache or (Path(SYSTEM_DIRS["models"]) / "hub")
    ).expanduser().resolve()
    try:
        snapshot = snapshot_download(
            repo_id=args.model_id,
            cache_dir=str(cache_dir),
            local_files_only=True,
        )
        cache_available = True
        print(f"TRELLIS_MODEL_CACHE=HIT snapshot={snapshot}")
    except LocalEntryNotFoundError:
        cache_available = False
        snapshot = None
        print(f"TRELLIS_MODEL_CACHE=MISS cache_dir={cache_dir}")

    return {
        "core_config": core_config,
        "system_dirs": SYSTEM_DIRS,
        "torch": torch,
        "pipeline_class": Trellis2ImageTo3DPipeline,
        "o_voxel": o_voxel,
        "snapshot_download": snapshot_download,
        "cache_miss_error": LocalEntryNotFoundError,
        "cache_dir": cache_dir,
        "snapshot": snapshot,
        "cache_available": cache_available,
    }


def _resolve_snapshot(args: argparse.Namespace, runtime: dict[str, Any]) -> Path:
    if runtime["cache_available"]:
        return Path(runtime["snapshot"])

    if args.offline:
        raise RuntimeError(
            f"Model {args.model_id!r} is not cached in {runtime['cache_dir']}. "
            "Run without --offline only when OEC StorageManager confirms configured allocation and filesystem headroom."
        )

    from storage_manager import managed_storage_operation, storage_preflight
    from storage_policy import BYTES_PER_GB, estimate_hf_repo_bytes

    safety_gb = max(0.0, float(os.environ.get("AIEROS_MODEL_DOWNLOAD_SAFETY_GB", "2.0")))
    required_gb = estimate_hf_repo_bytes(args.model_id) / BYTES_PER_GB + safety_gb
    minimum_free_gb = max(0.0, float(os.environ.get("AIEROS_MODEL_MIN_FREE_GB", "2.0")))
    ok, reason = storage_preflight(
        "models",
        required_gb=required_gb,
        require_fresh_quota=False,
        minimum_free_gb=minimum_free_gb,
    )
    if not ok:
        raise RuntimeError(f"TRELLIS model download denied by storage policy: {reason}")

    with managed_storage_operation(
        "models",
        required_gb=required_gb,
        require_fresh_quota=False,
        minimum_free_gb=minimum_free_gb,
    ):
        snapshot = runtime["snapshot_download"](
            repo_id=args.model_id,
            cache_dir=str(runtime["cache_dir"]),
        )
    print(f"TRELLIS_MODEL_DOWNLOAD=PASS snapshot={snapshot}")
    return Path(snapshot)


def _load_pipeline(args: argparse.Namespace, runtime: dict[str, Any]) -> Any:
    snapshot = _resolve_snapshot(args, runtime)
    pipeline = runtime["pipeline_class"].from_pretrained(str(snapshot))
    pipeline.cuda()
    print(f"TRELLIS_PIPELINE_LOAD=PASS model={args.model_id}")
    return pipeline


def _prepare_image(image: Any, max_size: int) -> Any:
    from PIL import Image

    if image is None:
        raise ValueError("Provide an input image first.")
    image = image.convert("RGB")
    width, height = image.size
    longest = max(width, height)
    if longest > max_size:
        scale = max_size / float(longest)
        width = max(1, int(round(width * scale)))
        height = max(1, int(round(height * scale)))
        image = image.resize((width, height), Image.Resampling.LANCZOS)

    # TRELLIS.2 performs more consistently with a square canvas aligned to 64 pixels.
    square_size = max(64, ((max(width, height) + 63) // 64) * 64)
    square = Image.new("RGB", (square_size, square_size), (255, 255, 255))
    square.paste(image, ((square_size - width) // 2, (square_size - height) // 2))
    return square


def generate_glb(
    image: Any,
    pipeline: Any,
    o_voxel: Any,
    system_dirs: dict[str, str],
    output_dir: Path | None,
    output_path: Path | None,
    max_image_size: int,
    decimation_target: int,
    texture_size: int,
) -> str:
    from storage_manager import managed_storage_operation
    import torch

    if decimation_target < 1_000:
        raise ValueError("decimation_target must be at least 1000 triangles.")
    if texture_size < 256 or texture_size > 8192:
        raise ValueError("texture_size must be between 256 and 8192.")

    prepared = _prepare_image(image, max_image_size)
    with torch.inference_mode():
        meshes = pipeline.run(prepared)
    if not meshes:
        raise RuntimeError("TRELLIS returned no mesh for this image.")
    mesh = meshes[0]

    if output_path is None:
        destination_dir = output_dir or (Path(system_dirs["outputs"]) / "3d_models")
        destination_dir = Path(destination_dir).expanduser().resolve()
        filename = f"trellis2_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.glb"
        destination = destination_dir / filename
    else:
        destination = Path(output_path).expanduser().resolve()
        destination_dir = destination.parent

    destination_dir.mkdir(parents=True, exist_ok=True)
    glb = o_voxel.postprocess.to_glb(
        vertices=mesh.vertices,
        faces=mesh.faces,
        attr_volume=mesh.attrs,
        coords=mesh.coords,
        attr_layout=mesh.layout,
        voxel_size=mesh.voxel_size,
        aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
        decimation_target=int(decimation_target),
        texture_size=int(texture_size),
        remesh=True,
        remesh_band=1,
        remesh_project=0,
        verbose=False,
    )
    # Managed output operation keeps the existing storage policy in force.
    with managed_storage_operation(
        "outputs",
        required_gb=0.20,
        require_fresh_quota=False,
        minimum_free_gb=0.05,
    ):
        glb.export(str(destination), extension_webp=True)

    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"GLB export did not create a non-empty file: {destination}")
    print(f"TRELLIS_GLB={destination} BYTES={destination.stat().st_size}")
    del mesh, glb, meshes
    gc.collect()
    torch.cuda.empty_cache()
    return str(destination)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "generate" and args.input is None:
        build_parser().error("--input is required when --mode generate")
    if args.mode == "generate" and not args.input.is_file():
        build_parser().error(f"input file does not exist: {args.input}")
    if args.port < 1 or args.port > 65535:
        build_parser().error("--port must be between 1 and 65535")

    _prepare_environment(args)
    runtime = _imports_and_probe(args)

    if args.mode == "check":
        print("TRELLIS_RUNTIME_CHECK=PASS")
        if runtime["cache_available"]:
            print("TRELLIS_READY=PASS")
        else:
            print("TRELLIS_READY=DEPENDENCY_CHECK_PASS_MODEL_CACHE_MISS")
            print("A guarded model download is required before inference unless run with a pre-populated cache.")
        return 0

    pipeline = _load_pipeline(args, runtime)
    if args.mode == "generate":
        from PIL import Image

        with Image.open(args.input) as opened:
            image = opened.copy()
        result = generate_glb(
            image=image,
            pipeline=pipeline,
            o_voxel=runtime["o_voxel"],
            system_dirs=runtime["system_dirs"],
            output_dir=args.output_dir,
            output_path=args.output,
            max_image_size=args.max_image_size,
            decimation_target=args.decimation_target,
            texture_size=args.texture_size,
        )
        print(f"TRELLIS_GENERATION=PASS output={result}")
        return 0

    import gradio as gr

    def gradio_generate(
        input_image: Any,
        decimation_target: int,
        texture_size: int,
        max_image_size: int,
    ) -> tuple[str, str]:
        try:
            result = generate_glb(
                image=input_image,
                pipeline=pipeline,
                o_voxel=runtime["o_voxel"],
                system_dirs=runtime["system_dirs"],
                output_dir=args.output_dir,
                output_path=None,
                max_image_size=int(max_image_size),
                decimation_target=int(decimation_target),
                texture_size=int(texture_size),
            )
            return result, result
        except Exception as exc:
            raise gr.Error(f"TRELLIS generation failed: {type(exc).__name__}: {exc}") from exc

    with gr.Blocks(title="OEC TRELLIS.2", theme=gr.themes.Monochrome()) as demo:
        gr.Markdown(
            "# OEC TRELLIS.2 Image-to-3D\n"
            "Upload one image, generate a textured GLB, and inspect it in the interactive viewer. "
            "Use an SSH tunnel to reach this interface; public sharing is disabled unless explicitly requested."
        )
        with gr.Row():
            with gr.Column(scale=1):
                input_image = gr.Image(label="Input image", type="pil")
                decimation_target = gr.Slider(
                    label="Target triangle count",
                    minimum=10_000,
                    maximum=500_000,
                    value=args.decimation_target,
                    step=10_000,
                )
                texture_size = gr.Dropdown(
                    label="Texture resolution",
                    choices=[512, 1024, 2048, 4096],
                    value=args.texture_size,
                )
                max_image_size = gr.Dropdown(
                    label="Maximum input dimension",
                    choices=[512, 768, 1024, 1280],
                    value=args.max_image_size,
                )
                generate_button = gr.Button("Generate 3D model", variant="primary")
            with gr.Column(scale=2):
                output_3d = gr.Model3D(label="Interactive GLB viewer")
                output_file = gr.File(label="Download GLB")
        generate_button.click(
            fn=gradio_generate,
            inputs=[input_image, decimation_target, texture_size, max_image_size],
            outputs=[output_3d, output_file],
        )

    demo.queue()
    print(
        f"TRELLIS_GRADIO_START=PASS host={args.server_name} port={args.port} "
        f"share={bool(args.share)} output={args.output_dir or Path(runtime['system_dirs']['outputs']) / '3d_models'}"
    )
    demo.launch(
        server_name=args.server_name,
        server_port=args.port,
        share=args.share,
        inbrowser=args.inbrowser,
        show_error=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
