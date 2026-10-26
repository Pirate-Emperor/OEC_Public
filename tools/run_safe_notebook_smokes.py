#!/usr/bin/env python3
"""Execute known safe, non-model control notebooks top-to-bottom on an OEC compute node.

The target set excludes login-node-only, deployment-mutating, and encrypted-object
notebooks. Upload daemons/cloud uploads/deployment launch are forced off in this
child process. Notebook cells still execute in file order, including read-only
IPython shell diagnostics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback
from typing import Any

from IPython.core.interactiveshell import InteractiveShell

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SAFE_NOTEBOOKS = (
    "Untitled.ipynb",
    "pipeline_demo_acceptance.ipynb",
    "phase1_test_compute_node.ipynb",
)
EXPLICIT_DIAGNOSTIC_NOTEBOOKS = (
    "oec_deply_install.ipynb",
    "pipeline_verify_encrypted_hf.ipynb",
)
NOTEBOOK_ALLOWLIST = SAFE_NOTEBOOKS + EXPLICIT_DIAGNOSTIC_NOTEBOOKS


def run_notebook(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("nbformat") != 4 or not isinstance(document.get("cells"), list):
        raise ValueError(f"{path.name} is not a valid nbformat v4 notebook")
    shell = InteractiveShell()
    namespace = {
        "__name__": "__main__",
        "__file__": str(path),
        "get_ipython": lambda: shell,
    }
    executed: list[int] = []
    for index, cell in enumerate(document["cells"]):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        if not source.strip():
            continue
        print(f"SAFE_NOTEBOOK_CELL_START={path.name}:{index}", flush=True)
        transformed = shell.transform_cell(source)
        exec(compile(transformed, f"{path.name}:cell-{index}", "exec"), namespace, namespace)
        executed.append(index)
        print(f"SAFE_NOTEBOOK_CELL_PASS={path.name}:{index}", flush=True)
    notebook_status = namespace.get("OEC_NOTEBOOK_STATUS", "PASS")
    if notebook_status not in {"PASS", "BLOCKED"}:
        raise RuntimeError(f"unexpected OEC_NOTEBOOK_STATUS={notebook_status!r}")
    return {
        "notebook": path.name,
        "kernel_metadata": (document.get("metadata") or {}).get("kernelspec", {}),
        "code_cells_executed": executed,
        "code_cells_nonempty": len(executed),
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "status": notebook_status,
        "acceptance_note": "Runtime diagnostic did not prove encrypted read-back when status is BLOCKED." if notebook_status == "BLOCKED" else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--notebooks", nargs="+", choices=NOTEBOOK_ALLOWLIST,
        help="Run only the selected safe/diagnostic notebook(s); default is the compute-safe control set.",
    )
    args = parser.parse_args()
    selected_notebooks = tuple(args.notebooks or SAFE_NOTEBOOKS)
    if not (ROOT / "storage_manager.py").is_file():
        raise RuntimeError("Run from the OEC repository checkout.")
    output_root = Path(os.environ.get("OEC_SAFE_NOTEBOOK_SMOKE_DIR", str(Path("/tmp") / "oec-safe-notebook-smoke"))).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    # These notebooks should be diagnostic only. Do not inherit a request to start
    # upload daemons, publish data, or launch deployment services from the runner.
    for key in (
        "OEC_START_HF_UPLOAD_DAEMON",
        "OEC_TEST_ENABLE_CLOUD_UPLOAD",
        "OEC_DEPLOY_LAUNCH_BIOME",
    ):
        os.environ[key] = "0"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

    report: dict[str, Any] = {
        "test": "OEC safe control-notebook top-to-bottom smoke",
        "root": str(ROOT),
        "python": sys.executable,
        "output_root": str(output_root),
        "selected_notebooks": list(selected_notebooks),
        "notebooks": [],
        "excluded_for_context_or_credentials": {
            "phase1_test_login_node.ipynb": "login/control-plane notebook; do not execute on the A100 compute runner. It requires a login-node-labelled runner.",
            "oec_deply_install.ipynb": "not part of the default compute-safe batch; explicitly run with --notebooks under the oec_deploy Conda environment and launch disabled.",
            "pipeline_verify_encrypted_hf.ipynb": "the notebook can report BLOCKED without touching credentials, but real proof requires a real encrypted remote object, private key and local decryptor.",
        },
        "status": "FAIL",
    }
    failed = False
    started = time.time()
    for name in selected_notebooks:
        path = ROOT / name
        if not path.is_file():
            report["notebooks"].append({"notebook": name, "status": "FAIL", "error": "file missing"})
            failed = True
            continue
        try:
            report["notebooks"].append(run_notebook(path))
        except Exception as exc:
            failed = True
            row = {
                "notebook": name,
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            report["notebooks"].append(row)
            print("SAFE_NOTEBOOK_FAILURE " + json.dumps(row, ensure_ascii=False), flush=True)
    report["elapsed_seconds"] = round(time.time() - started, 3)
    blocked = sum(row.get("status") == "BLOCKED" for row in report["notebooks"])
    report["status"] = "FAIL" if failed else ("BLOCKED" if blocked else "PASS")
    target = output_root / "safe-notebook-smoke-report.json"
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("SAFE_NOTEBOOK_SMOKE_SUMMARY " + json.dumps({
        "status": report["status"],
        "passed": sum(x.get("status") == "PASS" for x in report["notebooks"]),
        "blocked": blocked,
        "failed": sum(x.get("status") == "FAIL" for x in report["notebooks"]),
        "report": str(target),
    }, ensure_ascii=False), flush=True)
    return 1 if failed else (2 if blocked else 0)


if __name__ == "__main__":
    raise SystemExit(main())
