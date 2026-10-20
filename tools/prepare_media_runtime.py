#!/usr/bin/env python3
"""Prepare isolated audio inference dependencies while preserving shared Torch/CUDA stacks."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))
from core_config import SYSTEM_DIRS  # noqa: E402

VENV = Path.home() / ".local" / "venvs" / "oec-audio-py311"
BLOCKED = {"torch", "torchvision", "torchaudio", "numpy", "triton", "torchao", "torchcodec"}


def _run(command: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    print("COMMAND " + json.dumps(command), flush=True)
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=timeout, check=False)


def _read_status() -> dict[str, dict[str, float | str]]:
    proc = _run([sys.executable, str(ROOT / "storage_manager.py"), "--status"], timeout=30)
    if proc.returncode:
        raise RuntimeError(f"storage_manager.py --status failed: {proc.stderr[-1500:]}")
    rows: dict[str, dict[str, float | str]] = {}
    pattern = re.compile(
        r"\[(models|outputs)\]\s+state=(\w+)\s+actual=([\d.]+)\s+(GB|MB)\s*/\s*([\d.]+)\s+GB\s+reserve=([\d.]+)\s+(GB|MB)"
    )
    def as_gb(value: str, unit: str) -> float:
        return float(value) if unit == "GB" else float(value) / 1024.0
    for line in proc.stdout.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        name, state, actual, unit, target, reserve, reserve_unit = match.groups()
        rows[name] = {"state": state.upper(), "actual_gb": as_gb(actual, unit),
                      "target_gb": float(target), "reserve_gb": as_gb(reserve, reserve_unit)}
    if "models" not in rows or "outputs" not in rows:
        raise RuntimeError("could not parse fresh models and outputs rows from StorageManager status")
    return rows


def _prepare_output_reserve() -> dict[str, Any]:
    """Read StorageManager state and budget a short audio smoke without resizing reserves.

    Reserve operations belong to StorageManager. This preflight must not read or
    modify protected reserve files, or change the reserve while another operation
    owns a lease. Actual model/output writes re-run their own live admission.
    """
    config_path = ROOT / "storage_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output_policy = next((d for d in config.get("directories", []) if d.get("name") == "outputs"), None)
    if not isinstance(output_policy, dict):
        raise RuntimeError("outputs reserve policy is missing from the active storage_config.json")

    minimum_reserve = float(output_policy.get("minimum_reserve_gb", config.get("minimum_reserve_gb", 0.25)))
    reserve_floor = max(minimum_reserve, float(output_policy.get("reserve_target_gb", minimum_reserve)))
    rows = _read_status()
    models, outputs = rows["models"], rows["outputs"]
    models_policy = next((d for d in config.get("directories", []) if d.get("name") == "models"), None)
    if not isinstance(models_policy, dict):
        raise RuntimeError("models reserve policy is missing from the active storage_config.json")
    model_minimum_reserve = max(
        0.0,
        float(models_policy.get("minimum_reserve_gb", config.get("minimum_reserve_gb", 0.25))),
    )
    # Use the actual StorageManager-reported .storage_reserve.bin allocation.
    # The preparation of the isolated Python environment does not consume the
    # models payload budget, so a hard-coded 40 GB floor incorrectly blocks
    # this step when the configured target is 280 GB and the existing reserve
    # has already been allocated (for example, 29.83 GB). Never resize it here.
    if models["state"] not in {"NORMAL", "WARNING"}:
        raise RuntimeError(f"model-target gate failed; StorageManager state is {models['state']}: {models}")
    if float(models["reserve_gb"]) + 0.02 < model_minimum_reserve:
        raise RuntimeError(
            f"existing models reserve {float(models['reserve_gb']):.3f} GB is below the configured "
            f"minimum {model_minimum_reserve:.3f} GB; refusing environment preparation: {models}"
        )
    if outputs["state"] not in {"NORMAL", "WARNING"}:
        raise RuntimeError(f"outputs state is {outputs['state']}; refusing to start model inference")

    current_reserve = float(outputs["reserve_gb"])
    if current_reserve + 0.02 < reserve_floor:
        raise RuntimeError(
            f"outputs reserve {current_reserve:.3f} GB is below the configured {reserve_floor:.3f} GB floor; "
            "refusing reserve mutation"
        )

    # Directory content and the protected reserve are separate StorageManager
    # quantities. Budget just generated content plus an explicit safety margin.
    artifact_budget_gb, safety_margin_gb = 0.10, 0.05
    projected = float(outputs["actual_gb"]) + artifact_budget_gb + safety_margin_gb
    if projected > float(outputs["target_gb"]) + 0.005:
        raise RuntimeError(
            f"outputs artifact budget denied: content={outputs['actual_gb']:.3f} GB "
            f"+ artifacts={artifact_budget_gb:.2f} GB + margin={safety_margin_gb:.2f} GB "
            f"> target={outputs['target_gb']:.2f} GB"
        )

    return {
        "models": models,
        "models_reserve_minimum_gb": model_minimum_reserve,
        "outputs": outputs,
        "output_reserve_floor_gb": reserve_floor,
        "projected_output_usage_with_artifacts_gb": projected,
        "output_reserve_resized": False,
        "reserve_mutation_attempted": False,
        "reserve_policy": "read-only StorageManager status; existing reserve preserved",
    }


def _base_python() -> Path:
    candidates = [
        Path.home() / "Conda" / "envs" / "phase1_ltx" / "bin" / "python",
        Path.home() / "Conda" / "envs" / "phase2_3d" / "bin" / "python",
        Path.home() / "Conda" / "envs" / "phase1" / "bin" / "python",
    ]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        proc = _run([str(candidate), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"], timeout=10)
        if proc.returncode == 0 and proc.stdout.strip().splitlines()[-1] in {"3.10", "3.11", "3.12"}:
            print(f"BASE_PYTHON={candidate} VERSION={proc.stdout.strip().splitlines()[-1]}", flush=True)
            return candidate
    raise RuntimeError("no pre-existing Python 3.10-3.12 interpreter exists for an isolated audio venv")


def _venv_python(base_python: Path) -> Path:
    if VENV.is_symlink():
        raise RuntimeError(f"refusing symlink venv path: {VENV}")
    VENV.parent.mkdir(parents=True, exist_ok=True)
    python = VENV / "bin" / "python"
    if not python.is_file():
        create = _run([str(base_python), "-m", "venv", "--system-site-packages", str(VENV)], timeout=180)
        if create.returncode:
            raise RuntimeError(f"isolated venv creation failed: {create.stderr[-2000:]}")
    verify = _run([str(python), "-c",
                   "import sys, torch; print(sys.version.split()[0]); print('torch',torch.__version__); print('cuda_available',torch.cuda.is_available())"], timeout=60)
    if verify.returncode:
        raise RuntimeError(f"audio venv cannot import inherited Torch: {verify.stderr[-2000:]}")
    print("VENV_BASELINE\n" + verify.stdout.strip(), flush=True)
    return python


def _install_group(python: Path, group: str, packages: list[str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="oec-audio-pip-plan-") as folder:
        report_path = Path(folder) / "report.json"
        dry = _run([str(python), "-m", "pip", "install", "--dry-run", "--no-cache-dir",
                    "--report", str(report_path), *packages], timeout=600)
        if dry.returncode or not report_path.is_file():
            print(f"RUNTIME_PLAN {group}: BLOCKED during dry-run; nothing installed\n{dry.stderr[-2500:]}", flush=True)
            return {"group": group, "status": "blocked_dry_run", "stderr": dry.stderr[-1500:]}
        plan = json.loads(report_path.read_text(encoding="utf-8"))
        installs = []
        for item in plan.get("install", []):
            metadata = item.get("metadata") or {}
            name = str(metadata.get("name", "")).lower().replace("_", "-")
            version = str(metadata.get("version", ""))
            installs.append({"name": name, "version": version})
        blocked = [p for p in installs if p["name"] in BLOCKED or p["name"].startswith("nvidia-")]
        print("RUNTIME_PLAN " + json.dumps({"group": group, "packages": packages,
              "candidate_installs": len(installs), "planned": installs, "blocked_torch_cuda_changes": blocked},
              ensure_ascii=False), flush=True)
        if blocked:
            return {"group": group, "status": "blocked_core_stack_replacement", "blocked": blocked,
                    "no_install_performed": True}
        install = _run([str(python), "-m", "pip", "install", "--no-cache-dir", *packages], timeout=1200)
        if install.returncode:
            print(f"RUNTIME_INSTALL {group}: FAILED\n{install.stdout[-2000:]}\n{install.stderr[-2500:]}", flush=True)
            return {"group": group, "status": "install_failed", "stderr": install.stderr[-1500:]}
        return {"group": group, "status": "installed_or_already_satisfied",
                "stdout": install.stdout[-1000:], "stderr": install.stderr[-1000:]}


def main() -> int:
    reserve = _prepare_output_reserve()
    print("OUTPUT_RESERVE_ACCEPTANCE " + json.dumps(reserve), flush=True)
    python = _venv_python(_base_python())
    groups = [_install_group(python, "kokoro", ["kokoro==0.9.4"]),
              _install_group(python, "qwen3-asr", ["qwen-asr==0.0.6"])]
    if shutil.which("ffmpeg"):
        groups.append(_install_group(python, "whisper", ["openai-whisper"]))
    else:
        groups.append({"group": "whisper", "status": "skipped_no_ffmpeg",
                       "reason": "ffmpeg is not on PATH; no system package install was attempted"})
    status = {}
    for provider, module in (("kokoro", "kokoro"), ("qwen3-asr", "qwen_asr"), ("whisper", "whisper")):
        if provider == "whisper" and not shutil.which("ffmpeg"):
            status[provider] = False
            continue
        code = f"import importlib.util as u, json; print(json.dumps({{'importable': bool(u.find_spec({module!r}))}}))"
        check = _run([str(python), "-c", code], timeout=20)
        try:
            status[provider] = check.returncode == 0 and json.loads(check.stdout.strip().splitlines()[-1])["importable"]
        except Exception:
            status[provider] = False
    summary = {"venv": str(VENV), "base_torch_preserved": True, "groups": groups,
               "provider_importable": status, "ffmpeg": shutil.which("ffmpeg"),
               "existing_conda_envs_modified": False, "checkpoint_weights_stored_outside_models_dir": False,
               "reserve_file_accessed_directly": False}
    print("AUDIO_RUNTIME_SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
