# Changelog — 2026-10-11

## Runner status and compute-node location

- Investigated the misleading `STOPPED` output produced when `runner_control.py list` is executed on a different compute node from a runner whose directory is shared.
- Updated the candidate controller so `list` reports **local process visibility** separately from the GitHub registry state. An idle runner online on another node is shown as `PROCESS=NOT_RUNNING_HERE | GITHUB=online/idle`, not as stopped.
- Added host location reporting. New starts write hostname, start time, username, and listener PID to `.oec_runner_host.json` inside the runner directory. Existing installs can fall back to the runner's `_diag/Runner_*.log` `Machine name:` entry.
- Updated `status` to show location and updated `stop` to refuse to claim a remote runner stopped when no listener is visible locally but GitHub still reports it online.
- Added a duplicate-start guard: when the registry reports the configured runner online but no listener is visible on the current node, `start` refuses to launch a second listener and reports the recorded host.
- Scope: changes are isolated to branch `fix/runner-control-stop-status-20261009`; no change to `main` or to the A100 `~/OEC` filesystem.

## Live A100 inventory verification

- Read-only matrix workflow successfully assigned and completed one no-GPU diagnostic job on every existing label `connector-1` through `connector-5`.
- Observed host mapping: `connector-1` → `scn17-mn`; `connector-2` → `scn20-mn`; `connector-3` → `scn20-mn`; `connector-4` → `scn17-mn`; `connector-5` → `scn21-mn`.
- GitHub Actions job IDs: connector-1 `3`, connector-2 `23`, connector-3 `24`, connector-4 `25`, connector-5 `26`; all five verification jobs completed successfully.
- On all five nodes, `~/OEC/tools/runner_control.py` had Git blob SHA `458b6d4d47cec6516af67d193d3da8fd6a165f17`. The tested candidate controller has blob SHA `c70142fc8873596d1efad04e3b09c19125fc9121`, confirming local code had not yet been synced.
- Each runner's expected `OEC/gpu/connector_N/actions-runner` path reported `.runner` and `bin/Runner.Listener` present in the final inventory; no nested `actions-runner/actions-runner` install was found.
- `connector-5` is already accepting jobs on `scn21-mn`; the earlier attempt to create it on `scn37-mn` failed due to that node's proxy policy, so this verification did not treat that failed setup as a new registration.
- Live inventory run: https://github.com/Killer4K-N/Connector_1/actions/runs/38081689687
- Detailed workspace/path verification run: https://github.com/Killer4K-N/Connector_1/actions/runs/38081809409

## Validation

- New regression tests cover remote-idle list output, diagnostic-log host fallback, host metadata written on start, remote-safe stop behavior, and duplicate-start prevention.
- `python -m py_compile tools/runner_control.py`: passed.
- Focused runner-control regressions: **12/12 passed**.
- Full repository suite: **36/36 passed** after the workflow installed `huggingface_hub`, which the pre-existing upload-daemon test imports. Before that CI adjustment, the full suite had 33 passes and one error caused only by this missing test-environment dependency.
- Earlier first attempt on the diagnostic-log test exposed a fixture with escaped literal newlines; corrected the fixture. The final focused and full runs passed.
- The full suite emits a non-failing `ResourceWarning` for an unclosed `upload_daemon.log` handler in `hf_upload_daemon.py:21`; this is outside the runner-control change.
- Final full validation run: https://github.com/Killer4K-N/OEC/actions/runs/38081353311
