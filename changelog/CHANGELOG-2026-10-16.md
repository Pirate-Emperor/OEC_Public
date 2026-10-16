# OEC Engineering Changelog — 2026-10-16

## Objective

Continue the OEC frozen-weight readiness work safely by addressing the blocker established in the dedicated runner's read-only Lustre quota investigation. Use OEC-Viewer's frozen fine-tuning architecture as the acceptance boundary: storage admission must be proven before a PEFT model or dataset write. No training was started.

## Read-only quota evidence

- Dedicated `oec-freeze` runner investigation: [run 38898669614](https://github.com/Killer4K-N/OEC_AireOS_Freezed/actions/runs/38898669614) completed successfully; the probe/parser suite passed 8/8 tests.
- The recorded Lustre group quota for `lmedge` at capture was usage 2,215,673,952 KiB (about 2,113.03 GiB), soft quota 2,147,483,648 KiB (2,048 GiB), and hard limit 2,254,857,830 KiB (about 2,150.40 GiB). This was roughly 65.03 GiB over soft with 37.37 GiB to hard and a reported grace of about 6 days 3 hours. This is a dated sample, not proof of current headroom.
- The runner found user-level block quota unset and the OEC shared directories owned by group `lmedge` (GID 55000). Since the applicable observed constraint is group quota, an old one-limit snapshot cannot safely represent this state.
- The read-only probe did not create/update a snapshot, invoke the OEC storage manager, inspect/control reserve files, open model/data files, download anything, or start training.

## Implementation on isolated source branch

- Source branch: [fix/lustre-soft-hard-quota-snapshot-20261016](https://github.com/Killer4K-N/OEC/tree/fix/lustre-soft-hard-quota-snapshot-20261016); latest source commit: [6182edd4](https://github.com/Killer4K-N/OEC/commit/6182edd4cafe22f65145b94e1f66998b31bcc182).
- Extended `tools/quota_snapshot.py` with a backward-compatible structured schema-v2 writer that represents usage, soft quota, hard limit, grace, identity type/name, timestamp, and source separately. The CLI is a writer only; it does not run `lfs quota` or otherwise acquire quota itself.
- Updated `storage_policy.py` so schema v2 keeps soft quota as the conservative admission boundary and exposes hard-limit headroom only for diagnostics. Usage above soft remains valid telemetry but supplies zero admission headroom and blocks new writes, even while grace/hard-limit headroom remains. Legacy unversioned single-limit snapshots retain their strict behavior.
- Hardened the consumer to reject unknown schema versions, missing schema-v2 limit/identity/source fields, identity-free structured values, negative or fractional limits, both soft/hard limits unset, non-finite timestamps, and non-object JSON roots. Large integer byte counts are preserved without round-tripping through float.
- Added regression coverage and documented the schema. No source changes were merged to OEC `main`.

## CI attempts and fix

- First hardening attempt: [run 38903339731](https://github.com/Killer4K-N/OEC/actions/runs/38903339731) failed one storage-policy test because an old hard-limit-overage fixture omitted the required schema-v2 identity/source. The new strict consumer correctly refused that malformed fixture. Earlier test groups passed; the failed suite stopped the later quota-snapshot test group and final notebook checks.
- Corrected the fixture with `quota_kind=group`, `quota_name=research`, and a source string; production code was unchanged in this follow-up: [commit 6182edd4](https://github.com/Killer4K-N/OEC/commit/6182edd4cafe22f65145b94e1f66998b31bcc182).
- Final hosted CI: [run 38903458777](https://github.com/Killer4K-N/OEC/actions/runs/38903458777), [job 116981112079](https://github.com/Killer4K-N/OEC/actions/runs/38903458777/job/116981112079), concluded success. All six test groups passed: 12 + 5 + 5 + 6 + 12 + 7 = **47 tests, 0 failures**. Python compilation passed, and JSON/Python-cell parsing passed for `pipeline_trellis_3d.ipynb` (16 cells), `pipeline_trellis_3d_only.ipynb` (15), `pipeline_flux_only.ipynb` (10), and `pipeline_audiocraft.ipynb` (6).

## Review and operational status

- Opened [draft PR #12](https://github.com/Killer4K-N/OEC/pull/12) for review. It remains unmerged and undeployed; no code was integrated into main.
- **Do not refresh or write the quota snapshot yet.** The capture is not current now, and changing the schema in a review branch does not mean that deployed runtime readers have the schema-v2 policy. Obtain a fresh read-only quota sample through the authorized procedure, review the soft/hard/grace fields, then explicitly decide how/when the reviewed producer/policy should be deployed and the snapshot published.
- OEC-Viewer [Frozen Fine-Tuning graph](https://github.com/Killer4K-N/OEC-Viewer/blob/main/diagrams/model_learning.json) remains the project acceptance contract: no model/data write until authoritative fresh storage admission, exact model/checkpoint/license review, and source-specific dataset provenance/schema/count/split approval pass.
- No snapshot was written/refreshed; no storage reserve or shared runtime filesystem was touched; no package install, model/data download, queue mutation, or training run occurred.

## Sources

- [OEC-Viewer Frozen Fine-Tuning architecture](https://github.com/Killer4K-N/OEC-Viewer/blob/main/diagrams/model_learning.json)
- [Official Lustre quota administration](https://wiki.lustre.org/Lustre_Quota_Administration)
- [Read-only quota probe and 8-test suite](https://github.com/Killer4K-N/OEC_AireOS_Freezed/actions/runs/38898669614)
- [Final structured snapshot/admission regression CI](https://github.com/Killer4K-N/OEC/actions/runs/38903458777)
- [Draft review PR #12](https://github.com/Killer4K-N/OEC/pull/12)
