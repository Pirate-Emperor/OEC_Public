
# OEC Active TODO


## 2026-10-20 — New Gradio clients and live E2E retry

- Repository inspected: CalamityStriker/OEC, branch fix/media-stack-supervision-20261019, parent source 2ca832a5e814d5f8bce43617ca04d2f7fdfee682.
- Added dedicated model UI notebooks for AudioGen, MusicGen, ACE-Step, Kokoro, Whisper Turbo and Qwen3-ASR, plus a static notebook source-policy test. Each notebook declares its UI kernel and inference environment. Speech and ACE-Step UI clients call the existing loopback API and do not import their backend ML packages.
- A new model/environment and OEC-Deploy integration runbook is being committed with the notebook set. Initial CPU contract run 39378972546 FAILED at the minimum-cell assertion; the Python parser did not reach AudioGen/MusicGen in that attempt. Fixed in commit 64254d6 by adding environment/startup markdown cells. Full static workflow and new notebook tests passed 3/3 in runs 39379119055 and 39379246551.
- E2E run 39320471955, attempt 2, job 118480769324, ended FAILURE at the GPU-ownership gate. A100 PID 3347078 (external Biome server-components Python process) was attached to all eight visible A100s; usage ranged from about 974 MiB to 8,986 MiB per device, and the runner explicitly refused overlap. E2E artifact 12244625569 (1,758 bytes) confirms this is a pre-inference block: no LTX output, no Qwen2-VL decision, no actual HF upload and no read-after-write occurred.
- Do not kill/signal PID 3347078 or launch another heavy GPU job against it. The user removed the Actions minutes restriction only; GPU ownership and StorageManager admission are still mandatory.
- Remaining: inspect candidate Actions static result, safely sync branch into the persistent $HOME/OEC checkout after local status checks, live Gradio tests for every UI, current-head FLUX→TRELLIS, ACE-Step generation, MusicGen cache/egress, full LTX→QA→chunked HF upload/readback and deployment client integration.




## 2026-10-19 — Current live checkpoint (23:33 IST)

