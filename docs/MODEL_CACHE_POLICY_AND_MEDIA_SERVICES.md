# OEC model cache policy and media-service adapters

## Disk-cache purge is not VRAM unload

Deleting one Hugging Face model cache directory can reclaim disk space after a complete model load only if the live pipeline no longer reads those files and is not using lazy loading or CPU/disk offload. It does not free VRAM held by a live model. torch.cuda.empty_cache() releases unused allocator blocks, not memory held by referenced tensors. True VRAM unloading requires the owning manager to drop the pipeline/engine references, synchronize, run garbage collection and clear allocator/compiled-graph state.

Use a per-model cache policy: retain (default), candidate (not approved), purge-after-load (only after documented model-specific testing). Never apply purge globally. Deleting cached weights can force later downloads and can break reload while offline or when storage admission blocks writes.

## Current audit status

| Model/runtime | Observed code behavior | Policy | Reason |
|---|---|---|---|
| TRELLIS.2-4B | pipeline_trellis_3d.py clears unused CUDA cache after generation but retains the pipeline; model cache stays on disk. | Retain | No accepted repeat-inference test after cache deletion was available in this audit. |
| FLUX.2 Klein | pipeline_flux_only.ipynb explicitly avoids purging the shared Hugging Face cache. OEC-Play loads its own FLUX.2 Klein/Gemma scene-authoring pipeline on demand. | Retain | No post-purge test for all components; keep using the built-in World Creator seed-image route. |
| LTX-2.3 + Gemma | Legacy worker supports disk cache purge by default; the established multi-node production launch uses --no-purge. | Retain in sidecar | A pipeline construction log is not evidence that prompt encoders/components no longer read cache files. |
| AudioCraft AudioGen/MusicGen | Notebook checks cache and uses OEC storage admission before missing-model downloads. | Retain | Post-purge inference and output checks have not been performed. |

Before approving purge for any model, record the exact repository/cache directory and disk usage; verify full load; produce and reopen a first artifact; delete only that model's own cache subdirectory; produce a second artifact with the same resident pipeline; reopen it; then separately test a fresh restart/reload. Record runtime revision, settings, peak VRAM, time, disk reclaimed, and any lazy disk access. This is an acceptance protocol, not a statement that these tests have passed.

The adapter prototypes keep model caches and delete only their own temporary per-job image inputs. The current job-timeout check detects an overrun after inference returns; it does not interrupt a hung in-process CUDA call. Hard cancellation requires process-level supervision and remains an acceptance item. Generated result retention is separate from model-cache retention and must never remove existing user assets.

## Sidecar API design

The prototype archive includes:
- tools/media_services/trellis_api.py: a TRELLIS.2 sidecar in phase2_3d, loopback port 7868, image-to-GLB jobs.
- tools/media_services/ltx_api.py: an LTX-2.3 sidecar in phase1_ltx, loopback port 7869, text-to-video and image-to-video jobs.
- tools/media_services/common.py: bounded queue, job records, request/image limits, OEC quota-admission checks, run-scoped input cleanup, retention and artifact validators.
- tests/test_media_service_api.py: CPU/mock API tests and small GLB/MP4 fixtures.

The model stack is imported inside its sidecar only. Do not import TRELLIS or LTX into the OEC-Play Waypoint process. The APIs offer GET /health, POST /v1/jobs, GET /v1/jobs/{job_id}, and GET /v1/jobs/{job_id}/result. The services bind only to loopback; use the approved SSH tunnel. Default startup is cache-only, and --allow-download must be a deliberate operator choice after fresh OEC StorageManager admission. A process is ready only after its model loader finishes and required storage checks pass.

Example commands (run only inside the proper approved allocation):
```bash
conda run -n phase2_3d python "$HOME/OEC/tools/media_services/trellis_api.py" --host 127.0.0.1 --port 7868
conda run -n phase1_ltx python "$HOME/OEC/tools/media_services/ltx_api.py" --host 127.0.0.1 --port 7869
```

OEC-Play should use OEC_TRELLIS_SERVICE_URL=http://127.0.0.1:7868 and OEC_LTX_SERVICE_URL=http://127.0.0.1:7869 only after the actual adapter files are transferred to the repo and each service passes live model-ready/artifact tests. FLUX stays in OEC-Play's built-in World Creator prompt route; no separate FLUX API is needed for that interactive path.

## Model selection for additional capabilities

The new model candidates are proposals, not integrated providers:

