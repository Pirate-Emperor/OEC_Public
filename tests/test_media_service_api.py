"""CPU-only regressions for the OEC media sidecar HTTP/job contract."""
from __future__ import annotations

import base64
import json
import struct
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "media_services"))
import common


class FakeProvider(common.MediaProvider):
    name = "fake"
    artifact_content_type = "application/octet-stream"
    artifact_extension = "bin"

    def __init__(self, block: threading.Event | None = None, started: threading.Event | None = None):
        super().__init__(False)
        self.output_root = Path("/tmp")
        self.block = block
        self.started = started

    def validate_request(self, payload):
        if payload.get("task") != "test":
            raise common.RequestError("task must be 'test'")
        return {"task": "test", "expects_image": False}

    def load_runtime(self):
        self.model_name = "fake-model"
        self.model_revision = "test-revision"
        self.device_name = "CPU test"
        self.model_loaded = True

    def run_job(self, job_id, request, input_file):
        if self.started:
            self.started.set()
        if self.block:
            self.block.wait(3)
        path = self.output_root / f"{job_id}.bin"
        path.write_bytes(b"fake artifact")
        return path, {"test": True}


def make_glb(path: Path) -> None:
    document = {"meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
                "accessors": [{"count": 3}, {"count": 3}]}
    payload = json.dumps(document, separators=(",", ":")).encode()
    payload += b" " * ((4 - len(payload) % 4) % 4)
    chunk = struct.pack("<II", len(payload), 0x4E4F534A) + payload
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(chunk)) + chunk)


def make_mp4_container(path: Path) -> None:
    # A small ISO-BMFF container fixture for the no-ffprobe structural fallback.
    path.write_bytes(struct.pack(">I4s", 16, b"ftyp") + b"isom\x00\x00\x02\x00" + struct.pack(">I4s", 16, b"moov") + b"\x00" * 8)


class MediaServiceApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.dirs = {key: str(base / key) for key in ("inputs", "outputs", "cache", "models")}
        for path in self.dirs.values():
            Path(path).mkdir(parents=True, exist_ok=True)
        self.patches = [
            mock.patch.object(common, "_system_dirs", return_value=self.dirs),
            mock.patch.object(common, "storage_check", return_value=(True, "test admission pass")),
            mock.patch.object(common, "managed_write", side_effect=lambda *a, **kw: _null_context()),
        ]
        for patcher in self.patches:
            patcher.start()
        self.fake_output = Path(self.dirs["outputs"]) / "fake_results"
        self.fake_output.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temp.cleanup()

    def new_service(self, provider=None, queue_size=2):
        provider = provider or FakeProvider()
        provider.output_root = self.fake_output
        service = common.MediaJobService(provider, queue_size=queue_size, job_timeout_seconds=60)
        deadline = time.time() + 2
        while service.loading and time.time() < deadline:
            time.sleep(0.01)
        self.assertTrue(provider.model_loaded)
        return service

    def test_health_is_not_ready_until_model_loaded(self):
        gate = threading.Event()

        class SlowProvider(FakeProvider):
            def load_runtime(inner_self):
                gate.wait(1)
                super(SlowProvider, inner_self).load_runtime()

        provider = SlowProvider()
        provider.output_root = self.fake_output
        service = common.MediaJobService(provider)
        try:
            self.assertFalse(service.health()["ready"])
            gate.set()
            deadline = time.time() + 2
            while not service.health()["ready"] and time.time() < deadline:
                time.sleep(0.01)
            self.assertTrue(service.health()["ready"])
        finally:
            gate.set()
            service.stop()

    def test_submit_status_and_result_lifecycle(self):
        service = self.new_service()
        try:
            accepted = service.submit({"task": "test"})
            self.assertEqual(accepted["status"], "queued")
            job_id = accepted["job_id"]
            deadline = time.time() + 3
            status = service.get_job(job_id)
            while status and status["status"] not in {"succeeded", "failed"} and time.time() < deadline:
                time.sleep(0.01)
                status = service.get_job(job_id)
            self.assertEqual(status["status"], "succeeded")
            result = service.result(job_id)
            self.assertEqual(result[0].read_bytes(), b"fake artifact")
            self.assertEqual(result[1], "application/octet-stream")
            self.assertEqual(service.get_job("job_unknownunknown"), None)
        finally:
            service.stop()

    def test_invalid_request_and_queue_saturation(self):
        block = threading.Event()
        started = threading.Event()
        provider = FakeProvider(block, started)
        service = self.new_service(provider, queue_size=1)
        try:
            with self.assertRaises(common.RequestError):
                service.submit({"task": "wrong"})
            first = service.submit({"task": "test"})
            self.assertTrue(started.wait(1))
            second = service.submit({"task": "test"})
            self.assertEqual(second["status"], "queued")
            with self.assertRaises(common.RequestError) as err:
                service.submit({"task": "test"})
            self.assertEqual(err.exception.status_code, 429)
            self.assertEqual(service.get_job(first["job_id"])["status"], "running")
        finally:
            block.set()
            service.stop()

    def test_result_not_ready_and_unknown_result(self):
        provider = FakeProvider()
        provider.output_root = self.fake_output
        service = self.new_service(provider)
        try:
            accepted = service.submit({"task": "test"})
            with self.assertRaises(common.RequestError) as err:
                service.result(accepted["job_id"])
            self.assertEqual(err.exception.status_code, 409)
            self.assertIsNone(service.result("job_unknownunknown"))
        finally:
            service.stop()

    def test_image_payload_validation_rejects_bad_base64_and_bad_image(self):
        with self.assertRaises(common.RequestError):
            common.image_bytes_to_png("%%%not-base64%%")
        with self.assertRaises(common.RequestError):
            common.image_bytes_to_png(base64.b64encode(b"not an image").decode())

    def test_audio_payload_validation_accepts_wav_signature_and_rejects_bad_base64(self):
        wav = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"fmt " + b"\x00" * 16
        decoded, extension = common.audio_bytes_with_extension(base64.b64encode(wav).decode())
        self.assertEqual(extension, "wav")
        self.assertEqual(decoded, wav)
        with self.assertRaises(common.RequestError):
            common.audio_bytes_with_extension("%%%not-base64%%")
        with self.assertRaises(common.RequestError):
            common.audio_bytes_with_extension(base64.b64encode(b"not audio").decode())

    def test_audio_upload_is_saved_as_validated_container(self):
        class AudioProvider(FakeProvider):
            def validate_request(inner_self, payload):
                return {"task": "transcribe", "expects_audio": True}

            def run_job(inner_self, job_id, request, input_file):
                self.assertIsNotNone(input_file)
                self.assertEqual(input_file.suffix, ".wav")
                self.assertTrue(input_file.read_bytes().startswith(b"RIFF"))
                path = inner_self.output_root / f"{job_id}.txt"
                path.write_text("test transcript\n", encoding="utf-8")
                return path, {"test": True}

        service = self.new_service(AudioProvider())
        try:
            wav = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"fmt " + b"\x00" * 16
            accepted = service.submit({"task": "transcribe", "audio_base64": base64.b64encode(wav).decode()})
            deadline = time.time() + 3
            status = service.get_job(accepted["job_id"])
            while status and status["status"] not in {"succeeded", "failed"} and time.time() < deadline:
                time.sleep(0.01)
                status = service.get_job(accepted["job_id"])
            self.assertEqual(status["status"], "succeeded")
        finally:
            service.stop()

    def test_glb_validation_requires_nonempty_mesh_accessors(self):
        with tempfile.TemporaryDirectory() as folder:
            good = Path(folder) / "good.glb"
            make_glb(good)
            result = common.validate_glb(good)
            self.assertEqual(result["positions"], [3])
            bad = Path(folder) / "bad.glb"
            bad.write_bytes(b"not a glb")
            with self.assertRaises(ValueError):
                common.validate_glb(bad)

    def test_mp4_structure_validation(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(common.shutil, "which", return_value=None):
            good = Path(folder) / "good.mp4"
            make_mp4_container(good)
            result = common.validate_mp4(good)
            self.assertEqual(result["validation"], "container-structure")
            bad = Path(folder) / "bad.mp4"
            bad.write_bytes(b"not mp4")
            with self.assertRaises(ValueError):
                common.validate_mp4(bad)

    def test_ltx_runtime_checks_only_configured_storage_target(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "tools" / "media_services" / "ltx_api.py").read_text(encoding="utf-8")
        start = source.index("    def load_runtime(self) -> None:")
        end = source.index("    def run_job(", start)
        loader = source[start:end]
        self.assertIn('storage_check("outputs"', loader)
        self.assertIn('managed_write("outputs"', loader)
        self.assertNotIn('storage_check("inputs"', loader)
        self.assertNotIn('storage_check("cache"', loader)
        self.assertNotIn('for area in ("inputs", "outputs", "cache")', loader)

    def test_runtime_and_input_storage_failures_log_private_tracebacks(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "tools" / "media_services" / "common.py").read_text(encoding="utf-8")
        self.assertIn('LOG.exception("%s runtime load failed (%s); traceback follows"', source)
        self.assertIn('LOG.exception("%s input managed-write failed (cause=%s)"', source)

    def test_http_routes_return_health_status_and_not_found(self):
        service = self.new_service()
        server = common.ReusableThreadingHTTPServer(("127.0.0.1", 0), common.build_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        local_http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with local_http.open(base + "/health", timeout=2) as response:
                body = json.loads(response.read())
                self.assertTrue(body["ready"])
            request = urllib.request.Request(base + "/v1/jobs", data=b'{"task":"test"}', headers={"Content-Type": "application/json"}, method="POST")
            with local_http.open(request, timeout=2) as response:
                accepted = json.loads(response.read())
                self.assertEqual(response.status, 202)
            with self.assertRaises(urllib.error.HTTPError) as err:
                local_http.open(base + "/v1/jobs/job_unknownunknown", timeout=2)
            self.assertEqual(err.exception.code, 404)
            self.assertIn("job_id", accepted)
        finally:
            server.shutdown()
            server.server_close()
            service.stop()
            thread.join(timeout=2)


def _null_context():
    from contextlib import nullcontext
    return nullcontext()


if __name__ == "__main__":
    unittest.main()
