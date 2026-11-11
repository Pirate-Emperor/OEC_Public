# OEC project continuation checklist

## 2026-11-12 — Storage reserve reconciliation and Git identity handoff

**Current source baseline:** OEC `main` remains at the source inspected for this handoff. Review branch `fix/storage-policy-regression-200gb-20261112` is five commits ahead, zero behind, and is not merged. The production files `storage_manager.py`, `storage_policy.py` and `storage_config.json` on the candidate are byte-for-byte identical to current main; the candidate changes tests, storage documentation, account-switch helper/tests, and Actions audit/regression workflows only.

### Storage reserve and live quota

- [x] The already completed, user-authorized StorageManager workflow ran in an isolated temporary worktree against the live model directory. It set models allocation target to 200 GiB and reconciled the model reserve to residual capacity (`allocation − actual payload`). Final recorded payload was approximately 64.68 GiB; physically allocated reserve approximately 135.321 GiB; reserve logical size 145,299,319,502 bytes; allocated blocks 145,299,353,600 bytes.
- [x] Outputs reserve remained fixed at 0.5 GiB (512 MiB). At completion, `.storage_pause.lock` and `.storage_lease.json` were absent.
- [x] The earlier isolated StorageManager suite recorded 36 passed tests. This was a temporary worktree based on the older persistent checkout, not current-main regression evidence.
- [x] A newer read-only audit executed current-main `storage_manager.py --status` on `oec-1` and `oec-2` (11 November 2026, 20:16 UTC). Both observed models payload 64.68 GB / 200 GB target, 135.32 GB reserve, outputs reserve 512 MB, group use 2.06 TB, soft 2.00 TB, hard 2.10 TB, and 39.39/39.38 GB hard-limit headroom with grace active for approximately 6d22h28m. This is a timestamped reading, not write permission.
- [ ] No further reserve expansion/shrink, model download or large write. Refresh live quota and use the regular StorageManager admission before any future write. Never exceed the 2.10 TB hard quota or manipulate `.storage_reserve.bin` directly.

### Code regression and tests

