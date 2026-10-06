import os
import shutil
import time
import gc
import sqlite3

# STRICT CORE_CONFIG IMPORT
from core_config import SYSTEM_DIRS

# ==============================================================================
# UNIVERSAL DISK PURGE MANAGER (CLUSTER EDITION)
# Reclaims NVMe storage safely across Multi-Node Distributed Systems.
# ==============================================================================

class DiskPurgeManager:
    @staticmethod
    def get_hf_cache_dir(repo_id: str) -> str:
        """Resolves the exact hidden Hugging Face cache directory for a repo."""
        folder_name = "models--" + repo_id.replace("/", "--")
        return os.path.join(SYSTEM_DIRS['models'], "hub", folder_name)

    @staticmethod
    def purge_directory(target_dir: str, label: str = "Directory"):
        """Surgically deletes a directory and reclaims disk space."""
        if os.path.exists(target_dir):
            print(f"\n[DISK MANAGER] ⚠️ PURGE EXECUTING for {label} ⚠️")
            try:
                gc.collect()
                time.sleep(2) # Brief pause to ensure all Python file handles are released
                shutil.rmtree(target_dir, ignore_errors=True)
                print(f"[DISK MANAGER] ✅ Successfully wiped: {target_dir}")
                print(f"[DISK MANAGER] ⚡ Assets now exist purely in VRAM.\n")
            except Exception as e:
                print(f"[DISK MANAGER] ❌ Warning: Could not purge {target_dir}: {e}")

    @staticmethod
    def purge_hf_model(repo_id: str):
        target_dir = DiskPurgeManager.get_hf_cache_dir(repo_id)
        DiskPurgeManager.purge_directory(target_dir, f"HF Model: '{repo_id}'")

class ClusterPurgeManager:
    """
    Coordinates multi-GPU loading across physical nodes using a shared SQLite lock.
    """
    DB_PATH = os.path.join(SYSTEM_DIRS['cache'], "cluster_purge_sync.db")

    @classmethod
    def _init_db(cls):
        with sqlite3.connect(cls.DB_PATH, timeout=30) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sync_state (
                    model_id TEXT PRIMARY KEY,
                    expected_count INTEGER,
                    arrived_count INTEGER,
                    status TEXT,
                    updated_at REAL
                )
            ''')
            # Fail-safe: Sweep stale locks older than 2 hours (e.g. from previous crashes)
            current_time = time.time()
            conn.execute("DELETE FROM sync_state WHERE ? - updated_at > 7200", (current_time,))
            conn.commit()

    @classmethod
    def sync_and_purge(cls, repo_id: str, expected_gpus: int, worker_id: str, timeout_seconds=600):
        """
        Increments the load count. Waits for all GPUs. Deletes model when target hit.
        """
        target_dir = DiskPurgeManager.get_hf_cache_dir(repo_id)
        
        # If running a single GPU or user didn't specify cluster tracking, purge normally.
        if expected_gpus <= 1:
            DiskPurgeManager.purge_directory(target_dir, f"HF Model: '{repo_id}'")
            return

        cls._init_db()
        
        print(f"[{worker_id}] Loaded '{repo_id}' into VRAM. Registering in Cluster Queue...")
        
        with sqlite3.connect(cls.DB_PATH, timeout=30) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT expected_count, arrived_count, status FROM sync_state WHERE model_id = ?", (repo_id,))
            row = cursor.fetchone()
            
            if not row:
                cursor.execute(
                    "INSERT INTO sync_state (model_id, expected_count, arrived_count, status, updated_at) VALUES (?, ?, 1, 'WAITING', ?)",
                    (repo_id, expected_gpus, time.time())
                )
            else:
                if row[2] == 'PURGED':
                    print(f"[{worker_id}] Model already purged by cluster. Proceeding.")
                    return
                cursor.execute(
                    "UPDATE sync_state SET arrived_count = arrived_count + 1, updated_at = ? WHERE model_id = ?",
                    (time.time(), repo_id)
                )
            conn.commit()

        start_time = time.time()
        while True:
            time.sleep(3)
            with sqlite3.connect(cls.DB_PATH, timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT expected_count, arrived_count, status FROM sync_state WHERE model_id = ?", (repo_id,))
                row = cursor.fetchone()

            if not row: 
                break # DB was wiped? Proceed safely.
                
            expected, arrived, status = row
            
            if status == 'PURGED':
                print(f"[{worker_id}] Cluster sync complete. Proceeding.")
                break
                
            if status == 'ABORTED':
                print(f"[{worker_id}] Cluster sync was aborted (Likely due to crashed node). Proceeding without purging.")
                break

            if arrived >= expected and status == 'WAITING':
                # ATOMIC ELECTION: Try to become the Leader who executes the deletion
                try:
                    with sqlite3.connect(cls.DB_PATH, timeout=5) as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE sync_state SET status = 'PURGING' WHERE model_id = ? AND status = 'WAITING'",
                            (repo_id,)
                        )
                        if cursor.rowcount > 0:
                            # WE WON THE ELECTION. Execute the purge.
                            print(f"\n[{worker_id}] 👑 ALL {expected} GPUS ARRIVED. Elected as Leader. Executing Global Purge...")
                            DiskPurgeManager.purge_directory(target_dir, f"Cluster HF Model: '{repo_id}'")
                            
                            conn.execute("UPDATE sync_state SET status = 'PURGED' WHERE model_id = ?", (repo_id,))
                            conn.commit()
                            break
                except sqlite3.OperationalError:
                    pass # Another GPU won the election and locked the DB. We just loop and wait for 'PURGED'.
            
            if time.time() - start_time > timeout_seconds:
                print(f"\n[{worker_id}] ❌ CRITICAL: Timeout reached ({timeout_seconds}s). Arrived: {arrived}/{expected}.")
                print(f"[{worker_id}] Aborting cluster purge to prevent deadlocks. GPUs will begin working immediately.")
                with sqlite3.connect(cls.DB_PATH, timeout=30) as conn:
                    conn.execute("UPDATE sync_state SET status = 'ABORTED' WHERE model_id = ?", (repo_id,))
                break