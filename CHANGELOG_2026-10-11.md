# Changelog — 2026-10-11

## Runner status and compute-node location

- Investigated the misleading `STOPPED` output produced when `runner_control.py list` is executed on a different compute node from a runner whose directory is shared.
- Updated the candidate controller so `list` reports **local process visibility** separately from the GitHub registry state. An idle runner online on another node is shown as `PROCESS=NOT_RUNNING_HERE | GITHUB=online/idle`, not as stopped.
- Added host location reporting. New starts write hostname, start time, username, and listener PID to `.oec_runner_host.json` inside the runner directory. Existing installs can fall back to the runner's `_diag/Runner_*.log` `Machine name:` entry.
- Updated `status` to show location and updated `stop` to refuse to claim a remote runner stopped when no listener is visible locally but GitHub still reports it online.
- Added a duplicate-start guard: when the registry reports the configured runner online but no listener is visible on the current node, `start` refuses to launch a second listener and reports the recorded host.
- Scope: changes are isolated to branch `fix/runner-control-stop-status-20261009`; no change to `main` or to the A100 `~/OEC` filesystem.

## Validation

- New regression tests cover remote-idle list output, diagnostic-log host fallback, host metadata written on start, remote-safe stop behavior, and duplicate-start prevention.
- `python -m py_compile tools/runner_control.py`: passed.
- Focused runner-control regressions: **12/12 passed**.
- Full repository suite: **36/36 passed** after the workflow installed `huggingface_hub`, which the pre-existing upload-daemon test imports. Before that CI adjustment, the full suite had 33 passes and one error caused only by this missing test-environment dependency.
- Earlier first attempt on the diagnostic-log test exposed a fixture with escaped literal newlines; corrected the fixture. The final focused and full runs passed.
- The full suite emits a non-failing `ResourceWarning` for an unclosed `upload_daemon.log` handler in `hf_upload_daemon.py:21`; this is outside the runner-control change.
- Final full validation run: https://github.com/Killer4K-N/OEC/actions/runs/38081353311
