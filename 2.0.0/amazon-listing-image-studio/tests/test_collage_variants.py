"""Regression fixtures for supporting images and optional, isolated variant exports."""
import copy
import json
import unittest

import test_export as original
from validate_export import sha256, validate


class CollageVariantTests(unittest.TestCase):
    setUp = original.ExportTests.setUp
    tearDown = original.ExportTests.tearDown

    def add_collage(self) -> None:
        self.data["supporting_assets"] = []
        self.data["assets"][0]["component_asset_ids"] = []
        for number in range(4):
            identity = f"scene-{number}"
            output = self.root / "无文案原图" / f"{identity}.png"
            output.write_bytes(self.source.read_bytes())
            self.data["assets"][0]["component_asset_ids"].append(identity)
            self.data["supporting_assets"].append({
                "asset_id": identity, "source_path": str(self.source),
                "source_sha256": sha256(self.source), "reviewed_sha256": sha256(self.source),
                "native_dimensions": [8, 8], "no_copy_path": f"无文案原图/{identity}.png",
                "visual_qa": "PASS"})

    def add_variant(self) -> None:
        master = self.root / "master.json"
        master.write_text(json.dumps({"schema": self.data["schema"],
                                     "export_root": str(self.root.parent / (self.root.name + "-master"))}),
                          encoding="utf-8")
        self.data["variant_template"] = {
            "variant_id": "blue", "approval_source": "Fixture user approval",
            "master_manifest_path": str(master), "master_manifest_sha256": sha256(master),
            "master_approval": "user_confirmed", "changed_attributes": ["color"],
            "reference_paths": [str(self.source)], "sample_visual_qa": "PASS", "copy_review": "PASS"}

    def test_four_scenes_count_as_one_formal_pair(self) -> None:
        self.add_collage()
        result = validate(self.data)
        self.assertEqual((result["status"], result["pair_count"], result["supporting_asset_count"]),
                         ("PASS", 1, 4))

    def test_missing_scene_is_rejected(self) -> None:
        self.add_collage()
        self.data["supporting_assets"].pop()
        self.assertEqual(validate(self.data)["status"], "PARTIAL")

    def test_scene_file_missing_is_rejected(self) -> None:
        self.add_collage()
        (self.root / "无文案原图/scene-0.png").unlink()
        self.assertEqual(validate(self.data)["status"], "PARTIAL")

    def test_stale_scene_review_is_rejected(self) -> None:
        self.add_collage()
        self.data["supporting_assets"][0]["reviewed_sha256"] = "0" * 64
        self.assertEqual(validate(self.data)["status"], "PARTIAL")

    def test_scene_pending_or_rejected_cannot_pass(self) -> None:
        self.add_collage()
        for field, value in (("visual_qa", "PENDING"), ("status", "REJECTED")):
            data = copy.deepcopy(self.data)
            data["supporting_assets"][0][field] = value
            self.assertEqual(validate(data)["status"], "PARTIAL")

    def test_scene_aliases_and_path_escape_rejected(self) -> None:
        self.add_collage()
        for field, value in (("asset_id", "main"), ("no_copy_path", "../scene.png"),
                             ("no_copy_path", "无文案原图/main.png")):
            data = copy.deepcopy(self.data)
            data["supporting_assets"][0][field] = value
            self.assertEqual(validate(data)["status"], "PARTIAL")

    def test_invalid_supporting_metadata_is_structured_error(self) -> None:
        for supporting in ({}, [None], [{"asset_id": []}]):
            data = copy.deepcopy(self.data)
            data["supporting_assets"] = supporting
            self.assertEqual(validate(data)["status"], "PARTIAL")

    def test_variant_is_optional_for_old_manifests(self) -> None:
        self.assertEqual(validate(self.data)["status"], "PASS")

    def test_color_and_material_variants_with_evidence_pass(self) -> None:
        self.add_variant()
        for changes in (["color"], ["material"], ["color", "material"]):
            self.data["variant_template"]["changed_attributes"] = changes
            self.assertEqual(validate(self.data)["status"], "PASS")

    def test_structural_variant_requires_new_review(self) -> None:
        self.add_variant()
        for changes in (["structure"], ["dimensions"], ["function"], []):
            self.data["variant_template"]["changed_attributes"] = changes
            self.assertEqual(validate(self.data)["status"], "PARTIAL")

    def test_variant_approval_sample_and_copy_conflicts_block(self) -> None:
        self.add_variant()
        for field in ("master_approval", "sample_visual_qa", "copy_review"):
            data = copy.deepcopy(self.data)
            data["variant_template"][field] = "PENDING"
            self.assertEqual(validate(data)["status"], "PARTIAL")

    def test_variant_master_hash_and_reference_required(self) -> None:
        self.add_variant()
        for field, value in (("master_manifest_sha256", "0" * 64), ("reference_paths", []),
                             ("reference_paths", ["missing.png"]), ("approval_source", "")):
            data = copy.deepcopy(self.data)
            data["variant_template"][field] = value
            self.assertEqual(validate(data)["status"], "PARTIAL")

    def test_variant_cannot_export_over_or_inside_master(self) -> None:
        self.add_variant()
        master = self.root / "master.json"
        for path in (self.root, self.root.parent, self.root / "nested"):
            master.write_text(json.dumps({"schema": self.data["schema"], "export_root": str(path)}),
                              encoding="utf-8")
            self.data["variant_template"]["master_manifest_sha256"] = sha256(master)
            self.assertEqual(validate(self.data)["status"], "PARTIAL")

    def test_validation_does_not_mutate_master_or_sources(self) -> None:
        self.add_collage()
        self.add_variant()
        before = {p: sha256(p) for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(validate(self.data)["status"], "PASS")
        self.assertEqual(before, {p: sha256(p) for p in before})


if __name__ == "__main__":
    unittest.main()
