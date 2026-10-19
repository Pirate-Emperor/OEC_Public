# OEC project continuation checklist

**Snapshot timestamp:** 2026-10-19T15:13:52.946+05:30 (Asia/Kolkata)  
**Project:** OEC / AIREOS — core implementation, full-model research, product demonstration and academic deliverables  
**Purpose:** Current status and next actions. Refresh GitHub refs, jobs, logs, trackers and quota before treating this as live state. Permanent rules are in [`Prompt.md`](Prompt.md).  
**Current OEC source branch:** `main` at `f6b9d7d484480d3f121241964fc28f69dbb5e3a4` when this snapshot was prepared.  
**Actions policy:** no workflow was deliberately triggered by this work. Keep the $0 rule.

## 1. Project window — unresolved

- [ ] Recover the **original project start date and 15-day deadline** from the original task/authoritative planning record. The records examined in this session did not establish either date. Do not reset the clock, guess the start date or claim a remaining-day count until this is verified.
- [ ] Once the start/deadline is evidenced, record both exact dates and the calculation method here; do not silently reset the deadline in later chats.

## 2. Snapshot scope and confidence

Read during this session: the OEC core branch/root listing, core `TODO.md`, `result.md`, `changelog/README.md`, live workflow YAML path filters, current Actions run list and relevant job logs; Full_Model README/TODO/EXPERIMENT_PLAN/result/test ledger, 19 October changelog, run 39213310959 job logs and key run report/persistence evidence; top-level listings for OEC-Viewer graphs, Report_Docs README and its continuation/checkpoint documents; current recent Actions summaries for Freezed, MOE, Deploy, Viewer, Report_Docs and Report_Logpoints.

Not fully inspected in this session: all source files on each repository's current head; every open PR; complete Viewer graph JSON bodies and all source links; detailed MoE implementation and runner; current PaperDock compilation/render output; local runner shell/process inventory. Runner facts below come from retrieved Action logs, not direct shell access. No new code test, model run or inference was executed by this session.

## 3. Current repository heads and latest relevant workflow evidence

### OEC core

- **Main:** `f6b9d7d484480d3f121241964fc28f69dbb5e3a4`.  
- **Active feature branch:** `fix/media-stack-supervision-20261019`, head `74abb2f77d9076cf00e8bf0b2c2bc95b642457ce`. Keep feature implementation on this branch; main changes here are tracking/documentation only unless otherwise authorized.

| Run / job | State at snapshot | Actual evidence / next action |
|---|---|---|
| [39225901764 — visual media sidecar smoke](https://github.com/Killer4K-N/OEC/actions/runs/39225901764), job [117971993674](https://github.com/Killer4K-N/OEC/actions/runs/39225901764/job/117971993674) | **In progress** on `oec-1`, host `scn30-mn`; source SHA `86298cfbfb01a723efdb4d5b01f5ef35fb9a2fd3` | Steps through runner/env validation, compile, guarded Brain/LTX queue regressions, StorageManager status and expired plain pause-lock handling completed. Step 8 (“Test each visual sidecar in isolation without model downloads”) was in progress; final StorageManager readout/artifact upload still pending. Re-check run/jobs/log/artifacts read-only. Do not launch a duplicate. |
| [39226037799 — model bootstrap](https://github.com/Killer4K-N/OEC/actions/runs/39226037799) | **Pending** on `fix/media-stack-supervision-20261019`; source SHA `74abb2f77d9076cf00e8bf0b2c2bc95b642457ce`; no job object returned at the snapshot check | Pending is not running. Do not launch another bootstrap. Re-check after state changes. |
| [39225808196 — model bootstrap failure](https://github.com/Killer4K-N/OEC/actions/runs/39225808196), job 117971686653 | **Failed** on `oec-1` / `scn30-mn`, source SHA `be0215e2f480438a4c0969db02707fc70439f55b` | CPU/mock test `test_managed_status_must_agree_with_reserve_file_size` errored because its fixture was 1 MiB size / 512 bytes allocated and the probe correctly rejected it as sparse/underallocated. Subsequent storage write, download and inference steps were skipped. Treat as a test-fixture failure to fix in the feature branch, not proof of a live reserve-file failure. |
| [39225531165 — earlier sidecar smoke failure](https://github.com/Killer4K-N/OEC/actions/runs/39225531165) | Failed, older commit `d31fe0ab8fb72957462d19765b4e2fd46eb7a4a2` | Preserve as failed history; do not replace it with the later still-active run. |

**Last measured StorageManager state from run 39225808196 (historical, not fresh admission):** models 219.97/280 GB with ~60.04 GB reserve; outputs ~290.02 MB/1 GB with ~734.41 MB reserve. Both showed WARNING (usage above soft quota while grace was active; logged hard-limit headroom ~69.29 GB). The manager reported it could not update the outputs reserve during a managed operation/unresolved lease. Do not treat that snapshot as authorization for new writes, downloads or training. Obtain fresh approved telemetry and manager admission for a future operation; never access the protected reserve file directly.

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
