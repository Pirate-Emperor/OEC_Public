"""Pure GPU selection/purge policy helpers for the LTX worker.

This module intentionally has no PyTorch/CUDA imports and does not mutate storage.
"""
from __future__ import annotations

import subprocess


def get_available_gpu_ids() -> list[str]:
    """Return physical GPU indices reported by nvidia-smi."""
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
            encoding="utf-8",
            stderr=subprocess.STDOUT,
            timeout=10,
        )
    except Exception as exc:
        raise ValueError(f"Could not discover physical GPUs with nvidia-smi: {exc}") from exc

    gpu_ids = []
    for line in output.splitlines():
        value = line.strip()
        if value.isdigit():
            gpu_ids.append(str(int(value)))
    if not gpu_ids:
        raise ValueError("nvidia-smi did not report any physical GPUs.")
    return gpu_ids


def resolve_gpu_selection(requested_gpus: str | None, available_gpu_ids: list[str]) -> list[str]:
    """Validate explicit IDs, or leave GPU 0 free when multiple GPUs exist."""
    available = [str(int(item)) for item in available_gpu_ids]
    if not available:
        raise ValueError("No GPUs are available on this host.")
    if requested_gpus is None or not requested_gpus.strip():
        preferred = [gpu for gpu in available if gpu != "0"]
        return preferred or available

    selected = [part.strip() for part in requested_gpus.split(",") if part.strip()]
    if not selected:
        raise ValueError("The --gpus list is empty.")
    if any(not item.isdigit() for item in selected):
        raise ValueError(f"Invalid --gpus value {requested_gpus!r}; use comma-separated integer IDs.")
    selected = [str(int(item)) for item in selected]
    if len(selected) != len(set(selected)):
        raise ValueError(f"The --gpus list contains duplicate IDs: {selected}.")
    unavailable = [gpu for gpu in selected if gpu not in available]
    if unavailable:
        raise ValueError(f"Requested GPU IDs {unavailable}, but this host reports only {available}.")
    return selected


def cluster_purge_is_enabled(cluster_gpus: int, should_purge: bool) -> bool:
    """Distributed cache purge/synchronization only runs when purge is explicitly enabled."""
    return int(cluster_gpus) > 1 and bool(should_purge)
