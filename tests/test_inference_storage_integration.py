import ast
import unittest
from pathlib import Path


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

        self.assertIn('parser.add_argument("--gpu", type=int, default=0', source)
        self.assertIn("process_qa_queue(purge_after_load=args.purge, gpu_id=args.gpu)", source)

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
