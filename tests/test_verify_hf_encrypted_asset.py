import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.verify_hf_encrypted_asset import assemble_chunks_to_file, safe_remote_path

class EncryptedHfAssetVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.part1, self.part2 = b"ciphertext-part-one", b"ciphertext-part-two"
        self.payload = self.part1 + self.part2
        self.p1, self.p2 = self.root / "part1", self.root / "part2"
        self.p1.write_bytes(self.part1); self.p2.write_bytes(self.part2)
        self.manifest = {
            "protocol":"oec-asset-chunks-v1", "status":"complete",
            "asset_bytes":len(self.payload), "asset_sha256":hashlib.sha256(self.payload).hexdigest(),
            "parts":[
                {"index":0,"offset_bytes":0,"path":"data/chunks/demo/part-000000.bin",
                 "size_bytes":len(self.part1),"sha256":hashlib.sha256(self.part1).hexdigest()},
                {"index":1,"offset_bytes":len(self.part1),"path":"data/chunks/demo/part-000001.bin",
                 "size_bytes":len(self.part2),"sha256":hashlib.sha256(self.part2).hexdigest()},
            ]}
        self.chunks = {self.manifest["parts"][0]["path"]:self.p1,
                       self.manifest["parts"][1]["path"]:self.p2}
    def tearDown(self):
        self.temp.cleanup()
    def test_assembles_ordered_ciphertext_and_verifies_hash(self):
        output = self.root / "assembled"
        result = assemble_chunks_to_file(self.manifest, self.chunks, output)
        self.assertEqual(output.read_bytes(), self.payload)
        self.assertEqual(result["sha256"], hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(result["parts_verified"], 2)
    def test_missing_part_fails(self):
        with self.assertRaisesRegex(ValueError, "missing/non-regular"):
            assemble_chunks_to_file(self.manifest, {next(iter(self.chunks)):self.p1}, self.root / "missing-out")
    def test_wrong_part_hash_fails(self):
        altered = self.root / "altered"; altered.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "size/SHA-256 mismatch"):
            assemble_chunks_to_file(self.manifest, {**self.chunks,self.manifest["parts"][0]["path"]:altered}, self.root / "bad-out")
    def test_bad_offset_fails(self):
        bad = {**self.manifest,"parts":[dict(p) for p in self.manifest["parts"]]}
        bad["parts"][1]["offset_bytes"] += 1
        with self.assertRaisesRegex(ValueError, "non-contiguous"):
            assemble_chunks_to_file(bad, self.chunks, self.root / "bad-offset-out")
    def test_incomplete_manifest_fails(self):
        bad = {**self.manifest,"status":"uploading"}
        with self.assertRaisesRegex(ValueError, "must be complete"):
            assemble_chunks_to_file(bad, self.chunks, self.root / "incomplete-out")
    def test_remote_path_traversal_is_rejected(self):
        for value in ("../escape","/absolute","data/../../secret","data\\secret"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                safe_remote_path(value)

if __name__ == "__main__":
    unittest.main()
