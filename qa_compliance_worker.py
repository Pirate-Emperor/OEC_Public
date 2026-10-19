# 1. CORE CONFIGURATION (Locks in proxies, storage, and auth)
import core_config
from core_config import SYSTEM_DIRS, QUEUE_DB_PATH

import os
import sys
import time
import json
import sqlite3
import subprocess
import shutil
import glob
import signal
import argparse
import traceback
import random
from pathlib import Path
from PIL import Image

# STRICT DISK MANAGER IMPORT
from purge_manager import DiskPurgeManager
from storage_manager import managed_storage_operation
from storage_policy import BYTES_PER_GB, estimate_hf_repo_bytes
from asset_status import mark_upload_pending

# ==============================================================================
# 2. GLOBAL LOGGING & CRASH CATCHER (Must be defined first)
# ==============================================================================
class DualLogger:
    """Writes to both the screen buffer and a text file simultaneously."""
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log_file = open(filepath, "a", buffering=1)
    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.flush()
    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

# Ensure logs directory exists
log_dir = SYSTEM_DIRS.get('logs', SYSTEM_DIRS['outputs'])
os.makedirs(log_dir, exist_ok=True)
log_path = os.path.join(log_dir, "qa_worker.log")

# Override standard output and error immediately
logger = DualLogger(log_path)
sys.stdout = logger
sys.stderr = logger

# Route fatal crashes directly into the log file
def global_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    print("\n[CRITICAL FATAL ERROR] Unhandled Exception Caught:", file=sys.stderr)
    traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)

sys.excepthook = global_exception_handler

# ==============================================================================
# QA & COMPLIANCE WORKER (Assign to GPU 0)
# ==============================================================================

REJECTED_DIR = os.path.join(SYSTEM_DIRS['outputs'], "rejected")

