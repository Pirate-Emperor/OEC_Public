#!/usr/bin/env python3
"""Prepare an isolated, pinned ACE-Step runtime without changing shared Conda/Torch."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://github.com/ace-step/ACE-Step-1.5.git"
SOURCE_COMMIT = "ca1e85fe9430179831e6bc6be790c332190a3866"
SOURCE_NAME = "ACE-Step-1.5"
RUNTIME_NAME = "oec-acestep-py311"
WEIGHT_SUFFIXES = {".safetensors", ".bin", ".pt", ".pth"}
REQUIRED_CHECKPOINT_DIRS = (
    "acestep-v15-turbo",
    "vae",
    "Qwen3-Embedding-0.6B",
    "acestep-5Hz-lm-0.6B",
)


def build_paths(home: Path, cache_root: Path, models_root: Path) -> dict[str, Path]:
    """Return distinct code, environment, cache and model roots."""
    home = home.expanduser().resolve()
    cache_root = cache_root.expanduser().resolve()
    models_root = models_root.expanduser().resolve()
    source_root = cache_root / "third_party" / SOURCE_NAME
    venv_root = home / ".local" / "venvs" / RUNTIME_NAME
    model_root = models_root / "ace-step-1.5"
    if source_root == model_root or model_root.is_relative_to(source_root):
        raise ValueError("ACE-Step source checkout and model weights must use separate roots")
    if not source_root.is_relative_to(cache_root):
        raise ValueError("ACE-Step source checkout must remain under the configured AIEROS cache")
    if not model_root.is_relative_to(models_root):
        raise ValueError("ACE-Step weights must remain under the configured AIEROS models root")
    return {
        "cache_root": cache_root,
        "source_root": source_root,
        "venv_root": venv_root,
        "python": venv_root / "bin" / "python",
        "models_root": models_root,
        "model_root": model_root,
        "uv_cache": cache_root / "uv" / "ace-step",
    }


def has_weights(folder: Path) -> bool:
    """Check for a nonempty real checkpoint file without following symlinks."""
    if folder.is_symlink() or not folder.is_dir():
        return False
    for parent, dirs, files in os.walk(folder, followlinks=False):
        base = Path(parent)
        dirs[:] = [name for name in dirs if not (base / name).is_symlink()]
        for name in files:
            path = base / name
            if path.is_symlink() or path.suffix.lower() not in WEIGHT_SUFFIXES:
                continue
            try:
                if path.is_file() and path.stat().st_size > 0:
                    return True
            except OSError:
                continue
    return False


def checkpoint_status(model_root: Path) -> dict[str, Any]:
    """Check every model folder required by this ACE-Step adapter."""
    model_root = model_root.expanduser()
    if model_root.is_symlink() or not model_root.is_dir():
        missing = list(REQUIRED_CHECKPOINT_DIRS)
        return {"root": str(model_root), "complete": False, "missing": missing}
    missing = [name for name in REQUIRED_CHECKPOINT_DIRS if not has_weights(model_root / name)]
    return {"root": str(model_root), "complete": not missing, "missing": missing}


def _run(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
         timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    print("ACE_STEP_COMMAND=" + json.dumps(argv), flush=True)
    result = subprocess.run(
        argv, cwd=str(cwd) if cwd else None, env=env, capture_output=True, text=True,
        timeout=timeout, check=False,
    )
    if result.stdout:
        print(result.stdout[-12000:], end="" if result.stdout.endswith("\n") else "\n", flush=True)
    if result.stderr:
        print(result.stderr[-12000:], file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n", flush=True)
    if result.returncode:
        raise RuntimeError(f"command failed with exit code {result.returncode}: {Path(argv[0]).name}")
    return result


def _system_dirs() -> dict[str, Path]:
    sys.path.insert(0, str(ROOT))
    import core_config

    directories = core_config.SYSTEM_DIRS
    for key in ("cache", "models"):
        value = directories.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"core_config.SYSTEM_DIRS[{key!r}] is missing")
    return {key: Path(directories[key]).expanduser().resolve() for key in ("cache", "models")}


def _git(source_root: Path, *args: str, timeout: int = 1800) -> str:
    result = _run(["git", "-C", str(source_root), *args], timeout=timeout)
    return result.stdout.strip()


def _is_pristine_no_checkout_tree(source_root: Path, status: str) -> bool:
    """Recognize an empty no-checkout clone, not a modified source tree."""
    if source_root.is_symlink() or not source_root.is_dir():
        return False
    try:
        entries = [item for item in source_root.iterdir() if item.name != ".git"]
    except OSError:
        return False
    if entries:
        return False
    rows = [line for line in status.splitlines() if line.strip()]
    return bool(rows) and all(line[:2].strip() == "D" for line in rows)


def _ensure_source_checkout(source_root: Path) -> str:
    """Create or update a tool-owned checkout to one immutable public commit."""
    if source_root.is_symlink():
        raise RuntimeError(f"refusing symlink for ACE-Step checkout: {source_root}")
    if not source_root.exists():
        source_root.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--filter=blob:none", "--no-checkout", SOURCE_URL, str(source_root)], timeout=900)
    if not source_root.is_dir() or not (source_root / ".git").is_dir():
        raise RuntimeError(f"ACE-Step source path is not a git checkout: {source_root}")
    origin = _git(source_root, "remote", "get-url", "origin")
    if origin.rstrip("/").removesuffix(".git").lower() != SOURCE_URL.rstrip("/").removesuffix(".git").lower():
        raise RuntimeError(f"unexpected ACE-Step git origin; refusing to reuse checkout: {origin}")
    status = _git(source_root, "status", "--porcelain", "--untracked-files=normal")
    if status:
        if _is_pristine_no_checkout_tree(source_root, status):
            print("ACE_STEP_EMPTY_NO_CHECKOUT=detected; restoring the pinned worktree", flush=True)
        else:
            raise RuntimeError("ACE-Step cached source checkout is dirty; refusing to overwrite local changes")
    elif not any(item.name != ".git" for item in source_root.iterdir()):
        raise RuntimeError("ACE-Step checkout is empty without a no-checkout deletion status; refusing recovery")
    _run(["git", "-C", str(source_root), "fetch", "--depth", "1", "origin", SOURCE_COMMIT], timeout=900)
    _run(["git", "-C", str(source_root), "checkout", "--detach", SOURCE_COMMIT], timeout=120)
    actual = _git(source_root, "rev-parse", "HEAD")
    if actual != SOURCE_COMMIT:
        raise RuntimeError(f"ACE-Step checkout is {actual}, expected pinned commit {SOURCE_COMMIT}")
    if not (source_root / "pyproject.toml").is_file() or not (source_root / "uv.lock").is_file():
        raise RuntimeError("pinned ACE-Step source is missing pyproject.toml or uv.lock")
    return actual


def _uv_executable() -> str:
    path = shutil.which("uv")
    if path:
        return path
    candidates = (
        Path(sys.prefix) / "bin" / "uv",
        Path.home() / "Conda" / "envs" / "oec_deploy" / "bin" / "uv",
        Path.home() / "Conda" / "bin" / "uv",
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise RuntimeError("uv is not present in the existing environment; no package manager was installed")


def _runtime_environment(paths: dict[str, Path]) -> dict[str, str]:
    env = os.environ.copy()
    env["UV_PROJECT_ENVIRONMENT"] = str(paths["venv_root"])
    env["UV_CACHE_DIR"] = str(paths["uv_cache"])
    env["AIEROS_ACE_STEP_SOURCE_ROOT"] = str(paths["source_root"])
    env["ACESTEP_CHECKPOINTS_DIR"] = str(paths["model_root"])
    env["ACESTEP_PROJECT_ROOT"] = str(paths["source_root"])
    env["ACESTEP_LM_BACKEND"] = "pt"
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    env["TORCH_HOME"] = str(paths["models_root"] / "torch_hub")
    env["PYTHONUNBUFFERED"] = "1"
    env.pop("VIRTUAL_ENV", None)
    return env


def _verify_runtime(paths: dict[str, Path], *, require_models: bool = True) -> dict[str, Any]:
    report = {
        "source_root": str(paths["source_root"]),
        "expected_source_commit": SOURCE_COMMIT,
        "venv_root": str(paths["venv_root"]),
        "models": checkpoint_status(paths["model_root"]),
    }
    source_sha = _git(paths["source_root"], "rev-parse", "HEAD")
    report["source_commit"] = source_sha
    if source_sha != SOURCE_COMMIT:
        raise RuntimeError(f"ACE-Step source commit mismatch: {source_sha}")
    if require_models and not report["models"]["complete"]:
        raise RuntimeError("ACE-Step checkpoints are incomplete: " + ", ".join(report["models"]["missing"]))
    if paths["venv_root"].is_symlink() or not paths["python"].is_file():
        raise RuntimeError(f"isolated ACE-Step Python does not exist: {paths['python']}")
    env = _runtime_environment(paths)
    code = r'''
import json, os, sys
from pathlib import Path
import torch
import acestep
import acestep.handler
prefix = Path(sys.prefix).resolve()
torch_path = Path(torch.__file__).resolve()
source = Path(os.environ["AIEROS_ACE_STEP_SOURCE_ROOT"]).resolve()
module_path = Path(acestep.__file__).resolve()
if prefix not in torch_path.parents:
    raise SystemExit("Torch was imported from outside the isolated ACE-Step venv: " + str(torch_path))
if source not in module_path.parents:
    raise SystemExit("ACE-Step was imported from outside the pinned checkout: " + str(module_path))
if not torch.cuda.is_available():
    raise SystemExit("CUDA is unavailable inside the isolated ACE-Step runtime")
gpu = torch.cuda.get_device_name(0)
if "A100" not in gpu.upper():
    raise SystemExit("expected A100 as first visible GPU; got " + gpu)
print(json.dumps({
 "python": sys.executable, "python_prefix": str(prefix), "torch_version": torch.__version__,
 "torch_cuda": torch.version.cuda, "torch_path": str(torch_path), "cuda_available": True,
 "gpu_name": gpu, "acestep_path": str(module_path), "source_root": str(source),
 "checkpoint_root": os.environ["ACESTEP_CHECKPOINTS_DIR"], "lm_backend": os.environ["ACESTEP_LM_BACKEND"]
}, sort_keys=True))
'''
    checked = _run([str(paths["python"]), "-c", code], env=env, timeout=180)
    parsed: dict[str, Any] | None = None
    for line in reversed(checked.stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "torch_version" in value:
            parsed = value
            break
    if parsed is None:
        raise RuntimeError("isolated ACE-Step verification did not emit its runtime report")
    report["runtime"] = parsed
    return report


def status() -> int:
    directories = _system_dirs()
    paths = build_paths(Path.home(), directories["cache"], directories["models"])
    source_commit = None
    if (paths["source_root"] / ".git").is_dir() and not paths["source_root"].is_symlink():
        try:
            source_commit = _git(paths["source_root"], "rev-parse", "HEAD")
        except Exception:
            source_commit = "unavailable"
    report = {
        "source_url": SOURCE_URL,
        "source_commit_pinned": SOURCE_COMMIT,
        "source_root": str(paths["source_root"]),
        "cached_source_commit": source_commit,
        "venv_python": str(paths["python"]),
        "venv_present": paths["python"].is_file() and not paths["venv_root"].is_symlink(),
        "models": checkpoint_status(paths["model_root"]),
        "reserve_file_accessed": False,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def install() -> int:
    directories = _system_dirs()
    paths = build_paths(Path.home(), directories["cache"], directories["models"])
    # Check the complete model layout before spending time building the isolated runtime.
    model_report = checkpoint_status(paths["model_root"])
    print("ACE_STEP_MODEL_PREFLIGHT " + json.dumps(model_report, sort_keys=True), flush=True)
    if not model_report["complete"]:
        raise RuntimeError(
            "ACE-Step model folders are incomplete. Use tools/prepare_media_models.py to download "
            "ace-step-main and ace-step-lm-0.6b through StorageManager, then retry. Missing: "
            + ", ".join(model_report["missing"])
        )
    if sys.version_info < (3, 11) or sys.version_info >= (3, 13):
        raise RuntimeError(f"ACE-Step requires Python 3.11-3.12; current interpreter is {sys.version.split()[0]}")
    source_commit = _ensure_source_checkout(paths["source_root"])
    uv = _uv_executable()
    paths["uv_cache"].mkdir(parents=True, exist_ok=True)
    if paths["venv_root"].is_symlink():
        raise RuntimeError(f"refusing symlink for isolated ACE-Step venv: {paths['venv_root']}")
    env = _runtime_environment(paths)
    print(
        "ACE_STEP_RUNTIME_INSTALL " + json.dumps({
            "source_commit": source_commit, "venv": str(paths["venv_root"]),
            "cache_dir": str(paths["uv_cache"]), "shared_torch_mutated": False,
            "model_downloads_by_installer": False,
        }, sort_keys=True),
        flush=True,
    )
    _run([uv, "sync", "--locked", "--python", sys.executable, "--no-progress"],
         cwd=paths["source_root"], env=env, timeout=2400)
    report = _verify_runtime(paths, require_models=True)
    report["status"] = "PASS"
    report["shared_torch_mutated"] = False
    report["model_downloads_by_installer"] = False
    print("ACE_STEP_RUNTIME_ACCEPTANCE " + json.dumps(report, sort_keys=True), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="report pinned source, isolated venv and existing model-checkpoint status")
    commands.add_parser("install", help="install the pinned official source into an isolated venv, without model downloads")
    args = parser.parse_args()
    try:
        return status() if args.command == "status" else install()
    except Exception as exc:
        print(json.dumps({
            "status": "FAIL", "error_type": type(exc).__name__, "error": str(exc),
            "reserve_file_accessed": False, "shared_torch_mutated": False,
        }, sort_keys=True), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
