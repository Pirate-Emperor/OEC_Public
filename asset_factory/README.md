# OEC Asset Factory

The shared Asset Factory routes each output kind to a loopback model sidecar. It stores validated assets and SHA-256 manifests under the OEC-managed outputs/asset_factory tree, then inserts each completed artifact/manifest pair into the existing HF upload queue (`QUEUE_DB_PATH`, default `outputs/upload_queue.db`) under the StorageManager gate. A `PENDING` queue row means the local pair is queued, not that a remote Hugging Face upload has completed; the upload daemon and remote read-back must be verified separately. Brain can generate model-appropriate prompts for images, 3D concepts, video, songs, music, sound effects, and TTS/speech. Automatic speech recognition (ASR) is input-driven and never invents an audio file.

| Asset type | Default model | Output | Sidecar / port |
|---|---|---|---|
| image | FLUX.2 Klein 4B | PNG | flux_api.py, 7867 |
| 3d_asset | TRELLIS.2 4B | GLB | trellis_api.py, 7868 |
| video | LTX-2.3 | MP4 | ltx_api.py, 7869 |
| song | ACE-Step 1.5 | FLAC | audio_api.py --model ace-step, 7870 |
| speech / tts | Kokoro-82M | WAV | audio_api.py --model kokoro, 7871 |
| transcript | Whisper / Qwen3-ASR-0.6B | TXT | audio_api.py --model whisper, 7872 / --model qwen3-asr, 7873 |
| sound_effect | AudioGen medium | WAV | audiocraft_api.py --model audiogen, 7874 |
| music | MusicGen medium | WAV | audiocraft_api.py --model musicgen, 7875 |

## Opt-in workflow

Asset Factory Brain use cases are present but disabled by default. This prevents a Brain process from unexpectedly queueing generations for multiple large model stacks. Opt into a single prompt job:

```bash
python brain.py --once --use-case asset_flux_image
python -m asset_factory.worker --once

# Input-conditioned speech recognition (no prompt-LLM load; input must be a real audio file):
python brain.py --once --use-case asset_whisper_transcription --input-path "$HOME/aireos_input/recording.wav"
python -m asset_factory.worker --once
python brain.py --once --use-case asset_qwen_transcription --input-path "$HOME/aireos_input/recording.wav"
python -m asset_factory.worker --once
```

Or call the client directly after starting the relevant sidecar:

```bash
python -m asset_factory.client --asset-type image --prompt "A brass lighthouse above alpine clouds"
python -m asset_factory.client --asset-type 3d_asset --prompt "A sculptural brass lighthouse"
python -m asset_factory.client --asset-type video --prompt "A slow aerial move toward a misty lighthouse"
python -m asset_factory.client --asset-type song --prompt "Atmospheric instrumental orchestration" --parameters-json '{"duration_seconds":30,"instrumental":true}'
python -m asset_factory.client --asset-type music --prompt "Warm piano and soft strings"
python -m asset_factory.client --asset-type sound_effect --prompt "Rain pattering on a metal roof"
python -m asset_factory.client --asset-type tts --prompt "Welcome to the coast."
python -m asset_factory.client --asset-type speech --prompt "The expedition starts at dawn."
python -m asset_factory.client --asset-type transcript --model whisper --input "$HOME/aireos_input/recording.wav"
```

For text-only 3D requests, the client composes FLUX PNG generation followed by TRELLIS image-to-3D and returns both artifacts. Whisper and Qwen3-ASR require a real audio input (WAV/MP3/FLAC/OGG/M4A). They do not synthesize audio from a text prompt.

Run each sidecar in the existing model environment appropriate to its dependencies. Start one heavy provider per available GPU allocation until simultaneous memory use has been measured. No model download is implicit: cache-only is the default; the explicit --allow-download option uses the existing StorageManager admission path. For LTX specifically, a normal cache-only sidecar keeps the LTX and Gemma checkpoint files so an offline restart is possible. When an operator explicitly starts `ltx_api.py` with `--allow-download`, the supported load-then-purge policy deletes those two model-cache trees after the pipeline loads into memory to reclaim disk space; use `--keep-model-cache` to opt out. A later restart after purging may need to re-fetch the large weights and will be gated by fresh StorageManager admission. This policy is not enabled for FLUX, TRELLIS, AudioCraft, ACE-Step, Kokoro or ASR because their current supervised sidecars do not have an equivalent verified safe purge/recovery contract.

AudioGen and MusicGen checkpoint metadata identify a CC-BY-NC-4.0/non-commercial restriction; their service start requires --accept-noncommercial-license. Do not use those outputs commercially without independent license review. Sidecars retain model weights on disk for restart, and keep the loaded model resident during service lifetime; VRAM release occurs on orderly shutdown, not after every job.

The Asset Factory contract workflow compiles the Python entry points and tests routing, input constraints, sidecar URL rules, and provider parameter validation. These contract checks are not proof that every GPU model has loaded or generated a valid production-quality artifact; live acceptance remains a separate per-provider gate.
