#!/usr/bin/env python3
"""Safe FLUX.2 Klein image-generation CLI and optional Gradio UI."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import gc
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from typing import Any

MODEL_ID = "black-forest-labs/FLUX.2-klein-4B"
REQUIRED_PACKAGE_VERSIONS = {
    "diffusers": "0.37.0",
    "huggingface-hub": "0.36.0",
    "transformers": "4.56.1",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate FLUX.2 Klein images from text or an optional source image.")
    parser.add_argument("--mode", choices=("check", "generate", "gradio"), default="gradio")
    parser.add_argument("--prompt", default="A sci-fi crate in a clean studio photograph")
    parser.add_argument("--input", type=Path, help="Optional reference image.")
    parser.add_argument("--output", type=Path, help="Exact PNG output path.")
    parser.add_argument("--output-dir", type=Path, help="Managed output folder; defaults to SYSTEM_DIRS/outputs/images.")
    parser.add_argument("--model-id", default=MODEL_ID)
    parser.add_argument("--model-cache", type=Path, help="Model cache root; defaults to SYSTEM_DIRS['models'].")
    parser.add_argument("--gpu", default=os.environ.get("AIEROS_GPU"), help="Physical GPU index; applied before importing torch.")
    parser.add_argument("--offline", action="store_true", help="Require local cached weights; do not download the model.")
    parser.add_argument("--scratch-output", action="store_true", help="Write to verified local scratch distinct from model storage.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--randomize-seed", action="store_true")
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--guidance-scale", type=float, default=1.0)
    parser.add_argument("--port", type=int, default=int(os.environ.get("AIEROS_FLUX_GRADIO_PORT", "7864")))
    parser.add_argument("--server-name", default=os.environ.get("AIEROS_FLUX_SERVER_NAME", "0.0.0.0"))
    parser.add_argument("--share", action="store_true", help="Explicitly enable a public Gradio share link.")
    return parser


def _prepare_gpu(gpu: str | None) -> str | None:
    """Choose GPU visibility before torch import; preserve scheduler visibility otherwise."""
    selected = gpu or os.environ.get("AIEROS_GPU")
    if selected is not None:
        selected = str(selected).strip()
        if not selected.isdigit():
            raise ValueError(f"--gpu/AIEROS_GPU must be a physical GPU index, got {selected!r}")
        os.environ["CUDA_VISIBLE_DEVICES"] = selected
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    return selected


def _system_dirs() -> dict[str, str]:
    import core_config
    from core_config import SYSTEM_DIRS
    return {k: str(v) for k, v in SYSTEM_DIRS.items()}


def _version_report() -> dict[str, dict[str, str | None]]:
    report = {}
    for package, required in REQUIRED_PACKAGE_VERSIONS.items():
        try:
            installed = metadata.version(package)
        except metadata.PackageNotFoundError:
            installed = None
        report[package] = {"installed": installed, "required": required}
    return report


def _assert_dependencies() -> dict[str, dict[str, str | None]]:
    versions = _version_report()
    mismatches = {name: row for name, row in versions.items() if row["installed"] != row["required"]}
    if mismatches:
        raise RuntimeError(
            "BLOCKED_FLUX_DEPENDENCIES: installed versions differ from the tested stack: "
            + json.dumps(mismatches, sort_keys=True)
            + ". Run the guarded notebook dependency cell and restart this kernel; do not pip-install during inference."
        )
    return versions


def _cache_roots(model_cache: str | Path) -> list[Path]:
    root = Path(model_cache).expanduser()
    roots = []
    seen = set()
    for candidate in (root, root / "hub", Path.home() / ".cache" / "huggingface" / "hub"):
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_dir() and resolved not in seen:
            roots.append(resolved)
            seen.add(resolved)
    return roots


def _valid_flux_snapshot(path: Path) -> bool:
    try:
        index = json.loads((path / "model_index.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(index, dict) or index.get("_class_name") not in {"Flux2KleinPipeline", "DiffusionPipeline"}:
        return False
    try:
        return any(p.is_file() and p.stat().st_size > 0 for p in path.rglob("*.safetensors"))
    except OSError:
        return False


def find_cached_snapshot(model_id: str, model_cache: str | Path) -> Path | None:
    """Resolve a complete cached snapshot without a Hub/network lookup."""
    repo = "models--" + model_id.replace("/", "--")
    candidates = []
    for root in _cache_roots(model_cache):
        snapshot_root = root / repo / "snapshots"
        if not snapshot_root.is_dir():
            continue
        for snap in snapshot_root.iterdir():
            if snap.is_dir() and _valid_flux_snapshot(snap):
                try:
                    size = sum(p.stat().st_size for p in snap.rglob("*.safetensors") if p.is_file())
                except OSError:
                    continue
                candidates.append((size, snap.resolve()))
    return max(candidates, key=lambda x: x[0])[1] if candidates else None


def _same_filesystem(path_a: Path, path_b: Path) -> bool:
    def nearest_existing(path: Path) -> Path:
        current = path.expanduser().resolve()
        while not current.exists() and current.parent != current:
            current = current.parent
        return current
    a, b = nearest_existing(path_a), nearest_existing(path_b)
    try:
        if a.stat().st_dev == b.stat().st_dev:
            return True
    except OSError:
        return True
    findmnt = shutil.which("findmnt")
    if findmnt:
        def mount_info(path: Path):
            p = subprocess.run([findmnt, "-T", str(path), "-n", "-o", "TARGET,SOURCE"],
                               text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               timeout=10, check=False)
            pieces = p.stdout.strip().split()
            return (pieces[0], pieces[1]) if p.returncode == 0 and len(pieces) >= 2 else None
        ma, mb = mount_info(a), mount_info(b)
        if ma and mb and (ma[0] == mb[0] or ma[1] == mb[1]):
            return True
    return False


def validate_scratch_path(
    output_path: str | Path,
    model_cache: str | Path,
    minimum_free_mib: int = 512,
) -> Path:
    """Allow only new scratch under a temp root with headroom and separate storage."""
    target = Path(output_path).expanduser().resolve()
    roots = [Path("/tmp"), Path(tempfile.gettempdir())]
    for key in ("RUNNER_TEMP", "TMPDIR"):
        if os.environ.get(key):
            roots.append(Path(os.environ[key]))
    if not any(_is_relative_to(target, root) for root in roots):
        raise RuntimeError("BLOCKED_SCRATCH_OUTPUT: use a path under /tmp or runner-local temporary storage.")
    if target.exists() or target.with_name(target.stem + "_info.json").exists():
        raise FileExistsError(f"BLOCKED_SCRATCH_OUTPUT: refusing to overwrite an existing PNG/metadata file: {target}")
    if _same_filesystem(target.parent, Path(model_cache)):
        raise RuntimeError("BLOCKED_SCRATCH_OUTPUT: temporary output filesystem is not distinct from shared model storage.")

    probe = target.parent
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        free_bytes = shutil.disk_usage(probe).free
    except OSError as exc:
        raise RuntimeError(f"BLOCKED_SCRATCH_OUTPUT: cannot measure scratch capacity: {exc}") from exc
    required_bytes = max(1, int(minimum_free_mib)) * 1024 * 1024
    if free_bytes < required_bytes:
        raise RuntimeError(
            f"BLOCKED_SCRATCH_OUTPUT: temporary filesystem has {free_bytes} free bytes; "
            f"need at least {required_bytes} bytes."
        )
    return target


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.expanduser().resolve())
        return True
    except (OSError, ValueError):
        return False


def validate_png_file(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file() or target.stat().st_size <= len(PNG_SIGNATURE):
        raise RuntimeError(f"FLUX PNG export missing or empty: {target}")
    with target.open("rb") as handle:
        if handle.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
            raise RuntimeError(f"FLUX export has an invalid PNG signature: {target}")
    return {"path": str(target), "bytes": target.stat().st_size}


@contextmanager
def _offline_hub():
    names = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY")
    old = {name: os.environ.get(name) for name in names}
    os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"})
    try:
        yield
    finally:
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _resolve_snapshot(model_id: str, model_cache: Path, offline: bool) -> Path:
    snapshot = find_cached_snapshot(model_id, model_cache)
    if snapshot is not None:
        print(f"FLUX_CACHE=HIT snapshot={snapshot}", flush=True)
        return snapshot
    if offline:
        raise RuntimeError(f"BLOCKED_FLUX_CACHE: no complete local snapshot for {model_id!r}; offline mode prevents download.")

    from storage_manager import managed_storage_operation, storage_preflight
    from storage_policy import BYTES_PER_GB, estimate_hf_repo_bytes
    from huggingface_hub import snapshot_download

    byte_estimate = estimate_hf_repo_bytes(model_id)
    if byte_estimate <= 0:
        raise RuntimeError("BLOCKED_FLUX_DOWNLOAD_ESTIMATE: could not determine a safe download budget.")
    required_gb = byte_estimate / BYTES_PER_GB + max(0.0, float(os.environ.get("AIEROS_MODEL_DOWNLOAD_SAFETY_GB", "2.0")))
    min_free_gb = float(os.environ.get("AIEROS_MODEL_MIN_FREE_GB", "2.0"))
    ok, reason = storage_preflight("models", required_gb=required_gb, require_fresh_quota=True, minimum_free_gb=min_free_gb)
    if not ok:
        raise RuntimeError(f"FLUX model download denied by OEC StorageManager: {reason}")
    with managed_storage_operation("models", required_gb=required_gb, require_fresh_quota=True, minimum_free_gb=min_free_gb):
        ok, reason = storage_preflight("models", required_gb=required_gb, require_fresh_quota=True, minimum_free_gb=min_free_gb)
        if not ok:
            raise RuntimeError(f"FLUX model download denied inside managed operation: {reason}")
        result = Path(snapshot_download(repo_id=model_id, cache_dir=str(model_cache), local_files_only=False)).resolve()
    if not _valid_flux_snapshot(result):
        raise RuntimeError(f"FLUX snapshot remains incomplete after download: {result}")
    return result


def check_runtime(model_id: str = MODEL_ID, model_cache: str | Path | None = None, gpu: str | None = None) -> dict[str, Any]:
    selected = _prepare_gpu(gpu)
    dirs = _system_dirs()
    cache = Path(model_cache).expanduser() if model_cache else Path(dirs["models"]).expanduser()
    versions = _assert_dependencies()
    snapshot = find_cached_snapshot(model_id, cache)
    if snapshot is None:
        raise RuntimeError(f"BLOCKED_FLUX_CACHE: no complete cached snapshot for {model_id!r}; no downloads performed.")
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("BLOCKED_FLUX_CUDA: torch.cuda.is_available() is false.")
    from diffusers import Flux2KleinPipeline
    result = {
        "status": "PASS_CHECK", "model_id": model_id, "snapshot": str(snapshot),
        "gpu_setting": selected or os.environ.get("CUDA_VISIBLE_DEVICES", "scheduler-default"),
        "cuda_available": True, "device_name": torch.cuda.get_device_name(0),
        "torch": torch.__version__, "torch_cuda": torch.version.cuda, "packages": versions,
        "outputs_root": dirs.get("outputs"), "pipeline_class": Flux2KleinPipeline.__name__,
    }
    print("FLUX_RUNTIME_CHECK=PASS " + json.dumps(result, sort_keys=True), flush=True)
    return result


def load_flux_pipeline(model_id: str = MODEL_ID, model_cache: str | Path | None = None,
                       offline: bool = True, gpu: str | None = None) -> Any:
    _prepare_gpu(gpu)
    dirs = _system_dirs()
    cache = Path(model_cache).expanduser() if model_cache else Path(dirs["models"]).expanduser()
    versions = _assert_dependencies()
    snapshot = _resolve_snapshot(model_id, cache, offline)
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("BLOCKED_FLUX_CUDA: CUDA is not available in this Python environment.")
    try:
        from diffusers import Flux2KleinPipeline
    except Exception as exc:
        raise RuntimeError(
            "FLUX_PIPELINE_IMPORT=FAIL. Diffusers/Hub is incompatible or incomplete; "
            "run the guarded dependency cell, restart the kernel and retry."
        ) from exc
    load_started = time.monotonic()
    with _offline_hub():
        print("FLUX_PIPELINE_LOAD=START " + json.dumps({
            "snapshot": str(snapshot), "device_map": "cuda", "dtype": "bfloat16"
        }, sort_keys=True), flush=True)
        # Load components directly to the selected CUDA device. This avoids
        # materializing the full BF16 pipeline on CPU and then copying it to GPU.
        pipeline = Flux2KleinPipeline.from_pretrained(
            str(snapshot), torch_dtype=torch.bfloat16, local_files_only=True,
            device_map="cuda",
        )
    print("FLUX_PIPELINE_LOAD=PASS " + json.dumps({
        "snapshot": str(snapshot), "packages": versions, "device_map": "cuda",
        "load_seconds": round(time.monotonic() - load_started, 3)
    }, sort_keys=True), flush=True)
    return pipeline


def _output_preflight():
    from storage_manager import storage_preflight
    dirs = _system_dirs()
    target = Path(dirs["outputs"]) / "images"
    ok, reason = storage_preflight("outputs", required_gb=0.05, require_fresh_quota=True, minimum_free_gb=0.02)
    if not ok:
        raise RuntimeError(f"FLUX output denied by OEC StorageManager: {reason}")
    return target


def generate_flux_image(pipeline: Any, prompt: str, seed: int = 42, randomize_seed: bool = False,
                        width: int = 1024, height: int = 1024, steps: int = 4, guidance_scale: float = 1.0,
                        input_image: Any | None = None, output_path: str | Path | None = None,
                        output_dir: str | Path | None = None, scratch_output: bool = False,
                        model_cache: str | Path | None = None) -> tuple[Any, int, str, str]:
    import torch
    from PIL import Image

    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 2000:
        raise ValueError("Prompt must be non-empty and no longer than 2000 characters.")
    for name, value in (("width", width), ("height", height)):
        if int(value) < 256 or int(value) > 1024 or int(value) % 64:
            raise ValueError(f"{name} must be a multiple of 64 between 256 and 1024.")
    if not 1 <= int(steps) <= 12:
        raise ValueError("steps must be in the range 1..12 for the distilled FLUX.2 Klein model.")
    if not 0.0 <= float(guidance_scale) <= 4.0:
        raise ValueError("guidance_scale must be between 0.0 and 4.0.")
    dirs = _system_dirs()
    cache = Path(model_cache).expanduser() if model_cache else Path(dirs["models"]).expanduser()

    if scratch_output:
        if output_path is None:
            raise ValueError("--scratch-output requires an explicit --output path.")
        destination = validate_scratch_path(output_path, cache)
        if destination.exists() or destination.with_name(destination.stem + "_info.json").exists():
            raise FileExistsError("Refusing to overwrite a scratch PNG or metadata file.")
    else:
        managed_root = (Path(dirs["outputs"]) / "images").resolve()
        output_root = Path(output_dir).expanduser().resolve() if output_dir else managed_root
        try:
            output_root.relative_to(managed_root)
        except ValueError as exc:
            raise RuntimeError("BLOCKED_OUTPUT_PATH: managed outputs must remain under SYSTEM_DIRS['outputs']/images.") from exc
        # Fail before inference if this output cannot be saved under the current storage policy.
        _output_preflight()
        if output_path:
            destination = Path(output_path).expanduser().resolve()
            try:
                destination.relative_to(managed_root)
            except ValueError as exc:
                raise RuntimeError("BLOCKED_OUTPUT_PATH: explicit output must be under SYSTEM_DIRS['outputs']/images.") from exc
        else:
            destination = output_root / f"flux2_klein_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{int(seed)}.png"
        if destination.exists() or destination.with_name(destination.stem + "_info.json").exists():
            raise FileExistsError("Refusing to overwrite an existing image or metadata file.")

    actual_seed = random.randint(0, 2**31 - 1) if randomize_seed else int(seed)
    kwargs = {
        "prompt": prompt.strip(), "width": int(width), "height": int(height),
        "guidance_scale": float(guidance_scale), "num_inference_steps": int(steps),
        "generator": torch.Generator(device="cuda").manual_seed(actual_seed),
    }
    source_path = None
    if input_image is not None:
        if isinstance(input_image, (str, Path)):
            source_path = str(Path(input_image).expanduser().resolve())
            with Image.open(source_path) as handle:
                kwargs["image"] = handle.convert("RGB").copy()
        else:
            kwargs["image"] = input_image.convert("RGB")
    started = time.time()
    image = pipeline(**kwargs).images[0].convert("RGB")
    metadata_path = destination.with_name(destination.stem + "_info.json")
    payload = {
        "model_id": MODEL_ID, "prompt": prompt.strip(), "seed": actual_seed,
        "randomized_seed": bool(randomize_seed), "width": int(width), "height": int(height),
        "num_inference_steps": int(steps), "guidance_scale": float(guidance_scale),
        "input_image": source_path, "image_path": str(destination),
        "generation_seconds": round(time.time() - started, 3), "host": socket.gethostname(),
        "output_mode": "local_scratch_only" if scratch_output else "managed_output",
        "created_at": datetime.now().astimezone().isoformat(), "packages": _version_report(),
    }

    if scratch_output:
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, format="PNG")
        save_result = validate_png_file(destination)
        payload["image_bytes"] = save_result["bytes"]
        metadata_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        from storage_manager import managed_storage_operation, storage_preflight
        with managed_storage_operation("outputs", required_gb=0.05, require_fresh_quota=True, minimum_free_gb=0.02):
            ok, reason = storage_preflight("outputs", required_gb=0.05, require_fresh_quota=True, minimum_free_gb=0.02)
            if not ok:
                raise RuntimeError(f"FLUX output denied inside managed write: {reason}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.save(destination, format="PNG")
            save_result = validate_png_file(destination)
            payload["image_bytes"] = save_result["bytes"]
            metadata_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    gc.collect()
    torch.cuda.empty_cache()
    print("FLUX_IMAGE_GENERATION=PASS " + json.dumps({
        "path": str(destination), "metadata_path": str(metadata_path),
        "bytes": save_result["bytes"], "seed": actual_seed, "width": int(width), "height": int(height),
        "generation_seconds": round(time.time() - started, 3),
        "output_mode": "local_scratch_only" if scratch_output else "managed_output",
    }, sort_keys=True), flush=True)
    return image, actual_seed, str(destination), str(metadata_path)


def create_gradio_demo(
    pipeline: Any,
    output_dir: str | Path | None = None,
    port: int = 7864,
    scratch_output: bool | None = None,
    model_cache: str | Path | None = None,
):
    """Create the UI with verified local scratch output by default.

    Set AIEROS_FLUX_UI_OUTPUT_MODE=shared, or pass scratch_output=False, only
    when shared output is intended and current StorageManager quota admission
    is available. Scratch PNG/sidecars live under /tmp and are not durable.
    """
    import gradio as gr
    dirs = _system_dirs()
    cache = Path(model_cache).expanduser() if model_cache else Path(dirs["models"]).expanduser()
    if scratch_output is None:
        mode = os.environ.get("AIEROS_FLUX_UI_OUTPUT_MODE", "scratch").strip().lower()
        if mode not in {"scratch", "shared"}:
            raise ValueError("AIEROS_FLUX_UI_OUTPUT_MODE must be 'scratch' or 'shared'.")
        scratch_output = mode == "scratch"
    if scratch_output:
        safe_user = "".join(
            char for char in os.environ.get("USER", "user") if char.isalnum() or char in "-_"
        ) or "user"
        configured_scratch = os.environ.get("AIEROS_FLUX_UI_SCRATCH_DIR")
        chosen_output = (
            Path(configured_scratch).expanduser()
            if configured_scratch
            else Path("/tmp") / f"oec-flux-ui-{safe_user}-{os.getpid()}"
        )
        if not _is_relative_to(chosen_output.resolve(), Path("/tmp")):
            raise RuntimeError("BLOCKED_SCRATCH_OUTPUT: AIEROS_FLUX_UI_SCRATCH_DIR must be under /tmp.")
        print(f"FLUX_UI_OUTPUT_MODE=scratch path={chosen_output}", flush=True)
    else:
        chosen_output = Path(output_dir).expanduser() if output_dir else Path(dirs["outputs"]) / "images"
        print(f"FLUX_UI_OUTPUT_MODE=shared path={chosen_output}", flush=True)

    def generate(prompt, input_image, width, height, steps, guidance, seed, randomize):
        try:
            output_path = None
            if scratch_output:
                # Let generate_flux_image validate the target filesystem/headroom
                # before it creates the scratch directory.
                output_path = chosen_output / f"flux2_klein_{time.time_ns()}_{int(seed)}.png"
            return generate_flux_image(
                pipeline=pipeline, prompt=prompt, input_image=input_image,
                width=int(width), height=int(height), steps=int(steps),
                guidance_scale=float(guidance), seed=int(seed), randomize_seed=bool(randomize),
                output_path=output_path, output_dir=chosen_output,
                scratch_output=bool(scratch_output), model_cache=cache,
            )
        except Exception as exc:
            raise gr.Error(f"FLUX generation failed: {type(exc).__name__}: {exc}") from exc

    # Keep the UI compatible with the older Gradio version installed in phase2_3d.
    # Theme customization is optional and has caused BlockContext constructor failures.
    with gr.Blocks(title="FLUX.2 Klein — OEC") as demo:
        gr.Markdown("# FLUX.2 Klein 4B — text-to-image and image-conditioned generation")
        gr.Markdown("Saves a validated PNG and JSON sidecar. Public Gradio sharing is disabled by default.")
        with gr.Row():
            with gr.Column(scale=1):
                prompt = gr.Textbox(label="Prompt", value="A sci-fi crate in a clean studio photograph", lines=4)
                input_image = gr.Image(label="Optional reference image", type="pil")
                with gr.Row():
                    width = gr.Slider(label="Width", minimum=256, maximum=1024, value=1024, step=64)
                    height = gr.Slider(label="Height", minimum=256, maximum=1024, value=1024, step=64)
                steps = gr.Slider(label="Inference steps", minimum=1, maximum=12, value=4, step=1)
                guidance = gr.Slider(label="Guidance scale", minimum=0, maximum=4, value=1, step=0.1)
                seed = gr.Number(label="Seed", value=42, precision=0)
                randomize = gr.Checkbox(label="Randomize seed", value=True)
                button = gr.Button("Generate image", variant="primary")
            with gr.Column(scale=2):
                output_image = gr.Image(label="Generated PNG")
                output_seed = gr.Number(label="Seed used", precision=0)
                output_file = gr.File(label="PNG file")
                metadata_file = gr.File(label="Generation metadata JSON")
        button.click(
            fn=generate, inputs=[prompt, input_image, width, height, steps, guidance, seed, randomize],
            outputs=[output_image, output_seed, output_file, metadata_file],
            api_name="generate",
        )
    demo.queue(default_concurrency_limit=1)
    # Gradio restricts file outputs to its cache, current directory, system temp,
    # or explicitly allowed paths. Our scratch directory can be a distinct local
    # filesystem, so the launcher must add exactly this output directory.
    demo.oec_output_dir = str(chosen_output.resolve())
    return demo


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    gpu = _prepare_gpu(args.gpu)
    dirs = _system_dirs()
    cache = args.model_cache or Path(dirs["models"])
    if args.mode == "check":
        check_runtime(args.model_id, cache, gpu)
        return 0
    if args.mode == "generate":
        pipeline = load_flux_pipeline(args.model_id, cache, offline=args.offline, gpu=gpu)
        output = args.output
        if args.scratch_output and output is None:
            run_id = os.environ.get("GITHUB_RUN_ID", "manual")
            output = Path("/tmp") / f"oec-flux-image-{run_id}" / "flux2_klein.png"
        _, _, png, metadata_path = generate_flux_image(
            pipeline, args.prompt, seed=args.seed, randomize_seed=args.randomize_seed,
            width=args.width, height=args.height, steps=args.steps, guidance_scale=args.guidance_scale,
            input_image=args.input, output_path=output, output_dir=args.output_dir,
            scratch_output=args.scratch_output, model_cache=cache,
        )
        print(f"FLUX_RESULT_FILE={png}\nFLUX_METADATA_FILE={metadata_path}", flush=True)
        return 0
    pipeline = load_flux_pipeline(args.model_id, cache, offline=args.offline, gpu=gpu)
    demo = create_gradio_demo(pipeline, output_dir=args.output_dir, port=args.port)
    print(f"FLUX_GRADIO_START port={args.port} server={args.server_name} share={args.share}", flush=True)
    demo.launch(server_name=args.server_name, server_port=args.port, inline=False, share=bool(args.share), show_error=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
