# Mandatory GitHub Actions Runner Policy

**Hard requirement: this repository must use local/self-hosted GitHub Actions runners only.**

- Every GitHub Actions job in every workflow must target a **self-hosted** runner. Each `runs-on` value must include the `self-hosted` label.
- Add the required local OS, architecture, and resource labels (for example `linux`, `x64`, `oec-1`, `oec-train`, `oec-train-2`, or connector-specific labels). Preserve existing dedicated runner labels.
- This applies to CI, tests, linting, code generation, documentation builds, packaging, releases, scheduled workflows, manual dispatches, reusable workflows, matrices, and every job in multi-job workflows.
- **Prohibited:** GitHub-hosted labels such as `ubuntu-latest`, `ubuntu-*`, `windows-latest`, `windows-*`, `macos-latest`, or equivalent hosted images. Do not add a matrix or reusable workflow that resolves to a GitHub-hosted runner.
- **No hosted fallback:** if no compatible local runner is online, leave the job queued or let it fail clearly and notify the repository owner. Never switch to a GitHub-hosted runner to make a check pass.
- Before manually dispatching or rerunning a workflow, verify that the selected runner is self-hosted and available. Do not spend GitHub-hosted Actions minutes.
- **Only exact-name exceptions:** `Report_PPT` and `Report_Logpoints` may use GitHub-hosted runners. This repository is not exempt unless its repository name is one of those exact names.

Review this policy before adding or changing workflows. A violating workflow must be corrected before it is dispatched or merged.
