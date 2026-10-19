import os
import time
import sqlite3
import tarfile
import hashlib
import tempfile
import shutil
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
from asset_status import fetch_pending_upload_rows, recover_archiving_rows, rollback_upload_batch

log_path = os.path.join(SYSTEM_DIRS['logs'], "upload_daemon.log")
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
_log_formatter = logging.Formatter("%(asctime)s - [HF-DAEMON] %(message)s")

# Avoid leaking a FileHandler when a host/test has already configured root logging.
# Explicitly attach only missing handlers instead of constructing handlers for basicConfig.
if not any(
    isinstance(handler, logging.FileHandler)
    and os.path.abspath(handler.baseFilename) == os.path.abspath(log_path)
    for handler in _root_logger.handlers
):
    _file_handler = logging.FileHandler(log_path)
    _file_handler.setFormatter(_log_formatter)
    _root_logger.addHandler(_file_handler)

if not any(
    isinstance(handler, logging.StreamHandler)
    and not isinstance(handler, logging.FileHandler)
    for handler in _root_logger.handlers
):
    _stream_handler = logging.StreamHandler(sys.stdout)
    _stream_handler.setFormatter(_log_formatter)
    _root_logger.addHandler(_stream_handler)

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
    def __init__(
        self,
        auto_confirm: bool = False,
        *,
        cleanup_on_start: bool = True,
        create_repo_if_missing: bool = True,
    ):
        self.api = HfApi()
        self.batch_limit_bytes = int(UPLOAD_BATCH_SIZE_GB * (1024**3))
        if self.batch_limit_bytes < 1:
            raise ValueError("UPLOAD_BATCH_SIZE_GB must allow a positive batch size")
        raw_chunk_mb = os.environ.get("AIEROS_UPLOAD_CHUNK_MB", "256")
        try:
            configured_chunk_mb = int(raw_chunk_mb)
        except (TypeError, ValueError) as exc:
            raise ValueError("AIEROS_UPLOAD_CHUNK_MB must be a positive integer") from exc
        if configured_chunk_mb < 1:
            raise ValueError("AIEROS_UPLOAD_CHUNK_MB must be a positive integer")
        self.chunk_size_bytes = min(configured_chunk_mb * (1024**2), self.batch_limit_bytes)
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
            print("The selected daemon instance is still active; targeted uploads must not bypass its lock.")
            sys.exit(1)
        
        # 1. Register graceful shutdown for Ctrl+C and Kill signals
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        
        # Full-daemon startup may recover stale queue/cache state. Targeted one-shot
        # mode must not mutate unrelated archives or ARCHIVING rows.
        if cleanup_on_start:
            self._cleanup_orphaned_tarballs()
        
        # Ensure repo exists with explicit confirmation
        try:
            if not self.api.repo_exists(repo_id=HF_DATASET_REPO, repo_type="dataset"):
                if not create_repo_if_missing:
                    raise RuntimeError(
                        "configured dataset repository does not exist; targeted --once mode never creates remote repositories"
                    )
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
                recovered = recover_archiving_rows(conn)
                if recovered > 0:
                    logging.info(f"Recovered {recovered} assets stuck in 'ARCHIVING' state from a previous proxy crash.")
                conn.commit()
                
        except Exception as e:
            logging.error(f"Failed to clean up cache/db: {e}")

    def _get_pending_batch(
        self,
        asset_id: int | None = None,
        force_flush: bool = False,
    ):
        now = time.time()

        with sqlite3.connect(self.db_path) as conn:
            rows = fetch_pending_upload_rows(conn)
            if asset_id is not None:
                rows = [row for row in rows if row[0] == asset_id]
                if not rows:
                    raise RuntimeError(
                        f"targeted asset id {asset_id} is not in PENDING state; refusing a broader upload batch"
                    )

            batch_ids, batch_files = [], []
            current_size = 0
            oldest_timestamp = None

            for row in rows:
                row_id, a_path, j_path, size, timestamp = row
                size = int(size or 0)
                if asset_id is not None and size > self.batch_limit_bytes:
                    raise ValueError(
                        f"targeted asset id {asset_id} is {size} bytes, above the configured batch limit "
                        f"{self.batch_limit_bytes}; individual-file chunking is not implemented"
                    )

                if os.path.exists(a_path) and os.path.exists(j_path):
                    batch_ids.append(row_id)
                    batch_files.extend([a_path, j_path])
                    current_size += size
                    if oldest_timestamp is None:
                        try:
                            oldest_timestamp = datetime.strptime(
                                timestamp, "%Y-%m-%d %H:%M:%S"
                            ).timestamp()
                        except (TypeError, ValueError):
                            oldest_timestamp = now
                    if current_size >= self.batch_limit_bytes:
                        break
                else:
                    conn.execute(
                        "UPDATE assets SET status = 'FAILED_MISSING_FILE' WHERE id = ?",
                        (row_id,),
                    )
            conn.commit()

        if not batch_ids:
            return [], [], 0, False
        if current_size >= self.batch_limit_bytes:
            return batch_ids, batch_files, current_size, False
        if force_flush:
            logging.info("Targeted one-shot upload: forcing selected asset pair into one archive.")
            return batch_ids, batch_files, current_size, True
        age = max(0.0, now - (oldest_timestamp or now))
        if age >= self.partial_batch_max_age_seconds:
            logging.info(
                "Partial upload batch aged %.0fs; forcing flush of %.2f GB.",
                age, current_size / (1024**3),
            )
            return batch_ids, batch_files, current_size, True
        return [], [], 0, False

    def _upload_asset_in_chunks(self, asset_id: int, chunk_size_bytes: int | None = None) -> int:
        """Upload one oversized PENDING asset as verified parts; publish the manifest last.

        Remote parts are deterministic for (asset ID, asset SHA-256), so a retry can safely
        overwrite partial objects. Consumers must assemble the ordered parts listed in
        manifest.json and verify the full SHA-256 before treating the asset as complete.
        """
        if isinstance(asset_id, bool) or not isinstance(asset_id, int) or asset_id < 1:
            raise ValueError("asset_id must be a positive integer")
        chunk_size = self.chunk_size_bytes if chunk_size_bytes is None else chunk_size_bytes
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size < 1:
            raise ValueError("chunk_size_bytes must be a positive integer")
        chunk_size = min(chunk_size, self.batch_limit_bytes)

        # The queue/status DB is an outputs write; admit it before claiming the row.
        ok, reason = storage_preflight_path(
            SYSTEM_DIRS["outputs"], required_gb=0.001, require_fresh_quota=True, minimum_free_gb=0.05
        )
        if not ok:
            raise RuntimeError(f"Chunked upload status admission denied: {reason}")

        claimed = False
        row_deleted = False
        work_dir: Path | None = None
        asset_path: Path | None = None
        metadata_path: Path | None = None
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute("BEGIN IMMEDIATE")
                rows = fetch_pending_upload_rows(conn)
                row = next((item for item in rows if item[0] == asset_id), None)
                if row is None:
                    raise RuntimeError(f"targeted asset id {asset_id} is not in PENDING state")
                _row_id, asset_raw, metadata_raw, recorded_total, _timestamp = row
                asset_path = Path(asset_raw)
                metadata_path = Path(metadata_raw)
                if not asset_path.is_file() or not metadata_path.is_file():
                    raise FileNotFoundError("targeted asset or metadata file is missing; source row left pending")
                asset_size = asset_path.stat().st_size
                metadata_size = metadata_path.stat().st_size
                actual_total = asset_size + metadata_size
                if actual_total != int(recorded_total or 0):
                    raise RuntimeError(
                        f"queued size {recorded_total} does not match current file bytes {actual_total}; refusing chunk upload"
                    )
                if actual_total <= self.batch_limit_bytes:
                    raise ValueError("targeted row fits a normal archive batch; chunk mode is only for oversized rows")
                if asset_size < 1:
                    raise ValueError("cannot chunk an empty asset file")
                if metadata_size > chunk_size:
                    raise ValueError(
                        "metadata JSON exceeds the configured chunk size; reduce the metadata or increase AIEROS_UPLOAD_CHUNK_MB"
                    )
                cursor = conn.execute(
                    "UPDATE assets SET status = 'ARCHIVING' WHERE id = ? AND status = 'PENDING'",
                    (asset_id,),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(f"could not atomically claim PENDING asset id {asset_id}")
                conn.commit()
                claimed = True

            cache_root = Path(SYSTEM_DIRS["cache"]).expanduser().resolve()
            # Read once to establish a deterministic remote namespace; never stage the full asset.
            initial_digest = hashlib.sha256()
            with asset_path.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    initial_digest.update(block)
            asset_sha256 = initial_digest.hexdigest()
            remote_prefix = f"data/chunks/asset-{asset_id}-{asset_sha256[:16]}"
            metadata_bytes = metadata_path.read_bytes()
            metadata_value = json.loads(metadata_bytes.decode("utf-8"))
            metadata_sha256 = hashlib.sha256(metadata_bytes).hexdigest()
            metadata_remote = f"{remote_prefix}/metadata.json"

            required_gb = (min(chunk_size, asset_size) * 1.15 + 16 * 1024 * 1024) / (1024**3)
            ok, reason = storage_preflight_path(
                str(cache_root), required_gb=max(0.001, required_gb),
                require_fresh_quota=True, minimum_free_gb=self.archive_min_free_gb,
            )
            if not ok:
                raise RuntimeError(f"Chunk staging storage admission denied: {reason}")
            cache_root.mkdir(parents=True, exist_ok=True)
            work_dir = Path(tempfile.mkdtemp(prefix=f"oec-upload-chunks-{asset_id}-", dir=str(cache_root)))
            parts: list[dict[str, object]] = []
            second_digest = hashlib.sha256()
            offset = 0
            part_index = 0

            with asset_path.open("rb") as source:
                while offset < asset_size:
                    current_part_bytes = min(chunk_size, asset_size - offset)
                    required_gb = (current_part_bytes * 1.15 + 16 * 1024 * 1024) / (1024**3)
                    ok, reason = storage_preflight_path(
                        str(cache_root), required_gb=max(0.001, required_gb),
                        require_fresh_quota=True, minimum_free_gb=self.archive_min_free_gb,
                    )
                    if not ok:
                        raise RuntimeError(f"Chunk staging admission denied before part {part_index}: {reason}")
                    chunk_path = work_dir / f"part-{part_index:06d}.bin"
                    part_digest = hashlib.sha256()
                    written = 0
                    with chunk_path.open("xb") as target:
                        while written < current_part_bytes:
                            data = source.read(min(1024 * 1024, current_part_bytes - written))
                            if not data:
                                break
                            target.write(data)
                            part_digest.update(data)
                            second_digest.update(data)
                            written += len(data)
                        target.flush()
                        os.fsync(target.fileno())
                    if written != current_part_bytes:
                        raise RuntimeError("source asset shrank while it was being chunked")
                    part_hash = part_digest.hexdigest()
                    remote_path = f"{remote_prefix}/part-{part_index:06d}.bin"
                    self.api.upload_file(
                        path_or_fileobj=str(chunk_path), path_in_repo=remote_path,
                        repo_id=HF_DATASET_REPO, repo_type="dataset",
                    )
                    parts.append({
                        "index": part_index, "path": remote_path, "offset_bytes": offset,
                        "size_bytes": written, "sha256": part_hash,
                    })
                    chunk_path.unlink(missing_ok=True)
                    logging.info(
                        "Chunk upload complete asset_id=%s part=%s bytes=%s sha256=%s",
                        asset_id, part_index, written, part_hash,
                    )
                    offset += written
                    part_index += 1
                if source.read(1):
                    raise RuntimeError("source asset grew while it was being chunked")

            if second_digest.hexdigest() != asset_sha256:
                raise RuntimeError("source asset changed while chunk uploads were in progress; manifest was not published")

            metadata_stage = work_dir / "metadata.json"
            metadata_stage.write_bytes(metadata_bytes)
            self.api.upload_file(
                path_or_fileobj=str(metadata_stage), path_in_repo=metadata_remote,
                repo_id=HF_DATASET_REPO, repo_type="dataset",
            )
            manifest = {
                "schema_version": 1,
                "protocol": "oec-asset-chunks-v1",
                "status": "complete",
                "asset_id": asset_id,
                "original_filename": asset_path.name,
                "asset_bytes": asset_size,
                "asset_sha256": asset_sha256,
                "chunk_size_bytes": chunk_size,
                "parts": parts,
                "metadata": {"path": metadata_remote, "bytes": len(metadata_bytes), "sha256": metadata_sha256},
                "assembly": "concatenate parts in ascending index order; verify each part SHA-256 and the full asset_sha256",
                "created_at": datetime.now().astimezone().isoformat(),
            }
            manifest_path = work_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest_remote = f"{remote_prefix}/manifest.json"
            # The manifest is uploaded LAST, so consumers never see a published completion marker
            # until every part and its metadata have been accepted by the Hub API.
            self.api.upload_file(
                path_or_fileobj=str(manifest_path), path_in_repo=manifest_remote,
                repo_id=HF_DATASET_REPO, repo_type="dataset",
            )
            logging.info(
                "Chunked asset published asset_id=%s bytes=%s parts=%s sha256=%s manifest=%s",
                asset_id, asset_size, len(parts), asset_sha256, manifest_remote,
            )

            with sqlite3.connect(self.db_path, timeout=30) as conn:
                cursor = conn.execute(
                    "DELETE FROM assets WHERE id = ? AND status = 'ARCHIVING'", (asset_id,)
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("remote manifest was uploaded but the selected ARCHIVING row could not be finalized")
                conn.commit()
                row_deleted = True

            # The manifest is complete and the DB hand-off committed. File cleanup is best-effort;
            # never roll back a valid remote manifest just because a local unlink fails.
            for source_path in (asset_path, metadata_path):
                try:
                    source_path.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    logging.warning("Chunked upload succeeded but local cleanup failed for %s: %s", source_path.name, cleanup_error)
            return 1
        except Exception:
            if claimed and not row_deleted:
                try:
                    with sqlite3.connect(self.db_path, timeout=30) as conn:
                        rollback_upload_batch(conn, [asset_id])
                        conn.commit()
                except Exception as rollback_error:
                    logging.error("Failed to restore selected asset id %s after chunk upload failure: %s", asset_id, rollback_error)
            raise
        finally:
            if work_dir is not None:
                shutil.rmtree(work_dir, ignore_errors=True)

    def process_queue(
        self,
        *,
        max_batches: int | None = None,
        asset_id: int | None = None,
        chunk_oversize: bool = False,
    ) -> int:
        if max_batches is not None and max_batches < 1:
            raise ValueError("max_batches must be positive when supplied")
        if asset_id is not None and (isinstance(asset_id, bool) or asset_id < 1):
            raise ValueError("asset_id must be a positive integer")
        if max_batches is not None and asset_id is None:
            raise ValueError("bounded upload mode requires an explicit --asset-id")
        if chunk_oversize and (max_batches is None or asset_id is None):
            raise ValueError("chunk_oversize is available only in bounded asset-id mode")

        logging.info("Daemon started. Polling upload queue...")
        processed_batches = 0
        while self.is_running:
            batch_ids, batch_files, tar_path = [], [], None
            try:
                try:
                    batch_ids, batch_files, total_size, batch_forced = self._get_pending_batch(
                        asset_id=asset_id,
                        force_flush=max_batches is not None,
                    )
                except ValueError as selection_error:
                    if not (
                        chunk_oversize and max_batches is not None and asset_id is not None
                        and "individual-file chunking is not implemented" in str(selection_error)
                    ):
                        raise
                    # Opt-in chunking is limited to one selected asset and never broadens the batch.
                    uploaded = self._upload_asset_in_chunks(asset_id)
                    processed_batches += uploaded
                    if max_batches is not None and processed_batches >= max_batches:
                        return processed_batches
                    continue

                if not batch_ids:
                    if max_batches is not None:
                        raise RuntimeError("targeted upload produced no eligible batch")
                    for _ in range(60):
                        if not self.is_running:
                            break
                        time.sleep(1)
                    continue

                if batch_forced:
                    logging.info(
                        "Timed/targeted partial flush: packing %s asset pair(s) (%.2f GB)...",
                        len(batch_ids), total_size / (1024**3),
                    )
                else:
                    logging.info(
                        "Batch threshold reached! Packing %s asset pair(s) (%.2f GB)...",
                        len(batch_ids), total_size / (1024**3),
                    )
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        f"UPDATE assets SET status = 'ARCHIVING' WHERE id IN ({','.join(map(str, batch_ids))})"
                    )

                asset_type, model_name = "mixed", "multi_model"
                try:
                    with open(batch_files[1], "r", encoding="utf-8") as handle:
                        meta = json.load(handle)
                    asset_type = meta.get("output_type", "mixed")
                    model_name = meta.get("model_type", "multi_model").replace("/", "-")
                except Exception:
                    pass

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                size_mb = int(total_size / (1024**2))
                tar_name = (
                    f"{timestamp}_batch_{batch_ids[0]}_{len(batch_ids)}items_"
                    f"{size_mb}MB_{asset_type}_{model_name}.tar.gz"
                )
                tar_path = os.path.join(SYSTEM_DIRS["cache"], tar_name)
                archive_budget_bytes = int(
                    total_size * self.archive_headroom_factor + 128 * 1024 * 1024
                )
                ok, reason = storage_preflight_path(
                    SYSTEM_DIRS["cache"],
                    required_gb=archive_budget_bytes / (1024**3),
                    require_fresh_quota=True,
                    minimum_free_gb=self.archive_min_free_gb,
                )
                if not ok:
                    raise RuntimeError(f"Archive storage admission denied: {reason}")

                with tarfile.open(tar_path, "w:gz") as tar:
                    for file_path in batch_files:
                        tar.add(file_path, arcname=Path(file_path).name)
                logging.info("Archive created. Uploading %s to Hugging Face...", tar_name)

                upload_success = False
                for attempt in range(5):
                    try:
                        self.api.upload_file(
                            path_or_fileobj=tar_path,
                            path_in_repo=f"data/{tar_name}",
                            repo_id=HF_DATASET_REPO,
                            repo_type="dataset",
                        )
                        upload_success = True
                        break
                    except Exception as upload_err:
                        if max_batches is not None:
                            raise ConnectionError(
                                "targeted one-shot Hugging Face upload failed; selected row will be rolled back to PENDING"
                            ) from upload_err
                        sleep_time = 30 * (attempt + 1)
                        logging.warning(
                            "Proxy upload attempt %s failed; waiting %ss: %s",
                            attempt + 1, sleep_time, upload_err,
                        )
                        if not self.is_running:
                            break
                        time.sleep(sleep_time)
                if not upload_success:
                    raise ConnectionError("Max upload retries reached due to persistent proxy timeout.")

                logging.info("Upload successful! Cleaning only selected local files and database rows...")
                for file_path in batch_files:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                if tar_path and os.path.exists(tar_path):
                    os.remove(tar_path)
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        f"DELETE FROM assets WHERE id IN ({','.join(map(str, batch_ids))})"
                    )
                    conn.commit()
                processed_batches += 1
                logging.info("Upload batch completed; processed_batches=%s", processed_batches)
                if max_batches is not None and processed_batches >= max_batches:
                    return processed_batches

            except Exception as exc:
                logging.error("Daemon error during batch process: %s", exc)
                if batch_ids:
                    logging.info("Safety net: rolling back only selected ids %s to PENDING.", batch_ids)
                    with sqlite3.connect(self.db_path) as conn:
                        rollback_upload_batch(conn, batch_ids)
                        conn.commit()
                if tar_path and os.path.exists(tar_path):
                    os.remove(tar_path)
                if max_batches is not None:
                    raise
                time.sleep(120)
        return processed_batches

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
    parser.add_argument(
        "--once",
        action="store_true",
        help="Upload exactly one explicitly selected pending asset pair, then exit.",
    )
    parser.add_argument(
        "--asset-id",
        type=int,
        help="Positive asset row ID; required with --once and refused unless status is PENDING.",
    )
    parser.add_argument(
        "--chunk-oversize",
        action="store_true",
        help="Explicitly upload one oversized selected asset as hashed parts plus a completion manifest; requires --once --asset-id.",
    )
    args = parser.parse_args()
    if args.once and (args.asset_id is None or args.asset_id < 1):
        parser.error("--once requires --asset-id with a positive ID")
    if not args.once and args.asset_id is not None:
        parser.error("--asset-id can only be used with --once")
    if args.once and args.generate_dummy:
        parser.error("--once cannot be combined with --generate-dummy")
    if args.chunk_oversize and not args.once:
        parser.error("--chunk-oversize requires --once --asset-id")

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

    daemon = HFUploadDaemon(
        auto_confirm=args.auto_confirm,
        cleanup_on_start=not args.once,
        create_repo_if_missing=not args.once,
    )
    if args.once:
        try:
            processed = daemon.process_queue(
                max_batches=1, asset_id=args.asset_id, chunk_oversize=args.chunk_oversize
            )
        except Exception as exc:
            print(f"[UPLOAD_ONCE] FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        if processed != 1:
            print("[UPLOAD_ONCE] FAIL no asset batch was uploaded", file=sys.stderr)
            raise SystemExit(1)
        print(f"[UPLOAD_ONCE] PASS asset_id={args.asset_id} batches={processed}")
    else:
        daemon.process_queue()