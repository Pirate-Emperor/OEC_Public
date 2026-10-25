"""Offline tests for explicit, quota-gated FLUX cache preparation."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from tools import prepare_flux_cache as prep


class PrepareFluxCacheTests(unittest.TestCase):
    def test_local_snapshot_is_reused_without_storage_write(self):
        with mock.patch.object(prep, "snapshot_download", return_value="/tmp/flux-snapshot") as download, \
             mock.patch.object(prep, "storage_preflight", side_effect=AssertionError("cache hit must not preflight writes")), \
             mock.patch.object(prep, "managed_storage_operation", side_effect=AssertionError("cache hit must not write")):
            path = prep.ensure_flux_cache()
        self.assertEqual(path, Path("/tmp/flux-snapshot"))
        self.assertTrue(download.call_args.kwargs["local_files_only"])

    def test_cache_miss_fails_closed_by_default(self):
        with mock.patch.object(prep, "snapshot_download", side_effect=prep.LocalEntryNotFoundError("missing")) as download:
            with self.assertRaisesRegex(RuntimeError, "cache miss"):
                prep.ensure_flux_cache()
        self.assertEqual(download.call_count, 1)
        self.assertTrue(download.call_args.kwargs["local_files_only"])

    def test_storage_denial_never_fetches_model_files(self):
        with mock.patch.object(prep, "snapshot_download", side_effect=prep.LocalEntryNotFoundError("missing")) as download, \
             mock.patch.object(prep, "storage_preflight", return_value=(False, "fresh quota is unavailable")):
            with self.assertRaisesRegex(RuntimeError, "fresh quota is unavailable"):
                prep.ensure_flux_cache(allow_download=True)
        self.assertEqual(download.call_count, 1)

    def test_explicit_download_checks_storage_before_and_inside_managed_write(self):
        with mock.patch.object(prep, "snapshot_download", side_effect=[
            prep.LocalEntryNotFoundError("missing"), "/tmp/flux-snapshot"
        ]) as download, \
             mock.patch.object(prep, "storage_preflight", return_value=(True, "within quota")) as preflight, \
             mock.patch.object(prep, "managed_storage_operation") as managed:
            managed.return_value.__enter__.return_value = None
            managed.return_value.__exit__.return_value = False
            path = prep.ensure_flux_cache(allow_download=True)
        self.assertEqual(path, Path("/tmp/flux-snapshot"))
        self.assertEqual(preflight.call_count, 2)
        self.assertTrue(managed.called)
        self.assertEqual(download.call_count, 2)
        self.assertFalse(download.call_args.kwargs["local_files_only"])


if __name__ == "__main__":
    unittest.main()
