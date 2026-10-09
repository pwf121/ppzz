from __future__ import annotations

import json
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


class RequirementSamplePolicyTests(unittest.TestCase):
    def test_requirement_mode_uses_comparable_top_ten(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        data_contract = (SKILL_ROOT / "references" / "data-contract.md").read_text(
            encoding="utf-8"
        )
        visual_playbook = (SKILL_ROOT / "references" / "visual-playbook.md").read_text(
            encoding="utf-8"
        )

        combined = "\n".join((skill_text, data_contract, visual_playbook))
        self.assertIn("同类/相似产品 Top 10", combined)
        self.assertIn("PARTIAL_MARKET_SET (n/10)", combined)
        self.assertNotIn("Top 100", combined)
        self.assertNotIn("前 100", combined)

    def test_trigger_eval_covers_comparable_top_ten(self) -> None:
        evals = json.loads(
            (SKILL_ROOT / "evals" / "trigger-evals.json").read_text(encoding="utf-8")
        )
        matching = [case for case in evals if "相同或类似产品前 10 名" in case["query"]]
        self.assertEqual(len(matching), 1)
        self.assertTrue(matching[0]["should_trigger"])
        self.assertIn("PARTIAL_MARKET_SET (n/10)", matching[0]["expected_behavior"])

    def test_quality_evals_cover_top_ten_and_regression(self) -> None:
        evals = json.loads(
            (SKILL_ROOT / "evals" / "evals.json").read_text(encoding="utf-8")
        )
        case_ids = {case["id"] for case in evals}
        self.assertGreaterEqual(len(evals), 5)
        self.assertIn("REQ-TOP10-002", case_ids)
        self.assertIn("REQ-TOP10-003", case_ids)
        self.assertIn("LINKS-REGRESSION-001", case_ids)

    def test_typography_roles_are_locked_across_secondary_images(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        visual_playbook = (SKILL_ROOT / "references" / "visual-playbook.md").read_text(
            encoding="utf-8"
        )
        combined = "\n".join((skill_text, visual_playbook))

        self.assertIn("typography_role_map", combined)
        self.assertIn("A/B/C 是角色占位符", combined)
        self.assertIn("不允许逐图替换字体", combined)
        self.assertIn("not_applicable", combined)

    def test_quality_evals_cover_typography_positive_and_negative_cases(self) -> None:
        evals = json.loads(
            (SKILL_ROOT / "evals" / "evals.json").read_text(encoding="utf-8")
        )
        cases = {case["id"]: case for case in evals}

        self.assertIn("TYPOGRAPHY-CONSISTENCY-001", cases)
        self.assertIn("TYPOGRAPHY-CONSISTENCY-002", cases)
        self.assertIn(
            "所有副图中同一文案角色必须保持同一字体身份（家族、样式、字重）",
            cases["TYPOGRAPHY-CONSISTENCY-001"]["expected"],
        )
        # User-approved semantics distinguish authorized exceptions from agent-invented changes.
        self.assertIn("TYPOGRAPHY-NO-AUTH", cases)
        self.assertIn("TYPOGRAPHY-MISSING-QA", cases)
        self.assertIn("尊重用户明确的第2和第5张字体例外，只改授权图位，不强迫其余图统一替换",
                      cases["TYPOGRAPHY-CONSISTENCY-002"]["expected"])
        self.assertIn("不自行制造字体例外，继续使用批次映射",
                      cases["TYPOGRAPHY-NO-AUTH"]["expected"])

    def test_skill_defines_three_mutually_exclusive_modes(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        data_contract = (SKILL_ROOT / "references" / "data-contract.md").read_text(
            encoding="utf-8"
        )
        combined = "\n".join((skill_text, data_contract))

        self.assertIn("三个互斥入口", skill_text)
        self.assertIn("links_without_requirements", combined)
        self.assertIn("links_with_requirements", combined)
        self.assertIn("requirements_sheet", combined)
        self.assertIn("REQUIREMENTS_CONFIRMATION_REQUIRED", combined)
        self.assertIn("NEEDS_USER_CONFIRMATION", combined)

    def test_generated_requirements_cover_main_scene_and_selling_point(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        visual_playbook = (SKILL_ROOT / "references" / "visual-playbook.md").read_text(
            encoding="utf-8"
        )
        combined = "\n".join((skill_text, visual_playbook))

        for field in (
            "display_effect",
            "scene_name",
            "space_type",
            "space_expression",
            "selling_point",
            "visual_evidence",
            "fact_source",
        ):
            self.assertIn(field, combined)

    def test_quality_evals_cover_all_three_modes(self) -> None:
        evals = json.loads(
            (SKILL_ROOT / "evals" / "evals.json").read_text(encoding="utf-8")
        )
        case_ids = {case["id"] for case in evals}

        self.assertIn("LINKS-NO-REQUIREMENTS-001", case_ids)
        self.assertIn("LINKS-WITH-REQUIREMENTS-001", case_ids)
        self.assertIn("REQUIREMENTS-ONLY-001", case_ids)


if __name__ == "__main__":
    unittest.main()
