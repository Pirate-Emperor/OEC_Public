# Runner Control

tools/runner_control.py is the single control point for GitHub Actions self-hosted runners on the HPC host.

## Directory rule

Every runner must live below ~/OEC/gpu/.
The controller rejects runner directories outside that tree.
Default layout: ~/OEC/gpu/<runner-name>/actions-runner
The controller can be launched from any working directory.

## Setup

Recommended token handling:

export ACTION_TOKEN='YOUR_CURRENT_GITHUB_RUNNER_REGISTRATION_TOKEN'
python ~/OEC/tools/runner_control.py setup \
  --repo-url https://github.com/Killer4K-N/Connector_1 \
  --name connector-2 \
  --labels gpu,a100,connector-2

Custom repo and directory:

python ~/OEC/tools/runner_control.py setup \
  --repo-url https://github.com/OTHER_OWNER/OTHER_REPO \
  --name my-runner \
  --labels gpu,a100,my-runner \
  --runner-dir ~/OEC/gpu/my-runner/actions-runner \
  --token-env ACTION_TOKEN

The registration token must be generated for the target repository or organization. Do not commit it to a notebook or source file.

## Start / stop / status

python ~/OEC/tools/runner_control.py start --name connector-2
python ~/OEC/tools/runner_control.py stop --name connector-2
python ~/OEC/tools/runner_control.py status --name connector-2
python ~/OEC/tools/runner_control.py list

Runner paths can also be supplied directly from any directory:

python ~/OEC/tools/runner_control.py start \
  --runner-dir ~/OEC/gpu/connector-2/actions-runner

## Remove

export ACTION_TOKEN='YOUR_CURRENT_RUNNER_REMOVE_TOKEN'
python ~/OEC/tools/runner_control.py remove --name connector-2

Stopping leaves the runner registered but offline. Removing unregisters it from GitHub.

## Proxy

The controller imports ~/OEC/core_config.py before setup/start when available, then writes the active Linux proxy variables into the runner-local .env. This keeps Jupyter and nbconvert launches consistent.

## Notebook use

A notebook can live anywhere and call the same central tool:

import os, subprocess, sys
subprocess.run([
    sys.executable,
    os.path.expanduser('~/OEC/tools/runner_control.py'),
    'start', '--name', 'connector-2',
], check=True)

For nbconvert, do not use a foreground !./run.sh cell. The controller starts the runner detached and returns immediately.

## Version

The default pinned runner version is 2.337.0. Override it with --version during setup.

## Detailed help

The controller has separate help for every command:

    python ~/OEC/tools/runner_control.py --help
    python ~/OEC/tools/runner_control.py setup --help
    python ~/OEC/tools/runner_control.py start --help
    python ~/OEC/tools/runner_control.py stop --help
    python ~/OEC/tools/runner_control.py status --help
    python ~/OEC/tools/runner_control.py remove --help
    python ~/OEC/tools/runner_control.py download --help
    python ~/OEC/tools/runner_control.py list --help

## A100 Installation_Setup normalization

The A100 host has these Installation_Setup notebooks:

- ~/OEC/gpu/project/Installation_Setup.ipynb
- ~/OEC/gpu/a3/Installation_Setup.ipynb
- ~/OEC/gpu/a4/Installation_Setup.ipynb
- ~/OEC/gpu/connector_1/Installation_Setup.ipynb
- ~/OEC/gpu/connector_2/Installation_Setup.ipynb
- ~/OEC/gpu/connector_3/Installation_Setup.ipynb

Use the central normalizer rather than editing runner cells individually:

    python ~/OEC/tools/normalize_installation_setup.py --dry-run
    python ~/OEC/tools/normalize_installation_setup.py

The normalizer removes old runner download/configuration/start cells, removes matching
Installation_Setup Jupyter checkpoints, and replaces them with cells that call the
central runner controller. It does not contain or write registration tokens.

The notebook metadata defaults preserve the currently observed repository and runner
names. They can be overridden at runtime with RUNNER_REPO_URL, RUNNER_NAME,
RUNNER_LABELS, and RUNNER_TOKEN_ENV.

## Runner location rule

The controller rejects any runner directory outside OEC_ROOT/gpu. This prevents a
notebook launched from another working directory from accidentally installing a
runner into the notebook's current directory.
