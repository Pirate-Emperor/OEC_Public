# 1. CORE CONFIGURATION (Must be the absolute first import to lock in cache paths)
import core_config
print("[SYSTEM] Core proxies, storage mapping, and HF Auth executed automatically.")

import os
import sys
import subprocess
import random
import time
import glob
import json
import struct
import argparse
import sqlite3
from pathlib import Path
from datetime import datetime
import multiprocessing as mp
import numpy as np

# STRICT DISK MANAGER IMPORT
from purge_manager import DiskPurgeManager, ClusterPurgeManager
from storage_manager import managed_storage_operation
from storage_policy import BYTES_PER_GB, estimate_hf_repo_bytes

os.environ["TORCH_COMPILE_DISABLE"] = "1"
os.environ["TORCHDYNAMO_DISABLE"] = "1"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["HF_HUB_USE_XET"] = "0"
os.environ["no_proxy"] = "localhost, 127.0.0.1, ::1, 0.0.0.0"
os.environ["NO_PROXY"] = "localhost, 127.0.0.1, ::1, 0.0.0.0"

# 2. RUNTIME DEPENDENCY / SOURCE PATHS
# Runtime workers must not install packages or clone repositories as an import
# side effect. Prepare the pinned LTX-2 checkout explicitly beforehand.
LTX_REPO_URL = "https://github.com/Lightricks/LTX-2.git"
LTX_COMMIT_SHA = "ae855f8538843825f9015a419cf4ba5edaf5eec2"
LTX_REPO_DIR = os.path.abspath(
    os.environ.get(
        "AIEROS_LTX_REPO_DIR",
        os.path.join(core_config.SYSTEM_DIRS["cache"], "third_party", "LTX-2"),
    )
)
LTX_CORE_DIR = os.path.join(LTX_REPO_DIR, "packages", "ltx-core")

def ensure_ltx_runtime():
    """Validate the explicitly prepared pinned LTX runtime without mutating it."""
    if not os.path.isdir(LTX_CORE_DIR):
        raise RuntimeError(
            "LTX-2 runtime is not prepared. Expected the pinned checkout at "
            f"{LTX_REPO_DIR}. Run the explicit LTX setup step before starting the worker."
        )

    try:
        import xformers  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "xformers is not installed in the active environment. "
            "Install it during environment setup; the inference worker will not "
            "pip-install dependencies at runtime."
        ) from exc

    pipeline_src = os.path.join(LTX_REPO_DIR, "packages", "ltx-pipelines", "src")
    core_src = os.path.join(LTX_CORE_DIR, "src")
    if pipeline_src not in sys.path:
        sys.path.insert(0, pipeline_src)
    if core_src not in sys.path:
        sys.path.insert(0, core_src)

# 3. HEAVY ML IMPORTS# 3. HEAVY ML IMPORTS
import torch
import gradio as gr
from huggingface_hub import hf_hub_download, snapshot_download

# ==============================================================================
# 4. GLOBAL SETTINGS & DIRECTORY MAPPING
# ==============================================================================
MODEL_TYPE = "ltx-2.3-22b"
OUTPUT_TYPE_VIDEO = "video"
OUTPUT_TYPE_IMAGE = "image"
MAX_SEED = np.iinfo(np.int32).max
DEFAULT_FRAME_RATE = 24.0

RESOLUTIONS = {
    "high": {"16:9": (1536, 1024), "9:16": (1024, 1536), "1:1": (1024, 1024)},
    "low": {"16:9": (768, 512), "9:16": (512, 768), "1:1": (768, 768)},
}

from core_config import SYSTEM_DIRS, QUEUE_DB_PATH
AIEROS_OUTPUT_DIR = Path(SYSTEM_DIRS['outputs']) / "videos"
AIEROS_INPUT_DIR = Path(SYSTEM_DIRS['inputs']) / "images"
JOB_DIR = Path(SYSTEM_DIRS['inputs']) / "jobs"

AIEROS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
AIEROS_INPUT_DIR.mkdir(parents=True, exist_ok=True)
JOB_DIR.mkdir(parents=True, exist_ok=True)

class DualLogger:
    """Writes to both the screen buffer and a text file simultaneously."""
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log_file = open(filepath, "a", buffering=1)
    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.terminal.flush()
        self.log_file.flush()
    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

