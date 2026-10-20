#!/usr/bin/env python3
"""One-row live OEC E2E acceptance: LTX -> Qwen2-VL QA -> chunked HF upload -> remote verification.

This is an opt-in operational smoke, not a quality benchmark. It requires the
configured assigned runner (oec-1 by default), an idle A100, fresh StorageManager admission, an existing
authenticated dataset repository, and existing/cacheable dependencies. It never
touches the shared upload queue or starts the continuous daemons.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class GateBlocked(RuntimeError):
    pass


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_logged(command: list[str], log_path: Path, *, env: dict[str, str] | None = None,
               timeout: int = 120) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command, cwd=ROOT, env=env, text=True, capture_output=True,
        timeout=timeout, check=False,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "COMMAND=" + json.dumps(command) + "\nEXIT_CODE=" + str(result.returncode)
        + "\n\nSTDOUT:\n" + result.stdout + "\n\nSTDERR:\n" + result.stderr,
        encoding="utf-8",
    )
    return result


def gpu_preflight() -> dict[str, Any]:
    runner = os.environ.get("RUNNER_NAME", "")
    expected_runner = os.environ.get("OEC_EXPECTED_RUNNER", "oec-1")
    if runner != expected_runner:
        raise GateBlocked(f"expected assigned runner {expected_runner}, got {runner or 'unknown'}")
    # Read-only nvidia-smi admission. Shared OEC-Play context is only tolerated when
    # explicitly enabled, same-user, recognized by executable path, low-memory and <=5% util.
    from oec_gpu_admission import inspect_a100_devices
    try:
        admission = inspect_a100_devices(min_free_mib=30000)
    except Exception as exc:
        raise GateBlocked(f"nvidia-smi GPU process admission failed: {type(exc).__name__}: {exc}") from exc
    eligible = admission["eligible_devices"]
    if not eligible:
        raise GateBlocked("no A100 has at least 30 GiB free VRAM and satisfies the GPU/process ownership policy: "
                          + json.dumps({"policy": admission["policy"], "devices": admission["devices"]}, sort_keys=True))
    selected = eligible[0]
    print("OEC_E2E_GPU_ADMISSION=" + json.dumps({
        "selected": selected, "policy": admission["policy"], "devices": admission["devices"]
    }, sort_keys=True), flush=True)
    return {
        "runner": runner,
        "host": __import__("socket").gethostname(),
        "gpus": admission["devices"],
        "selected_qa_gpu": int(selected["index"]),
        "compute_processes": [p for d in admission["devices"] for p in d["processes"]],
        "gpu_admission_policy": admission["policy"],
    }


def verify_hf_target() -> tuple[str, Any]:
    from huggingface_hub import HfApi
    from core_config import HF_DATASET_REPO

    repo = str(HF_DATASET_REPO or "").strip()
    if not repo or "YourHFUsername" in repo or repo.endswith("/AIEROS-Asset-Factory") and repo.startswith("Your"):
        raise GateBlocked("AIEROS_HF_DATASET_REPO is unset or still a placeholder; no upload attempted")
    api = HfApi()
    try:
        api.whoami()
    except Exception as exc:
        raise GateBlocked("Hugging Face authentication preflight failed; credential values are not logged") from exc
    try:
        exists = api.repo_exists(repo_id=repo, repo_type="dataset")
    except Exception as exc:
        raise GateBlocked("could not verify the configured dataset repository; no repository will be created") from exc
    if not exists:
        raise GateBlocked("configured dataset repository does not already exist; no repository will be created")
    return repo, api


def create_run_scoped_queue(db_path: Path, asset_path: Path, metadata_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_path TEXT NOT NULL,
                json_path TEXT NOT NULL,
                total_size_bytes INTEGER NOT NULL,
                status TEXT DEFAULT 'PENDING',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        cur = conn.execute(
            "INSERT INTO assets (asset_path, json_path, total_size_bytes, status) VALUES (?, ?, ?, 'PENDING_QA')",
            (str(asset_path), str(metadata_path), asset_path.stat().st_size + metadata_path.stat().st_size),
        )
        asset_id = int(cur.lastrowid)
        conn.commit()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["asset_id"] = asset_id
    write_json(metadata_path, metadata)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE assets SET total_size_bytes = ? WHERE id = ?",
            (asset_path.stat().st_size + metadata_path.stat().st_size, asset_id),
        )
        conn.commit()
    return asset_id


def remote_chunk_readback(api: Any, repo: str, report_root: Path, asset_sha: str,
                          metadata_sha: str, expected_asset_bytes: int) -> dict[str, Any]:
    from huggingface_hub import hf_hub_download

    remote_prefix = None
    # The asset ID is placed in the manifest namespace and is returned by the uploader.
    # The caller sets report_root/remote-manifest-path.txt after the manifest name is known.
    locator = report_root / "remote-manifest-path.txt"
    if not locator.is_file():
        raise RuntimeError("chunk uploader did not record its expected remote manifest path")
    manifest_path = locator.read_text(encoding="utf-8").strip()
    remote_prefix = manifest_path.rsplit("/", 1)[0]
    repo_files = set(api.list_repo_files(repo_id=repo, repo_type="dataset"))
    if manifest_path not in repo_files:
        raise RuntimeError("remote manifest is not present after upload")
    readback_root = report_root / "hf-readback"
    downloaded_manifest = Path(hf_hub_download(
        repo_id=repo, filename=manifest_path, repo_type="dataset", local_dir=str(readback_root)
    ))
    manifest = json.loads(downloaded_manifest.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete" or manifest.get("protocol") != "oec-asset-chunks-v1":
        raise RuntimeError("downloaded remote manifest is incomplete or has an unexpected protocol")
    if manifest.get("asset_sha256") != asset_sha or int(manifest.get("asset_bytes", -1)) != expected_asset_bytes:
        raise RuntimeError("remote manifest does not match the expected QA-passed asset")
    rebuilt = bytearray()
    part_reports = []
    for expected_index, part in enumerate(manifest.get("parts", [])):
        if int(part.get("index", -1)) != expected_index:
            raise RuntimeError("manifest parts are not in contiguous index order")
        path = str(part["path"])
        if path not in repo_files:
            raise RuntimeError(f"remote manifest references missing part: {path}")
        downloaded_part = Path(hf_hub_download(
            repo_id=repo, filename=path, repo_type="dataset", local_dir=str(readback_root)
        ))
        data = downloaded_part.read_bytes()
        part_sha = hashlib.sha256(data).hexdigest()
        if len(data) != int(part["size_bytes"]) or part_sha != part["sha256"]:
            raise RuntimeError(f"remote part size/hash mismatch: {path}")
        if int(part["offset_bytes"]) != len(rebuilt):
            raise RuntimeError(f"remote part offset mismatch: {path}")
        rebuilt.extend(data)
        part_reports.append({"path": path, "bytes": len(data), "sha256": part_sha})
    assembled_sha = hashlib.sha256(rebuilt).hexdigest()
    if len(rebuilt) != expected_asset_bytes or assembled_sha != asset_sha:
        raise RuntimeError("assembled remote chunks differ from the QA-passed local asset")
    meta_spec = manifest.get("metadata", {})
    metadata_remote_path = str(meta_spec.get("path", ""))
    if metadata_remote_path not in repo_files:
        raise RuntimeError("remote metadata JSON listed in manifest is missing")
    downloaded_metadata = Path(hf_hub_download(
        repo_id=repo, filename=metadata_remote_path, repo_type="dataset", local_dir=str(readback_root)
    ))
    metadata_data = downloaded_metadata.read_bytes()
    metadata_readback_sha = hashlib.sha256(metadata_data).hexdigest()
    if metadata_readback_sha != metadata_sha or metadata_readback_sha != meta_spec.get("sha256"):
        raise RuntimeError("remote metadata JSON hash differs from the QA-passed local metadata")
    return {
        "status": "PASS",
        "manifest_path": manifest_path,
        "remote_parts": part_reports,
        "metadata_path": metadata_remote_path,
        "metadata_sha256": metadata_readback_sha,
        "assembled_asset_bytes": len(rebuilt),
        "assembled_asset_sha256": assembled_sha,
    }


def main() -> int:
    report_root = Path(os.environ.get(
        "OEC_E2E_REPORT_DIR",
        str(Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "oec-e2e-acceptance"),
    )).expanduser().resolve()
    report_root.mkdir(parents=True, exist_ok=True)
    run_id = os.environ.get("GITHUB_RUN_ID") or uuid.uuid4().hex[:12]
    report: dict[str, Any] = {
        "test": "OEC live LTX -> Qwen2-VL QA -> Hugging Face chunk upload -> remote readback",
        "run_id": run_id,
        "runner": os.environ.get("RUNNER_NAME", "unknown"),
        "downloads_by_sidecar": False,
        "package_installs": False,
        "shared_queue_used": False,
        "remote_dataset_created": False,
        "process_kill_attempted": False,
        "started_unix": time.time(),
        "status": "IN_PROGRESS",
    }
    run_db: Path | None = None
    try:
        gpu = gpu_preflight()
        report["gpu_preflight"] = gpu
        from core_config import SYSTEM_DIRS
        from storage_manager import managed_storage_operation
        status = run_logged(
            [sys.executable, str(ROOT / "storage_manager.py"), "--status"],
            report_root / "storage-before.log", timeout=45,
        )
        report["storage_status_returncode"] = status.returncode
        if status.returncode != 0:
            raise GateBlocked("read-only StorageManager status failed; no writes started")
        repo, api = verify_hf_target()
        report["hf_target"] = {"configured": True, "existing_dataset": True, "authenticated": True}
        before_paths = set(api.list_repo_files(repo_id=repo, repo_type="dataset"))
        report["remote_dataset_files_before"] = len(before_paths)
        visual_dir = report_root / "visual"
        sidecar_env = {
            **os.environ,
            "OEC_VISUAL_SMOKE_DIR": str(visual_dir),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        }
        sidecar = run_logged(
            [sys.executable, str(ROOT / "tools" / "run_visual_media_sidecar_smokes.py")],
            report_root / "visual-sidecar.log", env=sidecar_env, timeout=7200,
        )
        sidecar_report_path = visual_dir / "report.json"
        if sidecar_report_path.exists():
            sidecar_report = json.loads(sidecar_report_path.read_text(encoding="utf-8"))
            report["visual_sidecar"] = sidecar_report
        else:
            raise RuntimeError("visual sidecar did not create report.json")
        if sidecar.returncode != 0 or sidecar_report.get("status") != "PASS":
            raise RuntimeError("TRELLIS/LTX sidecar preflight or live inference did not pass; see visual-sidecar.log")
        ltx_provider = sidecar_report.get("providers", {}).get("ltx", {})
        ltx_file = Path(str(ltx_provider.get("artifact_path", ""))).expanduser()
        if not ltx_file.is_file():
            raise RuntimeError("LTX sidecar reported PASS but its MP4 artifact is missing")
        if sha256_file(ltx_file) != ltx_provider.get("artifact_sha256"):
            raise RuntimeError("LTX MP4 does not match the sidecar artifact hash")

        from core_config import SYSTEM_DIRS
        run_output_root = Path(SYSTEM_DIRS["outputs"]) / "oec-e2e-acceptance" / str(run_id)
        asset_path = run_output_root / f"oec-e2e-{run_id}.mp4"
        metadata_path = run_output_root / f"oec-e2e-{run_id}_info.json"
        run_db = run_output_root / "upload_queue.db"
        with managed_storage_operation(
            "outputs", required_gb=0.01, require_fresh_quota=True, minimum_free_gb=0.05
        ):
            run_output_root.mkdir(parents=True, exist_ok=False)
            shutil.copy2(ltx_file, asset_path)
            metadata = {
                "timestamp": time.strftime("%Y%m%d_%H%M%S", time.localtime()),
                "model_type": "LTX-2.3",
                "output_type": "video",
                "file_name": asset_path.name,
                "source": "OEC cache-only live sidecar acceptance",
                "generation_parameters": {
                    "provider": "ltx",
                    "model_revision": ltx_provider.get("model_revision"),
                    "source_artifact_sha256": ltx_provider.get("artifact_sha256"),
                    "source_artifact_bytes": ltx_provider.get("artifact_bytes"),
                },
                "run_id": str(run_id),
                "qa_pipeline": "Qwen2-VL-7B-Instruct",
            }
            write_json(metadata_path, metadata)
            asset_id = create_run_scoped_queue(run_db, asset_path, metadata_path)
        report["asset"] = {
            "asset_id": asset_id,
            "run_scoped_db": str(run_db),
            "source_asset": asset_path.name,
            "source_sha256_before_qa": sha256_file(asset_path),
            "source_bytes_before_qa": asset_path.stat().st_size,
            "status_before_qa": "PENDING_QA",
        }

        # Run QA in an already-provisioned Python 3.11 environment that has Qwen2-VL
        # dependencies. Never import QA in oec_deploy (which may not contain qwen_vl_utils),
        # and fail closed on a missing cache instead of downloading model weights mid-smoke.
        qa_python = Path(os.environ.get(
            "OEC_QA_PYTHON",
            str(Path.home() / "Conda" / "envs" / "phase1_ltx" / "bin" / "python"),
        )).expanduser()
        if not qa_python.is_file():
            raise GateBlocked(f"existing QA Python runtime not found: {qa_python}")
        qa_env = {
            **os.environ,
            "OEC_QA_CACHE_ONLY": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        }
        qa_log = report_root / "qa-worker.log"
        qa_command = [
            str(qa_python), str(ROOT / "qa_compliance_worker.py"),
            "--once", "--asset-id", str(asset_id),
            "--gpu", str(gpu["selected_qa_gpu"]),
            "--no-purge", "--db-path", str(run_db),
        ]
        qa_process = run_logged(qa_command, qa_log, env=qa_env, timeout=1800)
        report["qa_runtime"] = {
            "python": str(qa_python),
            "returncode": qa_process.returncode,
            "cache_only": True,
            "run_scoped_db": str(run_db),
            "log": str(qa_log),
        }
        if qa_process.returncode == 0 and f"[QA_ONCE] PASS asset_id={asset_id} status=PENDING_UPLOAD" in qa_process.stdout:
            qa_outcome = "PENDING_UPLOAD"
        elif qa_process.returncode == 0 and f"[QA_ONCE] REJECTED asset_id={asset_id}" in qa_process.stdout:
            qa_outcome = "REJECTED"
        else:
            raise RuntimeError(
                "Qwen2-VL QA subprocess did not return a completed PASS/REJECTED marker; "
                f"exit={qa_process.returncode}; stdout_tail={qa_process.stdout[-1500:]}; "
                f"stderr_tail={qa_process.stderr[-1500:]}"
            )
        report["qa_outcome"] = qa_outcome
        with sqlite3.connect(run_db) as conn:
            row = conn.execute(
                "SELECT status, asset_path, json_path, total_size_bytes FROM assets WHERE id = ?",
                (asset_id,),
            ).fetchone()
        if qa_outcome == "REJECTED":
            report["status"] = "QA_POLICY_REJECTED"
            report["finished_unix"] = time.time()
            report["note"] = "A complete QA rejection is recorded; upload was correctly not attempted."
            write_json(report_root / "pipeline-report.json", report)
            return 2
        if qa_outcome != "PENDING_UPLOAD" or row is None or row[0] != "PENDING_UPLOAD":
            raise RuntimeError(f"QA did not hand off the selected asset to PENDING_UPLOAD (outcome={qa_outcome}, row={row})")
        if not asset_path.is_file() or not metadata_path.is_file():
            raise RuntimeError("QA hand-off row is pending upload but one or both files are missing")
        passed_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if passed_metadata.get("qa_passed") is not True:
            raise RuntimeError("QA row changed state but its JSON metadata lacks qa_passed=true")

        # Retain exact post-QA source bytes and metadata before the uploader deletes selected inputs.
        preserved = report_root / "qa-passed-source"
        preserved.mkdir(parents=True, exist_ok=True)
        asset_backup = preserved / asset_path.name
        metadata_backup = preserved / metadata_path.name
        shutil.copy2(asset_path, asset_backup)
        shutil.copy2(metadata_path, metadata_backup)
        asset_sha = sha256_file(asset_path)
        metadata_sha = sha256_file(metadata_path)
        report["qa_passed_asset"] = {
            "asset_id": asset_id,
            "status": row[0],
            "asset_bytes": asset_path.stat().st_size,
            "asset_sha256": asset_sha,
            "metadata_bytes": metadata_path.stat().st_size,
            "metadata_sha256": metadata_sha,
            "qa_category": passed_metadata.get("qa_category"),
            "seo_title_present": bool(passed_metadata.get("seo_title")),
            "keyword_count": len(passed_metadata.get("seo_keywords", [])),
        }

        # Force a small, test-only chunk threshold so the actual generated MP4 exercises
        # the real chunk upload/read-after-write path without fabricating a huge dummy video.
        import hf_upload_daemon as uploader
        uploader.QUEUE_DB_PATH = str(run_db)
        uploader.HF_DATASET_REPO = repo
        uploader.UPLOAD_BATCH_SIZE_GB = 0.0001  # about 104.9 KiB; forces this MP4 into 3 bounded chunks
        os.environ["AIEROS_UPLOAD_CHUNK_MB"] = "1"
        daemon = uploader.HFUploadDaemon(
            auto_confirm=False, cleanup_on_start=False, create_repo_if_missing=False,
        )
        uploaded = daemon.process_queue(max_batches=1, asset_id=asset_id, chunk_oversize=True)
        daemon.lock_file.close()
        if uploaded != 1:
            raise RuntimeError("bounded uploader did not complete exactly one asset")

        remote_prefix = f"data/chunks/asset-{asset_id}-{asset_sha}"
        manifest_remote = f"{remote_prefix}/manifest.json"
        (report_root / "remote-manifest-path.txt").write_text(manifest_remote + "\n", encoding="utf-8")
        report["remote_upload"] = {
            "status": "API_UPLOAD_PASS",
            "repo_existing_verified": True,
            "manifest_path": manifest_remote,
        }
        # The uploader deletes the selected local files only after remote completion.
        # Use the pre-upload byte count retained in the report, not the deleted path.
        expected_asset_bytes = int(report["qa_passed_asset"]["asset_bytes"])
        readback = remote_chunk_readback(
            api, repo, report_root, asset_sha, metadata_sha, expected_asset_bytes
        )
        report["remote_read_after_write"] = readback
        with sqlite3.connect(run_db) as conn:
            remaining = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        if remaining != 0:
            raise RuntimeError(f"selected queue row remains after successful remote publish: remaining={remaining}")
        report["queue_final"] = {"selected_rows_remaining": remaining, "status": "complete"}
        report["status"] = "PASS"
        report["finished_unix"] = time.time()
        write_json(report_root / "pipeline-report.json", report)
        return 0
    except GateBlocked as exc:
        report["status"] = "BLOCKED"
        report["blocker"] = str(exc)
        report["error_type"] = type(exc).__name__
        report["traceback"] = traceback.format_exc()
        write_json(report_root / "pipeline-report.json", report)
        print("OEC_E2E_BLOCKED=" + str(exc), file=sys.stderr, flush=True)
        return 3
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["error_type"] = type(exc).__name__
        report["traceback"] = traceback.format_exc()
        report["finished_unix"] = time.time()
        write_json(report_root / "pipeline-report.json", report)
        print("OEC_E2E_FAIL=" + str(exc), file=sys.stderr, flush=True)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
