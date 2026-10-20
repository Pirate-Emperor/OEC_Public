# Model-specific Gradio notebooks and worker integration

**Updated:** 2026-10-20 (Asia/Kolkata)  
**Scope:** OEC core feature branch fix/media-stack-supervision-20261019; not merged to main.

## Notebook and environment map

| Model / workflow | Notebook | UI kernel / inference environment | Backend | Current evidence |
|---|---|---|---|---|
| LTX-2.3 text/image-to-video | pipeline_ltx_video.ipynb | phase1_ltx | Existing LTX worker/sidecar, manager default loopback port 17869 (smoke may override) | Valid MP4 from [A100 run 39278268411](https://github.com/CalamityStriker/OEC/actions/runs/39278268411); joined Brain→QA→upload remains open |
| TRELLIS.2 image-to-3D | pipeline_trellis_3d.ipynb, pipeline_trellis_3d_only.ipynb | phase2_3d | Existing worker/sidecar, manager default loopback port 17868 (smoke may override) | GLB generated and reopened; mesh was not watertight |
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

- LTX and TRELLIS expose GET /health, POST /v1/jobs, GET /v1/jobs/{job_id}, GET /v1/jobs/{job_id}/result on loopback manager default ports 17869 and 17868 (a specific smoke can override them). OEC-Deploy should submit, poll, then retrieve the validated artifact.
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


## Latest state and local sync caveat (2026-10-20)

- Static workflow run 39379246551 on source c79401c00182e94f3bc3f4d38109174f0662c7f5 passed all steps, including the new notebook tests 3/3.
- The live E2E attempt 39320471955 (attempt 2) is blocked by the external GPU process noted in docs/checklist.md; no inference/QA/upload was reached.
- Safe sync run 39379246680 blocked because $HOME/OEC is on detached HEAD. The script refused to switch it; its working-tree cleanliness is unknown. Diagnose before taking a manual action.


## Exact persistent checkout status (2026-10-20)

Read-only preflight in run 39379628387/job 118485509739 confirmed: origin matches CalamityStriker/OEC; $HOME/OEC is detached at 081aaf34f6379873bdc925d1dcf6b9c3d50349d3; the expected local branch does not exist; the origin tracking ref does exist; 662 dirty/untracked entries are present. The sync helper correctly stopped. Do not run reset/clean/checkout over this state. Review the local status/diffs and back up user work first, or prepare a separate clean worktree once storage and path capacity are verified.


## Additional repository model: Wan 2.1 (not yet accepted)

The existing `pipeline_wan_video.ipynb` declares the `phase1` Python 3.9.25 kernel and embeds a Wan2.1-T2V-14B class in a notebook cell; it is not a separate worker or Gradio application. It references `SYSTEM_DIRS` without binding that name (it imports `core_config` only), selects GPU by free memory alone, and includes historical saved outputs. Therefore it is **not** counted as working or integrated. Do not install additional packages into shared `phase1` to make it run. First verify the cached Wan model, PyTorch/diffusers versions, and an isolated environment; then implement a dedicated, process-aware, StorageManager-gated worker plus a Gradio client and static/runtime checks.


## Clean local A100 test checkout

The existing `$HOME/OEC` checkout has 662 dirty/untracked entries and is detached. The sync workflow never resets or overwrites it. If the in-place fast-forward guard blocks, `tools/create_clean_a100_test_worktree.sh` checks StorageManager admission first and creates or updates only the dedicated, clean `$HOME/OEC_feature_sync` worktree. It refuses a pre-existing unregistered/dirty target, uses `--detach` and verifies actual SHA equals origin. Look for `OEC_CLEAN_WORKTREE_SYNC=PASS` and `A100_CHECKOUT_ACTUAL_SHA=<expected>` in [the sync workflow](../.github/workflows/oec-a100-local-sync.yml). If StorageManager denies the operation or the target is dirty, it does not force a write.

Once the workflow passes, use `cd "$HOME/OEC_feature_sync"` for notebook/test commands below. This is a separate checkout; the old 662-entry `$HOME/OEC` tree remains untouched.


## Sync result for this session

Run [39380653563](https://github.com/CalamityStriker/OEC/actions/runs/39380653563), job 118488776455, passed by creating `$HOME/OEC_feature_sync` after fresh StorageManager admission. Exact target and actual source SHA: `32e1a5f9203ed94214f4151c51e2504fe6589002`. The existing `$HOME/OEC` detached/dirty checkout was preserved. The static workflow [39380653548](https://github.com/CalamityStriker/OEC/actions/runs/39380653548) passed on the same code source; this is not a live inference pass.
