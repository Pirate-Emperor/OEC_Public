# OEC daily changelog — 2026-10-28

Branch: `fix/media-stack-supervision-20261019`
Candidate before tracker/sync correction: `f9b3f095e7f711d88a996ad3842d140a312e6586`

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
