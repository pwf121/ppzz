from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
from workspace import ContractError, file_sha256
from workflow import resume_plan


class RecoveryTests(unittest.TestCase):
    """Synthetic dependency tests, not real image generation or visual QA."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "project.json").write_text(json.dumps({"project_root": str(self.root)}), encoding="utf-8")
        self.source = self.root / "product.txt"
        self.source.write_bytes(b"anonymous product evidence fixture")
        self.output = self.root / "output.txt"
        self.output.write_bytes(b"anonymous output fixture - not an image")
        fingerprints = {"source_hash": file_sha256(self.source), "fact_revision": "f1",
                        "requirements_revision": "r1", "prompt_hash": "p1",
                        "font_revision": "font1", "copy_hash": "copy1"}
        self.asset = {"asset_id": "listing-01", "status": "passed", "stage": "reviewed",
                      "required_facts": ["door_count"], "source_path": str(self.source),
                      "fingerprints": fingerprints, "current_fingerprints": dict(fingerprints),
                      "output_path": str(self.output), "output_sha256": file_sha256(self.output),
                      "reviewed_sha256": file_sha256(self.output), "base_path": str(self.output),
                      "base_sha256": file_sha256(self.output), "base_reviewed_sha256": file_sha256(self.output)}
        self.data = {"operation": "continue", "project_root": str(self.root),
                     "expected_asset_ids": ["listing-01"], "selected_asset_ids": ["listing-01"],
                     "product_review": {"status": "passed", "family": "cabinet", "fact_revision": "f1",
                                        "confirmed_facts": ["door_count"], "unknown_facts": []},
                     "assets": [self.asset]}

    def action(self) -> str:
        return resume_plan(self.data)["assets"][0]["action"]

    def test_same_inputs_skip_without_writes(self) -> None:
        before = {str(path): file_sha256(path) for path in self.root.iterdir()}
        result = resume_plan(self.data)
        self.assertEqual(result["assets"][0]["action"], "skip")
        self.assertEqual(result["mutations"], 0)
        self.assertEqual(before, {str(path): file_sha256(path) for path in self.root.iterdir()})

    def test_copy_only_export_does_not_research_or_generate(self) -> None:
        self.data["operation"] = "export"
        result = resume_plan(self.data)
        self.assertEqual(result["assets"][0]["action"], "copy_only")
        self.assertEqual(result["research_actions"], [])
        self.assertFalse(result["generation_executed"])

    def test_copy_or_font_change_only_relayouts(self) -> None:
        for field in ("copy_hash", "font_revision"):
            with self.subTest(field=field):
                self.asset["current_fingerprints"][field] += "-new"
                self.assertEqual(self.action(), "layout")

    def test_layout_requires_reviewed_base_bytes(self) -> None:
        self.asset["current_fingerprints"]["copy_hash"] = "copy2"
        del self.asset["base_reviewed_sha256"]
        self.assertEqual(self.action(), "needs_review")

    def test_changed_prompt_regenerates_only_selected_asset(self) -> None:
        other = copy.deepcopy(self.asset)
        other["asset_id"] = "listing-02"
        self.data["assets"].append(other)
        self.data["expected_asset_ids"].append("listing-02")
        self.data["selected_asset_ids"] = ["listing-01", "listing-02"]
        self.asset["current_fingerprints"]["prompt_hash"] = "p2"
        self.assertEqual([item["action"] for item in resume_plan(self.data)["assets"]], ["generate", "skip"])

    def test_changed_fact_requires_current_product_review(self) -> None:
        self.asset["current_fingerprints"]["fact_revision"] = "f2"
        self.assertEqual(self.action(), "needs_review")
        self.data["product_review"]["fact_revision"] = "f2"
        self.assertEqual(self.action(), "generate")

    def test_source_bytes_changed_without_manifest_update_blocked(self) -> None:
        self.source.write_bytes(b"new actual source")
        self.assertEqual(self.action(), "needs_review")
        self.asset["current_fingerprints"]["source_hash"] = file_sha256(self.source)
        self.assertEqual(self.action(), "generate")

    def test_output_bytes_changed_even_same_filename_blocked(self) -> None:
        self.output.write_bytes(b"different output")
        self.assertEqual(self.action(), "needs_review")

    def test_review_hash_must_match_actual_output(self) -> None:
        self.asset["reviewed_sha256"] = "0" * 64
        self.assertEqual(self.action(), "needs_review")

    def test_missing_output_is_not_skipped(self) -> None:
        self.output.unlink()
        self.assertEqual(self.action(), "needs_review")

    def test_missing_dependencies_need_review(self) -> None:
        del self.asset["current_fingerprints"]["font_revision"]
        self.assertEqual(self.action(), "needs_review")

    def test_requirements_change_needs_scope_review(self) -> None:
        self.asset["current_fingerprints"]["requirements_revision"] = "r2"
        self.assertEqual(self.action(), "needs_review")

    def test_trial_and_rejected_are_not_promoted_by_export(self) -> None:
        self.data["operation"] = "export"
        for state in ("trial", "rejected", "pending"):
            self.asset["status"] = state
            self.assertEqual(self.action(), "needs_review")
            self.assertEqual(self.asset["status"], state)

    def test_retry_budget_pauses_only_bad_asset(self) -> None:
        other = copy.deepcopy(self.asset)
        other["asset_id"] = "listing-02"
        self.data["assets"].append(other)
        self.data["expected_asset_ids"].append("listing-02")
        self.data["selected_asset_ids"] = ["listing-01", "listing-02"]
        for kind in ("structure", "critical_material"):
            self.asset.update({"status": "rejected", "consecutive_failures": 2, "failure_kind": kind})
            self.assertEqual([item["action"] for item in resume_plan(self.data)["assets"]], ["paused", "skip"])

    def test_unknown_cabinet_and_sofa_features_block_dependent_images(self) -> None:
        for family, fact in (("cabinet", "hinge_type"), ("sofa", "chaise_orientation"), ("sofa", "recliner_mode")):
            with self.subTest(family=family, fact=fact):
                self.data["product_review"].update({"family": family, "unknown_facts": [fact]})
                self.asset["required_facts"] = [fact]
                self.assertEqual(self.action(), "needs_review")

    def test_selected_subset_never_claims_full_completion(self) -> None:
        self.data["expected_asset_ids"].append("listing-02")
        result = resume_plan(self.data)
        self.assertEqual(result["expected_count"], 2)
        self.assertEqual(result["selected_count"], 1)
        self.assertFalse(result["full_scope_verified"])

    def test_missing_asset_record_is_explicit(self) -> None:
        self.data["assets"] = []
        self.assertEqual(self.action(), "needs_review")

    def test_invalid_types_and_unowned_ids_fail_cleanly(self) -> None:
        for field, value in (("assets", ["bad"]), ("selected_asset_ids", ["unknown"]),
                             ("selected_asset_ids", "listing-01"), ("operation", []), ("copy_only", "true")):
            with self.subTest(field=field), self.assertRaises(ContractError):
                resume_plan({**self.data, field: value})
        self.asset["failure_kind"] = []
        with self.assertRaises(ContractError):
            resume_plan(self.data)

    def test_untrusted_output_path_cannot_escape_project(self) -> None:
        self.asset["output_path"] = str(self.root.parent / "outside.txt")
        with self.assertRaises(ContractError):
            resume_plan(self.data)

    def test_project_identity_mismatch_is_blocked(self) -> None:
        (self.root / "project.json").write_text(json.dumps({"project_root": str(self.root.parent)}), encoding="utf-8")
        with self.assertRaises(ContractError):
            resume_plan(self.data)


if __name__ == "__main__":
    unittest.main()
