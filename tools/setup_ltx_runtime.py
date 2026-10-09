#!/usr/bin/env python3
"""Explicitly prepare the pinned LTX-2 source checkout.

This tool only manages the source checkout. It does not install Python packages,
download model weights, purge caches, or alter an existing checkout.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Sequence

LTX_REPO_URL = "https://github.com/Lightricks/LTX-2.git"
LTX_COMMIT_SHA = "ae855f8538843825f9015a419cf4ba5edaf5eec2"
REQUIRED_RELATIVE_DIRS = (
    Path("packages/ltx-core"),
    Path("packages/ltx-core/src"),
    Path("packages/ltx-pipelines"),
    Path("packages/ltx-pipelines/src"),
)


def _import_core_config():
    """Import OEC's config regardless of whether this file is run as a script."""
    oec_root = str(Path(__file__).resolve().parents[1])
    if oec_root not in sys.path:
        sys.path.insert(0, oec_root)
    return importlib.import_module("core_config")


def _run_git(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Run Git without a shell and include bounded diagnostics on failure."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "no diagnostic output").strip()
        raise RuntimeError(
            f"git {' '.join(args)} failed with exit code {result.returncode}: "
            f"{detail[-2000:]}"
        )
    return result.stdout.strip()


def resolve_runtime_dir(cli_path: str | None = None) -> Path:
    """Resolve the same target as worker_ltx_video.py."""
    configured = cli_path or os.environ.get("AIEROS_LTX_REPO_DIR")
    if configured:
        return Path(os.path.abspath(os.path.expandvars(os.path.expanduser(configured))))

    # Import only when needed. core_config initializes its configured paths and
    # proxy environment at import time; the setup command is an explicit action.
    core_config = _import_core_config()
    return Path(core_config.SYSTEM_DIRS["cache"]) / "third_party" / "LTX-2"


def _configure_hpc_environment() -> None:
    """Apply OEC's existing proxy/storage environment setup before Git access."""
    # Importing core_config invokes its documented module initialization, including
    # mapping shared storage paths and setting the HPC proxy variables.
    _import_core_config()


def _renameat2_noreplace(staging_dir: Path, target: Path) -> tuple[int, int]:
    """Try Linux RENAME_NOREPLACE and return (result, errno)."""
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        return -1, errno.ENOSYS

    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    result = renameat2(
        -100,  # AT_FDCWD
        os.fsencode(staging_dir),
        -100,  # AT_FDCWD
        os.fsencode(target),
        1,  # RENAME_NOREPLACE
    )
    return (0, 0) if result == 0 else (-1, ctypes.get_errno())


def _publish_without_overwrite(staging_dir: Path, target: Path) -> None:
    """Publish a validated checkout without replacing an existing target.

    Prefer Linux renameat2(RENAME_NOREPLACE), which is race-safe. Some shared
    filesystems (including some NFS configurations) return EINVAL/ENOSYS or
    EOPNOTSUPP for that operation. In that case, serialize cooperating setup
    processes by locking the parent directory, recheck the destination while
    holding the lock, and use the filesystem's normal atomic same-filesystem
    rename. Never use this fallback if the destination already exists.
    """
    if target.exists() or target.is_symlink():
        raise FileExistsError(
            f"Refusing to overwrite existing LTX runtime path: {target}"
        )

    result, error_number = _renameat2_noreplace(staging_dir, target)
    if result == 0:
        return
    if error_number == errno.EEXIST:
        raise FileExistsError(
            error_number,
            "Target appeared during setup; refusing to overwrite it.",
            str(target),
        )

    unsupported_errors = {errno.EINVAL, errno.ENOSYS}
    for name in ("EOPNOTSUPP", "ENOTSUP"):
        value = getattr(errno, name, None)
        if value is not None:
            unsupported_errors.add(value)
    if error_number not in unsupported_errors:
        raise OSError(
            error_number,
            f"Atomic no-overwrite rename failed: {os.strerror(error_number)}",
            str(target),
        )

    parent = target.parent
    parent_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        try:
            fcntl.flock(parent_fd, fcntl.LOCK_EX)
        except OSError as exc:
            raise RuntimeError(
                f"Filesystem does not support setup serialization for {parent}; "
                "refusing to publish the LTX checkout."
            ) from exc
        try:
            # Recheck after acquiring the parent lock; this prevents a second
            # invocation of this helper from replacing a directory or symlink.
            if target.exists() or target.is_symlink():
                raise FileExistsError(
                    f"Target appeared during setup; refusing to overwrite it: {target}"
                )
            os.rename(staging_dir, target)
        finally:
            fcntl.flock(parent_fd, fcntl.LOCK_UN)
    finally:
        os.close(parent_fd)


def prepare_runtime(
    repo_dir: str | Path,
    *,
    repo_url: str = LTX_REPO_URL,
    commit_sha: str = LTX_COMMIT_SHA,
    configure_environment: bool = True,
) -> Path:
    """Fetch and verify only the pinned commit into staging, then publish it.

    Existing target paths (including symlinks) are never overwritten. The staged
    checkout is created beside the target so publication stays on one filesystem.
    """
    target = Path(os.path.abspath(os.path.expanduser(str(repo_dir))))

    if target.exists() or target.is_symlink():
        raise FileExistsError(
            f"Refusing to overwrite existing LTX runtime path: {target}. "
            "Inspect it manually before deciding how to proceed."
        )
    if not target.name or target == target.parent:
        raise ValueError(f"Unsafe LTX runtime target path: {target}")

    if configure_environment:
        _configure_hpc_environment()

    target.parent.mkdir(parents=True, exist_ok=True)
    staging_dir: Path | None = None
    try:
        staging_dir = Path(
            tempfile.mkdtemp(prefix=f".{target.name}.setup-", dir=str(target.parent))
        )

        # The upstream repository tracks demo/media files with Git LFS. Keep the
        # pointer files but do not download LFS assets into the shared cache.
        git_env = os.environ.copy()
        git_env["GIT_LFS_SKIP_SMUDGE"] = "1"

        _run_git(["init", "--quiet"], cwd=staging_dir)
        _run_git(["remote", "add", "origin", repo_url], cwd=staging_dir)
        _run_git(
            ["fetch", "--no-tags", "--depth", "1", "origin", commit_sha],
            cwd=staging_dir,
            env=git_env,
        )
        _run_git(
            ["checkout", "--detach", "FETCH_HEAD"],
            cwd=staging_dir,
            env=git_env,
        )

        actual_origin = _run_git(["remote", "get-url", "origin"], cwd=staging_dir)
        if actual_origin != repo_url:
            raise RuntimeError(
                f"Fetched remote does not match the pinned repository URL: {actual_origin}"
            )

        actual_commit = _run_git(["rev-parse", "HEAD"], cwd=staging_dir)
        if actual_commit != commit_sha:
            raise RuntimeError(
                f"Pinned checkout mismatch: expected {commit_sha}, got {actual_commit}"
            )

        missing = [
            str(relative)
            for relative in REQUIRED_RELATIVE_DIRS
            if not (staging_dir / relative).is_dir()
        ]
        if missing:
            raise RuntimeError(
                "The pinned LTX checkout is missing required package directories: "
                + ", ".join(missing)
            )

        status = _run_git(["status", "--porcelain"], cwd=staging_dir)
        if status:
            raise RuntimeError(
                "The staged LTX checkout is unexpectedly dirty; refusing to publish it."
            )

        _publish_without_overwrite(staging_dir, target)
        staging_dir = None
        return target
    finally:
        # Remove only the unique staging directory created by this invocation.
        # The target, shared cache, model files, and storage-reserve files are untouched.
        if staging_dir is not None and staging_dir.exists():
            shutil.rmtree(staging_dir)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare the pinned LTX-2 source checkout for worker_ltx_video.py."
    )
    parser.add_argument(
        "--repo-dir",
        help=(
            "Explicit checkout target. Defaults to AIEROS_LTX_REPO_DIR, or "
            "core_config.SYSTEM_DIRS['cache']/third_party/LTX-2."
        ),
    )
    args = parser.parse_args(argv)

    try:
        target = resolve_runtime_dir(args.repo_dir)
        prepared = prepare_runtime(target)
    except Exception as exc:
        print(f"[LTX SETUP] FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"[LTX SETUP] Checkout prepared: {prepared}")
    print(f"[LTX SETUP] Repository: {LTX_REPO_URL}")
    print(f"[LTX SETUP] Pinned commit: {LTX_COMMIT_SHA}")
    print("[LTX SETUP] Source checkout verified; no packages or model weights were installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
