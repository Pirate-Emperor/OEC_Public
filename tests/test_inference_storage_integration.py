import ast
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class InferenceStorageIntegrationTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def _read(self, filename):
        return (self.ROOT / filename).read_text(encoding="utf-8")

    def _tree(self, filename):
        return ast.parse(self._read(filename), filename=filename)

    def test_ltx_worker_has_no_runtime_package_install_or_clone(self):
        source = self._read("worker_ltx_video.py")
        self.assertNotIn("pip install", source)
        self.assertNotIn("subprocess.run([sys.executable, \"-m\", \"pip\"", source)
        self.assertNotIn("git clone", source)
        self.assertNotIn("release_reserve", source)
        self.assertIn("managed_storage_operation", source)
        self.assertIn("estimate_hf_repo_bytes", source)
        self.assertIn("AIEROS_LTX_REPO_DIR", source)

    def test_ltx_worker_enforces_model_and_output_storage(self):
        source = self._read("worker_ltx_video.py")
        self.assertIn('with managed_storage_operation(\n            "models"', source)
        self.assertIn('with managed_storage_operation(\n                "outputs"', source)
        tree = self._tree("worker_ltx_video.py")
        functions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertIn("_estimate_ltx_model_download_gb", functions)
        self.assertIn("_estimate_output_gb", functions)


    def test_qa_sets_physical_gpu_before_torch_import(self):
        source = self._read("qa_compliance_worker.py")
        tree = ast.parse(source, filename="qa_compliance_worker.py")

        top_level_torch_imports = [
            node for node in tree.body
            if isinstance(node, ast.Import)
            and any(alias.name == "torch" for alias in node.names)
        ]
        self.assertEqual(top_level_torch_imports, [], "Torch must not initialize before QA selects its GPU")

        qa_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "QANode"
        )
        ctor = next(
            node for node in qa_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        visibility_index = next(
            i for i, node in enumerate(ctor.body)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Attribute)
                and isinstance(target.value.value, ast.Name)
                and target.value.value.id == "os"
                and target.value.attr == "environ"
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == "CUDA_VISIBLE_DEVICES"
                for target in node.targets
            )
        )
        torch_import_index = next(
            i for i, node in enumerate(ctor.body)
            if isinstance(node, ast.Import)
            and any(alias.name == "torch" for alias in node.names)
        )
        self.assertLess(visibility_index, torch_import_index)

        # qwen-vl-utils can import Torch transitively; defer it until after
        # CUDA_VISIBLE_DEVICES has been applied as well.
        top_level_qwen_imports = [
            node for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "qwen_vl_utils"
        ]
        self.assertEqual(top_level_qwen_imports, [])
        qwen_import_index = next(
            i for i, node in enumerate(ctor.body)
            if isinstance(node, ast.Try)
            and any(
                isinstance(child, ast.ImportFrom) and child.module == "qwen_vl_utils"
                for child in ast.walk(node)
            )
        )
        self.assertLess(torch_import_index, qwen_import_index)

        self.assertIn('parser.add_argument("--gpu", type=int, default=0', source)
        self.assertIn('parser.add_argument("--once", action="store_true"', source)
        self.assertIn('parser.add_argument("--asset-id", type=int', source)
        self.assertIn("process_qa_queue(\n                purge_after_load=args.purge, gpu_id=args.gpu, asset_id=args.asset_id, once=True", source)

    def test_qa_one_shot_filters_exact_id_and_skips_global_recovery_sweep(self):
        source = self._read("qa_compliance_worker.py")
        tree = ast.parse(source, filename="qa_compliance_worker.py")
        queue_fn = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "process_qa_queue"
        )
        bounded_sweep_guards = [
            node for node in ast.walk(queue_fn)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.UnaryOp)
            and isinstance(node.test.op, ast.Not)
            and isinstance(node.test.operand, ast.Name)
            and node.test.operand.id == "once"
            and any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "sweep_stuck_jobs"
                for child in ast.walk(node)
            )
        ]
        self.assertTrue(bounded_sweep_guards, "targeted QA must skip sweeping unrelated PROCESSING_QA rows")
        self.assertIn("WHERE id = ? AND status = 'PENDING_QA' LIMIT 1", source)
        self.assertIn("WHERE id = ? AND status = 'PROCESSING_QA'", source)
        self.assertIn('with managed_storage_operation(\n                "outputs", required_gb=0.001, require_fresh_quota=True', source)
        self.assertIn('parser.error("--once requires --asset-id with a positive ID")', source)
        self.assertIn('parser.error("--asset-id can only be used with --once")', source)

    def test_qa_frame_extraction_preserves_webm_and_avi_inputs(self):
        source = self._read("qa_compliance_worker.py")
        tree = ast.parse(source, filename="qa_compliance_worker.py")
        qa_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "QANode"
        )
        extractor = next(
            node for node in qa_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "extract_evaluation_frame"
        )
        # Execute only the small method in isolation, avoiding core_config, Torch,
        # model loading, and all shared OEC directories.
        module = ast.Module(body=[extractor], type_ignores=[])
        ast.fix_missing_locations(module)
        namespace = {"Path": Path, "subprocess": subprocess}
        exec(compile(module, "qa_compliance_worker.py", "exec"), namespace)
        extract = namespace["extract_evaluation_frame"]

        for suffix in (".mp4", ".webm", ".avi"):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as temp:
                video = Path(temp) / f"source{suffix}"
                original = b"original-video-bytes"
                video.write_bytes(original)
                calls = []

                def fake_ffmpeg(command, **kwargs):
                    calls.append(command)
                    Path(command[-1]).write_bytes(b"jpeg-frame")
                    return None

                with mock.patch("subprocess.run", side_effect=fake_ffmpeg):
                    frame, extracted = extract(object(), str(video))

                self.assertTrue(extracted)
                self.assertEqual(frame, str(video.with_name("source_qa_frame.jpg")))
                self.assertNotEqual(Path(frame), video)
                self.assertEqual(video.read_bytes(), original)
                self.assertEqual(Path(frame).read_bytes(), b"jpeg-frame")
                self.assertEqual(calls[0][-1], frame)

    def test_qa_video_transcode_requires_fresh_storage_admission(self):
        source = self._read("qa_compliance_worker.py")
        start = source.index("    def improve_and_standardize_video")
        end = source.index("\ndef sweep_stuck_jobs", start)
        transcode = source[start:end]
        self.assertIn('with managed_storage_operation(', transcode)
        self.assertIn('require_fresh_quota=True', transcode)
        self.assertNotIn('require_fresh_quota=False', transcode)

    def test_qa_worker_enforces_storage_for_model_and_transcode(self):
        source = self._read("qa_compliance_worker.py")
        self.assertNotIn("release_reserve", source)
        self.assertIn("managed_storage_operation", source)
        self.assertIn("estimate_hf_repo_bytes", source)
        tree = self._tree("qa_compliance_worker.py")
        function_names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertIn("_ensure_downloaded_robustly", function_names)
        self.assertIn("improve_and_standardize_video", function_names)

if __name__ == "__main__":
    unittest.main()
