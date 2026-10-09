"""Adversarial regressions for image bytes, review binding and export scope."""
import copy
import unittest
from unittest import mock

import test_export as original
from validate_export import sha256, validate


class ExportIntegrityTests(unittest.TestCase):
    setUp = original.ExportTests.setUp
    tearDown = original.ExportTests.tearDown

    def refresh_output_hashes(self) -> None:
        digest = sha256(self.root / "亚马逊文案图/main.png")
        self.data["assets"][0].update(with_copy_sha256=digest, reviewed_sha256=digest)

    def test_truncated_png_header_rejected_even_with_matching_hashes(self) -> None:
        output = self.root / "亚马逊文案图/main.png"
        output.write_bytes(output.read_bytes()[:24])
        self.refresh_output_hashes()
        result = validate(self.data)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertIn("integrity", result["errors"][0]["error"])

    def test_replaced_same_size_pixels_reject_stale_hashes(self) -> None:
        from PIL import Image
        Image.new("RGB", (16, 16), "black").save(self.root / "亚马逊文案图/main.png")
        result = validate(self.data)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertIn("with_copy_sha256", result["errors"][0]["error"])

    def test_updated_output_hash_does_not_reuse_old_review(self) -> None:
        from PIL import Image
        output = self.root / "亚马逊文案图/main.png"
        Image.new("RGB", (16, 16), "black").save(output)
        self.data["assets"][0]["with_copy_sha256"] = sha256(output)
        self.assertIn("reviewed_sha256", validate(self.data)["errors"][0]["error"])

    def test_every_supplied_output_hash_is_checked(self) -> None:
        self.data["assets"][0]["output_sha256"] = "0" * 64
        self.assertIn("output_sha256", validate(self.data)["errors"][0]["error"])

    def test_output_hash_alias_supported(self) -> None:
        row = self.data["assets"][0]
        row["output_sha256"] = row.pop("with_copy_sha256")
        self.assertEqual(validate(self.data)["status"], "PASS")

    def test_string_asset_row_returns_structured_error(self) -> None:
        self.data["assets"] = ["not-an-object"]
        result = validate(self.data)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["errors"][0]["asset_id"], "row_1")
        self.assertIn("must be an object", result["errors"][0]["error"])

    def test_other_invalid_asset_rows_return_structured_errors(self) -> None:
        for row in (None, [], 7, {}, {"asset_id": []}):
            with self.subTest(row=row):
                self.data["assets"] = [row]
                self.assertEqual(validate(self.data)["status"], "PARTIAL")

    def test_invalid_root_types_return_error(self) -> None:
        for root in (None, [], "bad", 7, {}):
            with self.subTest(root=root):
                self.assertEqual(validate(root)["status"], "ERROR")

    def test_invalid_root_field_types_return_error(self) -> None:
        for field, value in (("export_root", []), ("assets", {}), ("expected_assets", True),
                             ("expected_asset_ids", ["main", "main"]),
                             ("selected_asset_ids", [None])):
            data = copy.deepcopy(self.data)
            data[field] = value
            with self.subTest(field=field):
                self.assertEqual(validate(data)["status"], "ERROR")

    def test_no_pillow_is_explicit_error(self) -> None:
        with mock.patch("validate_export.Image", None):
            result = validate(self.data)
        self.assertEqual(result["status"], "ERROR")
        self.assertIn("Pillow", result["message"])

    def test_old_manifest_stays_limited(self) -> None:
        self.data.pop("expected_asset_ids")
        self.data.pop("selected_asset_ids")
        row = self.data["assets"][0]
        row.pop("with_copy_sha256")
        row.pop("reviewed_sha256")
        result = validate(self.data)
        self.assertEqual(result["status"], "PASS_WITH_LIMITS")
        self.assertEqual(result["task_scope"]["status"], "UNVERIFIED")
        self.assertEqual(result["selected_subset"]["status"], "PASS_WITH_LIMITS")

    def test_missing_review_or_output_hash_not_full_pass(self) -> None:
        for field in ("with_copy_sha256", "reviewed_sha256"):
            data = copy.deepcopy(self.data)
            data["assets"][0].pop(field)
            result = validate(data)
            with self.subTest(field=field):
                self.assertEqual(result["status"], "PARTIAL")
                self.assertEqual(result["task_scope"]["status"], "PARTIAL")
                self.assertTrue(result["limits"])

    def test_subset_pass_does_not_complete_whole_task(self) -> None:
        self.data["expected_asset_ids"] = ["main", "secondary-01"]
        result = validate(self.data)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["selected_subset"]["status"], "PASS")
        self.assertEqual(result["task_scope"]["status"], "PARTIAL")
        self.assertEqual(result["task_scope"]["missing_or_unverified_asset_ids"], ["secondary-01"])

    def test_missing_full_scope_does_not_complete_whole_task(self) -> None:
        self.data.pop("expected_asset_ids")
        result = validate(self.data)
        self.assertEqual(result["selected_subset"]["status"], "PASS")
        self.assertEqual(result["task_scope"]["status"], "UNVERIFIED")
        self.assertEqual(result["status"], "PASS_WITH_LIMITS")

    def test_selected_scope_mismatch_rejected(self) -> None:
        self.data["expected_asset_ids"] = ["main", "secondary-01"]
        self.data["selected_asset_ids"] = ["main", "secondary-01"]
        result = validate(self.data)
        self.assertEqual(result["selected_subset"]["status"], "PARTIAL")
        self.assertTrue(any("selected_asset_ids" in item["error"] for item in result["errors"]))

    def test_selected_outside_approved_scope_rejected(self) -> None:
        self.data["selected_asset_ids"] = ["unapproved"]
        self.assertEqual(validate(self.data)["status"], "ERROR")

    def test_draft_or_rejected_status_cannot_be_promoted(self) -> None:
        for field in ("status", "asset_status", "source_status"):
            for value in ("DRAFT", "REJECTED", "PENDING", "试稿", "拒收"):
                data = copy.deepcopy(self.data)
                data["assets"][0][field] = value
                with self.subTest(field=field, value=value):
                    self.assertEqual(validate(data)["status"], "PARTIAL")

    def test_visual_qa_not_pass_cannot_be_promoted(self) -> None:
        for value in ("REJECTED", "REVISION_NEEDED", "PENDING", None):
            self.data["assets"][0]["visual_qa"] = value
            with self.subTest(value=value):
                self.assertEqual(validate(self.data)["status"], "PARTIAL")

    def test_canvas_margins_do_not_imply_upscaling(self) -> None:
        row = self.data["assets"][0]
        row.update(placement_dimensions=[8, 8], scale_factor=1, upscaled=False)
        self.assertEqual(validate(self.data)["status"], "PASS")

    def test_placement_mismatch_or_stretch_rejected(self) -> None:
        for placement in ([8, 8], [16, 12], [True, 16], [16], [0, 16]):
            self.data["assets"][0]["placement_dimensions"] = placement
            with self.subTest(placement=placement):
                self.assertEqual(validate(self.data)["status"], "PARTIAL")

    def test_boolean_scale_rejected(self) -> None:
        self.data["assets"][0].update(scale_factor=True, upscaled=False)
        self.assertIn("Invalid scale_factor", validate(self.data)["errors"][0]["error"])

    def test_validation_does_not_modify_files(self) -> None:
        before = {path: sha256(path) for path in self.root.rglob("*.png")}
        self.assertEqual(validate(self.data)["status"], "PASS")
        self.assertEqual(before, {path: sha256(path) for path in before})

    def test_valid_and_truncated_jpeg_source(self) -> None:
        from PIL import Image
        source = self.root / "source.jpg"
        original_copy = self.root / "无文案原图/main.jpg"
        Image.new("RGB", (8, 8), "white").save(source)
        original_copy.write_bytes(source.read_bytes())
        row = self.data["assets"][0]
        row.update(source_path=str(source), source_sha256=sha256(source),
                   no_copy_path="无文案原图/main.jpg")
        self.assertEqual(validate(self.data)["status"], "PASS")
        source.write_bytes(source.read_bytes()[:-2])
        original_copy.write_bytes(source.read_bytes())
        row["source_sha256"] = sha256(source)
        result = validate(self.data)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertIn("integrity", result["errors"][0]["error"])


if __name__ == "__main__":
    unittest.main()
