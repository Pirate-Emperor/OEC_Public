#!/usr/bin/env python3
"""Cache-aware AudioGen text-to-sound inference CLI for OEC.

AudioCraft code is MIT licensed, but the AudioGen weights are CC-BY-NC 4.0.
This CLI records that boundary in every output metadata file. It does not install
packages; model downloads are opt-in and require current OEC StorageManager admission.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import uuid
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core_config import SYSTEM_DIRS  # noqa: E402

MODEL_ID = "facebook/audiogen-medium"
WEIGHT_LICENSE = "CC-BY-NC-4.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("check", "generate"), default="generate")
    parser.add_argument("--gpu", type=int, default=None, help="Physical A100 index.")
    parser.add_argument("--offline", action="store_true", help="Require cached model weights.")
    parser.add_argument("--allow-download", action="store_true", help="Allow cache fill after fresh StorageManager admission.")
    parser.add_argument("--scratch-output", action="store_true", help="Write output only below /tmp.")
    parser.add_argument("--output", type=Path, help="Output WAV path.")
    parser.add_argument("--prompt", default="A soft rain shower on a window with occasional distant thunder")
    parser.add_argument("--duration", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def _validate(prompt: str, duration: int) -> None:
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 1200:
        raise ValueError("prompt must contain 1–1200 characters")
    if isinstance(duration, bool) or not isinstance(duration, int) or not 1 <= duration <= 10:
        raise ValueError("duration must be an integer between 1 and 10 seconds")


def _check_versions() -> dict[str, str]:
    expected = {"audiocraft": "1.3.0", "torch": "2.1.0", "torchaudio": "2.1.0", "numpy": "1.26.4"}
    actual: dict[str, str] = {}
    mismatches: dict[str, dict[str, str]] = {}
    for package, version in expected.items():
        try:
            installed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            installed = "MISSING"
        actual[package] = installed
        print(f"AUDIOGEN_PACKAGE_{package}={installed} required_prefix={version}", flush=True)
        if not installed.startswith(version):
            mismatches[package] = {"actual": installed, "required_prefix": version}
    if mismatches:
        raise RuntimeError("AudioCraft runtime mismatch; no packages were changed: " + json.dumps(mismatches, sort_keys=True))
    return actual


def _select_gpu(requested: int | None) -> dict[str, str]:
    from pipeline_flux_image import select_idle_a100_gpu
    return select_idle_a100_gpu(requested)


def _snapshot(allow_download: bool) -> Path:
    models_root = Path(SYSTEM_DIRS["models"]).expanduser().resolve()
    os.environ["AUDIOCRAFT_CACHE_DIR"] = str(models_root)
    from huggingface_hub import snapshot_download
    try:
        from huggingface_hub.errors import LocalEntryNotFoundError
    except ImportError:
        from huggingface_hub.utils import LocalEntryNotFoundError
    try:
        snapshot = snapshot_download(repo_id=MODEL_ID, cache_dir=str(models_root), local_files_only=True)
        print(f"AUDIOGEN_CACHE=HIT snapshot={snapshot}", flush=True)
        return Path(snapshot)
    except LocalEntryNotFoundError:
        if not allow_download:
            raise RuntimeError(f"{MODEL_ID} is not fully cached; offline mode forbids downloads")

    from storage_policy import BYTES_PER_GB, estimate_hf_repo_bytes
    from storage_manager import managed_storage_operation, storage_preflight
    required_gb = estimate_hf_repo_bytes(MODEL_ID) / BYTES_PER_GB
    required_gb += max(0.0, float(os.environ.get("AIEROS_AUDIOGEN_DOWNLOAD_SAFETY_GB", "2.0")))
    minimum_free_gb = max(2.0, float(os.environ.get("AIEROS_MODEL_MIN_FREE_GB", "2.0")))
    ok, reason = storage_preflight("models", required_gb=required_gb, require_fresh_quota=True,
                                   minimum_free_gb=minimum_free_gb)
    print(f"AUDIOGEN_MODEL_ADMISSION={ok} required_gb={required_gb:.3f} reason={reason}", flush=True)
    if not ok:
        raise RuntimeError(f"StorageManager denied AudioGen model download: {reason}")
    with managed_storage_operation("models", required_gb=required_gb, require_fresh_quota=True,
                                  minimum_free_gb=minimum_free_gb):
        ok, reason = storage_preflight("models", required_gb=required_gb, require_fresh_quota=True,
                                       minimum_free_gb=minimum_free_gb)
        if not ok:
            raise RuntimeError(f"StorageManager denied AudioGen download inside managed operation: {reason}")
        snapshot = snapshot_download(repo_id=MODEL_ID, cache_dir=str(models_root), local_files_only=False)
    print(f"AUDIOGEN_DOWNLOAD=PASS snapshot={snapshot}", flush=True)
    return Path(snapshot)


def _is_below(path: Path, root: Path) -> bool:
    path, root = path.expanduser().resolve(), root.expanduser().resolve()
    return path != root and root in path.parents


def _output_path(output: Path | None, scratch: bool, seed: int) -> Path:
    outputs_root = Path(SYSTEM_DIRS["outputs"]).expanduser().resolve()
    tag = f"{int(time.time())}-{uuid.uuid4().hex[:8]}-{seed}"
    if output is None:
        output = (Path("/tmp") / f"oec-audiogen-{tag}.wav") if scratch else outputs_root / "audio" / f"audiogen-{tag}.wav"
    path = output.expanduser().resolve()
    if scratch and not _is_below(path, Path("/tmp")):
        raise ValueError("--scratch-output requires an output below /tmp")
    if not scratch and not _is_below(path, outputs_root):
        raise ValueError("managed AudioGen output must be below the configured OEC outputs root")
    if path.exists() or path.with_suffix(".info.json").exists():
        raise FileExistsError(f"refusing to overwrite existing AudioGen output: {path}")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_audio(audio: Any, sample_rate: int, path: Path, scratch: bool, metadata: dict[str, Any]) -> dict[str, Any]:
    import soundfile as sf

    def write() -> dict[str, Any]:
        if path.exists() or path.with_suffix(".info.json").exists():
            raise FileExistsError(f"refusing to overwrite existing AudioGen output: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        # AudioCraft waveform is [channels, frames]; SoundFile expects [frames, channels].
        with sf.SoundFile(str(path), mode="x", samplerate=int(sample_rate), channels=int(audio.shape[0]), subtype="PCM_16", format="WAV") as writer:
            writer.write(audio.transpose(0, 1).contiguous().numpy())
        info = sf.info(str(path))
        if info.frames <= 0 or info.samplerate <= 0 or info.channels <= 0:
            raise RuntimeError("AudioGen output WAV has invalid frame/rate/channel metadata")
        metadata.update({
            "artifact_path": str(path), "artifact_bytes": path.stat().st_size, "artifact_sha256": _sha256(path),
            "sample_rate": info.samplerate, "channels": info.channels, "frames": info.frames,
            "duration_seconds": round(info.frames / info.samplerate, 4),
        })
        if abs(metadata["duration_seconds"] - metadata["requested_duration_seconds"]) > 0.35:
            raise RuntimeError(f"AudioGen output duration mismatch: {metadata['duration_seconds']} seconds")
        with path.with_suffix(".info.json").open("x", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, sort_keys=True)
        return metadata

    if scratch:
        return write()
    from storage_manager import managed_storage_operation, storage_preflight
    with managed_storage_operation("outputs", required_gb=0.03, require_fresh_quota=True, minimum_free_gb=0.02):
        ok, reason = storage_preflight("outputs", required_gb=0.03, require_fresh_quota=True, minimum_free_gb=0.02)
        if not ok:
            raise RuntimeError(f"StorageManager denied AudioGen output inside managed operation: {reason}")
        return write()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.allow_download and args.offline:
        parser.error("--allow-download and --offline cannot be combined")
    try:
        _validate(args.prompt, args.duration)
    except ValueError as exc:
        parser.error(str(exc))

    gpu = _select_gpu(args.gpu)
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu["index"]
    os.environ["AUDIOCRAFT_CACHE_DIR"] = str(Path(SYSTEM_DIRS["models"]).expanduser().resolve())
    versions = _check_versions()
    snapshot = _snapshot(args.allow_download)
    if args.mode == "check":
        print("AUDIOGEN_CACHE_CHECK=PASS revision=" + snapshot.name)
        return 0

    import torch
    from audiocraft.models import AudioGen
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable after A100 selection")
    torch.cuda.set_device(0)
    if "A100" not in torch.cuda.get_device_name(0).upper():
        raise RuntimeError("visible CUDA device is not an A100")
    model = AudioGen.get_pretrained(MODEL_ID, device="cuda")
    model.set_generation_params(duration=int(args.duration))
    torch.manual_seed(int(args.seed))
    torch.cuda.manual_seed_all(int(args.seed))
    output = _output_path(args.output, args.scratch_output, args.seed)
    if not args.scratch_output:
        from storage_manager import storage_preflight
        ok, reason = storage_preflight("outputs", required_gb=0.03, require_fresh_quota=True, minimum_free_gb=0.02)
        if not ok:
            raise RuntimeError(f"StorageManager denied AudioGen output before inference: {reason}")
    torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()
    with torch.inference_mode():
        waveform = model.generate([args.prompt.strip()])
    elapsed = time.monotonic() - started
    metadata = {
        "provider": "audiogen", "model": MODEL_ID, "model_revision": snapshot.name,
        "license": WEIGHT_LICENSE, "use_boundary": "research/non-commercial only until license review",
        "physical_gpu": int(gpu["index"]), "prompt": args.prompt.strip(), "seed": int(args.seed),
        "requested_duration_seconds": int(args.duration), "sample_rate": int(model.sample_rate),
        "generation_seconds": round(elapsed, 3), "packages": versions,
        "peak_allocated_gib": round(torch.cuda.max_memory_allocated() / 1024**3, 3),
        "peak_reserved_gib": round(torch.cuda.max_memory_reserved() / 1024**3, 3),
    }
    metadata = _write_audio(waveform[0].detach().float().cpu(), model.sample_rate, output, args.scratch_output, metadata)
    torch.cuda.empty_cache()
    print("AUDIOGEN_ACCEPTANCE=" + json.dumps(metadata, sort_keys=True), flush=True)
    print("AUDIOGEN_GENERATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
