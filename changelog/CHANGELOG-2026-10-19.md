# Changelog — 2026-10-19 (Asia/Kolkata)

## Continuation entry point and live-state recovery

**Recorded at:** 2026-10-19T15:13:52.946+05:30  
**Repository/branch:** `Killer4K-N/OEC`, `main`; previous head checked immediately before this update: `f6b9d7d484480d3f121241964fc28f69dbb5e3a4`.  
**Scope:** Documentation and navigation only. No model/service code, workflows, dataset, checkpoints, reserve files, runner state or shared runtime was changed.

- Added `docs/Prompt.md` as the permanent first-read point. It defines repo routing, mandatory read order, evidence rules, $0 Actions safeguards, storage/security restrictions, tracker conventions and academic crosswalk rules. Changing run status stays out of this file.
- Added `docs/checklist.md` as a timestamped live-state snapshot with unresolved 15-day deadline provenance, latest inspected Actions/jobs, experiment evidence and prioritized acceptance criteria.
- Added a short entry-point note to `TODO.md`; retained the established consolidated backlog. The detailed current snapshot is linked rather than duplicated.
- Kept all new/edited files under `docs/**`, `TODO.md` and `changelog/**`. The inspected live OEC workflow ignores these paths for its main-branch push filter; no workflow trigger was deliberately called. After commit, verify the changed paths and reread the latest Actions list.
- Current visual-sidecar run 39225901764 was still in progress at the read; its job 117971993674 on `oec-1` / `scn30-mn` had reached the no-download isolated-sidecar test. Bootstrap run 39226037799 was pending with no job object returned. Do not duplicate either.
- Bootstrap run 39225808196 failed a CPU/mock test because its synthetic reserve fixture had size 1 MiB but only 512 allocated bytes; subsequent storage writes/download/inference steps were skipped. Keep the production guard strict and fix the test fixture in the feature branch only after source review.
- Full_Model run 39213310959 completed three 256-update TUM RGB-D configuration-parallel arms on three A100s (not DDP). Validation losses were 0.308463, 0.361289 and 0.238310; eight holdout clips came from the same trajectory. Checkpoint persistence is evidenced on the work branch; Actions artifact listing was empty. Keep all claims bounded to real-data reconstruction/config comparison.
- The deploy server check in run 39226858867 failed because no `SLURM_JOB_ID` was present on `oec-deploy`; it did not start a service. The source CI and checkout sync runs are not live-service acceptance.
- The authoritative 15-day project start/deadline was not found in the inspected planning records. The next session must recover it from an authoritative original record; do not guess or reset the clock.

## Validation and next step

- No new unit/integration test, training job, inference, workflow dispatch, rerun or artifact upload was performed as part of this documentation update.
- Acceptance of this documentation update requires read-back of the resulting branch/head and file blobs, then confirmation that the documentation-only paths did not start an Action.
- Next action: poll the currently active visual-sidecar job and pending bootstrap run read-only, inspect final logs/artifacts and update the checklist using their terminal results.


## 2026-10-19T18:28:04+05:30 — model-inference handoff refresh

Updated the permanent continuation rules and checklist to reflect the user's Actions-quota reset instruction. The detailed handoff is saved in `docs/MODEL_PIPELINE_CONTINUATION_PROMPT.md`. Current A100 evidence: AudioGen and standalone TRELLIS/LTX passed; MusicGen did not reach inference because model cache/network access failed; current FLUX→TRELLIS attempt stopped on two unit-test fixture errors; ACE-Step guard is committed but its latest bootstrap did not run. Next: fix FLUX fixtures, rerun combined inference, verify ACE-Step on A100 and diagnose MusicGen cache/egress. StorageManager rules remain separate from Action-runner quota.
