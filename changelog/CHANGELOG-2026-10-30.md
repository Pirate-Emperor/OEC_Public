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
