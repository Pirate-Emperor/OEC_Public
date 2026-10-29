# OEC Gradio Acceptance — Schedule Coordination and Safety Policy

**Last audited:** 2026-10-29 23:10 IST  
**Repository:** [xflexwork/OEC](https://github.com/xflexwork/OEC)  
**Working branch baseline:** `fix/media-stack-supervision-20261019` at `47cdb0043c26978cf0651015692063631321cf89`  
**Scope:** OEC root repository only. This document does not authorize modifying other repositories, submodules, runners, shared storage or workflows.

## 1. Non-negotiable ownership boundary — include in every task prompt

Every scheduled task and every manual continuation MUST repeat these rules in its prompt, not merely link to this file:

1. **Writable scope:** `xflexwork/OEC` and the permitted local OEC checkout only. Do not write to `xflexwork/OEC_AireOS_Full_Model`, any of its branches or trackers; another chat owns that repository.
2. **Protected submodules:** never edit or modify local `OEC/oec_deploy` or `OEC/oec_train`. They are separate repository submodules. Do not modify their contents, Git state, gitlinks, HEADs, working trees, config or package environments.
3. **Checklist first:** read the latest OEC `docs/checklist.md`, `TODO.md`, `result.md`, `changelog/README.md`, latest dated changelog, and relevant pipeline/workflow files. Then refresh branch head, exact code SHA, recent Actions runs, job states/steps/logs/artifacts and relevant runner/lock state. Old tracker text is not live evidence.
4. **OEC Actions runner:** the OEC model acceptance workflow currently requires labels `[self-hosted, linux, x64, gpu, a100, oec-train]`. Verify actual registration, repository association and host identity separately; a label or runner name alone is not proof of safe ownership. The distinct Full Model runner label/name `oec-train-2` is not an OEC label substitute.
5. **No overlapping GPU/storage work:** before changing workflow-triggered paths or dispatching any GPU task, inspect queued/in-progress workflows and assigned runner status. Verify local EDA/process state when authorized. GitHub showing zero runs does not prove the host is idle. If local runner/EDA state is unavailable, record **UNVERIFIED**, stay read-only or use non-conflicting hosted-CPU tests, and do not dispatch.
6. **Concurrency:** respect the OEC media workflow concurrency group `oec-media-gpu-storage-serial`. The current OEC acceptance workflow uses `cancel-in-progress: false`; do not create overlapping duplicate jobs.
7. **Environment/storage safety:** preserve Conda environments/packages, model weights/caches, storage locks, protected reserves and trusted StorageManager configuration. No installs/recreation, cache deletion/purge, synthetic/default configuration, runner relabel/re-registration, admission bypass, secret disclosure, or lock recovery without approved host/PID/lease proof.
8. **Legacy pause/remote locks:** the OEC checklist records a legacy `.storage_pause.lock` under `/nlsasfs/home/lmedge/rahkus/aireos_models`; lock-owner identity is unverified and authorized recovery is host-restricted to `oec-1` / `scn30-mn`. Do not remove it or bypass it. Preserve remote-or-unknown ACE-Step/Kokoro/Qwen3-ASR/Whisper locks reported on `scn30-mn`.
9. **Evidence discipline:** static tests and UI launch are not generation acceptance. For each model, require a real callback invocation on the verified intended source plus a non-empty output, exact run association, output path/artifact URL, SHA-256, and format-specific independent validation. WAV/FLAC decode; transcript text review; PNG decode; GLB parse and reopen; MP4 ffprobe plus decode. Keep absent/untested outputs **NOT_RUN**, failed outputs **FAIL**, missing prerequisites **BLOCKED**, and queued/unexecuted work **PENDING**.
10. **Safe tracker changes:** modify OEC-root trackers only. Re-read the target file immediately before an edit, preserve unrelated content, use atomic commits, stamp local time in `Asia/Kolkata`, and update branch refs with an expected-head/lease check rejecting concurrent changes. Do not push to the workflow-triggering branch until push consequences and runner admission are understood.
11. **Stop and hand off precisely:** preserve logs and partial evidence; state what ran, what passed/failed, exact blockers, artifact identifiers/hashes, runner labels and one next safe action. Never claim a clean shutdown or PASS without corresponding evidence.

## 2. OEC-only baseline reconciled on 2026-10-29

- OEC candidate branch was verified at `47cdb0043c26978cf0651015692063631321cf89` at audit time. The executable pin noted by the OEC tracker is `662f8225f110163cbd8e2f60c9548c4839ce8566`; current branch commits after it must be classified from an actual diff, not assumed to be code or documentation-only.
- OEC's own callback workflow is `.github/workflows/oec-demo-notebook-acceptance.yml`, with runner labels `[self-hosted, linux, x64, gpu, a100, oec-train]`, and is scoped to branch `fix/media-stack-supervision-20261019`.
- Latest OEC Actions query at audit time: zero in-progress, queued and waiting runs. This does **not** verify local EDA/host activity. Latest known root-sync run [40818428276](https://github.com/xflexwork/OEC/actions/runs/40818428276) failed runner identity validation; canonical sync was skipped. The latest OEC callback acceptance [40802365390](https://github.com/xflexwork/OEC/actions/runs/40802365390) was cancelled and had zero artifacts.
- OEC's prior tracker records historical AudioGen, MusicGen, TRELLIS and FLUX-generated outputs on older executable revisions. Preserve that evidence; do not duplicate those outputs unless relevant executable code changed. LTX text-to-video/image-to-video and current WAN generation remain outstanding; WAN source was updated for XPU compatibility.
- The known unresolved host/storage gate prevents fresh model acquisition: do not run new weight downloads/inference on an unauthorized host or recover locks by assumption.

## 3. Schedule creation limit and safe synchronization

The ChatGPT task scheduler supports one-time, daily, weekly and monthly schedules. **Hourly recurring schedules are not supported.** Recurring schedules are flexible, not exact-time guarantees.

At audit time the scheduler reported **3 enabled tasks out of a plan limit of 3**. Those existing slots belong to two Full Model/D2E daily tasks and one Full Model checkpoint task, outside this OEC task's ownership. An attempt to create the first new OEC checkpoint at 23:12 IST returned `too_many_active_automations` (`current_count=3`, `plan_limit=3`). No event was created, and no existing automation was disabled, repurposed or changed. Do not retry repeatedly or manipulate another chat's tasks to bypass this limit.

After an authorized slot becomes available, use one OEC daily coordinator plus a bounded one-time checkpoint chain only if the scheduler permits it. Suggested next checkpoint batch, because 23:09 has already passed: **23:12, 23:25, 23:40, 23:52 IST, then 00:05 IST on 2026-10-30 for the scheduler checkpoint**. Before scheduling any exact time, read the current time and omit past times. Each event must independently contain the standing rules in §1.

### Five-stage checkpoint responsibilities

1. **Reconcile current state:** inspect OEC head, docs/checklist, TODO/results/changelog, exact code SHA, latest relevant Actions runs/jobs/logs/artifacts, runner/queue and blockers. Resume earliest missing safe prerequisite.
2. **Verify access and admission:** verify approved source access and OEC runner label/registration/host. Inspect StorageManager state only through trusted supported paths; preserve the lock/reserve rules. No inference from another repo.
3. **Run safe contracts:** perform only non-conflicting static/CPU validation that cannot trigger a GPU workflow. Check whether edits to any watched path would launch acceptance/root-sync. Do not touch protected submodules or install packages.
4. **Actual callback and asset validation:** only proceed if the source pin, authorized runner/host, idle/EDA state and storage admission are positively verified. Run only missing/changed model paths; preserve historical successful outputs. Record output link/path, SHA-256 and appropriate decoder/parser evidence.
5. **Evidence-led handoff and next-batch planning:** refresh current Actions and checklist state; write precise statuses and blockers to OEC's tracker; only then plan subsequent events from completed evidence, using the same slot if and only if the automation tooling confirms a permitted update. Never assert a future task exists without tool confirmation.

## 4. Daily coordinator precedence and synchronization

When a daily OEC coordinator runs, it has priority over any overlapping one-time checkpoint: the checkpoint must not duplicate the same read/audit, mutate files under review, or launch conflicting GPU/storage work. The daily coordinator should record the active checkpoint, its last confirmed result and next scheduled stage; let non-conflicting read-only work continue only. Resume the one-time chain after the daily coordinator records a fresh handoff.

The daily coordinator should re-read the full repo-wide checklist and progress, not only the Gradio notebook. It should cover model servers, generation callbacks, deployment readiness, asset validators, StorageManager/locks, runner sync, environment preservation, Actions workflows, tests, results, changelog, missing artifacts and next gates. It may propose/create future tasks only if automation slots are genuinely available; it must not disable or rewrite unrelated tasks.

There is no supported hourly recurrence to prioritize against. Use explicitly scheduled one-time checkpoints for this short batch, while the daily coordinator owns repo-wide reconciliation and any decision to create the next batch.

## 5. Completion criteria

The goal is not “UI opens” or “workflow green” by itself. Close each model row only when the OEC tracker ties all of the following to the exact candidate source and Actions run: actual Gradio event/callback ran; service health was valid; real non-empty asset saved; output path/artifact and SHA-256 recorded; format/content validator passed; service stop and cleanup are evidenced without removing shared caches/locks; final storage/runner observations are permitted and safe. If a prerequisite cannot be established, retain **BLOCKED/NOT_RUN** and state the authorized maintainer intervention.


## Runner identity evidence refinement — 2026-10-29 23:11 IST

The job log for OEC root-sync run [40818428276](https://github.com/xflexwork/OEC/actions/runs/40818428276), job `123264981530`, shows the local runner config name `oec-train` but its recorded repository association is `Killer4K-N/OEC_AireOS_Full_Model`, not `xflexwork/OEC`. The audit stopped at `IDENTITY_MISMATCH` before adding a label or syncing the checkout. The second expected runner `oec-train-2` was not verified because the job exited at the first mismatch. No runner label or registration change is authorized here.

The current OEC branch `47cdb0043c26978cf0651015692063631321cf89` compares to the executable pin `662f8225f110163cbd8e2f60c9548c4839ce8566` with three commits ahead and no commits behind; the compare endpoint reports changes only to `TODO.md`, `docs/checklist.md`, `result.md`, `test.json` and changelog trackers. Thus the pin remains the known code-bearing candidate, but there is still no successful current-head runner checkout/callback acceptance. Next owner intervention is a correctly authorized `xflexwork/OEC` runner registration on the intended host or a separately approved runner; do not relabel/re-register the current runner as a shortcut.
