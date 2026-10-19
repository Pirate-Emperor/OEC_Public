#!/usr/bin/env python3
"""Cache-aware MusicGen text-to-music inference for research use.

Important licensing boundary: AudioCraft model weights are marked CC-BY-NC 4.0.
Treat this backend as non-commercial research only unless rights for the exact
weights and resulting use have been reviewed. The script does not install packages.
"""
from __future__ import annotations
import argparse, hashlib, importlib.metadata, json, os, time, uuid
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core_config import SYSTEM_DIRS  # noqa: E402

MODEL_ID = "facebook/musicgen-medium"
WEIGHT_LICENSE = "CC-BY-NC-4.0"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("check", "generate"), default="generate")
    p.add_argument("--gpu", type=int, default=None, help="Physical A100 index.")
    p.add_argument("--offline", action="store_true", help="Require cached weights.")
    p.add_argument("--allow-download", action="store_true", help="Permit model download after StorageManager admission.")
    p.add_argument("--scratch-output", action="store_true", help="Write only under /tmp.")
    p.add_argument("--output", type=Path)
    p.add_argument("--prompt", default="A calm instrumental soundtrack with warm piano, soft strings and a steady gentle pulse")
    p.add_argument("--duration", type=int, default=3)
    p.add_argument("--seed", type=int, default=42)
    return p


def _validate(prompt: str, duration: int) -> None:
    if not prompt or not prompt.strip() or len(prompt) > 1200:
        raise ValueError("prompt must contain 1–1200 characters")
    if not 1 <= duration <= 10:
        raise ValueError("duration must be between 1 and 10 seconds")


def _versions() -> dict[str, str]:
    required = {"audiocraft": "1.3.0", "torch": "2.1.0", "torchaudio": "2.1.0", "numpy": "1.26.4"}
    actual = {}
    bad = {}
    for package, prefix in required.items():
        try:
            value = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            value = "MISSING"
        actual[package] = value
        print(f"MUSICGEN_PACKAGE_{package}={value} required_prefix={prefix}", flush=True)
        if not value.startswith(prefix):
            bad[package] = {"actual": value, "required_prefix": prefix}
    if bad:
        raise RuntimeError("AudioCraft shared environment mismatch; no packages were changed: " + json.dumps(bad))
    return actual


def _gpu(requested: int | None) -> dict[str, str]:
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
        path = snapshot_download(repo_id=MODEL_ID, cache_dir=str(models_root), local_files_only=True)
        print(f"MUSICGEN_CACHE=HIT snapshot={path}", flush=True)
        return Path(path)
    except LocalEntryNotFoundError:
        if not allow_download:
            raise RuntimeError(f"{MODEL_ID} is not completely cached; offline mode forbids a download")
    from storage_policy import BYTES_PER_GB, estimate_hf_repo_bytes
    from storage_manager import managed_storage_operation, storage_preflight
    required_gb = estimate_hf_repo_bytes(MODEL_ID) / BYTES_PER_GB
    required_gb += max(0.0, float(os.environ.get("AIEROS_MUSICGEN_DOWNLOAD_SAFETY_GB", "2.0")))
    minimum_free_gb = max(2.0, float(os.environ.get("AIEROS_MODEL_MIN_FREE_GB", "2.0")))
    ok, reason = storage_preflight("models", required_gb=required_gb, require_fresh_quota=True,
                                   minimum_free_gb=minimum_free_gb)
    print(f"MUSICGEN_MODEL_ADMISSION={ok} required_gb={required_gb:.3f} reason={reason}", flush=True)
    if not ok:
        raise RuntimeError(f"StorageManager denied MusicGen download: {reason}")
    with managed_storage_operation("models", required_gb=required_gb, require_fresh_quota=True,
                                   minimum_free_gb=minimum_free_gb):
        ok, reason = storage_preflight("models", required_gb=required_gb, require_fresh_quota=True,
                                       minimum_free_gb=minimum_free_gb)
        if not ok:
            raise RuntimeError(f"StorageManager denied MusicGen download inside managed operation: {reason}")
        path = snapshot_download(repo_id=MODEL_ID, cache_dir=str(models_root), local_files_only=False)
    print(f"MUSICGEN_DOWNLOAD=PASS snapshot={path}", flush=True)
    return Path(path)


def _under(path: Path, root: Path) -> bool:
    path, root = path.expanduser().resolve(), root.expanduser().resolve()
    return path != root and root in path.parents


