"""Read-only checks for OEC's already-allocated storage reserve files.

The reserve file is an allocation guard, not a model checkpoint. Read only a
small prefix and filesystem metadata; never copy it into the model directory.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

RESERVE_FILENAME = ".storage_reserve.bin"
BYTES_PER_GB = 1024**3


def inspect_reserve_file(path: str | Path, sample_bytes: int = 16) -> dict[str, Any]:
    """Validate a reserve is a real allocated file and sample at most 16 bytes."""
    target = Path(path).expanduser()
    if isinstance(sample_bytes, bool) or not isinstance(sample_bytes, int) or not 0 <= sample_bytes <= 16:
        raise ValueError("sample_bytes must be an integer from 0 to 16")
    if target.is_symlink() or not target.is_file():
        raise RuntimeError(f"storage reserve is missing, not a regular file, or is a symlink: {target}")
    info = target.stat()
    if info.st_size <= 0:
        raise RuntimeError(f"storage reserve is empty: {target}")
    allocated_bytes = int(getattr(info, "st_blocks", 0)) * 512
    if allocated_bytes < int(info.st_size * 0.95):
        raise RuntimeError(
            f"storage reserve is sparse or insufficiently allocated: size={info.st_size} allocated={allocated_bytes}"
        )
    with target.open("rb") as handle:
        prefix = handle.read(sample_bytes)
    return {
        "path": str(target.resolve()),
        "size_bytes": int(info.st_size),
        "allocated_bytes": allocated_bytes,
        "sample_bytes": len(prefix),
        "sample_prefix_hex": prefix.hex(),
        "is_symlink": False,
        "is_dense_allocation": True,
    }


def inspect_managed_reserve(
    area: str,
    reported_reserve_gb: float | None = None,
    system_dirs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Inspect a configured managed-area reserve without changing it."""
    if system_dirs is None:
        import core_config
        system_dirs = core_config.SYSTEM_DIRS
    if area not in system_dirs:
        raise KeyError(f"unknown configured OEC storage area: {area}")
    folder = Path(system_dirs[area]).expanduser()
    path = folder / RESERVE_FILENAME
    result = inspect_reserve_file(path)
    actual_gb = result["size_bytes"] / BYTES_PER_GB
    if reported_reserve_gb is not None and abs(actual_gb - float(reported_reserve_gb)) > 0.03:
        raise RuntimeError(
            f"{area} reserve status/file size disagree: StorageManager={float(reported_reserve_gb):.3f} GB, "
            f"file={actual_gb:.3f} GB"
        )
    return {"area": area, **result, "reserve_gb": actual_gb}
