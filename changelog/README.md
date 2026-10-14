# OEC Work Changelog

Daily engineering records live here. Use the local Asia/Kolkata date in each filename. Append work to the current day's file while the date remains the same; create a new `CHANGELOG-YYYY-MM-DD.md` on the next date.

## Daily records

- [2026-10-14 — Read-only quota telemetry diagnosis and runtime blockers](CHANGELOG-2026-10-14.md)
  - [Connector_1 run 38555689884](https://github.com/Killer4K-N/Connector_1/actions/runs/38555689884) succeeded in producing a read-only report: the configured quota snapshot is missing and `quota_check` is unavailable on scn17-mn.
  - Model storage is on shared Lustre with very high measured filesystem free capacity; that is not user/project quota proof, so package/model write admission remains blocked.
  - The live OEC checkout is detached at `081aaf34...` with tracked dirty paths; no live sync/reset occurred. Reserve size differs from an earlier logged value and needs read-only reconciliation.
  - TRELLIS runtime diagnostic [run 38587490301](https://github.com/Killer4K-N/Connector_1/actions/runs/38587490301) passed its 7 then-current tests and safely admitted a low-footprint GPU, then exposed a missing local `pipeline.json` lookup in offline mode. The pinned-config/local-overlay correction is on [Connector_1 diagnostic branch](https://github.com/Killer4K-N/Connector_1/tree/diagnose/trellis-asset-generation-20261014); loader validation [run 38598822415](https://github.com/Killer4K-N/Connector_1/actions/runs/38598822415) is in progress and the expanded 10-test run [38598881722](https://github.com/Killer4K-N/Connector_1/actions/runs/38598881722) is queued. Fresh GLB acceptance remains pending.
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
- **Structured experiment/test log:** [`test.json`](../test.json) — currently 35 experiment records.
- **Cumulative significant results:** [`result.md`](../result.md)
- **Reusable interactive-model implementation convention:** [`model_entrypoint_convention.md`](../docs/model_entrypoint_convention.md)

Update the daily changelog, `TODO.md`, `test.json`, and `result.md` at the end of each OEC task. Do not create additional parallel TODO/test/result files.


- **2026-10-14 — TRELLIS asset proof and current live-runtime blockers**
  - Current candidate [run 38571665298](https://github.com/Killer4K-N/OEC/actions/runs/38571665298) passed 28/28 static tests plus compilation and notebook JSON validation.
  - Historic TRELLIS run [37942265623](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623) produced a real 8,950,028-byte GLB; the recovered artifact was re-opened independently with `trimesh` and contains 97,783 vertices and 92,819 faces. It is linked as a downloadable file in `result.md`.
  - Current offline TRELLIS smoke [38571363231](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231) discovered the cached model/source/input but stopped at GPU occupancy before inference; no current GLB was generated. FLUX image generation is similarly blocked by active compute processes. Quota telemetry remains absent, so no download/install bypass is allowed.


## 2026-10-14 — Main branch integration

- Integrated the reviewed TRELLIS/FLUX notebooks and CLI, storage-output admission fixes, regression tests and cumulative tracking files into `main`.
- Candidate test run [38572444007](https://github.com/Killer4K-N/OEC/actions/runs/38572444007) passed 28/28 static tests, Python compilation and four notebook JSON checks; main-triggered validation is pending.
- Historical TRELLIS image-to-3D generation is confirmed by [run 37942265623](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623): 8,950,028-byte GLB artifact [11622412194](https://github.com/Killer4K-N/Connector_1/actions/runs/37942265623/artifacts/11622412194) reopens with 97,783 vertices and 92,819 faces. Those earlier Oct 14 TRELLIS attempts were blocked before the later cache-only loader fix; see the newer successful GLB evidence below. FLUX end-to-end generation remains unverified.

- **Main CI result recorded:** [run 38575822798](https://github.com/Killer4K-N/OEC/actions/runs/38575822798) on main commit `9c9d7acc...` passed 28/28 static tests, Python compilation and 4/4 notebook JSON checks. Earlier shared GPU generation attempts were blocked at admission; the later TRELLIS cache-only runtime now succeeds. FLUX end-to-end generation remains unverified.

- **Latest GPU smoke retries:** TRELLIS [run 38571363231 attempt 2](https://github.com/Killer4K-N/Connector_1/actions/runs/38571363231) and FLUX [run 38559255790 attempt 2](https://github.com/Killer4K-N/Connector_1/actions/runs/38559255790) both blocked safely at GPU occupancy; the retry results are recorded in `test.json` and the Oct. 14 changelog. Historical TRELLIS GLB remains independently validated.


- **TRELLIS fix runtime-verified:** Connector_1 run 38598822415 generated a fresh GLB (8,870,632 bytes; SHA-256 0ba06de0e028d975b7108f4dcb9856a81dcdd76037e94cc852883fc5b2ad6b1e) and reopened it with trimesh (96,532 vertices, 91,986 faces). OEC candidate CI 38601987037 passed 34 tests; review PR #10 is open, not merged.
- **Follow-up checks:** corrected Connector_1 retry 38601626147 had passed tests and was generating. Exact-run artifact guard run 38602330418 was queued. Artifact 11913875417 from the failed test-only run is stale, not proof of a fresh result.
