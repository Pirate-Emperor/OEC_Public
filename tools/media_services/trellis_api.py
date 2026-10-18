#!/usr/bin/env python3
"""Loopback JSON job API for OEC's existing TRELLIS.2 image-to-3D pipeline.

Run inside the phase2_3d environment. The sidecar keeps one model instance in
this process; it never imports TRELLIS into the OEC-Play Waypoint server.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common import MediaJobService, MediaProvider, RequestError, managed_write, safe_child, serve, validate_glb

LOG = logging.getLogger("oec.media_service.trellis")
MODEL_ID = "microsoft/TRELLIS.2-4B"


class TrellisProvider(MediaProvider):
    name = "trellis"
    artifact_content_type = "model/gltf-binary"
    artifact_extension = "glb"
    max_prompt_chars = 500

    def __init__(self, allow_download: bool = False, gpu: str | None = None, attention_backend: str = "xformers"):
        super().__init__(allow_download=allow_download)
        self.gpu = gpu
        self.attention_backend = attention_backend
        self.module = None
        self.runtime: dict[str, Any] | None = None
        self.pipeline = None

    def validate_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("task") != "image_to_3d":
            raise RequestError("task must be 'image_to_3d'")
        prompt = payload.get("prompt", "")
        if not isinstance(prompt, str) or len(prompt) > self.max_prompt_chars:
            raise RequestError(f"prompt must be a string of at most {self.max_prompt_chars} characters")
        filename = payload.get("filename", "reference.png")
        if not isinstance(filename, str) or len(filename) > 128 or Path(filename).name != filename:
            raise RequestError("filename must be a simple file name without a path")
        params = payload.get("parameters", {})
        if not isinstance(params, dict):
            raise RequestError("parameters must be a JSON object")
        unknown = set(params) - {"max_image_size", "texture_size", "decimation_target"}
        if unknown:
            raise RequestError(f"unsupported TRELLIS parameters: {', '.join(sorted(unknown))}")
        max_size = params.get("max_image_size", 1024)
        texture_size = params.get("texture_size", 2048)
        decimation_target = params.get("decimation_target", 100_000)
        if isinstance(max_size, bool) or not isinstance(max_size, int) or max_size not in {512, 768, 1024, 1280}:
            raise RequestError("max_image_size must be one of 512, 768, 1024, 1280")
        if isinstance(texture_size, bool) or not isinstance(texture_size, int) or texture_size not in {512, 1024, 2048, 4096}:
            raise RequestError("texture_size must be one of 512, 1024, 2048, 4096")
        if isinstance(decimation_target, bool) or not isinstance(decimation_target, int) or not 1_000 <= decimation_target <= 500_000:
            raise RequestError("decimation_target must be an integer from 1000 to 500000")
        if "image_base64" not in payload:
            raise RequestError("image_base64 is required for image_to_3d")
        return {"task": "image_to_3d", "prompt": prompt, "filename": filename,
                "parameters": {"max_image_size": max_size, "texture_size": texture_size,
                               "decimation_target": decimation_target}, "expects_image": True}

    def load_runtime(self) -> None:
        import pipeline_trellis_3d as trellis
        self.module = trellis
        argv = ["--mode", "generate", "--attention-backend", self.attention_backend]
        if self.gpu is not None:
            argv += ["--gpu", self.gpu]
        if not self.allow_download:
            argv.append("--offline")
        args = trellis.build_parser().parse_args(argv)
        runtime = trellis._imports_and_probe(args)
        pipeline = trellis._load_pipeline(args, runtime)
        if pipeline is None:
            raise RuntimeError("TRELLIS pipeline loader returned no model")
        self.runtime = runtime
        self.pipeline = pipeline
        self.model_name = MODEL_ID
        self.model_revision = Path(str(runtime.get("snapshot", "unknown"))).name
        try:
            self.device_name = runtime["torch"].cuda.get_device_name(0)
        except Exception:
            self.device_name = "cuda:0"
        self.model_loaded = True

    def run_job(self, job_id: str, request: dict[str, Any], input_file: Path | None) -> tuple[Path, dict[str, Any]]:
        if not self.model_loaded or self.pipeline is None or self.runtime is None or input_file is None:
            raise RuntimeError("TRELLIS runtime or input image is unavailable")
        from PIL import Image
        with Image.open(input_file) as opened:
            image = opened.convert("RGB")
        dirs = self.runtime["system_dirs"]
        output_root = Path(dirs["outputs"]).expanduser().resolve() / "media_services" / "trellis" / "jobs"
        job_dir = safe_child(output_root, job_id)
        output_path = safe_child(job_dir, f"{job_id}.glb")
        params = request["parameters"]
        start = time.monotonic()
        generated = self.module.generate_glb(
            image=image,
            pipeline=self.pipeline,
            o_voxel=self.runtime["o_voxel"],
            system_dirs=dirs,
            output_dir=None,
            output_path=output_path,
            max_image_size=params["max_image_size"],
            decimation_target=params["decimation_target"],
            texture_size=params["texture_size"],
        )
        path = Path(generated).resolve()
        geometry = validate_glb(path)
        return path, {
            "provider": "trellis", "model": MODEL_ID,
            "model_revision": self.model_revision, "device": self.device_name,
            "parameters": params, "input_filename": request["filename"],
            # TRELLIS.2's current entry point is image-conditioned; this optional
            # prompt is retained as job metadata and is not passed as a model input.
            "prompt_metadata_only": request["prompt"],
            "geometry_validation": geometry,
            "generation_seconds": round(time.monotonic() - start, 3),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7868)
    parser.add_argument("--gpu", default=None, help="Optional local GPU index; omit to preserve scheduler CUDA_VISIBLE_DEVICES.")
    parser.add_argument("--attention-backend", choices=("xformers", "flash_attn"), default=os.environ.get("AIEROS_TRELLIS_ATTN_BACKEND", "xformers"))
    parser.add_argument("--max-queue", type=int, default=2)
    parser.add_argument("--job-timeout-seconds", type=int, default=1800)
    parser.add_argument("--allow-download", action="store_true", help="Allow missing model files to download only through the existing OEC storage gate.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    provider = TrellisProvider(args.allow_download, args.gpu, args.attention_backend)
    return serve(provider, args.host, args.port, args.max_queue, args.job_timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