def get_best_gpu():
    """Finds the GPU with the most free VRAM automatically."""
    try:
        smi_output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,nounits,noheader"], 
            encoding="utf-8"
        )
        memory_free = [int(x.strip()) for x in smi_output.strip().split('\n')]
        best_gpu = memory_free.index(max(memory_free))
        print(f"[SYSTEM] Auto-selected GPU {best_gpu} ({memory_free[best_gpu]} MB free)")
        return str(best_gpu)
    except Exception as e:
        raise RuntimeError(f"Could not determine available GPU memory via nvidia-smi: {e}") from e

# ==============================================================================
# 5. ML PATCHES & PIPELINE LOADING
# ==============================================================================
def apply_fuse_patches():
    """Patches xformers and Safetensors to prevent A100 memory deadlocks."""
    from ltx_core.loader.primitives import StateDict
    from ltx_core.loader.sft_loader import SafetensorsStateDictLoader
    from ltx_core.model.transformer import attention as _attn_mod
    
    try:
        from xformers.ops import memory_efficient_attention as _mea
        _attn_mod.memory_efficient_attention = _mea
        print("[ATTN] memory_efficient_attention patched successfully.")
    except Exception as e:
        print(f"[ATTN] xformers patch FAILED: {e}")

    try:
        from xformers.ops.fmha import _set_use_fa3
        _set_use_fa3(False)
        print("[ATTN] xformers FA3 dispatch disabled (Blackwell/Hopper compatibility)")
    except Exception:
        pass

    _SAFETENSORS_DTYPE_MAP = {
        "F64": torch.float64, "F32": torch.float32, "F16": torch.float16,
        "BF16": torch.bfloat16, "F8_E5M2": torch.float8_e5m2, "F8_E4M3": torch.float8_e4m3fn,
        "I64": torch.int64, "I32": torch.int32, "I16": torch.int16,
        "I8": torch.int8, "U8": torch.uint8, "BOOL": torch.bool,
    }

    def _patched_load(self, path, sd_ops, device=None):
        sd = {}
        size = 0
        dtype = set()
        device = device or torch.device("cpu")
        model_paths = path if isinstance(path, list) else [path]
        for shard_path in model_paths:
            with open(shard_path, "rb") as f:
                header_len = struct.unpack("<Q", f.read(8))[0]
                header = json.loads(f.read(header_len).decode("utf-8"))
                data_base = 8 + header_len
                for name, meta in header.items():
                    if name == "__metadata__": continue
                    expected_name = name if sd_ops is None else sd_ops.apply_to_key(name)
                    if expected_name is None: continue
                    start, end = meta["data_offsets"]
                    f.seek(data_base + start)
                    buf = f.read(end - start)
                    t = torch.frombuffer(bytearray(buf), dtype=_SAFETENSORS_DTYPE_MAP[meta["dtype"]]).reshape(meta["shape"])
                    t = t.to(device=device, non_blocking=True, copy=False)
                    kvs = (((expected_name, t),) if sd_ops is None else sd_ops.apply_to_key_value(expected_name, t))
                    for key, v in kvs:
                        size += v.nbytes
                        dtype.add(v.dtype)
                        sd[key] = v
        return StateDict(sd=sd, device=device, size=size, dtype=dtype)

    SafetensorsStateDictLoader.load = _patched_load
    print("[FUSE-PATCH] SafetensorsStateDictLoader.load replaced (chunked-read)")

def _estimate_ltx_model_download_gb():
    """Conservative remote-size estimate used only when the local cache is incomplete."""
    ltx_files = [
        "ltx-2.3-22b-distilled-1.1.safetensors",
        "ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
    ]
    total_bytes = estimate_hf_repo_bytes(
        "Lightricks/LTX-2.3",
        filenames=ltx_files,
    )
    total_bytes += estimate_hf_repo_bytes(
        "google/gemma-3-12b-it-qat-q4_0-unquantized",
    )
    safety_gb = max(
        0.0,
        float(os.environ.get("AIEROS_MODEL_DOWNLOAD_SAFETY_GB", "2.0")),
    )
    return total_bytes / BYTES_PER_GB + safety_gb