- **Delivery timeout:** current GitHub reads and run artifacts are accessible; no rollback was observed. A timeout alone does not indicate repository damage. Exact client-side streaming cause is not visible via GitHub APIs.
- **Delivery target:** user asked to finish by 2026-10-21. Authoritative original 15-day start/deadline remains unverified; do not reset or guess it.
- **Branch/current state:** `fix/media-stack-supervision-20261019`; latest tracker commit `48e13fbf13871d31934e90d81ac011d09b8622a7`; latest tested code SHA `80cc89480ee79f18d1ec7c101f97cfc310379ed1`. No merge to `main`.
- **PASS — current full static suite:** [run 39300850953](https://github.com/CalamityStriker/OEC/actions/runs/39300850953), job [118225345013](https://github.com/CalamityStriker/OEC/actions/runs/39300850953/job/118225345013), source SHA `80cc89480ee79f18d1ec7c101f97cfc310379ed1`, hosted runner/Python 3.11.17. **96 tests passed**, including six new E2E acceptance contract tests; source compilation and all four notebook JSON checks (16/15/10/6 cells) passed; no ResourceWarning.
- **LIVE E2E attempt — BLOCKED before inference as designed:** [run 39300850928](https://github.com/CalamityStriker/OEC/actions/runs/39300850928), job [118225345452](https://github.com/CalamityStriker/OEC/actions/runs/39300850928/job/118225345452), runner `oec-1`, source SHA `80cc89480ee79f18d1ec7c101f97cfc310379ed1`, concluded FAILURE at the guarded run step with exit code 3. The guard found external PID `3347078` (`/nlsasfs/home/lmedge/rahkus/OEC/oec_deploy/v1/Biome/server-components/.venv/bin/python`) attached to all eight A100s. Observed GPU memory usage: 8194 / 1072 / 974 / 1046 / 970 / 1212 / 1126 / 8986 MiB. The harness exited before StorageManager/HF preflight or model inference, leaving those checks unexecuted. Do not kill/signal this owner process; rerun only after normal release and fresh GPU admission.
- **E2E artifact proves fail-closed behavior:** [artifact 12211286861](https://github.com/CalamityStriker/OEC/actions/runs/39300850928/artifacts/12211286861), SHA-256 `662beaa9a52c82274a0b4997dd9a7995f94f3da1a904f9fffd890cbf8c339add`, 1758 bytes. Its `pipeline-report.json` is `BLOCKED`, `process_kill_attempted=false`, `shared_queue_used=false`, `remote_dataset_created=false`. No LTX/Qwen2-VL inference, no real HF write, and no remote read-after-write occurred in this attempt.
- **PASS — visual sidecar workflow:** [run 39278268411](https://github.com/CalamityStriker/OEC/actions/runs/39278268411) concluded success. Artifact [12198722285](https://github.com/CalamityStriker/OEC/actions/runs/39278268411/artifacts/12198722285) was downloaded/reopened: TRELLIS GLB 2,775,928 bytes SHA-256 `e7a1a970edae002596a80fa47b19ad87e96ad82a8dfa3d4523ad65167435e875`; mesh reopened with 48,806 vertices / 95,566 faces, **not watertight**. LTX H.264 MP4 242,547 bytes SHA-256 `5d7d54de4354936f66867fecd19d20c0ab6972b5d997ca00c145ab0c1e54ec51`, 768×512, 2.083333 s, local ffprobe pass. This proves sidecar APIs/artifacts, not joined Brain→QA→upload.
- **PASS — mocked resumable chunk uploader:** the 96-test suite carries forward `--once --asset-id ID --chunk-oversize` protocol checks: bounded parts, full/part SHA-256, verified-existing-part skip, failure rollback/source retention, manifest-last publication, and reassembly against a fake Hub. **Not yet tested against a real HF target** or real remote consumer.
- **Latest ACE-Step status:** [run 39278145617](https://github.com/CalamityStriker/OEC/actions/runs/39278145617) ended FAILURE after Kokoro/Whisper/Qwen3-ASR smokes passed and ACE-Step runtime/checkpoints passed; music generation was refused due no idle A100. No music artifact. Combined FLUX→TRELLIS [run 39271901007](https://github.com/CalamityStriker/OEC/actions/runs/39271901007) remains blocked at its safe GPU-admission gate, no PNG/GLB from that attempt; MusicGen remains incomplete-cache/proxy `No route to host` blocked and CC-BY-NC.
- **Whole pipeline remains unaccepted:** no loaded Qwen2-VL pass/reject decision; no real HF upload receipt/read-after-write; no real remote-resume test; no sustained Brain→LTX worker→QA→archive/upload→OEC-Play path; no live OEC-Play health test. The new guarded E2E job is ready, but the external GPU owner must release its process normally.
- **Workflow failures/history:** E2E attempts `39300485256` and `39300507195` failed before jobs (zero jobs, workflow-validation issue; no side effects); after moving the `runner.temp` expression to step-level env, run `39300850928` created a real oec-1 job and failed closed on GPU ownership. All these failures remain in history; do not report them as green.
- [ ] **Immediate next gate:** recheck live A100 ownership and StorageManager on `oec-1`. Do not kill/signal PID `3347078`; ask its owner/operator to release it normally. Then rerun guarded E2E and capture GPU, StorageManager, HF auth/repo status, Qwen2-VL decision, upload receipt and remote readback.
- [ ] If GPU is unavailable, continue independent deliverables: rebuild/visually inspect Report_Docs report/PPT/poster; recheck OEC-Viewer diagrams and PaperDock source/compile state. No fresh academic deliverable rebuild/page-by-page visual QA has been performed in this work cycle.
- [ ] Verify real chunk-manifest remote reassembly through a separate consumer after a successfully authorized one-row upload. Do not use dummy media or create a new HF dataset repo without explicit scope approval.

## 2026-10-18 — Latest live acceptance, visual sidecar fixes, and full-pipeline follow-up

- [x] **AudioGen is completed and accepted.** A100/phase1 run [39135140674](https://github.com/Killer4K-N/OEC/actions/runs/39135140674) executed notebook code cells 1–5, hit the existing `facebook/audiogen-medium` cache, loaded the model and generated a valid 3-second mono 16 kHz WAV (96,078 bytes). Generation took 20.763 s; peak allocated VRAM was 5.155 GiB. The acceptance report records SHA-256 `d4cd48e45890ec2668321a6dfbf95b3e57f3541b9d7cb414afe484cd349805cc`. Artifact: [run output and logs](https://github.com/Killer4K-N/OEC/actions/runs/39135140674/artifacts/12140085687).
- [x] Fixed the AudioGen headless harness import defect by adding the repo root to `sys.path`. The final run is PASS; earlier missing-`core_config` runs and the superseded cancellation remain recorded as debugging history, not as the final status.
- [x] Speech pipeline acceptance on A100 run [39135140660](https://github.com/Killer4K-N/OEC/actions/runs/39135140660): Kokoro-82M TTS, Whisper-Turbo and Qwen3-ASR-0.6B each passed; 3 passed, 0 failed, ACE-Step skipped. Whisper and Qwen matched on one fixed English acceptance clip only.
- [x] Fixed Lustre soft-quota `*` parsing and confirmed the focused test suites in [run 39142266535](https://github.com/Killer4K-N/OEC/actions/runs/39142266535): 10 StoragePolicy tests + 7 quota-snapshot tests passed. Live StorageManager admission used an explicit active grace period and observed hard-limit headroom; no directory-only bypass was enabled.
- [x] Added `docs/PIPELINE_DAEMONS_AND_MEDIA_SERVICE_RUNBOOK.md` with the Brain queue batching semantics, production daemon commands, sidecar commands, API health checks, and the OEC-Deploy read-only investigation notes.
- [x] Fixed the LTX sidecar to check only the configured `outputs` storage target before creating its queue/runtime, and added private traceback logging for runtime-load errors. Added regression checks. The old LTX failure came from passing unconfigured logical areas `inputs`/`cache` to StorageManager, not from a missing model checkpoint.
- [x] Reduced the synthetic TRELLIS acceptance request from 1024 to 512 texture size and from 30,000 to 5,000 target faces so the live smoke tests the basic API/artifact path with a cheaper fixture. Production defaults are unchanged.
- [ ] **TRELLIS and LTX live JSON sidecar acceptance is still open.** Prior cache-only run [39142905429](https://github.com/Killer4K-N/OEC/actions/runs/39142905429) saw TRELLIS stay at 5% and time out without a validated GLB; LTX failed on the unconfigured storage-area check, which is now fixed in source. The old run [39143306660](https://github.com/Killer4K-N/OEC/actions/runs/39143306660) was still running the pre-fix revision at the last status check; latest-revision rerun [39148645009](https://github.com/Killer4K-N/OEC/actions/runs/39148645009) is queued/pending. Do not claim both providers are working until the current run returns validated GLB and MP4 artifacts.
- [ ] ACE-Step music generation remains untested because `acestep` is not installed in any of the checked existing environments. Prepare a separate, compatible runtime and pass StorageManager admission before any dependency/model setup; do not upgrade shared Conda stacks to force a pass.
- [ ] Run the complete sustained Brain → queue file → LTX worker → QA/compliance → HF upload path in the assigned multi-GPU allocation after inspecting existing process/GPU state and validating each component's environment. Unit/mock tests and individual model acceptance do not prove that all production daemons were started together.
- [ ] Verify the actual OEC-Play server from its existing allocation with `/health` and `/api/media-services`; this chat did not access a live server shell or assert it is online. OEC-Deploy was **not edited**. The AppImage source/build validation passed, while GUI automation run [39148052034](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39148052034) failed its DOM hero-text assertion although the uploaded screenshot visibly shows the home hero; DevTools screenshot capture timed out. Follow the diagnostic steps in the runbook, without editing OEC-Deploy.


## 2026-10-18 — Live speech services and AudioGen notebook follow-through

- [x] **Live speech pipeline accepted on the assigned `oec-1` A100 runner** in [Actions run 39135140660](https://github.com/Killer4K-N/OEC/actions/runs/39135140660). The job completed successfully. The API/validation and media-service CPU/mock suites passed **10/10 + 10/10**.
- [x] Fresh quota telemetry is now parsed correctly when Lustre marks the used-KiB number with an asterisk. Strict StorageManager admission passed using the explicitly active soft-quota grace period and available hard-limit headroom; no directory-only fallback was used.
- [x] The downloader verified cached weights for Kokoro-82M, Whisper-Turbo, and Qwen3-ASR-0.6B. No model-weight download was needed for those three providers.
- [x] Isolated `oec-audio-py311` runtime checks and setup completed under StorageManager control; no shared `phase1` packages were upgraded.
- [x] Kokoro speech synthesis passed on CUDA: generated a valid 24 kHz mono WAV, 4.7 seconds, 225,644 bytes; inference time 24.328 seconds; service startup plus inference 136.43 seconds.
- [x] Whisper-Turbo transcription passed on CUDA: it transcribed the generated acceptance audio to valid text, 57 bytes, one segment; inference time 11.851 seconds; startup plus inference 46.90 seconds.
- [x] Qwen3-ASR-0.6B transcription passed on CUDA: valid text, 57 bytes; it matched the Whisper output for this single test clip; inference time 28.711 seconds; startup plus inference 52.57 seconds.
- [ ] ACE-Step music generation remains **SKIPPED**: none of the checked existing environments had the `acestep` package. The workflow deliberately did not install it into the shared environments.
- [x] AudioGen notebook harness fix: the repo root is now added to `sys.path` before executing the notebook. The subsequent run reached code cell 4 after cells 1–3 passed, but run [39134976949](https://github.com/Killer4K-N/OEC/actions/runs/39134976949) was cancelled by the newer quota-parser commit before a model-load or WAV-acceptance marker was captured.
- [ ] Latest AudioGen retry [39135140674](https://github.com/Killer4K-N/OEC/actions/runs/39135140674) was still queued on `oec-1` at the time of this update. Do not count notebook inference or AudioGen output as passed until that run produces a complete acceptance report.
- [ ] Run the new `test_live_lustre_quota_parser_accepts_soft_quota_asterisk_marker` regression method in a focused runner-side suite. The regression source is present, but it has not yet been confirmed by that suite.
- [ ] After AudioGen notebook acceptance, optionally connect it as a separate service provider; the current audio API still exposes Kokoro, Whisper, Qwen3-ASR and ACE-Step, not AudioGen.


## 2026-10-18 — A100 model downloads and utilization

- [x] Added tools/prepare_media_models.py to read live storage_manager.py --status, tail the manager log, inventory model cache, inspect existing environments, aggregate-preflight model storage and download supported checkpoint groups with managed writes.
- [x] Fixed HF cache verification to validate snapshot symlinks remain inside the repo cache and lead to nonempty weights. ACE-Step startup now verifies DiT, VAE, text-encoder and selected LM weight parts and checks both handler initialization results.
- [x] Local bundle validation after these changes: Python compile passed; 19/19 CPU/mock tests passed. No real models were loaded.
- [ ] Still requires execution on A100: run python tools/prepare_media_models.py status, then env-audit, then plan --preflight; only if aggregate preflight is positive, run download --model all. The current download plan estimates 21 GB for all groups plus a 2 GB positive headroom margin.
- [ ] User-reported model directory: 209 GB / 280 GB used with about 71 GB nominal free and a 40 GB positive reserve handled by user-run StorageManager. The assistant cannot directly read or operate A100 from this session because no remote-shell connector or A100 filesystem mount is available; no daemon was started.
- [ ] After weights arrive, select only existing environments that pass env-audit; install no packages into shared environments blindly. Run one live inference per chosen model and validate the artifact. Test purge/reload only after first-output acceptance.


## 2026-10-18 — Audio model services and explicit cache purge

- [x] Added separate cache-first audio provider service for ACE-Step 1.5 (music), Kokoro-82M (English TTS), Whisper (transcription), and Qwen3-ASR 0.6B (multilingual transcription). Proposed loopback ports: 7870-7873.
- [x] Added model-specific cache target inventory and runtime locks. The purge command targets only the chosen model's exact subdirectory under configured AIEROS_MODELS_DIR and calls OEC DiskPurgeManager; it refuses unsafe paths and active/ambiguous runtime locks.
- [x] Aligned all media service state and temporary job inputs with StorageManager's configured outputs target. Only weights/checkpoints are placed under the configured models target; this avoids unconfigured cache/inputs admission areas.
- [x] Added bounded audio upload validation and CPU/mock tests. Local result: py_compile PASS; unittest suite 17 passed, 0 failed, 0 errors.
- [x] Recorded operator-supplied quota baseline: 2.14 TB occupancy / 2.15 TB soft / 2.25 TB hard; reported Actions usage 1836 minutes. No workflow was triggered, and no StorageManager daemon was started by the assistant.
- [ ] Operator to inspect cache status with the already-running StorageManager and verify that the intended isolated environments exist before starting a service. Proposed environment names are examples only; no package install or env provisioning occurred.
- [ ] After live model loading and one valid artifact per model are confirmed, measure runtime/VRAM and evaluate music/TTS/transcription quality. Test exact-cache purge with resident inference and then separate clean restart/reload before enabling any purge policy.
- [ ] Live GPU inference, model download, dependency installation, shared-cache purge, direct A100 StorageManager check, and fresh checkout execution have not been run.


## 2026-10-18 — TRELLIS/LTX media sidecars and model-cache policy

- [x] Audited current model/cache code and the OEC-Deploy media-service contract. Confirmed the disk purger deletes Hugging Face cache folders; it does not unload model tensors from VRAM. TRELLIS and FLUX retain cache by current policy. The established multi-node LTX launch uses `--no-purge`; leave production policy unchanged until post-purge repeated-inference checks pass.
- [x] Added cache-only controls to the LTX loader on this feature branch: `allow_download=False` prevents missing model files from being downloaded, and `preserve_cuda_visible_devices=True` preserves the scheduler allocation. Legacy worker defaults are unchanged.
- [x] Added `tools/media_services/common.py`, `trellis_api.py`, `ltx_api.py`, `__init__.py`, and `tests/test_media_service_api.py` on this isolated feature branch. The APIs use bounded queues, loopback-only bind, StorageManager-gated writes, job status, temporary-input cleanup, result metadata and GLB/MP4 validation. The ZIP remains a convenient snapshot; live models and OEC-Play integration are not verified.
- [x] Local tests: `python -m py_compile tools/media_services/common.py tools/media_services/trellis_api.py tools/media_services/ltx_api.py tests/test_media_service_api.py` passed; `python -m unittest discover -s tests -p 'test_media_service_api.py' -v` passed 8/8 CPU/mock tests (2026-10-18). No model weights were downloaded, no GPU inference was run, no shared cache was purged, and no Actions workflow was triggered.
- [ ] Fresh-checkout rerun remains open: the local CPU/mock suite passed 8/8, and branch files were read back via the GitHub connector, but direct `git clone` failed because DNS/network access was unavailable in this session. Do not report the remote branch itself as test-passed.
- [ ] OEC-Play integration remains gated by the companion `hpc-dgx-deployment` CI: latest run [39106225707](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39106225707) failed TypeScript checks in `MediaServicesPanel.tsx` (TS2677 at line 145 and TS18047 at line 149). This task is scoped to OEC; do not edit/push OEC_Deploy here or trigger another workflow.
- [ ] Add process-level timeout supervision for a GPU inference call that hangs indefinitely. Current prototype detects a timeout only after the provider call returns; it cannot safely interrupt an in-process CUDA call. Do not configure OEC-Play URLs until both real model services pass health and authorized live artifact checks.
- [ ] In a later authorized allocation, run the cache-purge acceptance sequence per model: record bytes, full-load marker, first artifact, delete only that exact model cache folder, generate again with the same resident pipeline, reopen output, then test a clean restart/reload. Do not enable purge by default before that evidence.
- [ ] Candidate model shortlist: ACE-Step 1.5 for music generation; Kokoro-82M for lightweight English TTS; SenseVoice/Whisper for speech input; Hunyuan3D-2.1 as a later TRELLIS baseline. MusicGen/AudioGen remain research-only until the CC-BY-NC model-weight terms are acceptable for the intended product.
- [ ] Remaining project deadline could not be recovered from an authoritative start/deadline record during this pass; do not restart or invent the original 15-day clock.

## 2026-10-16 — latest notebook acceptance and frozen-weight audit

- [x] Executed the actual final UI cells on designated \`oec-1\` in [run 38912593770](https://github.com/Killer4K-N/OEC/actions/runs/38912593770): FLUX-only generation, TRELLIS-only GLB generation, combined-notebook FLUX generation and combined TRELLIS app startup. Artifact: [12052395126](https://github.com/Killer4K-N/OEC/actions/runs/38912593770/artifacts/12052395126).
- [x] Recorded standalone TRELLIS GLB size 5,457,384 bytes, SHA-256 \`7db7600e9dd9de6c1549eaf06f08cd687a55e8d62465754b426c521501ed9183\`, 51,658 vertices / 97,935 faces; run time 337.646 s. FLUX-only PNG generation took 8.839 s and the combined-notebook FLUX cell took 10.012 s.
- [x] Confirmed precise scope: all modes were cache-only/local scratch; the combined TRELLIS notebook was startup-only (HTTP 200), not a generate_3d call. Do not describe this as a combined end-to-end image-to-mesh result or production integration.
- [x] Logged the storage admission regression run 38912593912 as passing; no quota snapshot publication, reserved/shared storage mutation, package install, model/data download or training was performed in this reporting pass.
- [x] Re-read [frozen-weight audit 38924202279](https://github.com/Killer4K-N/OEC_AireOS_Freezed/actions/runs/38924202279): audit execution passed but semantic readiness remains BLOCKED; PEFT missing, fresh numeric quota unavailable, managed models directory WARNING / group soft-quota overage, model/license/task and dataset provenance/schema/split approvals unresolved; \`training_started=false\`, \`downloads_started=false\`.
- [ ] Keep all write/download/training gates closed until fresh authoritative quota and managed storage NORMAL state are verified through the sanctioned storage-manager interface. Never access \`.storage_reserve.bin\` directly.
- [ ] For the combined TRELLIS notebook, exercise \`/generate_3d\` through the combined UI with exact input/output hashes, mesh reopen, timeout and cleanup checks; then test the intended FLUX→TRELLIS request chain end-to-end before making an integration claim.
- [ ] Resume frozen-weight work only after the dedicated environment has PEFT and exact model/license/task plus dataset provenance/schema/group-safe split approvals, then perform baseline, one-batch adapter gradient/frozen-tensor assertions, checkpoint round-trip/resume and held-out evaluation.

## 2026-10-16 — Lustre soft/hard quota schema and admission hardening

- [x] Verified the dedicated `oec-freeze` read-only probe [run 38898669614](https://github.com/Killer4K-N/OEC_AireOS_Freezed/actions/runs/38898669614): 8/8 probe/parser tests passed. Captured group usage above soft quota with hard-limit headroom and grace; this is time-stamped evidence, not a current quota guarantee.
- [x] Extended the isolated OEC branch [fix/lustre-soft-hard-quota-snapshot-20261016](https://github.com/Killer4K-N/OEC/tree/fix/lustre-soft-hard-quota-snapshot-20261016) with structured quota schema v2, preserving soft/hard limits, grace, quota identity and provenance separately.
- [x] Hardened structured-snapshot reading: schema/identity/limits/source must be valid, limits must be non-negative integers with at least one configured limit, malformed JSON roots reject, and hard headroom never authorizes writes when usage exceeds soft.
- [x] Validated on hosted CI [run 38903458777](https://github.com/Killer4K-N/OEC/actions/runs/38903458777) / [job 116981112079](https://github.com/Killer4K-N/OEC/actions/runs/38903458777/job/116981112079): 47 tests passed, 0 failed; compilation and four notebook JSON/Python-cell checks passed.
- [x] Opened [draft PR #12](https://github.com/Killer4K-N/OEC/pull/12). It remains unmerged/unpublished to runtime; main only receives tracking-file updates in this cycle.
- [ ] Keep snapshot publication and all model/data/output writes blocked until a new authoritative quota sample is obtained, the schema/policy is reviewed and deployed under an explicit decision, and admission uses the structured soft/hard/grace fields. Never infer user quota from filesystem free-space output or fabricate values for the snapshot.
- [ ] After storage admission is safe, return to OEC-Viewer's frozen_ft acceptance contract: approve exact model/license and source-specific dataset/provenance/splits; only then install required PEFT dependencies and run the real baseline/LoRA smoke with exact parameter, gradient, frozen-state, checkpoint/resume and held-out evaluation evidence.

**Last updated:** 2026-10-18T12:36:53.201+05:30 (Asia/Kolkata)
**Policy:** This is the single consolidated TODO list. Update this file at the end of every OEC work prompt; keep day-by-day history in `changelog/CHANGELOG-YYYY-MM-DD.md`. Record each meaningful test/experiment in `test.json` and only major milestones in `result.md`.
## 2026-10-15 20:29 IST — cluster coordinator, CLI help and notebook GPU isolation

- [x] Added per-action and per-service `--help` documentation and regression tests for all local services and cluster actions in `tools/oec_service_manager.py`.
- [x] Added `tools/oec_cluster_services.example.json` with the `ltx-3node`, `mixed-stack`, `flux-image-once`, `flux-trellis`, and `trellis-folder` profiles. The coordinator supports one-command SSH fan-out, status, log collection and owned-service stop; it does not deploy/sync code. Host aliases and paths remain operator-local.
- [x] Fixed the combined notebook to keep TRELLIS in the Jupyter kernel while launching FLUX Gradio in a separate managed process/GPU (default physical GPUs 0/1, ports 7862/7863); updated stale tests for this execution architecture.
- [x] The final current-head hosted CI [run 38761087455](https://github.com/Killer4K-N/OEC/actions/runs/38761087455) passed **86/86 tests**, Python compilation, and JSON/Python-cell validation of all four notebooks after aligning the example per-node Conda paths with the `source Conda/bin/activate` project-root layout. Earlier run [38760561720](https://github.com/Killer4K-N/OEC/actions/runs/38760561720) passed the same suite before that config-template adjustment.
- [ ] OPEN — the cluster profile is validated via config/help/plan/dry-run only. Actual three-node SSH preflight/start/status/stop remains unrun on the user's hosts.
- [ ] OPEN — actual browser/Gradio submissions, live LTX/QA runtime and existing-image-folder TRELLIS GPU inference remain unrun. Earlier single-image combined cache-only inference [38725376076](https://github.com/Killer4K-N/OEC/actions/runs/38725376076) is prior evidence, not proof of these new UI/folder paths.
- [ ] OPEN — authoritative fresh quota data remains missing. Do not download missing model/dependency files or write managed shared outputs until fresh admission passes.

## 2026-10-15 evening — supervised background pipelines and notebook follow-through

- [x] Audited the supplied LTX launch/kill commands and documented why compound background shells and broad `pkill -9 -f "python"` are unsafe for shared work nodes.
- [x] Added `tools/oec_service_manager.py` and usage guide `docs/background-pipelines.md` on [review PR #11](https://github.com/Killer4K-N/OEC/pull/11): LTX control/worker/QA, FLUX-only background image/UI, TRELLIS folder batch/UI, combined FLUX-by-default, and combined existing-image-folder mode.
- [x] Fixed LTX worker source so `--no-purge` suppresses distributed purge and associated synchronization/barriers; added GPU-ID validation/default GPU-0 reservation and explicit QA `--gpu`.
- [x] Added TRELLIS `generate-batch` input-folder mode and combined `--source-mode images --image-dir ... [--recursive]`; the default combined source remains FLUX.
- [x] Cleared saved execution outputs and execution counts on the three relevant notebooks, preserving private Gradio defaults: FLUX-only 7864; TRELLIS-only 7862; combined TRELLIS 7862 and FLUX 7863.
- [x] Hosted CI [run 38743800209](https://github.com/Killer4K-N/OEC/actions/runs/38743800209) passed 78 tests before final QA GPU-isolation hardening. Final current-head CI [run 38744924124](https://github.com/Killer4K-N/OEC/actions/runs/38744924124) again passed all 78 tests, py_compile and JSON/Python-cell validation for all 4 notebooks after verifying QA `CUDA_VISIBLE_DEVICES` is set before Python starts. Earlier run [38743502455](https://github.com/Killer4K-N/OEC/actions/runs/38743502455) failed on an outdated TRELLIS CLI test expectation; [38743634536](https://github.com/Killer4K-N/OEC/actions/runs/38743634536) failed on syntax in a new test. Both defects were fixed and their causes retained in the changelog/test ledger.
- [x] Refreshed the daily changelog, `test.json` (48 experiment records), results and index with this evidence. All source/workflow/notebook changes remain on PR #11; main received tracking files only.
- [ ] OPEN — run a live LTX controller + worker smoke on chosen compute nodes, using `nvidia-smi` first and launching QA separately on an unclaimed GPU. Verify service status/logs, safe stop, and one known test job end-to-end. Hosted static CI is not live LTX validation.
- [ ] Startup safety before rollout — the supervisor only tracks services it launches itself. Review exact per-node assignments and unmanaged jobs before launching any profile. Before starting its services, inspect any existing manually launched daemons and gracefully stop only exact owned PIDs if they must be replaced; do not start duplicates and do not use broad `pkill` patterns.
- [ ] OPEN — launch each FLUX, TRELLIS and combined Gradio UI on a selected cached-environment host, establish SSH tunnels, and submit one small generation per UI; live browser/submission testing was not run in hosted CI.
- [ ] OPEN — test a small existing-image folder with TRELLIS batch and combined `--source-mode images`; inspect each real GLB after inference. Static tests validate the batch code/path but do not prove folder inference on GPU.
- [ ] OPEN — fresh authoritative quota telemetry is still missing. Do not download missing model/dependency files or write managed shared outputs until admission succeeds.
- [ ] OPEN — evaluate any `brain_config.json` prompt/rule or profitability changes in controlled experiments with QA acceptance/rejection, runtime/cost and downstream conversion measures before changing prompts. No speculative prompt change was made.
- [ ] Policy — do not merge PR #11 source changes to `main` without explicit permission. No live queue, process or reserve-file mutation was done during this task.

## 2026-10-14 — quota telemetry and live-checkout diagnosis
- [x] Verified GitHub state: OEC `main` is `82346c0753e139b92240f53734eb48d2113ed9ad`; `fix/trellis-gradio-notebooks-20261011` is `2543b26d2888e667c6443c984259f84ac5b6c142` (111 ahead, 0 behind). No main-branch change or merge.
- [x] Reviewed failed remediation [run 38175212786](https://github.com/Killer4K-N/Connector_1/actions/runs/38175212786). Main job blocked on missing fresh quota; separate connector-2 QA recovery failed with `scontrol: stepd_available: Couldn't find nodename` and `sacct` connection refusal to `localhost:6819`.
- [x] Created the read-only Connector_1 diagnostic on [branch `diagnose/oec-storage-telemetry-20261014`](https://github.com/Killer4K-N/Connector_1/tree/diagnose/oec-storage-telemetry-20261014), commit `70d9000ba48cfdd6a6413276d7a4d4fe2888ad17`. [Run 38555689884](https://github.com/Killer4K-N/Connector_1/actions/runs/38555689884) succeeded, job `115824133792`; JSON artifact [11888967874](https://github.com/Killer4K-N/Connector_1/actions/runs/38555689884/artifacts/11888967874).
- [x] The probe confirmed the configured quota snapshot is **MISSING**, `quota_check` is **NOT_FOUND** on `scn17-mn`, and the resolved model directory `/nlsasfs/home/lmedge/rahkus/aireos_models` is on shared Lustre. Free-space measurement was 9,383,140,028,837,888 bytes (8,738,730.13 GiB); this does not establish user/project quota. Keep fresh-quota admission fail-closed.
- [x] GPU visibility showed two A100-SXM4-40GB devices. This was not an attention probe or inference test.
- [x] The live OEC checkout was observed at `081aaf34f6379873bdc925d1dcf6b9c3d50349d3`, with no branch name (detached) and ten tracked dirty paths: `core_config.py`, `oec_aireos/MOE`, `oec_deploy`, three model notebooks, `qa_compliance_worker.py`, `storage_config.json`, and `tools/runner_control.py`. No live sync/reset/clean was attempted.
- [ ] **Reconcile the reserve-size discrepancy before any storage write.** The 2026-10-11 run `38175212786` logged `STORAGE_MANAGER_RESERVE_BYTES=37190724326`; the 2026-10-14 read-only stat reports size `33580119505` bytes, allocated `33580130304`, non-sparse, mtime `2026-10-12T20:33:53Z`. Cause/path equivalence is unknown. Do not resize, recreate, overwrite, delete or relocate the reserve.
- [ ] Obtain genuine quota values via the approved site/login-node route, publish with `tools/quota_snapshot.py` from actual `quota_check` values, verify shared visibility/freshness, and rerun admission. If the login route is still unavailable, resolve that transport or provide a site-approved telemetry producer; do not invent values.
- [ ] Diagnose the connector-2 Slurm control/accounting failure before QA recovery. Preserve the stopped process and queue until ownership and the replacement job state can be verified.
- [x] **TRELLIS cache-only runtime acceptance:** Connector_1 run [38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418) passed the CUDA xFormers operator check, pipeline load, inference, GLB export and geometry reopen using the cached `phase2_3d` stack. Fresh GLB: 8,865,916 bytes, SHA-256 `22caca5fe9c02c50c095e4385a7c17e94b214b5fc7d87417b94b48c796a89257`, 96,672 vertices / 92,062 faces; exact-run artifact [11914941709](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11914941709). OEC CLI/notebook implementation is still awaiting review in PR [#10](https://github.com/Killer4K-N/OEC/pull/10), not merged.
- [ ] **Still open:** FLUX image generation, intended-kernel notebook end-to-end checks, and separate AudioCraft/QA checks. The latest FLUX smoke [38559255790](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790) did not create a PNG because the GPU admission check found no eligible device.
## Completed in this workstream
- [x] Add standalone `pipeline_trellis_3d.py` with `check`, `generate`, and optional `gradio` modes; configurable GPU, model/cache/source paths, output path/folder, port, bind host, offline behavior and mesh/texture options.
- [x] Make TRELLIS notebook model loading cache-first and pass a local snapshot path to the TRELLIS loader (rather than passing the unsupported `local_files_only` loader kwarg).
- [x] Make model/dependency download/install cells use OEC fresh-quota admission and the managed storage operation lock. No quota bypass.
- [x] Improve combined TRELLIS + FLUX notebook execution order, dependency checks, setup text and duplicate-model-load avoidance.
- [x] Rework standalone `pipeline_flux_only.ipynb`: `phase2_3d` kernel, hostname/tunnel directions, configurable GPU/port, non-destructive process inspection, no forced Jupyter upgrade, no unpinned GitHub-main install, no automatic shared-cache purge, cache-first model resolution, gated missing-model download, share disabled, and image/seed/file outputs.
- [x] Add/maintain `docs/model_entrypoint_convention.md` for future interactive models: notebook + CLI, light check, one-shot inference, optional Gradio, configurable runtime, cache/storage guards, share disabled.
- [x] Fix path-alias verification so a correct existing symlink reports `ALIAS_OK`; guarded sync created and verified `aireos_datasets -> aireos_dataset`, `aireos_inputs -> aireos_input`, and `aireos_outputs -> aireos_output`. Canonical singular directories were not renamed.
- [x] Harden `qa_compliance_worker.py`: GPU visibility is selected before importing PyTorch, a `--gpu` option is available, missing model downloads require fresh quota admission, shared-cache purge is opt-in (off by default), and regression tests cover these guarantees.
- [x] Preserve the QA database and its existing rows. Queue doctor remains report-only during normal sync; mutations require explicit approval and cross-node ownership checks.
- [x] Snapshot the prior `Wan2.1/requirements.txt` and phase2_3d package freeze before targeted edits in `.oec_snapshots/trellis-sync-20261011-38141547014`.
- [x] Run offline source tests on connector-1, connector-2 and connector-5. The matrix at run [38157725815](https://github.com/Killer4K-N/Connector_1/actions/runs/38157725815) passed 17 TRELLIS/entry-point tests, 5 AudioCraft notebook tests, 10 QA recovery tests, and 6 alias tests per runner (38 per runner, 114 total).
- [x] Provision this single TODO, `test.json`, and cumulative `result.md` so future prompts can update persistent project tracking.
- [x] Copy and validate the tracking files in the live shared OEC tree with [connector-1 sync run 38160976083](https://github.com/Killer4K-N/Connector_1/actions/runs/38160976083); the staged JSON parse and all four offline test suites passed.
## P0 — unblock runtime safely
- [ ] **Fresh authoritative quota snapshot.** On the approved login node, run `quota_check` and use the actual reported usage/limit values (do not estimate) to create a fresh snapshot, e.g. `python ~/OEC/tools/quota_snapshot.py --used-gb <ACTUAL_USED_GB> --limit-gb <ACTUAL_LIMIT_GB> --source "quota_check"`. Use actual bytes with `--used-bytes`/ `--limit-bytes` if the command returns bytes. Then re-run the guarded admission probe. All three compute runners currently report no fresh snapshot; connector-1 cannot use its prior login-host route, and the other runners do not have an SSH client.
- [ ] **TRELLIS CUDA attention.** Once admission passes, install only the compatible `xformers==0.0.29.post2` wheel for the current `torch==2.6.0+cu124` stack via the cu124 wheel index, under the managed-operation lock. First snapshot the current environment as already implemented. Require an actual CUDA `memory_efficient_attention` probe to pass before model load. `xformers==0.0.29.post1` currently fails this probe; `flash-attn` is not installed and its fallback probe also failed.
- [ ] **TRELLIS.2 model cache.** The read-only cache probe for `microsoft/TRELLIS.2-4B` returned `LocalEntryNotFoundError` on all three runners. After fresh quota admission, download/cache the license-compliant source model via the guarded loader, then run offline image-to-3D, export a GLB, reopen it with trimesh, assert vertices/faces, and repeat export to check CuMesh stability. No model was downloaded during the audits.
- [ ] **FLUX.2 environment.** The model `black-forest-labs/FLUX.2-klein-4B` is cached, but the current package stack cannot import the FLUX pipeline: `diffusers==0.40.0.dev0` imports `get_cached_repo_tree`, missing from `huggingface-hub==0.36.2`. After quota admission, let the notebook reconcile the pinned released stack (`diffusers==0.37.0`, `huggingface-hub==0.36.0`, `transformers==4.56.1`) and verify imports, then generate and open one image from the existing cache. Do not claim FLUX fixed until this is tested in the real `phase2_3d` environment.
- [ ] **QA worker.** On connector-2, PID 2529002 (`qa_compliance_worker.py`) was observed stopped (`T`) under an interactive shell, started Oct 9; do not send SIGCONT to the stale process because it predates the latest guards. After checking user/session ownership and replacing it with the updated file, verify CUDA/quota/model-cache prerequisites and then launch exactly one guarded worker using the appropriate `--gpu`. Confirm logs advance and `PENDING_QA` rows transition; do not run a second worker or bulk-requeue claims on top of it.
- [ ] **Quota-gated model cache for QA.** The QA model `Qwen/Qwen2-VL-7B-Instruct` must be checked locally first. If missing, get fresh admission before download; otherwise the updated worker correctly stops rather than downloading.
## P1 — fix remaining dependency/backlog items
- [ ] **AudioCraft original wheel-build issue.** The current `phase1` environment imports `AudioGen` and `audio_write`, but `pip check` reports `thinc==8.3.6` requiring NumPy >=2 while phase1 has NumPy 1.26.4. The original build traceback was not found in recent logs and was not reproduced. Capture the exact failing command/traceback and prepare an isolated, license-compliant dependency plan before changing phase1. Do not blindly upgrade NumPy or reinstall AudioCraft in place.
- [ ] **QA backlog triage.** Read-only DB snapshot: 225 rows — `FAILED_MISSING_FILE=78`, `PENDING=144`, `PENDING_QA=2`, `PROCESSING_QA=1`. Inspect the affected file paths and error history. Preserve failure rows; only requeue a specific row after proving its files exist and active worker ownership is clear.
- [ ] **GPU utilization/worker liveness.** Current samples were 0% GPU utilization on the three hosts. The connector-2 video worker and upload daemon were sleeping in poll loops; QA process was stopped. After safe QA replacement and quota/model prerequisites, watch utilization, logs, queue latency and worker progress to separate idle queue time from inefficient active inference.
- [ ] **Jupyter/UI acceptance.** The notebook Python-cell syntax tests pass and a temporary Jupyter server/kernel smoke previously passed, but the user's actual persistent Jupyter session/browser SSH tunnel has not been verified. Run the updated TRELLIS, TRELLIS-only, FLUX-only and AudioCraft notebooks in their intended kernels end-to-end after the quota/dependency blockers clear.
- [ ] **AudioCraft wheel/install reproducibility.** Add the original build command and bounded build logs to `test.json` when the user/environment can reproduce the issue. Record the exact versions/platform/accelerator in that experiment record.
## P2 — ongoing project hygiene
- [ ] Keep `changelog/README.md` indexed to all day-specific changelogs.
- [ ] At the end of every new task, append a dated experiment to `test.json`, update this TODO list, append to the current day's changelog (create a new daily file when local date changes), and update `result.md` when a material result changes.
- [ ] Never merge these changes into `main` without explicit approval. Preserve dirty/untracked files in the live OEC checkout; do not force checkout/reset/clean.
- [ ] Continue using only the authorized runner labels `connector-1`, `connector-2`, and `connector-5` for parallel audit/test jobs.
## Latest sync note — 2026-10-11
The latest source sync copied the current tracker set from feature revision `70411afa152a862e4356cb09ccdc83cb1278b2fc`. `TRACKING_FILES_VALIDATION=PASS`; source/static results were 17 TRELLIS, 5 AudioCraft notebook, 10 QA, and 6 path-alias tests passing. `STORAGE_ADMISSION=BLOCKED`, therefore package installation and live TRELLIS inference were not run. See the daily changelog and `test.json` for the details.
The official Diffusers release notes list Flux2 Klein support in v0.37.0; the current Hugging Face Hub docs expose `get_cached_repo_tree`, explaining the observed import mismatch with the installed older Hub. This supports the proposed version pin but is not a substitute for the gated live import/generation smoke.
### Latest confirmed sync — run 38161408008
- [x] Fixed the missing quote in `MODEL_NOTEBOOKS_VALIDATED` after run 38161193474 failed before staging; the workflow now runs `bash -n tools/sync_trellis_and_audit_oec.sh` first and logs `SYNC_SCRIPT_SYNTAX=PASS`.
- [x] The subsequent [run 38161408008](https://github.com/Killer4K-N/Connector_1/actions/runs/38161408008) passed shell syntax, tracking validation, staged notebook/CLI validation, tracker-file copy, and the static suites (17 TRELLIS, 5 AudioCraft notebook, 10 QA, 6 alias tests).
- [ ] Runtime package/model installation and TRELLIS inference remain blocked on fresh quota telemetry. No packages were installed, no model was downloaded and no QA queue rows were changed.
## Final confirmed sync — run 38161747478
- [x] Shell preflight `bash -n tools/sync_trellis_and_audit_oec.sh` passed; the prior quote parse error is resolved.
- [x] `TRACKING_FILES_VALIDATION=PASS` and `STAGED_NOTEBOOK_AND_CLI_VALIDATION=PASS`; the run copied the latest `TODO.md`, `test.json`, `result.md`, daily changelog and index.
- [x] Four suites passed again: 17 TRELLIS/entry-point, 5 AudioCraft notebook, 10 QA, and 6 path-alias tests. Queue handling stayed report-only.
- [ ] Live TRELLIS/FLUX runtime remains gated by missing fresh quota data; no package installation or model download was performed.
## 2026-10-12 — Runtime remediation in progress
### Guarded fixes prepared (awaiting new action validation)
- [x] Created an isolated Connector_1 branch `ops/runtime-remediation-20261012` and corrected all 12 package/model admission calls in the sync helper plus all 6 write-related QA-helper admission calls to require fresh quota data. StorageManager must still check the existing allocated reserve, allocation target, and actual filesystem headroom; reserve resizing/deletion and cache purging remain forbidden.
- [x] Constrain the `xformers==0.0.29.post2` candidate to a prebuilt wheel (`--only-binary=:all:`) for the official Torch 2.6/CUDA 12.4 combination. It still needs a real CUDA fp16 attention probe after admission; do not mark fixed based only on the wheel version.
- [x] Correct the AudioCraft repair plan to pin `numpy==1.26.4`, `spacy==3.7.6`, and the spaCy-compatible `thinc==8.2.5` with binary wheels only. Runtime package consistency and imports must pass after the guarded action.
- [x] Harden QA recovery: pass the scheduled GPU via `--gpu`, capture PID/parent/session/TTY/job identifiers, revalidate them before retirement, and never retire the old stopped process until the replacement Slurm job has reached RUNNING. The model/dependency preflight still fails closed if a required download/install lacks a fresh snapshot.
- [x] Include `changelog/CHANGELOG-2026-10-12.md` in the explicit snapshot and staging allowlists so the guarded sync preserves the required daily tracking records.
### Runtime acceptance still pending
- [ ] **Quota:** obtain real values by running `quota_check` in the approved login shell and create `~/.cache/aieros/quota_snapshot.json` with `tools/quota_snapshot.py`. Never estimate, forge a timestamp, or turn off `require_fresh_quota`. Latest verified audit reported no fresh snapshot; all package/model writes remain blocked until this is resolved.
- [ ] **TRELLIS attention:** run the actual CUDA attention probe after wheel admission. If xFormers still fails, assess a separately quota-gated, upstream `flash-attn==2.7.3` path from [Microsoft TRELLIS.2 setup](https://github.com/microsoft/TRELLIS.2/blob/main/setup.sh).
- [ ] **TRELLIS.2 inference:** cache-first check/download `microsoft/TRELLIS.2-4B`, generate one sample, export GLB, re-open with trimesh, and verify nonempty geometry.
- [ ] **FLUX.2 inference:** install/verify the released Diffusers 0.37.0 / Hub 0.36.0 / Transformers 4.56.1 set only after admission; import the Flux2 pipeline and generate/re-open a PNG from cached FLUX.2 Klein weights.
- [ ] **QA worker:** execute syntax/preflight on the remediation branch, inspect exact process/session ownership, and replace at most one stopped worker only after the guarded model/dependency checks and confirmation that the new job is RUNNING. Inspect worker logs afterward.
- [ ] **QA backlog:** retain the 225-row status snapshot as report-only. Do not requeue any of the 78 `FAILED_MISSING_FILE` records or mutate any row without file-by-file and process-ownership evidence.
- [ ] **AudioCraft:** after quota admission, require `pip check`, `AudioGen` and `audio_write` imports to pass; perform small generation/write validation only when model-cache and runtime prerequisites are satisfied.
- [ ] **Action verification:** the remediation helpers have source commits, but no new run has yet validated the combined helper flow. Record the exact run ID and result in `test.json`, this daily changelog, `result.md`, and this TODO once the new branch action finishes.
**Upstream references reviewed:** [TRELLIS.2](https://github.com/microsoft/TRELLIS.2), [xFormers changelog](https://github.com/facebookresearch/xformers/blob/main/CHANGELOG.md), [Diffusers FLUX.2 v0.37.0 docs](https://huggingface.co/docs/diffusers/v0.37.0/en/api/pipelines/flux2), and [AudioCraft requirements](https://github.com/facebookresearch/audiocraft/blob/main/requirements.txt). Source reference review is not runtime acceptance.
## 2026-10-14 follow-up — storage write-guard fix and runtime smoke evidence
- [x] Created the source candidate branch [`fix/storage-admission-write-guards-20261014`](https://github.com/Killer4K-N/OEC/tree/fix/storage-admission-write-guards-20261014); current source commit [`4ade353d566bfeb525949f5f4c1905a1ae1e135c`](https://github.com/Killer4K-N/OEC/commit/4ade353d566bfeb525949f5f4c1905a1ae1e135c). Rollback/reference branch [`backup/oec-before-write-guards-20261014`](https://github.com/Killer4K-N/OEC/tree/backup/oec-before-write-guards-20261014) pins the pre-code baseline. `main` remains unchanged at `82346c0753e139b92240f53734eb48d2113ed9ad`.
- [x] Corrected unsafe `require_fresh_quota=False` calls across the four model notebooks and TRELLIS CLI. Explicit StoragePolicy preflight now runs before and again inside managed model/output write locks; combined and TRELLIS-only setup commands gate pip installs/git clones; output directories are created only after admission. This is a source guard fix, not permission to bypass the missing telemetry gate.
- [x] Added `tests/test_storage_write_admission.py` and `.github/workflows/storage-admission-guard-tests.yml`. Final hosted validation [run 38559330370](https://github.com/Killer4K-N/OEC/actions/runs/38559330370) on commit `4ade353...` passed 27/27 static tests (12 TRELLIS notebook + 5 CLI/easy run + 5 AudioCraft notebook + 5 new storage-admission tests), Python compilation, and JSON validation for all four notebooks (16/15/10/6 cells). First run [38558509401](https://github.com/Killer4K-N/OEC/actions/runs/38558509401) failed two of the new tests; the log exposed the missing AudioCraft under-lock recheck and a too-narrow test assertion. Those were corrected and the final run passed.
- [x] Reconciled a newer historical baseline from [Connector_1 run 38175212786](https://github.com/Killer4K-N/Connector_1/actions/runs/38175212786), job `114576061200`: at that run, `xformers==0.0.29.post2` CUDA attention and the Flux2 Klein import passed; Diffusers/Hub/Transformers were `0.37.0/0.36.0/4.56.1`; Flux model cache was a hit; TRELLIS.2-4B cache was a miss. The overall run still failed at fresh-quota admission, so it did not perform full inference. The earlier `0.0.29.post1` failure remains a genuine older result; reason for package version change is unestablished.
- [x] Attempted an offline, cached FLUX generation without installs/downloads. [Run 38558972259](https://github.com/Killer4K-N/Connector_1/actions/runs/38558972259) and [run 38559255790](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790) stopped safely at GPU preflight. The latter confirmed the cached snapshot, but both A100s had an active compute process (GPU0 31,536/40,960 MiB free; GPU1 39,902/40,960 MiB free), so inference never began and no image was created. Do not stop or restart unidentified GPU jobs to make this pass.
- [ ] **BLOCKED — authoritative quota telemetry:** snapshot remains missing and `quota_check` is not on the compute runner. Obtain real quota values through approved site/login-node access, then publish only genuine values using `tools/quota_snapshot.py`; never substitute Lustre free blocks or weaken `require_fresh_quota`.
- [ ] **OPEN — TRELLIS runtime:** cache miss for `microsoft/TRELLIS.2-4B`; wait for quota admission, then separately test attention, model load, actual image-to-3D inference, GLB export and geometry reopen.
- [ ] **BLOCKED — FLUX actual generation:** weights are cached and historical imports passed, but the latest inference smoke has not reached model load because both A100s were busy. Retry only when an idle GPU is confirmed, preserving offline/cache-only behavior.
- [ ] **OPEN — notebook and AudioCraft runtime:** static checks passed only. No Jupyter end-to-end execution, AudioCraft repair or generated output was completed; do not modify `phase1` without approval.
- [ ] **BLOCKED — QA worker:** separate connector-2 recovery failed due Slurm node-name and accounting DB connectivity. Keep queue and stopped process unchanged until scheduler state and process ownership are reverified.
- [ ] **OPEN — shared state reconciliation:** investigate the reserve-size discrepancy and plan a safe snapshot of the detached live OEC checkout with ten tracked dirty paths before any permitted sync. The reserve file and live checkout were not modified.
- [x] Final tracking commit `dac91f09bc6cecd896e38213072fe19142d30390` was itself revalidated by [hosted run 38559861094](https://github.com/Killer4K-N/OEC/actions/runs/38559861094): 27/27 static tests, Python compilation, and all four notebook JSON checks passed. This rerun confirms the documentation commit did not change source-test outcomes; it is not runtime inference acceptance.
## 2026-10-14 — TRELLIS / FLUX generation verification follow-up
- [x] Corrected TRELLIS cache discovery: the CLI's local-only Hub lookup now falls back to scanning the configured cache for actual `.safetensors` shards before reporting a miss or requesting a download. Latest candidate source commit: [`f571f508fc693d2afd96c17544702d64a0c29c27`](https://github.com/Killer4K-N/OEC/commit/f571f508fc693d2afd96c17544702d64a0c29c27).
- [x] Corrected combined notebook cache resolution: FLUX.2 Klein is tried from both `aireos_models` and `aireos_models/hub`; current cache location is accounted for before the quota-gated download path.
- [x] Added output-admission checks before costly TRELLIS/FLUX inference, plus GLB/PNG checks after saving. The CLI also verifies the GLB 2.0 header/length, JSON chunk and nonempty mesh accessors.
- [x] Static suite passed on latest candidate commit in [run 38571665298](https://github.com/Killer4K-N/OEC/actions/runs/38571665298): 28/28 (12 TRELLIS notebook, 5 CLI/easy-run, 5 AudioCraft notebook, 6 storage-admission tests), Python compilation and four notebook JSON validations.
- [x] **Confirmed TRELLIS has generated a real 3D asset before.** The historical successful [run 37942265623](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623) logged pipeline load, image-to-3D inference, and GLB export PASS; the 8,950,028-byte output was retrieved from artifact [11622412194](https://api.github.com/repos/Killer4K-N/Connector_1/actions/artifacts/11622412194/zip) and independently validated. The recovered GLB has one mesh/primitive, 2 textures and reopens with `trimesh` to 97,783 vertices / 92,819 faces. This proves a prior isolated run generated a real asset, not that the current shared environment generated one today.
- [x] Latest October 14 cache-only TRELLIS attempt [run 38571363231](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231) confirmed the source checkout, official `T.png`, and cached 7 safetensors shards (14,819,870,530 bytes). It stopped safely at the idle-GPU preflight; no current GLB was produced. Report artifact [11897043384](https://api.github.com/repos/Killer4K-N/Connector_1/actions/artifacts/11897043384/zip).
- [ ] **Still blocked — current live TRELLIS generation:** retry the offline cached smoke only when at least one A100 has zero active compute processes and at least 30,000 MiB free. Do not interrupt, signal, or kill existing GPU work.
- [ ] **Still blocked — current live FLUX generation:** cached FLUX.2 Klein weights exist and historical imports passed, but the recent smoke found one active compute process on each A100. Retry an offline cache-only generation when an idle GPU is confirmed; validate the resulting nonempty PNG.
- [ ] **Still blocked — model downloads and package writes:** authoritative quota snapshot remains missing and `quota_check` remains absent on the compute node. Get genuine quota values from the approved site/login route and publish them through the existing snapshot writer before any new model/dependency download. Never use Lustre free space as a quota substitute.
- [x] Updated this TODO, `test.json`, `result.md` and dated changelog with final TRELLIS run [38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418), exact-run artifact [11914941709](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11914941709), hash, test count and geometry reopen results.
## 2026-10-14 main-branch integration (requested)
- [x] Integrated tested TRELLIS/FLUX notebook and CLI updates, storage write-admission guards, static regression suite and cumulative run records into `main`. The main-hosted validation run is pending and must be added here with its exact result before this task is considered closed.
- [x] Added the latest candidate static rerun [38572444007](https://github.com/Killer4K-N/OEC/actions/runs/38572444007): 28/28 static tests, Python compilation PASS and four notebook JSON checks PASS.
- [x] Logged the initial capacity-matrix workflow configuration failure, the corrected connector-1 diagnostic and the current TRELLIS smoke blocked by occupied GPUs.
- [x] **Fresh TRELLIS asset generated and validated:** Connector_1 run 38598822415, artifact 11912523421 (8,870,632 bytes; SHA-256 0ba06de0e028d975b7108f4dcb9856a81dcdd76037e94cc852883fc5b2ad6b1e); GLB structural checks and trimesh reopen passed (96,532 vertices / 91,986 faces).
- [x] **OEC CLI/notebook source candidate CI:** run 38601987037 passed 34 tests, Python compilation and four notebook JSON checks; review PR #10 is open and not merged.
- [x] **Final Connector_1 retry verified:** run [38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418) passed 10/10 tests and uploaded the exact current-run GLB artifact [11914941709](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11914941709) plus report [11913529964](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11913529964). GLB 8,865,916 bytes; SHA-256 `22caca5fe9c02c50c095e4385a7c17e94b214b5fc7d87417b94b48c796a89257`; GLB 2.0, valid JSON chunk and mesh accessors, `trimesh_reopen=PASS` (96,672 vertices / 92,062 faces).
- [ ] **OPEN — current FLUX image:** cached FLUX weights exist, but the offline generation smoke did not create a PNG because both A100s were occupied. Retry with an idle GPU and verify the output image.
- [ ] **BLOCKED — fresh quota telemetry:** quota snapshot missing and `quota_check` absent on the compute runner. Keep shared model/dependency downloads and quota-gated writes fail-closed; never substitute Lustre free-space values.
- [x] **Main-branch CI verified:** commit [`9c9d7acc12e47658f37e71840449f8558b42ee2b`](https://github.com/Killer4K-N/OEC/commit/9c9d7acc12e47658f37e71840449f8558b42ee2b), [run 38575822798](https://github.com/Killer4K-N/OEC/actions/runs/38575822798), job `115892512804`: 28/28 static tests PASS, compilation PASS, all four notebook JSON checks PASS. The test/run result has been added to the cumulative registry and dated changelog on main.
- [x] Re-tried the current TRELLIS and FLUX cache-only GPU smoke workflows. TRELLIS run `38571363231` attempt 2 remained blocked at idle-GPU preflight (report artifact `11899728417`); FLUX run `38559255790` attempt 2 found one active compute process on each A100 and generated no PNG. Both reasons/results have been added to `test.json` and the dated changelog on main.
## 2026-10-14 follow-up — TRELLIS offline config fix
- [x] Reproduced the loader defect in [Connector_1 run 38587490301](https://github.com/Killer4K-N/Connector_1/actions/runs/38587490301): 7/7 previous tests passed and GPU admission selected an allowed device, then model load attempted a forbidden offline Hub lookup for a missing \`pipeline.json\`.
- [x] Committed the pinned config and local snapshot-overlay fix on [\`diagnose/trellis-asset-generation-20261014\`](https://github.com/Killer4K-N/Connector_1/tree/diagnose/trellis-asset-generation-20261014), with expanded 10-test regression coverage.
- [ ] **BLOCKED — any missing model/dependency download:** fresh authoritative quota telemetry remains missing; no quota bypass, install or download.
## 2026-10-14 follow-up — TRELLIS offline pipeline-config fix
- [x] Reproduced and fixed the weight-only snapshot pipeline.json lookup bug with a pinned /tmp overlay and offline Hub access.
- [x] Validated a fresh GLB in Connector_1 run 38598822415; artifact 11912523421; structure and trimesh reopen passed.
- [x] OEC CLI and both TRELLIS notebooks use the shared offline config helper; CI 38601987037 passed 34 tests; PR #10 is open, not merged.
- [x] Fixed the Connector_1 fixture assertion and narrowed GLB upload to the exact workflow run ID.
- [x] Verified run-scoped artifact workflow [38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418) uploads only the GLB created under `/tmp/oec-trellis-asset-generation-38602330418/`; the artifact and report are linked above.
- [ ] BLOCKED — any missing model/dependency download: authoritative quota telemetry is still missing; no quota bypass, install or download.

## 2026-10-14 22:39 IST — TRELLIS final generation acceptance
- [x] Actual cached TRELLIS.2 pipeline load, inference, mesh processing, GLB export and independent `trimesh` reopen passed in [Connector_1 run 38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418). All 10 regression tests passed.
- [x] Fresh GLB artifact [11914941709](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11914941709) is run-scoped, 8,865,916 bytes, SHA-256 `22caca5fe9c02c50c095e4385a7c17e94b214b5fc7d87417b94b48c796a89257`. Valid GLB 2.0, one mesh/primitive, two textures, 96,672 vertices and 92,062 faces. Report: [11913529964](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11913529964).
- [x] The no-`pipeline.json` offline-load defect is fixed by a pinned config plus `/tmp` overlay. The successful path used cached weights and config only; no model/package downloads, shared-cache writes, or GPU-process termination occurred.
- [x] OEC CLI/notebook candidate CI [38601987037](https://github.com/Killer4K-N/OEC/actions/runs/38601987037) passed 34 static tests, Python compilation and four notebook JSON checks. PR [#10](https://github.com/Killer4K-N/OEC/pull/10) is open and unmerged; Connector_1 PR [#2](https://github.com/Killer4K-N/Connector_1/pull/2) is ready for review.
- [ ] FLUX image generation still needs a successful PNG-producing run. Fresh quota telemetry also remains missing, so missing-model/dependency downloads must stay blocked.


## 2026-10-14 — OEC runner pool migration baseline
- [x] Archived all 677 reported `Connector_1` Actions workflow-run records (677 unique ids) in [`docs/runner_migration/connector_1_actions_runs.json`](docs/runner_migration/connector_1_actions_runs.json); run-level outcomes: 305 success, 236 failure, 122 cancelled, 13 skipped, 1 queued.
- [x] Migrated the migration method, historical result counts, source URLs and runner transition plan to [`docs/runner_migration/README.md`](docs/runner_migration/README.md) and registered the experiment in `test.json`. Original job logs/artifacts stay at the original URLs; the GitHub run objects were not moved.
- [x] **Runner migration acceptance probe:** [OEC run 38610558599](https://github.com/Killer4K-N/OEC/actions/runs/38610558599) successfully ran on all three labels `oec-1`, `oec-2`, `oec-3`; each reported actual identity match, eight visible A100 devices, TRELLIS and FLUX cache hits and an uploaded diagnostic report ([oec-1](https://github.com/Killer4K-N/OEC/actions/runs/38610558599/artifacts/11916534964), [oec-2](https://github.com/Killer4K-N/OEC/actions/runs/38610558599/artifacts/11918195061), [oec-3](https://github.com/Killer4K-N/OEC/actions/runs/38610558599/artifacts/11918525046)). The probe confirms the quota snapshot is missing; no packages were installed, downloads made, caches mutated or processes signalled.
- [ ] **FLUX runtime still blocked — no valid PNG:** [run 38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955) failed on oec-1 after approximately 11 minutes. GitHub returns `BlobNotFound` for its job log; job and step states conflict, no artifact was uploaded, and the root cause is undetermined. Subsequent runs [38613199844](https://github.com/Killer4K-N/OEC/actions/runs/38613199844) and [38613575959](https://github.com/Killer4K-N/OEC/actions/runs/38613575959) have all labels queued without runner assignments. Verify/reconnect the three runner agents and cancel these stale queued attempts in Actions UI before a clean retry. New source captures logs/status, uses `device_map="cuda"`, and serializes GPU use with a host-local lock, but no runtime pass is claimed.
- [x] **Notebook static validation:** [candidate CI 38613904439](https://github.com/Killer4K-N/OEC/actions/runs/38613904439) passed all 46 tests, six-source Python compilation, and all four notebook JSON/Python-cell checks. FLUX-only Gradio default port is 7864; combined TRELLIS/FLUX default is 7863; TRELLIS Gradio default remains 7862, with public sharing off.
- [ ] **Notebook runtime verification:** UI/tunnel and real FLUX generation remain unverified until a clean PNG-producing OEC-runner job completes.

## 2026-10-14 23:38 IST — OEC candidate source validation
- [x] [OEC CI run 38612345392](https://github.com/Killer4K-N/OEC/actions/runs/38612345392) passed 46/46 tests: TRELLIS notebook static 12, TRELLIS easy-run 5, offline TRELLIS config 6, Flux CLI/notebook/cache/PNG 7, Flux GPU admission 5, AudioCraft static 5, and storage-write admission 6.
- [x] Six Python sources compiled and all four notebooks parsed as valid JSON. This validates source shape and guard behavior; it is not an end-to-end FLUX image-generation result.
- [ ] FLUX runtime remains open until [run 38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955) uploads a PNG and metadata that pass validation on the new OEC runners.
## 2026-10-14 23:48 IST — FLUX first runtime attempt and mitigation
- [x] First cache-only FLUX runtime [38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955) recorded as FAIL, not PASS: oec-1 job ended failure after ~11 minutes; log blob was unavailable and no PNG/metadata artifact exists. Exact cause remains unknown.
- [x] Added stage logging and failure status JSON to the runner workflow; changed it to schedule labels concurrently but hold a `/tmp` host-local `flock` around GPU admission/inference, so separate oec labels on the same host cannot race onto one GPU. The inference step has a 14-minute timeout and job artifact captures log/status when the runner remains alive.
- [x] Changed FLUX model loading to `device_map="cuda"` in candidate commit [e594269](https://github.com/Killer4K-N/OEC/commit/e59426970956ff83fbd433612adc29eb9364d0f8) to avoid CPU-load-then-GPU-copy peak memory; candidate CI [38613904439](https://github.com/Killer4K-N/OEC/actions/runs/38613904439) passed 46/46 tests and all static checks.
- [ ] **BLOCKED — runner availability / stale queue:** runs [38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955), [38613199844](https://github.com/Killer4K-N/OEC/actions/runs/38613199844) and [38613575959](https://github.com/Killer4K-N/OEC/actions/runs/38613575959) remain queued/partly failed without available runner assignments. Verify oec-1/oec-2/oec-3 are Online/Idle, cancel old queued attempts, then push `.github/flux-smoke.trigger` or use workflow dispatch for a clean run.
- [ ] No fresh quota snapshot; do not install dependencies/download model weights until approved telemetry is available.

## 2026-10-15 — FLUX/TRELLIS integration fixed and verified on review branch

Tracking only on main: model/source changes remain on review branch fix/flux-trellis-pipeline-20261015; no code merge was made by this record update.

- [x] Reviewed OEC combined run 38723286765. FLUX generated and validated its PNG, and TRELLIS cache/attention/model loading passed, but generation stopped before inference because pipeline_trellis_3d.py used subprocess.run() without importing subprocess in its scratch-filesystem findmnt fallback.
- [x] Added the import plus a regression test for the findmnt path. The same run showed GPU utilization 100% with no visible compute processes was incorrectly admitted as IDLE; idle admission now requires known utilization ≤5%, and the orchestrator resamples for up to 180 seconds before fail-closed denial.
- [x] Hosted CI 38725202281 passed 58/58 tests, Python compilation, and all four notebook checks.
- [x] End-to-end cache-only run 38725376076 passed on oec-1 / host scn30-mn. Duration 419.848s; exact-run report PASS. FLUX PNG 512×512, 255,946 bytes, SHA-256 2b05b417eb928a93511c88ee2d45b21357419720c31917a8e5129434eed6afbb. TRELLIS exported a 3,484,804-byte GLB (SHA-256 74e3654625a0662302ecb1bf1c0c79885833563753b6a30acbeee45a5c4b360e); independent trimesh reopen passed with 54,597 vertices / 93,617 faces. Artifact 11967418646 includes PNG, sidecar, pipeline_report.json and GLB.
- [ ] OPEN — authoritative fresh quota telemetry is still missing; keep model/dependency downloads and managed shared writes blocked. The combined run used caches and /tmp only.
- [ ] Separate follow-up — audit qa_compliance_worker.py import/CUDA visibility order in a focused change; no QA worker or queue was modified here.

Detailed evidence is in changelog/CHANGELOG-2026-10-15.md and test.json. Keep main source unchanged unless a code merge is explicitly authorized.

- [x] Added tools/media_services/smoke_client.py to run a live loopback model job and validate/save the artifact through managed outputs storage; no live inference has been run by the assistant.


## 2026-10-19 — media supervision and QA upload-state candidate

- [x] Preserved historical live passes: AudioGen generated a valid 3-second mono 16 kHz WAV in run 39135140674; run 39135140660 passed one controlled Kokoro → Whisper Turbo/Qwen3-ASR speech chain. ACE-Step was skipped because its package was absent.
- [x] Preserved later failure evidence: audio bootstrap run 39149243881 did not reach package installation because StorageManager refused output-reserve resizing during an active managed operation; no packages were installed. Visual sidecar run 39149240005 loaded TRELLIS but the job request failed HTTP 507 because outputs had an active managed operation; LTX did not reach ready/model_loaded within 20 minutes.
- [x] Candidate commit [f52aae4](https://github.com/Killer4K-N/OEC/commit/f52aae4dfac62d67f75401f7fb643e4a47a63b43) adds the local media service supervisor, safe GPU/port/import gates, loopback health probe, shared workflow serialization, a canonical QA/upload status helper, and two regression test files.
- [ ] Run the new unit and temporary-SQLite tests using an already-authorized, verified $0 route. These tests have been authored but not executed in this candidate update.
- [ ] Before model start, obtain fresh quota/StorageManager status and identify the active lease owner using the sanctioned manager interface. Never resize reserves during active operations or run purge to clear a lock.
- [ ] Run one cache-only provider at a time, confirm health and validated audio/text/GLB/MP4 artifacts. No persistent service was started by this update.
- [ ] Verify the actual OEC-Play server /health and /api/media-services from its dedicated environment; current live-server status remains unverified.
- [ ] Integrate speech/music job types into brain.py and brain_config.json only after service contracts and artifact metadata are validated. Existing video prompt-batch limits are not audio/music chunking semantics.


## 2026-10-19 — queue schema consistency follow-up

- [x] Aligned worker_ltx_video.py's new-database status default to PENDING, matching the canonical QA/uploader status; added a static regression assertion. Existing shared SQLite databases were not changed or migrated.
- [ ] The static schema assertion and disposable SQLite lifecycle tests remain authored but not executed.


## 2026-10-19 — A100 speech acceptance result

- [x] [A100 run 39209090292](https://github.com/Killer4K-N/OEC/actions/runs/39209090292) completed successfully on oec-1 / scn30-mn; all workflow steps passed.
- [x] Compile/mock suites passed: media API 12/12, audio validation 10/10, supervisor 8/8, SQLite status-contract 5/5 (35 tests total).
- [x] Cache-only Kokoro-to-Whisper Turbo/Qwen3-ASR chain passed on CUDA. Kokoro created a valid 4.7-second mono 24 kHz WAV; both recognizers returned the same accepted 56-character transcript from that WAV. Audio/text artifacts were saved under the configured output root.
- [ ] ACE-Step music generation remains skipped because acestep is absent from phase1, phase1_ltx and phase2_3d. Prepare and test it in an isolated runtime without modifying the shared Torch stack.
- [ ] Visual acceptance [39209706982](https://github.com/Killer4K-N/OEC/actions/runs/39209706982) is running on the same serialized A100 lane; require a validated GLB from TRELLIS and decoded MP4 from LTX.
- [ ] Continuous Brain-to-worker-to-QA-to-uploader acceptance and production OEC-Play health checks remain unverified.

## Static validation follow-up — 2026-10-20

- Preserved failure [run 39378972546](https://github.com/CalamityStriker/OEC/actions/runs/39378972546). The failure was the static validator asserting at least three cells in pipeline_audiogen_gradio.ipynb; both CLI notebooks used two cells. The Python AST loop did not run for those notebooks. Added a dedicated environment/safety cell to both; wait for the next Actions result before marking Python/notebook validation passed.

## 2026-10-20 — Safe persistent-checkout sync gate

- Added tools/sync_feature_branch_a100.sh and .github/workflows/oec-a100-local-sync.yml. The designated oec-1 runner attempts only a clean same-branch fast-forward from origin; it does not clone, branch-switch, reset, delete files or touch GPU/storage state.
- The live A100 checkout is not yet claimed synced: await this workflow's log and require OEC_A100_SYNC=PASS and matching target/after SHA. If the tree is dirty or origin/branch differs, resolve that state without overwriting it.


## 2026-10-20 — Latest verification reconciliation

- **Static regression PASS on current source SHA `c79401c00182e94f3bc3f4d38109174f0662c7f5`:** [run 39379246551](https://github.com/CalamityStriker/OEC/actions/runs/39379246551), job [118484298605](https://github.com/CalamityStriker/OEC/actions/runs/39379246551/job/118484298605), hosted Ubuntu/Python 3.11. All 14 test commands completed successfully (102 test cases total as emitted in the logs); the new Gradio notebook suite passed 3/3 including code-cell AST parsing, explicit environment/API contract, and provider-stack isolation. The existing TRELLIS/FLUX/AudioCraft notebook JSON checks passed. This is static/contract evidence only, not live inference.
- **A100 E2E is still BLOCKED before inference:** [run 39320471955, attempt 2](https://github.com/CalamityStriker/OEC/actions/runs/39320471955), job [118480769324](https://github.com/CalamityStriker/OEC/actions/runs/39320471955/job/118480769324), failed closed because external PID 3347078 from the Biome server-components Python runtime still had CUDA contexts on all eight A100s. Artifact [12244625569](https://github.com/CalamityStriker/OEC/actions/runs/39320471955/artifacts/12244625569) is a pre-inference blocked report; no LTX inference, Qwen2-VL decision, upload, or read-after-write happened. The process was not killed/signalled.
- **Persistent A100 checkout sync not completed:** [sync run 39379246680](https://github.com/CalamityStriker/OEC/actions/runs/39379246680), job [118484298968](https://github.com/CalamityStriker/OEC/actions/runs/39379246680/job/118484298968), was correctly blocked because `git branch --show-current` in `$HOME/OEC` returned an empty string (detached HEAD). The sync script did not switch branches or change files. The script stops before testing whether that checkout is dirty, so do not assume it is clean.
- **Old failed static attempt retained as history:** run 39378972546 failed at a minimum-cell assertion for the two-cell AudioGen/MusicGen notebooks. Commit 64254d6 added the explicit environment markdown cells; the 3/3 notebook tests and complete static workflow passed in runs 39379119055 and 39379246551.

## Remaining acceptance gates

1. [ ] Read-only diagnose the persistent `$HOME/OEC` checkout (actual HEAD, branch list, dirty count and whether the intended local branch exists), then manually resolve the detached-HEAD state without discarding user data; re-run the fail-closed sync and require `OEC_A100_SYNC=PASS` plus matching expected/actual SHA.
2. [ ] Obtain normal release of all A100 contexts by the external process owner; do not kill/signal PID 3347078. Recheck `nvidia-smi` and fresh StorageManager state afterward.
3. [ ] Run current-head FLUX→TRELLIS on the assigned A100 and validate a generated PNG plus a reopened GLB.
4. [ ] Generate an actual ACE-Step FLAC in its isolated venv; no accepted music artifact exists yet.
5. [ ] Resolve MusicGen cache/egress only with current cache/network evidence; keep its CC-BY-NC model-weight limitation explicit.
6. [ ] For Kokoro, Whisper and Qwen3-ASR, launch one worker at a time after admission and check service ready/model_loaded, full job lifecycle, result bytes, logs, and environment isolation.
7. [ ] Complete actual Brain/LTX→Qwen2-VL accept/reject→upload-pending→HF chunk manifest/upload→remote read-after-write/reassembly/hash validation; current mock chunk tests are not live Hugging Face acceptance.
8. [ ] Complete OEC-Deploy clients/worker dispatch against the accepted APIs and supervised AudioGen/MusicGen CLIs; add typed job state, license metadata and artifact validation.
9. [ ] Audit existing Wan and other catalogued model workflows and environment/license/cache gaps before adding more model runtimes.


## 2026-10-20 — Persistent A100 checkout state discovered

- The read-only preflight in run 39379628387/job 118485509739 reports origin=EXPECTED, branch is detached/empty, HEAD 081aaf34f6379873bdc925d1dcf6b9c3d50349d3, expected local feature branch missing, expected origin remote-tracking ref present, and 662 dirty/untracked entries. No filenames/content were overwritten and the sync stopped before mutation.
- **Do not automatically sync/reset/clean the existing checkout.** Review/back up the 662 entries, then recover on a reviewed branch or separate worktree. The current branch source remains in GitHub at this feature branch; the persistent $HOME/OEC checkout is not synced.
- Latest static suite run 39379628368 passed on tested source b6de4b086705caa30a1705039baf4ac49996725a, including notebook tests 3/3. Live E2E run 39320471955 attempt 2 remains blocked by external PID 3347078 occupying all eight A100s; do not kill it.


## Additional model catalogue finding — Wan 2.1

- The repo contains `pipeline_wan_video.ipynb`, kernel metadata `phase1` / Python 3.9.25, and a legacy Wan 2.1 14B worker class embedded in a notebook. It contains stored historical outputs, no Gradio UI, selects GPU by free memory alone instead of verifying process ownership, and references bare `SYSTEM_DIRS` although it only imports `core_config`. This is not a verified worker. Do not run it against the shared GPU, or install Wan packages into shared `phase1`; first identify cached model/dependency state and provide a dedicated runtime/worker with safe GPU/storage admission.


## Safe A100 test-worktree fallback — 2026-10-20

- Added `tools/create_clean_a100_test_worktree.sh`. When the existing $HOME/OEC fails fast-forward gates, the workflow may create/update only a dedicated sibling test worktree after fresh StorageManager admission of 0.25 GB requested and at least 1.0 GB free. It refuses path collisions or dirty/unregistered existing targets and validates fetched/ref and actual SHA.
- This does not claim success before the next sync workflow log confirms it. $HOME/OEC's detached HEAD and 662 dirty/untracked entries are preserved.


## 2026-10-20 — Sync fallback accepted

- Current static/storage acceptance run 39380653548/job 118488776376 passed on source SHA `32e1a5f9203ed94214f4151c51e2504fe6589002`; 14 command groups/102 logged tests succeeded, including notebook tests 3/3.
- Sync run 39380653563/job 118488776455 successfully created `$HOME/OEC_feature_sync` after the current StorageManager preflight passed. Output `OEC_CLEAN_WORKTREE_SYNC=PASS`, actual SHA equals target SHA `32e1a5f9203ed94214f4151c51e2504fe6589002`. Source path is the clean sibling worktree. Existing `$HOME/OEC` stayed at detached HEAD `081aaf34f6379873bdc925d1dcf6b9c3d50349d3` with 662 dirty/untracked entries; no files were overwritten.
- The sync workflow is now configured to re-run for checklist/result/runbook/tracker changes as well as notebook/script changes, so the sibling test worktree can be advanced to the final documentation commit only while clean and after another StorageManager preflight.


## Latest sync and regression result — 2026-10-20

- Current branch SHA `132a8a5820a104ec27c14a87c9af3d4f84e83b98` passed static acceptance in run 39380928743/job 118489623553; new notebook tests 3/3 passed.
- Sync run 39380928762/job 118489623737 passed after StorageManager admission and updated the isolated `$HOME/OEC_feature_sync` worktree to the current SHA. The primary `$HOME/OEC` checkout remains preserved at its detached HEAD with its 662 dirty/untracked entries.
- Do not run model GPU tests until a fresh `nvidia-smi`/process-owner check and StorageManager check show the requested device/output admission is safe. Last E2E attempt found external PID 3347078 attached to all eight A100s; release must come from its owner.


## 2026-10-20 — User-requested live UI and worker acceptance

- Route live A100 acceptance to the reported idle `oec-2` runner, not the `oec-1` runner that saw an external CUDA owner. Keep GPU/storage tests serialized.
- For each model-specific notebook, start its actual Gradio interface on loopback, verify the UI responds HTTP 200, invoke the wired callback against the live isolated backend, validate generated WAV/FLAC or ASR transcript, and record the SHA-256 of generated audio.
- Select/pin a process-checked, low-use A100 for every live speech/music provider. If no device is admitted, fail closed rather than letting the provider default to GPU 0.
- Static checks and source sync are not live acceptance. Require current Actions artifacts for AudioGen, MusicGen, ACE-Step, Kokoro, Whisper, Qwen3-ASR, FLUX→TRELLIS, LTX/TRELLIS, and full QA/upload/read-back.


## E2E runner correction — 2026-10-20

- Previous current-candidate E2E run on oec-2 correctly failed closed before inference because the Python harness still hardcoded expected runner `oec-1`. Added explicit `OEC_EXPECTED_RUNNER` (defaults to oec-1 for backward compatibility) and configured the ordered oec-2 suite to set it to oec-2.
- This changes only runner identity validation. The harness still refuses any active compute process and requires an idle A100 with at least 30 GiB free, current StorageManager status, existing authenticated HF dataset and cache-only QA.


## 2026-10-20 — Storage recovery moved to its authorized runner

- Current oec-2 model prep stopped with `legacy lock recovery is restricted to oec-1/scn30-mn; current identity=oec-2/scn30-mn`. This was a safety policy failure before checkpoint downloads, not model inference.
- Added an ordered `recover-storage-locks` stage on oec-1; it uses only the conservative existing recovery helper, which checks lock age, owner PID, absence of a lease manifest, and invariant reserve size before calling StorageManager `--resume`.
- Model jobs on oec-2 are now gated on the authorized recovery job succeeding and independently verify there are no remaining pause locks or lease manifests. Any unresolved lock/lease blocks inference; no reserve file is manually deleted or resized.


## Actual live results and fixes — 2026-10-20

- Existing AudioGen notebook live smoke on oec-2 passed, producing a non-silent 3.0s WAV of 96,078 bytes; SHA-256 `30b67f2c8f0dbfd017a319705091f607cada98f44f086bf5e545a0cff4893c92`. Artifact is linked in docs/checklist.md.
- Dedicated AudioGen Gradio UI callback did not run because Gradio's loopback health check was intercepted by the runner's HTTP proxy. Updated the callback harness to append localhost/127.0.0.1/::1 to both NO_PROXY and no_proxy before importing Gradio and disabled Gradio analytics for the local test. Rerun must prove it works.
- MusicGen generation failed closed at GPU selection (`no eligible idle A100; no process was killed or signalled`). We must inspect current physical GPU owners and retry only after a device is genuinely available; do not bypass the guard or terminate another process.

 
## Current live test findings (2026-10-20)

- AudioGen existing notebook generation passed on `oec-2` with a valid, non-silent 3-second WAV. The separate Gradio app/callback failed because of Gradio 4.44.1 / gradio_client 1.3.0 boolean-schema handling. An isolated runtime shim was added; next live run must prove the UI root plus callback pass.
- Speech environment prep was blocked by an obsolete hard-coded 40 GB reserve floor. Current StorageManager status reported 29.83 GB existing reserve in the 280 GB model allocation; the environment prep does not need a larger reserve. Its gate now uses the configured model minimum and never resizes the reserve.
- MusicGen did not load/generate: its GPU admission refused because no physical A100 met the idle/process/memory/utilization policy. A diagnostic audit was added; do not weaken the guard or stop other owners.
- No all-model pass and no joined QA/upload pass yet. Verify the output for each provider and the Hugging Face remote manifest/part hashes before checking off the corresponding items.


## Latest confirmed live evidence and blockers — 2026-10-20

- AudioGen model inference passed in `phase1` on `oec-2` physical A100 4: 3s mono/16kHz WAV, 96,078 bytes, SHA-256 `c543c2e6a45a44a89f45d22a135ac5000b154f0025d2e93592a31c672589e7ba`, 5.155 GiB peak allocated VRAM. Its Gradio page returned HTTP 200 but callback failed because the notebook picked runner temp instead of `/tmp` required by `--scratch-output`; the notebook path and static test are corrected in the new candidate.
- MusicGen inference passed in `phase1` on physical A100 4: 3s mono/32kHz WAV, 192,044 bytes, SHA-256 `0cbb209e90f823ef309457410d72ac53899d378b5df6d19db476189d30e61d7b`, 4.352 GiB peak allocated VRAM. Its job then failed at an incorrect shell copy of `.info.json`; the workflow copy path is corrected to match `Path.with_suffix`.
- GPU admission/sharing contract tests and static/storage regressions passed at `d037bfff24f7ffef7bc2ac640071f6eb6d3dea71` in [run 39402803588](https://github.com/CalamityStriker/OEC/actions/runs/39402803588).
- The live speech job prepared its environment but failed before invoking Kokoro/Whisper/Qwen3-ASR because the smoke entrypoint lacked the repository root on `sys.path`. The root import path is fixed in the candidate, awaiting a new live run.
- ACE-Step was skipped due to the speech job's fail-fast dependency. It has not been verified. Do not check it off without a real generated FLAC, validated metadata, and a passing Gradio event request.
- Prior live run [39388844316](https://github.com/CalamityStriker/OEC/actions/runs/39388844316) generated/validated an LTX MP4 and TRELLIS GLB in `phase1_ltx` and `phase2_3d`; repeat on current candidate.
- Remaining: real Gradio event callbacks for both AudioCraft models; live Kokoro/Whisper/Qwen3-ASR; ACE-Step; FLUX PNG → TRELLIS GLB; joined Brain/LTX/Qwen2-VL QA, chunked HF upload, remote manifest/part hash read-after-write; model-specific purge-safety and restart tests. Keep cache purge off and preserve `.storage_reserve.bin`.

## Media readiness and OEC_Deploy integration — 2026-10-20

- [x] Implemented a read-only provider readiness report separating actual HTTP health/model-loaded state from environment and checkpoint/cache preflight.
- [x] Added a downstream integration guide for OEC_Deploy; the downstream repository is intentionally unchanged.
- [x] Updated the media service supervisor to use shared process-aware fail-closed GPU admission plus model-specific free-VRAM floors.
- [x] Fixed live-test defects found in FLUX's mocked GPU inventory, QA status handoff, AudioGen/MusicGen scratch output locations and MusicGen metadata filename.
- [x] Independent ACE-Step acceptance now runs even when the speech acceptance step fails; the job still reports overall failure unless both groups pass.
- [ ] Exact-head validation for this candidate is pending.
- [ ] Verify ACE-Step real music generation and Gradio event acceptance; separately validate Kokoro synthesis, Whisper transcription and Qwen3-ASR transcription.
- [ ] Complete current-source FLUX-to-TRELLIS and the HF upload/remote hash read-back path.
- [ ] Add supervised HTTP job APIs for AudioGen and MusicGen before they are marked available to OEC_Deploy.
## Latest Gradio UI event evidence — 2026-10-20

- AudioGen's real Gradio event acceptance passed in run 39404646877 on old candidate SHA a558d2d52a5f6f93afabd5c0aaa14f6e721cf844: HTTP 200, gradio_client event completed, WAV 96,044 bytes, SHA-256 02341fb8a7c71886fd8b837cf1f6558c0d26b6a8f5cce45949cdade5e5ceda58, 5.155 GiB peak allocated.
- Gradio 6's API name for the speech notebook did not match /predict. Candidate harness now submits by function index 0 for the single-function Interface; re-run required.
- MusicGen run is still in progress, and ACE-Step is not yet accepted. Wait for the actual job/artifact results before updating statuses.
## AudioCraft Gradio live callbacks verified — 2026-10-20

- AudioGen and MusicGen both passed their actual Gradio HTTP event callbacks on run 39404646877 (source SHA a558d2d52a5f6f93afabd5c0aaa14f6e721cf844). The artifacts and SHA-256 values are recorded in docs/checklist.md and test.json.
- This does not make either provider HTTP-ready for OEC_Deploy; neither has a supervised OEC /v1/jobs API. Use the readiness report status NOT_EXPOSED.
- Speech/ASR requires the Gradio 6.0.1 fn_index=0 fix validation; ACE-Step remains pending independent model/API acceptance.