1. ACE-Step 1.5 — first music-generation candidate for game ambience/background scores. The upstream repository publishes an MIT license, but still review the exact code, checkpoints, dependencies, generated-output rights and requirements before commercial use. https://github.com/ace-step/ACE-Step-1.5
2. Kokoro-82M — small text-to-speech candidate for English NPC dialogue, narration and accessibility voice-over. Its model card lists Apache-2.0 weights, but its phonemizer/dependency licences and actual supported languages must be checked. https://huggingface.co/hexgrad/Kokoro-82M
3. SenseVoice or Whisper — a speech-input candidate for transcription, captions and voice commands. Select only after validating exact checkpoint licences, language coverage and latency.
4. Hunyuan3D-2.1 — later image-to-3D baseline against TRELLIS. It has a separate community licence and model/resource requirements, so review terms and hardware before integration. https://github.com/tencent-hunyuan/hunyuan3d-2.1
5. MusicGen/AudioGen — research-only unless the intended commercial deployment is cleared: official model cards say code is MIT but weights are CC-BY-NC 4.0. https://github.com/facebookresearch/audiocraft/blob/main/model_cards/MUSICGEN_MODEL_CARD.md

The existing OEC catalog contains model research notes in the four CSVs under docs/. Catalog entries are not by themselves proof that a model, license assertion, resource estimate, or dependency combination has been independently verified.

## Integration and MoE wording

Start with deterministic task routing from a requested task to a compatible provider. That is model orchestration, not a trained mixture-of-experts model. A learned MoE claim requires an implemented router, experts, training procedure and loss, checkpoint, routing metrics and evaluation against a baseline.

## Current test status (2026-10-18)

Local compile check passed; the CPU/mock sidecar API suite passed 8/8 tests. Live TRELLIS/LTX inference, model downloads, clean restart, cache purge and OEC-Play integration were not run. Hard process-level timeout enforcement for a GPU call that never returns is not yet implemented. The adapter modules and CPU/mock tests are now committed on the isolated feature branch, but the remote branch was not independently checked out and re-tested after transfer. Live model load/inference and client integration remain unverified.


## New audio-model sidecar

The separate `tools/media_services/audio_api.py` supports four capability-specific providers, one per process:

| Provider | Capability | Cache target under `SYSTEM_DIRS["models"]` | Loopback port |
|---|---|---|---:|
| ACE-Step 1.5 | Prompt-to-music / soundtracks | `ace-step-1.5/` | 7870 |
| Kokoro-82M | English speech synthesis | `hub/models--hexgrad--Kokoro-82M/` | 7871 |
| Whisper | Transcription | `whisper/<size>/` | 7872 |
| Qwen3-ASR 0.6B | Multilingual transcription | `hub/models--Qwen--Qwen3-ASR-0.6B/` | 7873 |

Model cache is rooted at OEC `AIEROS_MODELS_DIR` (or its configured fallback). Whisper has an explicit `download_root`; ACE-Step sets `ACESTEP_CHECKPOINTS_DIR`; Hugging Face providers use OEC `HF_HOME`. Download is disabled unless the operator supplies `--allow-download`, and that mode requires the current StorageManager model preflight plus an in-lock managed write. Do not move model files to `~/.cache`, `/tmp`, scratch, or any unreserved directory as a workaround.

The assistant did not start StorageManager. The operator supplied the fresh `quota_check` baseline for 2026-10-18: 2.14 TB project occupancy, 2.15 TB soft limit and 2.25 TB hard limit; 1836 GitHub Actions minutes were reported used. That is user-supplied telemetry, not a measurement fetched by these code tests. Model loads/writes still use the running OEC StorageManager gate.

Example commands assume environments provisioned by the operator; no environment is created or changed automatically:

```bash
python "$HOME/OEC/tools/model_cache_manager.py" status
conda run -n phase1_ace_step python "$HOME/OEC/tools/media_services/audio_api.py" --model ace-step --host 127.0.0.1 --port 7870
conda run -n phase1_kokoro python "$HOME/OEC/tools/media_services/audio_api.py" --model kokoro --host 127.0.0.1 --port 7871
conda run -n phase1_whisper python "$HOME/OEC/tools/media_services/audio_api.py" --model whisper --whisper-size turbo --host 127.0.0.1 --port 7872
conda run -n phase1_qwen_asr python "$HOME/OEC/tools/media_services/audio_api.py" --model qwen3-asr --host 127.0.0.1 --port 7873
```

The four environment names are proposed isolation points, not a claim that they exist. Audit environment/package state before installing. The API exposes the shared health/job/result routes and accepts bounded `audio_base64` transcribe requests. These services are isolated adapters, not a live client/UI integration.

### Explicit per-model cache purge

`tools/model_cache_manager.py status` reports model-specific cache locations, approximate disk use and runtime locks. Purge requires a named model and `--confirm`, routes deletion through OEC `DiskPurgeManager`, and refuses unsafe paths, active locks, or remote/unknown locks. Example, only after stopping the exact service and checking no active lock remains:

```bash
python "$HOME/OEC/tools/model_cache_manager.py" purge kokoro --confirm
python "$HOME/OEC/tools/model_cache_manager.py" purge whisper-turbo --confirm
```

