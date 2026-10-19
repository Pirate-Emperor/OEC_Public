# OEC project continuation checklist

**Snapshot:** 2026-10-19 20:18 IST  
**Branch:** `fix/media-stack-supervision-20261019` (not merged to main)  
**Static test source SHA:** `3db0a5294e170fd61dc95f1e84b4ead4be538dd2`; subsequent commits update workflow diagnostics and records. No merge to main.  
**Target:** user requests completion by 2026-10-21. The original 15-day start/deadline has not been recovered; do not reset or guess it.

Permanent instructions are in [Prompt.md](Prompt.md); current media pipeline detail is in [MODEL_PIPELINE_CONTINUATION_PROMPT.md](MODEL_PIPELINE_CONTINUATION_PROMPT.md); daily chronological record is in [the 2026-10-19 changelog](../changelog/CHANGELOG-2026-10-19.md); consolidated engineering backlog is [TODO.md](../TODO.md).

## Verified source and test state

- **Latest static/storage tests PASS:** [run 39272166140](https://github.com/CalamityStriker/OEC/actions/runs/39272166140), job `118127020858`, commit `3db0a5294e17`, hosted runner/Python 3.11.17. **79 tests passed**: TRELLIS notebook 12, TRELLIS CLI 5, AudioCraft notebook 6, storage write admission 6, inference/storage integration 4, Brain/LTX queue 4, upload status 5, upload daemon storage 4, StorageManager 10, StoragePolicy 10, quota snapshot 7, storage reservation 6. `py_compile` passed; four notebooks parsed as valid JSON with 16/15/10/6 cells. The uploader test logger `ResourceWarning` is now cleaned up in test teardown. Static/unit tests do not prove real model inference/upload.
- **QA GPU-selection correction:** `qa_compliance_worker.py` now sets `CUDA_VISIBLE_DEVICES` before importing Torch, supports `--gpu`, and validates non-negative physical index. Static AST test passed; live Qwen2-VL model inference remains unverified.
- **Newest FLUX→TRELLIS attempt BLOCKED:** [run 39271901007](https://github.com/CalamityStriker/OEC/actions/runs/39271901007), job `118126083988`, `oec-1`/`phase2_3d`; environment/preflight, source compilation, 7 FLUX + 5 combined-pipeline contract tests, storage before/after and artifact upload succeeded. Real inference failed safely because PID `3347078`, owner `rahkus`, parent `3345823`, had a compute context on all eight A100s (0% utilization; 6,280 MiB GPU 0 and 416 MiB GPUs 1–7; process age ~1h36m). **No process was killed and no PNG/GLB was generated.** Diagnostic artifact [12195338666](https://github.com/CalamityStriker/OEC/actions/runs/39271901007/artifacts/12195338666). This is a point-in-time observation; refresh before any retry.
- **Speech smoke PASS:** [run 39268082165](https://github.com/CalamityStriker/OEC/actions/runs/39268082165), job `118112826187` on `oec-1`. Kokoro / Whisper / Qwen3-ASR passed controlled inference with startup+inference 22.45 / 18.47 / 20.45 s.
- **ACE-Step runtime prepared / actual generation BLOCKED:** same run confirms selected checkpoint groups and isolated source `ca1e85fe9430179831e6bc6be790c332190a3866`; actual runtime is Python 3.12, Torch 2.10.0+cu128, CUDA 12.8, A100 detected, shared Torch unchanged. Its required generation step failed closed because no idle A100 was eligible; no music file was produced.
- **MusicGen BLOCKED before inference:** [run 39254306725](https://github.com/Killer4K-N/OEC/actions/runs/39254306725) passed 4/4 offline contracts but cached weights were incomplete and the Hugging Face proxy returned `No route to host`. No WAV; checkpoint is CC-BY-NC research-only absent separate commercial rights.
- **Earlier independent artifact passes:** AudioGen [39240127736](https://github.com/Killer4K-N/OEC/actions/runs/39240127736) produced a valid 3 s mono 16 kHz WAV (96,078 bytes, 26.737 s). TRELLIS/LTX standalone [39240127757](https://github.com/Killer4K-N/OEC/actions/runs/39240127757) produced a validated 2,742,900-byte GLB and 242,547-byte H.264 MP4 (768×512, 2.083 s). These are standalone, not the joined Brain/QA/upload path.
- **Training is separate and blocked:** latest bounded Phase-1 profile run [39268460684](https://github.com/CalamityStriker/OEC_AireOS_Full_Model/actions/runs/39268460684), job `118114144337` on `oec-train` / `oec_train`, failed before training because fresh quota telemetry was unavailable for the requested 2 GB dependency install. Cleanup verification also failed. Unit-only [39267110795](https://github.com/CalamityStriker/OEC_AireOS_Full_Model/actions/runs/39267110795) passed tests, not training.

## Pipeline integration boundary

- Live Qwen2-VL compliance decisions and actual approval/rejection output not yet tested.
- A sustained Brain → LTX worker → QA → SQLite PENDING → uploader ARCHIVING → tar.gz → Hugging Face upload/read-after-write lifecycle is not yet accepted.
- `hf_upload_daemon.py` batches full asset + JSON pairs into size/age-flushed tar.gz archives. `brain_config.json:max_batch_size=10` batches prompts/jobs. No individual-file resumable chunk upload implementation was verified. LTX temporal/VAE chunking is a separate concern.
- OEC-Play live `/health`, GUI→server path, and production launch are not verified in this session.
- Viewer graph structural audit on main: `temp/temp_recent.json` SHA `af713bce3dd4db2dfec556821ecd10b4037f1953` had arch v44.0 (29 nodes/27 edges), pipeline v39.0 (30/31), hardware v44.0 (22/21); `diagrams/model_learning.json` SHA `d88f675461a1d32ca67339bf0b7cffae6d0435cc` has 5 training versions (16–24 nodes), frozen_ft v1.0 (12/12), and moe v1.0 (17/14). The simple audit found 0 duplicate node IDs and 0 missing edge endpoints. This does not validate all sources/equations or browser rendering.
- Report_Docs `main` current head observed `a47d5a792d8c`; source scan / continuation rules / version-reconciliation / poster evidence were inspected. No PDF was built or visually reviewed in this session; PaperDock compile is not verified. Keep poster, presentation and dissertation claims synchronized to accepted runs.

## Storage and runner safety

The newest StorageManager snapshot from run 39271901007 showed 2.04/2.10 TB group hard quota, 60.38 GB reported hard headroom under active grace, models 232.81/280 GB and outputs 294.17 MB/1 GB. It is not future write authorization. User withdrew the Actions-only $0 veto; StorageManager admission, fresh telemetry, model licensing, exact runner/env, GPU ownership and no-overlap rules remain mandatory. The GPU listing from run 39271901007 showed PID 3347078 (`server-components/.venv/bin/python`, user rahkus, parent 3345823, about 1h36m old) on all eight A100s at 0% utilization; that is historical, not proof of current state. Do not kill or signal it. Do not kill or signal it.

## Next acceptance gates

1. Refresh assigned `oec-1` GPU/process/port state and StorageManager status. If safe idle-A100 admission passes, run cache-only FLUX→TRELLIS then ACE-Step separately; require actual reopened, hashed PNG/GLB and audio artifacts.
2. Run `test_upload_daemon_storage.py`, `test_upload_status_contract.py`, and `test_brain_ltx_queue_storage.py` on the approved lightweight environment. Then execute one run-scoped, small approved media item through real QA→archive→HF upload and verify receipt + read-after-write without touching existing shared records.
3. Test Qwen2-VL QA with one policy-compliant and one known policy-violating fixture under its assigned GPU and environment, recording the decision/status/output trace.
4. Diagnose MusicGen cache completeness and actual runner egress before any retry. Keep its non-commercial boundary.
5. Recover the authoritative original project start/deadline. The user’s target is 2026-10-21, not a replacement for the original 15-day clock.
6. Rebuild and inspect the existing Report_Docs poster/PPT/report only after checking current PaperDock source versions; this session did not perform PDF visual QA.