#!/usr/bin/env python3
"""Read OEC StorageManager status or download selected media-model weights safely.

This script never starts the StorageManager daemon, installs dependencies, accesses
.reserve files directly, or purges models. Downloads are explicit, one model at a
time, and gated by the existing OEC StorageManager admission + managed-write API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import shutil
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "tools"
for _entry in (str(ROOT), str(TOOLS_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from core_config import SYSTEM_DIRS  # noqa: E402
from storage_reserve_probe import inspect_managed_reserve  # noqa: E402
from media_services.model_cache import MODELS_ROOT, cache_status, hf_cache_has_weights, model_targets  # noqa: E402
from storage_manager import managed_storage_operation, storage_preflight  # noqa: E402

HUB_CACHE = MODELS_ROOT / "hub"
MINIMUM_FREE_GB = 2.0

MODEL_SPECS: dict[str, dict[str, Any]] = {
    "kokoro": {
        "kind": "hf-cache", "repo_id": "hexgrad/Kokoro-82M", "required_gb": 1.0,
        "summary": "Kokoro-82M English speech synthesis (Hugging Face cache)",
    },
    "whisper-turbo": {
        "kind": "whisper-file", "size": "turbo", "required_gb": 2.0,
        "summary": "OpenAI Whisper turbo checkpoint (official SHA-256 URL)",
    },
    "qwen3-asr-0.6b": {
        "kind": "hf-cache", "repo_id": "Qwen/Qwen3-ASR-0.6B", "required_gb": 3.0,
        "summary": "Qwen3-ASR-0.6B multilingual speech recognition (~1.88 GB upstream checkpoint)",
    },
    "ace-step-main": {
        "kind": "hf-local", "repo_id": "ACE-Step/Ace-Step1.5", "required_gb": 12.0,
        "target": MODELS_ROOT / "ace-step-1.5",
        "summary": "ACE-Step 1.5 DiT, VAE and text encoder; skips unused bundled 1.7B LM",
    },
    "ace-step-lm-0.6b": {
        "kind": "hf-local", "repo_id": "ACE-Step/acestep-5Hz-lm-0.6B", "required_gb": 3.0,
        "target": MODELS_ROOT / "ace-step-1.5" / "acestep-5Hz-lm-0.6B",
        "summary": "ACE-Step optional 0.6B 5Hz language model",
    },
}
DOWNLOAD_ORDER = ("kokoro", "whisper-turbo", "qwen3-asr-0.6b", "ace-step-main", "ace-step-lm-0.6b")
WHISPER_MODELS = {
    # URL path embeds the expected SHA-256 exactly as in openai/whisper.
    "tiny": ("https://openaipublic.azureedge.net/main/whisper/models/65147644a518d12f04e32d6f3b26facc3f8dd46e5390956a9424a650c0ce22b9/tiny.pt", 0.2),
    "base": ("https://openaipublic.azureedge.net/main/whisper/models/ed3a0b6b1c0edf879ad9b11b1af5a0e6ab5db9205f891f668f8b0e6c6326e34e/base.pt", 0.3),
    "small": ("https://openaipublic.azureedge.net/main/whisper/models/9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794/small.pt", 1.0),
    "medium": ("https://openaipublic.azureedge.net/main/whisper/models/345ae4da62f9b3d59415adc60127b97c714f32e89e936602e85993674d08dcb1/medium.pt", 5.5),
    "large-v3": ("https://openaipublic.azureedge.net/main/whisper/models/e5b1a55b89c1367dacf97e3e19bfd829a01529dbfdeefa8caeb59b3f1b81dadb/large-v3.pt", 10.5),
    "turbo": ("https://openaipublic.azureedge.net/main/whisper/models/aff26ae408abcba5fbf8813c21e62b0941638c5f6eebfb145be0c9839262a19a/large-v3-turbo.pt", 2.0),
}


def _bytes(path: Path) -> int:
    if path.is_symlink() or not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for folder, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(folder) / name).is_symlink()]
        for name in files:
            item = Path(folder) / name
            if item.is_symlink():
                continue
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def _has_weights(path: Path) -> bool:
    if not path.is_dir() or path.is_symlink():
        return False
    extensions = {".safetensors", ".bin", ".pt", ".pth"}
    for item in path.rglob("*"):
        if item.is_symlink() or not item.is_file() or item.suffix.lower() not in extensions:
            continue
        try:
            if item.stat().st_size > 0:
                return True
        except OSError:
            continue
    return False


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _is_complete(model: str) -> bool:
    if model == "kokoro":
        return hf_cache_has_weights("kokoro")
    if model == "qwen3-asr-0.6b":
        return hf_cache_has_weights("qwen3-asr-0.6b")
    if model == "whisper-turbo":
        target = MODELS_ROOT / "whisper" / "turbo" / Path(WHISPER_MODELS["turbo"][0]).name
        if not target.is_file() or target.is_symlink():
            return False
        return _sha256(target) == WHISPER_MODELS["turbo"][0].split("/")[-2]
    if model == "ace-step-main":
        root = MODEL_SPECS[model]["target"]
        return all(_has_weights(root / name) for name in ("acestep-v15-turbo", "vae", "Qwen3-Embedding-0.6B"))
    if model == "ace-step-lm-0.6b":
        return _has_weights(MODEL_SPECS[model]["target"])
    return False


def _models_config() -> tuple[dict[str, Any], dict[str, Any]]:
    config_path = ROOT / "storage_config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read active storage_config.json ({type(exc).__name__})") from exc
    entry = next((item for item in config.get("directories", []) if item.get("name") == "models"), None)
    if not isinstance(entry, dict):
        raise RuntimeError("models logical storage directory is missing from storage_config.json")
    return config, entry


def _read_model_storage_status() -> dict[str, Any]:
    command = [sys.executable, str(ROOT / "storage_manager.py"), "--status"]
    try:
        proc = subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True, timeout=30, check=False)
    except Exception as exc:
        raise RuntimeError(f"StorageManager status could not run ({type(exc).__name__})") from exc
    if proc.returncode:
        raise RuntimeError(f"StorageManager --status failed: {proc.stderr[-2000:]}")
    match = re.search(
        r"\[models\]\s+state=(\w+)\s+actual=([\d.]+)\s+GB\s*/\s*([\d.]+)\s+GB\s+reserve=([\d.]+)\s+GB",
        proc.stdout,
    )
    if not match:
        raise RuntimeError("could not parse the live [models] status row; refusing capacity assumptions")
    state, actual, target, reserve = match.groups()
    return {"state": state.upper(), "actual_gb": float(actual), "target_gb": float(target),
            "reserve_gb": float(reserve), "stdout": proc.stdout, "stderr": proc.stderr}


def _effective_reserve_floor(requested_gb: float) -> float:
    config, models = _models_config()
    minimum = float(models.get("minimum_reserve_gb", config.get("minimum_reserve_gb", 0.25)))
    configured_target = models.get("reserve_target_gb")
    floor = max(float(requested_gb), minimum)
    if configured_target is not None:
        floor = max(floor, float(configured_target))
    if floor <= 0:
        raise RuntimeError("refusing zero or negative model reserve")
    return floor


def _manager_directory_capacity(required_gb: float, reserve_floor_gb: float, *, resize_reserve: bool) -> dict[str, Any]:
    """Admit model writes without resizing the existing allocated reserve.

    StorageManager's fresh-quota preflight below the caller remains authoritative
    for hard-quota headroom. The models target is a payload budget; adding the
    already-allocated reserve to that payload budget double-counts the same
    protected blocks and was rejecting cached-model workflows unnecessarily.
    """
    status = _read_model_storage_status()
    reserve_floor_gb = _effective_reserve_floor(reserve_floor_gb)
    state, actual, target, reserve = status["state"], status["actual_gb"], status["target_gb"], status["reserve_gb"]
    if state not in {"NORMAL", "WARNING"}:
        raise RuntimeError(f"OEC models directory state is {state}; refusing new model writes")

    reserve_file = inspect_managed_reserve("models", reserve, SYSTEM_DIRS)
    if reserve <= 0:
        raise RuntimeError("models reserve is not positive; no reserve mutation or model download was attempted")
    if reserve + 0.1 < reserve_floor_gb:
        raise RuntimeError(
            f"existing models reserve {reserve:.2f} GB is below the configured minimum {reserve_floor_gb:.2f} GB; "
            "the downloader will not grow or shrink reserve files"
        )

    projected = actual + float(required_gb) + MINIMUM_FREE_GB
    if projected > target + 0.01:
        raise RuntimeError(
            f"models payload budget denied: content={actual:.2f} GB + download={required_gb:.2f} GB "
            f"+ free-space margin={MINIMUM_FREE_GB:.2f} GB exceeds target={target:.2f} GB"
        )

    # Kept in the return schema for callers; resize_reserve remains accepted for
    # backward-compatible CLI wiring but can no longer trigger a reserve resize.
    return {
        "state": state,
        "content_gb": actual,
        "target_gb": target,
        "reserve_gb": reserve,
        "reserve_file": reserve_file,
        "planned_reserve_after_download_gb": reserve,
        "reserve_resize_needed": False,
        "reserve_resize_requested_but_ignored": bool(resize_reserve),
        "required_download_gb": float(required_gb),
        "safety_margin_gb": MINIMUM_FREE_GB,
        "projected_payload_plus_free_space_gb": projected,
        "reserve_floor_gb": reserve_floor_gb,
        "reserve_resized": False,
    }


def _storage_manager_status() -> dict[str, Any]:

def _storage_manager_status() -> dict[str, Any]:
    """Invoke the existing CLI's read-only --status command; never start daemon mode."""
    command = [sys.executable, str(ROOT / "storage_manager.py"), "--status"]
    try:
        proc = subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True, timeout=25, check=False)
        return {"command": "storage_manager.py --status", "returncode": proc.returncode,
                "stdout": proc.stdout[-12000:], "stderr": proc.stderr[-4000:]}
    except Exception as exc:
        return {"command": "storage_manager.py --status", "error": f"{type(exc).__name__}: {exc}"}


