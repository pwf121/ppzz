from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from workspace import (  # noqa: E402
    ContractError,
    batch_plan,
    create_batch,
    create_project,
    normalize_folder_name,
    project_plan,
    validate_intake,
)


class IntakeTests(unittest.TestCase):
    def test_links_without_requirements_routes_to_brief_first(self) -> None:
        result = validate_intake(
            {
                "input_mode": "links_without_requirements",
                "marketplace": "US",
                "amazon_urls": [
                    "https://www.amazon.com/dp/B012345678",
                    "https://amazon.com/gp/product/B087654321",
                ],
            }
        )
        self.assertEqual(result["status"], "READY")
        self.assertEqual(len(result["amazon_links"]), 2)
        self.assertEqual(result["workflow_mode"], "links_without_requirements")
        self.assertEqual(result["requirements_status"], "TO_BE_GENERATED")
        self.assertEqual(result["next_gate"], "GENERATE_IMAGE_REQUIREMENTS")

    def test_links_with_requirements_routes_to_prompt_reconstruction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sheet = Path(temp_dir) / "requirements.csv"
            sheet.write_text("asset_type,image_goal\nmain,show product\n", encoding="utf-8")
            result = validate_intake(
                {
                    "input_mode": "links_with_requirements",
                    "marketplace": "US",
                    "requirements_path": str(sheet),
                    "amazon_urls": [
                        "https://www.amazon.com/dp/B012345678",
                        "https://amazon.com/gp/product/B087654321",
                    ],
                }
            )

        self.assertEqual(result["workflow_mode"], "links_with_requirements")
        self.assertEqual(result["requirements_status"], "PROVIDED")
        self.assertEqual(
            result["next_gate"], "RECONSTRUCT_PROMPTS_AND_CHECK_AMBIGUITIES"
        )
        self.assertEqual(len(result["requirements_sha256"]), 64)

    def test_legacy_links_alias_normalizes_from_sheet_presence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sheet = Path(temp_dir) / "requirements.csv"
            sheet.write_text("asset_type,image_goal\nmain,show product\n", encoding="utf-8")
            result = validate_intake(
                {
                    "input_mode": "links",
                    "marketplace": "US",
                    "requirements_path": str(sheet),
                    "amazon_urls": [
                        "https://www.amazon.com/dp/B012345678",
                        "https://amazon.com/gp/product/B087654321",
                    ],
                }
            )

        self.assertEqual(result["input_mode"], "links_with_requirements")
        self.assertEqual(result["requested_input_mode"], "links")

    def test_explicit_no_requirements_mode_rejects_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sheet = Path(temp_dir) / "requirements.csv"
            sheet.write_text("asset_type,image_goal\nmain,show product\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                validate_intake(
                    {
                        "input_mode": "links_without_requirements",
                        "marketplace": "US",
                        "requirements_path": str(sheet),
                        "amazon_urls": [
                            "https://www.amazon.com/dp/B012345678",
                            "https://amazon.com/gp/product/B087654321",
                        ],
                    }
                )

    def test_link_intake_needs_distinct_asins(self) -> None:
        with self.assertRaises(ContractError):
            validate_intake(
                {
                    "input_mode": "links_without_requirements",
                    "marketplace": "US",
                    "amazon_urls": [
                        "https://www.amazon.com/dp/B012345678",
                        "https://amazon.com/gp/product/B012345678",
                    ],
                }
            )

    def test_non_amazon_url_is_rejected(self) -> None:
        with self.assertRaises(ContractError):
            validate_intake(
                {
                    "input_mode": "links_without_requirements",
                    "marketplace": "US",
                    "amazon_urls": [
                        "https://example.com/dp/B012345678",
                        "https://amazon.com/dp/B087654321",
                    ],
                }
            )

    def test_sensitive_fields_are_rejected_without_echoing_values(self) -> None:
        secret_value = "do-not-print-this-value"
        with self.assertRaises(ContractError) as context:
            validate_intake(
                {
                    "input_mode": "links_without_requirements",
                    "marketplace": "US",
                    "api_token": secret_value,
                    "amazon_urls": [
                        "https://amazon.com/dp/B012345678",
                        "https://amazon.com/dp/B087654321",
                    ],
                }
            )
        self.assertNotIn(secret_value, str(context.exception))

    def test_sheet_requires_existing_supported_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sheet = Path(temp_dir) / "requirements.csv"
            sheet.write_text("field,value\ncategory,desk lamp\n", encoding="utf-8")
            result = validate_intake(
                {
                    "input_mode": "requirements_sheet",
                    "marketplace": "US",
                    "requirements_path": str(sheet),
                    "category_keyword": "desk lamp",
                }
            )
            self.assertEqual(result["status"], "READY")
            self.assertEqual(result["research_depth"], "light")
            self.assertEqual(result["research_target"], 3)
            self.assertEqual(result["research_max"], 5)
            self.assertEqual(len(result["requirements_sha256"]), 64)

    def test_full_research_preserves_node_confirmation_and_ten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sheet = Path(temp_dir) / "requirements.csv"
            sheet.write_text("goal\nshow product\n", encoding="utf-8")
            for extra in ({"research_depth": "full"}, {"explicit_top10": True, "research_depth": "light"}):
                result = validate_intake({"input_mode": "requirements_sheet", "marketplace": "US",
                                          "requirements_path": str(sheet), "category_keyword": "cabinet", **extra})
                self.assertEqual(result["status"], "NEEDS_CATEGORY_CONFIRMATION")
                self.assertEqual(result["research_target"], 10)
                self.assertEqual(result["research_max"], 10)

    def test_old_scope_is_not_silently_downgraded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sheet = Path(temp_dir) / "requirements.csv"
            sheet.write_text("goal\nshow product\n", encoding="utf-8")
            data = {"input_mode": "requirements_sheet", "marketplace": "US", "operation": "continue",
                    "requirements_path": str(sheet), "category_keyword": "cabinet"}
            result = validate_intake(data)
            self.assertEqual(result["status"], "NEEDS_RESEARCH_MIGRATION")
            self.assertIsNone(result["research_target"])
            result = validate_intake({**data, "next_gate": "DISCOVER_COMPARABLE_TOP_TEN"})
            self.assertEqual(result["research_depth"], "full")
            self.assertEqual(result["research_migration"], "PRESERVED_LEGACY_TOP10")

    def test_single_reference_is_explicit_and_report_edition_is_independent(self) -> None:
        for edition in ("basic", "enhanced"):
            result = validate_intake({"input_mode": "SINGLE_REFERENCE", "marketplace": "US",
                                      "amazon_urls": ["https://amazon.com/dp/B012345678"],
                                      "report_edition": edition})
            self.assertEqual(result["research_depth"], "provided")
            self.assertEqual(result["initial_gate"], "PRODUCT_UNDERSTANDING")
            self.assertIn("NO_CATEGORY_OR_SALES_INFERENCE", result["research_scope"])
        with self.assertRaises(ContractError):
            validate_intake({"input_mode": "links", "marketplace": "US",
                             "amazon_urls": ["https://amazon.com/dp/B012345678"]})

    def test_url_safety_and_marketplace_match_without_secret_echo(self) -> None:
        urls = ["https://amazon.example/dp/B012345678", "https://www.amazon.de/dp/B012345678",
                "https://secret:do-not-echo@amazon.com/dp/B012345678",
                "https://amazon.com:bad/dp/B012345678", "https://amazon.com.evil.net/dp/B012345678"]
        for url in urls:
            with self.subTest(url=url), self.assertRaises(ContractError) as error:
                validate_intake({"input_mode": "SINGLE_REFERENCE", "marketplace": "US", "amazon_urls": [url]})
            self.assertNotIn("do-not-echo", str(error.exception))
        result = validate_intake({"input_mode": "SINGLE_REFERENCE", "marketplace": "US",
                                  "amazon_urls": ["https://amazon.com/dp/B012345678?token=do-not-echo"]})
        self.assertNotIn("do-not-echo", json.dumps(result))

    def test_invalid_enum_types_are_contract_errors(self) -> None:
        base = {"input_mode": "SINGLE_REFERENCE", "marketplace": "US",
                "amazon_urls": ["https://amazon.com/dp/B012345678"]}
        for field in ("input_mode", "operation", "report_edition", "research_depth"):
            with self.subTest(field=field), self.assertRaises(ContractError):
                validate_intake({**base, field: []})


