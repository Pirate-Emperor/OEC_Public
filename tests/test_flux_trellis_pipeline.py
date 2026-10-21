"""Offline contract tests for the FLUX→TRELLIS orchestrator."""
from __future__ import annotations
import json, struct, tempfile, unittest
from pathlib import Path
import pipeline_flux_trellis as combined


class FluxTrellisPipelineTests(unittest.TestCase):
    def test_service_manager_flux_route_arguments(self):
        a=combined.build_parser().parse_args(["--work-dir","/tmp/oec-test-work","--source-mode","flux","--seed","42"])
        self.assertEqual(a.source_mode,"flux")
        self.assertEqual(a.seed,42)

    def test_service_manager_existing_images_route_arguments(self):
        a=combined.build_parser().parse_args(["--work-dir","/tmp/oec-test-work","--source-mode","images",
                                              "--image-dir","/tmp/images","--recursive"])
        self.assertEqual(a.source_mode,"images")
        self.assertTrue(a.recursive)

    def test_image_folder_is_sorted_and_empty_input_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/"b.png").write_bytes(b"b"); (root/"a.jpg").write_bytes(b"a")
            self.assertEqual([p.name for p in combined._image_files(root,False,5)],["a.jpg","b.png"])
            with self.assertRaises(ValueError):
                combined._image_files(root/"missing",False,5)

    def test_glb_structure_and_mesh_accessors_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"test.glb"
            doc={"meshes":[{"primitives":[{"attributes":{"POSITION":0},"indices":1}]}],
                 "accessors":[{"count":3},{"count":3}]}
            payload=json.dumps(doc,separators=(",",":")).encode()
            payload += b" " * ((4-len(payload)%4)%4)
            raw=b"glTF"+struct.pack("<II",2,20+len(payload))+struct.pack("<II",len(payload),0x4E4F534A)+payload
            path.write_bytes(raw)
            info=combined._inspect_glb_header(path)
            self.assertEqual(info["glb_version"],2)
            self.assertEqual(info["position_accessor_counts"],[3])
            self.assertEqual(info["index_accessor_counts"],[3])



    def test_glb_structure_rejects_wrong_declared_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"broken.glb"
            doc={"meshes":[{"primitives":[{"attributes":{"POSITION":0},"indices":1}]}],
                 "accessors":[{"count":3},{"count":3}]}
            payload=json.dumps(doc,separators=(",",":")).encode()
            payload += b" " * ((4-len(payload)%4)%4)
            actual=20+len(payload)
            # Declared file length differs from the actual bytes, even though the
            # JSON mesh/accessors otherwise look structurally plausible.
            raw=b"glTF"+struct.pack("<II",2,actual+1)+struct.pack("<II",len(payload),0x4E4F534A)+payload
            path.write_bytes(raw)
            with self.assertRaisesRegex(RuntimeError,"declared length"):
                combined._inspect_glb_header(path)

    def test_safe_work_dir_creates_nonexistent_requested_path_and_rejects_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            requested = Path(tmp) / "work"
            self.assertFalse(requested.exists())
            result = combined._safe_work_dir(requested)
            self.assertEqual(result, requested.resolve())
            self.assertTrue(result.is_dir())
            with self.assertRaisesRegex(FileExistsError, "refusing to reuse existing work directory"):
                combined._safe_work_dir(requested)

if __name__ == "__main__":
    unittest.main()
