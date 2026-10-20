"""Contract checks for the guarded live QA-to-HF acceptance harness.

These tests inspect the orchestration source without importing core_config or
touching the configured shared output/model directories.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OecE2EAcceptanceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "tools" / "run_oec_e2e_acceptance.py").read_text(encoding="utf-8")

    def test_gpu_gate_refuses_unowned_compute_processes(self):
        self.assertIn('expected_runner = os.environ.get("OEC_EXPECTED_RUNNER", "oec-1")', self.source)
        self.assertIn("if runner != expected_runner:", self.source)
        self.assertIn("nvidia-smi", self.source)
        self.assertIn("active_compute", self.source)
        self.assertIn("refusing overlap", self.source)
        self.assertIn("free_mib", self.source)

    def test_runner_override_does_not_disable_gpu_process_ownership_gate(self):
        self.assertIn('expected_runner = os.environ.get("OEC_EXPECTED_RUNNER", "oec-1")', self.source)
        self.assertIn("if runner != expected_runner:", self.source)
        self.assertIn("active_compute = [line.strip() for line in process_check.stdout.splitlines() if line.strip()]", self.source)
        self.assertIn("if active_compute:", self.source)
        self.assertIn("no A100 has at least 30 GiB free VRAM", self.source)

    def test_upload_target_requires_auth_and_existing_dataset(self):
        self.assertIn("api.whoami()", self.source)
        self.assertIn("api.repo_exists(repo_id=repo, repo_type=\"dataset\")", self.source)
        self.assertIn("no repository will be created", self.source)
        self.assertIn("YourHFUsername", self.source)

    def test_qa_uses_only_run_scoped_db_and_selected_asset(self):
        self.assertIn("create_run_scoped_queue(run_db, asset_path, metadata_path)", self.source)
        self.assertIn('"--db-path", str(run_db)', self.source)
        self.assertIn('"--once", "--asset-id", str(asset_id)', self.source)
        self.assertIn('row[0] != "PENDING_UPLOAD"', self.source)
        self.assertIn('passed_metadata.get("qa_passed") is not True', self.source)

    def test_upload_is_chunked_opt_in_and_not_continuous_daemon(self):
        self.assertIn("uploader.QUEUE_DB_PATH = str(run_db)", self.source)
        self.assertIn("cleanup_on_start=False, create_repo_if_missing=False", self.source)
        self.assertIn("daemon.process_queue(max_batches=1, asset_id=asset_id, chunk_oversize=True)", self.source)
        self.assertNotIn("daemon.process_queue()", self.source)
        self.assertNotIn("generate_dummy", self.source.lower())

    def test_qa_runs_in_existing_runtime_with_cache_only_and_run_scoped_db(self):
        self.assertIn("OEC_QA_PYTHON", self.source)
        self.assertIn('Conda" / "envs" / "phase1_ltx" / "bin" / "python', self.source)
        self.assertIn('"OEC_QA_CACHE_ONLY": "1"', self.source)
        self.assertIn('"HF_HUB_OFFLINE": "1"', self.source)
        self.assertIn('"--db-path", str(run_db)', self.source)
        self.assertIn("qa_compliance_worker.py", self.source)
        self.assertNotIn("import qa_compliance_worker as qa_worker", self.source)
        self.assertIn("qa_process.returncode == 0", self.source)
        self.assertIn("[QA_ONCE] PASS asset_id=", self.source)

    def test_remote_readback_reassembles_and_verifies_hashes(self):
        self.assertIn("manifest.json", self.source)
        self.assertIn("oec-asset-chunks-v1", self.source)
        self.assertIn("assembled_asset_sha256", self.source)
        self.assertIn("remote part size/hash mismatch", self.source)
        self.assertIn("remote metadata JSON hash differs", self.source)

    def test_failure_report_and_safety_flags_are_retained(self):
        self.assertIn('"shared_queue_used": False', self.source)
        self.assertIn('"remote_dataset_created": False', self.source)
        self.assertIn('"process_kill_attempted": False', self.source)
        self.assertIn('write_json(report_root / "pipeline-report.json", report)', self.source)
        self.assertIn("GateBlocked", self.source)


if __name__ == "__main__":
    unittest.main()