def _manager_processes() -> list[str]:
    try:
        proc = subprocess.run(["ps", "-eo", "pid=,etime=,args="], text=True, capture_output=True, timeout=5, check=False)
        rows = []
        for line in proc.stdout.splitlines():
            if "storage_manager.py" not in line or "--status" in line:
                continue
            if str(Path(__file__).resolve()) in line:
                continue
            rows.append(line.strip())
        return rows
    except Exception:
        return []


def environment_audit() -> int:
    """Inspect selected pre-existing Conda envs without installing or importing models."""
    conda = shutil.which("conda")
    if not conda:
        candidate = Path.home() / "Conda" / "bin" / "conda"
        if candidate.is_file():
            conda = str(candidate)
    if not conda:
        print("Conda executable was not found; no environment was created or changed.")
        return 2
    try:
        listing = subprocess.run([conda, "env", "list", "--json"], text=True, capture_output=True,
                                 timeout=20, check=True)
        prefixes = json.loads(listing.stdout).get("envs", [])
    except Exception as exc:
        print(f"Could not inspect Conda environments ({type(exc).__name__}: {exc}); no changes made.")
        return 2
    by_name = {Path(prefix).name: Path(prefix) for prefix in prefixes}
    desired = ("phase1", "phase1_ltx", "phase2_3d")
    audit_code = (
        "import importlib.util as u, json, sys; "
        "mods=['torch','huggingface_hub','acestep','kokoro','whisper','qwen_asr','soundfile','numpy']; "
        "out={m:bool(u.find_spec(m)) for m in mods}; "
        "print(json.dumps({'python':sys.version.split()[0],'packages':out}, sort_keys=True))"
    )
    results = []
    for name in desired:
        prefix = by_name.get(name)
        if prefix is None:
            results.append({"environment": name, "present": False, "status": "not found"})
            continue
        python = prefix / "bin" / "python"
        if not python.is_file():
            results.append({"environment": name, "present": True, "status": "python executable not found", "prefix": str(prefix)})
            continue
        try:
            proc = subprocess.run([str(python), "-c", audit_code], text=True, capture_output=True,
                                  timeout=20, check=False)
            results.append({"environment": name, "present": True, "prefix": str(prefix),
                            "returncode": proc.returncode, "report": proc.stdout.strip(),
                            "stderr": proc.stderr[-2000:] if proc.returncode else ""})
        except Exception as exc:
            results.append({"environment": name, "present": True, "prefix": str(prefix),
                            "status": f"audit failed: {type(exc).__name__}: {exc}"})
    print(json.dumps({"conda": conda, "environments": results,
                      "no_environment_created_or_modified": True}, indent=2))
    return 0 if any(item.get("present") for item in results) else 2


