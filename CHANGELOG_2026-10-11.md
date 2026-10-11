# Changelog — 2026-10-11

## Runner status and compute-node location

- Investigated the misleading `STOPPED` output produced when `runner_control.py list` is executed on a different compute node from a runner whose directory is shared.
- Updated the candidate controller so `list` reports **local process visibility** separately from the GitHub registry state. An idle runner online on another node is shown as `PROCESS=NOT_RUNNING_HERE | GITHUB=online/idle`, not as stopped.
- Added host location reporting. New starts write hostname, start time, username, and listener PID to `.oec_runner_host.json` inside the runner directory. Existing installs can fall back to the runner's `_diag/Runner_*.log` `Machine name:` entry.
- Updated `status` to show location and updated `stop` to refuse to claim a remote runner stopped when no listener is visible locally but GitHub still reports it online.
- Added a duplicate-start guard: when the registry reports the configured runner online but no listener is visible on the current node, `start` refuses to launch a second listener and reports the recorded host.
- The initial state/location implementation was merged in PR #3 (`ec4ebcfa14d709f199a81bbeb0751a1fc708be8b`), and real-format compatibility fixes were merged in PR #7 (`7ef49b7afaa613b8553a1b61f9a6067e8fd7d5a1`). The A100 source sync is complete; subsequent readable-list and cross-node host-persistence improvements are documented below.

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
- Two initial guarded sync attempts failed safely before any write because of an incorrect payload hash and then an incorrect expected-old hash. After the guard was corrected to the verified local file hash, the sync succeeded with a backup and exact post-write hash verification. The readable table was deployed in a later guarded sync; cross-node host persistence is included in the current final sync.

## Validation

- New regression tests cover remote-idle list output, diagnostic-log host fallback, host metadata written on start, remote-safe stop behavior, and duplicate-start prevention.
- `python -m py_compile tools/runner_control.py`: passed.
- Focused runner-control regressions: **12/12 passed**.
- Full repository suite: **36/36 passed** after the workflow installed `huggingface_hub`, which the pre-existing upload-daemon test imports. Before that CI adjustment, the full suite had 33 passes and one error caused only by this missing test-environment dependency.
- Earlier first attempt on the diagnostic-log test exposed a fixture with escaped literal newlines; corrected the fixture. The final focused and full runs passed.
- The full suite emits a non-failing `ResourceWarning` for an unclosed `upload_daemon.log` handler in `hf_upload_daemon.py:21`; this is outside the runner-control change.
- Final full validation run: https://github.com/Killer4K-N/OEC/actions/runs/38081353311


## Readable runner inventory and selectable columns

- Replaced the raw one-line-per-runner path/status dump with a compact aligned table. Default columns are `NAME`, `HOST`, `PROCESS`, and `GITHUB`; entries are sorted by displayed runner name.
- Added `list --columns name,host,github`, `list --columns name,process,pid`, and `list --columns all`; recognized columns are name, host, process, pid, github, started, repo, path, source, and error. Friendly aliases include `runner`, `node`, `state`, `status`, `directory`, and `api_detail`.
- Added `list --name connector-1,connector-2`, `list --no-github`, and `list --details`. The default view summarizes DNS/API errors such as `API down (DNS)` or `API 404 (repo/access)` instead of printing entire exceptions in every row. `--details` expands raw diagnostic details.
- Clarified that `not here` means no `Runner.Listener` is visible in the current node's `/proc`; it does not mean stopped. A host marked `(last)` is persisted history, not proof the remote process is still active. The list uses a shorter per-request GitHub API timeout to keep the inventory responsive when network/DNS is degraded.
- Final CI validation after host-persistence, name-sorting, and bounded API-timeout changes: focused runner-control suite **20/20 passed** and full repository suite **44/44 passed**. Run: https://github.com/Killer4K-N/OEC/actions/runs/38132506639

## Cross-node host metadata for pre-existing runners

- Confirmed why legacy runners such as `a3-test` could show `HOST=unknown` on `scn17-mn` even though `status --name a3-test --no-github` on `scn24-mn` showed `HOST=scn24-mn`: the status code had inferred the local hostname from `/proc` but had not persisted it to the shared runner directory.
- Changed `status` so, when a configured runner already has a local Listener PID, it writes host/start-time/username/PID metadata through the existing atomic metadata writer and prints a short confirmation. This does not start or restart the runner.
- Added regression coverage that calls status on `scn24-mn`, then lists the same shared runner from `scn17-mn`, and checks the output identifies `scn24-mn (last)` rather than `unknown`. Added a sorting test where directory order differs from displayed runner-name order.
- For legacy runners, run `status --name <runner> --no-github` once on the node where the Listener actually runs. Once metadata is recorded in the shared directory, other nodes can display that host. Since DNS/API is currently unreliable, remote activity must still be treated as unconfirmed unless GitHub status is available.
- The final guarded deployment installed `tools/runner_control.py` from OEC blob `89b74fedcf4edf4d3ae65ea37278cfcbe4f45da8`; it backed up the previous blob `a83f4e7d8b8c09523bfeb388a5ce70cc638ec637` as `tools/runner_control.py.pre-sync-20261011T103647Z.bak`. Post-write hash verification and Python compilation passed.
- The real connector-node list smoke test passed and showed the five connector hosts in a compact table. The legacy `a3-test` row remains `unknown` until the newly deployed `status` command is run again on `scn24-mn`; the pre-deployment run had detected that hostname but did not persist it.
- Successful final A100 sync and table smoke test: https://github.com/Killer4K-N/Connector_1/actions/runs/38132553565


## Final live-table verification

- Normal GitHub-enabled `list` ran on `scn17-mn` and displayed a sorted, aligned `NAME | HOST | PROCESS | GITHUB` table. GitHub API failures were shortened to labels such as `API 404 (repo/access…)`; the full exception was not leaked into each table row.
- End-to-end checks passed for all five Connector_1 host rows: connector-1 → `scn17-mn`, connector-2 → `scn20-mn`, connector-3 → `scn20-mn`, connector-4 → `scn17-mn`, connector-5 → `scn21-mn`. `--columns name,host,process --no-github` and `--name connector-1,connector-2 --columns name,host --no-github` both passed.
- One live-verification workflow run initially failed because the verification script contained escaped Bash variables, so it searched for the literal `${name}`/`${host}` instead of expanding them. This was a test-script bug, not a controller-output failure. The test was corrected and the rerun passed: https://github.com/Killer4K-N/Connector_1/actions/runs/38132847486
- On the A100 live list, `a3-test` still showed `unknown` because its earlier `status` was executed before the new status-time metadata write was deployed. The corrected code is installed. Rerun `python ~/OEC/tools/runner_control.py status --name a3-test --no-github` once on `scn24-mn`; subsequent nodes should then show `scn24-mn (last)` until a successful GitHub lookup can confirm current activity.
