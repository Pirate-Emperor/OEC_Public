import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BrainLtxQueueStorageTests(unittest.TestCase):
    def test_brain_publishes_atomic_prompt_jobs_under_managed_outputs(self):
        source = (ROOT / "brain.py").read_text(encoding="utf-8")
        self.assertIn('os.path.join(SYSTEM_DIRS["outputs"], "ltx_pipeline", "jobs")', source)
        self.assertIn('os.path.join(SYSTEM_DIRS["inputs"], "jobs")', source)  # read/count legacy jobs only
        self.assertIn('managed_storage_operation(', source)
        self.assertIn('os.replace(temp_job_path, job_path)', source)
        self.assertIn('self.legacy_jobs_dir)', source)

    def test_worker_uses_same_new_queue_and_keeps_legacy_queue_readable(self):
        source = (ROOT / "worker_ltx_video.py").read_text(encoding="utf-8")
        self.assertIn('PIPELINE_ROOT = Path(SYSTEM_DIRS["outputs"]) / "ltx_pipeline"', source)
        self.assertIn('JOB_DIR = PIPELINE_ROOT / "jobs"', source)
        self.assertIn('LEGACY_JOB_DIR = Path(SYSTEM_DIRS["inputs"]) / "jobs"', source)
        self.assertIn('glob.glob(str(LEGACY_JOB_DIR / "*.json"))', source)
        self.assertIn('_managed_ltx_job_rename(target_job, active_processing_file)', source)

    def test_video_inference_is_storage_gated_before_gpu_call_and_fresh_gated_on_write(self):
        source = (ROOT / "worker_ltx_video.py").read_text(encoding="utf-8")
        body = source.split("def generate_asset(", 1)[1].split("def worker_process(", 1)[0]
        self.assertLess(body.index('storage_preflight('), body.index('video, audio = pipeline('))
        self.assertIn('require_fresh_quota=True', body)
        self.assertNotIn('require_fresh_quota=False', body)
        self.assertIn('LTX output write blocked inside managed operation', body)

    def test_temporary_conditioning_images_live_under_managed_outputs(self):
        source = (ROOT / "worker_ltx_video.py").read_text(encoding="utf-8")
        self.assertIn('AIEROS_INPUT_DIR = PIPELINE_ROOT / "inputs"', source)
        self.assertIn('with managed_storage_operation(', source)
        self.assertIn('Temporary LTX input cleanup deferred by StorageManager', source)


    def test_brain_exposes_bounded_single_use_case_orchestration(self):
        source = (Path(__file__).resolve().parents[1] / "brain.py").read_text(encoding="utf-8")
        self.assertIn('"--config"', source)
        self.assertIn('"--once"', source)
        self.assertIn('"--use-case"', source)
        self.assertIn('parser.error("--once requires --use-case")', source)
        self.assertIn('parser.error("--use-case can only be used with --once")', source)
        self.assertIn('if self.use_case_filter and use_case["id"] != self.use_case_filter:', source)
        self.assertIn('self.jobs_created += 1', source)
        self.assertIn('self.is_running = False', source)
        self.assertIn('raise SystemExit(1)', source)
        self.assertIn('config_path=args.config, once=args.once, use_case=args.use_case', source)

if __name__ == "__main__":
    unittest.main(verbosity=2)
