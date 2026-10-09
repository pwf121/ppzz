"""Static contract tests; these do not claim to measure live model invocation."""
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseContractTests(unittest.TestCase):
    def test_onboarding_rules_and_metadata_are_aligned(self) -> None:
        text = (ROOT / "references/onboarding.md").read_text(encoding="utf-8")
        for rule in ("停止/取消", "不追踪跨任务用户身份", "不要求重填", "不静默创建", "已选中Skill＋“1”"):
            self.assertIn(rule, text)
        metadata = (ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn("$amazon-listing-image-studio", metadata)
        self.assertIn("暂不生成图片", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)

    def test_new_trigger_cases_do_not_replace_old_twelve(self) -> None:
        cases = json.loads((ROOT / "evals/trigger-evals.json").read_text(encoding="utf-8"))
        self.assertEqual(len([case for case in cases if "id" not in case]), 12)
        ids = {case.get("id"): case for case in cases}
        for identity in ("ONBOARD-HELLO", "ONBOARD-DIGIT", "ONBOARD-SYMBOL", "ONBOARD-STOP",
                         "ONBOARD-INFO", "ONBOARD-RESUME"):
            self.assertTrue(ids[identity]["should_trigger"])
        self.assertFalse(ids["NO-INTERCEPT"]["should_trigger"])

    def test_optional_variants_and_collages_are_not_fixed_product_facts(self) -> None:
        text = (ROOT / "references/variants.md").read_text(encoding="utf-8")
        for rule in ("不是所有项目的必选项", "结构、尺寸、功能、配件", "先集中确认", "不新增operation枚举"):
            self.assertIn(rule, text)
        cases = json.loads((ROOT / "evals/evals.json").read_text(encoding="utf-8"))
        self.assertEqual(len(cases), 22)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))


if __name__ == "__main__":
    unittest.main()
