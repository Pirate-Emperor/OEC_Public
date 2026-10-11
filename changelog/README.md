# OEC Work Changelog

Daily engineering records live here. Use the local Asia/Kolkata date in each filename. Append work to the current day's file while the date remains the same; create a new `CHANGELOG-YYYY-MM-DD.md` on the next date.

## Daily records

- [2026-10-11 — TRELLIS, Jupyter, and source-sync verification](CHANGELOG-2026-10-11.md)
  - Historical isolated A100 test generated a real TRELLIS mesh and GLB, but the current shared `phase2_3d` run fails before inference because its installed xFormers build has no usable CUDA extension for Torch 2.6.0+cu124.
  - Temporary Jupyter Server and actual `phase2_3d` notebook-kernel smoke checks passed; a user's existing server/browser tunnel was not confirmed active.
  - The live OEC checkout is not synchronized with remote `main` and has pre-existing dirty/untracked work; it was not reset or edited.
  - See the daily log for the traceback, successful historical run/artifact, official source checks, and safe remediation sequence.
