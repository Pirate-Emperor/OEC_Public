#!/usr/bin/env python3
"""Loopback-only OEC service for music generation, TTS and speech recognition.

One provider per process/Conda environment. Cache-only by default; model files
must stay under core_config.SYSTEM_DIRS['models'] (AIEROS_MODELS_DIR).
"""
from __future__ import annotations
import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
_ace_root_value = os.environ.get("AIEROS_ACE_STEP_SOURCE_ROOT", "").strip()
ACE_STEP_SOURCE_ROOT = Path(_ace_root_value).expanduser().resolve() if _ace_root_value else None
if ACE_STEP_SOURCE_ROOT is not None and (ACE_STEP_SOURCE_ROOT / "acestep").is_dir():
    if str(ACE_STEP_SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(ACE_STEP_SOURCE_ROOT))
from core_config import SYSTEM_DIRS
from common import MediaProvider, ModelNotReady, RequestError, managed_write, safe_child, serve, storage_check
from model_cache import MODELS_ROOT, RuntimeLock, hf_cache_has_weights, model_targets

LOG = logging.getLogger("oec.media_service.audio")
VOICES = {"af_heart", "af_bella", "af_sarah", "af_nicole", "af_sky", "am_adam", "am_michael",
          "bf_emma", "bf_isabella", "bm_george", "bm_lewis"}
LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "zh": "Chinese", "ja": "Japanese", "ko": "Korean",
                  "fr": "French", "de": "German", "es": "Spanish", "pt": "Portuguese", "it": "Italian",
                  "ru": "Russian", "ar": "Arabic", "th": "Thai", "vi": "Vietnamese", "id": "Indonesian",
                  "ms": "Malay", "nl": "Dutch", "sv": "Swedish", "da": "Danish", "fi": "Finnish",
                  "pl": "Polish", "tr": "Turkish", "fa": "Persian", "el": "Greek"}

def _has_model_weights(folder: Path) -> bool:
    """Return true only when a model-owned folder contains a nonempty weight file."""
    if not folder.is_dir() or folder.is_symlink():
        return False
    for path in folder.rglob("*"):
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in {".safetensors", ".bin", ".pt", ".pth"}:
            continue
        try:
            if path.stat().st_size > 0:
                return True
        except OSError:
            continue
    return False


def _network_policy(allow_download: bool) -> None:
    offline = "0" if allow_download else "1"
    os.environ["HF_HUB_OFFLINE"] = offline
    os.environ["TRANSFORMERS_OFFLINE"] = offline
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["ACESTEP_CHECKPOINTS_DIR"] = str(MODELS_ROOT / "ace-step-1.5")
    os.environ["TORCH_HOME"] = str(MODELS_ROOT / "torch_hub")
    if ACE_STEP_SOURCE_ROOT is not None:
        os.environ["ACESTEP_PROJECT_ROOT"] = str(ACE_STEP_SOURCE_ROOT)
        os.environ["AIEROS_ACE_STEP_SOURCE_ROOT"] = str(ACE_STEP_SOURCE_ROOT)
    os.environ.setdefault("ACESTEP_LM_BACKEND", "pt")


