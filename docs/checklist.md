# OEC project continuation checklist

**Snapshot:** 2026-10-20 — model-specific Gradio rollout added; live acceptance status below  
**Branch:** `fix/media-stack-supervision-20261019` (not merged to main)  
**Latest tested code SHA:** `132a8a5820a104ec27c14a87c9af3d4f84e83b98` passed the complete static/storage workflow in [run 39380928743](https://github.com/CalamityStriker/OEC/actions/runs/39380928743), job `118489623553`; the new Gradio notebook suite passed 3/3. Current branch head may advance with the tracker update; branch `fix/media-stack-supervision-20261019`; not merged to main.  
**Target:** user requests completion by 2026-10-21. The original 15-day start/deadline has not been recovered; do not reset or guess it.

Permanent instructions are in [Prompt.md](Prompt.md); current media pipeline detail is in [MODEL_PIPELINE_CONTINUATION_PROMPT.md](MODEL_PIPELINE_CONTINUATION_PROMPT.md); daily chronological record is in [the 2026-10-19 changelog](../changelog/CHANGELOG-2026-10-19.md); consolidated engineering backlog is [TODO.md](../TODO.md).

## Verified source and test state

- **Latest completed static/storage suite PASS:** [run 39300850953](https://github.com/CalamityStriker/OEC/actions/runs/39300850953), job `118225345013`, tested source SHA `80cc89480ee79f18d1ec7c101f97cfc310379ed1`, hosted Python 3.11.17. **96 tests passed**, including 6 guarded E2E acceptance contract tests; source compilation and all four notebook JSON checks (16/15/10/6 cells) passed; no ResourceWarning. This preserves the uploader chunk/resume, QA frame-path, fresh quota, and Brain/LTX queue tests.
- **QA GPU-selection correction:** `qa_compliance_worker.py` now sets `CUDA_VISIBLE_DEVICES` before importing Torch, supports `--gpu`, and validates non-negative physical index. Static AST test passed; live Qwen2-VL model inference remains unverified.
- **Guarded live E2E attempted and blocked safely:** [run 39300850928](https://github.com/CalamityStriker/OEC/actions/runs/39300850928), job `118225345452`, assigned `oec-1`, ran runner/env checks and `py_compile`, then exited with `OEC_E2E_BLOCKED` because external PID `3347078` (`Biome/server-components/.venv/bin/python`) had CUDA contexts on all eight A100s. It stopped before StorageManager/HF-target checks, LTX inference, Qwen2-VL QA or upload. Failure report artifact [12211286861](https://github.com/CalamityStriker/OEC/actions/runs/39300850928/artifacts/12211286861) confirms `process_kill_attempted=false`, `shared_queue_used=false`, `remote_dataset_created=false`. Do not kill/signal the process; rerun only after normal owner release and fresh admission.
- **QA frame-path/transcode hardening verified:** `qa_compliance_worker.py` derives a separate `*_qa_frame.jpg` from `Path.stem` for `.mp4`, `.webm`, and `.avi`, removes only its own partial frame after ffmpeg failure, and requires fresh quota for transcode writes. Executable mocked-ffmpeg regression coverage passed in `tests/test_inference_storage_integration.py` at run 39278190899. This verifies source-path integrity and static quota enforcement, not a live Qwen2-VL decision.
- **New live sidecar acceptance (workflow SUCCESS):** [run 39278268411](https://github.com/CalamityStriker/OEC/actions/runs/39278268411), runner `oec-1`, terminal GitHub conclusion is now success; report JSON records 2/2 providers PASS. TRELLIS API ready/model-loaded and generated GLB 2,775,928 bytes (SHA-256 `e7a1a970edae002596a80fa47b19ad87e96ad82a8dfa3d4523ad65167435e875`); independent local `trimesh` reopen passed but mesh is **not watertight**. LTX API ready/model-loaded and generated H.264 MP4 242,547 bytes (SHA-256 `5d7d54de4354936f66867fecd19d20c0ab6972b5d997ca00c145ab0c1e54ec51`), 768×512, 2.083 s; independent ffprobe passed. Artifact [12198722285](https://github.com/CalamityStriker/OEC/actions/runs/39278268411/artifacts/12198722285) contains the outputs/report/logs, was downloaded and inspected. Model downloads/package installs were disabled. This is loopback sidecar API acceptance, not Brain→QA→uploader E2E.
- **Newest FLUX→TRELLIS attempt BLOCKED:** [run 39271901007](https://github.com/CalamityStriker/OEC/actions/runs/39271901007), job `118126083988`, `oec-1`/`phase2_3d`; environment/preflight, source compilation, 7 FLUX + 5 combined-pipeline contract tests, storage before/after and artifact upload succeeded. Real inference failed safely because PID `3347078`, owner `rahkus`, parent `3345823`, had a compute context on all eight A100s (0% utilization; 6,280 MiB GPU 0 and 416 MiB GPUs 1–7; process age ~1h36m). **No process was killed and no PNG/GLB was generated.** Diagnostic artifact [12195338666](https://github.com/CalamityStriker/OEC/actions/runs/39271901007/artifacts/12195338666). This is a point-in-time observation; refresh before any retry.
- **Latest completed A100 bootstrap:** [run 39278145617](https://github.com/CalamityStriker/OEC/actions/runs/39278145617), job `118147435541`, runner `oec-1`, SHA `249b34e7738cda7596b5019c8b096144825955bc`, concluded FAILURE. Kokoro/Whisper/Qwen3-ASR smokes passed at 22.48/18.47/20.45 s; ACE-Step source/checkpoints and isolated Python 3.12 + Torch 2.10.0+cu128/CUDA 12.8 runtime checks passed, but required generation was refused: no idle A100 was eligible. No song output. MusicGen model-weight fetches still hit proxy/CDN timeouts and `No route to host`.
- **ACE-Step runtime prepared / actual generation BLOCKED:** same run confirms selected checkpoint groups and isolated source `ca1e85fe9430179831e6bc6be790c332190a3866`; actual runtime is Python 3.12, Torch 2.10.0+cu128, CUDA 12.8, A100 detected, shared Torch unchanged. Its required generation step failed closed because no idle A100 was eligible; no music file was produced.
- **MusicGen BLOCKED before inference:** [run 39254306725](https://github.com/Killer4K-N/OEC/actions/runs/39254306725) passed 4/4 offline contracts but cached weights were incomplete and the Hugging Face proxy returned `No route to host`. No WAV; checkpoint is CC-BY-NC research-only absent separate commercial rights.
- **Independent live outputs:** AudioGen [39240127736](https://github.com/Killer4K-N/OEC/actions/runs/39240127736) produced a valid 3 s mono 16 kHz WAV (96,078 bytes, 26.737 s). The stronger current TRELLIS/LTX loopback API acceptance is run 39278268411 (see above); prior run [39240127757](https://github.com/Killer4K-N/OEC/actions/runs/39240127757) also passed standalone artifact generation. These outputs are not the joined Brain/QA/upload path.
- **Training is separate and blocked:** latest bounded Phase-1 profile run [39268460684](https://github.com/CalamityStriker/OEC_AireOS_Full_Model/actions/runs/39268460684), job `118114144337` on `oec-train` / `oec_train`, failed before training because fresh quota telemetry was unavailable for the requested 2 GB dependency install. Staging cleanup passed; no training was run. Unit-only [39267110795](https://github.com/CalamityStriker/OEC_AireOS_Full_Model/actions/runs/39267110795) passed tests, not training.

## Pipeline integration boundary

- Live Qwen2-VL compliance decisions and actual approval/rejection output not yet tested. The guarded E2E workflow is now implemented, but its first live attempt (39300850928) failed closed before inference because all eight A100s had CUDA contexts owned by external PID 3347078. Quota/HF-auth gates, actual QA, upload and read-after-write therefore remain untested in that run.
- A sustained Brain → LTX worker → QA → SQLite PENDING → uploader ARCHIVING → tar.gz → Hugging Face upload/read-after-write lifecycle is not yet accepted.
- `hf_upload_daemon.py` normal mode batches whole asset + JSON pairs into size/age-flushed tar.gz archives; `brain_config.json:max_batch_size=10` batches prompts/jobs. The explicit `--once --asset-id ID --chunk-oversize` mode adds bounded per-file chunks, full-source/per-part SHA-256s, metadata, and a completion manifest uploaded last. Existing remote parts are skipped only after size/digest verification. The simulated interruption/resume/reassembly tests passed in both prior run 39291422187 and current 96-test run 39300850953; **no real HF upload/read-after-write or remote consumer reassembly has occurred**. The live E2E run was blocked before that gate. LTX temporal/VAE chunking remains separate.
- Commit `a7b513bad73564a8d3e75a25167e315a15feb21d` narrows expensive A100 bootstrap push triggers so future QA/uploader/status-only edits do not trigger model download/bootstrap workflows. The formerly queued/in-progress jobs have been reconciled: bootstraps `39277286186` and `39278145617` both concluded FAILURE because ACE-Step generation found no eligible idle A100; visual sidecar `39278268411` concluded SUCCESS with validated TRELLIS/LTX outputs. Do not interpret these terminal results as a pass for ACE-Step music or the combined FLUX→TRELLIS pipeline.
- The bounded uploader `hf_upload_daemon.py --once --asset-id ID` selects exactly one PENDING row, no broader fallback/startup cleanup/remote-repo auto-create, and rolls only the selected row back after failure. Oversized assets remain rejected by default; opt-in `--chunk-oversize` now performs per-file hashed chunk uploads and can resume verified remote parts. CI run 39291422187 passed the simulated interruption→resume, local source preservation, SHA reassembly, metadata and manifest-last tests. **It has not been run against a real Hugging Face dataset**, so live receipt/read-after-write and consumer assembly remain open.
- OEC-Play live `/health`, GUI→server path, and production launch are not verified in this session.
- Viewer graph structural audit on main: `temp/temp_recent.json` SHA `af713bce3dd4db2dfec556821ecd10b4037f1953` had arch v44.0 (29 nodes/27 edges), pipeline v39.0 (30/31), hardware v44.0 (22/21); `diagrams/model_learning.json` SHA `d88f675461a1d32ca67339bf0b7cffae6d0435cc` has 5 training versions (16–24 nodes), frozen_ft v1.0 (12/12), and moe v1.0 (17/14). The simple audit found 0 duplicate node IDs and 0 missing edge endpoints. This does not validate all sources/equations or browser rendering.
- Report_Docs `main` current head observed `a47d5a792d8c`; source scan / continuation rules / version-reconciliation / poster evidence were inspected. No PDF was built or visually reviewed in this session; PaperDock compile is not verified. Keep poster, presentation and dissertation claims synchronized to accepted runs.

## Storage and runner safety

The newest StorageManager snapshot from run 39271901007 showed 2.04/2.10 TB group hard quota, 60.38 GB reported hard headroom under active grace, models 232.81/280 GB and outputs 294.17 MB/1 GB. It is not future write authorization. User withdrew the Actions-only $0 veto; StorageManager admission, fresh telemetry, model licensing, exact runner/env, GPU ownership and no-overlap rules remain mandatory. The GPU listing from run 39271901007 showed PID 3347078 (`server-components/.venv/bin/python`, user rahkus, parent 3345823, about 1h36m old) on all eight A100s at 0% utilization; that is historical, not proof of current state. Do not kill or signal it.

## Next acceptance gates (updated 2026-10-19 23:33 IST)

1. Refresh assigned `oec-1` GPU/process/port state and StorageManager status. The newest E2E run proves its guard works but did not reach quota/HF/inference because PID `3347078` occupied all eight A100s. Release must happen through the process owner’s normal lifecycle; never kill or signal it or bypass the selector.
2. After fresh idle-GPU and quota admission pass, rerun [the guarded E2E workflow](https://github.com/CalamityStriker/OEC/actions/workflows/oec-e2e-acceptance.yml). Require a real sidecar-generated LTX asset, actual Qwen2-VL decision, `PENDING_UPLOAD` handoff, verified existing/authenticated HF dataset, successful one-row chunk upload, and independent remote manifest/part/metadata readback with reconstructed full-file SHA-256.
3. If GPU remains blocked, use the window for independent academic delivery tasks: rebuild existing Report_Docs report/PPT/poster from their authoritative sources and perform page-by-page visual review; recheck current Viewer graph source claims and PaperDock source/build state. No fresh Report_Docs PDF/PPT/poster build or visual review was completed in this session.
4. Run combined FLUX→TRELLIS and ACE-Step separately only after the assigned selector admits an idle GPU; require a real PNG→GLB result for the former and an audio artifact for the latter. MusicGen remains cache/proxy blocked and CC-BY-NC.
5. Recover the original project start/deadline from authoritative records. Target requested by the user is 2026-10-21; do not replace the original 15-day clock with a newly invented timeline.


## 2026-10-20 — model-specific Gradio notebook rollout

- [x] Added dedicated AudioGen and MusicGen Gradio notebooks, both using the existing phase1 CLI workers with offline/cache-only mode and run-scoped /tmp outputs.
- [x] Added ACE-Step, Kokoro, Whisper Turbo and Qwen3-ASR Gradio control notebooks. They call the existing loopback job API; the frontend does not import provider ML packages, preserving oec-audio-py311 and oec-acestep-py311 isolation.
- [x] Added a model/environment matrix and OEC-Deploy API/worker integration notes in docs/MODEL_NOTEBOOKS_AND_WORKER_INTEGRATION.md.
- [x] Preserved the first static test failure [39378972546](https://github.com/CalamityStriker/OEC/actions/runs/39378972546) as history. It failed at the notebook minimum-cell assertion; after adding environment/startup cells, run [39379119055](https://github.com/CalamityStriker/OEC/actions/runs/39379119055) and current-source run [39379246551](https://github.com/CalamityStriker/OEC/actions/runs/39379246551) passed, including the new notebook static tests 3/3.
- [ ] No new live model job was run by creating these notebook files. Gradio browser interaction, ACE-Step generation and MusicGen generation remain unverified by the current commit.
- [ ] The guarded E2E run 39320471955 attempt 2 concluded failure before inference: runner oec-1 found external PID 3347078 attached to all eight A100s. Artifact 12244625569 records BLOCKED; do not kill or signal the process. Wait for normal release by its owner.
- [ ] Follow-up: current-head FLUX→TRELLIS, live ACE-Step, cache/egress resolution for MusicGen, persistent audio service health/result tests, Qwen2-VL compliance decision, real HF manifest/chunk upload and independent read-after-write/reassembly/hash validation.
- [ ] Sync remains blocked: run [39379246680](https://github.com/CalamityStriker/OEC/actions/runs/39379246680) found `$HOME/OEC` has detached HEAD (empty `git branch --show-current`) and stopped before branch switch. It has not checked dirty status or changed files. Diagnose first, then fast-forward only after safely restoring the expected named branch.

- [x] Candidate validation follow-up closed: initial run 39378972546 remains a historical cell-count failure; notebook syntax/static contract subsequently passed in runs 39379119055, 39379246551 and 39379628368.

- [ ] A fail-closed A100 sync workflow/script has been added; it must run and prove OEC_A100_SYNC=PASS plus expected==actual SHA before claiming the long-lived $HOME/OEC checkout was updated. The workflow intentionally blocks on dirty checkout, wrong origin/branch, or divergent history.


## 2026-10-20 — Latest verification reconciliation

- **Static regression PASS on current source SHA `c79401c00182e94f3bc3f4d38109174f0662c7f5`:** [run 39379246551](https://github.com/CalamityStriker/OEC/actions/runs/39379246551), job [118484298605](https://github.com/CalamityStriker/OEC/actions/runs/39379246551/job/118484298605), hosted Ubuntu/Python 3.11. All 14 test commands completed successfully (102 test cases total as emitted in the logs); the new Gradio notebook suite passed 3/3 including code-cell AST parsing, explicit environment/API contract, and provider-stack isolation. The existing TRELLIS/FLUX/AudioCraft notebook JSON checks passed. This is static/contract evidence only, not live inference.
- **A100 E2E is still BLOCKED before inference:** [run 39320471955, attempt 2](https://github.com/CalamityStriker/OEC/actions/runs/39320471955), job [118480769324](https://github.com/CalamityStriker/OEC/actions/runs/39320471955/job/118480769324), failed closed because external PID 3347078 from the Biome server-components Python runtime still had CUDA contexts on all eight A100s. Artifact [12244625569](https://github.com/CalamityStriker/OEC/actions/runs/39320471955/artifacts/12244625569) is a pre-inference blocked report; no LTX inference, Qwen2-VL decision, upload, or read-after-write happened. The process was not killed/signalled.
- **Persistent A100 checkout sync not completed:** [sync run 39379246680](https://github.com/CalamityStriker/OEC/actions/runs/39379246680), job [118484298968](https://github.com/CalamityStriker/OEC/actions/runs/39379246680/job/118484298968), was correctly blocked because `git branch --show-current` in `$HOME/OEC` returned an empty string (detached HEAD). The sync script did not switch branches or change files. The script stops before testing whether that checkout is dirty, so do not assume it is clean.
- **Old failed static attempt retained as history:** run 39378972546 failed at a minimum-cell assertion for the two-cell AudioGen/MusicGen notebooks. Commit 64254d6 added the explicit environment markdown cells; the 3/3 notebook tests and complete static workflow passed in runs 39379119055 and 39379246551.

## Remaining acceptance gates

1. [ ] Recover the persistent `$HOME/OEC` checkout safely. Read-only diagnostics are complete: origin is correct; HEAD is `081aaf34f6379873bdc925d1dcf6b9c3d50349d3`; checkout is detached; expected local branch missing; 662 dirty/untracked entries; expected remote-tracking ref exists. Back up/review the dirty state, then use a reviewed named branch or separate clean worktree and require `OEC_A100_SYNC=PASS` plus matching expected/actual SHA.
2. [ ] Obtain normal release of all A100 contexts by the external process owner; do not kill/signal PID 3347078. Recheck `nvidia-smi` and fresh StorageManager state afterward.
3. [ ] Run current-head FLUX→TRELLIS on the assigned A100 and validate a generated PNG plus a reopened GLB.
4. [ ] Generate an actual ACE-Step FLAC in its isolated venv; no accepted music artifact exists yet.
5. [ ] Resolve MusicGen cache/egress only with current cache/network evidence; keep its CC-BY-NC model-weight limitation explicit.
6. [ ] For Kokoro, Whisper and Qwen3-ASR, launch one worker at a time after admission and check service ready/model_loaded, full job lifecycle, result bytes, logs, and environment isolation.
7. [ ] Complete actual Brain/LTX→Qwen2-VL accept/reject→upload-pending→HF chunk manifest/upload→remote read-after-write/reassembly/hash validation; current mock chunk tests are not live Hugging Face acceptance.
8. [ ] Complete OEC-Deploy clients/worker dispatch against the accepted APIs and supervised AudioGen/MusicGen CLIs; add typed job state, license metadata and artifact validation.
9. [ ] Audit existing Wan and other catalogued model workflows and environment/license/cache gaps before adding more model runtimes.


## 2026-10-20 — Persistent-checkout diagnostic and newest static run

- **Static suite PASS on commit `b6de4b086705caa30a1705039baf4ac49996725a`:** [run 39379628368](https://github.com/CalamityStriker/OEC/actions/runs/39379628368), job [118485509728](https://github.com/CalamityStriker/OEC/actions/runs/39379628368/job/118485509728). All 14 unittest command groups passed (102 test cases from logged summaries), including the new notebook suite (3/3); existing TRELLIS/FLUX/AudioCraft JSON checks passed. Still static/contract evidence, not inference.
- **A100 checkout diagnostics are conclusive enough to forbid automatic sync:** [run 39379628387](https://github.com/CalamityStriker/OEC/actions/runs/39379628387), job [118485509739](https://github.com/CalamityStriker/OEC/actions/runs/39379628387/job/118485509739). `$HOME/OEC` origin matches the intended repo, but the checkout is detached (`git branch --show-current` empty), current HEAD is `081aaf34f6379873bdc925d1dcf6b9c3d50349d3`, the intended local branch does **not** exist, and the tree has **662 dirty/untracked entries**. The expected remote-tracking ref exists. Sync correctly stopped before any branch switch/merge; no files were changed by the sync step. Do **not** run reset/clean, checkout, or bulk-overwrite. Review the local dirty state and recover on a reviewed branch/new checkout first.
- **Live media E2E remains blocked:** attempt 2 of run [39320471955](https://github.com/CalamityStriker/OEC/actions/runs/39320471955) found external PID 3347078 on all eight A100s. No inference/QA/upload occurred and no process was stopped.

## User-owned persistent checkout recovery steps (non-destructive)

Run these read-only commands on the A100 host. They list dirty paths but do not change the checkout:

```bash
cd "$HOME/OEC"
git status --short --branch --untracked-files=all
git rev-parse HEAD
git branch --all --no-color
git diff --stat
git diff --cached --stat
git ls-files --others --exclude-standard | sed -n '1,100p'
```

Review/backup those 662 entries first. Do not reset, clean or overwrite them. After preserving needed changes, make a reviewed named branch or a separate clean worktree for the OEC feature branch; only then retry a normal fast-forward and compare exact SHAs.


10. [ ] **Wan 2.1 (additional model found):** `pipeline_wan_video.ipynb` is an old `phase1`/Python 3.9 notebook with stored July outputs, no Gradio UI cell, GPU selection based only on free memory, and code that refers to `SYSTEM_DIRS` without importing/binding it. Treat it as unverified; refactor only after the available Wan dependencies/cache/environment are identified and a separate worker with GPU-ownership + StorageManager gates can be tested. Do not install Wan dependencies into `phase1` as a shortcut.


- [x] Latest sync on current branch head passed in [run 39380928762](https://github.com/CalamityStriker/OEC/actions/runs/39380928762), job `118489623737`: the dedicated `$HOME/OEC_feature_sync` worktree was cleanly advanced after StorageManager admission; actual SHA equals target SHA `132a8a5820a104ec27c14a87c9af3d4f84e83b98`. The original `$HOME/OEC` detached/662-entry working tree was preserved.


## Latest checkpoint — 2026-10-20, sync + static acceptance

- [x] Static/storage workflow passed at candidate source SHA `32e1a5f9203ed94214f4151c51e2504fe6589002`: [run 39380653548](https://github.com/CalamityStriker/OEC/actions/runs/39380653548), job 118488776376. 14 unittest command groups succeeded (102 cases in emitted summaries); Gradio notebook suite 3/3; existing TRELLIS/FLUX/AudioCraft notebook JSON checks passed.
- [x] Safe A100 sync workflow passed via the sibling worktree, not by changing the user-owned primary tree: [run 39380653563](https://github.com/CalamityStriker/OEC/actions/runs/39380653563), job 118488776455. Fresh StorageManager quota/capacity admission passed, actual/target SHA matched `32e1a5f9203ed94214f4151c51e2504fe6589002`, and local test checkout is `$HOME/OEC_feature_sync`.
- [ ] Still not a live model pass: A100 E2E run 39320471955 attempt 2 was blocked at GPU preflight by external process PID 3347078 on all eight A100s. No inference, live QA, HF upload or read-after-write ran.


## Latest verified current-branch checkpoint — 2026-10-20

- [x] Static workflow passed on branch head `132a8a5820a104ec27c14a87c9af3d4f84e83b98`: [39380928743](https://github.com/CalamityStriker/OEC/actions/runs/39380928743), job 118489623553. All test groups passed, including notebook JSON/Python syntax, environment-contract, and frontend backend-stack-isolation tests.
- [x] Local A100 feature-source sync passed to the same head: [39380928762](https://github.com/CalamityStriker/OEC/actions/runs/39380928762), job 118489623737. Actual/target SHA = `132a8a5820a104ec27c14a87c9af3d4f84e83b98`; worktree `$HOME/OEC_feature_sync`.
- [ ] Live model pipeline remains unaccepted as a whole: the last guarded E2E run blocked before inference due the external CUDA owner. Do not infer a live pass from static tests or the source sync.


## 2026-10-20 — Live acceptance retarget and actual Gradio callback testing

- [x] Retargeted live GPU workflows to the reported idle runner `oec-2`; they remain serialized through the common media/storage concurrency group. The former `oec-1` GPU preflight failure is preserved in history.
- [x] Added headless launch gating to the six model Gradio notebooks so their actual Gradio Interfaces can be launched by a smoke harness without public sharing.
- [x] Added `tools/run_gradio_model_notebook_smokes.py`: executes notebook code, launches the actual Gradio UI on loopback, checks HTTP 200 HTML, calls the real generation/transcription callback, validates WAV/FLAC headers or non-empty transcript, records artifact SHA-256 and closes the UI.
- [x] Hardened `tools/run_media_model_smokes.py` to select/pin an actually idle A100 for all four speech/music API providers based on process owner, memory use and GPU utilization; previously only ACE-Step was explicitly pinned.
- [ ] The new oec-2 Actions runs are triggered by this commit. Do not mark any model/UI/full-pipeline task passed until the run-specific artifacts show generated assets and the E2E report confirms QA→HF upload→remote read-back/reassembly/hash.


- [x] Corrected the stale E2E runner-name check to accept an explicit `OEC_EXPECTED_RUNNER`; current ordered oec-2 job sets it to `oec-2`. All GPU process ownership and VRAM checks remain fail-closed.
- [ ] Full end-to-end QA→HF acceptance remains pending; only mark pass after current oec-2 job produces the expected report and upload/read-back evidence.


## 2026-10-20 — Authorized storage recovery gate

- [x] Latest live suite proved source sync to oec-2 works, but the speech-model preparation job failed before model downloads because `recover_dead_storage_locks.py` is explicitly authorized only on `oec-1/scn30-mn`; it refused to run on oec-2.
- [x] Ordered suite corrected: a separate non-inference `recover-storage-locks` job runs that helper only on oec-1, while all model-generation jobs remain on oec-2. Downstream GPU tests are gated on successful storage recovery.
- [x] oec-2 now performs read-only checks for remaining `.storage_pause.lock` or `.storage_lease.json` and fails closed if either remains; it no longer tries unauthorized legacy-lock recovery.
- [ ] Verify the new authorized recovery gate on the next ordered suite. No live speech model was tested in the failed preparation stage.


## Live run evidence — 2026-10-20

- [x] The existing `pipeline_audiocraft.ipynb` headless run on `oec-2` generated an actual non-silent 3.0-second AudioGen WAV (96,078 bytes, SHA-256 `30b67f2c8f0dbfd017a319705091f607cada98f44f086bf5e545a0cff4893c92`); see [live suite run 39384873799](https://github.com/CalamityStriker/OEC/actions/runs/39384873799), artifact [12247855010](https://github.com/CalamityStriker/OEC/actions/runs/39384873799/artifacts/12247855010).
- [ ] The dedicated `pipeline_audiogen_gradio.ipynb` callback did not execute: Gradio failed its localhost check because inherited HTTP proxy settings intercepted loopback. Added NO_PROXY/no_proxy plus disabled Gradio analytics in the headless harness; next ordered run must confirm actual UI and callback.
- [ ] MusicGen did not generate an asset: its fail-closed selector raised `no eligible idle A100; no process was killed or signalled` before inference. This is a live GPU-availability block, not a model-generation result.


- [x] Corrected the new static assertion to match loop-based `NO_PROXY`/`no_proxy` setup rather than requiring direct assignments. The failure in [run 39385994021](https://github.com/CalamityStriker/OEC/actions/runs/39385994021) was a test assertion mismatch, not evidence the helper failed Python syntax checks. Re-run static acceptance before calling the fix validated.

## 2026-10-20 — Live acceptance findings and targeted fixes

- [x] Confirmed actual AudioGen inference on `oec-2`: the existing `pipeline_audiocraft.ipynb` produced a non-silent 3-second mono 16 kHz WAV (96,078 bytes; run-specific SHA is recorded in the Actions artifact). This is a model-generation pass, not a dedicated Gradio UI pass.
- [ ] Dedicated `pipeline_audiogen_gradio.ipynb` UI callback failed at Gradio startup. Runner logs identify a `gradio_client 1.3.0` JSON-schema bug: `get_type(False)` raises `TypeError: argument of type 'bool' is not iterable`. A process-local compatibility shim was added; it does not upgrade or mix Conda packages. Current candidate awaits rerun.
- [ ] Speech runtime bootstrap stopped before model inference because `prepare_media_runtime.py` hard-coded a 40 GB model-reserve floor even though StorageManager reported an existing 29.83 GB `.storage_reserve.bin` reserve in the 280 GB model allocation. Corrected to use the configured minimum and preserve the reserve; the change neither shrinks nor rewrites the reserve file.
- [ ] MusicGen generation did not start: the strict GPU selector found no eligible idle A100. The failure is retained; it will not bypass ownership checks or kill external processes. Added per-GPU admission diagnostics to identify why the next attempt is blocked.
- [ ] FLUX/TRELLIS, LTX sidecar, the live Gradio callbacks for ACE-Step/Kokoro/Whisper/Qwen3-ASR, and the joined LTX→Qwen2-VL→chunked HF upload/read-back pipeline remain unaccepted until successful run artifacts show actual generated outputs and verified hashes.
- [x] AudioGen live smoke now pins a verified idle physical A100 before importing Torch and records the physical index; no more implicit use of device zero in the smoke harness.


## 2026-10-20 — Live model acceptance pass/fail (Actions run 39401991943, source 9db29e82)

This section distinguishes model inference from UI acceptance. All results below came from the live Actions logs, not user-performed tests.

- [x] Source was synced non-destructively to `$HOME/OEC_feature_sync` on `oec-2`; expected and actual commit were both `9db29e82c8346ee245dfe7db6a527feb0dde2d99`. The unrelated, dirty `$HOME/OEC` checkout was not touched.
- [x] Authorized legacy-storage-lock recovery on `oec-1` completed successfully. The `oec-2` model job's read-only storage check then passed.
- [x] **AudioGen inference** in `phase1` passed on A100 physical GPU 4: 3.0-second mono 16 kHz WAV, 96,078 bytes, SHA-256 `c543c2e6a45a44a89f45d22a135ac5000b154f0025d2e93592a31c672589e7ba`, peak allocated VRAM 5.155 GiB. This was the existing `pipeline_audiocraft.ipynb`, not yet the dedicated UI's full button-event acceptance.
- [x] **MusicGen inference** in `phase1` passed on physical GPU 4: 3.0-second mono 32 kHz WAV, 96,000 frames, 192,044 bytes, SHA-256 `0cbb209e90f823ef309457410d72ac53899d378b5df6d19db476189d30e61d7b`, peak allocated VRAM 4.352 GiB, model snapshot `d3bd7b00761b78ad7a8a05145ee31e7832e9916c`. The workflow job nevertheless exited nonzero **after generation** because it copied `$OUT.info.json`; Python's `Path.with_suffix(".info.json")` writes `${OUT%.wav}.info.json`. That workflow path is corrected in the next candidate commit.
- [x] The Gradio AudioGen app launched and served HTTP 200. Its attempted callback failed because `tempfile.gettempdir()` resolved to the Actions runner temp directory, but the CLI explicitly requires `--scratch-output` below `/tmp`. Both AudioGen and MusicGen notebook scratch paths are being pinned to `/tmp`; the static test now enforces this.
- [x] Static/storage-admission regression suite passed on commit `d037bfff24f7ffef7bc2ac640071f6eb6d3dea71` in [run 39402803588](https://github.com/CalamityStriker/OEC/actions/runs/39402803588), including four dedicated GPU-admission tests and notebook/source checks.
- [ ] Kokoro, Whisper and Qwen3-ASR **inference is not yet accepted**. Their environment/cache preparation passed in the older run, but the shared smoke helper could not import root-level `oec_gpu_admission.py` when invoked from `tools/`; the import path has been corrected on the candidate branch, and a newer ordered run is queued.
- [ ] **ACE-Step is not accepted**: its download, service start, generation and UI steps were skipped because the upstream speech smoke step failed. It has not produced an acceptance artifact in the evidence reviewed here.
- [ ] **AudioGen Gradio callback and MusicGen Gradio callback** are still pending. The next candidate uses a real `gradio_client` `/predict` event request, not a direct call to the Python callback; UI acceptance must remain unchecked until that request and artifact validation pass.
- [ ] **FLUX → TRELLIS** was not accepted in the latest finished live run because an older GPU-selector test fixture encoded literal `\\n` text rather than newline-separated `nvidia-smi` rows. The fixture was corrected on the candidate branch; next live run must confirm PNG generation, GLB generation and both artifacts' validation.
- [x] A prior live run [39388844316](https://github.com/CalamityStriker/OEC/actions/runs/39388844316) passed isolated **LTX-2.3** video generation (validated 768×512 H.264 MP4, 242,547 bytes) and **TRELLIS.2** image-to-3D generation (validated GLB, 2,870,928 bytes), with the existing `phase1_ltx` and `phase2_3d` environments respectively. This evidence is for that run/commit; repeat acceptance on the newest candidate is still required.
- [ ] The joined Brain/LTX/Qwen2-VL QA → chunked Hugging Face upload → remote hash/read-after-write acceptance has not passed. No claim is made that `brain.py`, `qa_compliance_worker.py`, `hf_upload_daemon.py` and the full path are end-to-end validated yet.
- [ ] Cache purge safety remains unapproved for all model weights. `torch.cuda.empty_cache()` is not disk purge or model unload; no shared model cache is deleted automatically. After-generation cache purge requires model-specific resident second-inference and separate restart/reload tests; never touch `.storage_reserve.bin`.

### Remaining live acceptance order

1. Re-run the latest candidate on `oec-2`: complete the true Gradio HTTP/event callback for AudioGen/MusicGen, then Kokoro → Whisper and Qwen3-ASR Gradio callbacks.
2. Run ACE-Step's isolated model preparation, health/readiness check, real soundtrack generation and Gradio `/predict` request, only if the fresh StorageManager/quota gate permits required downloads; do not bypass or resize the reserve.
3. Re-run LTX/TRELLIS, then FLUX PNG → TRELLIS GLB on the current source and validate/reopen each file.
4. Run the joined QA → uploader → manifest/part upload → remote reassembly/hash read-after-write test against the already-configured Hugging Face dataset; no repository creation and no purge until remote verification succeeds.
5. Update this checklist with each run ID, source SHA, conda runtime, GPU, artifact dimensions/bytes, SHA-256, VRAM, runtime and exact failure reason. Merge to `main` only after the integrated acceptance is green and the branch/main divergence has been reconciled; do not blindly merge the current heavily diverged branch.

## Media readiness and deployment integration — 2026-10-20

- [x] Added a read-only readiness CLI at tools/check_media_service_readiness.py to report API health, model-loaded state, runtime modules and cached checkpoint presence separately. It explicitly marks AudioGen and MusicGen NOT_EXPOSED because they lack a supervised HTTP job API.
- [x] Added OEC_Deploy integration documentation at docs/OEC_DEPLOY_MEDIA_SERVICE_READINESS.md: provider ports/environments, live readiness semantics, HTTP job lifecycle, and SSH-tunnel access while keeping sidecars loopback-only.
- [x] Aligned oec_service_manager.py to the shared fail-closed GPU admission policy and added provider-specific minimum-free-VRAM floors.
- [x] Fixed the FLUX test fixture (memory.total omitted), QA E2E handoff comparison (canonical DB status is PENDING; PENDING_UPLOAD is the QA result marker), AudioGen/MusicGen explicit /tmp paths, and MusicGen metadata-copy path.
- [x] Changed the ordered live workflow so speech failure no longer silently skips the independent ACE-Step steps. A final gating step still fails the job if speech or ACE-Step fails.
- [ ] These current candidate changes need exact-head static and A100 Actions validation. Do not report ACE-Step, speech or persistent endpoints ready before the next results prove them.
- [ ] AudioGen/MusicGen remain unavailable to OEC_Deploy via HTTP until supervised job APIs are added, even though prior real CLI inference generated WAV files.
- [ ] Run the new readiness command on the persistent OEC host after starting each service. Smoke sidecars launched inside Actions stop at the end of their job.
## Dedicated AudioGen Gradio event acceptance — 2026-10-20

- [x] On source SHA a558d2d52a5f6f93afabd5c0aaa14f6e721cf844, run 39404646877 passed the dedicated AudioGen Gradio test: loopback UI HTTP 200; a real gradio_client event request completed; generated WAV validated (96,044 bytes, 3 seconds, mono 16 kHz; SHA-256 02341fb8a7c71886fd8b837cf1f6558c0d26b6a8f5cce45949cdade5e5ceda58). Physical GPU 4, peak allocated 5.155 GiB.
- [x] The test actually exercises the Gradio HTTP/event API, not a direct Python callback call. This confirms the /tmp scratch-path fix.
- [ ] The same old run's Kokoro UI reached HTTP 200 but its event call failed because Gradio 6.0.1 exposes a different endpoint name; Whisper/Qwen3-ASR were then blocked because no Kokoro WAV was produced. The harness now uses the one-interface function index (fn_index=0), awaiting the new exact-head retry.
- [ ] MusicGen's current live job was still generating when this note was written; do not call its dedicated Gradio acceptance passed until the artifact/report is retrieved.
- [ ] ACE-Step remains unaccepted; the current candidate now runs ACE independently of speech failure, then applies an explicit final gate.