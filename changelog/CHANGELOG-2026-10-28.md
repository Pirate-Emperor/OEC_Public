# OEC daily changelog — 2026-10-28

Branch: `fix/media-stack-supervision-20261019`
Candidate before tracker/sync correction: `f9b3f095e7f711d88a996ad3842d140a312e6586`

## Follow-up — 2026-10-29 09:52 IST: pinned current-source callback acceptance

- The xflexwork/OEC_AireOS_Full_Model repository owns the registered oec-train / oec-train-2 runners. To avoid changing registration or labels, the acceptance workflow was added there on branch work/oec-gradio-callback-acceptance-20261029.
- Workflow run [40817297589](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40817297589) fetches OEC source commit 662f8225f110163cbd8e2f60c9548c4839ce8566 into a clean Actions workspace and requests actual Gradio callback plus asset validation for the configured model providers.
- Status is QUEUED, not accepted. D2E training run [40813924732](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40813924732) is in progress on the same runner and prepared-data EDA [40815451090](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40815451090) is queued ahead. Trusted StorageManager configuration and GPU admission have not yet been checked by this job.
- Cache deletion and package/environment installation paths were disabled for this bridge; model weights, if needed, may only be prepared through StorageManager. No cache/lock was deleted, no Conda environment was recreated, and no new output is marked accepted.

## Follow-up — 2026-10-29 10:02 IST: storage-config and lock-scope guard corrections