def status() -> int:
    print("== StorageManager process(es) (read-only process-list inspection) ==")
    process_list = _manager_processes()
    print("\n".join(process_list) if process_list else "No StorageManager daemon process detected by this process namespace.")

    print("\n== Fresh StorageManager --status output (read-only) ==")
    manager = _storage_manager_status()
    print(manager.get("stdout", "") or "(no stdout)")
    if manager.get("stderr"):
        print("STDERR:\n" + manager["stderr"])
    if manager.get("error"):
        print("STATUS ERROR: " + manager["error"])

    logs = Path(SYSTEM_DIRS["logs"]).expanduser().resolve() / "storage_manager.log"
    print(f"\n== Latest storage_manager.log lines: {logs} ==")
    try:
        with logs.open("r", encoding="utf-8", errors="replace") as handle:
            tail = deque(handle, maxlen=60)
        print("".join(tail) if tail else "(log file is empty)")
    except OSError as exc:
        print(f"Log not readable: {type(exc).__name__}: {exc}")

    print("\n== OEC model folders / approximate bytes (no reserve-file inspection) ==")
    print(json.dumps(cache_status(), indent=2))
    return 0 if manager.get("returncode", 1) == 0 else 2


def _download_hf_cache(model: str, *, manager_directory_only: bool = False) -> dict[str, Any]:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is missing in this environment; no install was attempted") from exc
    spec = MODEL_SPECS[model]
    repo_id = spec["repo_id"]
    target = spec["target"] if spec["kind"] == "hf-local" else None
    before = _bytes(target) if target else _bytes(HUB_CACHE / ("models--" + repo_id.replace("/", "--")))
    required_gb = float(spec["required_gb"])
    require_fresh = not manager_directory_only
    ok, reason = storage_preflight("models", required_gb, require_fresh_quota=require_fresh, minimum_free_gb=MINIMUM_FREE_GB)
    print(json.dumps({"model": model, "preflight_ok": bool(ok), "reason": str(reason),
                      "estimated_required_gb": required_gb, "minimum_free_gb": MINIMUM_FREE_GB}, indent=2))
    if not ok:
        raise RuntimeError(f"StorageManager denied {model}: {reason}")
    with managed_storage_operation("models", required_gb=required_gb, require_fresh_quota=require_fresh,
                                   minimum_free_gb=MINIMUM_FREE_GB):
        if target:
            target_root = MODELS_ROOT.resolve()
            resolved = target.resolve()
            if target.is_symlink() or resolved == target_root or target_root not in resolved.parents:
                raise RuntimeError(f"Unsafe local checkpoint path: {target}")
            target.mkdir(parents=True, exist_ok=True)
            ignore = ["acestep-5Hz-lm-1.7B/**", "acestep-5Hz-lm-1.7B/*"] if model == "ace-step-main" else None
            path = snapshot_download(repo_id=repo_id, local_dir=str(target), ignore_patterns=ignore)
        else:
            HUB_CACHE.mkdir(parents=True, exist_ok=True)
            path = snapshot_download(repo_id=repo_id, cache_dir=str(HUB_CACHE))
        if not _is_complete(model):
            raise RuntimeError(f"Download finished but required weight validation failed for {model}; partial files were preserved for resume")
    after = _bytes(target) if target else _bytes(HUB_CACHE / ("models--" + repo_id.replace("/", "--")))
    return {"model": model, "status": "downloaded_and_weight_check_passed", "repo_id": repo_id,
            "path": str(target or path), "bytes_before": before, "bytes_after": after,
            "bytes_added_estimate": max(0, after - before)}


