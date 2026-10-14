# OEC Work Changelog

Daily engineering records live here. Use the local Asia/Kolkata date in each filename. Append work to the current day's file while the date remains the same; create a new `CHANGELOG-YYYY-MM-DD.md` on the next date.

## Daily records

- [2026-10-14 — Read-only quota telemetry diagnosis and runtime blockers](CHANGELOG-2026-10-14.md)
  - [Connector_1 run 38555689884](https://github.com/Killer4K-N/Connector_1/actions/runs/38555689884) succeeded in producing a read-only report: the configured quota snapshot is missing and `quota_check` is unavailable on scn17-mn.
  - Model storage is on shared Lustre with very high measured filesystem free capacity; that is not user/project quota proof, so package/model write admission remains blocked.
  - The live OEC checkout is detached at `081aaf34...` with tracked dirty paths; no live sync/reset occurred. Reserve size differs from an earlier logged value and needs read-only reconciliation.
  - The connector-2 QA recovery job separately failed on Slurm host discovery/accounting DB connectivity. Queue/process mutation is not claimed.

- [2026-10-12 — Runtime blocker remediation and official upstream compatibility review](CHANGELOG-2026-10-12.md)
  - Audited the real failed result in [Connector_1 run 38161901000](https://github.com/Killer4K-N/Connector_1/actions/runs/38161901000): source/static tests passed, but fresh quota data was unavailable, so runtime installs and inference remained gated.
  - Corrected the isolated Connector_1 remediation helpers to require fresh quota for package/model writes; constrain xFormers and AudioCraft repair installs to binary wheels; and defer stopped QA-worker retirement until its replacement is confirmed RUNNING.
  - Reviewed official Microsoft TRELLIS.2, Facebook xFormers, Hugging Face Diffusers FLUX.2, and AudioCraft requirements. The helper changes still need workflow validation; no runtime fix is claimed until actual attention/model/image/AudioCraft tests pass.
  - The queue remains read-only at 225 rows; no package/model downloads or QA queue mutations were performed during source editing.

- [2026-10-11 — TRELLIS, Jupyter, QA, paths, and runtime diagnosis](CHANGELOG-2026-10-11.md)
  - The standalone TRELLIS.2 CLI/Gradio entry point and safer TRELLIS/FLUX notebook flows were added on the feature branch. Future interactive-model requirements are in `docs/model_entrypoint_convention.md`.
  - The final 3-runner offline/static matrix at [run 38157725815](https://github.com/Killer4K-N/Connector_1/actions/runs/38157725815) passed 38 tests per runner across connector-1, connector-2, and connector-5: 17 TRELLIS/entry-point tests, 5 AudioCraft notebook tests, 10 QA queue/worker guard tests, and 6 path-alias tests (114 passes total).
  - Latest targeted sync [run 38161747478](https://github.com/Killer4K-N/Connector_1/actions/runs/38161747478) copied the current `TODO.md`, `test.json`, `result.md`, daily changelog and index into the live OEC checkout after validation. `SYNC_SCRIPT_SYNTAX=PASS`, `TRACKING_FILES_VALIDATION=PASS`, and `STAGED_NOTEBOOK_AND_CLI_VALIDATION=PASS`; all four static suites passed again (17/5/10/6). Its overall result remains incomplete because storage admission blocked package installation and TRELLIS inference.
  - Plural aliases are created and verified: `aireos_datasets -> aireos_dataset`, `aireos_inputs -> aireos_input`, and `aireos_outputs -> aireos_output`. Canonical singular paths were preserved.
  - The installed `xformers==0.0.29.post1` fails CUDA attention with `torch==2.6.0+cu124`; `flash-attn` is absent. The TRELLIS.2 model cache probe misses `microsoft/TRELLIS.2-4B`. Fresh quota admission is still unavailable on all three compute runners, so no bypass is allowed.
  - The official Diffusers v0.37.0 release notes list Flux2 Klein support, while current Hugging Face Hub docs expose `get_cached_repo_tree`; this supports the proposed released dependency-set direction, but a real import/image-generation run is still blocked by quota admission.
  - FLUX.2 Klein weights are cached, but `diffusers==0.40.0.dev0` cannot import the FLUX pipeline with `huggingface-hub==0.36.2`: Diffusers expects `get_cached_repo_tree`, which is missing. The notebook's released dependency set is gated and still requires real import/image-generation verification.
  - QA worker source selects GPU before importing PyTorch and guards model download/cache purge. The existing connector-2 QA process was observed stopped (state `T`) under an interactive session; it was not resumed or duplicated. Queue rows were not changed.
  - AudioCraft imports work in phase1, but `pip check` reports the `thinc==8.3.6` / `numpy==1.26.4` conflict. The original reported wheel-build traceback was not found; phase1 was not changed.
  - No changes were merged into `main`; the dirty live working tree was not reset or cleaned.


- **Follow-up on 2026-10-14 — storage write guards and offline FLUX attempt**
  - Reviewable OEC candidate [`fix/storage-admission-write-guards-20261014`](https://github.com/Killer4K-N/OEC/tree/fix/storage-admission-write-guards-20261014), tested at [run 38559330370](https://github.com/Killer4K-N/OEC/actions/runs/38559330370): 27/27 static tests, py_compile, and four notebook JSON checks pass.
  - Source paths now require fresh quota for model/package/output writes and recheck admission inside managed locks; shared runtime is still gated by missing authoritative telemetry.
  - After the tracking-only commit, [run 38559861094](https://github.com/Killer4K-N/OEC/actions/runs/38559861094) again passed the unchanged 27-test suite plus compilation and JSON checks.
  - Cached FLUX snapshot is present, but [run 38559255790](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790) found active compute processes on both A100s and correctly refused to start inference.

## Persistent project tracking

- **One active TODO list:** [`TODO.md`](../TODO.md)
- **Structured experiment/test log:** [`test.json`](../test.json) — currently 25 experiment records.
- **Cumulative significant results:** [`result.md`](../result.md)
- **Reusable interactive-model implementation convention:** [`model_entrypoint_convention.md`](../docs/model_entrypoint_convention.md)

Update the daily changelog, `TODO.md`, `test.json`, and `result.md` at the end of each OEC task. Do not create additional parallel TODO/test/result files.