class QANode:
    def __init__(self, gpu_id=0, purge_after_load=True):
        self.gpu_id = str(gpu_id)
        if not self.gpu_id.isdigit():
            raise ValueError("gpu_id must be a non-negative physical GPU index")
        self.purge_after_load = purge_after_load
        # Set physical-device visibility before the first Torch import.
        os.environ["CUDA_VISIBLE_DEVICES"] = self.gpu_id
        import torch
        self.torch = torch
        self.device = "cuda" if self.torch.cuda.is_available() else "cpu"
        # qwen-vl-utils can import Torch transitively too; import it only after the
        # physical CUDA device has been selected for this QA worker.
        try:
            from qwen_vl_utils import process_vision_info
            self.process_vision_info = process_vision_info
        except ImportError:
            self.process_vision_info = None
            print("[QA-NODE] qwen-vl-utils is not installed; VLM QA cannot run until the dependency is installed.")
        self.processor = None
        self.model = None
        self.repo_id = "Qwen/Qwen2-VL-7B-Instruct"

    def _ensure_downloaded_robustly(self):
        from huggingface_hub import snapshot_download
        
        try:
            snapshot_download(
                repo_id=self.repo_id,
                cache_dir=SYSTEM_DIRS["models"],
                local_files_only=True,
            )
            print(f"[QA-NODE-GPU{self.gpu_id}] Model verified in local HF cache.")
            return
        except Exception as cache_exc:
            cache_only = os.environ.get("OEC_QA_CACHE_ONLY", "").strip().lower() in {"1", "true", "yes"}
            if cache_only:
                raise RuntimeError(
                    f"{self.repo_id} is not fully available in the local Hugging Face cache; "
                    "OEC_QA_CACHE_ONLY=1 forbids any model download"
                ) from cache_exc

        print(f"[QA-NODE-GPU{self.gpu_id}] Model missing or incomplete. Estimating required download size...")
        required_gb = estimate_hf_repo_bytes(self.repo_id) / BYTES_PER_GB
        safety_gb = max(
            0.0,
            float(os.environ.get("AIEROS_MODEL_DOWNLOAD_SAFETY_GB", "2.0")),
        )
        required_gb += safety_gb
        print(
            f"[QA-NODE-GPU{self.gpu_id}] Conservative model download budget: "
            f"{required_gb:.2f} GB"
        )

        offline_status = os.environ.get("HF_HUB_OFFLINE", "0")
        os.environ["HF_HUB_OFFLINE"] = "0"

        try:
            with managed_storage_operation(
                "models",
                required_gb=required_gb,
                require_fresh_quota=True,
                minimum_free_gb=float(
                    os.environ.get("AIEROS_MODEL_MIN_FREE_GB", "2.0")
                ),
            ):
                for attempt in range(5):
                    try:
                        snapshot_download(
                            repo_id=self.repo_id,
                            cache_dir=SYSTEM_DIRS["models"],
                        )
                        print(f"[QA-NODE-GPU{self.gpu_id}] Download successful.")
                        break
                    except Exception as e:
                        sleep_time = 15 * (attempt + 1)
                        print(
                            f"[QA-NODE-GPU{self.gpu_id}] Download error: "
                            f"{type(e).__name__}. Retrying in {sleep_time}s..."
                        )
                        time.sleep(sleep_time)
                else:
                    raise RuntimeError(
                        f"Failed to download {self.repo_id} after 5 attempts."
                    )
        finally:
            os.environ["HF_HUB_OFFLINE"] = offline_status

    def load_vlm(self):
        torch = self.torch
        print(f"[QA-NODE-GPU{self.gpu_id}] Initializing Qwen2-VL-7B-Instruct for Strict Compliance Checking...")
        from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
        
        self._ensure_downloaded_robustly()
        
        print(f"[QA-NODE-GPU{self.gpu_id}] Pushing weights into VRAM...")
        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            self.repo_id, 
            torch_dtype=torch.bfloat16, 
            device_map="auto",
            cache_dir=SYSTEM_DIRS['models'],
            local_files_only=True
        )
        self.processor = AutoProcessor.from_pretrained(
            self.repo_id, 
            cache_dir=SYSTEM_DIRS['models'],
            local_files_only=True
        )
        print(f"[QA-NODE-GPU{self.gpu_id}] VLM Fully Loaded into VRAM.")
        
        if self.purge_after_load:
            DiskPurgeManager.purge_hf_model(self.repo_id)

    def analyze_and_tag(self, image_path):
        if not self.model: self.load_vlm()
        
        image = Image.open(image_path)
        
        prompt = (
            "You are an elite QA reviewer for Adobe Stock. Analyze this frame strictly.\n"
            "Rules: NO artist names, NO fictional characters, NO logos/trademarks, NO recognizable human faces.\n"
            "If there is a human, it MUST be an anonymous silhouette, unrecognizable top-down angle, or hands/body only.\n"
            "Categorize this asset into exactly one of these 3 buckets:\n"
            "1: 'Unpublishable' (Contains text, watermarks, severe anatomical mutations, copyrighted logos, recognizable human faces, or gibberish).\n"
            "2: 'AI-generated' (Clean and usable, but has obvious AI aesthetics like surrealism or perfectly smooth synthetic styling).\n"
            "3: 'Photorealistic' (Flawless, looks like real camera footage, no AI tells, faceless/anonymous human elements if any).\n"
            "Output ONLY valid JSON in this exact format:\n"
            "{\n"
            "  \"category\": 1,\n"
            "  \"rejection_reason\": \"Explain why if category 1, otherwise null\",\n"
            "  \"title\": \"Highly descriptive commercial title, max 150 chars\",\n"
            "  \"keywords\": [\"array\", \"of\", \"exactly\", \"30\", \"seo\", \"keywords\"]\n"
            "}"
        )
        
        messages = [
            {"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}
        ]
        
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        if self.process_vision_info is None:
            raise RuntimeError("qwen-vl-utils is unavailable; cannot perform Qwen2-VL QA")
        image_inputs, video_inputs = self.process_vision_info(messages)
        inputs = self.processor(
            text=[text], images=image_inputs, videos=video_inputs, padding=True, return_tensors="pt"
        ).to(self.device)
        
        generated_ids = self.model.generate(**inputs, max_new_tokens=512)
        generated_ids_trimmed = [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)]
        output_text = self.processor.batch_decode(generated_ids_trimmed, skip_special_tokens=True)[0]
        
        try:
            clean_json = output_text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)
        except Exception as e:
            print(f"[QA-NODE] Failed to parse VLM output: {e}\nRaw Output: {output_text}")
            return {"category": 1, "rejection_reason": "VLM parsing failure"}

    def extract_evaluation_frame(self, media_path):
        """Extracts a frame if video, otherwise returns the image path directly."""
        if media_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            return media_path, False
            
        # Preserve the input extension and derive a sibling JPEG for any supported video.
        # String-replacing ".mp4" returned the original .webm/.avi path and could overwrite it.
        source_path = Path(media_path)
        frame_path = str(source_path.with_name(f"{source_path.stem}_qa_frame.jpg"))
        try:
            subprocess.run([
                "ffmpeg", "-y", "-ss", "00:00:02", "-i", media_path,
                "-vframes", "1", "-q:v", "2", frame_path
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            return frame_path, True
        except Exception as e:
            # Remove only a partial frame emitted by this exact extraction attempt.
            try:
                Path(frame_path).unlink(missing_ok=True)
            except OSError:
                pass
            print(f"[QA-NODE] Frame extraction failed: {e}")
            return None, False

    def improve_and_standardize_video(self, raw_vid_path, target_path):
        """Fixes AI melting endings by trimming 1.5s off the back and adds a 0.5s fade-out."""
        if not raw_vid_path.lower().endswith(('.mp4', '.webm', '.avi')):
            return True
            
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", raw_vid_path]
            duration = float(subprocess.check_output(cmd).decode().strip())
            
            trim_duration = max(1.0, duration - 1.5)
            fade_start = max(0.5, trim_duration - 0.5)
            
            print(f"[QA-NODE] Applying Quality Improver: Trimming to {trim_duration}s and fading out...")
            
            raw_size_gb = os.path.getsize(raw_vid_path) / BYTES_PER_GB
            with managed_storage_operation(
                "outputs",
                required_gb=max(0.05, raw_size_gb * 1.25),
                require_fresh_quota=True,
                minimum_free_gb=float(
                    os.environ.get("AIEROS_OUTPUT_MIN_FREE_GB", "0.05")
                ),
            ):
                subprocess.run([
                    "ffmpeg", "-y", "-i", raw_vid_path,
                    "-vf", f"fade=t=out:st={fade_start}:d=0.5",
                    "-t", str(trim_duration),
                    "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
                    "-crf", "16", "-r", "24",
                    "-movflags", "+faststart",
                    target_path
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            return True
        except Exception as e:
            print(f"[QA-NODE] Quality Improver failed: {e}")
            return False

def sweep_stuck_jobs(db_path):
    """Recovers crashed jobs."""
    try:
        # FIX: Reverted the cross-queue extraction hack.
        # Now strictly isolated to recovering its own processing crashes to maintain safe linear pipeline flow.
        with sqlite3.connect(db_path, timeout=30) as conn:
            cursor = conn.cursor()
            
            cursor.execute("UPDATE assets SET status = 'PENDING_QA' WHERE status = 'PROCESSING_QA'")
            if cursor.rowcount > 0:
                print(f"[QA-NODE] 🧹 Recovered {cursor.rowcount} crashed jobs back to PENDING_QA.")
            conn.commit()
    except Exception as e:
        print(f"[QA-NODE] Failed to sweep DB: {e}")

def process_qa_queue(purge_after_load=True, gpu_id=0, asset_id=None, once=False):
    if once:
        if isinstance(asset_id, bool) or not isinstance(asset_id, int) or asset_id < 1:
            raise ValueError("targeted QA mode requires a positive --asset-id")
        if not os.path.isfile(QUEUE_DB_PATH):
            return "QUEUE_DATABASE_NOT_FOUND"
        # Check the selected row before importing/loading the 7B VLM.
        with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
            eligible = conn.execute(
                "SELECT 1 FROM assets WHERE id = ? AND status = 'PENDING_QA'",
                (asset_id,),
            ).fetchone()
        if not eligible:
            return "NOT_PENDING_QA"

    qa = QANode(gpu_id=gpu_id, purge_after_load=purge_after_load)
    # The continuous daemon recovers its own abandoned QA rows as before. A targeted
    # acceptance must never sweep unrelated PROCESSING_QA rows in the shared database.
    if not once:
        sweep_stuck_jobs(QUEUE_DB_PATH)

    print("\\n[QA-NODE] Assembly Line Active. Polling database for 'PENDING_QA' assets...")
    is_running = True
    def handle_sig(sig, frame):
        nonlocal is_running
        print("\\n[QA-NODE] Shutdown signal received. Exiting loop safely...")
        is_running = False

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    while is_running:
        record_id = asset_id if once else None
        try:
            with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
                cursor = conn.cursor()
                if once:
                    cursor.execute(
                        "SELECT id, asset_path, json_path FROM assets WHERE id = ? AND status = 'PENDING_QA' LIMIT 1",
                        (asset_id,),
                    )
                else:
                    cursor.execute(
                        "SELECT id, asset_path, json_path FROM assets WHERE status = 'PENDING_QA' LIMIT 1"
                    )
                row = cursor.fetchone()

            if not row:
                if once:
                    return "NOT_PENDING_QA"
                time.sleep(5)
                if random.random() < 0.1:
                    sweep_stuck_jobs(QUEUE_DB_PATH)
                continue

            record_id, raw_vid_path, json_path = row
            with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
                cursor = conn.execute(
                    "UPDATE assets SET status = 'PROCESSING_QA' WHERE id = ? AND status = 'PENDING_QA'",
                    (record_id,),
                )
                if cursor.rowcount != 1:
                    if once:
                        return "NOT_PENDING_QA"
                    continue

            print(f"\\n[QA-NODE] Evaluating Asset ID: {record_id} | {os.path.basename(raw_vid_path)}")
            if not os.path.exists(raw_vid_path) or not os.path.exists(json_path):
                print("[QA-NODE] Files missing from disk.")
                with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
                    if once:
                        conn.execute(
                            "UPDATE assets SET status = 'FAILED_MISSING_FILE' WHERE id = ?",
                            (record_id,),
                        )
                    else:
                        conn.execute("DELETE FROM assets WHERE id = ?", (record_id,))
                    conn.commit()
                if once:
                    return "FAILED_MISSING_FILE"
                continue

            with open(json_path, 'r', encoding='utf-8') as handle:
                metadata = json.load(handle)
            with managed_storage_operation(
                "outputs", required_gb=0.001, require_fresh_quota=True, minimum_free_gb=0.05
            ):
                frame_path, is_extracted = qa.extract_evaluation_frame(raw_vid_path)
            if frame_path:
                analysis = qa.analyze_and_tag(frame_path)
                if is_extracted:
                    os.remove(frame_path)
                category = analysis.get("category", 1)

                if category == 1:
                    reason = analysis.get("rejection_reason", "Failed Adobe Stock Guidelines")
                    print(f"[QA-NODE] REJECTED: {reason}. Moving to rejected.")
                    raw_size = os.path.getsize(raw_vid_path) if os.path.isfile(raw_vid_path) else 0
                    with managed_storage_operation(
                        "outputs", required_gb=max(0.001, raw_size / BYTES_PER_GB),
                        require_fresh_quota=True, minimum_free_gb=0.05,
                    ):
                        os.makedirs(REJECTED_DIR, exist_ok=True)
                        shutil.move(raw_vid_path, os.path.join(REJECTED_DIR, os.path.basename(raw_vid_path)))
                        if os.path.exists(json_path):
                            os.remove(json_path)
                    with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
                        conn.execute("DELETE FROM assets WHERE id = ?", (record_id,))
                        conn.commit()
                    if once:
                        return "REJECTED"
                    continue

                cat_string = "Photorealistic / Human-Created" if category == 3 else "AI-Generated Style"
                print(f"[QA-NODE] PASSED. Category: {cat_string}")
                metadata["qa_category"] = category
                metadata["seo_title"] = analysis.get("title", "Cinematic AI Generation")
                metadata["seo_keywords"] = analysis.get("keywords", [])
                metadata["qa_passed"] = True
                improved_vid_path = raw_vid_path.replace(".mp4", "_improved.mp4")
                success = qa.improve_and_standardize_video(raw_vid_path, improved_vid_path)
                if success:
                    if raw_vid_path.lower().endswith(('.mp4', '.webm', '.avi')):
                        os.replace(improved_vid_path, raw_vid_path)
                    with managed_storage_operation(
                        "outputs", required_gb=0.001, require_fresh_quota=True, minimum_free_gb=0.05
                    ):
                        with open(json_path, "w", encoding="utf-8") as handle:
                            json.dump(metadata, handle, indent=4)
                    new_size = os.path.getsize(raw_vid_path) + os.path.getsize(json_path)
                    with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
                        mark_upload_pending(conn, record_id, new_size)
                        conn.commit()
                    print("[QA-NODE] QA Complete. Asset handed over to HF Upload Daemon.")
                    if once:
                        return "PENDING_UPLOAD"
                else:
                    print("[QA-NODE] Quality Improver failed.")
                    with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
                        conn.execute("UPDATE assets SET status = 'FAILED_IMPROVER' WHERE id = ?", (record_id,))
                        conn.commit()
                    if once:
                        return "FAILED_IMPROVER"
            else:
                print("[QA-NODE] QA frame extraction failed. Check FFmpeg and input media.")
                with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
                    conn.execute("UPDATE assets SET status = 'FAILED_QA_EXTRACTION' WHERE id = ?", (record_id,))
                    conn.commit()
                if once:
                    return "FAILED_QA_EXTRACTION"

        except Exception as exc:
            print(f"[QA-NODE] Fatal error in QA loop: {type(exc).__name__}: {exc}")
            if once:
                try:
                    with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
                        conn.execute(
                            "UPDATE assets SET status = 'FAILED_QA_RUNTIME' WHERE id = ? AND status = 'PROCESSING_QA'",
                            (record_id,),
                        )
                        conn.commit()
                except Exception as state_exc:
                    print(f"[QA-NODE] Could not record targeted QA runtime failure: {type(state_exc).__name__}")
                raise
            time.sleep(10)

    return "STOPPED"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QA & Compliance Worker Node")
    parser.add_argument("--purge", action="store_true", help="Purge model from disk after loading into VRAM (Default)")
    parser.add_argument("--no-purge", dest="purge", action="store_false", help="Keep model on disk after loading")
    parser.add_argument("--gpu", type=int, default=0, help="Physical GPU index selected before importing Torch")
    parser.add_argument("--once", action="store_true", help="Process only the exact selected PENDING_QA row and exit.")
    parser.add_argument("--asset-id", type=int, help="Positive asset ID; required for --once, no fallback to other rows.")
    parser.add_argument(
        "--db-path",
        help="Optional run-scoped SQLite DB path; only accepted beneath outputs/oec-e2e-acceptance/ with --once --asset-id.",
    )
    parser.set_defaults(purge=True)
    args = parser.parse_args()
    if args.once and (args.asset_id is None or args.asset_id < 1):
        parser.error("--once requires --asset-id with a positive ID")
    if not args.once and args.asset_id is not None:
        parser.error("--asset-id can only be used with --once")
    if args.db_path:
        if not args.once or args.asset_id is None or args.asset_id < 1:
            parser.error("--db-path is permitted only with --once --asset-id ID")
        raw_db = Path(args.db_path).expanduser()
        if raw_db.is_symlink():
            parser.error("--db-path must not be a symlink")
        allowed_root = (Path(SYSTEM_DIRS["outputs"]).expanduser().resolve() / "oec-e2e-acceptance")
        try:
            resolved_db = raw_db.resolve(strict=True)
        except OSError:
            parser.error("--db-path must point to an existing run-scoped SQLite file")
        if (
            not resolved_db.is_file()
            or resolved_db.name != "upload_queue.db"
            or allowed_root not in resolved_db.parents
        ):
            parser.error("--db-path must be upload_queue.db beneath outputs/oec-e2e-acceptance/<run-id>/")
        QUEUE_DB_PATH = str(resolved_db)

    print("[SYSTEM] Starting QA Compliance Worker...")
    if args.once:
        try:
            outcome = process_qa_queue(
                purge_after_load=args.purge, gpu_id=args.gpu, asset_id=args.asset_id, once=True
            )
        except Exception as exc:
            print(f"[QA_ONCE] FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        if outcome == "PENDING_UPLOAD":
            print(f"[QA_ONCE] PASS asset_id={args.asset_id} status=PENDING_UPLOAD")
            raise SystemExit(0)
        if outcome == "REJECTED":
            print(f"[QA_ONCE] REJECTED asset_id={args.asset_id} (policy decision completed)")
            raise SystemExit(0)
        print(f"[QA_ONCE] FAIL asset_id={args.asset_id} outcome={outcome}", file=sys.stderr)
        raise SystemExit(1)
    process_qa_queue(purge_after_load=args.purge, gpu_id=args.gpu)