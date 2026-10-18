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

Local compile check passed; the CPU/mock sidecar API suite passed 8/8 tests. Live TRELLIS/LTX inference, model downloads, clean restart, cache purge and OEC-Play integration were not run. Hard process-level timeout enforcement for a GPU call that never returns is not yet implemented. The adapter source remains a local prototype archive until it is transferred and reviewed on this branch.
