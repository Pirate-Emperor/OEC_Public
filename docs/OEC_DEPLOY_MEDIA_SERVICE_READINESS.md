# OEC media-service readiness and OEC_Deploy integration contract

**Scope:** OEC core repository only. OEC_Deploy is not edited by this workstream.
**Read-only command:** `python tools/check_media_service_readiness.py --json`

## Readiness means

- `READY`: GET `/health` returns HTTP 200 and `ready=true` plus `model_loaded=true`. This alone determines whether a running HTTP provider is usable now.
- `NOT_READY`: health responds, but the service/model/storage is not ready.
- `UNREACHABLE`: the loopback endpoint cannot be reached.
- `NOT_EXPOSED`: a model only has CLI/Gradio and does not have the supervised HTTP job API.
- `runtime_preflight=PASS`: expected interpreter/modules and checkpoint/cache presence checks pass. This does not prove model inference.

The readiness command is read-only: it does not start services, install packages, download checkpoints, allocate GPUs, purge caches, or access `.storage_reserve.bin` directly. Add `--provider ltx` to narrow the report; `--strict` exits nonzero unless every selected service API is ready and runtime preflight passes.

## Provider map

| Capability | Inference environment | Loopback port | Output |
|---|---|---:|---|
| LTX-2.3 video | `phase1_ltx` | `17869` | validated MP4 |
| TRELLIS.2 image-to-3D | `phase2_3d` | `17868` | validated GLB; requires `o_voxel` |
| ACE-Step 1.5 music | `~/.local/venvs/oec-acestep-py311` | `7870` | validated FLAC |
| Kokoro-82M TTS | `~/.local/venvs/oec-audio-py311` | `7871` | validated WAV |
| Whisper Turbo ASR | `~/.local/venvs/oec-audio-py311` | `7872` | text/segments as implemented |
| Qwen3-ASR-0.6B | `~/.local/venvs/oec-audio-py311` | `7873` | text/segments as implemented |
| AudioGen medium | `phase1` | — | WAV; CLI/Gradio only, not HTTP exposed |
| MusicGen medium | `phase1` | — | WAV; CLI/Gradio only, not HTTP exposed |

ACE-Step, Kokoro, Whisper and Qwen3-ASR notebook frontends use `phase2_3d` only as Gradio clients. Provider ML packages remain in isolated backend environments. AudioGen/MusicGen use the existing AudioCraft 1.3.0 / Torch 2.1.0 / CUDA 11.8 `phase1` environment; do not mix model dependencies into shared Conda environments.

## HTTP job contract

These sidecars share a loopback-only contract:

1. `GET /health`; require HTTP 200, `ready=true`, `model_loaded=true`.
2. `POST /v1/jobs`; an accepted provider-specific request returns HTTP 202 and a `job_id`.
3. `GET /v1/jobs/{job_id}` until `succeeded` or `failed`; queued/running is not success.
4. `GET /v1/jobs/{job_id}/result` only after success. Validate content type, artifact bytes and metadata/hash.

Provider task names are not interchangeable: LTX supports `text_to_video` / `image_to_video`; TRELLIS supports `image_to_3d`; ASR providers support `transcribe`. Read the relevant provider adapters for exact parameter schemas. Preserve request IDs, timings, provider/model identity, artifact byte count, SHA-256 and actionable failure details. Never log secrets or accept shell fragments.

## Connecting OEC_Deploy

Sidecars deliberately refuse non-loopback binds. If OEC_Deploy runs on another host, create an SSH tunnel from that deployment host to the OEC host (replace placeholders):

~~~bash
ssh -N \
  -L 17868:127.0.0.1:17868 \
  -L 17869:127.0.0.1:17869 \
  -L 7870:127.0.0.1:7870 \
  -L 7871:127.0.0.1:7871 \
  -L 7872:127.0.0.1:7872 \
  -L 7873:127.0.0.1:7873 \
  <ssh-user>@<oec-host>
~~~

Configure the deployment-side client to use the forwarded `http://127.0.0.1:<port>` addresses. Port `7987` is the OEC-Play engine/server, not a media-service port. Smoke sidecars launched inside Actions can stop when that job exits, so recheck readiness on the persistent OEC host after starting a service.

## Safe operation

First run:

~~~bash
python tools/check_media_service_readiness.py --json
python tools/oec_service_manager.py status ltx-sidecar
python tools/oec_service_manager.py status trellis-sidecar
python tools/oec_service_manager.py status audio-api
python storage_manager.py --status
~~~

Start only a provider whose environment/cache passed preflight, after fresh StorageManager admission, on a GPU passing the shared process-aware admission and that provider's free-VRAM floor. The supervisor is cache-only by default; it must not install or download at start. The optional OEC-Play context-sharing gate only trusts the known same-user, low-memory server-components process when explicitly enabled by `OEC_ALLOW_OEC_PLAY_IDLE_GPU_SHARING=1`; unknown owners block, and no process is killed.

Never purge a shared model cache after one successful request. Test second inference and stop/restart/reload behavior first. `torch.cuda.empty_cache()` does not unload model weights or delete disk cache. `.storage_reserve.bin` is protected and must not be read or modified directly.

## Known gaps

- AudioGen and MusicGen need supervised typed HTTP job APIs before OEC_Deploy can call them using the shared job contract.
- ACE-Step requires independent runtime/checkpoint/source checks, live health, real FLAC generation and Gradio event acceptance before being marked ready.
- Kokoro, Whisper and Qwen3-ASR each need current live model-specific acceptance; environment preparation is not inference acceptance.
- A successful QA decision is not full E2E acceptance: Brain/LTX → Qwen2-VL QA → chunked HF upload → remote manifest/part reassembly and hash read-back remains a separate gate.

Downstream repository `CalamityStriker/OEC_Deploy` intentionally remains unchanged.