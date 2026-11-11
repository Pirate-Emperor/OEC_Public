# OEC Daily Engineering Changelog — 2026-11-12

**Timezone:** Asia/Kolkata  
**Workstream:** Storage-manager correction, A100 checkout reconciliation and GitHub identity handoff.

## Storage reserve and quota

- A previously completed StorageManager run, performed in an isolated temporary worktree against the live models directory, set the models allocation target to 200 GiB and dynamically sized the models reserve to the unused allocation capacity. It recorded approximately 64.68 GiB payload and 135.321 GiB physically allocated reserve (logical size 145,299,319,502 bytes; allocated blocks 145,299,353,600 bytes). The outputs reserve remained fixed at 0.5 GiB. Both pause/lease markers were absent on completion.
- The earlier temporary worktree storage suite passed 36 tests. This is not a test of current-main source.
- Read-only StorageManager status against current-main source on oec-1 and oec-2 then measured group usage about 2.06 TB, soft quota 2.00 TB, hard quota 2.10 TB, hard headroom about 39.39 GB and active grace (~6d22h28m at capture). Models payload/reserve were 64.68/135.32 GB; outputs reserve 512 MB. No reserve mutation was made.
- Hard quota headroom is narrow and time-sensitive. No further reserve growth/shrink, model download or large write is authorized by this record.

## Storage policy code and regression

- Reviewed current-main `storage_manager.py`, `storage_policy.py`, `storage_config.json` and related tests.
- Confirmed the hard-quota exception is narrowly scoped to residual model-reserve growth. Normal writes continue using soft/grace admission and require fresh quota where configured.
- The source test workflow exposed two fixture defects: `test_preflight_uses_fresh_quota` and `test_critical_monitor_preserves_existing_reserve` used synthetic quota fixtures while allowing the A100 runner's live Lustre quota lookup to override them. Added `live_lustre_quota=False` to those two synthetic fixtures only; production StorageManager/StoragePolicy code is unchanged.
- Candidate regression run [43095020135](https://github.com/xflexwork/OEC/actions/runs/43095020135) passed after those fixture corrections. The workflow completed all prescribed suites, compilation and notebook JSON checks; the Actions log endpoint timed out when retrieving the detailed per-suite counts, so no aggregate count is asserted here.
- The final candidate source also adds account-helper checks to the regression workflow. Its latest queued run is tracked separately in the checklist; it has not yet been verified.

## Persistent A100 checkout and GitHub identity

- Read-only preflight on 10 November found the persistent OEC checkout on its older feature branch with exactly three local-only entries: modified `storage_config.json`, untracked `tools/git_account_switch.py`, and untracked `tools/git-credential-gh-account.sh`. Preserve all three.
- oec-1 and oec-2 share the same persistent checkout Git common directory and the same home-level Git config and credential file. A repository-local credential helper change is therefore shared by those runners.
- Git author identity already resolves to `xflexwork <xflexwork@gmail.com>`. This does not prove the authenticated GitHub login.
- The A100 environment did not have `gh` installed, lacked a GitHub CLI hosts config and had no repo-local credential helper; non-interactive HTTPS origin read failed under the old saved username credential.
- The ChatGPT GitHub connector reports login `xflexwork` with admin permission on OEC. This is separate from the A100 CLI account. The intended A100 login remains unconfirmed.
- Added account helper code to the candidate branch. Before modifying repository-local Git settings it verifies selected `gh api user`, OEC push permission, HTTPS read, and a non-mutating `git push --dry-run`. The helper avoids putting tokens in remotes or printing token material.
- The expanded A100 read-only audit checks the local config diff, runner registration metadata and OEC/Deploy/Play process markers. It is still queued; no persistent checkout sync has been performed.

## Current state

- Candidate branch: `fix/storage-policy-regression-200gb-20261112`, ahead of main at the last comparison. Production storage manager, policy and config files are byte-identical to main; changes are tests, documentation, audit workflow and account helper/tests.
- Main was not modified. No OEC_Deploy files were modified. No client, server, inference or GPU process was restarted, killed or interrupted.
- Next order: final regression with account helper tests; read-only process/config audit across A100 runners; only then decide if safe non-destructive persistent checkout sync is possible; complete A100 device flow after intended login is confirmed.