def _download_whisper(model: str = "whisper-turbo", *, manager_directory_only: bool = False) -> dict[str, Any]:
    url, required_gb = WHISPER_MODELS["turbo"]
    target_dir = MODELS_ROOT / "whisper" / "turbo"
    filename = Path(url).name
    target = target_dir / filename
    expected_sha256 = url.split("/")[-2]
    if target.is_file() and not target.is_symlink() and _sha256(target) == expected_sha256:
        return {"model": model, "status": "already_cached_and_sha256_verified", "path": str(target), "bytes": target.stat().st_size}

    require_fresh = not manager_directory_only
    ok, reason = storage_preflight("models", required_gb, require_fresh_quota=require_fresh, minimum_free_gb=MINIMUM_FREE_GB)
    print(json.dumps({"model": model, "preflight_ok": bool(ok), "reason": str(reason),
                      "estimated_required_gb": required_gb, "minimum_free_gb": MINIMUM_FREE_GB}, indent=2))
    if not ok:
        raise RuntimeError(f"StorageManager denied {model}: {reason}")
    root = MODELS_ROOT.resolve()
    resolved = target.resolve()
    if target.is_symlink() or resolved == root or root not in resolved.parents:
        raise RuntimeError(f"Unsafe Whisper target path: {target}")
    with managed_storage_operation("models", required_gb=required_gb, require_fresh_quota=require_fresh,
                                   minimum_free_gb=MINIMUM_FREE_GB):
        target_dir.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        digest = hashlib.sha256()
        try:
            with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as output:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    output.write(block)
                    digest.update(block)
                output.flush()
                os.fsync(output.fileno())
            if digest.hexdigest() != expected_sha256:
                raise RuntimeError("Whisper checkpoint SHA-256 mismatch; partial download removed")
            os.replace(partial, target)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
    return {"model": model, "status": "downloaded_and_sha256_verified", "path": str(target),
            "bytes": target.stat().st_size, "sha256_verified": True}


