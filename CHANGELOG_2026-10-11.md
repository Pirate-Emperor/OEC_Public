# Changelog — 2026-10-11

## Runner status and compute-node location

- Investigated the misleading `STOPPED` output produced when `runner_control.py list` is executed on a different compute node from a runner whose directory is shared.
- Updated the candidate controller so `list` reports **local process visibility** separately from the GitHub registry state. An idle runner online on another node is shown as `PROCESS=NOT_RUNNING_HERE | GITHUB=online/idle`, not as stopped.
- Added host location reporting. New starts write hostname, start time, username, and listener PID to `.oec_runner_host.json` inside the runner directory. Existing installs can fall back to the runner's `_diag/Runner_*.log` `Machine name:` entry.
- Updated `status` to show location and updated `stop` to refuse to claim a remote runner stopped when no listener is visible locally but GitHub still reports it online.
- Added a duplicate-start guard: when the registry reports the configured runner online but no listener is visible on the current node, `start` refuses to launch a second listener and reports the recorded host.
- The initial state/location implementation was merged in PR #3 (`ec4ebcfa14d709f199a81bbeb0751a1fc708be8b`), and real-format compatibility fixes were merged in PR #7 (`7ef49b7afaa613b8553a1b61f9a6067e8fd7d5a1`). The follow-up source sync to the A100 directory was subsequently completed and verified on `scn17-mn`; details are recorded below.

## Live A100 inventory verification

- Read-only matrix workflow successfully assigned and completed one no-GPU diagnostic job on every existing label `connector-1` through `connector-5`.
- Observed host mapping: `connector-1` → `scn17-mn`; `connector-2` → `scn20-mn`; `connector-3` → `scn20-mn`; `connector-4` → `scn17-mn`; `connector-5` → `scn21-mn`.
- GitHub Actions job IDs: connector-1 `3`, connector-2 `23`, connector-3 `24`, connector-4 `25`, connector-5 `26`; all five verification jobs completed successfully.
- On all five nodes, the preliminary inventory reported a digest of `458b6d4d47cec6516af67d193d3da8fd6a165f17`, but its hash routine used an escaped separator and that value was not a valid Git blob SHA. The guarded deployment preflight computed the actual local controller blob as `88050dbfa12072ab6d53e8dbd3be13ae73421627`; the merged source blob is `7ccb4a95819c8feddaa4e3093d999d92cd8685b9`.
- Each runner's expected `OEC/gpu/connector_N/actions-runner` path reported `.runner` and `bin/Runner.Listener` present in the final inventory; no nested `actions-runner/actions-runner` install was found.
- `connector-5` is already accepting jobs on `scn21-mn`; the earlier attempt to create it on `scn37-mn` failed due to that node's proxy policy, so this verification did not treat that failed setup as a new registration.
- Live inventory run: https://github.com/Killer4K-N/Connector_1/actions/runs/38081689687
- Detailed workspace/path verification run: https://github.com/Killer4K-N/Connector_1/actions/runs/38081809409

## Real runner metadata compatibility follow-up

- The actual `.runner` files inspected on the live runners have a UTF-8 BOM, use `agentName`, and contain `gitHubUrl` for the repository URL. The `serverUrl` field is an Actions service endpoint and must not be used to derive the GitHub repository. No service-endpoint URL is recorded in this changelog.
- Updated `_runner_identity` and `status` to parse `utf-8-sig`, accept `agentName`, and prefer `gitHubUrl`.
- Updated host metadata seeding for an already-running listener to obtain its start time from Linux `/proc` when available, instead of incorrectly treating the time of the first observation as its start time. Added a separate observation timestamp.
- Added regression tests for BOM-prefixed runner metadata, the real `agentName` / `gitHubUrl` field combination, correct GitHub API endpoint derivation, safe status output, and accurate start-time stamping.
- Follow-up validation: focused runner-control suite **15/15 passed**; full repository test suite **39/39 passed**. Run: https://github.com/Killer4K-N/OEC/actions/runs/38082197015
- Two initial guarded sync attempts failed safely before any write: the first rejected a bad payload digest, and the second rejected an incorrect expected-old digest inherited from the faulty inventory. After correcting the guard to the actual local Git blob SHA, the later sync completed successfully. No failed attempt modified the local file.

## Validation

- New regression tests cover remote-idle list output, diagnostic-log host fallback, host metadata written on start, remote-safe stop behavior, and duplicate-start prevention.
- `python -m py_compile tools/runner_control.py`: passed.
- Focused runner-control regressions: **12/12 passed**.
- Full repository suite: **36/36 passed** after the workflow installed `huggingface_hub`, which the pre-existing upload-daemon test imports. Before that CI adjustment, the full suite had 33 passes and one error caused only by this missing test-environment dependency.
- Earlier first attempt on the diagnostic-log test exposed a fixture with escaped literal newlines; corrected the fixture. The final focused and full runs passed.
- The full suite emits a non-failing `ResourceWarning` for an unclosed `upload_daemon.log` handler in `hf_upload_daemon.py:21`; this is outside the runner-control change.
- Final full validation run: https://github.com/Killer4K-N/OEC/actions/runs/38081353311


## Guarded local source sync and host metadata bootstrap (completed)

- Used the dedicated `Connector_1` self-hosted runner on `scn17-mn` to synchronize `~/OEC/tools/runner_control.py` from the verified OEC `main` source. The source/payload blob SHA was pinned to `7ccb4a95819c8feddaa4e3093d999d92cd8685b9`.
- Pre-sync local blob SHA: `88050dbfa12072ab6d53e8dbd3be13ae73421627`. The final workflow used a correct Git blob header with a NUL separator, verified the payload and Python syntax before writing, created backup `tools/runner_control.py.pre-sync-20261011T100729Z.bak`, replaced the file atomically, and verified the installed blob SHA exactly matched the expected source.
- Post-sync Python compilation passed. The first smoke run's check was overly broad: it failed on 404 responses from unrelated legacy runner configurations (for example A3/A4 and older deploy runners) even though the five Connector_1 runners were reporting online. The smoke check was scoped to the target Connector_1 registry; the subsequent sync smoke run passed. These unrelated legacy 404 entries remain visible in `list` but no longer invalidate the Connector_1 sync check.
- Created controller host metadata only for runners whose `status --no-github` confirmed an existing local Listener process. The workflow then invoked `start --no-github-wait`, which detected each existing listener and recorded metadata without starting a duplicate process.
- Final host mapping confirmed by reading the actual `runner_control.py list` output on `scn17-mn`: connector-1 → `scn17-mn`; connector-2 → `scn20-mn`; connector-3 → `scn20-mn`; connector-4 → `scn17-mn`; connector-5 → `scn21-mn`. All five entries reported `GITHUB=online` and the expected `HOST=` value. Remote connectors correctly display `PROCESS=NOT_RUNNING_HERE` on `scn17-mn` rather than being mislabeled stopped.
- Successful sync and smoke check: https://github.com/Killer4K-N/Connector_1/actions/runs/38130903358
- Successful host metadata bootstrap for all five connectors: https://github.com/Killer4K-N/Connector_1/actions/runs/38130924049
- Final end-to-end `list` output verified all five expected hosts: https://github.com/Killer4K-N/Connector_1/actions/runs/38131004727