def _estimate_output_gb(duration, output_type="video"):
    """Estimate a conservative per-take output budget before encoding."""
    if output_type != "video":
        return max(0.02, float(os.environ.get("AIEROS_IMAGE_OUTPUT_BUDGET_GB", "0.05")))

    bitrate_mbps = max(
        1.0,
        float(os.environ.get("AIEROS_OUTPUT_ESTIMATE_BITRATE_MBPS", "100")),
    )
    safety_factor = max(
        1.0,
        float(os.environ.get("AIEROS_OUTPUT_ESTIMATE_SAFETY_FACTOR", "2.0")),
    )
    estimated_bytes = (
        max(0.1, float(duration))
        * bitrate_mbps
        * 1_000_000
        / 8.0
        * safety_factor
    )
    return estimated_bytes / BYTES_PER_GB


def load_pipeline_instance(gpu_id, *, allow_download=True, preserve_cuda_visible_devices=False):
    """Load LTX from cache, optionally permitting a guarded download.

    The production worker keeps its existing download behavior by default.
    Sidecar services pass allow_download=False unless the operator explicitly
    opts in; scheduler-provided CUDA visibility is preserved in that mode.
    """
    if not preserve_cuda_visible_devices or "CUDA_VISIBLE_DEVICES" not in os.environ:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    ensure_ltx_runtime()
    apply_fuse_patches()

    from ltx_core.quantization import QuantizationPolicy
    from ltx_pipelines.distilled import DistilledPipeline

    print(f"[GPU {gpu_id}] Verifying LTX Models in Local Cache...")
    
    def robust_download(func, **kwargs):
        """Fail-safe mechanism for interrupted or dropped proxy downloads."""
        for attempt in range(5):
            try:
                return func(**kwargs)
            except Exception as e:
                print(f"[GPU {gpu_id}] Download interrupted: {e}. Retrying {attempt+1}/5 in 10s...")
                time.sleep(10)
        raise RuntimeError(f"[GPU {gpu_id}] Fatal: Could not download required weights.")

    try:
        distilled_checkpoint_path = hf_hub_download(repo_id="Lightricks/LTX-2.3", filename="ltx-2.3-22b-distilled-1.1.safetensors", local_files_only=True)
        spatial_upsampler_path = hf_hub_download(repo_id="Lightricks/LTX-2.3", filename="ltx-2.3-spatial-upscaler-x2-1.1.safetensors", local_files_only=True)
        gemma_root = snapshot_download(repo_id="google/gemma-3-12b-it-qat-q4_0-unquantized", local_files_only=True)
        print(f"[GPU {gpu_id}] Cache hit! Models verified offline.")
    except Exception as cache_error:
        if not allow_download:
            raise RuntimeError(
                "LTX model cache is incomplete. This launch is cache-only; "
                "restore the approved local cache or restart with --allow-download "
                "after verifying OEC storage admission."
            ) from cache_error
        print(f"[GPU {gpu_id}] Cache miss or partial. Estimating required download size before transfer...")
        required_gb = _estimate_ltx_model_download_gb()
        print(f"[GPU {gpu_id}] Conservative model download budget: {required_gb:.2f} GB")

        with managed_storage_operation(
            "models",
            required_gb=required_gb,
            require_fresh_quota=True,
            minimum_free_gb=float(os.environ.get("AIEROS_MODEL_MIN_FREE_GB", "2.0")),
        ):
            distilled_checkpoint_path = robust_download(
                hf_hub_download,
                repo_id="Lightricks/LTX-2.3",
                filename="ltx-2.3-22b-distilled-1.1.safetensors",
            )
            spatial_upsampler_path = robust_download(
                hf_hub_download,
                repo_id="Lightricks/LTX-2.3",
                filename="ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
            )
            gemma_root = robust_download(
                snapshot_download,
                repo_id="google/gemma-3-12b-it-qat-q4_0-unquantized",
            )

    print(f"[GPU {gpu_id}] Loading DistilledPipeline...")
    pipeline = DistilledPipeline(
        distilled_checkpoint_path=distilled_checkpoint_path,
        spatial_upsampler_path=spatial_upsampler_path,
        gemma_root=gemma_root,
        loras=[],
        quantization=QuantizationPolicy.fp8_cast(),
    )
    print(f"[GPU {gpu_id}] Pipeline ready!")
    return pipeline

