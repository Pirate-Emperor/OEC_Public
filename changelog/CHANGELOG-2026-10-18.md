# OEC engineering changelog — 2026-10-18

## Goal
Audit load/purge safety and make progress toward OEC-Play media-service integration without downloads, GPU inference, shared-cache changes, or GitHub Actions usage.

## Source and runtime audit
- Inspected current OEC main purge/storage code, TRELLIS entry point, FLUX notebook, AudioCraft/AudioGen notebook, LTX worker and related tests.
- Inspected the OEC-Deploy feature branch contract in docs/OEC_MEDIA_SERVICES_INTEGRATION.md.
- Confirmed disk-cache purge is separate from VRAM unload. OEC purger deletes selected cache directories; gc.collect() does not unload a referenced pipeline, and torch.cuda.empty_cache() does not free memory occupied by live tensors.
- TRELLIS clears unused CUDA cache after generation but leaves the pipeline loaded and retains model files. The FLUX notebook says it does not purge the shared cache. LTX's existing worker purges cache after loading by default, but the established production multi-node command uses --no-purge. No evidence from this pass proves a successful second inference after cache deletion.
- Reviewed the Waypoint server lifecycle: it has explicit engine/scene-authoring unload helpers; media model adapters must remain in separate phase2_3d and phase1_ltx processes.

## Implementation
- Created feature branch feat/media-service-sidecars-20261018 and updated worker_ltx_video.py to support allow_download=False for cache-only service startup and preserve_cuda_visible_devices=True for respecting the scheduler's visibility mask. Existing worker defaults remain unchanged.
- Prepared a local prototype archive with tools/media_services/common.py, trellis_api.py, ltx_api.py, API fixture tests, and a cache/model selection note. The adapter source bundle is available for download in the associated project chat. The files were subsequently committed to this isolated feature branch; see the follow-up source-integration section below.
- The sidecar design uses loopback-only HTTP, bounded job queues, opaque IDs, safe image validation, OEC quota-aware input/output/state writes, job persistence, run-scoped temporary input cleanup, bounded result retention, GLB geometry validation and MP4 container/ffprobe checks.
- No remote FLUX sidecar was added. OEC-Play's built-in World Creator prompt route remains the FLUX interactive seed path.
- Candidate triage favors ACE-Step 1.5 for music, Kokoro-82M for lightweight English speech, SenseVoice/Whisper for speech input, and Hunyuan3D-2.1 as a later TRELLIS comparison. MusicGen/AudioGen remain research-only pending acceptance of their CC-BY-NC weight licensing for the intended product.

## Tests and experiments
- PASS: python -m py_compile tools/media_services/common.py tools/media_services/trellis_api.py tools/media_services/ltx_api.py tests/test_media_service_api.py.
- PASS: python -m unittest discover -s tests -p 'test_media_service_api.py' -v — 8 passed, 0 failed, 0 errors; local CPU/mock tests using small fixtures.
- The tests cover not-ready/ready state, basic HTTP routes, valid job lifecycle, full queue, invalid request/base64/image, unknown/incomplete result, and GLB/MP4 container validation.
- NOT RUN: live TRELLIS/LTX model load and inference, clean-restart/reload, OEC-Play-to-sidecar integration, cache deletion after load, model download, GPU job, fresh cluster storage probe.
- No GitHub Actions were triggered; no shared model cache, user asset, reserve or quota was changed.

## Follow-up source integration on the same feature branch
- Added `tools/media_services/common.py`, `trellis_api.py`, `ltx_api.py`, package initializer, and `tests/test_media_service_api.py` to this branch after the local prototype suite passed. These remote source files have not been independently re-tested from a fresh branch checkout. This did not trigger GitHub Actions.

## Interpretation and limitations
The local suite validates the prototype API/job boundaries only. It does not prove either model runs in the proposed sidecar or that real GLB/MP4 outputs pass end-to-end acceptance. The current timeout check only catches an overrun after inference returns; a hung in-process CUDA call is not forcibly interrupted. Hard timeout enforcement via process supervision remains open. The model adapter files must first be transferred into the repository and reviewed, then tested in their assigned environments after fresh storage and allocation checks.

## Next actions
1. Review the committed sidecar files and rerun the CPU/mock suite from a fresh checkout of this feature branch.
2. In an authorized allocation, verify GET /health, run one fixed TRELLIS image-to-GLB job and one fixed LTX prompt-to-MP4 job; independently reopen the GLB and read the MP4.
3. Configure OEC-Play service URLs only after both adapters pass live artifact acceptance.
4. Authorize model cache purge individually only after a repeat inference succeeds after deleting that exact model-cache directory, and record disk/VRAM/latency effects.
5. Establish the original project start/deadline from an authoritative project record; it was not recoverable during this pass.