def _output_path(output: Path | None, scratch: bool, seed: int) -> Path:
    outputs_root = Path(SYSTEM_DIRS["outputs"]).expanduser().resolve()
    tag = f"{int(time.time())}-{uuid.uuid4().hex[:8]}-{seed}"
    if output is None:
        output = (Path("/tmp") / f"oec-musicgen-{tag}.wav") if scratch else outputs_root / "audio" / f"musicgen-{tag}.wav"
    path = output.expanduser().resolve()
    if scratch and not _under(path, Path("/tmp")):
        raise ValueError("--scratch-output requires a path below /tmp")
    if not scratch and not _under(path, outputs_root):
        raise ValueError("managed MusicGen output must be below the configured OEC outputs root")
    if path.exists() or path.with_suffix(".info.json").exists():
        raise FileExistsError(f"refusing to overwrite existing MusicGen output: {path}")
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
        path.parent.mkdir(parents=True, exist_ok=True)
        # AudioCraft waveform is [channels, frames]; SoundFile wants [frames, channels].
        sf.write(str(path), audio.transpose(0, 1).contiguous().numpy(), int(sample_rate), subtype="PCM_16")
        info = sf.info(str(path))
        if info.frames <= 0 or info.samplerate <= 0 or info.channels <= 0:
            raise RuntimeError("MusicGen output WAV has invalid frame/rate/channel metadata")
        metadata.update({"artifact_path": str(path), "artifact_bytes": path.stat().st_size,
                         "artifact_sha256": _sha256(path), "sample_rate": info.samplerate,
                         "channels": info.channels, "frames": info.frames,
                         "duration_seconds": round(info.frames / info.samplerate, 4)})
        if abs(metadata["duration_seconds"] - metadata["requested_duration_seconds"]) > 0.35:
            raise RuntimeError(f"MusicGen duration mismatch: {metadata['duration_seconds']} seconds")
        with path.with_suffix(".info.json").open("x", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, sort_keys=True)
        return metadata
    if scratch:
        return write()
    from storage_manager import managed_storage_operation, storage_preflight
    with managed_storage_operation("outputs", required_gb=0.03, require_fresh_quota=True, minimum_free_gb=0.02):
        ok, reason = storage_preflight("outputs", required_gb=0.03, require_fresh_quota=True, minimum_free_gb=0.02)
        if not ok:
            raise RuntimeError(f"StorageManager denied MusicGen output inside managed operation: {reason}")
        return write()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.allow_download and args.offline:
        parser.error("--allow-download and --offline cannot be used together")
    try:
        _validate(args.prompt, args.duration)
    except ValueError as exc:
        parser.error(str(exc))
    gpu = _gpu(args.gpu)
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu["index"]
    os.environ["AUDIOCRAFT_CACHE_DIR"] = str(Path(SYSTEM_DIRS["models"]).expanduser().resolve())
    versions = _versions()
    snapshot = _snapshot(args.allow_download)
    if args.mode == "check":
        print("MUSICGEN_CACHE_CHECK=PASS revision=" + snapshot.name)
        return 0
    import torch
    from audiocraft.models import MusicGen
    torch.cuda.set_device(0)
    if not torch.cuda.is_available() or "A100" not in torch.cuda.get_device_name(0).upper():
        raise RuntimeError("MusicGen requires the selected A100 CUDA device")
    model = MusicGen.get_pretrained(MODEL_ID, device="cuda")
    model.set_generation_params(duration=int(args.duration))
    torch.manual_seed(int(args.seed))
    torch.cuda.manual_seed_all(int(args.seed))
    output = _output_path(args.output, args.scratch_output, args.seed)
    if not args.scratch_output:
        from storage_manager import storage_preflight
        ok, reason = storage_preflight("outputs", required_gb=0.03, require_fresh_quota=True, minimum_free_gb=0.02)
        if not ok:
            raise RuntimeError(f"StorageManager denied MusicGen output before inference: {reason}")
    torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()
    with torch.inference_mode():
        wav = model.generate([args.prompt.strip()])
    elapsed = time.monotonic() - started
    metadata = {"provider":"musicgen","model":MODEL_ID,"model_revision":snapshot.name,
                "license":WEIGHT_LICENSE,"use_boundary":"research/non-commercial only until license review",
                "physical_gpu":int(gpu["index"]),"prompt":args.prompt.strip(),"seed":int(args.seed),
                "requested_duration_seconds":int(args.duration),"sample_rate":int(model.sample_rate),
                "generation_seconds":round(elapsed,3),"packages":versions}
    metadata["peak_allocated_gib"] = round(torch.cuda.max_memory_allocated() / 1024**3, 3)
    metadata["peak_reserved_gib"] = round(torch.cuda.max_memory_reserved() / 1024**3, 3)
    metadata = _write_audio(wav[0].detach().float().cpu(), model.sample_rate, output, args.scratch_output, metadata)
    torch.cuda.empty_cache()
    print("MUSICGEN_ACCEPTANCE=" + json.dumps(metadata, sort_keys=True), flush=True)
    print("MUSICGEN_GENERATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
