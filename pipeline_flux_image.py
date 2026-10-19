#!/usr/bin/env python3
"""Cache-only FLUX.2 Klein text-to-image inference and Gradio entry point."""
from __future__ import annotations
import argparse, csv, hashlib, importlib.metadata, json, os, subprocess, sys, time, uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core_config import SYSTEM_DIRS  # noqa: E402

MODEL_ID = "black-forest-labs/FLUX.2-klein-4B"
VERSIONS = {"diffusers": "0.37.0", "huggingface-hub": "0.36.0", "transformers": "4.56.1"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("check", "generate", "gradio"), default="generate")
    p.add_argument("--offline", action="store_true", help="Cache-only operation; no package/model downloads.")
    p.add_argument("--scratch-output", action="store_true", help="Limit generated files to local /tmp.")
    p.add_argument("--gpu", type=int, default=None, help="Physical A100 index.")
    p.add_argument("--output", type=Path, help="Exact PNG path.")
    p.add_argument("--prompt", default="A photorealistic amber glass sphere on a clean studio background")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--width", type=int, default=512)
    p.add_argument("--height", type=int, default=512)
    p.add_argument("--steps", type=int, default=4)
    p.add_argument("--guidance-scale", type=float, default=1.0)
    p.add_argument("--port", type=int, default=7864)
    return p


def _under(path: Path, root: Path) -> bool:
    p, r = path.expanduser().resolve(), root.expanduser().resolve()
    return p != r and r in p.parents


def _validate(prompt: str, width: int, height: int, steps: int, guidance: float) -> None:
    if not prompt or not prompt.strip() or len(prompt) > 2000:
        raise ValueError("prompt must contain 1–2000 characters")
    if any(v < 256 or v > 1024 or v % 16 for v in (width, height)):
        raise ValueError("width/height must be multiples of 16 between 256 and 1024")
    if not 1 <= steps <= 20 or not 0 <= guidance <= 10:
        raise ValueError("steps must be 1–20 and guidance-scale must be 0–10")


def select_idle_a100_gpu(requested: int | None = None) -> dict[str, str]:
    try:
        inv = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid,name,memory.used,utilization.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
        apps = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid",
                               "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError("GPU/process telemetry unavailable; refusing inference") from e
    if inv.returncode or apps.returncode:
        raise RuntimeError("nvidia-smi GPU/process telemetry failed; refusing inference")
    busy = {row[0].strip() for row in csv.reader(apps.stdout.splitlines())
            if len(row) >= 2 and row[0].strip() and row[1].strip().isdigit()}
    for row in csv.reader(inv.stdout.splitlines()):
        if len(row) != 5:
            continue
        idx, uid, name, memory, util = (v.strip() for v in row)
        if not idx.isdigit() or "A100" not in name.upper() or (requested is not None and int(idx) != requested):
            continue
        try:
            idle = uid not in busy and float(memory) <= 1024 and float(util) <= 5
        except ValueError:
            idle = False
        if idle:
            result = {"index": idx, "uuid": uid, "name": name, "memory_used_mib": memory, "utilization_percent": util}
            print("FLUX_GPU_ADMITTED=" + json.dumps(result, sort_keys=True), flush=True)
            return result
    raise RuntimeError("no eligible idle A100; no process was killed or signalled")


def _check_versions() -> None:
    bad = {}
    for package, expected in VERSIONS.items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            actual = None
        print(f"FLUX_PACKAGE_{package}={actual or 'MISSING'} required={expected}", flush=True)
        if actual != expected:
            bad[package] = {"actual": actual, "required": expected}
    if bad:
        raise RuntimeError("FLUX dependency mismatch; no packages were installed or upgraded: " + json.dumps(bad))


def _snapshot() -> Path:
    from huggingface_hub import snapshot_download
    try:
        from huggingface_hub.errors import LocalEntryNotFoundError
    except ImportError:
        from huggingface_hub.utils import LocalEntryNotFoundError
    try:
        path = snapshot_download(repo_id=MODEL_ID, cache_dir=str(SYSTEM_DIRS["models"]), local_files_only=True)
    except LocalEntryNotFoundError as e:
        raise RuntimeError(f"FLUX cache miss for {MODEL_ID}; offline path will not download weights") from e
    print(f"FLUX_CACHE=HIT snapshot={path}", flush=True)
    return Path(path)


def _load(snapshot: Path, gpu: dict[str, str]) -> tuple[Any, Any]:
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu["index"]
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch
    from diffusers import DiffusionPipeline, Flux2KleinPipeline  # noqa: F401
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable after physical GPU selection")
    torch.cuda.set_device(0)
    if "A100" not in torch.cuda.get_device_name(0).upper():
        raise RuntimeError("visible CUDA device is not an A100")
    pipe = DiffusionPipeline.from_pretrained(str(snapshot), torch_dtype=torch.bfloat16,
        cache_dir=str(SYSTEM_DIRS["models"]), local_files_only=True)
    pipe.enable_model_cpu_offload()
    print(f"FLUX_MODEL_LOAD=PASS class={type(pipe).__name__} revision={snapshot.name}", flush=True)
    return pipe, torch


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _output_path(output: Path | None, scratch: bool, seed: int) -> Path:
    root = Path(SYSTEM_DIRS["outputs"]).expanduser().resolve()
    tag = f"{int(time.time())}-{uuid.uuid4().hex[:8]}-{seed}"
    if output is None:
        output = (Path("/tmp") / f"oec-flux-{tag}.png") if scratch else root / "images" / f"flux2_klein_{tag}.png"
    path = output.expanduser().resolve()
    if scratch and not _under(path, Path("/tmp")):
        raise ValueError("--scratch-output requires a path below /tmp")
    if not scratch and not _under(path, root):
        raise ValueError("managed image outputs must be below the configured OEC outputs root")
    if path.exists() or path.with_suffix(".info.json").exists():
        raise FileExistsError(f"refusing to overwrite existing FLUX output: {path}")
    return path


