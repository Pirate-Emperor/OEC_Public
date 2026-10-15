"""Offline-only helpers for cached TRELLIS.2 snapshots.

The upstream loader looks up pipeline.json on the Hugging Face Hub when it is
absent from a local weight snapshot. Keep the config overlay and Hub metadata
under local /tmp; never write into shared model-cache files.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Iterator

MODEL_ID = "microsoft/TRELLIS.2-4B"
PINNED_CONFIG_REVISION = "af44b45f2e35a493886929c6d786e563ec68364d"
BUNDLED_CONFIG = Path(__file__).resolve().with_name("trellis2_pipeline.json")


def is_valid_pipeline_config(path: str | Path) -> bool:
    """Accept only a TRELLIS2 config with a non-empty model registry."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("name") == "Trellis2ImageTo3DPipeline"
        and isinstance(payload.get("args"), dict)
        and isinstance(payload["args"].get("models"), dict)
        and bool(payload["args"]["models"])
    )


def _mirror_cached_repositories(
    cache_roots: tuple[Path, ...],
    destination_cache: Path,
    primary_repo_name: str,
) -> None:
    """Mirror cached HF refs and snapshot links; copy only small metadata files."""
    for cache_root in cache_roots:
        if not cache_root.is_dir():
            continue
        for source_repo in sorted(cache_root.glob("models--*")):
            if not source_repo.is_dir() or source_repo.name == primary_repo_name:
                continue
            destination_repo = destination_cache / source_repo.name
            destination_repo.mkdir(mode=0o700, parents=True, exist_ok=True)

            source_snapshots = source_repo / "snapshots"
            mirrored_names: list[str] = []
            if source_snapshots.is_dir():
                destination_snapshots = destination_repo / "snapshots"
                destination_snapshots.mkdir(mode=0o700, exist_ok=True)
                for source_snapshot in sorted(source_snapshots.iterdir()):
                    try:
                        resolved = source_snapshot.resolve(strict=True)
                    except OSError:
                        continue
                    if not resolved.is_dir():
                        continue
                    target = destination_snapshots / source_snapshot.name
                    if not target.exists() and not target.is_symlink():
                        target.symlink_to(str(resolved), target_is_directory=True)
                    mirrored_names.append(source_snapshot.name)

            source_refs = source_repo / "refs"
            if source_refs.is_dir():
                destination_refs = destination_repo / "refs"
                destination_refs.mkdir(mode=0o700, exist_ok=True)
                for source_ref in sorted(source_refs.iterdir()):
                    if not source_ref.is_file():
                        continue
                    target = destination_refs / source_ref.name
                    if not target.exists():
                        shutil.copyfile(source_ref, target)

            # A missing refs/main can be reconstructed only when the repository has
            # exactly one cached revision; never guess between multiple snapshots.
            refs_dir = destination_repo / "refs"
            refs_dir.mkdir(mode=0o700, exist_ok=True)
            main_ref = refs_dir / "main"
            if not main_ref.exists() and len(set(mirrored_names)) == 1:
                main_ref.write_text(mirrored_names[0] + "\n", encoding="utf-8")


