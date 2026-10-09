"""Golden file-contract cases: pairing, source integrity and resolution claims."""
import copy
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_export import sha256, validate
from workspace import create_project, create_batch


def png_bytes(width: int, height: int) -> bytes:
    def chunk(name: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", zlib.crc32(name + payload))
    raw = (b"\x00" + b"\xff\xff\xff" * width) * height
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class ExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for folder in ("无文案原图", "亚马逊文案图"):
            (self.root / folder).mkdir()
        self.source = self.root / "source.png"
        self.source.write_bytes(png_bytes(8, 8))
        (self.root / "无文案原图/main.png").write_bytes(self.source.read_bytes())
        (self.root / "亚马逊文案图/main.png").write_bytes(png_bytes(16, 16))
        self.data = {"schema": "amazon-listing-image-studio/dual-export/v1",
                     "export_root": str(self.root), "expected_assets": 1,
                     "expected_asset_ids": ["main"], "selected_asset_ids": ["main"],
                     "assets": [{"asset_id": "main", "asset_type": "main", "source_path": str(self.source),
                                 "source_sha256": sha256(self.source), "no_copy_path": "无文案原图/main.png",
                                 "with_copy_path": "亚马逊文案图/main.png", "native_dimensions": [8, 8],
                                 "export_dimensions": [16, 16], "placement_dimensions": [16, 16],
                                 "scale_factor": 2, "upscaled": True,
                                 "with_copy_sha256": sha256(self.root / "亚马逊文案图/main.png"),
                                 "reviewed_sha256": sha256(self.root / "亚马逊文案图/main.png"),
                                 "detail_limit": "Interpolated", "resampling": "Lanczos3",
                                 "copy_applied": False, "visual_qa": "PASS"}]}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_valid_pair(self) -> None:
        self.assertEqual(validate(self.data)["status"], "PASS")

    def test_missing_copy(self) -> None:
        (self.root / "亚马逊文案图/main.png").unlink()
        self.assertEqual(validate(self.data)["status"], "PARTIAL")

    def test_reencoded_original_rejected(self) -> None:
        (self.root / "无文案原图/main.png").write_bytes(png_bytes(7, 8))
        self.assertIn("hash", validate(self.data)["errors"][0]["error"])

    def test_upscale_must_be_disclosed(self) -> None:
        self.data["assets"][0]["detail_limit"] = ""
        self.assertEqual(validate(self.data)["status"], "PARTIAL")

    def test_native_claim_must_match(self) -> None:
        self.data["assets"][0]["native_dimensions"] = [16, 16]
        self.assertEqual(validate(self.data)["status"], "PARTIAL")

    def test_duplicate_id_rejected(self) -> None:
        self.data["assets"].append(copy.deepcopy(self.data["assets"][0]))
        self.data["expected_assets"] = 2
        self.assertEqual(validate(self.data)["status"], "PARTIAL")

    def test_path_escape_rejected(self) -> None:
        self.data["assets"][0]["with_copy_path"] = "../main.png"
        self.assertIn("outside", validate(self.data)["errors"][0]["error"])

    def test_main_copy_rejected(self) -> None:
        self.data["assets"][0]["copy_applied"] = True
        self.assertEqual(validate(self.data)["status"], "PARTIAL")

    def test_png_extension_is_not_sufficient(self) -> None:
        (self.root / "亚马逊文案图/main.png").write_bytes(b"not an image")
        self.assertEqual(validate(self.data)["status"], "PARTIAL")

    def test_batch_creates_two_folders(self) -> None:
        project = create_project(self.root, "fixture", "fixture")
        batch = create_batch(Path(project["project_root"]), "round", "round")
        for folder in ("无文案原图", "亚马逊文案图"):
            self.assertTrue((Path(batch["batch_root"]) / "exports" / folder).is_dir())


if __name__ == "__main__":
    unittest.main()
