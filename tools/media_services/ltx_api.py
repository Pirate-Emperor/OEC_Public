#!/usr/bin/env python3
"""Loopback JSON job API for OEC's existing LTX-2.3 video worker.

Run inside phase1_ltx. It does not replace the production multi-node queue / QA /
upload orchestration; it hosts an isolated one-GPU sidecar for OEC-Play jobs.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common import MediaProvider, RequestError, managed_write, safe_child, serve, storage_check, validate_mp4

LOG = logging.getLogger("oec.media_service.ltx")
MODEL_ID = "Lightricks/LTX-2.3"

def purge_loaded_ltx_caches() -> dict[str, bool]:
    """Use the existing LTX load-then-purge policy after model weights are resident.

    This is only called when the operator has opted into the guarded-download mode;
    cache-only deployments retain their on-disk weights for restartability.
    """
    from purge_manager import DiskPurgeManager

    results = {
        "ltx": bool(DiskPurgeManager.purge_hf_model("Lightricks/LTX-2.3")),
        "gemma": bool(DiskPurgeManager.purge_hf_model("google/gemma-3-12b-it-qat-q4_0-unquantized")),
    }
    for model_key, purged in results.items():
        LOG.info("LTX_MODEL_CACHE_PURGE model=%s status=%s", model_key, "PASS" if purged else "FAILED")
    return results




class LtxProvider(MediaProvider):
    name = "ltx"
    artifact_content_type = "video/mp4"
    artifact_extension = "mp4"
    max_prompt_chars = 800

    def __init__(self, allow_download: bool = False, purge_after_load: bool = False):
        super().__init__(allow_download=allow_download)
        self.purge_after_load = bool(purge_after_load)
        if self.purge_after_load and not allow_download:
            raise ValueError("purge-after-load requires --allow-download so a later restart can restore purged weights under StorageManager")
        self.module = None
        self.pipeline = None
        self.gpu_id = "0"  # logical device index inside the scheduler-provided visibility mask

    def validate_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = payload.get("task")
        if task not in {"text_to_video", "image_to_video"}:
            raise RequestError("task must be 'text_to_video' or 'image_to_video'")
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > self.max_prompt_chars:
            raise RequestError("prompt must be a non-empty string of at most 800 characters")
        params = payload.get("parameters", {})
        if not isinstance(params, dict):
            raise RequestError("parameters must be a JSON object")
        allowed = {"duration_seconds", "fps", "seed", "randomize_seed", "enhance_prompt", "width", "height"}
        unknown = set(params) - allowed
        if unknown:
            raise RequestError(f"unsupported LTX parameters: {', '.join(sorted(unknown))}")
        duration = params.get("duration_seconds", 4.0)
        fps = params.get("fps", 24)
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not 1 <= float(duration) <= 10:
            raise RequestError("duration_seconds must be between 1 and 10")
        if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not 12 <= float(fps) <= 30:
            raise RequestError("fps must be between 12 and 30")
        seed = params.get("seed", 42)
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2_147_483_647:
            raise RequestError("seed must be an integer from 0 to 2147483647")
        randomize = params.get("randomize_seed", False)
        enhance = params.get("enhance_prompt", False)
        if not isinstance(randomize, bool) or not isinstance(enhance, bool):
            raise RequestError("randomize_seed and enhance_prompt must be boolean")
        width = params.get("width", 1536)
        height = params.get("height", 1024)
        allowed_sizes = {(1536, 1024), (1024, 1536), (1024, 1024), (768, 512), (512, 768), (768, 768)}
        if isinstance(width, bool) or isinstance(height, bool) or not isinstance(width, int) or not isinstance(height, int) or (width, height) not in allowed_sizes:
            raise RequestError("width/height must be one of the supported low/high LTX resolution pairs")
        filename = payload.get("filename", "reference.png")
        if not isinstance(filename, str) or len(filename) > 128 or Path(filename).name != filename:
            raise RequestError("filename must be a simple file name without a path")
        expects_image = task == "image_to_video"
        if expects_image and "image_base64" not in payload:
            raise RequestError("image_base64 is required for image_to_video")
        return {"task": task, "prompt": prompt.strip(), "filename": filename,
                "parameters": {"duration_seconds": float(duration), "fps": float(fps), "seed": seed,
                               "randomize_seed": randomize, "enhance_prompt": enhance,
                               "width": width, "height": height},
                "expects_image": expects_image}

    def load_runtime(self) -> None:
        # StorageManager only defines the models and outputs targets. Sidecar
        # job inputs, state and results are all contained under the managed
        # outputs/media_services tree; "inputs" and "cache" are not configured
        # logical targets and must not be passed as StorageManager areas.
        ok, reason = storage_check("outputs", 0.05, 0.05)
        if not ok:
            LOG.error("OEC outputs storage admission denied before LTX import: %s", reason)
            raise RuntimeError("OEC outputs storage admission denied; inspect the storage-manager log")
        import core_config
        with managed_write("outputs", 0.05, minimum_free_gb=0.05):
            Path(core_config.SYSTEM_DIRS["outputs"]).expanduser().mkdir(parents=True, exist_ok=True)
        import worker_ltx_video as ltx
        self.module = ltx
        # The updated worker method guarantees cache-only loading unless the
        # operator explicitly launches this sidecar with --allow-download.
        pipeline = ltx.load_pipeline_instance(
            self.gpu_id,
            allow_download=self.allow_download,
            preserve_cuda_visible_devices=True,
        )
        if pipeline is None:
            raise RuntimeError("LTX pipeline loader returned no model")
        self.pipeline = pipeline
        self.model_name = MODEL_ID
        self.model_revision = getattr(ltx, "LTX_COMMIT_SHA", None)
        try:
            self.device_name = ltx.torch.cuda.get_device_name(0)
        except Exception:
            self.device_name = "cuda:0"
        self.model_loaded = True
        if self.purge_after_load:
            # Match worker_ltx_video.py's established load-then-purge behavior.
            # With --allow-download, a future service restart may restore these
            # weights only after the existing fresh StorageManager admission.
            purge_loaded_ltx_caches()

    def run_job(self, job_id: str, request: dict[str, Any], input_file: Path | None) -> tuple[Path, dict[str, Any]]:
        if not self.model_loaded or self.pipeline is None or self.module is None:
            raise RuntimeError("LTX runtime is not loaded")
        if request["task"] == "image_to_video" and input_file is None:
            raise RuntimeError("image-conditioned task is missing its validated input")
        dirs = self.module.SYSTEM_DIRS
        output_root = Path(dirs["outputs"]).expanduser().resolve() / "media_services" / "ltx" / "jobs"
        job_dir = safe_child(output_root, job_id)
        params = request["parameters"]
        old_output_dir = self.module.AIEROS_OUTPUT_DIR
        self.module.AIEROS_OUTPUT_DIR = job_dir
        start = time.monotonic()
        try:
            # Create only the per-job directory under a short managed lease.
            # worker_ltx_video.generate_asset acquires its own lease for encode/
            # output writes. Holding a lease around the whole generation call
            # deadlocks when the worker opens its nested managed operation.
            with managed_write("outputs", 0.002, minimum_free_gb=0.01):
                job_dir.mkdir(parents=True, exist_ok=False)
            video_path, metadata_path, actual_seed = self.module.generate_asset(
                pipeline=self.pipeline,
                target_gpu_id=self.gpu_id,
                input_image=str(input_file) if input_file else None,
                prompt=request["prompt"],
                duration=params["duration_seconds"],
                enhance_prompt=params["enhance_prompt"],
                seed=params["seed"],
                randomize_seed=params["randomize_seed"],
                height=params["height"],
                width=params["width"],
                output_type="video",
                fps=params["fps"],
            )
        finally:
            self.module.AIEROS_OUTPUT_DIR = old_output_dir
        if not video_path or not metadata_path:
            raise RuntimeError("LTX generation returned no video artifact")
        path = Path(video_path).resolve()
        validation = validate_mp4(path)
        saved_metadata: dict[str, Any] = {}
        try:
            with Path(metadata_path).open("r", encoding="utf-8") as handle:
                saved_metadata = json.load(handle)
        except (OSError, json.JSONDecodeError):
            # The video is still validated below; missing side metadata is a
            # job-record issue, not a reason to misreport an unreadable file.
            saved_metadata = {}
        return path, {
            "provider": "ltx", "model": MODEL_ID, "model_revision": self.model_revision,
            "device": self.device_name, "task": request["task"], "prompt": request["prompt"],
            "parameters": params, "seed_used": actual_seed,
            "input_filename": request["filename"] if input_file else None,
            "worker_metadata": saved_metadata, "video_validation": validation,
            "generation_seconds": round(time.monotonic() - start, 3),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7869)
    parser.add_argument("--max-queue", type=int, default=1)
    parser.add_argument("--job-timeout-seconds", type=int, default=2400)
    parser.add_argument("--allow-download", action="store_true", help="Allow missing model files to download only through the existing OEC storage gate.")
    parser.add_argument(
        "--keep-model-cache",
        action="store_true",
        help="Keep LTX/Gemma checkpoints on disk even when --allow-download is enabled.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Purge only when the operator explicitly enabled the guarded download/recovery
    # lifecycle. Cache-only mode remains restartable without network access.
    purge_after_load = args.allow_download and not args.keep_model_cache
    provider = LtxProvider(args.allow_download, purge_after_load=purge_after_load)
    return serve(provider, args.host, args.port, args.max_queue, args.job_timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
