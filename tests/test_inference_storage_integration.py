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
