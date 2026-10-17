"""Temporary leases against OEC's physically allocated storage reserve.

Only write temporary artifacts into the yielded scratch directory. The context
manager removes that unique directory before restoring reserve blocks. If a
process is interrupted, a manifest and pause marker remain and storage_manager
fails closed rather than silently resizing the reserve.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path

import storage_manager
from storage_policy import BYTES_PER_GB, StoragePolicy, directory_size_bytes

STAGING_DIRECTORY = ".oec_temp_downloads"


def _write_json_exclusive(path: Path, payload: dict) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _restore_reserve(reserve_path: Path, reduced_size: int, original_size: int) -> None:
    """Restore the released tail as allocated blocks, or fail closed."""
    if not hasattr(os, "posix_fallocate"):
        raise RuntimeError("posix_fallocate is required to restore a real reserve")
    if reserve_path.is_symlink() or not reserve_path.is_file():
        raise RuntimeError("reserve file is missing or unsafe during restoration")

    fd = os.open(reserve_path, os.O_RDWR)
    try:
        current_size = os.fstat(fd).st_size
        if current_size not in (reduced_size, original_size):
            raise RuntimeError(f"reserve size changed unexpectedly: {current_size} bytes")
        if current_size == original_size:
            os.posix_fallocate(fd, reduced_size, original_size - reduced_size)
        else:
            os.ftruncate(fd, original_size)
            try:
                os.posix_fallocate(fd, reduced_size, original_size - reduced_size)
            except BaseException:
                os.ftruncate(fd, reduced_size)
                raise
        os.fsync(fd)
        if os.fstat(fd).st_size != original_size:
            raise RuntimeError("reserve restoration size verification failed")
    finally:
        os.close(fd)


@contextlib.contextmanager
def temporary_download_reservation(
    dir_name: str = "models",
    *,
    reserve_release_gb: float,
    max_download_gb: float,
    minimum_reserve_gb: float = 1.0,
    minimum_quota_headroom_gb: float = 1.0,
):
    """Lend a bounded part of the reserve to one download, then restore it.

    A fresh quota snapshot or live Lustre group-quota result is mandatory. The
    caller must write temporary artifacts under the yielded path; that path is
    deleted before reserve restoration.
    """
    config = storage_manager.load_config()
    if not config:
        raise RuntimeError("storage configuration is unavailable")
    dir_cfg = storage_manager._directory_config(config, dir_name)
    folder = Path(storage_manager.SYSTEM_DIRS.get(dir_name, dir_name)).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)

    release_bytes = int(float(reserve_release_gb) * BYTES_PER_GB)
    download_bytes = int(float(max_download_gb) * BYTES_PER_GB)
    min_reserve_bytes = int(float(minimum_reserve_gb) * BYTES_PER_GB)
    min_headroom_bytes = int(float(minimum_quota_headroom_gb) * BYTES_PER_GB)
    if release_bytes <= 0 or download_bytes <= 0:
        raise ValueError("reserve release and maximum download sizes must be positive")
    if release_bytes < download_bytes + min_headroom_bytes:
        raise ValueError("reserve release must cover max download plus minimum quota headroom")

    reserve_path = folder / storage_manager.RESERVE_FILENAME
    pause_path = folder / storage_manager.LOCK_FILENAME
    manifest_path = folder / storage_manager.LEASE_MANIFEST_FILENAME
    staging_root = folder / STAGING_DIRECTORY
    lease_id = uuid.uuid4().hex
    scratch = None
    original_size = 0
    reduced_size = 0
    lease_created = False

    with storage_manager._directory_lock(str(folder)):
        if manifest_path.exists() or manifest_path.is_symlink():
            raise RuntimeError("an existing temporary lease needs recovery; refusing a second lease")
        if storage_manager._pause_lock_active(str(folder), float(config.get("lock_ttl_seconds", 21600))):
            raise RuntimeError("storage directory already has an active managed operation")
        if reserve_path.is_symlink() or not reserve_path.is_file():
            raise RuntimeError("allocated reserve is missing or unsafe")
        original_size = reserve_path.stat().st_size
        reduced_size = original_size - release_bytes
        if reduced_size < min_reserve_bytes:
            raise RuntimeError(
                f"lease would leave only {reduced_size / BYTES_PER_GB:.3f} GiB reserved; "
                f"minimum is {minimum_reserve_gb:.3f} GiB"
            )

        policy = StoragePolicy(config)
        quota = policy.get_quota_snapshot(folder)
        if quota is None:
            raise RuntimeError(
                "no fresh quota snapshot and no successful live Lustre group-quota result are available"
            )
        available, quota_reason = policy.quota_write_headroom(quota)
        if quota.hard_limit_exceeded:
            raise RuntimeError("quota is already above the hard limit; temporary reserve leases are blocked")
        if quota.soft_quota_exceeded and not quota.grace_active:
            raise RuntimeError(
                "usage is above soft quota but Lustre grace is not active; temporary reserve leases are blocked"
            )
        if available + release_bytes < download_bytes + min_headroom_bytes:
            raise RuntimeError(
                "insufficient quota headroom even after reserve release: "
                f"available={available} released={release_bytes} "
                f"required={download_bytes + min_headroom_bytes}; {quota_reason}"
            )

        target_gb = float(dir_cfg.get("target_allocation_gb", 0))
        if target_gb > 0:
            controls = (
                storage_manager.RESERVE_FILENAME,
                storage_manager.LOCK_FILENAME,
                storage_manager.MANAGER_LOCK_FILENAME,
                storage_manager.LEASE_MANIFEST_FILENAME,
            )
            current_bytes = directory_size_bytes(folder, controls)
            target_bytes = int(target_gb * BYTES_PER_GB)
            if current_bytes + download_bytes > target_bytes:
                raise RuntimeError(
                    "download would exceed configured directory target: "
                    f"current={current_bytes} requested={download_bytes} target={target_bytes}"
                )

        staging_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        scratch = Path(tempfile.mkdtemp(prefix=f"lease-{lease_id}-", dir=str(staging_root)))
        manifest = {
            "lease_id": lease_id,
            "pid": os.getpid(),
            "created_at": time.time(),
            "directory": str(folder),
            "reserve_file": str(reserve_path),
            "original_reserve_bytes": original_size,
            "reduced_reserve_bytes": reduced_size,
            "released_bytes": release_bytes,
            "max_download_bytes": download_bytes,
            "scratch_relative_path": str(scratch.relative_to(folder)),
            "state": "PREPARING",
        }
        try:
            _write_json_exclusive(manifest_path, manifest)
            _write_json_exclusive(
                pause_path,
                {"lease_id": lease_id, "pid": os.getpid(), "created_at": time.time()},
            )
            fd = os.open(reserve_path, os.O_RDWR)
            try:
                os.ftruncate(fd, reduced_size)
                os.fsync(fd)
            finally:
                os.close(fd)
            manifest["state"] = "ACTIVE"
            temp_manifest = manifest_path.with_name(f".{manifest_path.name}.{lease_id}.tmp")
            _write_json_exclusive(temp_manifest, manifest)
            os.replace(temp_manifest, manifest_path)
            lease_created = True
        except BaseException:
            try:
                current_size = reserve_path.stat().st_size
            except OSError:
                current_size = -1
            if current_size == original_size:
                for marker in (manifest_path, pause_path):
                    try:
                        marker.unlink()
                    except OSError:
                        pass
                if scratch and scratch.exists():
                    shutil.rmtree(scratch)
            raise

    body_error = None
    size_error = None
    cleanup_error = None
    restore_error = None
    try:
        yield scratch
    except BaseException as exc:
        body_error = exc
    finally:
        try:
            if scratch is not None:
                if scratch.is_symlink() or not scratch.is_dir():
                    raise RuntimeError("temporary scratch path was replaced or is no longer a directory")
                actual_download_bytes = directory_size_bytes(scratch, ())
                if actual_download_bytes > download_bytes:
                    size_error = RuntimeError(
                        f"scratch exceeded declared max download: actual={actual_download_bytes} "
                        f"max={download_bytes}; scratch will be removed before reserve restoration"
                    )
                shutil.rmtree(scratch)
                try:
                    staging_root.rmdir()
                except OSError:
                    pass
        except BaseException as exc:
            cleanup_error = exc

        if cleanup_error is None and lease_created:
            try:
                with storage_manager._directory_lock(str(folder)):
                    current = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if current.get("lease_id") != lease_id:
                        raise RuntimeError("lease manifest ownership changed; refusing restoration")
                    _restore_reserve(reserve_path, reduced_size, original_size)
                    manifest_path.unlink()
                    try:
                        pause_path.unlink()
                    except FileNotFoundError:
                        pass
            except BaseException as exc:
                restore_error = exc

    if cleanup_error is not None:
        raise RuntimeError(
            f"temporary download cleanup failed; reserve remains reduced and lease is locked: {cleanup_error}"
        ) from cleanup_error
    if restore_error is not None:
        raise RuntimeError(
            f"reserve restoration failed; recovery manifest and pause lock were preserved: {restore_error}"
        ) from restore_error
    if size_error is not None:
        raise size_error
    if body_error is not None:
        raise body_error
