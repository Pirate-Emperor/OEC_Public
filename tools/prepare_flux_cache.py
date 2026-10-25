#!/usr/bin/env python3
"""Explicitly prepare the FLUX.2 Klein Hub snapshot under OEC StorageManager admission."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core_config import SYSTEM_DIRS
from huggingface_hub import snapshot_download
try:
    from huggingface_hub.errors import LocalEntryNotFoundError
except ImportError:
    from huggingface_hub.utils import LocalEntryNotFoundError
from storage_manager import managed_storage_operation, storage_preflight
from storage_policy import BYTES_PER_GB, estimate_hf_repo_bytes

MODEL_ID = "black-forest-labs/FLUX.2-klein-4B"

def ensure_flux_cache(*, allow_download: bool = False) -> Path:
    """Return a local snapshot; only fetch missing files when explicitly authorized."""
    cache_dir = Path(SYSTEM_DIRS["models"]).expanduser().resolve()
    try:
        snapshot = snapshot_download(repo_id=MODEL_ID, cache_dir=str(cache_dir), local_files_only=True)
        print(f"FLUX_CACHE=HIT snapshot={snapshot}", flush=True)
        return Path(snapshot)
    except LocalEntryNotFoundError:
        if not allow_download:
            raise RuntimeError(
                f"FLUX cache miss for {MODEL_ID}; cache-only mode refuses to fetch model files. "
                "Run this helper with --allow-download after verifying fresh StorageManager admission."
            )
    os.environ["HF_HUB_OFFLINE"] = "0"
    os.environ["TRANSFORMERS_OFFLINE"] = "0"
    safety_gb = max(0.0, float(os.environ.get("OEC_FLUX_DOWNLOAD_SAFETY_GB", "2.0")))
    required_gb = estimate_hf_repo_bytes(MODEL_ID) / BYTES_PER_GB + safety_gb
    minimum_free_gb = max(2.0, float(os.environ.get("AIEROS_MODEL_MIN_FREE_GB", "2.0")))
    ok, reason = storage_preflight("models", required_gb=required_gb,
                                   require_fresh_quota=True, minimum_free_gb=minimum_free_gb)
    print(f"FLUX_MODEL_STORAGE_ADMISSION={bool(ok)} required_gb={required_gb:.3f} reason={reason}", flush=True)
    if not ok:
        raise RuntimeError(f"StorageManager denied FLUX cache fill: {reason}")
    with managed_storage_operation("models", required_gb=required_gb,
                                   require_fresh_quota=True, minimum_free_gb=minimum_free_gb):
        ok, reason = storage_preflight("models", required_gb=required_gb,
                                       require_fresh_quota=True, minimum_free_gb=minimum_free_gb)
        if not ok:
            raise RuntimeError(f"StorageManager denied FLUX cache fill inside managed operation: {reason}")
        snapshot = snapshot_download(repo_id=MODEL_ID, cache_dir=str(cache_dir), local_files_only=False)
    print(f"FLUX_DOWNLOAD=PASS snapshot={snapshot}", flush=True)
    return Path(snapshot)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-download", action="store_true",
                        help="Allow a missing FLUX snapshot to be downloaded after fresh StorageManager admission.")
    parser.add_argument("--check-only", action="store_true",
                        help="Check the local cache and fail if the complete snapshot is absent.")
    args = parser.parse_args(argv)
    if args.check_only and args.allow_download:
        parser.error("--check-only and --allow-download are mutually exclusive")
    snapshot = ensure_flux_cache(allow_download=args.allow_download)
    print(json.dumps({"status":"PASS","model_id":MODEL_ID,"snapshot":str(snapshot),
        "cache_root":str(Path(SYSTEM_DIRS["models"]).expanduser().resolve()),
        "download_allowed":bool(args.allow_download)},sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
