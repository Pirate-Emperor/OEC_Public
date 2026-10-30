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
        self.assertNotIn(r'\${GITHUB_TOKEN', script)
        self.assertIn('SOURCE_REPOSITORY="${OEC_SOURCE_REPOSITORY:-${GITHUB_REPOSITORY:-}}"', script)
        self.assertIn('[[ "$SOURCE_REPOSITORY" == "xflexwork/OEC" ]]', script)
        self.assertIn("refs/remotes/oec-sync/$EXPECTED_BRANCH", script)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", workflow)
        self.assertIn("OEC_SOURCE_REPOSITORY: ${{ github.repository }}", workflow)
        self.assertNotIn(r'GITHUB_TOKEN: \${{ github.token }}', workflow)
        self.assertIn("tr -d '\\n'", script)

    def test_root_sync_uses_oec_core_runners(self):
        root_sync = (ROOT / ".github" / "workflows" / "oec-root-sync.yml").read_text(encoding="utf-8")
        model_acceptance = (ROOT / ".github" / "workflows" / "oec-demo-notebook-acceptance.yml").read_text(encoding="utf-8")
        self.assertIn("a100, oec-2]", root_sync)
        self.assertIn('test "$RUNNER_NAME" = "oec-2"', root_sync)
        self.assertIn("a100, oec-1]", model_acceptance)
        self.assertIn('test "$RUNNER_NAME" = "oec-1"', model_acceptance)
        self.assertNotIn("oec-train", root_sync)

    def test_deadline_watchdog_tolerates_force_cancel_conflict(self):
        workflow = (ROOT / ".github" / "workflows" / "oec-root-sync.yml").read_text(encoding="utf-8")
        self.assertGreaterEqual(workflow.count('method="POST", allow_conflict=True)'), 2)
        self.assertIn("OEC_DEADLINE_FORCE_CANCEL_CONFLICT_TERMINAL", workflow)
        self.assertIn("OEC_DEADLINE_FORCE_CANCEL_CONFLICT_ACTIVE", workflow)
        self.assertIn("action=leave_for_checkout_guard", workflow)

    def test_storage_guard_workflow_uses_oec_core_runner(self):
        workflow = (ROOT / ".github" / "workflows" / "storage-admission-guard-tests.yml").read_text(encoding="utf-8")
        self.assertIn("runs-on: [self-hosted, linux, x64, gpu, a100, oec-2]", workflow)
        self.assertIn('test "$RUNNER_NAME" = "oec-2"', workflow)
        self.assertIn('test "$GITHUB_REPOSITORY" = "xflexwork/OEC"', workflow)
        self.assertNotIn("a100, oec-train]", workflow)

    def test_runner_identity_accepts_verified_pre_transfer_repo_slug(self):
        root_sync = (ROOT / ".github" / "workflows" / "oec-root-sync.yml").read_text(encoding="utf-8")
        audit = root_sync.split("  core-runner-identity-audit:", 1)[1].split("  canonical-root-sync:", 1)[0]
        script = (ROOT / "tools" / "reconcile_a100_oec_root.sh").read_text(encoding="utf-8")
        self.assertIn('"Killer4K-N/OEC"', audit)
        self.assertIn("legacy_transfer_alias", audit)
        self.assertIn('GITHUB_REPOSITORY', audit)
        self.assertIn("Killer4K-N/OEC.git", script)
        self.assertIn("xflexwork/OEC.git", script)
        self.assertIn('[[ "$SOURCE_REPOSITORY" == "xflexwork/OEC" ]]', script)

if __name__ == "__main__":
    unittest.main()
