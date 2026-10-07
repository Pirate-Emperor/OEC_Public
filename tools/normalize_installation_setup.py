#!/usr/bin/env python3
"""Normalize A100 Installation_Setup notebooks to use the central runner controller.

This script contains no runner secrets. It only writes repository/name/label metadata
and calls ~/OEC/tools/runner_control.py at notebook execution time.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


DEFAULT_CONFIGS = {
    "project": {
        "repo_url": "https://github.com/SpryzenHell/gpu-nvidia",
        "name": "gpu-project",
        "labels": "gpu,a100",
    },
    "a3": {
        "repo_url": "https://github.com/Killer4K-N/Connector_1",
        "name": "connector-1",
        "labels": "gpu,a100",
    },
    "a4": {
        "repo_url": "https://github.com/SpryzenHell/a4",
        "name": "integrator",
        "labels": "gpu,a100",
    },
    "connector_3": {
        "repo_url": "https://github.com/Killer4K-N/Connector_1",
        "name": "connector-3",
        "labels": "gpu,a100",
    },
    "connector_2": {
        "repo_url": "https://github.com/Killer4K-N/Connector_1",
        "name": "connector-2",
        "labels": "gpu,a100",
    },
    "connector_1": {
        "repo_url": "https://github.com/Killer4K-N/Connector_1",
        "name": "connector-1",
        "labels": "gpu,a100",
    },
}

RUNNER_MARKERS = (
    "actions-runner-linux-x64",
    "ACTION_TOKEN",
    "config.sh",
    "run.sh",
    "actions-runner",
    "runner_control.py",
    "REMOVE_RUNNER",
)


def notebook_paths(root: Path) -> list[tuple[str, Path]]:
    return [
        (name, root / name / "Installation_Setup.ipynb")
        for name in DEFAULT_CONFIGS
    ]


def make_markdown_cell(folder: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "## Phase: GitHub Actions Runner Management\n",
            "\n",
            "Runner installation and execution are controlled centrally by ~/OEC/tools/runner_control.py.\n",
            "\n",
            "The runner is always stored under ~/OEC/gpu/<runner-folder>/actions-runner. "
            "No registration token is stored in this notebook.\n",
            "\n",
            "Set ACTION_TOKEN in the shell only when a new runner must be registered. "
            "An already-configured runner can be started without a token.",
        ],
    }


def make_setup_cell(folder: str, cfg: dict) -> dict:
    repo_url = cfg["repo_url"]
    name = cfg["name"]
    labels = cfg["labels"]
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "import os\n",
            "import subprocess\n",
            "import sys\n",
            "from pathlib import Path\n",
            "\n",
            "CONTROL = Path.home() / 'OEC/tools/runner_control.py'\n",
            f"RUNNER_DIR = Path.home() / 'OEC/gpu/{folder}/actions-runner'\n",
            f"RUNNER_REPO_URL = os.environ.get('RUNNER_REPO_URL', {repo_url!r})\n",
            f"RUNNER_NAME = os.environ.get('RUNNER_NAME', {name!r})\n",
            f"RUNNER_LABELS = os.environ.get('RUNNER_LABELS', {labels!r})\n",
            "RUNNER_TOKEN_ENV = os.environ.get('RUNNER_TOKEN_ENV', 'ACTION_TOKEN')\n",
            "\n",
            "if not CONTROL.is_file():\n",
            "    raise FileNotFoundError(f'Central runner controller not found: {CONTROL}')\n",
            "\n",
            "subprocess.run([\n",
            "    sys.executable, str(CONTROL), 'setup',\n",
            "    '--repo-url', RUNNER_REPO_URL,\n",
            "    '--name', RUNNER_NAME,\n",
            "    '--labels', RUNNER_LABELS,\n",
            "    '--runner-dir', str(RUNNER_DIR),\n",
            "    '--token-env', RUNNER_TOKEN_ENV,\n",
            "], check=True)\n",
        ],
    }


def make_start_cell(folder: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "import subprocess\n",
            "import sys\n",
            "from pathlib import Path\n",
            "\n",
            "CONTROL = Path.home() / 'OEC/tools/runner_control.py'\n",
            f"RUNNER_DIR = Path.home() / 'OEC/gpu/{folder}/actions-runner'\n",
            "\n",
            "subprocess.run([sys.executable, str(CONTROL), 'status', '--runner-dir', str(RUNNER_DIR)], check=True)\n",
            "subprocess.run([sys.executable, str(CONTROL), 'start', '--runner-dir', str(RUNNER_DIR)], check=True)\n",
        ],
    }


def normalize(path: Path, folder: str, cfg: dict, dry_run: bool) -> bool:
    if not path.is_file():
        print(f"[SKIP] Missing: {path}")
        return False

    original_text = path.read_text()
    nb = json.loads(original_text)
    cells = nb.get("cells", [])
    hit_indices = []

    for i, cell in enumerate(cells):
        src = "".join(cell.get("source", []))
        if any(marker in src for marker in RUNNER_MARKERS):
            hit_indices.append(i)

    if hit_indices:
        start = min(hit_indices)
        end = max(hit_indices)
        replacement = [
            make_markdown_cell(folder),
            make_setup_cell(folder, cfg),
            make_start_cell(folder),
        ]
        new_cells = cells[:start] + replacement + cells[end + 1 :]
    else:
        new_cells = cells + [
            make_markdown_cell(folder),
            make_setup_cell(folder, cfg),
            make_start_cell(folder),
        ]

    nb["cells"] = new_cells
    changed = json.dumps(nb, indent=1) + "\n" != original_text

    if changed and not dry_run:
        path.write_text(json.dumps(nb, indent=1) + "\n")
        for checkpoint in path.parent.glob(".ipynb_checkpoints/*Installation_Setup*.ipynb"):
            try:
                checkpoint.unlink()
                print(f"[REMOVE] Old checkpoint: {checkpoint}")
            except OSError as exc:
                print(f"[WARN] Could not remove checkpoint {checkpoint}: {exc}")

    state = "WOULD UPDATE" if dry_run and changed else "UPDATE" if changed else "OK"
    print(f"[{state}] {path}")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize all A100 Installation_Setup notebooks to use the central runner controller."
    )
    parser.add_argument(
        "--root",
        default=os.path.expanduser("~/OEC/gpu"),
        help="A100 gpu root containing project/, a3/, a4/, connector_1/, connector_2/, connector_3/ (default: ~/OEC/gpu).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without writing notebooks or deleting checkpoints.",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    print(f"[INFO] GPU root: {root}")

    changed = 0
    for folder, path in notebook_paths(root):
        if normalize(path, folder, DEFAULT_CONFIGS[folder], args.dry_run):
            changed += 1

    print(f"[DONE] {'Would update' if args.dry_run else 'Updated'} {changed} notebook(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