@torch.inference_mode()
def generate_asset(pipeline, target_gpu_id, input_image, prompt: str, duration: float, enhance_prompt: bool = True, seed: int = 42, randomize_seed: bool = True, height: int = 1024, width: int = 1536, output_type: str = "video", fps: float = 24.0):
    from ltx_core.model.video_vae import TilingConfig, get_video_chunks_number
    from ltx_pipelines.utils.args import ImageConditioningInput
    from ltx_pipelines.utils.media_io import encode_video
    
    if len(prompt) > 800:
        print(f"[GPU {target_gpu_id}] Prompt too long ({len(prompt)} chars). Truncating to 800 chars to prevent tokenizer crash.")
        prompt = prompt[:800]

    resolutions_to_try = [(width, height), (1024, 576)]
    current_seed = random.randint(0, MAX_SEED) if randomize_seed else int(seed)
    
    for attempt, (w, h) in enumerate(resolutions_to_try):
        try:
            import gc
            gc.collect()
            torch.cuda.empty_cache()
            
            w = int(round(w / 64.0)) * 64
            h = int(round(h / 64.0)) * 64
            
            num_frames = ((int(duration * fps) - 1 + 7) // 8) * 8 + 1
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"{timestamp}_{output_type}_{MODEL_TYPE}"
            print(f"[GPU {target_gpu_id}] Generating: {w}x{h}, {num_frames} frames ({duration}s @ {fps}fps), seed={current_seed}, type={output_type}")
            
            images = []
            if input_image is not None:
                input_filename = f"{timestamp}_{OUTPUT_TYPE_IMAGE}_input_{MODEL_TYPE}.jpg"
                temp_image_path = AIEROS_INPUT_DIR / input_filename
                if hasattr(input_image, "save"): 
                    input_image.save(temp_image_path)
                else: 
                    temp_image_path = Path(input_image)
                images = [ImageConditioningInput(path=str(temp_image_path), frame_idx=0, strength=1.0)]

            tiling_config = TilingConfig.default()
            video_chunks_number = get_video_chunks_number(num_frames, tiling_config)

            video, audio = pipeline(
                prompt=prompt, seed=current_seed, height=h, width=w,
                num_frames=num_frames, frame_rate=fps, images=images,
                tiling_config=tiling_config, enhance_prompt=enhance_prompt,
            )

            output_video_path = AIEROS_OUTPUT_DIR / f"{base_filename}.mp4"
            output_json_path = AIEROS_OUTPUT_DIR / f"{base_filename}_info.json"

            output_budget_gb = _estimate_output_gb(duration, output_type)
            print(
                f"[GPU {target_gpu_id}] Output storage budget: "
                f"{output_budget_gb:.3f} GB for this take"
            )

            metadata = {
                "timestamp": timestamp,
                "model_type": MODEL_TYPE,
                "output_type": output_type,
                "file_name": f"{base_filename}.mp4",
                "generation_parameters": {
                    "prompt": prompt, "enhance_prompt": enhance_prompt, "duration_seconds": duration,
                    "frame_rate": fps, "total_frames": num_frames,
                    "resolution": {"width": w, "height": h}, "seed": current_seed,
                    "randomize_seed": randomize_seed, "image_conditioned": input_image is not None,
                    "target_gpu_id": target_gpu_id,
                    "audio_muted": True
                }
            }
            with managed_storage_operation(
                "outputs",
                required_gb=output_budget_gb,
                require_fresh_quota=False,
                minimum_free_gb=float(os.environ.get("AIEROS_OUTPUT_MIN_FREE_GB", "0.05")),
            ):
                encode_video(
                    video=video,
                    fps=fps,
                    audio=None,
                    output_path=str(output_video_path),
                    video_chunks_number=video_chunks_number,
                )

                with open(output_json_path, "w", encoding="utf-8") as json_file:
                    json.dump(metadata, json_file, indent=4)

            print(f"[GPU {target_gpu_id}] Saved SILENT {output_type} to: {output_video_path}")
            return str(output_video_path), str(output_json_path), current_seed
        
        except torch.OutOfMemoryError:
            print(f"[GPU {target_gpu_id}] CRITICAL: CUDA Out of Memory at {w}x{h}!")
            import gc
            gc.collect()
            torch.cuda.empty_cache()
            
            if attempt < len(resolutions_to_try) - 1:
                print(f"[GPU {target_gpu_id}] Retrying generation in Safe Mode (Lower Resolution)...")
                continue
            else:
                print(f"[GPU {target_gpu_id}] Safe Mode also OOM'd. VRAM exhausted. Aborting take.")
                return None, None, current_seed
                
        except Exception as e:
            import traceback
            print(f"[GPU {target_gpu_id}] Error: {str(e)}\n{traceback.format_exc()}")
            import gc
            gc.collect()
            torch.cuda.empty_cache()
            print(f"[SYSTEM] Generation failed. Dumped VRAM cache to prevent hoarding on GPU {target_gpu_id}.")
            return None, None, current_seed
            
    return None, None, current_seed

# ==============================================================================
# 6. WORKER PROCESS LOGIC
# ==============================================================================
def worker_process(gpu_id, sync_barrier=None, master_gpu="0", should_purge=True, cluster_gpus=0):
    log_path = Path(SYSTEM_DIRS['logs']) / f"worker_GPU{gpu_id}.log"
    sys.stdout = DualLogger(str(log_path))
    sys.stderr = sys.stdout

    # FIX: Robustly separated queue submission directly to PENDING_QA, bypassing external daemons.
    def submit_to_qa_queue(vid_path, json_path):
        try:
            with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
                conn.execute('''CREATE TABLE IF NOT EXISTS assets (
                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    asset_path TEXT NOT NULL,
                                    json_path TEXT NOT NULL,
                                    total_size_bytes INTEGER NOT NULL,
                                    status TEXT DEFAULT 'PENDING_UPLOAD',
                                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                                )''')
                size = os.path.getsize(vid_path) + os.path.getsize(json_path)
                conn.execute(
                    "INSERT INTO assets (asset_path, json_path, status, total_size_bytes) VALUES (?, ?, 'PENDING_QA', ?)",
                    (vid_path, json_path, size)
                )
                print(f"[GPU {gpu_id}] Asset submitted to QA Node (Status: PENDING_QA)")
        except Exception as e:
            print(f"[GPU {gpu_id}] Database Error submitting to QA queue: {e}")

    pipeline = load_pipeline_instance(gpu_id)
    
    # ---------------------------------------------------------
    # MULTI-GPU SYNCHRONIZATION & PURGE MECHANIC
    if cluster_gpus > 1:
        print(f"[GPU {gpu_id}] Executing Distributed Cluster Purge...")
        ClusterPurgeManager.sync_and_purge(
            "Lightricks/LTX-2.3", cluster_gpus, f"GPU {gpu_id}"
        )
        ClusterPurgeManager.sync_and_purge(
            "google/gemma-3-12b-it-qat-q4_0-unquantized", cluster_gpus, f"GPU {gpu_id}"
        )
    elif sync_barrier:
        print(f"[GPU {gpu_id}] VRAM loaded. Waiting for local node synchronization...")
        sync_barrier.wait() 
        
        if gpu_id == master_gpu and should_purge:
            print(f"\n[SYSTEM] Local sync complete. Master GPU {gpu_id} executing Load & Purge...")
            DiskPurgeManager.purge_hf_model("Lightricks/LTX-2.3")
            DiskPurgeManager.purge_hf_model("google/gemma-3-12b-it-qat-q4_0-unquantized")
            
        sync_barrier.wait() 
        print(f"[GPU {gpu_id}] Local sync complete. Proceeding to job queue.")
        
    else:
        if should_purge:
            DiskPurgeManager.purge_hf_model("Lightricks/LTX-2.3")
            DiskPurgeManager.purge_hf_model("google/gemma-3-12b-it-qat-q4_0-unquantized")

    print(f"\n[GPU {gpu_id}] Worker Mode Active. Polling for JSON jobs...")

    active_processing_file = None

    while True:
        try:
            job_files = glob.glob(str(JOB_DIR / "*.json"))
            job_files = [f for f in job_files if f.endswith(".json")]
            
            job_files.sort() 
            
            if not job_files:
                time.sleep(5)
                continue
                
            target_job = job_files[0]
            active_processing_file = target_job + ".processing"
            
            try:
                os.rename(target_job, active_processing_file)
            except FileNotFoundError:
                active_processing_file = None
                continue
            except OSError:
                time.sleep(1)
                continue

            with open(active_processing_file, 'r') as f:
                job = json.load(f)
                
            print(f"\n[GPU {gpu_id}] Processing Job: {os.path.basename(target_job)}")
            
            prompt = job.get("prompt", "Cinematic landscape, 4k, professional cinematography")
            image_path = job.get("image_path", None)
            duration = job.get("duration", 3.0) 
            width = job.get("width", 1536)
            height = job.get("height", 1024) 
            fps = job.get("fps", 24.0)
            
            enhance = False 
            
            num_takes = job.get("num_takes", 1) 
            output_type = job.get("output_type", "video")
            
            success_count = 0
            for take in range(num_takes):
                print(f"[GPU {gpu_id}] -> Take {take + 1}/{num_takes}...")
                vid_path, json_path, final_seed = generate_asset(
                    pipeline, gpu_id, image_path, prompt, duration, enhance, 0, True, height, width, output_type, fps
                )
                
                if vid_path and json_path:
                    success_count += 1
                    submit_to_qa_queue(vid_path, json_path)
                elif not vid_path:
                    print(f"[GPU {gpu_id}] -> Take {take + 1} failed. Skipping to next.")
            
            if success_count > 0:
                os.remove(active_processing_file)
                print(f"[GPU {gpu_id}] Job completed ({success_count}/{num_takes} successful)")
            else:
                failed_path = active_processing_file.replace(".processing", ".failed")
                os.rename(active_processing_file, failed_path)
                print(f"[GPU {gpu_id}] FATAL: All takes failed. Job renamed to .failed")
                
            active_processing_file = None

        except KeyboardInterrupt:
            if active_processing_file and os.path.exists(active_processing_file):
                os.rename(active_processing_file, active_processing_file.replace(".processing", ""))
            break
        except Exception as e:
            print(f"[GPU {gpu_id}] Error processing job: {e}")
            if active_processing_file and os.path.exists(active_processing_file):
                os.rename(active_processing_file, active_processing_file.replace(".processing", ".error"))
            active_processing_file = None
            time.sleep(5)

# ==============================================================================
# 7. MASTER EXECUTION & ROUTING
# ==============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LTX-2.3 Multi-GPU Worker")
    parser.add_argument("--gpus", type=str, default="1,2,3", help="Comma-separated list of GPUs to use (e.g., 1,2,3)")
    parser.add_argument("--mode", type=str, default="WORKER_PARALLEL", choices=["WORKER_PARALLEL", "WORKER_SINGLE", "GRADIO"])
    parser.add_argument("--purge", action="store_true", default=True, help="Safely purge models from NVMe disk after loading into VRAM")
    parser.add_argument("--no-purge", dest="purge", action="store_false", help="Keep models on disk")
    parser.add_argument("--clean-state", action="store_true", help="Wipe existing model caches before downloading (Fixes corrupt downloads)")
    parser.add_argument("--cluster-gpus", type=int, default=0, help="Total expected GPUs across ALL nodes for distributed purge sync (e.g., 11)")
    args = parser.parse_args()

    AVAILABLE_GPUS = [g.strip() for g in args.gpus.split(",") if g.strip()]
    
    if args.clean_state:
        print("\n[SYSTEM] --clean-state triggered. Wiping existing Hugging Face caches for LTX and Gemma...")
        DiskPurgeManager.purge_hf_model("Lightricks/LTX-2.3")
        DiskPurgeManager.purge_hf_model("google/gemma-3-12b-it-qat-q4_0-unquantized")
        print("[SYSTEM] Clean state achieved. Proceeding to fresh download...\n")

    orphans = glob.glob(str(JOB_DIR / "*.processing"))
    for orphan in orphans:
        try:
            os.rename(orphan, orphan.replace(".processing", ""))
            print(f"[SYSTEM] Swept orphaned file back to queue: {os.path.basename(orphan)}")
        except Exception:
            pass

    if args.mode == "GRADIO":
        target = get_best_gpu()
        print(f"\n[SYSTEM] Launching Gradio UI on GPU {target}...")
        pipeline = load_pipeline_instance(target)
        
        def detect_aspect_ratio(image) -> str:
            if image is None: return "16:9"
            w, h = image.size if hasattr(image, "size") else image.shape[:2]
            ratio = w / h
            candidates = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0}
            return min(candidates, key=lambda k: abs(ratio - candidates[k]))

        def on_image_upload(image, high_res):
            aspect = detect_aspect_ratio(image)
            tier = "high" if high_res else "low"
            w, h = RESOLUTIONS[tier][aspect]
            return gr.update(value=w), gr.update(value=h)

        def on_highres_toggle(image, high_res):
            aspect = detect_aspect_ratio(image)
            tier = "high" if high_res else "low"
            w, h = RESOLUTIONS[tier][aspect]
            return gr.update(value=w), gr.update(value=h)

        def gradio_wrapper(*args):
            vid, json_path, seed = generate_asset(pipeline, target, *args, output_type="video", fps=24.0)
            return vid, seed

        with gr.Blocks(title="LTX-2.3 Distilled") as demo:
            gr.Markdown("# LTX-2.3 Distilled (22B): Interactive Testing Interface")
            with gr.Row():
                with gr.Column():
                    input_image = gr.Image(label="Input Image (Optional)", type="pil")
                    prompt = gr.Textbox(label="Prompt", value="Arri Alexa footage, 35mm film grain. A tight macro shot of glowing bioluminescent moss on a wet rock, extremely shallow depth of field, f/2.8, smooth cinematic pan.", lines=3)
                    with gr.Row():
                        duration = gr.Slider(label="Duration (seconds)", minimum=1.0, maximum=10.0, value=3.0, step=0.1)
                        with gr.Column():
                            enhance_prompt = gr.Checkbox(label="Enhance Prompt", value=False)
                            high_res = gr.Checkbox(label="High Resolution", value=True)
                    generate_btn = gr.Button("Generate Video", variant="primary", size="lg")
                    with gr.Accordion("Advanced Settings", open=False):
                        seed = gr.Slider(label="Seed", minimum=0, maximum=MAX_SEED, value=10, step=1)
                        randomize_seed = gr.Checkbox(label="Randomize Seed", value=True)
                        with gr.Row():
                            width = gr.Number(label="Width", value=1536, precision=0)
                            height = gr.Number(label="Height", value=1024, precision=0)
                with gr.Column():
                    output_video = gr.Video(label="Generated Video", autoplay=True)

            input_image.change(fn=on_image_upload, inputs=[input_image, high_res], outputs=[width, height])
            high_res.change(fn=on_highres_toggle, inputs=[input_image, high_res], outputs=[width, height])
            generate_btn.click(
                fn=gradio_wrapper,
                inputs=[input_image, prompt, duration, enhance_prompt, seed, randomize_seed, height, width],
                outputs=[output_video, seed],
            )

        demo.launch(server_name="0.0.0.0", server_port=7860, inline=True, share=False)

    else:
        try:
            mp.set_start_method('spawn', force=True)
        except RuntimeError:
            pass 

        processes = []
        try:
            if args.mode == "WORKER_PARALLEL":
                print(f"[SYSTEM] Launching {len(AVAILABLE_GPUS)} concurrent GPU workers...")
                
                sync_barrier = mp.Barrier(len(AVAILABLE_GPUS)) if (len(AVAILABLE_GPUS) > 1 and args.cluster_gpus <= 1) else None
                master_gpu = AVAILABLE_GPUS[0] if AVAILABLE_GPUS else "0"
                
                for gpu in AVAILABLE_GPUS:
                    p = mp.Process(target=worker_process, args=(gpu, sync_barrier, master_gpu, args.purge, args.cluster_gpus))
                    p.start()
                    processes.append(p)
                    time.sleep(5)
                    
            elif args.mode == "WORKER_SINGLE":
                target = get_best_gpu()
                print(f"[SYSTEM] Launching SINGLE worker on GPU {target}...")
                p = mp.Process(target=worker_process, args=(target, None, target, args.purge, args.cluster_gpus))
                p.start()
                processes.append(p)

            while True:
                time.sleep(1)
                if all(not p.is_alive() for p in processes):
                    break

        except KeyboardInterrupt:
            print("\n[SYSTEM] Master Shutdown Triggered. Broadcasting stop signals...")
            for p in processes:
                p.join(timeout=10)
                if p.is_alive():
                    p.terminate()
            print("[SYSTEM] All GPUs successfully shut down.")