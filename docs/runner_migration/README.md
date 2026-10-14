# Runner migration: legacy connector evidence and OEC runner pool

**Updated:** 2026-10-14 (Asia/Kolkata)

## Destination runner pool

New GPU jobs in this migration target only the OEC repository's self-hosted runners and require all of these labels: `self-hosted`, `linux`, `x64`, `gpu`, `a100`, plus exactly one of `oec-1`, `oec-2`, or `oec-3`. GitHub label matching is cumulative; a runner must carry every label listed in `runs-on`. See the [GitHub runner-label documentation](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/use-in-a-workflow).

Non-GPU static regression workflows may remain on `ubuntu-latest`; they do not use the legacy connector runners.

## Legacy history archive

The former runner workflow source repository is [Killer4K-N/Connector_1](https://github.com/Killer4K-N/Connector_1). Its Actions API reported 677 workflow runs. The migration fetched all seven pages and archived 677 unique records in [`connector_1_actions_runs.json`](./connector_1_actions_runs.json).

Captured fields include workflow name/path/id, run id, display title, branch, commit SHA, trigger, attempt, status, conclusion, timestamps, actor, PR references and canonical Action-run URL. Run-level outcomes in the snapshot: 305 successful, 236 failed, 122 cancelled, 13 skipped and 1 queued.

This is a metadata/history migration, not a relocation of GitHub's underlying run objects. Original job logs and binary artifacts remain accessible through the source-run links in the JSON. The latest TRELLIS GLB and report are also cross-linked in OEC's `test.json`, `result.md`, daily changelog and this repository's Action records.

## Relevant migrated results

- **TRELLIS root cause:** cached weight snapshot `af44b45f2e35a493886929c6d786e563ec68364d` had no `pipeline.json`, so the normal loader attempted a Hugging Face Hub lookup while the job was offline.
- **TRELLIS fix:** use the pinned, validated pipeline config in a private `/tmp` snapshot overlay; symlink cached weights read-only; construct local Hugging Face cache metadata; and load the local overlay while Hub access is disabled.
- **Final TRELLIS run:** [Connector_1 run 38602330418](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418) passed 10/10 regression tests, completed model load, inference, GLB export and geometry reopen. Artifact [11914941709](https://github.com/Killer4K-N/Connector_1/actions/runs/38602330418/artifacts/11914941709); 8,865,916-byte GLB; SHA-256 `22caca5fe9c02c50c095e4385a7c17e94b214b5fc7d87417b94b48c796a89257`; 96,672 vertices and 92,062 faces.
- **FLUX legacy smoke:** [run 38559255790](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790) was blocked by GPU admission and did not create a PNG. The new OEC runner flow must test this afresh instead of claiming the connector result as a successful generation.
- **Quota constraint:** prior connector diagnostics could not find a fresh quota snapshot or the `quota_check` command on the old host. New workflows must not bypass OEC StorageManager admission or download missing models/packages to force a passing test.

## Migration sequence

1. Preserve the legacy Action run inventory and outcome links (done).
2. Run a read-only probe across all three OEC labels, capture one artifact per runner, and verify the actual runner name, CUDA/GPU, Python environment and cache/package inventory.
3. Run TRELLIS/FLUX generation only on an explicitly selected OEC runner after the inventory report. Use cached assets and a local temporary output for the diagnostic smoke; publish the generated artifact with exact-run paths.
4. Keep the regular source-entry workflows (CLI and notebooks with Gradio) reviewable in OEC's PR and record any new runner job/artifact ids in `test.json`, `result.md`, `TODO.md` and the dated changelog.
