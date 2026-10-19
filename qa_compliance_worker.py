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
os.makedirs(REJECTED_DIR, exist_ok=True)

try:
    from qwen_vl_utils import process_vision_info
except ImportError:
    process_vision_info = None
    print("[QA-NODE] qwen-vl-utils is not installed; VLM QA cannot run until the dependency is installed.")

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
        except Exception:
            pass

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
        image_inputs, video_inputs = process_vision_info(messages)
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
            
        frame_path = media_path.replace(".mp4", "_qa_frame.jpg")
        try:
            subprocess.run([
                "ffmpeg", "-y", "-ss", "00:00:02", "-i", media_path, 
                "-vframes", "1", "-q:v", "2", frame_path
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            return frame_path, True
        except Exception as e:
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
                require_fresh_quota=False,
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

def process_qa_queue(purge_after_load=True, gpu_id=0):
    qa = QANode(gpu_id=gpu_id, purge_after_load=purge_after_load)
    
    sweep_stuck_jobs(QUEUE_DB_PATH)
    
    print(f"\n[QA-NODE] Assembly Line Active. Polling database for 'PENDING_QA' assets...")

    is_running = True
    def handle_sig(sig, frame):
        nonlocal is_running
        print("\n[QA-NODE] Shutdown signal received. Exiting loop safely...")
        is_running = False
    
    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    while is_running:
        try:
            with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, asset_path, json_path FROM assets WHERE status = 'PENDING_QA' LIMIT 1")
                row = cursor.fetchone()
                
            if not row:
                time.sleep(5)
                if random.random() < 0.1:
                    sweep_stuck_jobs(QUEUE_DB_PATH)
                continue
                
            record_id, raw_vid_path, json_path = row
            
            with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
                conn.execute("UPDATE assets SET status = 'PROCESSING_QA' WHERE id = ?", (record_id,))
                
            print(f"\n[QA-NODE] Evaluating Asset ID: {record_id} | {os.path.basename(raw_vid_path)}")
            
            if not os.path.exists(raw_vid_path) or not os.path.exists(json_path):
                print(f"[QA-NODE] Files missing from disk. Deleting record.")
                with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
                    conn.execute("DELETE FROM assets WHERE id = ?", (record_id,))
                continue
            
            with open(json_path, 'r') as f:
                metadata = json.load(f)
                
            frame_path, is_extracted = qa.extract_evaluation_frame(raw_vid_path)
            if frame_path:
                analysis = qa.analyze_and_tag(frame_path)
                if is_extracted:
                    os.remove(frame_path) 
                
                category = analysis.get("category", 1)
                
                if category == 1:
                    reason = analysis.get("rejection_reason", "Failed Adobe Stock Guidelines")
                    print(f"[QA-NODE] ❌ REJECTED: {reason}. Moving to trash.")
                    
                    shutil.move(raw_vid_path, os.path.join(REJECTED_DIR, os.path.basename(raw_vid_path)))
                    os.remove(json_path)
                    
                    with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
                        conn.execute("DELETE FROM assets WHERE id = ?", (record_id,))
                    continue
                    
                cat_string = "Photorealistic / Human-Created" if category == 3 else "AI-Generated Style"
                print(f"[QA-NODE] ✅ PASSED. Category: {cat_string}")
                
                metadata["qa_category"] = category
                metadata["seo_title"] = analysis.get("title", "Cinematic AI Generation")
                metadata["seo_keywords"] = analysis.get("keywords", [])
                metadata["qa_passed"] = True
            
                improved_vid_path = raw_vid_path.replace(".mp4", "_improved.mp4")
                success = qa.improve_and_standardize_video(raw_vid_path, improved_vid_path)
                
                if success:
                    if raw_vid_path.lower().endswith(('.mp4', '.webm', '.avi')):
                        os.replace(improved_vid_path, raw_vid_path)
                        
                    with open(json_path, "w") as f:
                        json.dump(metadata, f, indent=4)
                        
                    new_size = os.path.getsize(raw_vid_path) + os.path.getsize(json_path)
                    with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
                        mark_upload_pending(conn, record_id, new_size)
                    print(f"[QA-NODE] QA Complete. Asset handed over to HF Upload Daemon.")
                else:
                    print(f"[QA-NODE] Quality Improver failed. Rejecting asset.")
                    with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
                        conn.execute("UPDATE assets SET status = 'FAILED_IMPROVER' WHERE id = ?", (record_id,))
            else:
                 print(f"[QA-NODE] QA Extraction failed. Check if FFmpeg is installed/working.")
                 with sqlite3.connect(QUEUE_DB_PATH, timeout=30) as conn:
                        conn.execute("UPDATE assets SET status = 'FAILED_QA_EXTRACTION' WHERE id = ?", (record_id,))
                        
        except Exception as e:
            print(f"[QA-NODE] Fatal error in QA loop: {e}")
            time.sleep(10)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QA & Compliance Worker Node")
    parser.add_argument("--purge", action="store_true", help="Purge model from disk after loading into VRAM (Default)")
    parser.add_argument("--no-purge", dest="purge", action="store_false", help="Keep model on disk after loading")
    parser.add_argument("--gpu", type=int, default=0, help="Physical GPU index selected before importing Torch")
    parser.set_defaults(purge=True)
    args = parser.parse_args()
    
    print("[SYSTEM] Starting QA Compliance Worker...")
    process_qa_queue(purge_after_load=args.purge, gpu_id=args.gpu)