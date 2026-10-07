import os
import time
import sqlite3
import tarfile
import logging
import signal
import sys
import glob
import argparse
import json
import fcntl
from datetime import datetime
from pathlib import Path
from huggingface_hub import HfApi

# 1. IMPORT CORE CONFIG
from core_config import UPLOAD_BATCH_SIZE_GB, HF_DATASET_REPO, QUEUE_DB_PATH, SYSTEM_DIRS
from storage_manager import storage_preflight_path, managed_storage_operation

log_path = os.path.join(SYSTEM_DIRS['logs'], "upload_daemon.log")
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [HF-DAEMON] %(message)s',
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler(sys.stdout)
    ]
)

# ==============================================================================
# PART 1: THE QUEUE API (Imported by your Generator Scripts)
# ==============================================================================

class AssetQueue:
    """API for generator scripts to securely submit Asset/JSON pairs to the upload queue."""
    def __init__(self):
        self.db_path = QUEUE_DB_PATH
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_path TEXT NOT NULL,
                    json_path TEXT NOT NULL,
                    total_size_bytes INTEGER NOT NULL,
                    status TEXT DEFAULT 'PENDING',
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def submit(self, asset_path: str, json_path: str):
        """Called by generator scripts after files are fully saved."""
        try:
            asset_size = os.path.getsize(asset_path)
            json_size = os.path.getsize(json_path)
            total_size = asset_size + json_size
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO assets (asset_path, json_path, total_size_bytes) VALUES (?, ?, ?)",
                    (str(asset_path), str(json_path), total_size)
                )
                conn.commit()
            logging.info(f"Queued Pair: {Path(asset_path).name} & {Path(json_path).name} ({total_size / (1024**2):.2f} MB)")
        except Exception as e:
            logging.error(f"Failed to queue asset {asset_path}: {e}")

    def purge_queue(self, auto_confirm: bool = False):
        """
        Utility to clear out bad test data from the SQLite database.
        Does NOT delete the physical files, only resets the database queue.
        """
        if not auto_confirm:
            print(f"\n[WARNING] You are about to PURGE the entire upload queue at {self.db_path}")
            response = input("This will permanently delete all pending upload records. Proceed? (y/n): ")
            if response.lower() not in ['y', 'yes']:
                print("Purge cancelled. The database was not modified.")
                return
                
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM assets")
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='assets'")
                conn.commit()
                
            logging.info("Queue database purged successfully.")
            print("[QUEUE] Database successfully purged and reset to zero.")
        except Exception as e:
            logging.error(f"Failed to purge database: {e}")
            print(f"[QUEUE] Error purging database: {e}")

# ==============================================================================
# PART 2: THE BACKGROUND DAEMON (Runs independently 24/7)
# ==============================================================================

