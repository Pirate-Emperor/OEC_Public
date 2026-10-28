"""Static contract tests for A100 sync target, ephemeral authentication, and runner selection."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class A100RootSyncContractTests(unittest.TestCase):
    def test_sync_uses_explicit_feature_repository_and_ephemeral_token(self):
        script = (ROOT / "tools" / "reconcile_a100_oec_root.sh").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "oec-root-sync.yml").read_text(encoding="utf-8")
        self.assertIn('if [[ -n "${GITHUB_TOKEN:-}" ]]; then', script)
        self.assertNotIn('\\${GITHUB_TOKEN', script)
        self.assertIn('SOURCE_REPOSITORY="${OEC_SOURCE_REPOSITORY:-${GITHUB_REPOSITORY:-}}"', script)
        self.assertIn('[[ "$SOURCE_REPOSITORY" == "xflexwork/OEC" ]]', script)
        self.assertIn("refs/remotes/oec-sync/$EXPECTED_BRANCH", script)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", workflow)
        self.assertIn("OEC_SOURCE_REPOSITORY: ${{ github.repository }}", workflow)
        self.assertNotIn('GITHUB_TOKEN: \\${{ github.token }}', workflow)
        self.assertIn("tr -d '\\n'", script)

    def test_model_and_sync_workflows_use_named_oec_train_runners(self):
        root_sync = (ROOT / ".github" / "workflows" / "oec-root-sync.yml").read_text(encoding="utf-8")
        model_acceptance = (ROOT / ".github" / "workflows" / "oec-demo-notebook-acceptance.yml").read_text(encoding="utf-8")
        self.assertIn("a100, oec-train-2]", root_sync)
        self.assertIn('test "$RUNNER_NAME" = "oec-train-2"', root_sync)
        self.assertIn("a100, oec-train]", model_acceptance)
        self.assertIn('test "$RUNNER_NAME" = "oec-train"', model_acceptance)

if __name__ == "__main__":
    unittest.main()
