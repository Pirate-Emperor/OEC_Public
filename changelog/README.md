# OEC Work Changelog

Daily engineering records live here. Use the local Asia/Kolkata date in each filename. Append work to the current day's file while the date remains the same; create a new `CHANGELOG-YYYY-MM-DD.md` on the next date.

## Daily records

- [2026-10-11 — TRELLIS, Jupyter, QA, paths, and runtime diagnosis](CHANGELOG-2026-10-11.md)
  - The standalone TRELLIS.2 CLI/Gradio entry point and safer TRELLIS/FLUX notebook flows were added on the feature branch. Future interactive-model requirements are in `docs/model_entrypoint_convention.md`.
  - The final 3-runner offline/static matrix at [run 38157725815](https://github.com/Killer4K-N/Connector_1/actions/runs/38157725815) passed 38 tests per runner across connector-1, connector-2, and connector-5: 17 TRELLIS/entry-point tests, 5 AudioCraft notebook tests, 10 QA queue/worker guard tests, and 6 path-alias tests (114 passes total).
  - The targeted live sync [run 38157960859](https://github.com/Killer4K-N/Connector_1/actions/runs/38157960859) passed staging, all four test suites, and alias checks. Its overall result remains incomplete because quota admission blocked package installation and TRELLIS inference; no packages/models were installed/downloaded by that run.
  - Plural aliases are created and verified: `aireos_datasets -> aireos_dataset`, `aireos_inputs -> aireos_input`, and `aireos_outputs -> aireos_output`. Canonical singular paths were preserved.
  - The currently installed `xformers==0.0.29.post1` fails CUDA attention with `torch==2.6.0+cu124`; `flash-attn` is absent. The TRELLIS.2 model cache probe misses `microsoft/TRELLIS.2-4B`. Fresh quota admission is still unavailable on all three compute runners, so no bypass is allowed.
  - FLUX.2 Klein weights are cached, but the installed `diffusers==0.40.0.dev0` fails to import with `huggingface-hub==0.36.2` because `get_cached_repo_tree` is unavailable. The notebook's proposed released version set remains quota-gated and must still be runtime-verified.
  - QA worker source now selects GPU before importing PyTorch and guards model download/cache purge. The existing connector-2 QA process was observed stopped (state `T`) under an interactive session; it was not resumed or duplicated. Queue rows were not changed.
  - AudioCraft imports work in phase1, but `pip check` reports the `thinc==8.3.6` / `numpy==1.26.4` conflict. The original reported wheel-build traceback was not found; phase1 was not changed.
  - No changes were merged into `main`; the dirty live working tree was not reset or cleaned.

## Persistent project tracking

- **One active TODO list:** [`TODO.md`](../TODO.md)
- **Structured experiment/test log:** [`test.json`](../test.json)
- **Cumulative significant results:** [`result.md`](../result.md)
- **Reusable interactive-model implementation convention:** [`model_entrypoint_convention.md`](../docs/model_entrypoint_convention.md)

Update the daily changelog, `TODO.md`, `test.json`, and `result.md` at the end of each OEC task. Do not create additional parallel TODO/test/result files.