class HFUploadDaemon:
    def __init__(self, auto_confirm: bool = False):
        self.api = HfApi()
        self.batch_limit_bytes = UPLOAD_BATCH_SIZE_GB * (1024**3)
        self.partial_batch_max_age_seconds = max(
            60,
            int(os.environ.get("AIEROS_UPLOAD_PARTIAL_BATCH_MAX_AGE_SECONDS", "1800")),
        )
        self.archive_headroom_factor = max(
            1.05,
            float(os.environ.get("AIEROS_UPLOAD_ARCHIVE_HEADROOM_FACTOR", "1.15")),
        )
        self.archive_min_free_gb = max(
            0.1,
            float(os.environ.get("AIEROS_UPLOAD_ARCHIVE_MIN_FREE_GB", "1.0")),
        )
        self.db_path = QUEUE_DB_PATH
        self.is_running = True
        
        # --- FIX 1: ATOMIC SINGLE-INSTANCE LOCK ---
        os.makedirs(SYSTEM_DIRS['cache'], exist_ok=True)
        self.lock_file = open(os.path.join(SYSTEM_DIRS['cache'], 'daemon.lock'), 'w')
        try:
            fcntl.lockf(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            print("[CRITICAL] Another instance of hf_upload_daemon is already running!")
            print("To stop it, run: pkill -f hf_upload_daemon.py")
            sys.exit(0)
        
        # 1. Register graceful shutdown for Ctrl+C and Kill signals
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        
        # 2. Clean up any leftover tarballs from a previous crash
        self._cleanup_orphaned_tarballs()
        
        # Ensure repo exists with explicit confirmation
        try:
            if not self.api.repo_exists(repo_id=HF_DATASET_REPO, repo_type="dataset"):
                if not auto_confirm:
                    print(f"\n[WARNING] The Hugging Face Dataset repository '{HF_DATASET_REPO}' does NOT exist.")
                    response = input("Would you like to create this repository now? (y/n): ")
                    if response.lower() not in ['y', 'yes']:
                        print("[ERROR] Daemon startup aborted. A valid repository is required.")
                        exit(1)
                
                print(f"Creating dataset repository: {HF_DATASET_REPO}...")
                self.api.create_repo(repo_id=HF_DATASET_REPO, repo_type="dataset", private=True, exist_ok=True)
                logging.info(f"Target Dataset Repo created successfully: {HF_DATASET_REPO}")
            else:
                logging.info(f"Target Dataset Repo verified (Already exists): {HF_DATASET_REPO}")
                
        except Exception as e:
            logging.error(f"Failed to verify/create repo. Check HF_TOKEN or network connection. Error: {e}")
            exit(1)

    def _shutdown_handler(self, signum, frame):
        """Catches Ctrl+C and allows the current upload to finish before exiting."""
        print("\n[SYSTEM] Shutdown signal received. Waiting for current batch to finish (Press Ctrl+C again to force kill)...")
        self.is_running = False

    def _cleanup_orphaned_tarballs(self):
        """Deletes any half-written tar files left in the cache from a previous hard crash."""
        try:
            cache_path = SYSTEM_DIRS['cache']
            # Match the new timestamp-first naming convention
            orphans = glob.glob(os.path.join(cache_path, "*_batch_*.tar.gz"))
            for orphan in orphans:
                os.remove(orphan)
                logging.info(f"Cleaned up orphaned cache file: {Path(orphan).name}")
                
            # --- FIX 2: DB ROLLBACK RUNS ONLY ONCE AT STARTUP ---
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE assets SET status = 'PENDING' WHERE status = 'ARCHIVING'")
                if cursor.rowcount > 0:
                    logging.info(f"Recovered {cursor.rowcount} assets stuck in 'ARCHIVING' state from a previous proxy crash.")
                conn.commit()
                
        except Exception as e:
            logging.error(f"Failed to clean up cache/db: {e}")

    def _get_pending_batch(self):
        now = time.time()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, asset_path, json_path, total_size_bytes, timestamp "
                "FROM assets WHERE status = 'PENDING' ORDER BY id ASC"
            )
            rows = cursor.fetchall()

            batch_ids, batch_files = [], []
            current_size = 0
            oldest_timestamp = None

            for row in rows:
                row_id, a_path, j_path, size, timestamp = row

                if os.path.exists(a_path) and os.path.exists(j_path):
                    batch_ids.append(row_id)
                    batch_files.extend([a_path, j_path])
                    current_size += size

                    if oldest_timestamp is None:
                        try:
                            oldest_timestamp = datetime.strptime(
                                timestamp,
                                "%Y-%m-%d %H:%M:%S",
                            ).timestamp()
                        except (TypeError, ValueError):
                            oldest_timestamp = now

                    if current_size >= self.batch_limit_bytes:
                        break
                else:
                    cursor.execute(
                        "UPDATE assets SET status = 'FAILED_MISSING_FILE' WHERE id = ?",
                        (row_id,),
                    )

            conn.commit()

        if not batch_ids:
            return [], [], 0, False

        if current_size >= self.batch_limit_bytes:
            return batch_ids, batch_files, current_size, False

        age = max(0.0, now - (oldest_timestamp or now))
        if age >= self.partial_batch_max_age_seconds:
            logging.info(
                "Partial upload batch aged %.0fs; forcing flush of %.2f GB.",
                age,
                current_size / (1024**3),
            )
            return batch_ids, batch_files, current_size, True

        return [], [], 0, False

    def process_queue(self):
        logging.info("Daemon started. Polling queue in background...")
        while self.is_running:
            batch_ids, tar_path, batch_forced = [], None, False
            
            try:
                batch_ids, batch_files, total_size, batch_forced = self._get_pending_batch()
                
                if not batch_ids:
                    # Short sleep loop so it responds to Ctrl+C quickly
                    for _ in range(60): 
                        if not self.is_running: break
                        time.sleep(1)
                    continue
                
                if batch_forced:
                    logging.info(
                        f"Timed partial flush: packing {len(batch_ids)//2} asset pairs "
                        f"({total_size / (1024**3):.2f} GB)..."
                    )
                else:
                    logging.info(
                        f"Batch threshold reached! Packing {len(batch_ids)//2} asset pairs "
                        f"({total_size / (1024**3):.2f} GB)..."
                    )
                
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(f"UPDATE assets SET status = 'ARCHIVING' WHERE id IN ({','.join(map(str, batch_ids))})")
                
                # Extract metadata from the first JSON file in the batch to name the archive
                asset_type = "mixed"
                model_name = "multi_model"
                try:
                    # batch_files are paired: [asset_path, json_path, asset_path, json_path...]
                    first_json = batch_files[1]
                    with open(first_json, 'r') as f:
                        meta = json.load(f)
                        asset_type = meta.get("output_type", "mixed")
                        model_name = meta.get("model_type", "multi_model").replace("/", "-")
                except Exception:
                    pass
                
                # Construct highly descriptive timestamp-first filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                size_mb = int(total_size / (1024**2))
                num_pairs = len(batch_ids)
                start_id = batch_ids[0]
                
                tar_name = f"{timestamp}_batch_{start_id}_{num_pairs}items_{size_mb}MB_{asset_type}_{model_name}.tar.gz"
                tar_path = os.path.join(SYSTEM_DIRS["cache"], tar_name)

                archive_budget_bytes = int(
                    total_size * self.archive_headroom_factor
                    + 128 * 1024 * 1024
                )
                archive_budget_gb = archive_budget_bytes / (1024**3)
                ok, reason = storage_preflight_path(
                    SYSTEM_DIRS["cache"],
                    required_gb=archive_budget_gb,
                    require_fresh_quota=True,
                    minimum_free_gb=self.archive_min_free_gb,
                )
                if not ok:
                    raise RuntimeError(
                        f"Archive storage admission denied: {reason}"
                    )

                with tarfile.open(tar_path, "w:gz") as tar:
                    for file_path in batch_files:
                        tar.add(file_path, arcname=Path(file_path).name)
                
                logging.info(f"Archive created. Uploading {tar_name} to Hugging Face...")
                
                # --- FIX 3: EXPONENTIAL BACKOFF FOR HPC PROXY DROPS ---
                upload_success = False
                for attempt in range(5):
                    try:
                        self.api.upload_file(
                            path_or_fileobj=tar_path,
                            path_in_repo=f"data/{tar_name}",
                            repo_id=HF_DATASET_REPO,
                            repo_type="dataset"
                        )
                        upload_success = True
                        break
                    except Exception as upload_err:
                        sleep_time = 30 * (attempt + 1) # Waits 30s, 60s, 90s...
                        logging.warning(f"Proxy stuttered on attempt {attempt+1}. Waiting {sleep_time}s to recover... Error: {upload_err}")
                        if not self.is_running: break
                        time.sleep(sleep_time)
                
                if not upload_success:
                    raise ConnectionError("Max upload retries reached due to persistent proxy timeout.")
                
                logging.info("Upload successful! Cleaning up local files and clearing DB...")
                
                for f in batch_files:
                    if os.path.exists(f): os.remove(f)
                if os.path.exists(tar_path): os.remove(tar_path)
                
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(f"DELETE FROM assets WHERE id IN ({','.join(map(str, batch_ids))})")
                
            except Exception as e:
                logging.error(f"Daemon error during batch process: {e}")
                
                # --- FIX 4: SAFETY ROLLBACK IF UPLOAD ULTIMATELY FAILS ---
                if batch_ids:
                    logging.info(f"Safety Net: Rolling back {len(batch_ids)} records to PENDING so they aren't lost.")
                    with sqlite3.connect(self.db_path) as conn:
                        conn.execute(f"UPDATE assets SET status = 'PENDING' WHERE id IN ({','.join(map(str, batch_ids))})")
                if tar_path and os.path.exists(tar_path):
                    os.remove(tar_path)
                    
                time.sleep(120)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIEROS Hugging Face Upload Daemon")
    parser.add_argument(
        "-y", "--yes", "--auto-confirm",
        action="store_true",
        dest="auto_confirm",
        help="Automatically confirm repository creation (required for headless/background running)"
    )
    parser.add_argument(
        "-n", "--no-proxy",
        action="store_true",
        help="Disable proxy routing (Use this when running on the Login Node)"
    )
    parser.add_argument(
        "-g", "--generate-dummy",
        action="store_true",
        help="Generate dummy 300MB video/json pairs to trigger the upload queue threshold."
    )
    args = parser.parse_args()

    # Dynamically strip proxies if we are on the login node
    if args.no_proxy:
        proxies_to_remove = ["http_proxy", "https_proxy", "ftp_proxy", "HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY"]
        for p in proxies_to_remove:
            os.environ.pop(p, None)
        logging.info("[SYSTEM] Proxy routing stripped (Login Node mode active).")

    # Generate massive dummy files for testing the upload queue
    if args.generate_dummy:
        print("\n[TESTING] Generating dummy payload to trigger upload threshold...")
        queue = AssetQueue()

        with managed_storage_operation(
            "outputs",
            required_gb=0.65,
            require_fresh_quota=False,
            minimum_free_gb=0.05,
        ):
            dummy_dir = os.path.join(SYSTEM_DIRS["outputs"], "videos")
            os.makedirs(dummy_dir, exist_ok=True)

            for i in range(2):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                vid_name = f"{timestamp}_video_dummy_{i}.mp4"
                json_name = f"{timestamp}_video_dummy_{i}_info.json"
                vid_path = os.path.join(dummy_dir, vid_name)
                json_path = os.path.join(dummy_dir, json_name)

                print(f"Creating large dummy file: {vid_name} (~300MB)...")
                with open(vid_path, "wb") as f:
                    f.write(b"\0" * (300 * 1024 * 1024))

                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "timestamp": timestamp,
                        "model_type": "dummy_test_model",
                        "output_type": "video",
                        "file_name": vid_name,
                        "generation_parameters": {
                            "dummy_data": True,
                            "size": "300MB",
                        },
                    }, f, indent=4)

                queue.submit(vid_path, json_path)
                time.sleep(1)

            print("[TESTING] Dummy files queued successfully! Starting daemon...\n")

    daemon = HFUploadDaemon(auto_confirm=args.auto_confirm)
    daemon.process_queue()