class WorkspaceTests(unittest.TestCase):
    def test_plan_does_not_create_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan = project_plan(Path(temp_dir), "台灯 主图")
            self.assertEqual(plan["normalized_name"], "台灯-主图")
            self.assertFalse(Path(plan["project_root"]).exists())

    def test_create_project_and_batch_requires_exact_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaises(ContractError):
                create_project(root, "Desk Lamp", "wrong-name")

            project = create_project(root, "Desk Lamp", "Desk-Lamp")
            project_root = Path(project["project_root"])
            self.assertTrue((project_root / "project.json").is_file())
            self.assertTrue((project_root / "generated").is_dir())

            plan = batch_plan(project_root, "第一轮")
            self.assertEqual(plan["normalized_name"], "第一轮")
            batch = create_batch(project_root, "第一轮", "第一轮")
            self.assertTrue((Path(batch["batch_root"]) / "images").is_dir())
            self.assertTrue((Path(batch["batch_root"]) / "generation-manifest.json").is_file())

    def test_collision_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            create_project(root, "demo", "demo")
            with self.assertRaises(ContractError):
                create_project(root, "demo", "demo")

    def test_reserved_windows_name_is_rejected(self) -> None:
        for name in ("CON", "CON.txt", "nul.png", "COM1.backup", "LPT9.test"):
            with self.subTest(name=name), self.assertRaises(ContractError):
                normalize_folder_name(name)


if __name__ == "__main__":
    unittest.main()