No purge runs automatically. The cache manager never reads, removes, shrinks or moves `.storage_reserve.bin`. All checkpoint targets are strictly below the configured models root. Job state, temporary inputs, lock records and generated artefacts live under the configured, StorageManager-managed outputs root because the current config defines `models` and `outputs` logical targets, not separate `cache`/`inputs` targets.

Disk-purge safety does not prove model reload works. Before declaring a model purge-safe, record its original size; produce and reopen a first artifact; delete only that model-owned folder; test a second artifact using the resident pipeline; then separately stop/restart and verify clean reload. Record latency, VRAM, bytes reclaimed and any lazy cache reads. The current code does not automatically unload idle models; stop the corresponding sidecar to release its runtime lock and model references.

No Conda environment was installed, no model weight downloaded, no GPU run, no storage daemon was started, no cache purged and no GitHub Actions workflow was triggered as part of this source/CPU-test work.


### Official model references and release checks

- ACE-Step 1.5: https://github.com/ace-step/ACE-Step-1.5 — the adapter defaults to the documented lighter 0.6B language model as a resource-conscious starting point; check the exact checkpoint and dependencies at download time.
- Kokoro-82M: https://huggingface.co/hexgrad/Kokoro-82M and https://github.com/hexgrad/kokoro — weights are listed as Apache-2.0. Check phonemizer and audio-stack dependencies, including espeak-ng if used, before packaging.
- Whisper: https://github.com/openai/whisper — the official repository says code and weights use MIT. Compare size-specific latency and VRAM before selecting the deployment default.
- Qwen3-ASR: https://github.com/QwenLM/Qwen3-ASR — the official repository is Apache-2.0 and documents multilingual recognition; verify the exact 0.6B checkpoint card and installed dependency licences.

The official ACE-Step inference guide documents the handler/generation API used here and demonstrates the 0.6B LM option. The source integration has not loaded these packages in the target Conda environments, so all upstream call compatibility remains subject to live acceptance.

Storage admission is held across actual output writes for TRELLIS GLB, LTX MP4/metadata, ACE-Step music and Kokoro WAV. Whisper/Qwen transcript writes are also managed. A check before folder creation is not a substitute for gating the write itself.


## Read StorageManager status and prepare the first model downloads

Run these commands on A100 inside the OEC checkout, with the user-managed StorageManager daemon already running. The status subcommand invokes only storage_manager.py --status, displays recent manager-log lines and inventories exact model cache folders. The env-audit subcommand checks existing phase1, phase1_ltx and phase2_3d environments without installing anything.

\`\`\`bash
cd "$HOME/OEC"
python tools/prepare_media_models.py status
python tools/prepare_media_models.py env-audit
python tools/prepare_media_models.py plan --preflight
\`\`\`

The downloader is explicit and cache-first. It downloads one model at a time into the configured model directory using live StorageManager preflight and managed_storage_operation; it never launches the daemon or touches the reserve file directly. The aggregate estimate is 21 GB for all five checkpoint groups, with a 2 GB additional free-space margin; each individual transfer rechecks fresh admission under the managed lock. The latest user-supplied model-directory reading was 209 GB used of a 280 GB target (about 71 GB nominal remaining), with a 40 GB positive reserve managed by the operator. These figures were not directly measured by this session. If the aggregate preflight passes, the intended initial batch is:

\`\`\`bash
python tools/prepare_media_models.py download --model all
python tools/model_cache_manager.py status
\`\`\`

The batch includes Kokoro-82M, Whisper turbo, Qwen3-ASR-0.6B, ACE-Step 1.5's DiT/VAE/text encoder, and the separate ACE-Step 0.6B LM. The ACE-Step downloader omits the unused bundled 1.7B LM to avoid duplicate weights. The script validates Hugging Face snapshot weight links and verifies Whisper's official checkpoint hash. On an admission, network or download-tool failure it stops instead of beginning the remaining downloads; rerun after resolving the named failure. It does not install Python packages or create Conda environments.

After downloading, run the environment audit. Start a service only in an existing environment that the audit shows has the required runtime packages; do not put all CUDA model stacks into one environment. For example, Kokoro's service is:

\`\`\`bash
conda run -n phase1 python "$HOME/OEC/tools/media_services/audio_api.py" --model kokoro --host 127.0.0.1 --port 7871
\`\`\`

This example is valid only if env-audit confirms Kokoro, Torch and audio dependencies in phase1. For ACE-Step, use a Python 3.11/3.12 environment that has the official ACE-Step runtime. No environment name beyond phase1, phase1_ltx and phase2_3d is assumed to exist.

The previous source tests were CPU/mock tests only. A model is not considered used successfully until a live health check returns ready, an artifact is generated, and the returned audio/video/transcript is validated. Purge remains disabled by default until a resident second inference succeeds after exact-cache deletion and a separate restart/reload test passes.