- Runner-side workflow revision `3a7ce66c1796200d37b2a5a5415a7f90f2fefbeb` now checks both `$HOME/OEC` and the already-existing `$HOME/OEC_feature_sync` worktree for trusted `storage_config.json`, validates a regular non-symlink config with models/outputs and quota snapshot settings, and copies only the validated file into the temporary job checkout. It does not synthesize configuration.
- Dead storage-lock recovery now runs only with its explicit authorized runner/host identity (`oec-train` / `scn30-mn`). If a pause lock or lease is present on another runner, the job fails closed instead of mutating it.
- Latest acceptance [run 40817769289](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40817769289) remains queued behind training [40813924732](https://github.com/xflexwork/OEC_AireOS_Full_Model/actions/runs/40813924732). Actual callback and asset validation is still NOT VERIFIED.

## Evidence

- Gradio UI launch: [40671622051](https://github.com/xflexwork/OEC/actions/runs/40671622051) — all 13 configured cases passed in UI-only mode; does not assert model callback success.
- Static/storage regression: [40671622040](https://github.com/xflexwork/OEC/actions/runs/40671622040) — PASS, including 37 Gradio/notebook tests and selected notebook JSON checks.
- Full model acceptance: [40671622024](https://github.com/xflexwork/OEC/actions/runs/40671622024) — failed before inference at runner/StorageManager validation. Real model callback steps were skipped, and no new current-candidate generated assets were accepted.
- A100 root sync: [40671622088](https://github.com/xflexwork/OEC/actions/runs/40671622088) — failed at repository-origin guard before reconciliation; canonical checkout SHA sync was not verified.

## Changes

- Updated the canonical A100 reconciliation allow-list to explicitly recognize the active `xflexwork/OEC` repository as well as the existing `CalamityStriker/OEC` origin. The sync script continues to enforce its existing serialized, non-destructive recovery, active-process, worktree, storage-admission and submodule checks.
- Refreshed `docs/checklist.md`, `TODO.md`, `test.json`, `result.md` and the changelog index with exact current evidence.
- No new model asset is marked accepted. Asset acceptance must be backed by a real Gradio submit, generated output file, hash/size evidence and format-specific decode/parse validation.

## Outstanding acceptance

1. Verify the follow-up root-sync workflow reports the canonical A100 checkout at the resulting branch SHA and confirms final local status.
2. Run the current candidate's real Gradio callbacks on the intended A100 runner(s), producing and validating audio/transcription/image/3D/video outputs for applicable models.
3. Preserve existing environments and caches; do not override storage locks or call UI-only launch a generation pass.


## Follow-up: root-sync Git authentication

- [Run 40678285024](https://github.com/xflexwork/OEC/actions/runs/40678285024) passed the repo-origin guard and live storage preflight but failed at Git fetch due missing authentication for the persistent checkout. No canonical SHA confirmation was emitted.
- Root-sync workflow now passes its repository-scoped read-only token to the script as an ephemeral Git extraheader inherited by nested Git processes; it is never written to the persistent checkout.
- Re-run must prove canonical A100 SHA equals the new branch SHA and report final clean status. This sync result does not substitute for current-candidate Gradio output generation/validation.


## Corrective follow-up — runner selectors and root-sync authentication

- Run 40678737412 failed before fetch because a prior auth patch emitted escaped Bash variable expansion. This is explicitly recorded; the code has been corrected.
- Reconciliation now authenticates from the read-only workflow token without persisting credentials and fetches the explicit `xflexwork/OEC` target branch, rather than assuming the canonical checkout's legacy origin is the feature source.
- Main model acceptance now uses the specified `oec-train` runner; root-sync and other relevant A100 workflows use `oec-train-2`. Legacy lock recovery is still confined to `oec-train/scn30-mn`, with owner PID, lock age and lease checks intact.
- Run evidence is still required before marking sync or current-candidate asset generation as PASS.


## 2026-10-29 07:12 IST follow-up — progress status and workflow correction

At inspection, branch head was `9e41ef4952cc2887268b8654519e0fcda6b8b268`. [Root-sync run 40680899602](https://github.com/xflexwork/OEC/actions/runs/40680899602) failed before job evidence because the runner-label audit job was self-dependent. The candidate correction (workflow blob `b4f18c4d87010aaf5c285d88be8f0eed925408f7`) makes the audit depend on the cutoff job only and canonical sync depend on both the cutoff and audit jobs. A separate static contract-test correction (blob `6652ff259697fdf41c3b8f1cf3e3e11f2eac210b`) asserts the intended DAG.

The current model acceptance [40680901503](https://github.com/xflexwork/OEC/actions/runs/40680901503) was pending and the static/storage run [40680901706](https://github.com/xflexwork/OEC/actions/runs/40680901706) was queued when inspected. Neither is a pass. Actual Gradio callbacks and generated assets remain unverified on the current head; the last full acceptance [40671622024](https://github.com/xflexwork/OEC/actions/runs/40671622024) failed before inference. The previous UI-only success [40671622051](https://github.com/xflexwork/OEC/actions/runs/40671622051) proves launch only. Canonical A100 sync still requires a successful run reporting the checkout SHA and final status.



## 2026-10-29 07:16 IST update — progress after root-sync DAG fix

Current source is `fd73717fd38d9fca4b5058ac909703ea68c202c3`. The root-sync workflow dependency has been corrected and committed. New root-sync run [40802365371](https://github.com/xflexwork/OEC/actions/runs/40802365371) has started; its cutoff/watchdog step was still in progress at the last poll. Canonical sync has not yet reported the final A100 checkout SHA or final status. Model acceptance [40802365390](https://github.com/xflexwork/OEC/actions/runs/40802365390) was queued/pending and static/storage tests [40802365318](https://github.com/xflexwork/OEC/actions/runs/40802365318) were queued. No current-head model-generated asset has been accepted. The last full model acceptance [40671622024](https://github.com/xflexwork/OEC/actions/runs/40671622024) failed before inference; UI launch pass [40671622051](https://github.com/xflexwork/OEC/actions/runs/40671622051) is older and UI-only.

Acceptance is still strictly: actual Gradio callback generates non-empty output, format-specific file validation passes, and canonical A100 sync explicitly proves `$HOME/OEC` SHA equals the branch SHA and reports final status. No Conda environment or package set was changed; no protected cache or storage lock was removed.


## 2026-10-29 07:18 IST — runner repository identity mismatch

Current branch head at inspection: `367d097417c33eff63f419c83c91c0d1a8b927af`. [Root-sync run 40802549636](https://github.com/xflexwork/OEC/actions/runs/40802549636) completed its cutoff job successfully, then the runner-label audit failed. The log reported that local runner `oec-train` has `.runner` repository identity `Killer4K-N/OEC_AireOS_Full_Model`, not `xflexwork/OEC`; no labels were changed and the canonical sync job was skipped. This is a runner registration/repository ownership mismatch. It is unsafe to rewrite the runner registration or add labels from this repo without verifying which repository should own the runner.

Current-head real Gradio callback acceptance is still NOT VERIFIED: [run 40802365390](https://github.com/xflexwork/OEC/actions/runs/40802365390) was cancelled before inference, and static/storage run [40802365318](https://github.com/xflexwork/OEC/actions/runs/40802365318) was cancelled. The prior full acceptance [40671622024](https://github.com/xflexwork/OEC/actions/runs/40671622024) failed before inference; UI-only run [40671622051](https://github.com/xflexwork/OEC/actions/runs/40671622051) does not prove generated assets. The current work has not accepted a WAV, transcript, PNG, GLB or MP4 generated by the current-head Gradio callbacks.
