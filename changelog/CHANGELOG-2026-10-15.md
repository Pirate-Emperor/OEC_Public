# OEC Engineering Changelog — 2026-10-15

## Objective

Trace the active FLUX/TRELLIS Actions failures to exact job logs, repair the broken scratch-output guard and unsafe GPU admission result, then prove a single-run FLUX image → TRELLIS.2 GLB path. This main-branch commit is tracking-only; source changes remain on review branch fix/flux-trellis-pipeline-20261015.

## Repository scope

- OEC main at investigation start: 99d9796d5bd5afc1731600b310ced3b5be521ee9.
- Code and workflow changes are on review branch fix/flux-trellis-pipeline-20261015; no model/source merge was made to main.
- Existing standalone runtime evidence: OEC run 38613575959 generated real FLUX PNGs on oec-1/oec-2/oec-3; Connector_1 run 38602330418 exported and reopened a real TRELLIS.2 GLB.

## Initial integrated failure and root cause

OEC combined run [38723286765](https://github.com/Killer4K-N/OEC/actions/runs/38723286765), job 116382882587, on oec-1, proved the FLUX model path, exact PNG writing/validation, TRELLIS cache lookup, CUDA/xFormers attention check and TRELLIS pipeline load all succeeded. The first TRELLIS generation command then failed before image-to-3D inference:

- Python exception: NameError because the scratch-filesystem helper invoked subprocess.run() through its findmnt fallback but pipeline_trellis_3d.py did not import subprocess.
- Evidence artifact: [11966744703](https://github.com/Killer4K-N/OEC/actions/runs/38723286765/artifacts/11966744703), which contains the FLUX PNG, metadata and pipeline_report.json.
- Secondary admission defect: that run observed zero visible compute processes but GPU utilization at 100%; the admission tool nevertheless classified the device as IDLE.

## Fixes delivered and tested on review branch

1. Added the missing import subprocess to pipeline_trellis_3d.py.
2. Added test_trellis_same_filesystem_probe_can_use_findmnt to force the fallback that originally raised NameError.
3. Hardened tools/flux_gpu_admission.py so an IDLE GPU must have known memory/process state and utilization at or below 5%. The combined orchestrator now waits and re-samples for up to 180 seconds, then fails closed if no eligible device appears. It never terminates or signals an existing process.
4. Retained offline/cache-only execution and local /tmp artifacts. Model/dependency download/install gates and managed shared-output quota guards were not bypassed.

## Hosted regression result

[Run 38725202281](https://github.com/Killer4K-N/OEC/actions/runs/38725202281), job 116389198433, tested commit d075b4442d87904e5b57128cb2f430bc53781738 and passed 58/58 targeted tests. Python compilation passed, and JSON/Python-cell validation passed for all four notebooks. The tests include the findmnt/subprocess regression and the high-utilization/no-visible-process GPU-admission case. This was hosted static CI, separate from the runtime run below.

## Final end-to-end result

[OEC run 38725376076](https://github.com/Killer4K-N/OEC/actions/runs/38725376076), job 116389784906, passed on runner oec-1 / host scn30-mn. Tested source revision: 3092ee7e11b56413a08f4b849e21f806537a2ea5.

- Overall report: PASS, duration 419.848 seconds, cache-only; network downloads disabled, package installs disabled, managed shared-output writes disabled.
- FLUX image: black-forest-labs/FLUX.2-klein-4B; 512×512 PNG, 255,946 bytes, seed 2048; SHA-256 2b05b417eb928a93511c88ee2d45b21357419720c31917a8e5129434eed6afbb. PNG and sidecar validation passed.
- Handoff: the exact generated PNG path was passed to TRELLIS.2 as its input. TRELLIS cache snapshot af44b45f2e35a493886929c6d786e563ec68364d, torch 2.6.0+cu124, CUDA 12.4 and xformers 0.0.29.post2 passed the runtime/attention checks.
- GLB artifact: [11967418646](https://github.com/Killer4K-N/OEC/actions/runs/38725376076/artifacts/11967418646). Four files are present: flux2_klein.png, flux2_klein_info.json, pipeline_report.json, trellis_asset.glb.
- Mesh: GLB 2.0, 3,484,804 bytes; SHA-256 74e3654625a0662302ecb1bf1c0c79885833563753b6a30acbeee45a5c4b360e. One mesh/primitive, 54,597 position vertices and 280,851 indices. Independent trimesh reopen passed with 54,597 vertices and 93,617 faces.

## Safety and remaining issues

- No model/dependency downloads or package installations occurred. No writes to shared output directories, shared model cache or .storage_reserve.bin occurred. No process signals, QA queue changes or phase1 edits were made.
- Fresh authoritative quota telemetry is still unavailable. Continue to block missing-model/dependency downloads and managed shared-output writes until fresh quota admission passes.
- A separate repo-wide observation is that qa_compliance_worker.py should be reviewed for CUDA visibility/import ordering. It was not changed here and no QA worker or queue was touched.
- Code is still review-only on fix/flux-trellis-pipeline-20261015. Main is receiving only the daily log, results, test ledger, TODO and changelog index in this commit.


## 2026-10-15 evening — Background LTX/FLUX/TRELLIS pipelines and Gradio notebook audit

### Objective and repository review

Audit the supplied shell launch and termination recipe; add one supervised background-service interface for LTX, FLUX-only image generation, TRELLIS-only image-folder conversion, and the combined FLUX→TRELLIS pipeline; retain the combined pipeline's default FLUX source while allowing an explicit folder-input mode; check the three relevant Jupyter/Gradio notebooks; and document tested results and remaining live-runtime checks.

Code and workflow changes for this section are on review branch `fix/flux-trellis-pipeline-20261015`, PR [#11](https://github.com/Killer4K-N/OEC/pull/11), not merged to main. Only this tracking update is on main.

### Findings in the supplied LTX shell recipe

- The shell can background the named long-running programs, but the compound semicolon/ampersand command has weak failure visibility, shared logs, no per-service identity, no GPU reservation check and no coordinated rollback. A successful shell return does not establish that each daemon loaded, reached its poll loop, or can consume a job.
- `brain.py` uses Transformers automatic device placement, while the QA worker's old default also selected GPU 0. Starting both together can make them compete. The new controller service pins Brain to physical GPU 0 and does not implicitly co-start QA; QA is a separate service with explicit `--gpu`.
- The previous LTX worker path checked distributed purge based on `--cluster-gpus` even when `--no-purge` was provided; in that path a distributed purge/synchronization could still run. The worker now gates the distributed purge and its local barrier on the actual purge flag.
- Broad `pkill -f` and especially `pkill -9 -f "python"` may terminate unrelated Python programs, Jupyter kernels or jobs. These are not safe general shutdown commands. The new supervisor maintains a per-host state record and log, launches independent process sessions, checks the managed session before signaling and escalates only within the recorded session after a grace period.
- GPU conflict checking tracks supervisor-managed services, not all unmanaged programs/Jupyter kernels. Verify the target host with `nvidia-smi` before launch. No live user processes were started, signaled or stopped during this source audit.

### Pipeline implementation

1. `tools/oec_service_manager.py` adds `start`, `stop`, `status` and `logs` controls, Conda interpreter resolution for `phase1_ltx` and `phase2_3d`, per-service logs/state, GPU claims, and managed-session child tracking for multiprocessing workers.
2. `tools/ltx_worker_config.py`, `worker_ltx_video.py` and `qa_compliance_worker.py` add physical GPU-ID validation, a GPU-0-free default when the node has additional GPUs, purge-aware LTX synchronization, and explicit QA GPU selection. The LTX controller service runs storage manager, upload daemon and Brain separately; QA stays separate.
3. `pipeline_trellis_3d.py` adds `--mode generate-batch --input-dir ... [--recursive]`, deterministic image ordering, output names, refusal to overwrite outputs, and per-asset GLB checks while reusing one loaded model.
4. `pipeline_flux_trellis.py` adds `--source-mode images --image-dir ... [--recursive]`. Default remains `--source-mode flux`; folder mode bypasses FLUX and validates each generated GLB and reopened geometry.
5. The service manager includes background single-image FLUX, FLUX Gradio, TRELLIS Gradio, TRELLIS folder-batch, combined FLUX→TRELLIS and combined folder-input commands. One-shot jobs use run-specific local `/tmp` output, stay offline/cache-only, and fail closed on missing caches.
6. Added `docs/background-pipelines.md` and removed stale saved execution counts/outputs from `pipeline_flux_only.ipynb`, `pipeline_trellis_3d_only.ipynb` and `pipeline_trellis_3d.ipynb`. Static checks assert private Gradio sharing and the intended ports: FLUX-only 7864, TRELLIS-only 7862, combined TRELLIS 7862 and FLUX 7863.

### Tests, runs, regressions and fixes

- **Run [38743502455](https://github.com/Killer4K-N/OEC/actions/runs/38743502455) — FAIL (test expectation):** existing TRELLIS easy-run test expected only `gradio/generate/check`. Adding `generate-batch` made that old assertion stale. No inference was attempted. Updated the expected mode list and added an assertion for `--input-dir`.
- **Run [38743634536](https://github.com/Killer4K-N/OEC/actions/runs/38743634536) — FAIL (new test syntax):** existing TRELLIS/FLUX/notebook/storage/LTX suites before the supervisor import passed; CI then failed to import the newly added supervisor tests because a multi-context `with` statement had literal escaped continuation characters. Corrected it to a parenthesized context manager. No inference was attempted.
- **Run [38743800209](https://github.com/Killer4K-N/OEC/actions/runs/38743800209) — PASS:** 78 tests across notebook static 13, TRELLIS CLI 6, TRELLIS offline config 6, combined pipeline 15, FLUX CLI 7, GPU admission 6, AudioCraft notebook static 5, storage write admission 6, LTX GPU/purge config 6, and service manager 8. Python compilation passed for the pipeline scripts, storage manager, LTX/QA workers and helper modules. Four notebook JSON/Python-cell checks passed (`pipeline_trellis_3d.ipynb` 16 cells; `pipeline_trellis_3d_only.ipynb` 15; `pipeline_flux_only.ipynb` 10; `pipeline_audiocraft.ipynb` 6).
- Focused new regressions cover default FLUX source, explicit folder source, file type/filtering, nested-image ordering, empty folders, symlink rejection, deterministic batch names, LTX GPU validation, `--no-purge`, explicit QA GPU selection, supervisor routes/log/state, and child-process shutdown escalation.
- Previous live FLUX→TRELLIS proof remains run [38725376076](https://github.com/Killer4K-N/OEC/actions/runs/38725376076): cache-only FLUX PNG handed to TRELLIS and validated GLB with independent `trimesh` reopen. This is historical evidence for the already-working combined single-image path, not a new folder-mode or Gradio-browser run.

### Status, limitations and next improvements

- **Static/CLI CI is green.** It does not prove that a browser can reach and submit to all three Gradio interfaces, nor that the LTX daemons, multi-GPU workers and QA process start correctly on each target compute node. Those live host checks remain open. Do not claim the entire newly supervised LTX/folder/Gradio pipeline has passed real inference until separate hardware-backed smoke runs complete.
- Fresh authoritative quota telemetry is still missing. Model/dependency downloads and managed shared-output writes remain blocked; no quota guard was bypassed. The new generation commands use cached weights and local scratch for this validation.
- The service manager does not inspect every external or notebook process; manually launched Jupyter/other services require a read-only `nvidia-smi` check before assigning GPU IDs.
- `brain_config.json` prompt/decision rules were read as project context but not changed: a claimed quality/profitability improvement requires controlled comparisons using acceptance rate, QA rejection, cost/time and downstream conversion results; no such result was measured in this task.
- No live process, QA queue, `.storage_reserve.bin`, shared model-cache content or `phase1_ltx` packages were modified. Source changes remain in PR #11, unmerged.


## 2026-10-15 final source review — QA GPU isolation verified

A final code review of the launch contract found that `qa_compliance_worker.py` imports Torch at module scope and sets `CUDA_VISIBLE_DEVICES` later inside `QANode`. To avoid relying on lazy CUDA initialization semantics, the supervisor now supplies `CUDA_VISIBLE_DEVICES=<selected physical GPU>` in the child's environment before Python starts. Added a focused regression assertion.

- Earlier complete 78-test pass: [run 38743800209](https://github.com/Killer4K-N/OEC/actions/runs/38743800209). Subsequent change is a testable GPU-visibility-before-import hardening, not an inference-code change.
- Final current-head CI: [run 38744924124](https://github.com/Killer4K-N/OEC/actions/runs/38744924124) — **PASS**, all 78 tests, `py_compile` and 4/4 notebook JSON/Python-cell checks. Suite counts remain 13 notebook-static, 6 TRELLIS CLI, 6 offline TRELLIS config, 15 combined pipeline, 7 FLUX CLI, 6 GPU admission, 5 AudioCraft notebook, 6 storage admission, 6 LTX configuration and 8 supervisor tests.
- Branch sync: source candidate now includes the exact main-branch tracking file versions through merge commit [3183d51](https://github.com/Killer4K-N/OEC/commit/3183d51435168b1a7b83f735d4a6d4106399526a), and the final QA isolation change is in the subsequent feature commits. PR #11 remains open and unmerged.
- Runtime caveat unchanged: this is hosted static/CLI regression CI. No live QA, LTX worker, Gradio browser request or folder-backed TRELLIS inference was executed. The successful prior single-image FLUX→TRELLIS run [38725376076](https://github.com/Killer4K-N/OEC/actions/runs/38725376076) remains separate evidence only.
