"""Dependency-light HTTP/job lifecycle shared by OEC media-model sidecars.

Model runtimes are imported only by their provider after the server has started.
The API never runs expensive inference on a request-handler thread.
"""
from __future__ import annotations

import base64
import binascii
import contextlib
import hashlib
import io
import json
import logging
import os
import queue
import re
import secrets
import shutil
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

LOG = logging.getLogger("oec.media_service")
MAX_HTTP_BODY = 20 * 1024 * 1024
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_DIMENSION = 4096
MAX_IMAGE_PIXELS = 16_777_216
JOB_ID_RE = re.compile(r"job_[A-Za-z0-9_-]{12,40}\Z")


class RequestError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class StorageUnavailable(RuntimeError):
    pass


class ModelNotReady(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _system_dirs() -> dict[str, str]:
    # OEC config is deliberately the first project import in each sidecar.
    import core_config
    return core_config.SYSTEM_DIRS


def storage_check(area: str, required_gb: float, minimum_free_gb: float = 0.05) -> tuple[bool, str]:
    """Use OEC's authoritative admission gate; never substitute guessed quota."""
    try:
        from storage_manager import storage_preflight
        ok, reason = storage_preflight(
            area,
            required_gb=required_gb,
            require_fresh_quota=True,
            minimum_free_gb=minimum_free_gb,
        )
        return bool(ok), str(reason)
    except Exception as exc:  # a missing/stale storage gate is a hard failure
        return False, f"storage admission unavailable ({type(exc).__name__})"


@contextlib.contextmanager
def managed_write(area: str, required_gb: float, minimum_free_gb: float = 0.05):
    from storage_manager import managed_storage_operation
    with managed_storage_operation(
        area,
        required_gb=required_gb,
        require_fresh_quota=True,
        minimum_free_gb=minimum_free_gb,
    ):
        yield


def safe_child(root: Path, *parts: str) -> Path:
    """Construct a path under a known OEC root without accepting user paths."""
    root_resolved = root.expanduser().resolve()
    result = root_resolved.joinpath(*parts).resolve()
    if result == root_resolved or root_resolved not in result.parents:
        raise ValueError("path escaped its OEC-managed root")
    return result


def remove_job_input(path: Path | None, expected_root: Path) -> None:
    """Delete only an adapter-owned, run-scoped input directory."""
    if path is None:
        return
    try:
        root = expected_root.expanduser().resolve()
        target = path.expanduser().resolve()
        if root not in target.parents or target.is_symlink():
            LOG.error("Refused cleanup outside adapter input root")
            return
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    except OSError as exc:
        LOG.warning("Could not remove temporary media-job input (%s)", type(exc).__name__)


def image_bytes_to_png(image_base64: str) -> bytes:
    if not isinstance(image_base64, str) or not image_base64:
        raise RequestError("image_base64 is required for this task")
    if len(image_base64) > (MAX_IMAGE_BYTES * 4 // 3 + 16):
        raise RequestError("encoded image exceeds the 12 MiB input limit", 413)
    try:
        raw = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RequestError("image_base64 must contain valid base64 without a data-URL prefix") from exc
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise RequestError("image must be between 1 byte and 12 MiB", 413)

    try:
        from PIL import Image, UnidentifiedImageError
        with Image.open(io.BytesIO(raw)) as probe:
            if probe.format not in {"PNG", "JPEG", "WEBP"}:
                raise RequestError("supported image formats are PNG, JPEG, and WebP")
            width, height = probe.size
            if width < 1 or height < 1 or width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                raise RequestError("image dimensions must be between 1 and 4096 pixels per side")
            if width * height > MAX_IMAGE_PIXELS:
                raise RequestError("image exceeds the 16-megapixel pixel limit", 413)
            probe.verify()
        with Image.open(io.BytesIO(raw)) as opened:
            image = opened.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=False)
            return buffer.getvalue()
    except RequestError:
        raise
    except Exception as exc:
        # Do not expose decoder internals or filesystem details to clients.
        raise RequestError("image file could not be decoded") from exc


def validate_glb(path: Path) -> dict[str, Any]:
    """Validate the GLB container and non-empty mesh accessors."""
    import struct
    if not path.is_file() or path.stat().st_size < 20:
        raise ValueError("TRELLIS did not produce a non-empty GLB file")
    raw = path.read_bytes()
    if raw[:4] != b"glTF":
        raise ValueError("GLB magic header is invalid")
    version, declared_length = struct.unpack_from("<II", raw, 4)
    if version != 2 or declared_length != len(raw):
        raise ValueError("GLB version or declared length is invalid")
    json_length, json_type = struct.unpack_from("<II", raw, 12)
    if json_type != 0x4E4F534A or 20 + json_length > len(raw):
        raise ValueError("GLB JSON chunk is invalid")
    document = json.loads(raw[20:20 + json_length].decode("utf-8").rstrip(" \t\r\n\x00"))
    accessors = document.get("accessors", [])
    primitives = [p for mesh in document.get("meshes", []) for p in mesh.get("primitives", [])]
    vertex_counts, index_counts = [], []
    for primitive in primitives:
        attributes = primitive.get("attributes", {})
        vertex_id = attributes.get("POSITION")
        index_id = primitive.get("indices")
        if isinstance(vertex_id, int) and 0 <= vertex_id < len(accessors):
            vertex_counts.append(int(accessors[vertex_id].get("count", 0)))
        if isinstance(index_id, int) and 0 <= index_id < len(accessors):
            index_counts.append(int(accessors[index_id].get("count", 0)))
    if not primitives or not any(vertex_counts) or not any(index_counts):
        raise ValueError("GLB contains no non-empty mesh geometry")
    return {"meshes": len(document.get("meshes", [])), "primitives": len(primitives),
            "positions": vertex_counts, "indices": index_counts, "bytes": len(raw)}


def validate_mp4(path: Path) -> dict[str, Any]:
    """Check MP4 box structure and, when available, ask ffprobe to read streams."""
    import json as json_module
    import struct
    import subprocess
    if not path.is_file() or path.stat().st_size < 32:
        raise ValueError("LTX did not produce a non-empty MP4 file")
    size = path.stat().st_size
    found = set()
    offset = 0
    with path.open("rb") as handle:
        while offset + 8 <= size and offset < 8 * 1024 * 1024:
            handle.seek(offset)
            header = handle.read(8)
            if len(header) != 8:
                break
            box_size = struct.unpack(">I", header[:4])[0]
            box_type = header[4:8].decode("latin1")
            if box_type:
                found.add(box_type)
            if box_size == 1:
                ext = handle.read(8)
                if len(ext) != 8:
                    break
                box_size = struct.unpack(">Q", ext)[0]
                header_size = 16
            else:
                header_size = 8
            if box_size == 0:
                break
            if box_size < header_size or offset + box_size > size:
                raise ValueError("MP4 contains an invalid top-level box size")
            offset += box_size
    if "ftyp" not in found or not ({"mdat", "moov"} & found):
        raise ValueError("MP4 container is missing required ftyp/media metadata boxes")
    ffprobe = shutil.which("ffprobe")
    streams: list[dict[str, Any]] = []
    if ffprobe:
        try:
            completed = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,duration",
                 "-of", "json", str(path)],
                check=True, capture_output=True, text=True, timeout=20,
            )
            streams = json_module.loads(completed.stdout).get("streams", [])
            if not streams or not any(s.get("codec_type") == "video" for s in streams):
                raise ValueError("MP4 has no readable video stream")
        except (subprocess.SubprocessError, json_module.JSONDecodeError) as exc:
            raise ValueError("ffprobe could not read the generated MP4") from exc
    elif "moov" not in found:
        raise ValueError("ffprobe is unavailable and MP4 metadata is incomplete")
    return {"bytes": size, "top_level_boxes": sorted(found), "streams": streams,
            "validation": "ffprobe" if ffprobe else "container-structure"}


