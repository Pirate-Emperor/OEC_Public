"""Pure selection/policy helpers for the LTX worker.

No CUDA context, storage manager, model import, or filesystem mutation occurs here.
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
        raise ValueError(
            f"Could not discover physical GPUs with nvidia-smi: {exc}"
        ) from exc

    gpu_ids = []
    for line in output.splitlines():
        value = line.strip()
        if value.isdigit():
            gpu_ids.append(str(int(value)))

    if not gpu_ids:
        raise ValueError("nvidia-smi did not report any available physical GPUs.")
    return gpu_ids


def resolve_gpu_selection(
    requested_gpus: str | None, available_gpu_ids: list[str]
) -> list[str]:
    """Validate explicit GPU IDs, or choose safe defaults for this host.

    The default keeps physical GPU 0 free when at least one other GPU exists,
    matching the project's usual reservation of GPU 0 for the reasoning model.
    On a single-GPU host, that GPU remains a valid fallback.
    """
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
        raise ValueError(
            f"Invalid --gpus value {requested_gpus!r}; use comma-separated integer GPU IDs."
        )
    selected = [str(int(item)) for item in selected]
    if len(selected) != len(set(selected)):
        raise ValueError(f"The --gpus list contains duplicate IDs: {selected}.")

    unavailable = [gpu for gpu in selected if gpu not in available]
    if unavailable:
        raise ValueError(
            f"Requested GPU IDs {unavailable}, but this host exposes only {available}. "
            "Choose only the IDs reported by nvidia-smi."
        )
    return selected


def cluster_purge_is_enabled(cluster_gpus: int, should_purge: bool) -> bool:
    """Distributed purge and its synchronization run only when purge is enabled."""
    return int(cluster_gpus) > 1 and bool(should_purge)