def prepare_local_trellis_snapshot(
    snapshot: str | Path,
    repo_id: str = MODEL_ID,
    *,
    cache_roots: tuple[str | Path, ...] = (),
    temp_root: str | Path = "/tmp",
) -> tuple[str, tempfile.TemporaryDirectory]:
    """Return a local config-complete snapshot overlay and its lifetime owner.

    A valid local pipeline.json is copied into the overlay. If it is missing, the
    bundled official config is permitted only for the known snapshot revision.
    Model files are symlinked read-only from the existing cache. A private HF cache
    view is created beside the overlay to expose cached submodel dependencies with
    no writes to shared-cache metadata.
    """
    snapshot_path = Path(snapshot).expanduser().resolve()
    if not snapshot_path.is_dir():
        raise RuntimeError(f"BLOCKED_TRELLIS_CACHE: local model snapshot is missing: {snapshot_path}")

    local_config = snapshot_path / "pipeline.json"
    if local_config.is_file():
        if not is_valid_pipeline_config(local_config):
            raise RuntimeError(
                f"BLOCKED_TRELLIS_CONFIG: invalid local pipeline.json in {snapshot_path}"
            )
        selected_config = local_config
    elif repo_id == MODEL_ID and snapshot_path.name == PINNED_CONFIG_REVISION:
        if not is_valid_pipeline_config(BUNDLED_CONFIG):
            raise RuntimeError(f"BLOCKED_TRELLIS_CONFIG: bundled config is invalid: {BUNDLED_CONFIG}")
        selected_config = BUNDLED_CONFIG
    else:
        raise RuntimeError(
            "BLOCKED_TRELLIS_CONFIG: pipeline.json is absent and no bundled config "
            f"is approved for repo={repo_id!r}, snapshot={snapshot_path.name!r}"
        )

    roots: list[Path] = []
    seen: set[Path] = set()
    for root in cache_roots:
        try:
            resolved = Path(root).expanduser().resolve()
        except OSError:
            continue
        if resolved not in seen and resolved.is_dir():
            roots.append(resolved)
            seen.add(resolved)

    temp = tempfile.TemporaryDirectory(prefix="oec-trellis-pipeline-", dir=str(temp_root))
    try:
        temp_path = Path(temp.name)
        overlay = temp_path / "snapshot"
        hf_home = temp_path / "hf-home"
        hf_cache = temp_path / "hf-hub"
        overlay.mkdir(mode=0o700)
        hf_home.mkdir(mode=0o700)
        hf_cache.mkdir(mode=0o700)

        for entry in sorted(snapshot_path.iterdir()):
            if entry.name == "pipeline.json":
                continue
            try:
                resolved = entry.resolve(strict=True)
            except OSError as exc:
                raise RuntimeError(
                    f"BLOCKED_TRELLIS_CACHE: snapshot entry is missing or dangling: {entry}"
                ) from exc
            (overlay / entry.name).symlink_to(
                str(resolved), target_is_directory=resolved.is_dir()
            )
        shutil.copyfile(selected_config, overlay / "pipeline.json")
        if not is_valid_pipeline_config(overlay / "pipeline.json"):
            raise RuntimeError("BLOCKED_TRELLIS_CONFIG: copied pipeline.json failed validation")

        repo_cache_name = f"models--{repo_id.replace('/', '--')}"
        _mirror_cached_repositories(tuple(roots), hf_cache, repo_cache_name)
        repo_cache = hf_cache / repo_cache_name
        snapshots_dir = repo_cache / "snapshots"
        refs_dir = repo_cache / "refs"
        snapshots_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        refs_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        snapshot_link = snapshots_dir / snapshot_path.name
        if not snapshot_link.exists() and not snapshot_link.is_symlink():
            snapshot_link.symlink_to(str(overlay), target_is_directory=True)
        (refs_dir / "main").write_text(snapshot_path.name + "\n", encoding="utf-8")
        return str(overlay), temp
    except BaseException:
        temp.cleanup()
        raise


@contextmanager
def offline_hub_mode(cache_view: str | Path | tempfile.TemporaryDirectory | None = None) -> Iterator[None]:
    """Block implicit Hub requests, redirect metadata to /tmp, then restore state."""
    env_names = (
        "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HOME", "HF_HUB_CACHE",
        "HUGGINGFACE_HUB_CACHE", "TRANSFORMERS_CACHE",
    )
    previous_env = {name: os.environ.get(name) for name in env_names}
    module_attrs = {
        "huggingface_hub.constants": (
            "HF_HUB_OFFLINE", "HF_HOME", "HF_HUB_CACHE",
        ),
        "huggingface_hub.file_download": ("HF_HUB_OFFLINE", "HF_HUB_CACHE"),
        "transformers.utils.hub": (
            "HF_HUB_OFFLINE", "HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE",
            "_is_offline_mode",
        ),
    }
    previous_attrs: list[tuple[object, str, object]] = []
    try:
        for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
            os.environ[name] = "1"
        if cache_view is not None:
            owner_path = Path(cache_view.name if isinstance(cache_view, tempfile.TemporaryDirectory) else cache_view)
            hf_home, hf_cache = owner_path / "hf-home", owner_path / "hf-hub"
            for name, value in (
                ("HF_HOME", hf_home),
                ("HF_HUB_CACHE", hf_cache),
                ("HUGGINGFACE_HUB_CACHE", hf_cache),
                ("TRANSFORMERS_CACHE", hf_cache),
            ):
                os.environ[name] = str(value)
        for module_name, attrs in module_attrs.items():
            module = sys.modules.get(module_name)
            if module is None:
                continue
            for attr in attrs:
                if not hasattr(module, attr):
                    continue
                previous_attrs.append((module, attr, getattr(module, attr)))
                if attr in ("HF_HUB_OFFLINE", "_is_offline_mode"):
                    setattr(module, attr, True)
                elif cache_view is not None and attr in ("HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE"):
                    owner_path = Path(cache_view.name if isinstance(cache_view, tempfile.TemporaryDirectory) else cache_view)
                    setattr(module, attr, str(owner_path / ("hf-home" if attr == "HF_HOME" else "hf-hub")))
        yield
    finally:
        for module, attr, value in reversed(previous_attrs):
            setattr(module, attr, value)
        for name, value in previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