class MediaProvider:
    name = "media"
    artifact_content_type = "application/octet-stream"
    artifact_extension = "bin"
    max_prompt_chars = 800

    def __init__(self, allow_download: bool = False):
        self.allow_download = allow_download
        self.model_loaded = False
        self.model_name = "unknown"
        self.model_revision: str | None = None
        self.device_name: str | None = None

    def validate_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def load_runtime(self) -> None:
        raise NotImplementedError

    def run_job(self, job_id: str, request: dict[str, Any], input_file: Path | None) -> tuple[Path, dict[str, Any]]:
        raise NotImplementedError


class MediaJobService:
    def __init__(self, provider: MediaProvider, queue_size: int = 2, job_timeout_seconds: int = 1800):
        self.provider = provider
        self.queue: queue.Queue[str | None] = queue.Queue(maxsize=max(1, queue_size))
        self.job_timeout_seconds = max(30, int(job_timeout_seconds))
        self.jobs: dict[str, dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.retention_seconds = max(3600, int(os.environ.get("OEC_MEDIA_RETENTION_SECONDS", str(7 * 24 * 3600))))
        self.retention_sweep_seconds = max(300, int(os.environ.get("OEC_MEDIA_RETENTION_SWEEP_SECONDS", "1800")))
        self.ready = False
        self.fatal_error: str | None = None
        self.loading = True
        self.shutdown_requested = False
        dirs = _system_dirs()
        self.input_root = Path(dirs["inputs"]).expanduser().resolve() / "media_services" / provider.name / "jobs"
        self.output_root = Path(dirs["outputs"]).expanduser().resolve() / "media_services" / provider.name / "jobs"
        self.state_root = Path(dirs["cache"]).expanduser().resolve() / "media_services" / provider.name / "jobs"
        self._restore_job_records_and_prune()
        self.worker = threading.Thread(target=self._worker_loop, name=f"oec-{provider.name}-worker", daemon=True)
        self.worker.start()
        self._retention_stop = threading.Event()
        self.retention_worker = threading.Thread(target=self._retention_loop, name=f"oec-{provider.name}-retention", daemon=True)
        self.retention_worker.start()

    @staticmethod
    def _age_seconds(iso_time: str) -> float | None:
        try:
            stamp = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
            return max(0.0, (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            return None

    def _delete_owned_job_artifacts(self, record: dict[str, Any]) -> None:
        job_id = record.get("job_id")
        if not isinstance(job_id, str) or not JOB_ID_RE.fullmatch(job_id):
            return
        # Only delete the exact per-job folder that this adapter creates.
        result_value = record.get("result_path")
        if isinstance(result_value, str):
            try:
                result_path = Path(result_value).expanduser().resolve()
                output_root = self.output_root.resolve()
                job_folder = result_path.parent
                if (output_root in job_folder.parents and job_folder.parent == output_root
                        and job_folder.name == job_id and not job_folder.is_symlink()):
                    shutil.rmtree(job_folder, ignore_errors=True)
            except OSError as exc:
                LOG.warning("Could not expire owned media result (%s)", type(exc).__name__)
        input_folder = safe_child(self.input_root, job_id)
        remove_job_input(input_folder, self.input_root.parent)

    def _restore_job_records_and_prune(self) -> None:
        """Restore visible job state and expire only sidecar-owned, old job data."""
        if not self.state_root.is_dir():
            return
        for state_path in self.state_root.glob("job_*.json"):
            if state_path.is_symlink() or not state_path.is_file():
                continue
            try:
                record = json.loads(state_path.read_text(encoding="utf-8"))
                job_id = record.get("job_id")
                if not isinstance(job_id, str) or not JOB_ID_RE.fullmatch(job_id) or state_path.stem != job_id:
                    continue
                age = self._age_seconds(record.get("updated_at", ""))
                if age is None:
                    LOG.warning("Preserving media job record with invalid timestamp: %s", job_id)
                    continue
                if age > self.retention_seconds:
                    self._delete_owned_job_artifacts(record)
                    state_path.unlink(missing_ok=True)
                    continue
                if record.get("status") in {"queued", "running"}:
                    self._delete_owned_job_artifacts(record)
                    record.update(status="failed", progress=100,
                                  message="Service restarted before this job finished; submit it again",
                                  error_type="ServiceRestarted", updated_at=utc_now(),
                                  input_file=None, input_dir=None, result_path=None)
                self.jobs[job_id] = record
            except (OSError, json.JSONDecodeError, AttributeError, TypeError) as exc:
                LOG.warning("Preserving unreadable media job record (%s)", type(exc).__name__)

    def _retention_loop(self) -> None:
        while not self._retention_stop.wait(self.retention_sweep_seconds):
            with self.lock:
                expired = []
                for job_id, record in self.jobs.items():
                    age = self._age_seconds(record.get("updated_at", ""))
                    if age is not None and age > self.retention_seconds:
                        expired.append((job_id, dict(record)))
                for job_id, record in expired:
                    self._delete_owned_job_artifacts(record)
                    self.jobs.pop(job_id, None)
                    state_path = safe_child(self.state_root, f"{job_id}.json")
                    with contextlib.suppress(OSError):
                        state_path.unlink()
            if expired:
                LOG.info("Expired %d own %s job records/artifacts by retention policy", len(expired), self.provider.name)

    def _check_storage(self, required_output_gb: float = 0.05) -> None:
        for area, required in (("outputs", required_output_gb), ("cache", 0.002)):
            ok, reason = storage_check(area, required)
            if not ok:
                LOG.error("OEC %s storage admission denied: %s", area, reason)
                raise StorageUnavailable(f"OEC {area} storage admission denied; inspect the storage-manager log")

    def health(self) -> dict[str, Any]:
        storage_ok, storage_reason = True, "admission passed"
        if self.provider.model_loaded:
            for area, required in (("outputs", 0.05), ("cache", 0.002)):
                ok, reason = storage_check(area, required)
                if not ok:
                    storage_ok, storage_reason = False, reason
                    break
        with self.lock:
            ready = bool(self.ready and storage_ok and not self.shutdown_requested)
            error = self.fatal_error
            loading = self.loading
        if not storage_ok:
            error = "required OEC storage is unavailable"
        return {"status": "ok", "api_version": 1, "ready": ready,
                "model_loaded": bool(self.provider.model_loaded), "loading": loading,
                "storage_ready": storage_ok, "message": "ready" if ready else ("model loading" if loading and not error else "not ready"),
                "error": error, "storage_message": storage_reason if not storage_ok else None}

    def _persist(self, job: dict[str, Any], required: bool = False) -> bool:
        path = safe_child(self.state_root, f"{job['job_id']}.json")
        temp = path.with_suffix(".json.tmp")
        serialized = json.dumps(job, ensure_ascii=False, separators=(",", ":"))
        try:
            with managed_write("cache", 0.002, minimum_free_gb=0.01):
                path.parent.mkdir(parents=True, exist_ok=True)
                temp.write_text(serialized, encoding="utf-8")
                os.replace(temp, path)
            return True
        except Exception as exc:
            with contextlib.suppress(OSError):
                temp.unlink()
            LOG.warning("Could not persist %s job state (%s)", self.provider.name, type(exc).__name__)
            if required:
                return False
            return False

    def _public_job(self, job: dict[str, Any]) -> dict[str, Any]:
        keys = ("job_id", "status", "progress", "message", "created_at", "updated_at")
        public = {key: job[key] for key in keys if key in job}
        if job.get("status") == "succeeded" and isinstance(job.get("metadata"), dict):
            public["metadata"] = job["metadata"]
        return public

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        if not JOB_ID_RE.fullmatch(job_id):
            return None
        with self.lock:
            job = self.jobs.get(job_id)
            return self._public_job(job) if job else None

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RequestError("request body must be a JSON object")
        with self.lock:
            if self.shutdown_requested:
                raise RequestError("media service is shutting down", 503)
            if self.fatal_error:
                raise RequestError("model runtime is unavailable; inspect the service log", 503)
        normalized = self.provider.validate_request(payload)
        has_image = "image_base64" in payload
        if has_image and not normalized.get("expects_image", False):
            raise RequestError("this task does not accept an image")
        if normalized.get("expects_image", False) and not has_image:
            raise RequestError("image_base64 is required for this task")
        # Never retain a base64 payload in job state or logs.
        normalized.pop("expects_image", None)
        job_id = "job_" + secrets.token_urlsafe(18).rstrip("=")
        input_file: Path | None = None
        input_dir: Path | None = None
        if has_image:
            png_bytes = image_bytes_to_png(payload.get("image_base64"))
            self._check_storage(0.10)
            input_dir = safe_child(self.input_root, job_id)
            input_file = safe_child(input_dir, "input.png")
            try:
                with managed_write("inputs", 0.03, minimum_free_gb=0.01):
                    input_dir.mkdir(parents=True, exist_ok=False)
                    input_file.write_bytes(png_bytes)
            except Exception as exc:
                remove_job_input(input_dir, self.input_root.parent)
                raise StorageUnavailable(f"input storage admission failed ({type(exc).__name__})") from exc
        else:
            self._check_storage(0.10)

        now = utc_now()
        job = {"job_id": job_id, "status": "queued", "progress": 0, "message": "Job accepted",
               "created_at": now, "updated_at": now, "request": normalized,
               "input_file": str(input_file) if input_file else None,
               "input_dir": str(input_dir) if input_dir else None,
               "result_path": None, "result_name": None, "result_content_type": None,
               "metadata": None, "error_type": None}
        if not self._persist(job, required=True):
            remove_job_input(input_dir, self.input_root.parent)
            raise StorageUnavailable("could not persist job state under OEC cache storage")
        with self.lock:
            self.jobs[job_id] = job
        try:
            self.queue.put_nowait(job_id)
        except queue.Full:
            with self.lock:
                self.jobs.pop(job_id, None)
            state_path = safe_child(self.state_root, f"{job_id}.json")
            with contextlib.suppress(OSError):
                state_path.unlink()
            remove_job_input(input_dir, self.input_root.parent)
            raise RequestError("media service queue is full; retry after a job completes", 429)
        return {"job_id": job_id, "status": "queued", "message": "Job accepted"}

    def _update(self, job_id: str, **fields: Any) -> None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return
            job.update(fields)
            job["updated_at"] = utc_now()
            snapshot = dict(job)
        self._persist(snapshot)

    def _worker_loop(self) -> None:
        try:
            self._check_storage(0.10)
            if self.provider.allow_download:
                ok, reason = storage_check("models", 0.01, 0.05)
                if not ok:
                    LOG.error("OEC model storage admission denied: %s", reason)
                    raise StorageUnavailable("OEC model storage admission denied; inspect the storage-manager log")
            self.provider.load_runtime()
            if not self.provider.model_loaded:
                raise ModelNotReady("provider loader returned without a loaded model")
            with self.lock:
                self.ready = True
                self.loading = False
            LOG.info("%s model runtime loaded; API ready", self.provider.name)
        except Exception as exc:
            with self.lock:
                self.loading = False
                self.ready = False
                self.fatal_error = f"{type(exc).__name__}: model runtime could not be loaded"
            LOG.error("%s runtime load failed (%s)", self.provider.name, type(exc).__name__)

        while True:
            job_id = self.queue.get()
            try:
                if job_id is None:
                    return
                with self.lock:
                    fatal = self.fatal_error
                if fatal:
                    self._update(job_id, status="failed", progress=100,
                                 message="Job failed because the model runtime is unavailable",
                                 error_type="ModelNotReady")
                    self._cleanup_input(job_id)
                    continue
                self._execute(job_id)
            finally:
                self.queue.task_done()

    def _cleanup_output(self, job_id: str) -> None:
        """Remove only this sidecar's own per-job output directory on failure."""
        try:
            target = safe_child(self.output_root, job_id)
            root = self.output_root.resolve()
            if target.parent == root and target.name == job_id and not target.is_symlink() and target.is_dir():
                shutil.rmtree(target)
        except (OSError, ValueError) as exc:
            LOG.warning("Could not remove failed media-job output (%s)", type(exc).__name__)

    def _cleanup_input(self, job_id: str) -> None:
        with self.lock:
            job = self.jobs.get(job_id)
            input_dir = Path(job["input_dir"]) if job and job.get("input_dir") else None
        remove_job_input(input_dir, self.input_root.parent)

    def _execute(self, job_id: str) -> None:
        started = time.monotonic()
        with self.lock:
            job = self.jobs[job_id]
            request = dict(job["request"])
            input_file = Path(job["input_file"]) if job.get("input_file") else None
        self._update(job_id, status="running", progress=5, message="Generation started")
        try:
            self._check_storage(0.10)
            result_path, metadata = self.provider.run_job(job_id, request, input_file)
            if not result_path.is_file() or result_path.stat().st_size <= 0:
                raise ValueError("provider returned no output artifact")
            if time.monotonic() - started > self.job_timeout_seconds:
                with contextlib.suppress(OSError):
                    result_path.unlink()
                raise TimeoutError("generation exceeded the configured job timeout")
            metadata = dict(metadata)
            metadata.setdefault("model", self.provider.model_name)
            metadata.setdefault("model_revision", self.provider.model_revision)
            metadata.setdefault("device", self.provider.device_name)
            metadata["artifact_bytes"] = result_path.stat().st_size
            metadata["artifact_sha256"] = self._file_sha256(result_path)
            self._update(job_id, status="succeeded", progress=100, message="Artifact validated and ready",
                         result_path=str(result_path), result_name=f"{job_id}.{self.provider.artifact_extension}",
                         result_content_type=self.provider.artifact_content_type, metadata=metadata, error_type=None)
        except Exception as exc:
            LOG.exception("%s media job failed (%s)", self.provider.name, type(exc).__name__)
            self._cleanup_output(job_id)
            if isinstance(exc, (RuntimeError, TimeoutError)):
                # A model/runtime error can leave device state uncertain. Stop
                # advertising readiness until the operator restarts and checks it.
                with self.lock:
                    self.ready = False
                    self.fatal_error = f"{type(exc).__name__}: runtime needs operator review"
            self._update(job_id, status="failed", progress=100,
                         message=f"Generation failed ({type(exc).__name__}); inspect service log",
                         error_type=type(exc).__name__)
        finally:
            self._cleanup_input(job_id)

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def result(self, job_id: str) -> tuple[Path, str, str] | None:
        if not JOB_ID_RE.fullmatch(job_id):
            return None
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return None
            if job.get("status") != "succeeded" or not job.get("result_path"):
                raise RequestError("job has not completed successfully", 409)
            path = Path(job["result_path"])
            content_type = str(job.get("result_content_type") or self.provider.artifact_content_type)
            name = str(job.get("result_name") or f"{job_id}.{self.provider.artifact_extension}")
        if not path.is_file():
            raise RequestError("job succeeded but its result artifact is missing", 409)
        return path, content_type, name

    def stop(self) -> None:
        with self.lock:
            self.shutdown_requested = True
            self.ready = False
        if hasattr(self, "_retention_stop"):
            self._retention_stop.set()
        try:
            self.queue.put_nowait(None)
        except queue.Full:
            # Wait briefly for one queue slot; work remains independent of the client.
            try:
                self.queue.put(None, timeout=2)
            except queue.Full:
                LOG.warning("Media worker queue did not drain before shutdown")
        if threading.current_thread() is not self.worker:
            self.worker.join(timeout=10)


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 16


def build_handler(service: MediaJobService) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "OEC-MediaService/1"
        sys_version = ""

        def log_message(self, fmt: str, *args: Any) -> None:
            LOG.info("http %s - %s", self.client_address[0], fmt % args)

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, Any]:
            raw_length = self.headers.get("Content-Length", "")
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise RequestError("Content-Length header is required") from exc
            if length < 1:
                raise RequestError("request body is empty")
            if length > MAX_HTTP_BODY:
                raise RequestError("request body exceeds the 20 MiB limit", 413)
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise RequestError("request body was incomplete")
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RequestError("request body must be valid UTF-8 JSON") from exc
            if not isinstance(payload, dict):
                raise RequestError("request body must be a JSON object")
            return payload

        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path == "/health":
                health = service.health()
                self._send_json(200 if health["ready"] else 503, health)
                return
            if path.startswith("/v1/jobs/"):
                match = re.fullmatch(r"/v1/jobs/([^/]+)(/result)?", path)
                if not match:
                    self._send_json(404, {"error": "unknown route"})
                    return
                job_id = unquote(match.group(1))
                if match.group(2):
                    try:
                        result = service.result(job_id)
                    except RequestError as exc:
                        self._send_json(exc.status_code, {"error": str(exc)})
                        return
                    if result is None:
                        self._send_json(404, {"error": "unknown job ID"})
                        return
                    file_path, content_type, filename = result
                    size = file_path.stat().st_size
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(size))
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    try:
                        with file_path.open("rb") as handle:
                            shutil.copyfileobj(handle, self.wfile, length=1024 * 1024)
                    except (BrokenPipeError, ConnectionResetError):
                        # The job/artifact survives a client disconnect.
                        LOG.info("client disconnected while downloading %s result", job_id)
                    return
                job = service.get_job(job_id)
                if job is None:
                    self._send_json(404, {"error": "unknown job ID"})
                else:
                    self._send_json(200, job)
                return
            self._send_json(404, {"error": "unknown route"})

        def do_POST(self) -> None:  # noqa: N802
            if urlsplit(self.path).path != "/v1/jobs":
                self._send_json(404, {"error": "unknown route"})
                return
            try:
                payload = self._read_json()
                result = service.submit(payload)
                self._send_json(202, result)
            except RequestError as exc:
                self._send_json(exc.status_code, {"error": str(exc)})
            except StorageUnavailable as exc:
                self._send_json(507, {"error": str(exc)})
            except Exception as exc:
                LOG.exception("request rejected (%s)", type(exc).__name__)
                self._send_json(500, {"error": "internal media-service error; inspect service log"})

        def do_PUT(self) -> None:  # noqa: N802
            self._send_json(405, {"error": "method not allowed"})

        def do_DELETE(self) -> None:  # noqa: N802
            self._send_json(405, {"error": "method not allowed"})

    return Handler


def serve(provider: MediaProvider, host: str, port: int, queue_size: int, timeout: int) -> int:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("Refusing non-loopback bind. Use an SSH tunnel to access the sidecar.")
    service = MediaJobService(provider, queue_size=queue_size, job_timeout_seconds=timeout)
    httpd = ReusableThreadingHTTPServer((host, port), build_handler(service))
    httpd.timeout = 1
    LOG.info("OEC %s sidecar listening on %s:%s (model loads in worker thread)", provider.name, host, port)
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        LOG.info("shutdown requested")
    finally:
        httpd.shutdown()
        httpd.server_close()
        service.stop()
    return 0
