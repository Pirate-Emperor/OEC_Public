# A100 ↔ GitHub synchronization runbook

**Repository:** `CalamityStriker/OEC`  
**Active implementation branch:** `fix/media-stack-supervision-20261019`  
**Rule:** treat a successful `git fetch` as updating remote-tracking refs only. It does not update the checked-out files.

## Before starting work or pulling remote changes

Run on the A100 login node:

```bash
cd "$HOME/OEC"
git status --short --branch
git branch --show-current
git rev-parse HEAD
git fetch origin --prune
```

If the worktree is dirty, **stop before switching branches or pulling**. Review `git diff` and `git diff --cached`; preserve every local change. Do not use `git reset --hard`, `git clean`, or an unreviewed checkout to force synchronization.

Once the worktree is clean, use the implementation branch for code work:

```bash
git switch fix/media-stack-supervision-20261019
git pull --ff-only origin fix/media-stack-supervision-20261019
git rev-parse HEAD
git rev-parse origin/fix/media-stack-supervision-20261019
git status --short --branch
```

The two `rev-parse` outputs should match after the fast-forward. Keep `main` tracking/reporting-only unless a task explicitly authorizes otherwise.

## After a local change

Run focused tests and `git diff --check` first. Review and stage only files intentionally changed; never stage secrets, model weights, caches, temporary outputs, or unrelated files.

```bash
git diff --check
git diff --stat
git status --short
# Stage explicit paths after review:
git add path/to/changed_file.py path/to/test_file.py
git diff --cached --check
git diff --cached
git commit -m "type(scope): concise reason"
git push origin HEAD:fix/media-stack-supervision-20261019
git fetch origin
git rev-parse HEAD
git rev-parse origin/fix/media-stack-supervision-20261019
git status --short --branch
```

Only push this branch when it is the intended implementation branch and the staged diff/tests are reviewed. If local and remote both have unique commits, stop and reconcile with a reviewed merge/rebase plan; do not force-push.

## After a remote/assistant commit

Before running or editing code on A100, inspect the status and fetch. If the tree is clean and the implementation branch is checked out, run the fast-forward pull from the first section. Verify `HEAD` equals the corresponding `origin/` ref before claiming that local execution tested the current GitHub code.

## Evidence and boundaries

- Record the source commit SHA for every test or inference run. A successful run on an older SHA does not validate the latest source.
- After a workflow-triggering push, inspect the exact run, terminal conclusion, steps/logs and output artifacts. Do not equate a queued run or a green static suite with live GPU acceptance.
- Never put a PAT in a remote URL, shell command, commit, or log. Use Git's credential helper for interactive HTTPS authentication.
- This runbook synchronizes repository source and tracking files—not model caches, checkpoints, private environment files or protected storage reserve/lock files. Those use their own audited workflows.
