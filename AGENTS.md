# Mandatory GitHub Actions Runner Policy

**Hard requirement: this repository must use local/self-hosted GitHub Actions runners only.**

## Required behavior

- Every GitHub Actions job in every workflow must target a **self-hosted** runner. Each `runs-on` value must include the `self-hosted` label.
- Add the needed local OS, architecture, and resource labels (for example `linux`, `x64`, `oec-1`, `oec-train`, `oec-train-2`, or a connector-specific label). Preserve existing dedicated runner labels when editing a workflow.
- This applies to CI, tests, linting, code generation, documentation builds, packaging, releases, scheduled workflows, manual dispatches, reusable workflows, matrices, and every job in a multi-job workflow.
- **Do not use GitHub-hosted runner labels**, including `ubuntu-latest`, `ubuntu-*`, `windows-latest`, `windows-*`, `macos-latest`, or any equivalent hosted image. Do not introduce a matrix or reusable workflow that resolves to a GitHub-hosted runner.
- **No hosted fallback is allowed.** If no compatible local runner is online, leave the job queued or let it fail with a clear explanation and notify the repository owner. Never switch to GitHub-hosted runners to make a check pass.
- Before manually dispatching or rerunning a workflow, verify that its selected runner is self-hosted and that the intended local runner is available. Do not spend GitHub-hosted Actions minutes.

## Only permitted repository exceptions

Only repositories named exactly **`Report_PPT`** and **`Report_Logpoints`** are exempt and may use GitHub-hosted runners. This repository is not exempt unless its repository name is one of those exact names.

When adding or changing workflows, review this policy first. A workflow that violates it must be corrected before it is dispatched or merged.
