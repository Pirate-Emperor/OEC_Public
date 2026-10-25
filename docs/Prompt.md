# OEC Engineering Continuation — Permanent Rules and Navigation

**Purpose:** This is the first entry point for every new OEC continuation chat or engineering session. It contains durable instructions and repository navigation, not today's status. The live state belongs in [`checklist.md`](checklist.md), ongoing work belongs in [`TODO.md`](../TODO.md), and dated events belong in [the daily changelog](../changelog/README.md). For the active model-setup and inference workstream, use the task-specific [model-pipeline continuation prompt](MODEL_PIPELINE_CONTINUATION_PROMPT.md).

## 1. Required reading order

At the start of every session, use this order. Refresh live state; never assume the previous chat or checklist is current.

1. **Read this file first:** `docs/Prompt.md`.
2. **Refresh the live checklist:** [`docs/checklist.md`](checklist.md). Treat it as a checkpoint, not live telemetry.
3. Read [`TODO.md`](../TODO.md), [`result.md`](../result.md), [`test.json`](../test.json), [`changelog/README.md`](../changelog/README.md), the most recent `changelog/CHANGELOG-YYYY-MM-DD.md`, and applicable `docs/` conventions.
4. Read the latest GitHub branch heads, commits, open PRs, and workflow YAML for the repository in scope. Review recent and active workflow runs, then the job list, runner identity, relevant step logs and actual artifacts. Check whether the tested source SHA equals the current branch head. Preserve failed and superseded attempts as history.
5. Read the workstream's own research plan, data/model contracts, tests, and current result records before changing code or claims.
6. For cross-repository claims, read the current OEC-Viewer graphs and source links. For academic deliverables, read the authoritative rules and latest source-scan checkpoint in [`Report_Docs/research/CONTINUATION_RULES_AND_DELIVERABLE_CHECKLIST.md`](https://github.com/xflexwork/Report_Docs/blob/main/research/CONTINUATION_RULES_AND_DELIVERABLE_CHECKLIST.md) and [`SOURCE_SCAN_CHECKPOINTS_2026-10-19.md`](https://github.com/xflexwork/Report_Docs/blob/main/research/SOURCE_SCAN_CHECKPOINTS_2026-10-19.md); refresh the actual main head before relying on either snapshot.

If a source or tool cannot be accessed, record exactly what was unavailable and continue with independent work. Do not claim inspection, tests, GPU use, runner access, paper build or inference unless there is retrieved evidence.

## 2. Repository routing and separation

| Repository | Scope | Required execution environment |
|---|---|---|
| [OEC](https://github.com/xflexwork/OEC) | Core pipeline, workers, service manager, runtime and storage contracts | Only the runners actually configured in the current workflow; historically `oec-1`, `oec-2`, `oec-3` |
| [OEC_AireOS_Full_Model](https://github.com/xflexwork/OEC_AireOS_Full_Model) | From-scratch model training and full-model research | `oec-train` only, environment `oec_train` |
| [OEC_AireOS_Freezed](https://github.com/xflexwork/OEC_AireOS_Freezed) | Frozen backbones, LoRA/adapters/PEFT | `oec-freeze` only, environment `oec_freeze`, Python 3.11 |
| [OEC_AireOS_MOE](https://github.com/xflexwork/OEC_AireOS_MOE) | Expert composition, routing and MoE experiments | `oec-moe` only |
| [OEC_Deploy](https://github.com/xflexwork/OEC_Deploy) | Packaged application, GUI and deployment | `oec-deploy` and the environment/workflow currently configured |
| [OEC-Viewer](https://github.com/xflexwork/OEC-Viewer) | Canonical architecture/pipeline/hardware/model-learning diagrams | Reference and validate its source graph files, schema and changelog |
| [Report_Docs](https://github.com/xflexwork/Report_Docs) | Authoritative dissertation/report, presentation and academic poster source | Use its template, versioning and build rules |
| [Report_Logpoints](https://github.com/xflexwork/Report_Logpoints) | Research logpoint archive/viewer | Use its source-checkpoint and record-count conventions |

Recheck each workflow's `runs-on`, branch/ref, checkout SHA, runner hostname, working directory, Python/Conda environment and actual GPU allocation on every consequential run. Do not redirect a workstream to another runner just because the assigned runner is unavailable. Do not assume that visible GPUs mean distributed training ran.

## 3. Evidence and research-claim rules

- Keep these states distinct: **implemented**, **unit-tested**, **integration-tested**, **live-inference-tested**, **trained**, **evaluated**, **research-validated**, **planned**, and **blocked**.
- For every Action, distinguish run conclusion from job/step conclusion and from scientific/semantic readiness. A queued job is not running. An active job is not passed. A green workflow does not prove inference, training quality, packaging, or a research hypothesis.
- Record source commit, branch, run/job IDs, runner/environment, data/model/config manifest and hashes, seed/split, commands, test counts, measured outputs, checkpoint/artifact hashes, limitations and failures for each material experiment.
- Actual GPU identity and per-arm/device evidence must support GPU claims. Separate configuration-parallel runs across cards from DDP/multi-process training.
- A dataset directory is not proof of usable data. Verify provenance, terms, schema, masks, coordinates, temporal alignment, sequence splits, duplicates and source hashes. Synthetic data validates infrastructure only.
- Use matched baselines, holdout definitions, adequate replication and uncertainty where feasible. Never infer independent-scene generalization from clips in a shared trajectory or novelty from model composition alone.
- The Full_Model, Freezed and MOE streams are distinct. Do not treat a reconstruction VAE as a validated action-conditioned world model; frozen inference is not adapter training; RRF/retrieval is not a trained sparse neural MoE.
- Validate end-user flows and artifacts independently. A GLB's existence/vertex count is not proof of accurate or watertight geometry. A UI startup, source test or build is not an end-to-end acceptance test.

## 4. Resource, storage, security and Actions billing

- **GitHub Actions quota policy (user update, 2026-10-19):** The user confirmed the runner quota was reset and withdrew the earlier special requirement to prove a workflow costs $0 before pushing, rerunning or dispatching. Do not re-impose that veto or artificially cap Actions usage. Use the assigned A100 runners for the necessary model setup, inference and acceptance tests; batch related work sensibly and avoid competing pending runs in the shared `oec-media-gpu-storage-serial` group. This change applies to Actions runner quota only; it does not disable StorageManager admission, model-storage limits, network checks, licenses, path safety, concurrency or evidence requirements.
- Prefer read-only GitHub inspection and local/offline validation when authorized. Batch related safe documentation updates. After any allowed documentation-only push, re-read the branch and check recent Action runs to confirm whether anything triggered.
- Never directly read, hash, resize, create, overwrite, move or delete `.storage_reserve.bin` or other protected reserve/lock files. Use only the sanctioned OEC StorageManager interface for storage/reserve state and operations.
- Before any shared write, model/dataset download, package install or substantial compute, require fresh authoritative quota, StorageManager admission, path ownership, output capacity, no conflicting lease/lock and resource occupancy checks. Missing or stale telemetry means fail closed. Filesystem free space is not quota evidence.
- Preserve datasets, checkpoints, caches, shared environments, running jobs and unrelated dirty changes. No broad destructive Git commands, unreviewed checkouts, force pushes, checkpoint replacement, bulk cache purge or killing processes. Modify only the correct branch; respect repository-specific approval gates and do not merge to `main` without authorization.
- Never expose credentials, tokens, private keys, signed URLs or secrets in logs or documentation.

## 5. Tracking and writing conventions

Use the existing tracker in each repository; do not create parallel trackers.

- **`docs/Prompt.md`:** permanent session rules, routing and first-read directions only. Do not put today's status or changing run IDs here.
- **`docs/checklist.md`:** current timestamped snapshot, unresolved blockers, active/pending job identities, ordered actions, acceptance criteria and the next single priority. Refresh it when status changes.
- **`TODO.md`:** one consolidated engineering backlog; update status and link checklist/changelog instead of copying the whole checklist.
- **`changelog/CHANGELOG-YYYY-MM-DD.md`:** one daily chronological history in Asia/Kolkata time. Append on the same local date; create a new file on a new date.
- **`test.json`:** structured ledger of material tests/experiments, including failed/blocked attempts; use the established schema.
- **`result.md`:** cumulative significant results, not a duplicate row-by-row history.
- Update `changelog/README.md` only when its index needs the new day. Check its current format first.

Record each real event once. Use a detailed experiment/test-ledger record for a consequential test, experiment, or implementation fix. Use a concise summary for routine progress and significant milestones. Do **not** create duplicate summary and experiment rows describing the same event. Never rewrite a historical failure to look successful; append a correction with date and evidence.

Write in plain engineering language. State exact facts, assumptions, limitations and the evidence used. Avoid promotional language, fabricated timestamps, duplicate trackers and generic AI-style filler.

## 6. Research and deliverables

- Read the current Viewer source graph and linked repository implementation before selecting or changing a research claim. Validate graph IDs, edges, schema/status, formulas, source links and contradictions. Architecture is not implementation.
- Keep the product demonstrator bounded to one complete, reproducible use case supported by actual code, permitted cached models and current compute. Record input/output hashes, metadata, failures, validation, latency/resource costs, and what the end user can observe.
- For dissertation, presentation and poster, follow the existing IIT Madras template and content/version policies. Use the latest approved code/run evidence and citations. Maintain consistent terminology and model versions, inspect the rendered output page-by-page, and explicitly label preliminary, proposed, blocked, negative or verified results.
- Academic order currently prescribed by Report_Docs is **poster repair and visual acceptance → presentation source/version reconciliation and rebuild/review → dissertation/report update after claims and diagrams stabilize**. Use its guide rather than inventing a competing academic tracker. PaperDock and GitHub source copies remain distinct until content/hashes are compared.
- Separate proof-of-concept from user acceptance and production readiness. Document licensing, deployment, latency, memory/storage, compute cost, failure behavior and the next commercial validation step without unsupported market claims.

## 7. Required end-of-session handoff

Update the checklist and daily changelog after meaningful work. Report:
1. current verified branch/head and what was actually inspected or edited;
2. current Action run/job statuses with links and exact conclusions;
3. changes and test results, including failed/blocked tests;
4. real outputs/metrics and limitations;
5. resource, license, cost or runner blockers;
6. what is still unverified;
7. the single most important next step.

Do not stop at a plan when safe work is possible. Do not start a shared-state operation while its approval, StorageManager admission, runner, network or license gates are unresolved. The prior $0-only Actions veto is retired; use Actions when it materially advances model setup and inference.
