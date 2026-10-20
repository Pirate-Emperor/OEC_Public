# OEC Work Changelog

- [2026-10-20 — live A100 media acceptance and Whisper timestamp follow-up](CHANGELOG-2026-10-20.md)
  - Added dedicated AudioGen, MusicGen, ACE-Step, Kokoro, Whisper and Qwen3-ASR notebooks with explicit UI/backend environments; the API-facing notebooks use isolated service workers rather than combining provider dependencies. Added a static notebook policy test and OEC-Deploy worker contract runbook.
  - Later source SHA `0c53f6a46328bc4ba6ce4d0942556e3077ea6d74` passed all 8 live jobs in [run 39435100568](https://github.com/CalamityStriker/OEC/actions/runs/39435100568); the bounded LTX→Qwen2-VL QA→HF chunk upload→remote hash read-back also passed. Exact-head static run 39452849501 passed for `72b71f861bba72b78da1cec330e4273b00baaabb`; exact-head live run 39452849617 is still running.
  - The older blocked attempts above are retained as history. The current source follow-up captures Whisper segment timestamps in job metadata; the actual A100 test against this change is pending run 39452849617.


- [2026-10-19 — model inference handoff and Actions quota update](CHANGELOG-2026-10-19.md)
  - **Latest checkpoint 23:33 IST:** static run [39300850953](https://github.com/CalamityStriker/OEC/actions/runs/39300850953) passed 96 tests, `py_compile`, all four notebook JSON checks, and no ResourceWarning. New guarded E2E run [39300850928](https://github.com/CalamityStriker/OEC/actions/runs/39300850928) ran on `oec-1` but stopped before inference because external PID `3347078` was attached to all eight A100s. Artifact [12211286861](https://github.com/CalamityStriker/OEC/actions/runs/39300850928/artifacts/12211286861) confirms BLOCKED, no process kill, no shared queue, no repository creation and no upload. Wait for normal GPU-owner release; actual Qwen2-VL decision, HF upload/readback, remote chunk consumer and Brain→OEC-Play remain open. Visual sidecar run [39278268411](https://github.com/CalamityStriker/OEC/actions/runs/39278268411) is terminal SUCCESS with inspected TRELLIS/LTX artifacts; ACE-Step remains no-idle-A100 blocked.

Daily engineering records live here. Use the local Asia/Kolkata date in each filename. Append work to the current day's file while the date remains the same; create a new `CHANGELOG-YYYY-MM-DD.md` on the next date.

## Daily records

- [2026-10-16 — Lustre soft/hard quota schema hardening](CHANGELOG-2026-10-16.md)
  - Read-only probe [38898669614](https://github.com/Killer4K-N/OEC_AireOS_Freezed/actions/runs/38898669614) found group usage above soft quota with hard-limit headroom and grace at capture. Isolated storage-schema PR [#12](https://github.com/Killer4K-N/OEC/pull/12) now preserves these fields separately, keeps write admission blocked above soft, and rejects malformed schema-v2 data. Final CI [38903458777](https://github.com/Killer4K-N/OEC/actions/runs/38903458777) passed 47 tests, Python compilation and all four notebook checks. An earlier fixture failure remains documented. No quota snapshot was written and PR #12 is draft/unmerged.

- [2026-10-15 — FLUX/TRELLIS fix validated end to end on review branch](CHANGELOG-2026-10-15.md)
  - Hosted CI [38725202281](https://github.com/Killer4K-N/OEC/actions/runs/38725202281) passed 58/58 tests, Python compilation and all four notebook checks. This includes the findmnt/subprocess and high-utilization GPU-admission regressions.
  - First combined attempt [38723286765](https://github.com/Killer4K-N/OEC/actions/runs/38723286765) found the missing subprocess import in the scratch filesystem probe and an over-permissive IDLE policy at 100% utilization. Both were corrected on the review branch.
  - Final combined run [38725376076](https://github.com/Killer4K-N/OEC/actions/runs/38725376076) passed FLUX image generation, exact PNG handoff to TRELLIS.2, GLB export and independent geometry reopen (54,597 vertices / 93,617 faces). Artifact [11967418646](https://github.com/Killer4K-N/OEC/actions/runs/38725376076/artifacts/11967418646) contains image, metadata, pipeline report and GLB.
  - Evening follow-up adds supervised LTX/FLUX/TRELLIS background services, safe managed-session shutdown, explicit TRELLIS folder input, and FLUX-by-default combined routing. CI [run 38743800209](https://github.com/Killer4K-N/OEC/actions/runs/38743800209) passed 78 tests; final current-head [run 38744924124](https://github.com/Killer4K-N/OEC/actions/runs/38744924124) also passed 78 tests, py_compile and JSON/Python-cell checks for all four notebooks after QA GPU visibility was moved into the pre-start child environment. Live LTX and browser/Gradio request checks remain open.
  - Further follow-up adds per-command service CLI help and an SSH cluster coordinator with example profiles for a three-node LTX pool, a mixed stack, four FLUX one-shot jobs, default FLUX→TRELLIS and TRELLIS folder batch. Combined notebook now assigns TRELLIS and FLUX to distinct GPUs/processes. Final CI [run 38760561720](https://github.com/Killer4K-N/OEC/actions/runs/38760561720) passed 86 tests, Python compilation, and all four notebook JSON/Python-cell checks. Cluster actual-node startup, browser/Gradio submissions, and folder-mode GPU inference remain open; fresh quota is still missing.
  - Conda-root template correction was revalidated by final CI [run 38761087455](https://github.com/Killer4K-N/OEC/actions/runs/38761087455): 86/86 tests, Python compilation and all four notebook checks passed. The example now uses `~/OEC/Conda/bin/activate` to match the project-local activation pattern; adjust it per node if the actual Conda root differs. Live cluster/UI/folder GPU tests remain open and quota is still missing.
  - Model/source changes remain on fix/flux-trellis-pipeline-20261015; main source was not merged. Fresh quota telemetry remains an open gate for future downloads and managed writes.

- [2026-10-14 — TRELLIS generation verified; quota and FLUX blockers tracked](CHANGELOG-2026-10-14.md)
  - [Connector_1 run 38555689884](https://github.com/Killer4K-N/Connector_1/actions/runs/38555689884) succeeded in producing a read-only report: the configured quota snapshot is missing and `quota_check` is unavailable on scn17-mn.
  - Model storage is on shared Lustre with very high measured filesystem free capacity; that is not user/project quota proof, so package/model write admission remains blocked.
  - The live OEC checkout is detached at `081aaf34...` with tracked dirty paths; no live sync/reset occurred. Reserve size differs from an earlier logged value and needs read-only reconciliation.
  - Root cause was the cached weight snapshot's missing `pipeline.json`; a pinned local config plus a temporary `/tmp` overlay and local Hugging Face metadata view fixed the offline load without modifying shared cache files. Final [Connector_1 run 38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418) passed 10/10 tests, loaded the pipeline, ran inference, and uploaded the exact-run GLB [11914941709](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11914941709): 8,865,916 bytes, SHA-256 `22caca5fe9c02c50c095e4385a7c17e94b214b5fc7d87417b94b48c796a89257`, 96,672 vertices / 92,062 faces; `trimesh_reopen=PASS`. OEC CLI/notebook source candidate [PR #10](https://github.com/Killer4K-N/OEC/pull/10) and Connector_1 [PR #2](https://github.com/Killer4K-N/Connector_1/pull/2) remain open and unmerged.
  - The connector-2 QA recovery job separately failed on Slurm host discovery/accounting DB connectivity. Queue/process mutation is not claimed.

- [2026-10-12 — Runtime blocker remediation and official upstream compatibility review](CHANGELOG-2026-10-12.md)
  - Audited the real failed result in [Connector_1 run 38161901000](https://github.com/Killer4K-N/Connector_1/actions/runs/38161901000): source/static tests passed, but fresh quota data was unavailable, so runtime installs and inference remained gated.
  - Corrected the isolated Connector_1 remediation helpers to require fresh quota for package/model writes; constrain xFormers and AudioCraft repair installs to binary wheels; and defer stopped QA-worker retirement until its replacement is confirmed RUNNING.
  - Reviewed official Microsoft TRELLIS.2, Facebook xFormers, Hugging Face Diffusers FLUX.2, and AudioCraft requirements. The helper changes still need workflow validation; no runtime fix is claimed until actual attention/model/image/AudioCraft tests pass.
  - The queue remains read-only at 225 rows; no package/model downloads or QA queue mutations were performed during source editing.

- [2026-10-11 — TRELLIS, Jupyter, QA, paths, and runtime diagnosis](CHANGELOG-2026-10-11.md)
  - The standalone TRELLIS.2 CLI/Gradio entry point and safer TRELLIS/FLUX notebook flows were added on the feature branch. Future interactive-model requirements are in `docs/model_entrypoint_convention.md`.
  - The final 3-runner offline/static matrix at [run 38157725815](https://github.com/Killer4K-N/Connector_1/actions/runs/38157725815) passed 38 tests per runner across connector-1, connector-2, and connector-5: 17 TRELLIS/entry-point tests, 5 AudioCraft notebook tests, 10 QA queue/worker guard tests, and 6 path-alias tests (114 passes total).
  - Latest targeted sync [run 38161747478](https://github.com/Killer4K-N/Connector_1/actions/runs/38161747478) copied the current `TODO.md`, `test.json`, `result.md`, daily changelog and index into the live OEC checkout after validation. `SYNC_SCRIPT_SYNTAX=PASS`, `TRACKING_FILES_VALIDATION=PASS`, and `STAGED_NOTEBOOK_AND_CLI_VALIDATION=PASS`; all four static suites passed again (17/5/10/6). Its overall result remains incomplete because storage admission blocked package installation and TRELLIS inference.
  - Plural aliases are created and verified: `aireos_datasets -> aireos_dataset`, `aireos_inputs -> aireos_input`, and `aireos_outputs -> aireos_output`. Canonical singular paths were preserved.
  - The installed `xformers==0.0.29.post1` fails CUDA attention with `torch==2.6.0+cu124`; `flash-attn` is absent. The TRELLIS.2 model cache probe misses `microsoft/TRELLIS.2-4B`. Fresh quota admission is still unavailable on all three compute runners, so no bypass is allowed.
  - The official Diffusers v0.37.0 release notes list Flux2 Klein support, while current Hugging Face Hub docs expose `get_cached_repo_tree`; this supports the proposed released dependency-set direction, but a real import/image-generation run is still blocked by quota admission.
  - FLUX.2 Klein weights are cached, but `diffusers==0.40.0.dev0` cannot import the FLUX pipeline with `huggingface-hub==0.36.2`: Diffusers expects `get_cached_repo_tree`, which is missing. The notebook's released dependency set is gated and still requires real import/image-generation verification.
  - QA worker source selects GPU before importing PyTorch and guards model download/cache purge. The existing connector-2 QA process was observed stopped (state `T`) under an interactive session; it was not resumed or duplicated. Queue rows were not changed.
  - AudioCraft imports work in phase1, but `pip check` reports the `thinc==8.3.6` / `numpy==1.26.4` conflict. The original reported wheel-build traceback was not found; phase1 was not changed.
  - No changes were merged into `main`; the dirty live working tree was not reset or cleaned.


- **Follow-up on 2026-10-14 — storage write guards and offline FLUX attempt**
  - Reviewable OEC candidate [`fix/storage-admission-write-guards-20261014`](https://github.com/Killer4K-N/OEC/tree/fix/storage-admission-write-guards-20261014), tested at [run 38559330370](https://github.com/Killer4K-N/OEC/actions/runs/38559330370): 27/27 static tests, py_compile, and four notebook JSON checks pass.
  - Source paths now require fresh quota for model/package/output writes and recheck admission inside managed locks; shared runtime is still gated by missing authoritative telemetry.
  - After the tracking-only commit, [run 38559861094](https://github.com/Killer4K-N/OEC/actions/runs/38559861094) again passed the unchanged 27-test suite plus compilation and JSON checks.
  - Cached FLUX snapshot is present, but [run 38559255790](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790) found active compute processes on both A100s and correctly refused to start inference.

## Persistent project tracking

- **One active TODO list:** [`TODO.md`](../TODO.md)
- **Structured experiment/test log:** [`test.json`](../test.json) — currently 49 experiment/test records.
- **Cumulative significant results:** [`result.md`](../result.md)
- **Reusable interactive-model implementation convention:** [`model_entrypoint_convention.md`](../docs/model_entrypoint_convention.md)

Update the daily changelog, `TODO.md`, `test.json`, and `result.md` at the end of each OEC task. Do not create additional parallel TODO/test/result files.


- **2026-10-14 — TRELLIS asset proof and current live-runtime blockers**
  - Current candidate [run 38571665298](https://github.com/Killer4K-N/OEC/actions/runs/38571665298) passed 28/28 static tests plus compilation and notebook JSON validation.
  - Historic TRELLIS run [37942265623](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623) produced a real 8,950,028-byte GLB; the recovered artifact was re-opened independently with `trimesh` and contains 97,783 vertices and 92,819 faces. It is linked as a downloadable file in `result.md`.
  - The early offline TRELLIS smoke [38571363231](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231) was blocked by GPU occupancy and did not generate an asset; that result is superseded by the later successful run 38602330418 documented above. FLUX image generation still has no passing PNG-producing run. Quota telemetry remains absent, so no download/install bypass is allowed.


## 2026-10-14 — Main branch integration

- Integrated the reviewed TRELLIS/FLUX notebooks and CLI, storage-output admission fixes, regression tests and cumulative tracking files into `main`.
- Candidate test run [38572444007](https://github.com/Killer4K-N/OEC/actions/runs/38572444007) passed 28/28 static tests, Python compilation and four notebook JSON checks; main-triggered validation is pending.
- Historical TRELLIS image-to-3D generation is confirmed by [run 37942265623](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623): 8,950,028-byte GLB artifact [11622412194](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623/artifacts/11622412194) reopens with 97,783 vertices and 92,819 faces. Those earlier Oct 14 TRELLIS attempts were blocked before the later cache-only loader fix; see the newer successful GLB evidence below. FLUX end-to-end generation remains unverified.

- **Main CI result recorded:** [run 38575822798](https://github.com/Killer4K-N/OEC/actions/runs/38575822798) on main commit `9c9d7acc...` passed 28/28 static tests, Python compilation and 4/4 notebook JSON checks. Earlier shared GPU generation attempts were blocked at admission; the later TRELLIS cache-only runtime now succeeds. FLUX end-to-end generation remains unverified.

- **Latest GPU smoke retries:** TRELLIS [run 38571363231 attempt 2](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231) and FLUX [run 38559255790 attempt 2](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790) both blocked safely at GPU occupancy; the retry results are recorded in `test.json` and the Oct. 14 changelog. Historical TRELLIS GLB remains independently validated.


- **TRELLIS fix runtime-verified:** Connector_1 run 38598822415 generated a fresh GLB (8,870,632 bytes; SHA-256 0ba06de0e028d975b7108f4dcb9856a81dcdd76037e94cc852883fc5b2ad6b1e) and reopened it with trimesh (96,532 vertices, 91,986 faces). OEC candidate CI 38601987037 passed 34 tests; review PR #10 is open, not merged.
- **Follow-up checks:** corrected Connector_1 retry [38601626147](https://github.com/Killer4K-N/Connector_1/actions/runs/38601626147) passed 10/10 tests and generated a fresh validated GLB (98,250 vertices, 93,243 faces); its old wildcard bundled multiple files. The exact-run artifact guard in run [38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418) is running. Artifact 11913875417 from the failed test-only run is stale, not proof of a fresh result.


## Runner migration

- Legacy source: [Connector_1 Actions runs](https://github.com/Killer4K-N/Connector_1/actions); captured run-level history: 677/677 unique records, outcomes 305 success / 236 failure / 122 cancelled / 13 skipped / 1 queued.
- Archive: [`docs/runner_migration/connector_1_actions_runs.json`](../docs/runner_migration/connector_1_actions_runs.json).
- Migration method and next steps: [`docs/runner_migration/README.md`](../docs/runner_migration/README.md).
- Inventory [run 38610558599](https://github.com/Killer4K-N/OEC/actions/runs/38610558599) passed for all three new OEC labels, with per-runner reports. The first cache-only FLUX runtime [38611186955](https://github.com/Killer4K-N/OEC/actions/runs/38611186955) failed without a retrievable log or PNG. Follow-up attempts [38613199844](https://github.com/Killer4K-N/OEC/actions/runs/38613199844) and [38613575959](https://github.com/Killer4K-N/OEC/actions/runs/38613575959) remain queued without runner assignment. Candidate CI [38613904439](https://github.com/Killer4K-N/OEC/actions/runs/38613904439) passed 46 tests and Python/notebook static checks, but Flux runtime remains unaccepted.


- [2026-10-20 — latest static pass and persistent A100 checkout diagnosis](CHANGELOG-2026-10-20.md)
  - Static run [39379628368](https://github.com/CalamityStriker/OEC/actions/runs/39379628368) passed all 14 test command groups (102 logged test cases); new notebook suite 3/3 passed.
  - Sync diagnostic [39379628387](https://github.com/CalamityStriker/OEC/actions/runs/39379628387) found detached HEAD 081aaf34f6379873bdc925d1dcf6b9c3d50349d3 and 662 dirty/untracked entries in the persistent checkout. Sync remained blocked, without modifying local files.


- Additional model audit: the repository also contains legacy `pipeline_wan_video.ipynb` (Wan 2.1), which is not currently accepted: it has no Gradio UI, an unbound `SYSTEM_DIRS` reference, and selects GPU based on free memory alone. A dedicated environment/worker audit remains open; shared `phase1` was not modified.


- [2026-10-20 — clean A100 test worktree fallback](CHANGELOG-2026-10-20.md): updated the existing safe sync workflow to use a fresh-StorageManager-gated isolated `$HOME/OEC_feature_sync` worktree when the primary 662-entry detached checkout cannot be fast-forwarded. Pending workflow result.


- [2026-10-20 — successful static acceptance and local A100 source sync](CHANGELOG-2026-10-20.md)
  - Static pass [39380653548](https://github.com/CalamityStriker/OEC/actions/runs/39380653548) validated notebook JSON/Python/env contracts. The clean worktree sync [39380653563](https://github.com/CalamityStriker/OEC/actions/runs/39380653563) created `$HOME/OEC_feature_sync` at the exact expected SHA after StorageManager admission; original dirty checkout preserved.


- [2026-10-20 — current-head test and sync pass](CHANGELOG-2026-10-20.md): static run [39380928743](https://github.com/CalamityStriker/OEC/actions/runs/39380928743) and A100 sync [39380928762](https://github.com/CalamityStriker/OEC/actions/runs/39380928762) passed at source SHA `132a8a5820a104ec27c14a87c9af3d4f84e83b98`; clean sibling worktree synced after StorageManager admission.


- [2026-10-20 — oec-2 live acceptance and real Gradio callbacks](CHANGELOG-2026-10-20.md): live model workflows now target `oec-2`. The API smoke can launch each notebook UI on loopback, call the wired callback against the live backend, validate outputs and capture SHA-256 evidence. Pending Actions artifacts.


- E2E runner guard now accepts `OEC_EXPECTED_RUNNER=oec-2` for the ordered suite while preserving the idle-GPU/process checks; see current checklist for live run result.


- [2026-10-20 — authorized storage recovery gate](CHANGELOG-2026-10-20.md): moved conservative legacy lock recovery to oec-1 and gated all oec-2 inference on successful recovery plus read-only no-lock/no-lease checks.


- [2026-10-20 — live AudioGen result and Gradio proxy fix](CHANGELOG-2026-10-20.md): existing notebook generated a validated 3s WAV; dedicated Gradio launch then exposed loopback/proxy settings and is being fixed. MusicGen was blocked by the idle-GPU gate.

- [2026-10-20 — live acceptance gaps and fixes](CHANGELOG-2026-10-20.md): existing AudioGen notebook inference passed but its dedicated Gradio UI hit a Gradio schema bug; speech venv preparation was blocked by a hard-coded reserve floor; MusicGen was blocked by GPU admission. Targeted fixes are committed pending a rerun.


- [2026-10-20 — live model acceptance and fixes](CHANGELOG-2026-10-20.md): real AudioGen and MusicGen inference both produced validated WAVs on A100 4; UI acceptance exposed a scratch-path issue and the MusicGen workflow exposed a metadata filename bug. Speech smoke import path was fixed; ACE-Step remains untested and current integrated acceptance is pending.

- [2026-10-20 — readiness contract and candidate integration fixes](CHANGELOG-2026-10-20.md): Added read-only provider readiness, OEC_Deploy integration documentation, shared GPU admission in the service supervisor, and fixes for FLUX/E2E/AudioCraft live-acceptance failures.
- [2026-10-20 — AudioGen Gradio event accepted; speech endpoint naming fix](CHANGELOG-2026-10-20.md): AudioGen passed a real Gradio HTTP-event callback; speech UI needs a Gradio-version-safe function-index call, now fixed pending rerun.
- [2026-10-20 — AudioGen and MusicGen Gradio event flows verified](CHANGELOG-2026-10-20.md): Both AudioCraft UIs passed real HTTP event acceptance; they remain CLI/Gradio-only and need supervised APIs for direct downstream deployment use.
- [2026-10-20 — FLUX included in readiness inventory](CHANGELOG-2026-10-20.md): FLUX.2 Klein appears in readiness but remains NOT_EXPOSED until a standalone supervised HTTP API exists.
- [2026-10-20 — ACE-Step verified reuse and current model readiness](CHANGELOG-2026-10-20.md): Added a no-write verified-reuse path for ACE-Step and recorded the latest live model acceptance plus deployment-endpoint persistence caveat.