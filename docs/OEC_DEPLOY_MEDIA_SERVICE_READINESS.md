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
| FLUX.2 Klein text-to-image | `phase2_3d` | — | PNG; combined CLI/Gradio pipeline only, not HTTP exposed |
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

Downstream repository `xflexwork/OEC_Deploy` intentionally remains unchanged.
## Current A100 acceptance evidence and blockers

On run 39422087711, the six requested HTTP-capability models plus independent AudioGen/MusicGen generation paths were exercised. Kokoro, Whisper and Qwen3-ASR each had `/health` report `ready=true` and `model_loaded=true` during its callback and returned usable outputs. LTX and TRELLIS did likewise and returned a validated MP4/GLB. Exact output byte counts and SHA-256 values are in `docs/checklist.md`.

ACE-Step was not inference-accepted: the preflight saw complete selected weights/source and present modules, but the guarded installer rejected the cache write on a fresh quota check (10,888,517,632 bytes available against 12,884,901,888 required). The workflow now uses `prepare_ace_step_runtime.py ensure`, which can reuse only a verified pinned environment without writes and otherwise keeps the StorageManager installation gate.

Provider artifacts generated by a CI smoke prove the model worked in that job; they do not keep that service running. Since the job tears down the test servers, the post-run readiness report correctly marks loopback APIs `UNREACHABLE` afterward. On the persistent deployment host, start just the required services via `tools/oec_service_manager.py`, then require the report's live `api_status=READY` and `usable_by_deploy_now=true` before routing OEC_Deploy traffic. AudioGen, MusicGen and standalone FLUX remain `NOT_EXPOSED` under the shared HTTP job contract.

## Latest evidence note — 2026-10-20

The full A100 acceptance run [39435100568](https://github.com/xflexwork/OEC/actions/runs/39435100568), source SHA `0c53f6a46328bc4ba6ce4d0942556e3077ea6d74`, passed all 8 ordered jobs. Actual inference and real callbacks were verified for ACE-Step, Kokoro, Whisper Turbo, Qwen3-ASR, AudioGen and MusicGen; temporary service inference/structural artifact checks passed for LTX-2.3 and TRELLIS.2; FLUX PNG→TRELLIS GLB passed. Joined job `118691033786` passed LTX generation → Qwen2-VL QA → three-part `oec-asset-chunks-v1` upload → separate remote read-back/reassembly. The 228,845-byte asset SHA-256 was `3d66b13693184eb7f76841f96836ded2f3407dc1e11b810f2e91c1db8b465392`, matching the local QA-passed source; metadata SHA-256 `67c48f7483c3eccf836e9daef75e271c4c400026852f0e3da0ad4012d8b822de`.

Current source SHA is `72b71f861bba72b78da1cec330e4273b00baaabb`. Static/storage run [39452849501](https://github.com/xflexwork/OEC/actions/runs/39452849501) passed on this exact SHA. Live run [39452849617](https://github.com/xflexwork/OEC/actions/runs/39452849617) is in progress after its source-sync job passed. This commit adds validated Whisper `segment_timestamps` metadata and unit coverage for correct and malformed timestamps, while preserving existing text-artifact bytes/format and segment count. Wait for run 39452849617 before claiming the changed Whisper provider accepted.

Historical source-sync runs used `$HOME/OEC_feature_sync` to avoid overwriting a dirty/detached primary checkout. That split-root workaround is retired in favor of the bounded canonical-root workflow; verify its latest run before relying on A100 checkout state. Workflow-local HTTP services shut down after test exit; a post-run unreachable endpoint does not prove deploy readiness. Standalone FLUX, AudioGen and MusicGen remain `NOT_EXPOSED` on the shared supervised `/v1/jobs` API. AudioGen/MusicGen weights are CC-BY-NC-4.0. The persistent service/consumer route, high-load reliability, broad semantic metrics and TRELLIS watertightness remain outstanding.