- [x] Reviewed current-main residual-reserve logic and scoped `allow_soft_quota_overage`: it is only passed by residual model-reserve growth, requires fresh quota and a hard ceiling, and uses hard headroom; ordinary writes continue to use soft/grace admission.
- [x] Fixed two test-fixture isolation errors on the candidate branch by adding `live_lustre_quota=False` to the synthetic quota fixtures in `tests/test_storage_policy.py` and `tests/test_storage_manager.py`. Production live-quota-first behavior is unchanged.
- [x] Candidate regression workflow passed on the intermediate source revision after these two fixes (run [43095020135](https://github.com/xflexwork/OEC/actions/runs/43095020135)). The workflow ran the prescribed notebook/CLI/storage suites, Python compilation and notebook JSON checks. Exact aggregate test count could not be retrieved from the Actions log endpoint; do not claim an unverified total.
- [ ] The latest candidate regression run, which also includes the account-helper tests, is queued and has not yet run. The final source revision must pass before the branch is treated as fully verified.
- [ ] Main’s earlier regression failure is preserved in history: its synthetic quota test was overridden by live Lustre telemetry, and a separate synthetic critical-monitor fixture also used live quota. Both candidate fixtures now isolate test quota.

### Persistent A100 checkout — not yet synchronized

- [x] Read-only evidence confirms that `oec-1` and `oec-2` use the same persistent checkout `$HOME/OEC`, the same Git common directory, and the same home-level `.gitconfig` and `.git-credentials` files.
- [x] Last complete identity/worktree preflight (10 November) observed the persistent checkout on `fix/media-stack-supervision-20261019`, at the old project revision, with exactly: modified `storage_config.json`; untracked `tools/git_account_switch.py`; untracked `tools/git-credential-gh-account.sh`. These files must be preserved.
- [x] The preflight observed Git commit identity `xflexwork <xflexwork@gmail.com>`; `gh` was not installed; no repository-local credential helper was configured; non-interactive `git ls-remote origin HEAD` failed using the previous saved Git credential identity.
- [ ] Do not change the shared checkout yet. The updated read-only audit which checks the exact `storage_config.json` diff, runner registration metadata and OEC/Deploy/Play process markers is queued. Confirm there are no protected client/server/inference processes before any checkout change. The `oec-3` inspection has not yet completed.
- [ ] After the process audit and final candidate CI pass, preserve all three local-only paths in an explicit backup and Git stash, preserve the old branch/ref, fetch the candidate non-destructively, and switch only if the persistent checkout is safe to update. Never reset/clean or drop the stash. Reconcile the local storage config intentionally; do not overwrite it blindly.

### GitHub account authentication — not yet transferred

- [x] The GitHub connector identity is `xflexwork` and its repository permission for OEC is `admin`. This is **not** proof of the A100 CLI login.
- [x] The existing account helper and credential script were reviewed and added to the candidate branch. The candidate helper now requires exact `gh api user` identity, repository `.permissions.push=true`, read access and a non-mutating `git push --dry-run` before changing repo-local settings. Auth-status output is filtered; credentials are not put in remote URLs or logs.
- [ ] The intended A100 GitHub login must be explicitly confirmed; do not infer the username from `xflexwork@gmail.com` or from the ChatGPT connector identity.
- [ ] Complete GitHub device authorization interactively on the A100 host once `gh` is available; verify `gh auth status`, `gh api user`, OEC push permission, and HTTPS read/write dry-run. Do not paste a personal token or expose device codes/tokens in Action logs.
- [ ] Do not change the shared home-level credential helper/config until the shared oec-1/oec-2 effect is understood and target login is confirmed. The repository-local helper is still a shared-checkout setting.

### Current priority

1. Let the queued final storage/account-helper regression workflow complete.
2. Let the expanded three-runner read-only audit complete; verify process markers and exact local config diff.
3. Only then decide whether a safe persistent checkout sync is possible.
4. Complete A100 interactive GitHub login only after the intended login is confirmed.


**Snapshot timestamp:** 2026-10-19T18:28:04+05:30 (Asia/Kolkata)  
**Project:** OEC / AIREOS — core implementation, full-model research, product demonstration and academic deliverables  
**Purpose:** Current status and next actions. Refresh GitHub refs, jobs, logs, trackers and quota before treating this as live state. Permanent rules are in [`Prompt.md`](Prompt.md).  
**Main head before this documentation refresh:** `f41db4905849e738968e8ac8ee3fe3e272640fe2`. The model implementation is on `fix/media-stack-supervision-20261019`; refresh both refs at session start.  
**Actions policy:** user confirmed the Actions runner quota reset on 2026-10-19 and withdrew the prior $0-only prerequisite. Do not impose that veto. Use Actions as needed, batch meaningful tests/inference, and avoid same-group pending-run collisions. StorageManager model/storage admission remains separate.

The non-OEC-media repository summaries below remain from the earlier 15:13 snapshot and must be refreshed before acting on those workstreams. The current OEC model-inference evidence and next steps are in section 0 above.

## 1. Project window — unresolved

- [ ] Recover the **original project start date and 15-day deadline** from the original task/authoritative planning record. The records examined in this session did not establish either date. Do not reset the clock, guess the start date or claim a remaining-day count until this is verified.
- [ ] Once the start/deadline is evidenced, record both exact dates and the calculation method here; do not silently reset the deadline in later chats.

## 2. Snapshot scope and confidence

Read during this session: the OEC core branch/root listing, core `TODO.md`, `result.md`, `changelog/README.md`, live workflow YAML path filters, current Actions run list and relevant job logs; Full_Model README/TODO/EXPERIMENT_PLAN/result/test ledger, 19 October changelog, run 39213310959 job logs and key run report/persistence evidence; top-level listings for OEC-Viewer graphs, Report_Docs README and its continuation/checkpoint documents; current recent Actions summaries for Freezed, MOE, Deploy, Viewer, Report_Docs and Report_Logpoints.

Not fully inspected in this session: all source files on each repository's current head; every open PR; complete Viewer graph JSON bodies and all source links; detailed MoE implementation and runner; current PaperDock compilation/render output; local runner shell/process inventory. Runner facts below come from retrieved Action logs, not direct shell access. No new code test, model run or inference was executed by this session.

## 3. Current repository heads and latest relevant workflow evidence

## 0. Current model-inference handoff — supersedes the older OEC run table below

**Evidence checkpoint:** 2026-10-19T18:28:04+05:30. Feature code head at review time: `76bb7f7a392acc2fbddd7428532f18da8c0aaf80`; tracker-only updates may move the branch tip without changing the implementation source.

| Capability / run | Current evidence | State and next action |
|---|---|---|
| AudioGen — [39240127736](https://github.com/Killer4K-N/OEC/actions/runs/39240127736) | A100; 3 s mono 16 kHz WAV, 96,078 bytes, SHA-256 `6be1acb0cf36cacfc5ba4464ebbecb7f6f3bbe46f8e1e3bdbf88f2eef80bde3b`; 26.737 s; 5.155/5.385 GiB allocated/reserved. Artifact [12181271517](https://github.com/Killer4K-N/OEC/actions/runs/39240127736/artifacts/12181271517). | **PASS** |
| TRELLIS and LTX sidecars — [39240127757](https://github.com/Killer4K-N/OEC/actions/runs/39240127757) | A100. TRELLIS GLB 2,742,900 bytes, SHA-256 `e0d8f0a3a45921b4119a01a0b45f560d4604fb44da44454ddee2b912bd2fe0b7`. LTX H.264 MP4 242,547 bytes, 768×512, 2.083 s, SHA-256 `5d7d54de4354936f66867fecd19d20c0ab6972b5d997ca00c145ab0c1e54ec51`. Artifact report [12182600342](https://github.com/Killer4K-N/OEC/actions/runs/39240127757/artifacts/12182600342). | **PASS standalone only**; a combined production/media job remains open. |
| MusicGen — [39254306725](https://github.com/Killer4K-N/OEC/actions/runs/39254306725) | A100/environment checks and 4/4 offline contract tests passed. Actual inference failed because `facebook/musicgen-medium` was not fully cached and connection to the Hugging Face proxy failed with `No route to host`. No WAV produced. Artifact [12187572013](https://github.com/Killer4K-N/OEC/actions/runs/39254306725/artifacts/12187572013). | **BLOCKED before inference by cache/egress**; inspect model cache and runner network before retrying. |
| FLUX→TRELLIS — [39254474617](https://github.com/Killer4K-N/OEC/actions/runs/39254474617) | Offline tests had two errors in `tests/test_flux_image_pipeline.py`: managed output-root fixture omitted `flux.SYSTEM_DIRS["outputs"]`; scratch-output fixture outside `/tmp`. Inference steps skipped. Artifact [12187637374](https://github.com/Killer4K-N/OEC/actions/runs/39254474617/artifacts/12187637374). | **FAILED before inference**; repair test fixtures, then rerun current-head PNG→GLB pipeline. Do not weaken production path checks. |
| ACE-Step — [39254306716](https://github.com/Killer4K-N/OEC/actions/runs/39254306716) | Bootstrap cancelled before runner assignment, no evidence. Previous [39246077924](https://github.com/Killer4K-N/OEC/actions/runs/39246077924) timed out after 900 s while upstream was downloading a 4.46 GiB DiT file at 91–92%. New strict checkpoint/cache-only guard is committed at [b84398af](https://github.com/Killer4K-N/OEC/commit/b84398af2654f9ddffb00b34d7b3e995e1b38418), not live-verified. | **OPEN**; run current bootstrap once the serial lane clears and require an actual music artifact. |
| Kokoro → Whisper Turbo / Qwen3-ASR | Previous one-clip A100 acceptance [39209090292](https://github.com/Killer4K-N/OEC/actions/runs/39209090292). | Historical **PASS**; repeat against current code when useful. |

**Next order:** (1) fix FLUX test fixtures and rerun offline suites; (2) current-head FLUX PNG→TRELLIS GLB inference; (3) run ACE-Step managed bootstrap and live generation; (4) diagnose MusicGen cache/egress instead of repeating a known failed download; (5) build a local job-level multimodal orchestrator for FLUX/TRELLIS/LTX, AudioGen, ACE-Step/MusicGen and optional Kokoro/Whisper/Qwen3-ASR, with a hashed output manifest and final muxed artifact. Scope is model setup/inference/orchestration, not full-model training or OEC-Play deployment.

**Actions quota:** The user explicitly withdrew the prior $0-only prerequisite because Actions quota was reset. Use Actions when required. Preserve shared concurrency, runner identity, model licensing and StorageManager admission. A captured StorageManager reading from the MusicGen run at ~18:20 IST showed group usage 2.04/2.10 TB hard limit with ~56.71 GB headroom under active grace; models 232.81/280 GB with 52.44 GB reserve; outputs 293.74 MB/1 GB with 734.41 MB reserve. This is storage telemetry, not Actions quota, and it is not future write approval.


### Full-model training

- Repository: [OEC_AireOS_Full_Model](https://github.com/Killer4K-N/OEC_AireOS_Full_Model)
- **Main:** `6c15a2f8a3086ef989a31b46244b86eef57aac60`.
- **Training branch:** `work/phase1-a100-training-2026-10-09`, latest observed head `cc91b43dfdfb54baa56cce0f7947a9a25aaa3e13`.
- **Latest run:** [39213310959](https://github.com/Killer4K-N/OEC_AireOS_Full_Model/actions/runs/39213310959), job [117931347186](https://github.com/Killer4K-N/OEC_AireOS_Full_Model/actions/runs/39213310959/job/117931347186), successful. Run source SHA `8ed71e0a8bf13c91fcd48c8fcd5ad9d83a19a4b2`; the job committed/pushed evidence at `cc91b43...` after the run.
- Runner gate: `oec-train`, `oec_train`, A100. Three configuration-parallel arms were assigned to three distinct A100-SXM4-40GB devices. This is **configuration-parallel GPU execution, not DDP**.
- Three configurations completed 256 updates each (768 updates total): Base-4/LR 1e-4 validation total loss `0.308463`; Base-4/LR 5e-5 `0.361289`; Base-8/LR 1e-4 `0.238310`. The last was lowest of the three. Same-trajectory split: 24 training clips and 8 chronological holdout clips from TUM RGB-D fr1/xyz. Manifest SHA-256: `154f530859cb72afee97bc161f8fc7cce62f19fb6fdb106db8c4b7f3f6ce58b8`.
- The run evidence includes a persisted checkpoint of 2,699,274 bytes, SHA-256 `e0cb39ccbfdf01c8269f340d6a04c831c92191ec16218bfa1c7cb2aeb733208d`; persistence evidence is committed to the work branch. GitHub Actions artifact listing was empty; the job committed run-scoped evidence instead. Do not look for or claim a downloadable Actions artifact for this run.
- Interpretation: bounded real-data reconstruction/config comparison only. It does **not** establish independent-scene transfer, action-conditioned dynamics, physical accuracy, convergence or a complete world model. Prior telemetry on the preceding matched sequential/parallel comparison recorded low average utilization (~4–5%, max 10%), despite a 1.612× wall-time difference (61.712 s sequential vs 38.265 s parallel). Diagnose data/input/GPU utilization from saved telemetry before scaling more training.
- The 19 October Full_Model changelog already exists on its work branch. Refresh it/README/TODO/EXPERIMENT_PLAN against current head before any further claim; do not overwrite its history or merge work to main without approval.

### Remaining repositories and report status

| Repository | Latest status actually checked | Open requirement |
|---|---|---|
| [OEC_AireOS_Freezed](https://github.com/Killer4K-N/OEC_AireOS_Freezed) | Last visible readiness audit [38938127656](https://github.com/Killer4K-N/OEC_AireOS_Freezed/actions/runs/38938127656) completed as a diagnostic workflow success on 16 Oct; semantic readiness was previously **BLOCKED**. | Refresh live head/PR/job. PEFT, fresh quota, model/license/task approval and dataset provenance/schema/group-safe split gates must pass before training/downloads. |
| [OEC_AireOS_MOE](https://github.com/Killer4K-N/OEC_AireOS_MOE) | Current Actions query returned no runs. Last head recorded by an earlier source-scan checkpoint was `0fa06974199b60b6952f53da3ffbfeb28f6d0d7b`; this head was not refreshed in this session. | Recheck branch head, source, test ledger and live scheduler/routing evidence. Empty Actions history is not a pass. RRF/retrieval is not trained sparse MoE. |
| [OEC_Deploy](https://github.com/Killer4K-N/OEC_Deploy) | On `hpc-dgx-deployment`, SHA `daf50e3b5ee957776636f24507f0923344a6daf8`: source CI [39226859126](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39226859126) and persistent checkout sync [39226858925](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39226858925) passed. Server ensure [39226858867](https://github.com/Killer4K-N/OEC_Deploy/actions/runs/39226858867) failed. | Job 117975128828 ran on `oec-deploy` / host `scn28-mn` but had no `SLURM_JOB_ID`: no server was started. Re-test only from the active approved allocation; leave existing sessions/processes untouched. CI and sync do not prove live service or gameplay. |
| [OEC-Viewer](https://github.com/Killer4K-N/OEC-Viewer) | Latest visible validation [39036088314](https://github.com/Killer4K-N/OEC-Viewer/actions/runs/39036088314) passed on 17 Oct at `ebef5b66c6024fda5b045e5dd3c76c4726f2eb54`; two preceding runs failed. This session read root/diagram listings, not all graph bodies. | Read `payload.json`, `temp/temp_recent.json`, `diagrams/model_learning.json`, rules/audit and source links; audit graph schema, equations, node/edge IDs, versions and evidence boundaries before editing research claims. |
| [Report_Docs](https://github.com/Killer4K-N/Report_Docs) | Report/poster validator [39036265685](https://github.com/Killer4K-N/Report_Docs/actions/runs/39036265685) and Beamer validator [39036265649](https://github.com/Killer4K-N/Report_Docs/actions/runs/39036265649) passed on 17 Oct, but do not prove current sources are rebuilt/visually accepted. | PaperDock’s active poster source fix has **not yet been compiled**; recorded PDF state remains failed/unavailable. Compile from its UI, inspect log and full PDF, then reconcile authoritative deck version and rebuild/inspect the report. Read its current rules/checkpoint first. No $0 path for triggering builds is assumed. |
| [Report_Logpoints](https://github.com/Killer4K-N/Report_Logpoints) | Last visible validator [38902530680](https://github.com/Killer4K-N/Report_Logpoints/actions/runs/38902530680) passed on 16 Oct. | Reconcile source-checkpoint contradiction before changing cutoff: claimed inclusive cutoff 17 Oct vs policy saying through 15 Oct; JSON says 210 records but previously inspected `logpoints.csv` had 728 data rows. Refresh live head and count before reporting. |

## 4. Immediate checklist (prioritized)

### P0 — resume from current live state, not a duplicate run

- [ ] Read-only poll run 39225901764, job 117971993674. When it terminates, retrieve job/step states and logs, report JSON/artifact manifest and hashes; record each sidecar separately as passed, failed, skipped or blocked. Do not rerun the active job.
- [ ] Read-only poll run 39226037799 until a job is assigned; if it starts, retrieve its actual runner, job steps and logs. Do not dispatch a replacement while pending/in progress.
- [ ] Diagnose the test fixture in failed bootstrap 39225808196. Inspect `tests/test_storage_reserve_probe.py` and its fixture in the feature commit; correct the fixture's intended allocation and keep assertions for sparse/underallocated rejection. Test on the correct code branch without touching the real protected reserve or relaxing production guards.
- [ ] Recover and record the exact original 15-day project start/deadline before publishing any “days remaining” claim.

### P1 — highest-value engineering and research tasks

- [ ] Diagnose low GPU utilization using existing run-scoped telemetry/data-loader timing from Full_Model; do not scale up solely because three GPU jobs completed.
- [ ] Inspect the existing TUM RGB-D adapter and registration report. Canonical pose / RGB-depth registration must be verified before strong geometry/depth claims. Keep the same-trajectory holdout limitations explicit.
- [ ] Review source and license information for the proposed Everyday Manipulation 3D source without downloading raw data. Extract the fields/time alignment needed for action, pose, object and contact contracts; test adapter schema using safe fixtures first.
- [ ] Continue OEC demonstrator from currently validated paths only. Prior cache-only FLUX→TRELLIS evidence exists, but current source branch, the latest sidecar acceptance, exact UI request chain and current quota/lease need reconciliation before claiming present integrated readiness.
- [ ] For deployment, inspect the active-allocation startup contract and launch only inside an approved existing SLURM allocation with fresh runner/process/port ownership checks. Do not bypass its preflight.
- [ ] Preserve Freezed and MoE as separate workstreams. No adapter training or learned-router acceptance without their own ready data/model contracts and held-out baseline tests.

### P1 — academic deliverables

- [ ] Repair/compile the existing poster in PaperDock and visually inspect the exact rendered PDF; retain source, evidence and print-size/format checks.
- [ ] Reconcile the authoritative presentation version between PaperDock and GitHub; preserve older versions and overlays. Recheck all claims, citations/equations and Viewer diagram references.
- [ ] Rebuild and inspect the dissertation/report only after its evidence and claim crosswalk matches the selected presentation/poster. Preserve IITM class/layout and placeholders for personal/institutional fields.
- [ ] Maintain one content crosswalk for graph version/source, run/commit, metric/split/seed, limitation and exact report/poster/slide location. Do not trigger academic workflows until zero-cost execution is established.

### P2 — source inventory and synchronization

- [ ] Complete the six-graph Viewer evidence inventory and validate graph schema, IDs, edges, versions, equations and linked sources.
- [ ] Refresh current heads and PRs in all workstreams, especially Freezed and MOE. Do not extrapolate current status from historical scan records.
- [ ] Fix the Report_Logpoints checkpoint and row-count inconsistency using a fresh repository read.
- [ ] At session end, update this file's timestamp, the appropriate daily changelog and the existing tracker for each repository actually changed. Do not create duplicate summary/experiment rows.

## 5. Required acceptance gates before scaling work

- [ ] **Cost gate:** current workflows/triggers/runner billing and artifact path reviewed; no assumed free execution.
- [ ] **Data gate:** source terms/license, schema, sample quality, hashes and leakage-safe split reviewed.
- [ ] **Storage gate:** fresh authoritative quota and sanctioned StorageManager admission; no direct reserve-file use.
- [ ] **Compute gate:** exact runner/env, GPU allocation and occupancy, memory, output space, current job locks, and no overlap confirmed.
- [ ] **Training gate:** CPU tests, one-batch forward/backward, finite loss/gradients, optimizer/frozen ownership, checkpoint round-trip, reproducible seed and resume checks pass.
- [ ] **Evaluation gate:** task-matched baselines, held-out data, metrics/uncertainty, artifacts and failure analysis stored.
- [ ] **Demonstrator gate:** reproducible input → runtime → validated output → visible user result; report hashes, metadata, errors, latency and resource cost.
- [ ] **Academic gate:** claims match the exact runs, branches, graph versions and citations; report, deck and poster builds/rendering are actually reviewed.

## 6. Most important immediate next action

**Poll the existing OEC visual-sidecar job 117971993674/run 39225901764 and the pending bootstrap run 39226037799 read-only, then use their real outcomes to update this checklist. Do not start another GPU job.** In parallel, recover the authoritative 15-day start/deadline. Fresh quota, model/data licensing and $0 execution are hard gates for any subsequent costly or shared-state operation.
