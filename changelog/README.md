# OEC Work Changelog

Daily engineering records live here. Use the local Asia/Kolkata date in each filename. Append work to the current day's file while the date remains the same; create a new `CHANGELOG-YYYY-MM-DD.md` on the next date.

## Daily records

- [2026-10-11 — TRELLIS, Jupyter, and source-sync verification](CHANGELOG-2026-10-11.md)
  - Historical isolated A100 test generated a real TRELLIS mesh and GLB, but the current shared `phase2_3d` run fails before inference because its installed xFormers build has no usable CUDA extension for Torch 2.6.0+cu124.
  - Temporary Jupyter Server and actual `phase2_3d` notebook-kernel smoke checks passed; a user's existing server/browser tunnel was not confirmed active.
  - The live OEC checkout is not synchronized with remote `main` and has pre-existing dirty/untracked work; it was not reset or edited.
  - Follow-up targeted sync (Connector-1 run 38141547014) copied the two TRELLIS notebooks and two TRELLIS Python tests; all nine earlier static regressions passed. A later sync (run 38150226432) added the standalone TRELLIS CLI, Gradio support, notebook run instructions, setup idempotency, the model-entrypoint convention, and additional tests; its 14 targeted tests passed. Dependency install and live inference still require fresh quota telemetry.
  - Confirmed path convention issue: .env-resolved singular aireos_dataset, aireos_input, and aireos_output exist; plural aliases do not. No directories were renamed.
  - New three-runner audit on connector-1, connector-2, and connector-5 is in progress under [run 38150422509](https://github.com/Killer4K-N/Connector_1/actions/runs/38150422509); results must be checked before considering the current runtime fixed.
  - AudioCraft imports in phase1, but pip check finds the thinc 8.3.6 / NumPy 1.26.4 conflict. QA queue contains stale/missing-file records, and current A100 sampling showed idle GPUs. Details and the login-node DNS blocker are in the daily log.