class AudioProvider(MediaProvider):
    max_prompt_chars = 2500

    def __init__(self, model: str, allow_download: bool = False, whisper_size: str = "turbo",
                 ace_config: str = "acestep-v15-turbo", ace_lm: str = "acestep-5Hz-lm-0.6B",
                 kokoro_voice: str = "af_heart", require_cuda: bool = True):
        super().__init__(allow_download=allow_download)
        if model not in {"ace-step", "kokoro", "whisper", "qwen3-asr"}:
            raise ValueError("unsupported audio model")
        self.kind, self.whisper_size = model, whisper_size
        self.name = f"whisper-{whisper_size}" if model == "whisper" else "qwen3-asr-0.6b" if model == "qwen3-asr" else model
        self.model_name = {"ace-step": "ACE-Step 1.5", "kokoro": "Kokoro-82M",
                           "whisper": f"OpenAI Whisper {whisper_size}", "qwen3-asr": "Qwen3-ASR-0.6B"}[model]
        self.model_revision = {"ace-step": "ACE-Step-1.5", "kokoro": "Kokoro-82M",
                               "whisper": whisper_size, "qwen3-asr": "Qwen3-ASR-0.6B"}[model]
        self.artifact_content_type, self.artifact_extension = {
            "ace-step": ("audio/flac", "flac"), "kokoro": ("audio/wav", "wav"),
            "whisper": ("text/plain; charset=utf-8", "txt"),
            "qwen3-asr": ("text/plain; charset=utf-8", "txt")}[model]
        self.ace_config, self.ace_lm, self.kokoro_voice = ace_config, ace_lm, kokoro_voice
        self.require_cuda = require_cuda
        self.runtime_lock = RuntimeLock(self.name)
        self.runtime: Any = None
        self.handlers: dict[str, Any] = {}

    def validate_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        params = payload.get("parameters", {})
        if not isinstance(params, dict): raise RequestError("parameters must be a JSON object")
        prompt = payload.get("prompt", "")
        if self.kind == "ace-step":
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 512:
                raise RequestError("prompt must be 1-512 characters for ACE-Step")
            allowed = {"duration_seconds", "seed", "steps", "lyrics", "instrumental", "bpm", "language"}
            if set(params) - allowed: raise RequestError("unsupported ACE-Step parameters")
            duration, seed, steps = params.get("duration_seconds", 30), params.get("seed", -1), params.get("steps", 8)
            lyrics, bpm, language = params.get("lyrics", ""), params.get("bpm"), params.get("language", "unknown")
            instrumental = params.get("instrumental", not bool(lyrics))
            if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not 10 <= float(duration) <= 180:
                raise RequestError("duration_seconds must be between 10 and 180")
            if isinstance(seed, bool) or not isinstance(seed, int) or not -1 <= seed <= 2**31 - 1:
                raise RequestError("seed must be -1 or a non-negative 32-bit integer")
            if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= 20:
                raise RequestError("steps must be an integer between 1 and 20")
            if not isinstance(lyrics, str) or len(lyrics) > 4096 or not isinstance(instrumental, bool):
                raise RequestError("lyrics/instrumental values are invalid")
            if bpm is not None and (isinstance(bpm, bool) or not isinstance(bpm, int) or not 30 <= bpm <= 300):
                raise RequestError("bpm must be an integer between 30 and 300")
            if not isinstance(language, str) or len(language) > 16: raise RequestError("language must be a short code")
            return {"prompt": prompt.strip(), "parameters": {"duration_seconds": float(duration), "seed": seed,
                    "steps": steps, "lyrics": lyrics, "instrumental": instrumental, "bpm": bpm, "language": language}}
        if self.kind == "kokoro":
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > self.max_prompt_chars:
                raise RequestError("prompt must be 1-2500 characters for Kokoro")
            if set(params) - {"voice"}: raise RequestError("unsupported Kokoro parameters")
            voice = params.get("voice", self.kokoro_voice)
            if voice not in VOICES: raise RequestError("voice is not in the supported English Kokoro voice list")
            return {"prompt": prompt.strip(), "parameters": {"voice": voice}}
        if payload.get("task", "transcribe") != "transcribe": raise RequestError("speech recognition supports task='transcribe' only")
        if set(params) - {"language", "initial_prompt", "temperature", "condition_on_previous_text"}:
            raise RequestError("unsupported transcription parameters")
        language, initial_prompt = params.get("language"), params.get("initial_prompt")
        temperature, condition = params.get("temperature", 0.0), params.get("condition_on_previous_text", True)
        if language is not None and (not isinstance(language, str) or len(language) > 16):
            raise RequestError("language must be a short language code")
        if initial_prompt is not None and (not isinstance(initial_prompt, str) or len(initial_prompt) > 500):
            raise RequestError("initial_prompt must contain at most 500 characters")
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not 0 <= temperature <= 1:
            raise RequestError("temperature must be between 0 and 1")
        if not isinstance(condition, bool): raise RequestError("condition_on_previous_text must be true or false")
        return {"task": "transcribe", "parameters": {"language": language, "initial_prompt": initial_prompt,
                "temperature": float(temperature), "condition_on_previous_text": condition}, "expects_audio": True}

    def _device(self, torch: Any) -> str:
        if torch.cuda.is_available(): return "cuda"
        if self.require_cuda: raise ModelNotReady("CUDA unavailable; use an approved GPU allocation or pass --allow-cpu")
        return "cpu"

    def _load_ace_step(self, device: str) -> None:
        checkpoint_root = MODELS_ROOT / "ace-step-1.5"
        if not self.allow_download:
            from tools.prepare_ace_step_runtime import (
                checkpoint_component_complete,
                checkpoint_status,
                selected_main_components_complete,
            )
            status = checkpoint_status(checkpoint_root)
            if not status["complete"]:
                raise ModelNotReady(
                    "ACE-Step cache-only startup requires complete, validated checkpoint files under "
                    f"{checkpoint_root}; incomplete groups: {', '.join(status['missing'])}"
                )
            if self.ace_config != "acestep-v15-turbo" or self.ace_lm != "acestep-5Hz-lm-0.6B":
                raise ModelNotReady(
                    "ACE-Step cache-only mode is configured for the validated turbo DiT and 0.6B LM only"
                )

            # OEC uses the separate 0.6B LM and intentionally omits the upstream
            # bundle's 1.7B LM. Upstream's default completeness check demands that
            # unused 1.7B folder and auto-downloads the entire bundle if it is absent.
            # Narrow the check to the fully validated selected components and deny
            # every fallback downloader in cache-only mode.
            import acestep.core.generation.handler.init_service_downloads as ace_downloads

            def _selected_main_exists(candidate_root=None):
                return selected_main_components_complete(Path(candidate_root or checkpoint_root))

            def _selected_dit_exists(model_name, candidate_root=None):
                if model_name != self.ace_config:
                    return False
                return checkpoint_component_complete(
                    Path(candidate_root or checkpoint_root) / model_name, model_name
                )

            def _deny_upstream_download(*_args, **_kwargs):
                raise RuntimeError(
                    "OEC cache-only policy blocked ACE-Step auto-download; "
                    "complete checkpoints via tools/prepare_media_models.py under StorageManager"
                )

            ace_downloads.check_main_model_exists = _selected_main_exists
            ace_downloads.check_model_exists = _selected_dit_exists
            ace_downloads.ensure_main_model = _deny_upstream_download
            ace_downloads.ensure_dit_model = _deny_upstream_download
            ace_downloads.ensure_vae_model = _deny_upstream_download
            print("ACE_STEP_CACHE_ONLY_GUARD=active selected_lm=acestep-5Hz-lm-0.6B upstream_auto_download=disabled",
                  flush=True)

        if ACE_STEP_SOURCE_ROOT is None or not (
            (ACE_STEP_SOURCE_ROOT / "pyproject.toml").is_file()
            and (ACE_STEP_SOURCE_ROOT / "acestep").is_dir()
        ):
            raise ModelNotReady(
                "ACE-Step source checkout is missing or unpinned; run prepare_ace_step_runtime.py install first"
            )
        if str(ACE_STEP_SOURCE_ROOT) not in sys.path:
            sys.path.insert(0, str(ACE_STEP_SOURCE_ROOT))
        from acestep.handler import AceStepHandler
        from acestep.llm_inference import LLMHandler
        from acestep.inference import GenerationParams, GenerationConfig, generate_music
        dit = AceStepHandler()
        dit_status, dit_ok = dit.initialize_service(
            project_root=str(ACE_STEP_SOURCE_ROOT), config_path=self.ace_config, device=device, offload_to_cpu=False
        )
        if not dit_ok:
            raise ModelNotReady(f"ACE-Step DiT initialization failed: {dit_status}")
        llm = LLMHandler()
        llm_status, llm_ok = llm.initialize(
            checkpoint_dir=str(checkpoint_root), lm_model_path=self.ace_lm,
            backend="pt", device=device, offload_to_cpu=False
        )
        if not llm_ok:
            raise ModelNotReady(f"ACE-Step language-model initialization failed: {llm_status}")
        self.handlers.update(dit=dit, llm=llm, GenerationParams=GenerationParams, GenerationConfig=GenerationConfig,
                             generate_music=generate_music)

    def _load_kokoro(self) -> None:
        if not self.allow_download and not hf_cache_has_weights("kokoro"):
            raise ModelNotReady("Kokoro checkpoint not cached completely under AIEROS_MODELS_DIR/hub")
        from kokoro import KPipeline
        self.runtime = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")

    def _load_whisper(self, device: str) -> None:
        import urllib.parse
        import whisper
        cache_path = model_targets()[self.name][0]
        url = whisper._MODELS.get(self.whisper_size)
        if not url: raise ModelNotReady("unknown Whisper model size")
        checkpoint = cache_path / urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]
        if not self.allow_download and not checkpoint.is_file():
            raise ModelNotReady(f"Whisper checkpoint not cached at {checkpoint}")
        if self.allow_download:
            cache_path.mkdir(parents=True, exist_ok=True)
        self.runtime = whisper.load_model(self.whisper_size, device=device, download_root=str(cache_path))

    def _load_qwen_asr(self, device: str) -> None:
        import torch
        from qwen_asr import Qwen3ASRModel
        if not self.allow_download and not hf_cache_has_weights(self.name):
            raise ModelNotReady("Qwen3-ASR checkpoint not cached completely under AIEROS_MODELS_DIR/hub")
        dtype = torch.bfloat16 if device == "cuda" and torch.cuda.is_bf16_supported() else torch.float16 if device == "cuda" else torch.float32
        self.runtime = Qwen3ASRModel.from_pretrained("Qwen/Qwen3-ASR-0.6B", dtype=dtype,
                device_map="cuda:0" if device == "cuda" else "cpu", max_inference_batch_size=1, max_new_tokens=1024)

    def load_runtime(self) -> None:
        import torch
        device = self._device(torch)
        ok, _ = storage_check("models", 0.01, 0.05)
        if not ok: raise ModelNotReady("model storage admission failed; inspect StorageManager")
        self.runtime_lock.acquire()
        try:
            _network_policy(self.allow_download)
            estimate = {"ace-step": (10.0, 0.5), "kokoro": (1.5, 0.25), "whisper": (2.0, 0.25), "qwen3-asr": (3.0, 0.25)}[self.kind]
            def load() -> None:
                if self.kind == "ace-step": self._load_ace_step(device)
                elif self.kind == "kokoro": self._load_kokoro()
                elif self.kind == "whisper": self._load_whisper(device)
                else: self._load_qwen_asr(device)
            if self.allow_download:
                with managed_write("models", estimate[0], minimum_free_gb=estimate[1]): load()
            else: load()
            self.device_name, self.model_loaded = device, True
        except Exception:
            self.runtime_lock.release()
            raise

    def close(self) -> None:
        self.runtime_lock.release()

    def run_job(self, job_id: str, request: dict[str, Any], input_file: Path | None):
        out_root = Path(SYSTEM_DIRS["outputs"]).expanduser().resolve() / "media_services" / self.name / "jobs"
        output_dir = safe_child(out_root, job_id)
        with managed_write("outputs", 0.10, minimum_free_gb=0.05): output_dir.mkdir(parents=True, exist_ok=True)
        params, start = request.get("parameters", {}), time.monotonic()
        if self.kind == "ace-step":
            h = self.handlers
            gp = h["GenerationParams"](task_type="text2music", thinking=True, caption=request["prompt"], lyrics=params["lyrics"], instrumental=params["instrumental"],
                duration=params["duration_seconds"], seed=params["seed"], inference_steps=params["steps"], bpm=params["bpm"],
                vocal_language=params["language"])
            cfg = h["GenerationConfig"](batch_size=1, use_random_seed=params["seed"] < 0, audio_format="flac")
            output_budget = max(0.05, params["duration_seconds"] * 0.0015)
            with managed_write("outputs", output_budget, minimum_free_gb=0.05):
                result = h["generate_music"](h["dit"], h["llm"], gp, cfg, save_dir=str(output_dir))
            audios = getattr(result, "audios", None)
            if not getattr(result, "success", False) or not audios: raise RuntimeError("ACE-Step did not return a successful audio result")
            source = Path(audios[0]["path"]).resolve()
            target = safe_child(output_dir, f"{job_id}.flac")
            if source != target.resolve():
                if output_dir.resolve() not in source.parents or not source.is_file():
                    raise RuntimeError("ACE-Step returned an output outside its job directory")
                source.replace(target)
            if not target.is_file() or target.stat().st_size < 64: raise RuntimeError("ACE-Step output is empty or invalid")
            return target, {"duration_seconds": params["duration_seconds"], "seed": params["seed"],
                            "elapsed_seconds": round(time.monotonic() - start, 3), "audio_format": "flac"}
        if self.kind == "kokoro":
            import numpy as np
            import soundfile as sf
            parts = [np.asarray(audio, dtype=np.float32).reshape(-1)
                     for _, _, audio in self.runtime(request["prompt"], voice=params["voice"]) if audio is not None]
            if not parts: raise RuntimeError("Kokoro returned no audio chunks")
            target = safe_child(output_dir, f"{job_id}.wav")
            with managed_write("outputs", 0.10, minimum_free_gb=0.05):
                sf.write(str(target), np.concatenate(parts), 24000, format="WAV", subtype="PCM_16")
            if not target.is_file() or target.stat().st_size < 64: raise RuntimeError("Kokoro output is empty")
            return target, {"voice": params["voice"], "sample_rate": 24000, "elapsed_seconds": round(time.monotonic() - start, 3)}
        if input_file is None or not input_file.is_file(): raise ValueError("speech recognition requires an uploaded audio file")
        if self.kind == "qwen3-asr":
            language = LANGUAGE_NAMES.get((params.get("language") or "").lower()) or params.get("language")
            results = self.runtime.transcribe(audio=str(input_file), language=language)
            item = results[0] if results else None
            transcript, language = (str(getattr(item, "text", "")).strip(), getattr(item, "language", None)) if item else ("", None)
            segments = None
        else:
            opts = {"temperature": params["temperature"], "condition_on_previous_text": params["condition_on_previous_text"],
                    "fp16": self.device_name == "cuda"}
            if params.get("language"): opts["language"] = params["language"]
            if params.get("initial_prompt"): opts["initial_prompt"] = params["initial_prompt"]
            result = self.runtime.transcribe(str(input_file), **opts)
            transcript, language, segments = str(result.get("text", "")).strip(), result.get("language"), len(result.get("segments", []))
        if not transcript: raise RuntimeError("speech recognition returned an empty transcript")
        target = safe_child(output_dir, f"{job_id}.txt")
        with managed_write("outputs", 0.02, minimum_free_gb=0.02): target.write_text(transcript + "\n", encoding="utf-8")
        return target, {"language": language, "segments": segments, "audio_input_bytes": input_file.stat().st_size,
                        "elapsed_seconds": round(time.monotonic() - start, 3), "task": "transcribe"}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("ace-step", "kokoro", "whisper", "qwen3-asr"), required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    parser.add_argument("--queue-size", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--allow-download", action="store_true", help="allow downloads after StorageManager admission; default cache-only")
    parser.add_argument("--whisper-size", choices=("tiny", "base", "small", "medium", "large-v3", "turbo"), default="turbo")
    parser.add_argument("--ace-config", default="acestep-v15-turbo")
    parser.add_argument("--ace-lm", default="acestep-5Hz-lm-0.6B")
    parser.add_argument("--kokoro-voice", default="af_heart")
    parser.add_argument("--allow-cpu", action="store_true", help="allow CPU inference if CUDA is unavailable")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ports = {"ace-step": 7870, "kokoro": 7871, "whisper": 7872, "qwen3-asr": 7873}
    provider = AudioProvider(args.model, args.allow_download, args.whisper_size, args.ace_config, args.ace_lm,
                             args.kokoro_voice, require_cuda=not args.allow_cpu)
    return serve(provider, args.host, args.port or ports[args.model], args.queue_size, args.timeout_seconds)

if __name__ == "__main__":
    raise SystemExit(main())