def _write_image(image: Any, path: Path, scratch: bool, metadata: dict[str, Any]) -> dict[str, Any]:
    import json
    from PIL import Image
    def write() -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, format="PNG")
        if not path.is_file() or path.stat().st_size <= 8 or path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("FLUX export is not a non-empty PNG")
        with Image.open(path) as check:
            check.verify()
        with Image.open(path) as check:
            width, height = check.size
        metadata.update({"artifact_path": str(path), "artifact_bytes": path.stat().st_size,
                         "artifact_sha256": _sha256(path), "width": width, "height": height})
        with path.with_suffix(".info.json").open("x", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, sort_keys=True)
        return metadata
    if scratch:
        return write()
    from storage_manager import managed_storage_operation, storage_preflight
    with managed_storage_operation("outputs", required_gb=0.05, require_fresh_quota=True, minimum_free_gb=0.02):
        ok, why = storage_preflight("outputs", required_gb=0.05, require_fresh_quota=True, minimum_free_gb=0.02)
        if not ok:
            raise RuntimeError(f"StorageManager refused FLUX output inside managed operation: {why}")
        return write()


def _generate(pipe: Any, torch: Any, gpu: dict[str, str], snapshot: Path, prompt: str, seed: int,
              width: int, height: int, steps: int, guidance: float, output: Path | None, scratch: bool):
    _validate(prompt, width, height, steps, guidance)
    path = _output_path(output, scratch, seed)
    if not scratch:
        from storage_manager import storage_preflight
        ok, why = storage_preflight("outputs", required_gb=0.05, require_fresh_quota=True, minimum_free_gb=0.02)
        if not ok:
            raise RuntimeError(f"StorageManager refused FLUX output before inference: {why}")
    generator = torch.Generator(device="cpu").manual_seed(int(seed))
    torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()
    with torch.inference_mode():
        image = pipe(prompt=prompt.strip(), width=width, height=height, guidance_scale=guidance,
                     num_inference_steps=steps, max_sequence_length=512, generator=generator).images[0].convert("RGB")
    metadata = {"provider": "flux", "model": MODEL_ID, "model_revision": snapshot.name,
                "physical_gpu": int(gpu["index"]), "seed": int(seed), "prompt": prompt.strip(),
                "steps": steps, "guidance_scale": guidance, "generation_seconds": round(time.monotonic()-started, 3)}
    metadata["peak_allocated_gib"] = round(torch.cuda.max_memory_allocated() / 1024**3, 3)
    metadata["peak_reserved_gib"] = round(torch.cuda.max_memory_reserved() / 1024**3, 3)
    metadata = _write_image(image, path, scratch, metadata)
    torch.cuda.empty_cache()
    print("FLUX_IMAGE_ACCEPTANCE=" + json.dumps(metadata, sort_keys=True), flush=True)
    return image, metadata


def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    if args.port < 1 or args.port > 65535:
        p.error("--port must be in 1..65535")
    if args.mode != "check":
        try:
            _validate(args.prompt, args.width, args.height, args.steps, args.guidance_scale)
        except ValueError as e:
            p.error(str(e))
    gpu = select_idle_a100_gpu(args.gpu)
    _check_versions()
    snapshot = _snapshot()
    if args.mode == "check":
        print("FLUX_CACHE_CHECK=PASS revision=" + snapshot.name)
        return 0
    pipe, torch = _load(snapshot, gpu)
    if args.mode == "generate":
        _image, _meta = _generate(pipe, torch, gpu, snapshot, args.prompt, args.seed, args.width,
                                  args.height, args.steps, args.guidance_scale, args.output, args.scratch_output)
        print("FLUX_GENERATION=PASS")
        return 0
    import gradio as gr
    with gr.Blocks(title="OEC FLUX.2 Klein", theme=gr.themes.Monochrome()) as demo:
        gr.Markdown("# OEC FLUX.2 Klein — text to image")
        prompt = gr.Textbox(label="Prompt", value=args.prompt, lines=3)
        with gr.Row():
            seed = gr.Number(label="Seed", value=args.seed, precision=0)
            width = gr.Dropdown([512, 768, 1024], value=args.width, label="Width")
            height = gr.Dropdown([512, 768, 1024], value=args.height, label="Height")
            steps = gr.Slider(1, 20, value=args.steps, step=1, label="Steps")
            guidance = gr.Slider(0, 10, value=args.guidance_scale, step=0.1, label="Guidance")
        button = gr.Button("Generate", variant="primary")
        picture = gr.Image(label="PNG")
        saved = gr.File(label="Saved image")
        def do_generate(txt: str, s: float, w: int, h: int, st: float, g: float):
            image, metadata = _generate(pipe, torch, gpu, snapshot, txt, int(s), int(w), int(h), int(st), float(g), None, False)
            return image, metadata["artifact_path"]
        button.click(do_generate, inputs=[prompt, seed, width, height, steps, guidance], outputs=[picture, saved])
    demo.launch(server_name="0.0.0.0", server_port=args.port, inline=False, share=False, show_error=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
