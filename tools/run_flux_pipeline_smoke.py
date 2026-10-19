#!/usr/bin/env python3
"""Run one cache-only FLUX→TRELLIS A100 inference and preserve run evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--gpu", type=int, default=None)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--steps", type=int, default=4)
    args = parser.parse_args()

    runner_temp = Path(os.environ.get("RUNNER_TEMP", "/tmp")).expanduser().resolve()
    report_dir = args.report_dir.expanduser().resolve()
    if report_dir != runner_temp and runner_temp not in report_dir.parents:
        raise ValueError("report directory must be below RUNNER_TEMP")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "pipeline-report.json"
    log_path = report_dir / "pipeline.log"
    command = [
        sys.executable, str(ROOT / "pipeline_flux_trellis.py"), "--source-mode", "flux",
        "--work-dir", str(args.work_dir), "--width", str(args.width), "--height", str(args.height),
        "--steps", str(args.steps), "--max-image-size", "512", "--decimation-target", "5000",
        "--texture-size", "512", "--report-output", str(report_path),
    ]
    if args.gpu is not None:
        command.extend(["--gpu", str(args.gpu)])
    print("FLUX_PIPELINE_SMOKE_COMMAND=" + json.dumps(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=5400, check=False)
    combined_log = completed.stdout + ("\n" + completed.stderr if completed.stderr else "")
    log_path.write_text(combined_log, encoding="utf-8")
    print(combined_log[-10000:], end="" if combined_log.endswith("\n") else "\n", flush=True)
    if completed.returncode:
        print(f"FLUX_PIPELINE_SMOKE=FAIL exit_code={completed.returncode}", flush=True)
        return completed.returncode
    if not report_path.is_file():
        raise RuntimeError("combined pipeline returned success but did not create a report")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "PASS" or not report.get("artifacts"):
        raise RuntimeError("combined pipeline report has no accepted GLB artifact")
    artifact_dir = report_dir / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    copied = []
    for source in report.get("sources", []):
        original = Path(source["path"])
        if not original.is_file():
            raise RuntimeError(f"reported source image is missing: {original}")
        target = artifact_dir / original.name
        shutil.copy2(original, target)
        digest = sha256(target)
        if digest != source.get("sha256"):
            raise RuntimeError(f"source-image copy hash mismatch: {target}")
        copied.append({"kind":"source_image","path":str(target),"bytes":target.stat().st_size,"sha256":digest})
    for record in report["artifacts"]:
        item = record["output"]
        original = Path(item["path"])
        if not original.is_file():
            raise RuntimeError(f"reported GLB is missing: {original}")
        target = artifact_dir / original.name
        shutil.copy2(original, target)
        digest = sha256(target)
        if digest != item.get("sha256"):
            raise RuntimeError(f"GLB copy hash mismatch: {target}")
        copied.append({"kind":"glb","path":str(target),"bytes":target.stat().st_size,"sha256":digest,
                       "trimesh_reopen":item.get("trimesh_reopen"),
                       "vertices":item.get("trimesh_vertices"),"faces":item.get("trimesh_faces")})
    manifest = {"status":"PASS","source_mode":report.get("source_mode"),
                "elapsed_seconds":report.get("elapsed_seconds"),"artifacts":copied,
                "limitations":report.get("limitations",[])}
    (report_dir / "artifact-manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True),encoding="utf-8")
    print("FLUX_PIPELINE_SMOKE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