def download_model(model: str, *, manager_directory_only: bool = False) -> dict[str, Any]:
    if model not in MODEL_SPECS:
        raise ValueError(f"unknown model {model!r}")
    if _is_complete(model):
        if model == "whisper-turbo":
            target = MODELS_ROOT / "whisper" / "turbo" / Path(WHISPER_MODELS["turbo"][0]).name
        elif model in {"ace-step-main", "ace-step-lm-0.6b"}:
            target = MODEL_SPECS[model]["target"]
        else:
            target = model_targets()[model][0]
        return {"model": model, "status": "already_cached_and_weight_check_passed", "bytes": _bytes(target)}
    if model == "whisper-turbo":
        return _download_whisper(model, manager_directory_only=manager_directory_only)
    return _download_hf_cache(model, manager_directory_only=manager_directory_only)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="read StorageManager CLI status/log and model cache inventory")
    commands.add_parser("env-audit", help="inspect existing model environments without installing anything")
    plan = commands.add_parser("plan", help="show download list and per-model size budgets; no downloads")
    plan.add_argument("--preflight", action="store_true", help="run aggregate admission without downloading")
    plan.add_argument("--use-manager-directory-only", action="store_true",
                      help="allow directory-target admission if manager quota telemetry is unavailable")
    plan.add_argument("--reserve-floor-gb", type=float, default=40.0,
                      help="minimum existing models reserve to verify; model preparation never resizes the reserve")
    download = commands.add_parser("download", help="download model files one at a time through StorageManager")
    download.add_argument("--model", choices=(*MODEL_SPECS.keys(), "all"), required=True)
    download.add_argument("--use-manager-directory-only", action="store_true",
                          help="allow directory-target admission if manager quota telemetry is unavailable")
    download.add_argument("--reserve-floor-gb", type=float, default=40.0,
                          help="minimum existing models reserve to verify; model preparation never resizes the reserve")
    args = parser.parse_args()
    if args.command == "status":
        return status()
    if args.command == "env-audit":
        return environment_audit()
    if args.command == "plan":
        plan_rows = []
        for name in DOWNLOAD_ORDER:
            row = {"model": name, **MODEL_SPECS[name], "cached_and_complete": _is_complete(name)}
            row.pop("kind", None)
            plan_rows.append(row)
        missing = [name for name in DOWNLOAD_ORDER if not _is_complete(name)]
        estimate = sum(float(MODEL_SPECS[name]["required_gb"]) for name in missing)
        print(json.dumps({"models_root": str(MODELS_ROOT), "plan": plan_rows,
                          "missing_models": missing, "estimated_remaining_download_gb": estimate,
                          "minimum_free_gb": MINIMUM_FREE_GB}, indent=2, default=str))
        if args.preflight and estimate > 0:
            try:
                budget = None
                if args.use_manager_directory_only:
                    budget = _manager_directory_capacity(estimate, args.reserve_floor_gb, resize_reserve=False)
                    ok, reason = storage_preflight("models", estimate, require_fresh_quota=False,
                                                   minimum_free_gb=MINIMUM_FREE_GB)
                else:
                    ok, reason = storage_preflight("models", estimate, require_fresh_quota=True,
                                                   minimum_free_gb=MINIMUM_FREE_GB)
                print(json.dumps({"aggregate_preflight_ok": bool(ok), "estimated_required_gb": estimate,
                                  "minimum_free_gb": MINIMUM_FREE_GB, "manager_directory_budget": budget,
                                  "reason": str(reason), "no_download_performed": True}, indent=2), flush=True)
                return 0 if ok else 2
            except Exception as exc:
                print(json.dumps({"aggregate_preflight_ok": False, "estimated_required_gb": estimate,
                                  "manager_directory_budget_error": f"{type(exc).__name__}: {exc}",
                                  "no_download_performed": True}, indent=2), flush=True)
                return 2
        return 0
    selections = DOWNLOAD_ORDER if args.model == "all" else (args.model,)
    missing = [name for name in selections if not _is_complete(name)]
    if missing:
        aggregate_gb = sum(float(MODEL_SPECS[name]["required_gb"]) for name in missing)
        try:
            budget = None
            if args.use_manager_directory_only:
                budget = _manager_directory_capacity(aggregate_gb, args.reserve_floor_gb, resize_reserve=True)
                ok, reason = storage_preflight("models", aggregate_gb, require_fresh_quota=False,
                                               minimum_free_gb=MINIMUM_FREE_GB)
            else:
                ok, reason = storage_preflight("models", aggregate_gb, require_fresh_quota=True,
                                               minimum_free_gb=MINIMUM_FREE_GB)
            print(json.dumps({"aggregate_preflight_ok": bool(ok), "models_to_fetch": missing,
                              "estimated_required_gb": aggregate_gb, "minimum_free_gb": MINIMUM_FREE_GB,
                              "manager_directory_budget": budget, "reason": str(reason)}, indent=2), flush=True)
            if not ok:
                print("Aggregate StorageManager preflight denied the batch; no files were downloaded.", file=sys.stderr)
                return 2
        except Exception as exc:
            print(json.dumps({"aggregate_preflight_ok": False, "models_to_fetch": missing,
                              "estimated_required_gb": aggregate_gb,
                              "manager_directory_budget_error": f"{type(exc).__name__}: {exc}",
                              "no_download_performed": True}, indent=2), file=sys.stderr, flush=True)
            return 2
    result_rows = []
    for name in selections:
        print(f"\n=== {name}: {MODEL_SPECS[name]['summary']} ===", flush=True)
        try:
            row = download_model(name, manager_directory_only=args.use_manager_directory_only)
        except Exception as exc:
            print(json.dumps({"model": name, "status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}, indent=2), file=sys.stderr)
            print("Stopped without starting any additional downloads. Rerun the selected model after resolving this error.", file=sys.stderr)
            return 2
        result_rows.append(row)
        print(json.dumps(row, indent=2), flush=True)
    print("\nDOWNLOAD SUMMARY\n" + json.dumps(result_rows, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
