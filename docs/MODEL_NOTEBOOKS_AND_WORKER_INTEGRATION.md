# Model-specific Gradio notebooks and worker integration

**Updated:** 2026-10-20 (Asia/Kolkata)  
**Scope:** OEC core feature branch fix/media-stack-supervision-20261019; not merged to main.

## Notebook and environment map

| Model / workflow | Notebook | UI kernel / inference environment | Backend | Current evidence |
|---|---|---|---|---|
| LTX-2.3 text/image-to-video | pipeline_ltx_video.ipynb | phase1_ltx | Existing LTX worker/sidecar, loopback port 7869 | Valid MP4 from [A100 run 39278268411](https://github.com/CalamityStriker/OEC/actions/runs/39278268411); joined Brain→QA→upload remains open |
| TRELLIS.2 image-to-3D | pipeline_trellis_3d.ipynb, pipeline_trellis_3d_only.ipynb | phase2_3d | Existing worker/sidecar, loopback port 7868 | GLB generated and reopened; mesh was not watertight |
| FLUX image generation | pipeline_flux_only.ipynb | phase2_3d | pipeline_flux_image.py; combined CLI pipeline_flux_trellis.py | Current-head PNG→GLB A100 acceptance still open |
| AudioGen sound effects | pipeline_audiogen_gradio.ipynb; existing pipeline_audiocraft.ipynb retained | phase1 / AudioCraft 1.3.0, Torch 2.1.0, CUDA 11.8 | pipeline_audiogen.py --offline | Previous short WAV smoke PASS; CC-BY-NC 4.0 weights |
| MusicGen music | pipeline_musicgen_gradio.ipynb | phase1 / AudioCraft 1.3.0, Torch 2.1.0, CUDA 11.8 | pipeline_musicgen.py --offline | BLOCKED before inference by incomplete cache and HF proxy/egress failure; no WAV |
| ACE-Step 1.5 music | pipeline_acestep_gradio.ipynb | UI phase2_3d only; inference ~/.local/venvs/oec-acestep-py311/bin/python | audio-api loopback port 7870 | Isolated runtime/checkpoints prepared historically; actual generation not yet accepted |
| Kokoro-82M TTS | pipeline_kokoro_gradio.ipynb | UI phase2_3d only; inference ~/.local/venvs/oec-audio-py311/bin/python | audio-api loopback port 7871 | Controlled live synthesis smoke passed historically; persistent service acceptance remains |
| Whisper Turbo ASR | pipeline_whisper_gradio.ipynb | UI phase2_3d only; inference ~/.local/venvs/oec-audio-py311/bin/python | audio-api loopback port 7872 | One-clip live smoke passed historically; broad WER not measured |
| Qwen3-ASR-0.6B | pipeline_qwen3_asr_gradio.ipynb | UI phase2_3d only; inference ~/.local/venvs/oec-audio-py311/bin/python | audio-api loopback port 7873 | One-clip live smoke passed historically; separate from visual QA |
| Qwen2-VL visual compliance / QA | qa_compliance_worker.py | Existing configured OEC worker environment | --once --asset-id ID --gpu N within gated E2E flow | Static path/contract tests pass; live decision has not yet been reached |

The phase2_3d kernel used by speech/ACE-Step controls is a Gradio client only. It must not import Torch, Whisper, Kokoro, Qwen-ASR or ACE-Step. Provider packages remain in isolated backend environments. The service supervisor selects the proper Python runtime and validates process/GPU/port ownership.

## Verify repo, environments and storage first

Run on the OEC A100 host from $HOME/OEC after normal access is available:

    cd "$HOME/OEC"
    git status --short --branch
    git fetch origin fix/media-stack-supervision-20261019
    git log -1 --format='%H %D %s'
    "$HOME/Conda/condabin/conda" env list
    nvidia-smi
    python storage_manager.py --status
    python tools/oec_service_manager.py status audio-api
    python tools/oec_service_manager.py status ltx-sidecar
    python tools/oec_service_manager.py status trellis-sidecar

Do not checkout/merge if the working tree is dirty. Do not kill a compute process, touch .storage_reserve.bin directly, or bypass a fresh StorageManager admission.

## Start audio backends one at a time, only when a GPU is actually available

Inspect nvidia-smi and GPU process owners first. The following are alternative, not batch, service starts; use a genuinely free GPU index, not automatically GPU 1:

    python tools/oec_service_manager.py start audio-api --provider kokoro --gpu 1
    python tools/oec_service_manager.py start audio-api --provider whisper --gpu 1
    python tools/oec_service_manager.py start audio-api --provider qwen3-asr --gpu 1
    python tools/oec_service_manager.py start audio-api --provider ace-step --gpu 1
    python tools/oec_service_manager.py status audio-api
    python tools/oec_service_manager.py logs audio-api --tail 80

Require /health to report ready=true and model_loaded=true. A running PID alone is insufficient. Default service mode is cache-only; do not enable downloads without explicit approval and fresh StorageManager admission.

## Model-specific Gradio smoke process

- AudioGen and MusicGen: open the dedicated notebook in phase1. The UI launches the existing CLI in offline/cache-only mode and writes a bounded test result under /tmp. Cache misses fail closed.
- ACE-Step, Kokoro, Whisper and Qwen3-ASR: start the chosen managed service, open its notebook in phase2_3d, confirm readiness and submit a bounded job. ASR accepts audio up to 12 MiB.
- FLUX→TRELLIS: use the existing assigned-runner workflow, which captures GPU admission, StorageManager state and artifacts; inspect the source PNG and independently reopen the GLB.
- LTX/TRELLIS sidecars: use the existing A100 sidecar acceptance and validate real MP4/GLB artifacts. A health endpoint or notebook cell is not production acceptance.

The added static suite checks notebook JSON, Python cell syntax, declared environment and frontend/backend separation only; it does not assert live inference.

## OEC-Deploy integration contract

Keep models in OEC core worker/service processes; do not import model packages into the Electron/UI or World Engine process.

- LTX and TRELLIS expose GET /health, POST /v1/jobs, GET /v1/jobs/{job_id}, GET /v1/jobs/{job_id}/result on loopback ports 7869 and 7868. OEC-Deploy should submit, poll, then retrieve the validated artifact.
- Audio providers expose the same API on ports 7870–7873. Kokoro accepts prompt plus voice. Whisper/Qwen3-ASR accept task=transcribe and base64 audio with no data-URL prefix (maximum 12 MiB). ACE-Step accepts duration 10–180 seconds and inference steps 1–20. Bind loopback only; if UI and API are on separate nodes, use an authenticated internal proxy/tunnel.
- AudioGen/MusicGen currently have guarded CLI workers, not persistent audio API sidecars. OEC-Deploy needs a supervised command/job wrapper with typed inputs, job IDs/status, artifact retrieval, licence metadata, output validation and StorageManager checks. Do not execute arbitrary user-supplied shell strings.
- brain.py/brain_config.json currently handle prompt→LTX job generation, not a general multimodal scheduler. Define and test a typed worker job schema (provider, task, parameters, artifact path/hash, licence, QA status, storage admission, retry/error) before routing audio/3D through Brain.
- qa_compliance_worker.py is the actual visual compliance worker filename (not a_compliance_worker.py). Only QA-approved rows should enter upload pending state.
- The corresponding canonical config/storage files in this checkout are core_config.py, storage_config.json and storage_manager.py (not config.json/storage_manger.py). Do not create aliases without an actual compatibility need.
- hf_upload_daemon.py has managed storage admission and a chunk/manifest upload path. Acceptance requires verifying remote manifest, all part hashes, metadata, independent full-file SHA-256 reconstruction and exact source/row cleanup after a real upload. Never use a placeholder dataset repo or create a repo as part of the smoke.

## Remaining acceptance checklist

1. [ ] Poll the newest guarded E2E attempt; identify whether inference started. The latest rerun failed at preflight because external PID 3347078 was attached to all eight A100s. It is not safe to terminate it.
2. [ ] Once an A100 is released, run current-head FLUX→TRELLIS PNG→GLB and inspect both outputs.
3. [ ] Run ACE-Step actual music generation and validate non-empty FLAC plus metadata and hash.
4. [ ] Resolve MusicGen cache/egress based on fresh network/cache evidence; no blind re-download and keep CC-BY-NC restrictions.
5. [ ] Launch Kokoro, Whisper, Qwen3-ASR and ACE-Step one at a time. Verify health, job lifecycle, artifact bytes, logs and environment isolation.
6. [ ] Run full LTX→Qwen2-VL accept/reject→upload-pending→chunk manifest→remote read-after-write/reassembly/hash workflow.
7. [ ] Test actual interruption/resume and remote chunk consumer with a disposable QA-approved test item; prove only the selected DB row was changed/deleted.
8. [ ] Sync the committed feature branch into $HOME/OEC only after confirming local status and branch state; compare SHAs and do not overwrite dirty local changes.
9. [ ] Build/validate OEC-Deploy clients for the new audio endpoints and for AudioGen/MusicGen worker dispatch; validate artifact downloads, job status and licensing metadata. OEC-Deploy remains read-only within this task.
10. [ ] Run static notebook tests and actual Gradio/provider tests separately; mark statuses independently.
11. [ ] Audit the existing Wan notebook and complete model catalogue for environment/licensing/cache/UI gaps.
12. [ ] Recheck environment pins without bulk-upgrading shared Conda stacks.


## Persistent A100 checkout synchronization

A fail-closed workflow attempts to fast-forward the persistent $HOME/OEC checkout after branch updates. It will not clone, switch branches, reset files, overwrite local changes or replace a divergent history. It proceeds only when the checkout exists, origin identifies CalamityStriker/OEC, the local branch is fix/media-stack-supervision-20261019, the working tree is clean and origin is a fast-forward descendant. The workflow must show OEC_A100_SYNC=PASS and matching before/after/target SHAs before we claim that the long-lived checkout is synced. If it blocks, preserve the local tree and resolve its branch/dirty/origin issue manually.
