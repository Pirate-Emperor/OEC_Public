## 2026-10-19 — Media inference status at 18:28 IST

AudioGen passed on A100 in [run 39240127736](https://github.com/Killer4K-N/OEC/actions/runs/39240127736), producing a valid 3-second mono 16 kHz WAV. Standalone TRELLIS/LTX sidecars passed in [run 39240127757](https://github.com/Killer4K-N/OEC/actions/runs/39240127757) with a validated GLB and ffprobe-validated H.264 MP4. MusicGen's 4/4 offline contracts passed in [run 39254306725](https://github.com/Killer4K-N/OEC/actions/runs/39254306725), but generation did not run because its model snapshot was incomplete and the runner could not reach Hugging Face. FLUX→TRELLIS [run 39254474617](https://github.com/Killer4K-N/OEC/actions/runs/39254474617) failed before inference on two path-test fixture errors. ACE-Step's stricter cache gate was committed at b84398af but live generation remains unverified; its latest bootstrap was cancelled before assignment.

The current scope is setup and inference of the media models, followed by a connected local orchestration and artifact validation—not full-model training or OEC-Play deployment. The user confirmed Actions runner quota reset and removed the prior $0-only prerequisite; StorageManager admission and the shared GPU concurrency group remain separate. Next: repair the FLUX fixtures, rerun visual inference, validate ACE-Step with a managed bootstrap, diagnose MusicGen cache/egress, then build the combined multimodal job.

## 2026-10-19 — AudioGen live inference re-accepted on the current OEC model branch

Run [39240127736](https://github.com/Killer4K-N/OEC/actions/runs/39240127736), job [118018656307](https://github.com/Killer4K-N/OEC/actions/runs/39240127736/job/118018656307), completed successfully on oec-1 / scn30-mn, commit [21f576b774e25c7766d7c2876b793366918f0436](https://github.com/Killer4K-N/OEC/commit/21f576b774e25c7766d7c2876b793366918f0436). The headless AudioCraft notebook ran all five code cells, loaded the cached facebook/audiogen-medium model and generated a 3-second mono 16 kHz PCM WAV. Generation time: 26.737 seconds; output 96,078 bytes; SHA-256 6be1acb0cf36cacfc5ba4464ebbecb7f6f3bbe46f8e1e3bdbf88f2eef80bde3b; peak VRAM 5.155 GiB allocated / 5.385 GiB reserved. The six notebook static tests passed. Artifact: [12181271517](https://github.com/Killer4K-N/OEC/actions/runs/39240127736/artifacts/12181271517). The WAV was independently reopened and matched the report’s hash, length, rate and duration.

The same commit removes nested StorageManager lease scopes during TRELLIS/LTX generation, adds a boolean remesh option to the TRELLIS API (disabled for the fast smoke only; standalone default remains unchanged), makes audio output-reserve preflight read-only, and adds no-GPU regression tests. Current visual acceptance [run 39240127757](https://github.com/Killer4K-N/OEC/actions/runs/39240127757) is in progress; the TRELLIS and LTX model paths are not yet accepted on this commit. Bootstrap run 39240127730 was cancelled before job assignment and provides no test/inference evidence.

The live StorageManager report showed models at 219.97/280 GB with a 60.04 GB reserve and outputs at 290.02 MB/1 GB with a 734.41 MB reserve. Group quota showed 2.03 TB used against a 2.10 TB hard limit with 69.26 GB headroom under active grace. These are captured readings, not approval for later writes. pip check also warns that thinc 8.3.6 requests NumPy >=2.0.0 while the pinned AudioCraft environment uses NumPy 1.26.4; no package was changed.

# OEC Significant Results

## 2026-10-18 follow-up — guarded model downloads and live acceptance tools

Added an A100-side helper, tools/prepare_media_models.py, to read the current read-only StorageManager status and recent log lines, inspect exact model-cache folders, audit the pre-existing phase1/phase1_ltx/phase2_3d Conda environments, and preflight/download selected model checkpoint groups through the actual OEC StorageManager APIs. It does not launch the daemon, install packages, create environments, or access the reserve file directly. The aggregate plan is 21 GB of model-download budget plus a 2 GB free-space margin, but the helper only downloads after the fresh live preflight succeeds; every model transfer is also gated by a managed write.

Added tools/media_services/smoke_client.py to submit a real loopback request, poll a job, fetch the result, validate WAV/FLAC/transcript structure, and preserve the acceptance artifact under managed outputs. Updated Hugging Face cache verification to validate snapshot symlinks remain inside the intended model cache and resolve to nonempty weights. ACE-Step cache-only readiness checks the selected DiT, VAE, text-encoder and LM weight folders, and the runtime reports initialization failures rather than silently treating a failed load as ready.

Latest local verification of the packaged source: Python compilation passed and 19/19 CPU/mock tests passed (0 failed, 0 errors). These tests do not load model weights or run generation, and the downloader/smoke-client were compiled but not executed against A100.

The assistant cannot directly read the live A100 StorageManager log in this session: the local execution container has no /nlsasfs or ~/OEC mount, and there is no connected SSH/remote-shell tool. Latest user-reported model directory reading (not independently measured by this test): 209 GB used of a 280 GB target, approximately 71 GB nominal free, with a 40 GB positive reserve managed by the user's running daemon. This is distinct from the earlier reported group quota reading of 2.14 TB occupancy, 2.15 TB soft limit and 2.25 TB hard limit.

No actual model downloads, dependency installs, live model inference, cache purges, StorageManager daemon startup or GitHub Actions runs were performed by the assistant. Next on A100: run the helper's status and environment audit, run aggregate preflight, download only if admitted, then run one live artifact acceptance per model in an existing isolated runtime. Do not approve purge until resident re-inference after exact-folder deletion and a separate fresh-restart/reload both pass.


## 2026-10-18 — Media-service prototype and model-cache policy

The current audit separates three different controls: disk-cache purge, live model unload and CUDA allocator cleanup. OEC's filesystem purger only removes cache files; GPU-memory release requires dropping live pipeline/engine references and cleaning device state. Keep cache purge disabled for TRELLIS, FLUX and the new LTX sidecar until a second inference succeeds after deletion of that exact model cache folder. The existing production LTX launch uses `--no-purge`.

Source files for the TRELLIS and LTX sidecars are now committed on the isolated `feat/media-service-sidecars-20261018` branch: `tools/media_services/common.py`, `trellis_api.py`, `ltx_api.py`, `__init__.py`, and `tests/test_media_service_api.py`. The companion ZIP is a convenient snapshot. Local compile checks passed and the fake-provider/fixture suite passed 8/8 tests against the local prototype. This demonstrates API/job validation and artifact-fixture checks only; no TRELLIS/LTX inference, model download, quota-changing write, or live OEC-Play service integration occurred. The timeout check notices overruns only after inference returns; hard termination of a hung CUDA call needs process-level supervision and remains unfinished. The branch source was not independently checked out and re-tested after transfer.

Additional model triage favors ACE-Step 1.5 for music generation, Kokoro-82M for lightweight English speech, SenseVoice/Whisper for speech input, and Hunyuan3D-2.1 as a later geometry baseline. MusicGen/AudioGen weights should remain research-only until their CC-BY-NC 4.0 weight terms are acceptable for the intended product. Provider routing remains deterministic orchestration, not a trained MoE.



The existing experiment ledger also distinguishes prior FLUX/TRELLIS artifact runs from LTX service readiness: the 15 October OEC background-pipeline static suite passed, but it explicitly records `live_ltx_service_start=NOT_RUN`. Therefore the new LTX sidecar must be treated as unverified until it loads on the assigned runtime and produces an MP4 that can be read by ffprobe/a decoder. Historical FLUX/TRELLIS output evidence is linked in the existing result history; this pass did not reproduce those GPU runs.



**OEC-Play integration status:** The companion `hpc-dgx-deployment` source CI [39106225707](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39106225707) finished with Python source validation passing but TypeScript validation failing in `MediaServicesPanel.tsx`: TS2677 at line 145 (optional `JobUpdate.message` conflicts with a required inferred field) and TS18047 at line 149 (`value` may be null). An earlier run also reported Tailwind line-wrap lint errors. OEC-Play service URLs were not configured, no OEC_Deploy files were changed, and no additional Actions run was started from this session.

The original 15-day project deadline could not be recovered from an authoritative start/deadline record in this pass; no remaining-days figure is asserted.

**Last updated:** 2026-10-18T12:36:53.201+05:30 (Asia/Kolkata)
**Branch:** `feat/media-service-sidecars-20261018` (isolated implementation and tracking branch; not merged to main).
**Policy:** This is one cumulative summary of material OEC results. Detailed run-by-run history is in `changelog/CHANGELOG-YYYY-MM-DD.md`; test approaches and parameters are in `test.json`; open work is in `TODO.md`.

## Current status

**Latest notebook acceptance (16 October 2026):** OEC run [38912593770](https://github.com/Killer4K-N/OEC/actions/runs/38912593770) on review branch \`fix/flux-trellis-pipeline-20261015\` passed FLUX-only generation, TRELLIS-only GLB generation, combined-notebook FLUX generation and combined TRELLIS UI startup. The standalone TRELLIS GLB was 5,457,384 bytes (SHA-256 \`7db7600e9dd9de6c1549eaf06f08cd687a55e8d62465754b426c521501ed9183\`), with 51,658 vertices and 97,935 faces in 337.646 s. The combined notebook's TRELLIS check was startup-only; no end-to-end combined image-to-mesh transaction was tested. All four modes were cache-only and used local scratch; code changes remain on the development branch and have not been merged into main.

**Frozen-weight readiness remains blocked:** read-only audit [38924202279](https://github.com/Killer4K-N/OEC_AireOS_Freezed/actions/runs/38924202279) finished successfully as a diagnostic job but set semantic status \`BLOCKED\` because PEFT is missing, a fresh quota snapshot is unavailable, managed models storage is in WARNING / group soft-quota overage, model/license/task approvals are incomplete, and dataset provenance/schema/group-safe splits are unverified. Audit flags explicitly say no training and no downloads started. No fine-tuning improvement can be claimed.


**The latest review candidate adds supervised local/multi-node background services, detailed CLI help, TRELLIS existing-image-folder mode, and separate-GPU combined Gradio services; hosted validation is green (86/86 tests), while live three-node launch, browser/Gradio and folder-inference acceptance are still pending.** PR [#11](https://github.com/Killer4K-N/OEC/pull/11) is open and not merged. Source code/workflow/notebook changes remain isolated on `fix/flux-trellis-pipeline-20261015`; main is tracking-only.
**OEC now has standalone FLUX and TRELLIS runtime evidence and a successful combined FLUX → TRELLIS.2 run on a review branch.** The FLUX stage generated and validated a 512×512 PNG (255,946 bytes; SHA-256 2b05b417eb928a93511c88ee2d45b21357419720c31917a8e5129434eed6afbb), which was passed as the exact TRELLIS input. OEC run [38725376076](https://github.com/Killer4K-N/OEC/actions/runs/38725376076), job 116389784906, ended with report status PASS after 419.848s on oec-1 / host scn30-mn. TRELLIS exported [artifact 11967418646](https://github.com/Killer4K-N/OEC/actions/runs/38725376076/artifacts/11967418646): a 3,484,804-byte GLB (SHA-256 74e3654625a0662302ecb1bf1c0c79885833563753b6a30acbeee45a5c4b360e). Independent trimesh reopen passed with 54,597 vertices and 93,617 faces.

The preceding failed combined run [38723286765](https://github.com/Killer4K-N/OEC/actions/runs/38723286765) exposed a missing subprocess import in the TRELLIS scratch-filesystem findmnt guard and an over-permissive GPU IDLE predicate (100% utilization with no visible compute process). The import and forced-findmnt regression test were added; the idle GPU predicate now requires known utilization at or below 5%, with re-sampling for up to 180 seconds. Guarded hosted CI [38725202281](https://github.com/Killer4K-N/OEC/actions/runs/38725202281) passed 58/58 tests, Python compilation and all four notebook checks.

These source changes remain on review branch fix/flux-trellis-pipeline-20261015 and are not merged into main. The combined run was cache-only with downloads/installations/shared-output writes disabled. Fresh authoritative quota telemetry remains unresolved; managed shared writes and missing model/dependency downloads continue to fail closed.
## 2026-10-15 20:29 follow-up — cluster services and notebook isolation

- PR [#11](https://github.com/Killer4K-N/OEC/pull/11) now includes the cluster coordinator and a per-user example config template with profiles for a three-node LTX pool, mixed FLUX/TRELLIS/LTX services, four FLUX one-shot jobs, combined FLUX→TRELLIS, and TRELLIS folder batch.
- `tools/oec_service_manager.py` has action/service-specific `--help`; the help/cluster regression suite exercises every advertised action/service, profile validation, plan output, and cluster dry-run without contacting GPUs.
- The combined notebook no longer loads both full model pipelines in the same kernel/GPU. TRELLIS stays in the notebook on GPU 0 and FLUX launches as a supervised child on GPU 1 by default (ports 7862/7863); these IDs must be distinct and free.
- Final current-head hosted CI [run 38761087455](https://github.com/Killer4K-N/OEC/actions/runs/38761087455) passed 86 tests, Python compilation, and all four notebook JSON/Python-cell checks after aligning the example per-node Conda root with the project-root `Conda/bin/activate` layout. The preceding run [38760561720](https://github.com/Killer4K-N/OEC/actions/runs/38760561720) passed before that template-path adjustment.
- The new cluster profile has not been run against the actual nodes; actual browser Gradio submission and existing-image-folder TRELLIS inference were not run. The earlier combined cache-only single-image inference remains separate evidence. Fresh quota telemetry remains missing, so no model/dependency downloads or managed shared-output writes were attempted.
- The code, config template, notebooks, tests and service manager remain on the open, unmerged source PR. Only results/changelog/TODO tracking was updated on main.

## Material fixes delivered in the feature branch

- **TRELLIS Python entry point:** `pipeline_trellis_3d.py` supports a lightweight environment check, one-image GLB generation, and optional Gradio rendering. GPU, mode, input/output, model ID/cache/repository, offline mode, host/port, attention backend, and quality/performance controls are configurable. Cache lookup precedes download and missing-model downloads require fresh quota admission. Gradio share defaults off.
- **TRELLIS Jupyter:** cache-first snapshot resolution, valid loader API usage, attention preflight before importing TRELLIS, installation guarded by fresh storage admission, setup ordering for the combined FLUX/TRELLIS notebook, safe re-runs, and cleaned execution/tunnel notes.
- **Standalone FLUX Jupyter:** moved to the `phase2_3d` kernel; removes a fixed-PID kill, hard-coded GPU 2, Jupyter self-upgrade, unpinned GitHub-main Diffusers install, unconditional cache purge and repeat pipeline loading. Adds safe process inspection, compute hostname and SSH tunnel instructions, a configurable Gradio port (7864), cache-first model resolution, quota-gated download/dependencies, public sharing off, and image/seed/file outputs.
- **Future-model convention:** `docs/model_entrypoint_convention.md` records the reusable pattern: notebook and standalone Python entry point, check/generate/optional-Gradio modes, pre-import GPU selection, storage admission, cache preservation, and configurable runtime options.
- **QA safety:** `qa_compliance_worker.py` now chooses GPU visibility before importing PyTorch, accepts `--gpu`, requires fresh quota before downloading a missing QA model, and retains shared cached weights by default. Regression tests enforce these guarantees.
- **Shared path consistency:** plural compatibility aliases now resolve to the singular canonical directories and report `ALIAS_OK`. Canonical directories were not renamed.
- **Persistent tracking:** this repository now tracks a single `TODO.md`, one structured cumulative `test.json`, a cumulative `result.md`, and the daily file `changelog/CHANGELOG-2026-10-11.md`.

## Verification results

Three-runner offline/static matrix: [run 38157725815](https://github.com/Killer4K-N/Connector_1/actions/runs/38157725815), feature source revision `624e26d84d997e72b4b890ce7e5c654598d0c2b8).

| Suite per runner | Passed | Result |
|---|---:|---|
| TRELLIS/entry-point/notebook | 17 | PASS |
| AudioCraft notebook | 5 | PASS |
| QA queue recovery + worker guards | 10 | PASS |
| Path aliases | 6 | PASS |
| **Total per runner** | **38** | **PASS** |

All three labels `connector-1`, `connector-2`, `connector-5` passed, giving **114 successful test executions**. These are static/unit tests and do not demonstrate real model inference.

Latest targeted sync/audit: [run 38157960859](https://github.com/Killer4K-N/Connector_1/actions/runs/38157960859). It copied the explicitly scoped notebook/Python/test/documentation targets, reported staged validation PASS, the same four suite results (17/17, 5/5, 10/10, 6/6), and verified path aliases. QA queue mutation was not performed. The workflow is marked failure/incomplete because runtime installation and inference remain blocked by quota admission.

A prior isolated TRELLIS smoke on October 9 produced a nonempty **8,950,028-byte GLB**, reopened its geometry, and reported `TRELLIS_IMAGE_TO_3D_SMOKE=PASS` ([run 37942265623](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623)). That environment was an isolated scratch environment, not the current shared `phase2_3d`.

## Confirmed remaining blockers

1. **Storage/quota:** all three compute runners lack a fresh OEC quota snapshot and do not have `quota_check` installed. The prior connector-1 attempt also failed to resolve the login host; connector-2/5 lack SSH. Do not invent quota values or bypass admission.
2. **TRELLIS CUDA attention (closed for the validated Connector_1 path):** earlier probes reported a CUDA operator failure, but final run [38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418) passed the same xFormers CUDA operator check in `phase2_3d` and then completed model inference/export. No package upgrade was needed for this cache-only run. This result validates connector-1's current environment/path, not every compute host or every notebook/UI session.
3. **TRELLIS model cache (closed for the validated Connector_1 path):** earlier resolution logic reported a miss, but the corrected resolver found snapshot `af44b45f2e35a493886929c6d786e563ec68364d` and completed generation without downloading weights. Other hosts have not been newly revalidated; if a model is missing elsewhere, fresh quota admission is still required before download.
4. **Earlier FLUX package mismatch (closed for the validated oec-1 path; other environments remain unverified):** the Oct 14 investigation found diffusers==0.40.0.dev0 attempting to import get_cached_repo_tree, which was absent from huggingface-hub==0.36.2 in that environment. The Oct 15 cache-only OEC runtime now proves generation works in the runner's phase2_3d environment with diffusers==0.37.0, huggingface-hub==0.36.0 and transformers==4.56.1. Do not install or replace packages on other hosts unless fresh quota admission passes; do not assume every Notebook/session environment has the same working stack.
5. **QA worker liveness:** live queue counts are `FAILED_MISSING_FILE=78`, `PENDING=144`, `PENDING_QA=2`, `PROCESSING_QA=1` (225 rows total). The existing QA worker PID 2529002 on connector-2 was observed in stopped state `T`, attached to an interactive shell/session, and its in-memory code predates the new guards. It was not resumed or duplicated. Replace the old process safely after verifying ownership and prerequisites, then run exactly one worker with the guarded source.
6. **GPU utilization:** sampled A100 GPUs showed 0% utilization on the three connector hosts. On connector-2 the upload/video daemons were sleeping between polls; the QA process was stopped. After safe restart and a real workload, re-check utilization and queue latency before concluding that active inference is inefficient.
7. **AudioCraft:** `phase1` imports AudioGen and `audio_write`, but `pip check` reports `thinc==8.3.6` requiring NumPy >=2 while the environment has `numpy==1.26.4`. The original wheel-build trace was not found in bounded recent logs; no Phase1 packages were modified. Capture the exact build traceback and plan an isolated, compatible environment before any install changes.
8. **Jupyter end-to-end:** notebook JSON and Python cells pass static tests; a temporary Jupyter Server API/kernel smoke previously passed. The user's normal browser/tunnel session and complete model inference through the UI remain unverified.

## Operational boundaries retained

- All edits are on the feature branch and the targeted live sync path; no changes were merged into `main`.
- No force checkout/reset/stash/clean of the dirty OEC worktree.
- No packages were installed/uninstalled and no model weights were downloaded in the latest sync.
- No production QA rows were changed and no worker signals were sent.
- The existing `.storage_reserve.bin` and shared cache/data are preserved.
- Only the authorized connectors `connector-1`, `connector-2`, and `connector-5` were used.


## Latest tracking-file sync

- [Connector-1 sync run 38160976083](https://github.com/Killer4K-N/Connector_1/actions/runs/38160976083) fetched feature revision `70411afa152a862e4356cb09ccdc83cb1278b2fc`, validated `TODO.md`, `test.json`, `result.md`, and the daily changelog/index, and copied them to the live shared OEC checkout.
- Marker `TRACKING_FILES_VALIDATION=PASS`; the same live sync run passed 17 TRELLIS/entry-point tests, 5 AudioCraft notebook tests, 10 QA worker/queue tests, and 6 path-alias tests.
- The workflow's final status remains **incomplete** because storage admission is blocked: no new packages installed, no model downloaded, and no TRELLIS inference attempted. Treat it as successful targeted source/tracking sync plus static validation, not as runtime model acceptance.
- The canonical daily log is `changelog/CHANGELOG-2026-10-11.md`; `TODO.md` remains the only TODO list and `test.json` the single cumulative experiment register.


## Compatibility-reference review

Official Diffusers release notes list Flux2 Klein support in the v0.37.0 release. The current official Hugging Face Hub download docs expose `get_cached_repo_tree`, which the shared `diffusers==0.40.0.dev0` build tries to import from installed `huggingface-hub==0.36.2` and fails. References: [Diffusers releases](https://github.com/huggingface/diffusers/releases), [Hub download API docs](https://github.com/huggingface/huggingface_hub/blob/main/docs/source/en/package_reference/file_download.md), [Hub utility PR workflow](https://github.com/huggingface/huggingface_hub/actions/runs/29011952200). This supports the proposed released dependency-set direction; it does not imply that the stack was installed or that an actual FLUX image was generated. The latest experiment file `test.json` contains 14 structured experiment entries.


## Final synchronization verification — run 38161408008

- The final corrected orchestration run [38161408008](https://github.com/Killer4K-N/Connector_1/actions/runs/38161408008) ran `bash -n` successfully, staged and copied `TODO.md`, `test.json`, `result.md`, the daily changelog and its index, and reported `TRACKING_FILES_VALIDATION=PASS`.
- All offline suites passed again: 17 TRELLIS/entrypoint, 5 AudioCraft notebook, 10 QA worker/queue, and 6 path-alias tests. The aliases remain verified; the QA database was report-only.
- The run is marked incomplete because storage admission is blocked. This is a clean source/tracking sync and static-validation result, **not** a successful live TRELLIS/FLUX inference result.
- The experiment register has 16 entries and records the original marker syntax failure, the `bash -n` prevention, the final successful sync-stage checks, and all remaining runtime blockers.


## Final verified shared-tree sync — 38161747478

The latest syntax-checked sync [38161747478](https://github.com/Killer4K-N/Connector_1/actions/runs/38161747478) emitted `SYNC_SCRIPT_SYNTAX=PASS`, `TRACKING_FILES_VALIDATION=PASS`, and `STAGED_NOTEBOOK_AND_CLI_VALIDATION=PASS`; it copied the current tracking files and reran all four suites successfully (17/17, 5/5, 10/10, 6/6). The workflow remains incomplete solely at storage admission; no install/model download/inference or queue mutation occurred. `test.json` now holds 17 experiments covering the source fixes, diagnostics, syntax regression and final sync.



## 2026-10-12 — Runtime blocker remediation (guard changes, not runtime acceptance)

The last shared-tree action, [38161901000](https://github.com/Killer4K-N/Connector_1/actions/runs/38161901000), passed source/static validation but failed at the mandatory quota admission because the 15-minute quota snapshot was missing or stale. Actual CUDA attention, TRELLIS model download, TRELLIS inference, FLUX image generation, AudioCraft repair, and QA-worker replacement therefore remain unverified. Its read-only queue report still had 225 rows (78 `FAILED_MISSING_FILE`, 144 `PENDING`, 2 `PENDING_QA`, 1 `PROCESSING_QA`); no queue mutation occurred.

An isolated Connector_1 branch, [`ops/runtime-remediation-20261012`](https://github.com/Killer4K-N/Connector_1/tree/ops/runtime-remediation-20261012), now carries source-level corrections prepared for action validation:
- Enforced `require_fresh_quota=True` in all 12 package/model write-admission calls in the main sync helper and six QA write-related admission calls.
- Restricted the candidate `xformers==0.0.29.post2` install to a prebuilt wheel for the existing Torch 2.6.0+cu124 runtime.
- Corrected AudioCraft's dependency target to `numpy==1.26.4`, `spacy==3.7.6`, and `thinc==8.2.5`, using binary wheels only so the existing Thinc 8.3.6/NumPy 1.26.4 mismatch cannot remain silently installed and cannot trigger an avoidable source build.
- Hardened QA recovery with an explicit Slurm `--gpu` argument, parent/session/TTY/job identity revalidation, and a rule to keep the previously stopped worker untouched until the replacement job is RUNNING.
- Added the October 12 changelog to the explicit snapshot and staging allowlists.

Official upstream references reviewed: Microsoft [TRELLIS.2 README](https://github.com/microsoft/TRELLIS.2) and [setup.sh](https://github.com/microsoft/TRELLIS.2/blob/main/setup.sh), [xFormers release changelog](https://github.com/facebookresearch/xformers/blob/main/CHANGELOG.md), [Diffusers v0.37.0 FLUX.2 API](https://huggingface.co/docs/diffusers/v0.37.0/en/api/pipelines/flux2), [AudioCraft requirements](https://github.com/facebookresearch/audiocraft/blob/main/requirements.txt), and the upstream [TRELLIS.2 setup issue #111](https://github.com/microsoft/TRELLIS.2/issues/111). These sources support scoped compatibility candidates; they do not substitute for testing the actual installed environment.

**Acceptance status:** source edits are committed but the combined remediation workflow has not yet reported. Actual package/model writes are still prohibited until authoritative quota telemetry is available. No package was installed, no model was downloaded, no shared cache or reserve file was purged/resized, no QA row changed, and no worker was signaled by the source-editing step. No merge to `main`.


## 2026-10-14 — Confirmed quota telemetry blocker and live checkout divergence

The OEC feature branch `fix/trellis-gradio-notebooks-20261011` is at `2543b26d2888e667c6443c984259f84ac5b6c142`, 111 commits ahead and 0 behind OEC `main` (`82346c0753e139b92240f53734eb48d2113ed9ad`). No main-branch changes or merge were made.

A focused read-only probe was committed on Connector_1 branch [`diagnose/oec-storage-telemetry-20261014`](https://github.com/Killer4K-N/Connector_1/tree/diagnose/oec-storage-telemetry-20261014), commit [`70d9000ba48cfdd6a6413276d7a4d4fe2888ad17`](https://github.com/Killer4K-N/Connector_1/commit/70d9000ba48cfdd6a6413276d7a4d4fe2888ad17). [Run 38555689884](https://github.com/Killer4K-N/Connector_1/actions/runs/38555689884) completed successfully; job `115824133792` on `connector-1` / `scn17-mn` passed Python compile, read-only report generation, JSON validation, and artifact upload ([artifact 11888967874](https://github.com/Killer4K-N/Connector_1/actions/runs/38555689884/artifacts/11888967874)).

Confirmed report observations:
- Configured quota snapshot `/nlsasfs/home/lmedge/rahkus/.cache/aieros/quota_snapshot.json`: **MISSING**; freshness threshold 900 seconds.
- `quota_check`: **NOT_FOUND** on this compute runner.
- Model path `/nlsasfs/home/lmedge/rahkus/aireos_models` resides on shared Lustre. Measured filesystem free space was 9,383,140,028,837,888 bytes (8,738,730.13 GiB). This is filesystem capacity only, **not** authoritative user/project quota.
- Two A100-SXM4-40GB GPUs were visible. No CUDA attention operator or model inference was tested.
- Live OEC checkout: HEAD `081aaf34f6379873bdc925d1dcf6b9c3d50349d3`, no branch name reported, and ten tracked dirty paths including config, three notebooks, QA worker, storage config and runner-control tooling. No sync/reset/clean occurred.
- Reserve discrepancy: run [38175212786](https://github.com/Killer4K-N/Connector_1/actions/runs/38175212786) had logged `STORAGE_MANAGER_RESERVE_BYTES=37190724326`; October 14 read-only stat found `.storage_reserve.bin` size 33,580,119,505 bytes, allocated 33,580,130,304 bytes, non-sparse, mtime `2026-10-12T20:33:53Z`. Cause/path equivalence has not been established. No reserve operation is authorized or performed.

Conclusion: **diagnostic PASS / storage admission BLOCKED**. Do not replace `require_fresh_quota=True` with filesystem-only admission for large writes on shared Lustre. Obtain genuine quota values through an approved login-node/site route and publish them using `tools/quota_snapshot.py` only from actual `quota_check` output; if the route remains unavailable, repair approved access/transport or arrange a site-approved producer before retrying package/model writes.

The separate [run 38175212786](https://github.com/Killer4K-N/Connector_1/actions/runs/38175212786) connector-2 QA job also failed with `scontrol: stepd_available: Couldn't find nodename` and `sacct` connection refusal to `localhost:6819`. This is an independent Slurm/scheduler issue and must not be confused with the quota telemetry failure.

No package was installed, no model was downloaded, no shared cache/reserve was changed, no queue row was mutated, and no process was signalled. TRELLIS shared-environment inference, FLUX generation, full notebook UI execution, AudioCraft repair/generation, and QA worker replacement remain unverified. The historical isolated TRELLIS GLB success remains isolated-environment evidence, not shared `phase2_3d` acceptance.


## 2026-10-14 — Quota-gated notebook/CLI write paths and static regression pass

Candidate branch: [`fix/storage-admission-write-guards-20261014`](https://github.com/Killer4K-N/OEC/tree/fix/storage-admission-write-guards-20261014), source commit [`4ade353d566bfeb525949f5f4c1905a1ae1e135c`](https://github.com/Killer4K-N/OEC/commit/4ade353d566bfeb525949f5f4c1905a1ae1e135c); backup reference [`backup/oec-before-write-guards-20261014`](https://github.com/Killer4K-N/OEC/tree/backup/oec-before-write-guards-20261014). OEC `main` remains `82346c0753e139b92240f53734eb48d2113ed9ad`.

The source audit found several notebook/CLI paths using `require_fresh_quota=False`. Also, `managed_storage_operation()` is a serialization/reserve coordinator and does not enforce freshness by itself. The candidate now explicitly checks fresh quota before managed operations and rechecks inside the lock for model and output writes; TRELLIS setup package installs and source clones are routed through a quota-gated managed operation; output directory creation is deferred until after admission. The CLI also preflights the actual destination's existing ancestor before making a custom output directory. No change was made to shared storage manager defaults or live machine config.

[Hosted workflow run 38559330370](https://github.com/Killer4K-N/OEC/actions/runs/38559330370), job `115836225568`, on commit `4ade353...` passed 27/27 static tests (12 TRELLIS notebook, 5 CLI/easy-run, 5 AudioCraft notebook, 5 new storage-admission regression tests), Python compilation and all four notebook JSON checks. The prior [run 38558509401](https://github.com/Killer4K-N/OEC/actions/runs/38558509401) failed the new guard tests, revealing the missing AudioCraft under-lock recheck plus a too-specific assertion; both were corrected before the final pass. This proves source/static guard consistency, not model inference.

A separate offline/cache-only FLUX smoke on Connector_1 was blocked before torch/Diffusers import and inference. [Run 38559255790](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790) confirmed the FLUX.2 Klein cache snapshot exists, but GPU0 had 31,536 MiB free and one active compute process, GPU1 had 39,902 MiB free and one active compute process; the test requires an otherwise idle GPU and did not proceed. The first attempt [38558972259](https://github.com/Killer4K-N/Connector_1/actions/runs/38558972259) also stopped before inference. No PNG was generated and no process was changed.

Retrospective review of [run 38175212786](https://github.com/Killer4K-N/Connector_1/actions/runs/38175212786), job `114576061200`, corrects an older stale summary: that pre-admission baseline on `scn17-mn` had `xformers==0.0.29.post2`, CUDA memory-efficient attention PASS, Flux2 Klein import PASS with Diffusers/Hub/Transformers `0.37.0/0.36.0/4.56.1`, and FLUX cache HIT; TRELLIS.2-4B cache was MISS. That action still failed at the storage admission gate and never completed inference. Earlier xformers.post1 failure logs remain valid observations from an older state; cause of version change is unknown.

**Current acceptance remains partial:** source guard regressions and static validation are fixed; authoritative fresh-quota telemetry is still missing; shared TRELLIS full inference/GLB geometry, FLUX generated PNG, Jupyter end-to-end runs, AudioCraft generation, and QA worker recovery remain unverified/blocked. No package install, model download, live checkout sync/reset, cache purge, reserve modification, QA queue mutation, process signal or merge to `main` occurred.

Upstream references consulted for the broader compatibility context (none substitutes for local validation): [TRELLIS.2 setup](https://github.com/microsoft/TRELLIS.2/blob/main/setup.sh), [TRELLIS.2 issue #111](https://github.com/microsoft/TRELLIS.2/issues/111), [xFormers changelog](https://github.com/facebookresearch/xformers/blob/main/CHANGELOG.md), [Diffusers FLUX.2 API docs v0.37.0](https://huggingface.co/docs/diffusers/v0.37.0/en/api/pipelines/flux2), and [AudioCraft requirements](https://github.com/facebookresearch/audiocraft/blob/main/requirements.txt).


## Post-documentation validation — 2026-10-14

The tracking-only documentation commit [`dac91f09bc6cecd896e38213072fe19142d30390`](https://github.com/Killer4K-N/OEC/commit/dac91f09bc6cecd896e38213072fe19142d30390) triggered [run 38559861094](https://github.com/Killer4K-N/OEC/actions/runs/38559861094), which also passed 27/27 static tests, Python compilation, and four notebook JSON validations. The tested source files were unchanged from `4ade353...`, so this confirms reproducibility of the candidate suite, not an additional runtime success.


## 2026-10-14 — TRELLIS asset proof, cache fixes, and current runtime state

### Source fixes on the candidate branch

Latest candidate commit [`f571f508fc693d2afd96c17544702d64a0c29c27`](https://github.com/Killer4K-N/OEC/commit/f571f508fc693d2afd96c17544702d64a0c29c27) adds a fallback in the TRELLIS CLI to detect actual local `.safetensors` shards when the normal Hugging Face cache index reports a miss. The combined TRELLIS/FLUX notebook tries the known FLUX cache in both `aireos_models` and `aireos_models/hub`. TRELLIS and FLUX output admission happens before costly inference, and generated files are checked after saving; the CLI validates the GLB header/length, JSON chunk, and nonempty mesh accessors.

[Action run 38571665298](https://github.com/Killer4K-N/OEC/actions/runs/38571665298) passed the 28-test hosted suite (12 TRELLIS notebook + 5 CLI/easy-run + 5 AudioCraft notebook + 6 storage-admission tests), Python compilation, and notebook JSON checks. No main-branch merge or shared runner edit was made.

### Confirmed TRELLIS asset generation — historic run, independently validated today

[Connector_1 run 37942265623](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623), job `113859380847`, recorded `PIPELINE_LOAD=PASS`, `INFERENCE=PASS`, and `GLB_EXPORT=PASS`. The generated `test_100k.glb` is 8,950,028 bytes. The exact output was recovered from [artifact 11622412194](https://api.github.com/repos/Killer4K-N/Connector_1/actions/artifacts/11622412194/zip) and independently validated locally on October 14:
- GLB 2.0 magic, header, declared length and JSON chunk all valid.
- One mesh and one primitive; nonempty position and index accessors; 2 textures and 1 material.
- `trimesh` reopen passes with 97,783 vertices and 92,819 faces.
- SHA-256: `ede239663f21023640356920a5eff129fd8bb1077f914e8ff19fcb720b7ece4d`.

This is **direct proof TRELLIS has generated a genuine 3D asset**. It is the output of the earlier isolated-environment run, not a fresh result from the current October 14 attempt. [The recovered GLB is available here](sandbox:/mnt/data/TRELLIS2-historical-validated-asset.glb).

### Current shared-runner asset attempt — blocked before inference

Latest offline smoke [run 38571363231](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231) on `scn17-mn` found the cached model snapshot (`microsoft/TRELLIS.2-4B`) with 7 safetensors files totaling 14,819,870,530 bytes, the existing TRELLIS source checkout and official input `T.png`. It verified `/tmp` is local ext4, separate from the shared Lustre model mount. It then stopped with `BLOCKED_GPU_OCCUPANCY`: no GPU had zero active compute processes and at least 30,000 MiB free. It did not load the pipeline, start inference, export a new GLB, install packages or download model weights. Its report is [artifact 11897043384](https://api.github.com/repos/Killer4K-N/Connector_1/actions/artifacts/11897043384/zip).

### FLUX status and unresolved blockers

FLUX.2 Klein model weights are cached at `/nlsasfs/home/lmedge/rahkus/aireos_models/models--black-forest-labs--FLUX.2-klein-4B/snapshots/e7b7dc27f91deacad38e78976d1f2b499d76a294`. Historical baseline [run 38175212786](https://github.com/Killer4K-N/Connector_1/actions/runs/38175212786) passed the Flux2 Klein import and xFormers attention checkpoint on that observed environment. The current cache-only image smoke still has not generated a PNG: earlier read-only diagnostics found an active compute process on each A100, and the safe smoke refused to use either.

Authoritative quota telemetry also remains missing on the compute node (`quota_check` absent; quota snapshot absent). Therefore package/model downloads and quota-gated shared-output writes must remain fail-closed. Do not use large shared-Lustre free-space numbers as the user's/project's quota, do not stop unidentified GPU work, and do not merge additional speculative runtime changes without validating the main workflow.

**Disposition:** TRELLIS/FLUX source/cache guard fixes and static validation **PASS**; historical TRELLIS real GLB generation and geometry reopen **PASS**; current shared TRELLIS inference and current FLUX image generation **BLOCKED pending idle GPU**; new model/dependency downloads **BLOCKED pending authoritative quota telemetry**. Source and cumulative tracking files are integrated on `main`; main-hosted static validation is pending.


## Main branch integration — 2026-10-14

The reviewed TRELLIS/FLUX source fixes, static tests/workflow, changelog, TODO, result summary and cumulative experiment JSON are being committed directly to `main` at the user's explicit request. Source basis: candidate `f8ed9453f296594fc2da0cdfd55c32f79f6e1359`; candidate verification [run 38572444007](https://github.com/Killer4K-N/OEC/actions/runs/38572444007) passed 28/28 static tests, Python compilation and four notebook JSON checks. The main-hosted validation result will be recorded in the following tracking-only commit.

The historical GLB's tracked download link points to GitHub artifact [11622412194](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623/artifacts/11622412194). Current shared TRELLIS/FLUX inference remains blocked by active GPU workloads; the authoritative quota snapshot remains missing. No live runner process, reserve, shared model cache, detached checkout or QA queue was changed.


### Main branch validation result — 2026-10-14

Main commit [`9c9d7acc12e47658f37e71840449f8558b42ee2b`](https://github.com/Killer4K-N/OEC/commit/9c9d7acc12e47658f37e71840449f8558b42ee2b) passed [GitHub Actions run 38575822798](https://github.com/Killer4K-N/OEC/actions/runs/38575822798), job `115892512804`: 28/28 static tests (12 TRELLIS notebook + 5 CLI/easy-run + 5 AudioCraft notebook + 6 storage-admission), Python compilation, and 4/4 notebook JSON checks. The cumulative JSON registry now contains 33 experiment/test records, including the run and why it was conducted.

**Still open:** this main CI run did not perform inference. TRELLIS has a real, independently validated historical GLB; current TRELLIS and FLUX attempts remain blocked by active GPU compute processes. Authoritative quota telemetry is missing, so no model/dependency download or bypass was attempted.


### Latest runtime retries after main integration — 2026-10-14

- TRELLIS run [38571363231 attempt 2](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231) (job `115893795773`) stayed blocked by GPU occupancy; report [11899728417](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231/artifacts/11899728417). It did not start model loading or inference and created no new GLB.
- FLUX run [38559255790 attempt 2](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790) (job `115894428716`) again detected the cached model but both A100s had an active compute process. It did not import Torch/Diffusers, run inference or create a PNG.
- These tests were re-run to see whether GPU availability had changed. They are blocked capacity checks, not model-generation failures. Both outcomes are now part of the 35-record experiment registry committed on `main`.

The remaining acceptance gate is a verified idle GPU for fresh TRELLIS and FLUX inference, followed by GLB geometry and PNG decoding/hash validation. The current quota snapshot is still missing, so downloads and shared storage writes remain fail-closed.


## 2026-10-14 — TRELLIS cache-only loader defect isolated; targeted fix under validation

The latest current-code action [38587490301](https://github.com/Killer4K-N/Connector_1/actions/runs/38587490301), job \`115933256897\`, passed the 7 existing admission/cache tests and safely selected GPU 1 (39,902 MiB free, 0% GPU utilization, 416 MiB attributed to an existing compute process). It then failed at model loading: \`Trellis2ImageTo3DPipeline.from_pretrained(MODEL_ID)\` tried to resolve \`pipeline.json\` through the Hugging Face Hub, but the temporary offline cache exposed only the weight snapshot and no pipeline config.

The correction is on the diagnostic branch of [Connector_1](https://github.com/Killer4K-N/Connector_1/tree/diagnose/trellis-asset-generation-20261014):
- [0fe92d6](https://github.com/Killer4K-N/Connector_1/commit/0fe92d6525540e83819f7a0943fbfded29dad8d6) adds the official \`pipeline.json\` for the pinned cached revision.
- [dcc0eb9](https://github.com/Killer4K-N/Connector_1/commit/dcc0eb9f8be81e20437416679414b67def6da358) resolves the config offline, creates a local \`/tmp\` snapshot overlay, mirrors cached Hub metadata locally, and loads from the local snapshot path.
- [293718c](https://github.com/Killer4K-N/Connector_1/commit/293718c8743a8720296a77a94672b105e244eb46) adds regression tests for the pinned config, offline overlay, cache links and fail-closed behavior for unknown snapshots.

The config-vendor run [38598747382](https://github.com/Killer4K-N/Connector_1/actions/runs/38598747382) was still in progress when this note was written; the loader fix [38598822415](https://github.com/Killer4K-N/Connector_1/actions/runs/38598822415) and expanded 10-test suite [38598881722](https://github.com/Killer4K-N/Connector_1/actions/runs/38598881722) were queued behind it. **Fresh asset generation remains pending** until a current run loads the model, performs inference, exports a GLB and validates actual geometry. Historical successful asset evidence remains [run 37942265623](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623), artifact [11622412194](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623/artifacts/11622412194).

No package installation, model download, shared-cache mutation, quota bypass, or process termination was performed. The missing authoritative quota snapshot remains a separate blocker for any downloads.


## 2026-10-14 22:25 IST — TRELLIS offline loader fixed; fresh asset generated and validated

### Root cause and runtime fix

The cache-only loader safely passed GPU admission but failed at model load because cached snapshot af44b45f2e35a493886929c6d786e563ec68364d lacked pipeline.json. Upstream from_pretrained(snapshot) then attempted a Hub lookup while offline. Connector_1 commit [dcc0eb9](https://github.com/Killer4K-N/Connector_1/commit/dcc0eb9f8be81e20437416679414b67def6da358) adds a pinned local config, isolated /tmp snapshot overlay and temporary Hugging Face metadata view. It does not write to shared model-cache files.

### Current asset proof

[Connector_1 run 38598822415](https://github.com/Killer4K-N/Connector_1/actions/runs/38598822415) completed successfully and generated a fresh GLB; artifact [11912523421](https://github.com/Killer4K-N/Connector_1/actions/runs/38598822415/artifacts/11912523421), 8,870,632 bytes, plus report artifact [11913208247](https://github.com/Killer4K-N/Connector_1/actions/runs/38598822415/artifacts/11913208247). SHA-256 is 0ba06de0e028d975b7108f4dcb9856a81dcdd76037e94cc852883fc5b2ad6b1e. GLB 2.0/length/JSON checks and trimesh reopen passed: one mesh/primitive, two textures, 96,532 vertices and 91,986 faces. GPU 1 admission was 39,902 MiB free, 0% utilization, with 416 MiB attributed to one existing process; no process was terminated. No model or package downloads occurred.

### Regression and source-entry follow-through

Expanded Connector_1 test run [38598881722](https://github.com/Killer4K-N/Connector_1/actions/runs/38598881722) failed one test (9/10 passed), not inference: the synthetic fixture intentionally had weight shards but no config.json. Generation was skipped. Its broad artifact path picked up a previous GLB, so artifact [11913875417](https://github.com/Killer4K-N/Connector_1/actions/runs/38598881722/artifacts/11913875417) is stale and is not accepted as output from that failed run. Commit [4dde5fd](https://github.com/Killer4K-N/Connector_1/commit/4dde5fdd9c815e7c1eee5e11e1e2c2f8840c2908) corrected the assertion; retry [38601626147](https://github.com/Killer4K-N/Connector_1/actions/runs/38601626147) passed tests and was generating when this note was written. Commit [d543a06](https://github.com/Killer4K-N/Connector_1/commit/d543a062b5695a07fd2952396ab8dc88f81a85d6) restricts artifact upload to the current run ID; validation run [38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418) is queued.

The same fix is in the OEC standalone CLI and both TRELLIS notebooks on branch [fix/trellis-offline-pipeline-config-20261014](https://github.com/Killer4K-N/OEC/tree/fix/trellis-offline-pipeline-config-20261014). CI [38601987037](https://github.com/Killer4K-N/OEC/actions/runs/38601987037) passed 34 tests (12 notebook static, 5 CLI, 6 offline config, 5 AudioCraft, 6 storage admission), Python compilation and four notebook JSON checks. Review PR [#10](https://github.com/Killer4K-N/OEC/pull/10) is open and not merged.

Authoritative quota telemetry remains missing. Any missing model/dependency download remains denied; the successful path uses cached files plus /tmp only.


## 2026-10-14 22:36 IST — Final TRELLIS guarded run PASS

[Connector_1 run 38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418) completed successfully with all job steps green. Its 10/10 offline cache/GPU admission tests passed; image-to-3D generation and both artifact uploads passed. The GLB is the exact run-specific output at \`/tmp/oec-trellis-asset-generation-38602330418/trellis_asset.glb\`.

- **GLB artifact:** [11914941709](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11914941709), artifact archive 7,243,343 bytes; SHA-256 of GLB \`22caca5fe9c02c50c095e4385a7c17e94b214b5fc7d87417b94b48c796a89257\`, GLB size 8,865,916 bytes.
- **Validation report:** [11913529964](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11913529964).
- **Geometry:** GLB 2.0, declared length matched, valid JSON chunk, one mesh and primitive, two textures, 96,672 position vertices and 92,062 faces; \`trimesh_reopen=PASS\`.
- **GPU admission:** GPU 1 admitted under the low-footprint policy (39,902 MiB free, 0% utilization, one pre-existing process attributed 416 MiB). Existing process was not stopped.
- **Source candidate:** OEC CI [38601987037](https://github.com/Killer4K-N/OEC/actions/runs/38601987037) remains green at 34 tests plus compilation/notebook JSON checks; [OEC PR #10](https://github.com/Killer4K-N/OEC/pull/10) is open and unmerged. [Connector_1 PR #2](https://github.com/Killer4K-N/Connector_1/pull/2) is now ready for review and also unmerged.

This resolves the TRELLIS config-load/generation acceptance criteria. The historical broad-wildcard artifact failure remains documented and is superseded by the exact-run upload that completed here. No model/package downloads, shared cache writes, quota bypass or process termination occurred; fresh authoritative quota remains necessary before any future downloads.


## Legacy runner-history migration (October 14, 2026)

Before new OEC self-hosted runners are exercised, all **677/677** reported run records from [Connector_1 Actions](https://github.com/Killer4K-N/Connector_1/actions) were captured across seven API pages and archived in [`docs/runner_migration/connector_1_actions_runs.json`](docs/runner_migration/connector_1_actions_runs.json). The snapshot has 677 unique run ids and run-level statuses/conclusions: 305 success, 236 failure, 122 cancelled, 13 skipped and 1 queued. The how/why and transition plan are in [`docs/runner_migration/README.md`](docs/runner_migration/README.md).

The archive is deliberately non-destructive: GitHub's historical run objects, per-job logs and binary artifacts remain canonical at their original Connector_1 URLs; the migration copies run-level metadata/results and retains those links, it does not falsely claim those objects were transferred to another repository. The detailed TRELLIS pass and FLUX GPU-admission failure are cross-linked in the main experiment register.

### Next execution pool

New OEC GPU diagnostic and asset-generation workflows will use `runs-on: [self-hosted, linux, x64, gpu, a100, oec-N]`, with `N` one of `1`, `2`, `3`. Read-only matrix [run 38610558599](https://github.com/Killer4K-N/OEC/actions/runs/38610558599) has now passed for all three labels `oec-1`, `oec-2`, `oec-3`. Each job matched the expected runner name, found eight visible A100 devices and hit both model caches; per-runner reports are linked from `TODO.md`. These GPUs are on host `scn30-mn`. The quota snapshot remains missing. A cache-only FLUX PNG generation attempt is running in [run 38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955) with serial GPU admission. Existing OEC hosted-runner static CI remains hosted because it is not a legacy connector GPU job.

## OEC runner migration inventory — observed runtime state

[Run 38610558599](https://github.com/Killer4K-N/OEC/actions/runs/38610558599) completed all three sequential jobs successfully. Each expected label matched its real RUNNER_NAME, reported host scn30-mn, detected eight visible A100 devices and reported both TRELLIS and FLUX weight caches as hits. Per-runner JSON artifacts: [oec-1](https://github.com/Killer4K-N/OEC/actions/runs/38610558599/artifacts/11916534964), [oec-2](https://github.com/Killer4K-N/OEC/actions/runs/38610558599/artifacts/11918195061), [oec-3](https://github.com/Killer4K-N/OEC/actions/runs/38610558599/artifacts/11918525046). The probe was read-only; no installs, downloads, shared-cache writes or process signals occurred. Quota snapshot: MISSING.

The cache-only FLUX generation workflow is running on the same three OEC labels, one at a time, in [run 38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955). Its acceptance criteria are package import, model load, inference, a non-empty PNG with valid PNG signature, metadata JSON, and a run-scoped artifact. No result is claimed until the workflow and artifact validation finish.
## OEC FLUX CLI and runner workflow source validation

[OEC candidate CI run 38612345392](https://github.com/Killer4K-N/OEC/actions/runs/38612345392) passed all 46 tests: 12 TRELLIS notebook-static, 5 TRELLIS easy-run, 6 offline config, 7 FLUX CLI/cache/PNG/notebook, 5 FLUX GPU admission, 5 AudioCraft notebook-static and 6 storage-write-admission tests. Python compilation passed for the TRELLIS and FLUX entry points and helper modules; all four notebooks parsed as valid JSON. The reusable FLUX CLI and the GPU-admission helper are source-tested. The actual FLUX PNG runtime is a separate test, [run 38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955), which failed on oec-1 after about 11 minutes with a missing GitHub log blob and no PNG artifact. Its job and step states conflicted, so the precise cause is undetermined. Follow-up runs [38613199844](https://github.com/Killer4K-N/OEC/actions/runs/38613199844) and [38613575959](https://github.com/Killer4K-N/OEC/actions/runs/38613575959) have no runner assignments and remain queued. A follow-up source patch switches to `device_map="cuda"`, persists failure logs/status and uses a host-local GPU lock. Candidate CI [38613904439](https://github.com/Killer4K-N/OEC/actions/runs/38613904439) passes 46/46 tests and static checks. The model-generation runtime is **not yet accepted**. Fresh quota telemetry remains missing, so the workflow stays cache-only and offline.
## FLUX live-runtime disposition (2026-10-14 23:48 IST)

The initial OEC-runner image generation attempt, [run 38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955), must be classified FAIL/INCOMPLETE: the oec-1 job returned failure after approximately 11 minutes, its log download returned BlobNotFound, step metadata still reported inference in progress, and the run uploaded no artifact. Exact failure cause is not known. The other two jobs remained queued. Two newer workflow attempts, [38613199844](https://github.com/Killer4K-N/OEC/actions/runs/38613199844) and [38613575959](https://github.com/Killer4K-N/OEC/actions/runs/38613575959), also remained queued without runner assignment.

The candidate source mitigation loads via `Flux2KleinPipeline.from_pretrained(..., device_map="cuda")` to avoid a CPU-resident model copy, writes stage/exit status into a diagnostic artifact and serializes host-local GPU work with `flock`. Static CI [38613904439](https://github.com/Killer4K-N/OEC/actions/runs/38613904439) passed 46 tests and the compilation/notebook checks. This is not proof of image generation: no PNG is available yet. Before a clean runtime retry, confirm the three runner services are online and cancel the stale queued jobs in Actions UI. The runtime workflow is restricted to an explicit marker or workflow dispatch to prevent routine source commits from piling up more inference attempts.

## 2026-10-15 — Combined FLUX/TRELLIS fix verified on review branch

The final report and exact-run artifact establish that the integrated cached route now passes: FLUX PNG → TRELLIS input → GLB export → independent geometry reopen. The source branch fixes the missing subprocess import and rejects GPU admission when utilization is high despite no visible process. CI passed 58/58 tests and four notebook checks. See changelog/CHANGELOG-2026-10-15.md and experiment entries TEST-2026-10-15-OEC-COMBINED-FLUX-TRELLIS-RUN-1/RUN-2 in test.json. These records do not merge source code to main; fresh quota telemetry remains an open blocker for downloads and managed shared writes.


## 2026-10-15 evening — Background launch/stop pipelines and Gradio notebook source validation

### Review candidate

PR [#11](https://github.com/Killer4K-N/OEC/pull/11) adds `tools/oec_service_manager.py` and `docs/background-pipelines.md` along with source changes to LTX worker GPU/purge control, QA GPU selection, TRELLIS folder generation, and explicit existing-image input for the combined pipeline. The PR remains open/unmerged. Main was updated only for tracking/results.

### Test evidence

Hosted CI [run 38743800209](https://github.com/Killer4K-N/OEC/actions/runs/38743800209) passed 78 tests; final current-head CI [run 38744924124](https://github.com/Killer4K-N/OEC/actions/runs/38744924124) passed the same 78-test suite after QA GPU-isolation hardening. The supervisor now sets `CUDA_VISIBLE_DEVICES` in the QA child's environment before Python starts, rather than relying on the worker's later environment assignment. Suite counts are notebook static 13; TRELLIS CLI 6; TRELLIS offline-config 6; combined pipeline 15; FLUX image 7; GPU admission 6; AudioCraft notebook static 5; storage-write admission 6; LTX routing/purge 6; service manager 8. Python compilation passed for the modified entry points and helpers. The workflow parsed all code cells and validated JSON for `pipeline_trellis_3d.ipynb` (16 cells), `pipeline_trellis_3d_only.ipynb` (15), `pipeline_flux_only.ipynb` (10), and `pipeline_audiocraft.ipynb` (6).

Two earlier CI results were inspected and documented, not hidden: [38743502455](https://github.com/Killer4K-N/OEC/actions/runs/38743502455) exposed an outdated TRELLIS mode assertion; [38743634536](https://github.com/Killer4K-N/OEC/actions/runs/38743634536) exposed a syntax error in the new supervisor regression. Both were corrected before the successful 78-test result.

### Operational semantics and limits

- LTX manager service keeps storage, upload and Brain separate and intentionally does not co-start QA onto the same GPU. Brain is confined to GPU 0; QA accepts a selected GPU. LTX worker's `--no-purge` now controls cluster purge/synchronization behavior too.
- TRELLIS has a single-model-load batch mode for PNG/JPEG/WEBP/BMP/TIFF folders; recursive traversal is opt-in. Combined pipeline still defaults to FLUX, while `--source-mode images --image-dir ... [--recursive]` skips FLUX. FLUX-only background image generation and FLUX/TRELLIS Gradio entry points are managed as separate services.
- Gradio source/ports/privacy are statically validated and stale saved notebook outputs were cleared. There is no claim that the live browser UIs accepted a generation request in this task. Likewise, no live LTX daemon/worker startup, live TRELLIS batch inference on a folder, or live GPU runtime for the newly added paths was run.
- Previously accepted same-run inference remains [run 38725376076](https://github.com/Killer4K-N/OEC/actions/runs/38725376076), a cache-only FLUX 512×512 PNG handed to TRELLIS and a valid GLB independently reopened by `trimesh`. It verifies the pre-existing single-image combined inference path, not the new batch or Gradio paths.
- Fresh authoritative quota telemetry remains missing. Missing model/dependency downloads and managed shared output writes stay blocked. No live processes, QA queue, `.storage_reserve.bin`, model cache or phase1 package state were mutated here.
- Prompt/profitability rules in `brain_config.json` were not changed: no measured QA yield, generation-cost or conversion experiment was available to support a claim that new prompts would improve profitability.

Open follow-ups are in `TODO.md`; per-run results and experiment details are in `test.json` and `changelog/CHANGELOG-2026-10-15.md`.


### Final launch-safety follow-through

CI [run 38744924124](https://github.com/Killer4K-N/OEC/actions/runs/38744924124) is the current-head revalidation after the QA GPU-visibility fix and passed all 78 tests, compilation and four notebook JSON/Python-cell checks. Before rollout, first inventory any existing manually launched background jobs on each node. The supervisor cannot adopt them; do not start duplicate daemon/worker instances or use broad kill patterns. Stop only exact owned legacy PIDs after inspecting them, then use the supervisor's per-service status/logs/stop controls. No user host or running process was touched in this task.


## 2026-10-16 — Structured Lustre quota schema and conservative admission

The dedicated runner's [read-only Lustre probe](https://github.com/Killer4K-N/OEC_AireOS_Freezed/actions/runs/38898669614) passed 8/8 parser/probe tests and found group usage above soft quota but below hard limit, with grace remaining at capture. The old one-limit snapshot cannot accurately represent soft quota, hard limit and grace simultaneously.

The isolated branch [fix/lustre-soft-hard-quota-snapshot-20261016](https://github.com/Killer4K-N/OEC/tree/fix/lustre-soft-hard-quota-snapshot-20261016) now adds a backward-compatible schema-v2 writer, strict structured-schema validation and conservative policy semantics. It preserves exact large byte counts, requires quota identity/source, rejects unknown or malformed schemas and limits, and denies new write admission while above soft quota even if hard-limit headroom remains. Legacy unversioned single-limit snapshots remain supported with the prior strict rule.

The first validation [run 38903339731](https://github.com/Killer4K-N/OEC/actions/runs/38903339731) correctly exposed a hard-quota test fixture missing required schema-v2 identity/source. The fixture was corrected, preserving the failure in history. Final [run 38903458777](https://github.com/Killer4K-N/OEC/actions/runs/38903458777) / [job 116981112079](https://github.com/Killer4K-N/OEC/actions/runs/38903458777/job/116981112079) passed **47/47 tests**, Python compilation and all four notebook JSON/Python-cell checks. Review [PR #12](https://github.com/Killer4K-N/OEC/pull/12) is draft and unmerged. No quota snapshot was written/refreshed; no reserve/shared filesystem mutation, package install, model/data download, or training occurred. Storage admission remains blocked pending fresh authoritative quota and explicit review/deployment of the new schema/policy.



## 2026-10-16 — later notebook-cell acceptance and frozen-weight readiness

The latest actual-cell acceptance results, detailed above, supersede earlier statements that the FLUX and TRELLIS notebook final UI cells were still untested. The result is component-level: the standalone TRELLIS cell generated a GLB and the combined app ran a FLUX generate request, but combined TRELLIS was only started and was not asked to generate a mesh. Do not merge or describe this as the complete OEC world-generation path.

The frozen-weight audit is a diagnostic PASS / semantic BLOCKED, not a PEFT/training pass. Continue to fail closed until storage manager and fresh numeric quota checks are cleared, model/license/task and dataset provenance/schema/split approvals are approved, PEFT is available in the dedicated environment, and a real-model frozen parameter/gradient/checkpoint/held-out evaluation is executed. Do not access the storage reserve file or run training/downloads to bypass these gates.


## 2026-10-18 — Live speech end-to-end acceptance and AudioGen status

The strict A100 speech bootstrap [run 39135140660](https://github.com/Killer4K-N/OEC/actions/runs/39135140660) completed successfully on \`oec-1\` / \`scn30-mn\`. The audio API mock/validation suites passed 10/10 and 10/10. The live-Lustre quota parser now accepts the soft-overage asterisk while retaining the numeric usage, soft limit, hard limit and grace fields. StorageManager admitted the required work because grace was explicitly active and the operation fit within the hard-limit headroom. Model and output writes continued through the managed-operation API.

Three live providers then produced and validated real outputs on CUDA using the isolated \`oec-audio-py311\` runtime:

- **Kokoro-82M — PASS.** Its service returned ready/model-loaded, generated a non-empty 24 kHz mono WAV of 4.7 seconds (225,644 bytes), and reported 24.328 seconds for synthesis. End-to-end service startup plus inference was 136.43 seconds.
- **Whisper-Turbo — PASS.** It transcribed the generated acceptance WAV to a validated 57-byte UTF-8 text output in 11.851 seconds. Service startup plus inference was 46.90 seconds.
- **Qwen3-ASR-0.6B — PASS.** It transcribed the same WAV to a validated 57-byte UTF-8 text output in 28.711 seconds. Its output exactly matched Whisper for this one controlled clip; this is a pipeline-consistency check, not a recognition-accuracy benchmark. Startup plus inference was 52.57 seconds.

The workflow summary is **3 passed, 0 failed, 1 skipped**. ACE-Step was skipped because no checked existing environment had the \`acestep\` runtime package. No shared Conda environment was upgraded to force music generation. The latest storage check after inference reported model usage 220.72 GB of the 280 GB model target, reserve 60.04 GB, and approximately 69.54 GB of hard-limit quota headroom during the explicitly active soft-quota grace period. The three outputs were written under the configured managed OEC output directory; the Action uploaded no artifact archive, so the evidence comes from the job's acceptance JSON and on-run storage report.

**AudioGen is not yet passed.** The notebook harness now adds the repository root before executing cells. The first run failed at cell 1 with \`ModuleNotFoundError: core_config\`; the next run passed cells 1–3 but was cancelled during cell 4 when the quota-parser commit superseded it. The latest AudioGen run, [39135140674](https://github.com/Killer4K-N/OEC/actions/runs/39135140674), remained queued when this result update was written. No AudioGen model-load success or generated WAV has yet been confirmed. The follow-up live run must finish and supply its acceptance report before AudioGen can be claimed as working.

The new soft-quota parser regression test has been added, but a focused run of that specific test is still pending. These speech smoke results validate one controlled audio path and two transcriptions, not overall speech quality, word-error rate, multilingual robustness, music generation, or commercial licensing. AudioGen's released weights remain a research-only candidate pending a separate rights review.


## 2026-10-18 — Final AudioGen acceptance and remaining media/pipeline gates

**AudioGen: PASS.** A100/phase1 run [39135140674](https://github.com/Killer4K-N/OEC/actions/runs/39135140674) executed all notebook code cells 1–5. The existing `facebook/audiogen-medium` snapshot was found locally; no model download was required. AudioGen loaded successfully and produced a non-empty, decoded 3-second mono WAV at 16 kHz (96,078 bytes); report SHA-256 `d4cd48e45890ec2668321a6dfbf95b3e57f3541b9d7cb414afe484cd349805cc`. Generation took 20.763 seconds, peak allocated VRAM 5.155 GiB and peak reserved VRAM 5.387 GiB. The full notebook harness took 61.147 seconds. [A100 run artifact/logs](https://github.com/Killer4K-N/OEC/actions/runs/39135140674/artifacts/12140085687).

The environment's non-fatal `pip check` output warns that `thinc 8.3.6` requires NumPy >=2 while phase1 intentionally has NumPy 1.26.4. AudioCraft imports and generation passed with the current pinned stack, and this task did not change phase1 packages. Revisit the conflict in a separately isolated environment rather than upgrading the shared training environment. AudioGen remains research-only for commercial product planning pending review of the released weights' CC-BY-NC terms.

**Speech: PASS (3 providers).** Run [39135140660](https://github.com/Killer4K-N/OEC/actions/runs/39135140660) passed Kokoro-82M synthesis, Whisper-Turbo transcription, and Qwen3-ASR-0.6B transcription on CUDA. Kokoro returned a valid 4.7-second, 24 kHz mono WAV (225,644 bytes). The two recognizers returned matching 57-byte English transcripts for that single controlled clip. This validates one live pipeline path, not overall recognition accuracy, language coverage or quality.

**Storage gate regression: PASS.** Run [39142266535](https://github.com/Killer4K-N/OEC/actions/runs/39142266535) passed the 10 StoragePolicy tests and 7 quota-snapshot tests, including the exact Lustre over-soft-quota asterisk row. Live admission succeeded only because quota grace was explicit and operation budget fit available hard headroom.

**Visual sidecars: still awaiting a completed live acceptance.** Run [39142905429](https://github.com/Killer4K-N/OEC/actions/runs/39142905429) found the TRELLIS checkpoint/runtime but its job stalled at 5% and timed out before a valid GLB was returned. The same run preflighted LTX checkpoints, but its API adapter incorrectly treated `inputs` and `cache` as StorageManager logical directories; only `models` and `outputs` are configured. The current OEC source now gates the sidecar under `outputs` and logs private runtime tracebacks. The synthetic TRELLIS test also uses a reduced 512 texture/5,000-face target. A run on the updated source is queued/pending ([39148645009](https://github.com/Killer4K-N/OEC/actions/runs/39148645009)); neither current TRELLIS GLB nor LTX MP4 acceptance is claimed until that run completes.

**Brain queue semantics and daemon startup.** The new runbook `docs/PIPELINE_DAEMONS_AND_MEDIA_SERVICE_RUNBOOK.md` records the exact production entry points and checks. `brain_config.json` has per-use-case queue targets 50/30/20; `max_batch_size=10` bounds prompt-generation requests, and Brain writes one JSON queue record per prompt. This is prompt/job batching, not a setting to split every video into 10 final clips. The sustained live Brain → LTX multi-GPU worker → QA → HF uploader pipeline was not started as a single run in this session, to avoid launching duplicate persistent services without verifying the existing process owners/allocation.

**OEC-Deploy verification is read-only.** Recent source CI [39120715995](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39120715995) and AppImage build [39120715944](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39120715944) passed. GUI smoke [39148052034](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39148052034) failed the DOM hero-text assertion after DevTools screenshot capture timed out, but its saved screenshot visibly contains the expected OEC-Play home hero. The GUI test explicitly did not connect to or restart the live server, so server-online status is not verified. OEC-Deploy files were not edited. The runbook lists the operator checks for `/health` and `/api/media-services`.


## 2026-10-18 — Final AudioGen acceptance and remaining media/pipeline gates

**AudioGen: PASS.** A100/phase1 run [39135140674](https://github.com/Killer4K-N/OEC/actions/runs/39135140674) executed all notebook code cells 1–5. The existing `facebook/audiogen-medium` snapshot was found locally; no model download was required. AudioGen loaded successfully and produced a non-empty, decoded 3-second mono WAV at 16 kHz (96,078 bytes); report SHA-256 `d4cd48e45890ec2668321a6dfbf95b3e57f3541b9d7cb414afe484cd349805cc`. Generation took 20.763 seconds, peak allocated VRAM 5.155 GiB and peak reserved VRAM 5.387 GiB. The full notebook harness took 61.147 seconds. [A100 run artifact/logs](https://github.com/Killer4K-N/OEC/actions/runs/39135140674/artifacts/12140085687).

The environment's non-fatal `pip check` output warns that `thinc 8.3.6` requires NumPy >=2 while phase1 intentionally has NumPy 1.26.4. AudioCraft imports and generation passed with the current pinned stack, and this task did not change phase1 packages. Revisit the conflict in a separately isolated environment rather than upgrading the shared training environment. AudioGen remains research-only for commercial product planning pending review of the released weights' CC-BY-NC terms.

**Speech: PASS (3 providers).** Run [39135140660](https://github.com/Killer4K-N/OEC/actions/runs/39135140660) passed Kokoro-82M synthesis, Whisper-Turbo transcription, and Qwen3-ASR-0.6B transcription on CUDA. Kokoro returned a valid 4.7-second, 24 kHz mono WAV (225,644 bytes). The two recognizers returned matching 57-byte English transcripts for that single controlled clip. This validates one live pipeline path, not overall recognition accuracy, language coverage or quality.

**Storage gate regression: PASS.** Run [39142266535](https://github.com/Killer4K-N/OEC/actions/runs/39142266535) passed the 10 StoragePolicy tests and 7 quota-snapshot tests, including the exact Lustre over-soft-quota asterisk row. Live admission succeeded only because quota grace was explicit and operation budget fit available hard headroom.

**Visual sidecars: still awaiting a completed live acceptance.** Run [39142905429](https://github.com/Killer4K-N/OEC/actions/runs/39142905429) found the TRELLIS checkpoint/runtime but its job stalled at 5% and timed out before a valid GLB was returned. The same run preflighted LTX checkpoints, but its API adapter incorrectly treated `inputs` and `cache` as StorageManager logical directories; only `models` and `outputs` are configured. The current OEC source now gates the sidecar under `outputs` and logs private runtime tracebacks. The synthetic TRELLIS test also uses a reduced 512 texture/5,000-face target. A run on the updated source is queued/pending ([39148645009](https://github.com/Killer4K-N/OEC/actions/runs/39148645009)); neither current TRELLIS GLB nor LTX MP4 acceptance is claimed until that run completes.

**Brain queue semantics and daemon startup.** The new runbook `docs/PIPELINE_DAEMONS_AND_MEDIA_SERVICE_RUNBOOK.md` records the exact production entry points and checks. `brain_config.json` has per-use-case queue targets 50/30/20; `max_batch_size=10` bounds prompt-generation requests, and Brain writes one JSON queue record per prompt. This is prompt/job batching, not a setting to split every video into 10 final clips. The sustained live Brain → LTX multi-GPU worker → QA → HF uploader pipeline was not started as a single run in this session, to avoid launching duplicate persistent services without verifying the existing process owners/allocation.

**OEC-Deploy verification is read-only.** Recent source CI [39120715995](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39120715995) and AppImage build [39120715944](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39120715944) passed. GUI smoke [39148052034](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39148052034) failed the DOM hero-text assertion after DevTools screenshot capture timed out, but its saved screenshot visibly contains the expected OEC-Play home hero. The GUI test explicitly did not connect to or restart the live server, so server-online status is not verified. OEC-Deploy files were not edited. The runbook lists the operator checks for `/health` and `/api/media-services`.


## 2026-10-19 — media runtime and queue-contract candidate

**Prior speech/audio successes remain valid.** Run [39135140674](https://github.com/Killer4K-N/OEC/actions/runs/39135140674) generated a valid 3-second, mono 16 kHz AudioGen WAV (96,078 bytes) from the existing cache; run [39135140660](https://github.com/Killer4K-N/OEC/actions/runs/39135140660) passed Kokoro synthesis, Whisper Turbo transcription and Qwen3-ASR transcription on one controlled clip. ACE-Step was skipped because its runtime package was absent. These are single-clip model acceptance results, not persistent service status or a sustained brain → media worker → QA → uploader acceptance.

**Later attempts are separate failures, not regressions to overwrite.** Audio bootstrap [39149243881](https://github.com/Killer4K-N/OEC/actions/runs/39149243881) failed before isolated runtime setup because StorageManager refused output-reserve resizing during an active managed operation. It installed no packages. Visual sidecar [39149240005](https://github.com/Killer4K-N/OEC/actions/runs/39149240005) found and loaded TRELLIS but its first job request failed HTTP 507 because outputs had an active managed operation. LTX passed cache preflight but did not reach ready/model_loaded during the 20-minute health wait.

Candidate source commit [f52aae4](https://github.com/Killer4K-N/OEC/commit/f52aae4dfac62d67f75401f7fb643e4a47a63b43) on branch fix/media-stack-supervision-20261019:
- Adds a cache-only supervised lifecycle for the existing audio/TTS/ASR and TRELLIS/LTX sidecars, including single-physical-GPU admission, port conflict checks, runtime-import checks, loopback health reporting and offline environment flags.
- Serializes the three shared oec-1 media workflows under one concurrency group with cancel-in-progress=false to prevent those workflows cancelling each other during a managed storage operation.
- Replaces the QA success status PENDING_UPLOAD with a single helper transition to PENDING, the same status selected by hf_upload_daemon.py. Startup ARCHIVING recovery and failed-upload rollback now use the same helper.
- Adds tests/test_oec_service_manager_media.py and tests/test_upload_status_contract.py for pure launch-spec/guard behavior and a disposable SQLite producer→selector→recovery/rollback lifecycle.

This is an unmerged candidate branch. These new tests were authored but not executed, and the live service manager did not start any process. No GitHub Actions workflow was deliberately triggered; the candidate branch is outside the current workflow push filters. No model downloads, package installation, reserve operations, purge, training, or OEC-Play server launch were performed. Current storage telemetry must be refreshed before a future service start; do not bypass an active manager lease. The OEC-Play /health status and a continuous brain→QA→uploader run remain unverified.


### Queue schema consistency follow-up

A post-change source read found the LTX worker's CREATE TABLE default was still PENDING_UPLOAD; it is now PENDING, matching the canonical status used by QA and the uploader. The offline contract test has an added static regression assertion. Tests remain unexecuted; no existing shared SQLite database was migrated or modified.


## 2026-10-19 — A100 speech service acceptance

Run [39209090292](https://github.com/Killer4K-N/OEC/actions/runs/39209090292) passed all workflow steps on oec-1 / scn30-mn with NVIDIA A100-SXM4-40GB. The pre-write compile/mock stage passed 35 tests: media API 12, audio validation 10, supervisor 8, and SQLite upload-status contract 5. StorageManager cleanup, checkpoint-cache verification, isolated runtime preparation and final status checks also passed.

Live cache-only inference passed for Kokoro, Whisper Turbo and Qwen3-ASR. Kokoro generated a valid mono 24 kHz, 4.7-second WAV (225,644 bytes) under the configured outputs root. Whisper and Qwen3-ASR both processed that WAV and returned the same 56-character transcript; each text artefact is 57 bytes and both have SHA-256 0d8e457da884656285032be2a06b38e00a801822df8682ae125a10058297e080. All three services reported ready=true, model_loaded=true and device=cuda; the temporary smoke processes were stopped after the jobs completed.

ACE-Step remains SKIPPED because its package is absent in all three checked Conda environments. The runtime dependency plan reported zero candidate package installs and preserved shared Torch; no model weights were downloaded. This validates one controlled speech clip, not broad ASR accuracy or the full persistent Brain-to-worker-to-QA-to-uploader pipeline. Visual run [39209706982](https://github.com/Killer4K-N/OEC/actions/runs/39209706982) is still running and must produce a validated GLB and MP4 before visual acceptance is claimed. Production OEC-Play server health remains unverified.
