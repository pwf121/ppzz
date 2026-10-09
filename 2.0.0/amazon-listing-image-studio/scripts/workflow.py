#!/usr/bin/env python3
"""Read-only asset recovery planner; never generates, edits, copies, or promotes files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from workspace import ContractError, OPERATIONS, file_sha256, find_sensitive_keys, load_json


FINGERPRINTS = (
    "source_hash", "fact_revision", "requirements_revision", "prompt_hash",
    "font_revision", "copy_hash",
)
GENERATIVE_KEYS = {"source_hash", "fact_revision", "prompt_hash"}
STATUSES = {"pending", "trial", "rejected", "passed"}
STAGES = {"pending", "generated", "layout", "reviewed"}
HASH_RE = re.compile(r"^[a-fA-F0-9]{64}$")


def string_list(value: Any, field: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ContractError(f"{field} must be a list of nonempty strings")
    if len(value) != len(set(value)) or (nonempty and not value):
        raise ContractError(f"{field} must be unique and cannot be empty when required")
    return value


def fingerprint_map(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ContractError(f"{field} must be an object")
    if any(key not in FINGERPRINTS for key in value):
        raise ContractError(f"{field} contains unsupported dependency keys")
    if any(not isinstance(item, str) or not item.strip() for item in value.values()):
        raise ContractError(f"{field} values must be nonempty strings")
    if "source_hash" in value and not HASH_RE.fullmatch(value["source_hash"]):
        raise ContractError(f"{field}.source_hash must be SHA-256")
    return value


def file_state(root: Path, raw_path: Any, expected_hash: Any, *, inside: bool) -> str:
    """Resolve exact paths; output files may not escape the verified project."""
    if raw_path is None or expected_hash is None:
        return "MISSING_EVIDENCE"
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ContractError("File paths must be nonempty strings")
    if not isinstance(expected_hash, str) or not HASH_RE.fullmatch(expected_hash):
        raise ContractError("File fingerprints must be SHA-256")
    path = Path(raw_path)
    path = (path if path.is_absolute() else root / path).resolve()
    if inside and not path.is_relative_to(root):
        raise ContractError("Asset output path must stay inside the verified project")
    if not path.is_file():
        return "MISSING_FILE"
    try:
        return "MATCH" if file_sha256(path).lower() == expected_hash.lower() else "CHANGED_BYTES"
    except OSError:
        return "UNREADABLE_FILE"


def asset_plan(root: Path, operation: str, asset: dict[str, Any], product: dict[str, Any]) -> dict[str, Any]:
    asset_id = asset["asset_id"]
    result: dict[str, Any] = {"asset_id": asset_id, "action": "needs_review", "reason": ""}

    def decision(action: str, reason: str) -> dict[str, Any]:
        return {**result, "action": action, "reason": reason}

    state = asset.get("status", "pending")
    stage = asset.get("stage", "pending")
    if not isinstance(state, str) or state not in STATUSES:
        raise ContractError("Asset status must be pending, trial, rejected, or passed")
    if not isinstance(stage, str) or stage not in STAGES:
        raise ContractError("Asset stage must be pending, generated, layout, or reviewed")
    failures = asset.get("consecutive_failures", 0)
    if isinstance(failures, bool) or not isinstance(failures, int) or failures < 0:
        raise ContractError("consecutive_failures must be a nonnegative integer")
    failure_kind = asset.get("failure_kind")
    if failure_kind is not None and (not isinstance(failure_kind, str) or failure_kind not in {"structure", "critical_material", "other"}):
        raise ContractError("failure_kind must be structure, critical_material, or other")
    before = fingerprint_map(asset.get("fingerprints", {}), "fingerprints")
    current = fingerprint_map(asset.get("current_fingerprints", {}), "current_fingerprints")
    required = string_list(asset.get("required_facts", []), "required_facts")
    if failures >= 2 and failure_kind in {"structure", "critical_material"}:
        return decision("paused", "REPEATED_FIDELITY_FAILURE_REQUIRES_NEW_EVIDENCE_OR_APPROVED_ROUTE")
    if set(current) != set(FINGERPRINTS):
        return decision("needs_review", "CURRENT_DEPENDENCIES_INCOMPLETE")
    if product.get("status") != "passed" or product.get("fact_revision") != current["fact_revision"]:
        return decision("needs_review", "PRODUCT_UNDERSTANDING_NOT_CURRENT")
    if not set(required).issubset(product["confirmed_facts"]):
        return decision("needs_review", "REQUIRED_PRODUCT_FACTS_UNKNOWN")
    if set(required).intersection(product["unknown_facts"]):
        return decision("needs_review", "REQUIRED_PRODUCT_FACTS_CONFLICT")
    source_state = file_state(root, asset.get("source_path"), current["source_hash"], inside=False)
    if source_state != "MATCH":
        return decision("needs_review", "SOURCE_" + source_state)
    if state == "passed" and (stage != "reviewed" or not before):
        return decision("needs_review", "PASSED_STATE_WITHOUT_REVIEW_EVIDENCE")
    if before and set(before) != set(FINGERPRINTS):
        return decision("needs_review", "PREVIOUS_DEPENDENCIES_INCOMPLETE")
    changed = {key for key in FINGERPRINTS if before.get(key) != current[key]}
    result["changed_dependencies"] = sorted(changed)
    if operation == "export" and (changed or state != "passed" or stage != "reviewed"):
        return decision("needs_review", "COPY_ONLY_REQUIRES_CURRENT_PASSED_VERSION")
    # Unknown layout/scene changes cannot be inferred safely from a revision number.
    if before and "requirements_revision" in changed:
        return decision("needs_review", "REQUIREMENTS_CHANGED_CONFIRM_AFFECTED_SCOPE")
    if not before or changed.intersection(GENERATIVE_KEYS):
        return decision("generate", "NEW_OR_CHANGED_PRODUCT_SOURCE_FACTS_OR_PROMPT_THEN_REVIEW")
    if changed.intersection({"copy_hash", "font_revision"}):
        base_state = file_state(root, asset.get("base_path"), asset.get("base_sha256"), inside=True)
        if base_state != "MATCH":
            return decision("needs_review", "LAYOUT_BASE_" + base_state)
        if asset.get("base_reviewed_sha256") != asset.get("base_sha256"):
            return decision("needs_review", "LAYOUT_BASE_HAS_NO_BYTE_BOUND_REVIEW")
        return decision("layout", "COPY_OR_FONT_ONLY_USE_VERIFIED_BASE_THEN_REVIEW")
    output_state = file_state(root, asset.get("output_path"), asset.get("output_sha256"), inside=True)
    if output_state != "MATCH":
        return decision("needs_review", "OUTPUT_" + output_state)
    reviewed = asset.get("reviewed_sha256")
    output_hash = asset.get("output_sha256")
    if state != "passed":
        return decision("review", "TRIAL_OR_REJECTED_VERSION_IS_NOT_DELIVERY_READY")
    if not isinstance(reviewed, str) or reviewed.lower() != str(output_hash).lower():
        return decision("needs_review", "REVIEW_NOT_BOUND_TO_CURRENT_OUTPUT_BYTES")
    return decision("copy_only" if operation == "export" else "skip", "CURRENT_PASSED_BYTES_VERIFIED")


def resume_plan(data: dict[str, Any]) -> dict[str, Any]:
    """Plan selected assets without executing work or changing their QA status."""
    if not isinstance(data, dict):
        raise ContractError("Workflow manifest must be an object")
    if find_sensitive_keys(data):
        raise ContractError("Credential-like fields are not allowed")
    operation = data.get("operation")
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise ContractError("operation must be new, continue, revise, or export")
    copy_only = data.get("copy_only", operation == "export")
    if not isinstance(copy_only, bool) or (operation == "export" and not copy_only):
        raise ContractError("export currently supports only explicit copy_only semantics")
    raw_root = data.get("project_root")
    if not isinstance(raw_root, str) or not Path(raw_root).is_absolute():
        raise ContractError("project_root must be an absolute existing project path")
    root = Path(raw_root).resolve()
    metadata = load_json(root / "project.json")
    stored_root = metadata.get("project_root")
    if not isinstance(stored_root, str) or Path(stored_root).resolve() != root:
        raise ContractError("Project identity does not match project.json")
    expected = string_list(data.get("expected_asset_ids"), "expected_asset_ids", nonempty=True)
    selected = string_list(data.get("selected_asset_ids", expected), "selected_asset_ids", nonempty=True)
    if not set(selected).issubset(expected):
        raise ContractError("selected_asset_ids must belong to expected_asset_ids")
    product = data.get("product_review", {})
    if not isinstance(product, dict):
        raise ContractError("product_review must be an object")
    product = {**product,
               "confirmed_facts": string_list(product.get("confirmed_facts", []), "confirmed_facts"),
               "unknown_facts": string_list(product.get("unknown_facts", []), "unknown_facts")}
    if set(product["confirmed_facts"]).intersection(product["unknown_facts"]):
        raise ContractError("A product fact cannot be both confirmed and unknown")
    assets = data.get("assets")
    if not isinstance(assets, list):
        raise ContractError("assets must be a list of objects")
    indexed: dict[str, dict[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, dict) or not isinstance(asset.get("asset_id"), str):
            raise ContractError("Every asset must be an object with a string asset_id")
        asset_id = asset["asset_id"]
        if asset_id not in expected or asset_id in indexed:
            raise ContractError("Asset IDs must be unique and belong to expected_asset_ids")
        indexed[asset_id] = asset
    plans = [asset_plan(root, operation, indexed[asset_id], product) if asset_id in indexed else
             {"asset_id": asset_id, "action": "needs_review", "reason": "MISSING_ASSET_RECORD"}
             for asset_id in selected]
    counts = {action: sum(plan["action"] == action for plan in plans)
              for action in ("skip", "generate", "layout", "review", "needs_review", "paused", "copy_only")}
    ready = counts["skip"] + counts["copy_only"]
    return {
        "status": "READ_ONLY_PLAN", "operation": operation, "mutations": 0,
        "research_actions": [], "generation_executed": False,
        "expected_count": len(expected), "selected_count": len(selected),
        "verified_ready_selected_count": ready,
        "full_scope_verified": len(selected) == len(expected) and ready == len(expected),
        "counts": counts, "assets": plans,
        "limitations": ["Hash matching does not perform image decoding or visual product QA",
                        "Run validate_export and human/product visual review before delivery"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inspect", "resume-plan"])
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = resume_plan(load_json(args.manifest))
    except (ContractError, OSError) as exc:
        # OSError may contain untrusted paths; only controlled contract messages are echoed.
        message = str(exc) if isinstance(exc, ContractError) else "Cannot read workflow evidence"
        print(json.dumps({"status": "ERROR", "message": message}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
