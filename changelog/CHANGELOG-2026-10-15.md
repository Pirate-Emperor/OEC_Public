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
