#!/usr/bin/env python3
"""Read-only structural and syntax audit for every top-level OEC Jupyter notebook."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from IPython.core.interactiveshell import InteractiveShell

ROOT = Path(__file__).resolve().parents[1]


def audit_notebook(path: Path, shell: InteractiveShell) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": str(path.relative_to(ROOT)),
        "status": "PASS",
        "cells": 0,
        "code_cells": 0,
        "syntax_checked_cells": 0,
        "saved_error_outputs": [],
        "errors": [],
        "kernel": None,
    }
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("nbformat") != 4 or not isinstance(doc.get("cells"), list):
            raise ValueError("expected valid nbformat 4 notebook with a cell list")
        metadata = doc.get("metadata") or {}
        kernel = metadata.get("kernelspec") or {}
        record["kernel"] = kernel.get("name") or kernel.get("display_name")
        record["cells"] = len(doc["cells"])
        ids: set[str] = set()
        for index, cell in enumerate(doc["cells"]):
            if not isinstance(cell, dict) or cell.get("cell_type") not in {"code", "markdown", "raw"}:
                record["errors"].append({"cell": index, "kind": "schema", "message": "invalid cell type"})
                continue
            source = cell.get("source", [])
            if isinstance(source, list):
                if any(not isinstance(line, str) for line in source):
                    record["errors"].append({"cell": index, "kind": "schema", "message": "source list contains non-text"})
                    continue
                source_text = "".join(source)
            elif isinstance(source, str):
                source_text = source
            else:
                record["errors"].append({"cell": index, "kind": "schema", "message": "source must be string or string list"})
                continue
            cell_id = cell.get("id")
            if cell_id is not None:
                if not isinstance(cell_id, str) or not cell_id:
                    record["errors"].append({"cell": index, "kind": "schema", "message": "cell id is empty or not text"})
                elif cell_id in ids:
                    record["errors"].append({"cell": index, "kind": "schema", "message": f"duplicate cell id {cell_id!r}"})
                ids.add(cell_id)
            if cell["cell_type"] != "code":
                continue
            record["code_cells"] += 1
            for output in cell.get("outputs") or []:
                if output.get("output_type") == "error":
                    record["saved_error_outputs"].append({
                        "cell": index,
                        "ename": output.get("ename"),
                        "evalue": str(output.get("evalue", ""))[:300],
                    })
            if not source_text.strip():
                continue
            try:
                transformed = shell.transform_cell(source_text)
                compile(transformed, f"{path.name}:cell-{index}", "exec")
                record["syntax_checked_cells"] += 1
            except Exception as exc:
                record["errors"].append({
                    "cell": index, "kind": "syntax",
                    "message": f"{type(exc).__name__}: {exc}"[:1000],
                })
        if record["errors"]:
            record["status"] = "FAIL"
        return record
    except Exception as exc:
        record["status"] = "FAIL"
        record["errors"].append({"kind": "notebook", "message": f"{type(exc).__name__}: {exc}"[:1000]})
        return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-json", type=Path, help="Write a machine-readable report to this path.")
    parser.add_argument("--strict-clean", action="store_true",
                        help="Fail if notebook code cells contain saved error outputs from an old execution.")
    parser.add_argument("--include-subdirectories", action="store_true",
                        help="Also audit notebooks below the repository root.")
    args = parser.parse_args(argv)
    pattern = "**/*.ipynb" if args.include_subdirectories else "*.ipynb"
    files = sorted(ROOT.glob(pattern))
    if not files:
        print("NOTEBOOK_AUDIT=FAIL no notebooks found", flush=True)
        return 1
    shell = InteractiveShell()
    results = [audit_notebook(path, shell) for path in files]
    for row in results:
        if args.strict_clean and row["saved_error_outputs"]:
            row["status"] = "FAIL"
            row["errors"].append({
                "kind": "stale-output",
                "message": "saved error output exists; rerun the notebook cell and replace historical failure output",
            })
        print("NOTEBOOK_AUDIT_ITEM " + json.dumps(row, ensure_ascii=False), flush=True)
    report = {
        "test": "OEC all-notebook structural and syntax audit",
        "started_unix": time.time(),
        "root": str(ROOT),
        "notebook_count": len(results),
        "passed": sum(row["status"] == "PASS" for row in results),
        "failed": sum(row["status"] == "FAIL" for row in results),
        "saved_error_output_count": sum(len(row["saved_error_outputs"]) for row in results),
        "code_cell_count": sum(row["code_cells"] for row in results),
        "syntax_checked_cell_count": sum(row["syntax_checked_cells"] for row in results),
        "notebooks": results,
    }
    report["finished_unix"] = time.time()
    output = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report_json:
        target = args.report_json.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
        print(f"NOTEBOOK_AUDIT_REPORT={target}", flush=True)
    print("NOTEBOOK_AUDIT_SUMMARY " + json.dumps({
        key: report[key] for key in (
            "notebook_count", "passed", "failed", "saved_error_output_count",
            "code_cell_count", "syntax_checked_cell_count",
        )
    }, ensure_ascii=False), flush=True)
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
