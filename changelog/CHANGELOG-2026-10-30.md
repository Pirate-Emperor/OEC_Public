## 2026-10-30 23:52 IST — current-head regression and canonical sync pass; model callbacks still gated

### Implemented
- OEC workflows route model/UI acceptance to OEC-owned `oec-1` and root-sync/storage static regression to OEC-owned `oec-2`; Full_Model training labels are no longer used as OEC runner identities.
- Root runner identity accepts verified `Killer4K-N/OEC` legacy metadata while requiring the live Actions repository to remain `xflexwork/OEC`.
- The root-sync watchdog handles HTTP 409 force-cancel races by rereading run state and leaving unresolved active jobs to the persistent-checkout safety guard.
- Corrected the root reconciler's duplicated Git stash pathspec separator; added regression checks for runner routing, transfer alias, watchdog conflict, storage test runner and stash pathspec.

### Verified runs
- [41101748877](https://github.com/xflexwork/OEC/actions/runs/41101748877): 13/13 Gradio UI launch modes HTTP 200; all are UI-only and all callbacks were skipped.
- [41103554752](https://github.com/xflexwork/OEC/actions/runs/41103554752): 18/18 notebook structural audit PASS, 80/88 code cells syntax checked, no saved error outputs. Overall acceptance failed at model preflight before any of the 13 callbacks.
- [41105142772](https://github.com/xflexwork/OEC/actions/runs/41105142772): current-head static/storage/media regression suite SUCCESS on `oec-2/scn28-mn`; 23 unittest groups / 229 logged cases, py_compile and four notebook JSON checks passed.
- [41105142713](https://github.com/xflexwork/OEC/actions/runs/41105142713): all three root-sync workflow jobs SUCCESS. Runner identity passed with `legacy_transfer_alias=true`; canonical root synchronized to `875350ff1ad6f98fde07793ae3b66c3851c837ea`; Freezed, Full_Model, MOE and OEC_Deploy submodule pins passed.
- Root sync preserved prior local tracked state in stash `fda1c72a5e82d852a695eb1b06d4ef22e62e1bf8`, and two loose files under the run-scoped recovery directory. Prior local HEAD was `21d8b1f915a72edd2c20c9bde026373672d99c52`. No broad clean/reset was used.

### Unresolved live acceptance
- The full Gradio callback matrix was not invoked because `/nlsasfs/home/lmedge/rahkus/aireos_models/.storage_pause.lock` (PID 2036305, timestamp 1793107308.942003) hit the fail-closed host rule on `oec-1/scn28-mn`; legacy recovery permits only `oec-train/scn30-mn`. PID owner/liveness on that designated host is unknown. Do not remove or bypass the lock.
- Fresh telemetry showed models/output areas NORMAL, about 89.06 GB quota write headroom, two idle A100s. This is not a storage-capacity failure.
- Zero current accepted WAV, FLAC, TXT, PNG, GLB or MP4 model outputs. Next: authorized owner-host lock inspection, then rerun all 13 callbacks and validate output hashes and file formats.

---
# OEC changelog — 2026-10-30

## Gradio workflow routing and acceptance hardening

- Updated `.github/workflows/oec-root-sync.yml`: replaced the Full_Model training-runner label audit with a read-only identity check for OEC's `oec-2` runner; routed canonical root synchronization to `oec-2`. The audit no longer calls GitHub runner-label mutation or inspects `oec-train` / `oec-train-2`.
- Updated `.github/workflows/oec-demo-notebook-acceptance.yml` and `.github/workflows/oec-gradio-ui-launch-smoke.yml` to use OEC's `oec-1` runner.
- Updated `.github/workflows/oec-flux-pipeline-smoke.yml` to target `oec-1` and retained its explicit `scn30-mn` lock-owner gate; no inference is authorized merely by a runner label.
- Updated the demo acceptance `contracts` step to run with `always() && !cancelled()`, so static tests can finish after a failed preflight without allowing any model inference step to skip its existing successful-preflight requirement.
- Added regression tests covering OEC-owned runner routing, root-sync identity, retained lock-owner guard, and static-contract behavior.

## Evidence recovered

- [OEC UI run 40671622051](https://github.com/xflexwork/OEC/actions/runs/40671622051): job 122759546646 on runner `oec-1` / host `scn28-mn`; all 13 configured modes returned Gradio HTTP 200 and `PASS_UI_ONLY`, each explicitly `callback=SKIPPED_UI_ONLY`; `GRADIO_UI_ONLY_FAILURES=0`.
- [OEC root-sync run 40818428276](https://github.com/xflexwork/OEC/actions/runs/40818428276): job 123264981530 on `oec-2` / `scn28-mn` failed because it inspected `oec-train` metadata registered to `Killer4K-N/OEC_AireOS_Full_Model`; canonical sync was skipped.
- [Full_Model bridge run 40818187983](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40818187983): job 123264150263 on `oec-train-2` / `scn28-mn` failed with HTTP 403 fetching private `xflexwork/OEC`; all callback steps were skipped; no artifacts were uploaded.
- Earlier OEC full acceptance run [40671622024](https://github.com/xflexwork/OEC/actions/runs/40671622024) stopped before callbacks: the observed `oec-1/scn28-mn` did not match the explicit `scn30-mn` lock-recovery restriction. The host guard is retained.
- Therefore actual current-source Gradio callback and asset acceptance remains PENDING. Historical UI checks and historical model outputs are not counted as current-head acceptance.

## Changes not performed

- No cache/checkpoint deletion, storage-reserve operation, lock removal, package install, Conda environment mutation, runner re-registration, runner relabeling, or `main` merge.
- All model-inference steps retain the successful-preflight prerequisite.
