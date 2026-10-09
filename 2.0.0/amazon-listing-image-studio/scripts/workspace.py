#!/usr/bin/env python3
"""Validate intake manifests and create collision-safe project/batch folders."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ALLOWED_SHEET_SUFFIXES = {".xlsx", ".xls", ".csv", ".tsv"}
RESERVED_WINDOWS_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}
SENSITIVE_KEY_RE = re.compile(
    r"(^|_)(token|cookie|secret|password|authorization|api_key|access_key)(_|$)",
    re.IGNORECASE,
)
ASIN_PATH_RE = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)", re.IGNORECASE)
LINK_MODES = {"links_without_requirements", "links_with_requirements"}
INPUT_MODES = {*LINK_MODES, "requirements_sheet", "links"}
INPUT_MODES.add("SINGLE_REFERENCE")
OPERATIONS = {"new", "continue", "revise", "export"}
MARKETPLACE_DOMAINS = {
    "US": "amazon.com", "CA": "amazon.ca", "MX": "amazon.com.mx",
    "BR": "amazon.com.br", "UK": "amazon.co.uk", "DE": "amazon.de",
    "FR": "amazon.fr", "IT": "amazon.it", "ES": "amazon.es",
    "NL": "amazon.nl", "SE": "amazon.se", "PL": "amazon.pl",
    "BE": "amazon.com.be", "IE": "amazon.ie", "JP": "amazon.co.jp",
    "AU": "amazon.com.au", "IN": "amazon.in", "SG": "amazon.sg",
    "AE": "amazon.ae", "SA": "amazon.sa", "TR": "amazon.com.tr",
    "EG": "amazon.eg", "ZA": "amazon.co.za",
}


class ContractError(ValueError):
    """Raised when an intake or workspace contract is invalid."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"Manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"Manifest is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError("Manifest root must be a JSON object")
    return data


def find_sensitive_keys(value: Any, prefix: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            location = f"{prefix}.{key_text}" if prefix else key_text
            if SENSITIVE_KEY_RE.search(key_text):
                findings.append(location)
            findings.extend(find_sensitive_keys(child, location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(find_sensitive_keys(child, f"{prefix}[{index}]"))
    return findings


def amazon_url_info(raw_url: str) -> tuple[str, str]:
    try:
        parsed = urlparse(raw_url)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as exc:
        raise ContractError("Invalid Amazon URL") from exc
    if parsed.scheme not in {"http", "https"}:
        raise ContractError("Amazon URL must use http or https")
    if parsed.username is not None or parsed.password is not None or port is not None:
        raise ContractError("Amazon URLs cannot contain credentials or explicit ports")
    allowed_hosts = {host for domain in MARKETPLACE_DOMAINS.values()
                     for host in (domain, "www." + domain)}
    if host not in allowed_hosts:
        raise ContractError("URL is not a supported direct Amazon marketplace domain")
    # Do not echo untrusted URLs: query strings and fragments can contain secrets.
    match = ASIN_PATH_RE.search(parsed.path + "/")
    if not match:
        raise ContractError("Amazon product URL does not expose a 10-character ASIN")
    return host, match.group(1).upper()


def requirements_file_info(raw_path: Any) -> dict[str, str]:
    path_text = str(raw_path or "").strip()
    if not path_text:
        raise ContractError("This input mode requires requirements_path")
    sheet_path = Path(path_text).expanduser().resolve()
    if sheet_path.suffix.lower() not in ALLOWED_SHEET_SUFFIXES:
        raise ContractError("requirements_path must be XLSX, XLS, CSV, or TSV")
    if not sheet_path.is_file():
        raise ContractError(f"Requirements file does not exist: {sheet_path}")
    return {
        "requirements_path": str(sheet_path),
        "requirements_sha256": file_sha256(sheet_path),
    }


def validate_intake(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ContractError("Manifest root must be a JSON object")
    sensitive_keys = find_sensitive_keys(data)
    if sensitive_keys:
        raise ContractError(
            "Sensitive credential-like fields are not allowed in the manifest: "
            + ", ".join(sensitive_keys)
        )

    requested_mode = data.get("input_mode")
    if not isinstance(requested_mode, str) or requested_mode not in INPUT_MODES:
        raise ContractError(
            "input_mode must be links_without_requirements, "
            "links_with_requirements, requirements_sheet, or SINGLE_REFERENCE"
        )

    has_requirements_path = bool(str(data.get("requirements_path", "")).strip())
    if requested_mode == "links":
        mode = "links_with_requirements" if has_requirements_path else "links_without_requirements"
    else:
        mode = requested_mode

    if mode == "links_without_requirements" and has_requirements_path:
        raise ContractError(
            "links_without_requirements cannot include requirements_path; "
            "use links_with_requirements"
        )
    if mode == "links_with_requirements" and not has_requirements_path:
        raise ContractError("links_with_requirements requires requirements_path")
    if mode == "requirements_sheet" and data.get("amazon_urls"):
        raise ContractError(
            "requirements_sheet is the no-link mode; use links_with_requirements when URLs are provided"
        )

    marketplace = str(data.get("marketplace", "")).strip().upper()
    if marketplace not in MARKETPLACE_DOMAINS:
        raise ContractError("marketplace must be a supported marketplace code")

    operation = data.get("operation", "new")
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise ContractError("operation must be new, continue, revise, or export")

    report_edition = data.get("report_edition", "auto")
    if not isinstance(report_edition, str) or report_edition not in {"auto", "basic", "enhanced"}:
        raise ContractError("report_edition must be auto, basic, or enhanced")

    explicit_top10 = data.get("explicit_top10", False)
    if not isinstance(explicit_top10, bool):
        raise ContractError("explicit_top10 must be true or false")
    depth = data.get("research_depth")
    if depth is not None and (not isinstance(depth, str) or depth not in {"light", "full", "provided"}):
        raise ContractError("research_depth must be light, full, or provided")
    historical = operation != "new" or data.get("schema_version") == 1 or "workflow_mode" in data
    preserve_full = data.get("research_target") == 10 or data.get("next_gate") == "DISCOVER_COMPARABLE_TOP_TEN"
    migration = "NONE"
    if explicit_top10:
        depth = "full"
    elif depth is None and preserve_full:
        depth, migration = "full", "PRESERVED_LEGACY_TOP10"
    elif depth is None and historical and mode == "requirements_sheet":
        migration = "CONFIRM_LEGACY_RESEARCH_DEPTH"
    elif depth is None:
        depth = "light" if mode == "requirements_sheet" else "provided"
        migration = "NEW_INTAKE_DEFAULT" if not historical else "PRESERVED_PROVIDED_LINKS"
    if mode == "requirements_sheet" and depth == "provided":
        raise ContractError("requirements_sheet cannot use provided research without links")

    normalized: dict[str, Any] = {
        "input_mode": mode,
        "workflow_mode": mode,
        "marketplace": marketplace,
        "report_edition": report_edition,
        "schema_version": 2,
        "operation": operation,
        "research_depth": depth,
        "research_migration": migration,
        "research_target": 10 if depth == "full" else (3 if depth == "light" else None),
        "research_max": 10 if depth == "full" else (5 if depth == "light" else None),
        "initial_gate": "PRODUCT_UNDERSTANDING" if operation == "new" else "INSPECT_RESUME_PLAN",
        "status": "READY",
        "gaps": [],
    }
    if requested_mode != mode:
        normalized["requested_input_mode"] = requested_mode

    if mode in LINK_MODES or mode == "SINGLE_REFERENCE":
        urls = data.get("amazon_urls")
        minimum = 1 if mode == "SINGLE_REFERENCE" else 2
        if not isinstance(urls, list) or len(urls) < minimum:
            raise ContractError(f"{mode} requires at least two amazon_urls")
        if mode == "SINGLE_REFERENCE" and len(urls) != 1:
            raise ContractError("SINGLE_REFERENCE requires exactly one URL")
        seen_asins: set[str] = set()
        normalized_links: list[dict[str, str]] = []
        for raw_url in urls:
            if not isinstance(raw_url, str):
                raise ContractError("Every amazon_urls item must be a string")
            host, asin = amazon_url_info(raw_url.strip())
            domain = MARKETPLACE_DOMAINS[marketplace]
            if host not in {domain, "www." + domain}:
                raise ContractError("Amazon URL marketplace does not match the manifest marketplace")
            if asin in seen_asins:
                continue
            seen_asins.add(asin)
            normalized_links.append({"url": f"https://www.{domain}/dp/{asin}", "host": host, "asin": asin})
        if len(normalized_links) < minimum:
            raise ContractError(f"{mode} requires at least two distinct ASINs")
        normalized["amazon_links"] = normalized_links
        if mode == "SINGLE_REFERENCE":
            normalized["research_scope"] = "SINGLE_REFERENCE_NO_CATEGORY_OR_SALES_INFERENCE"
        if mode == "links_without_requirements" or (mode == "SINGLE_REFERENCE" and not has_requirements_path):
            full_auto = data.get("full_auto_after_brief", False)
            if not isinstance(full_auto, bool):
                raise ContractError("full_auto_after_brief must be true or false")
            normalized.update(
                {
                    "requirements_status": "TO_BE_GENERATED",
                    "next_gate": "GENERATE_IMAGE_REQUIREMENTS",
                    "full_auto_after_brief": full_auto,
                }
            )
        else:
            normalized.update(requirements_file_info(data.get("requirements_path")))
            normalized.update(
                {
                    "requirements_status": "PROVIDED",
                    "next_gate": "RECONSTRUCT_PROMPTS_AND_CHECK_AMBIGUITIES",
                }
            )
    else:
        category_node = str(data.get("category_node", "")).strip()
        category_keyword = str(data.get("category_keyword", "")).strip()
        if not category_node and not category_keyword:
            raise ContractError("Provide category_node or category_keyword")
        normalized.update(requirements_file_info(data.get("requirements_path")))
        normalized.update(
            {
                "category_node": category_node or None,
                "category_keyword": category_keyword or None,
                "requirements_status": "PROVIDED",
                "next_gate": "DISCOVER_COMPARABLE_TOP_TEN" if depth == "full" else "DISCOVER_REPRESENTATIVE_REFERENCES",
            }
        )
        if depth == "full" and not category_node:
            normalized["status"] = "NEEDS_CATEGORY_CONFIRMATION"
            normalized["gaps"].append("Exact Amazon browse node must be confirmed")

    if migration == "CONFIRM_LEGACY_RESEARCH_DEPTH":
        normalized["status"] = "NEEDS_RESEARCH_MIGRATION"
        normalized["next_gate"] = "CONFIRM_RESEARCH_DEPTH"
        normalized["gaps"].append("Legacy research scope is unknown; explicitly choose light or full")
    if depth == "full" and mode != "requirements_sheet":
        normalized["category_node"] = str(data.get("category_node", "")).strip() or None
        normalized["next_gate"] = "DISCOVER_COMPARABLE_TOP_TEN"
        if not normalized["category_node"]:
            normalized["status"] = "NEEDS_CATEGORY_CONFIRMATION"
            normalized["gaps"].append("Exact Amazon browse node must be confirmed for full research")

    return normalized


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_folder_name(raw_name: str) -> str:
    name = raw_name.strip().rstrip(". ")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", name)
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"-+", "-", name).strip("-.")
    if not name:
        raise ContractError("Folder name is empty after normalization")
    if name.split(".", 1)[0].lower() in RESERVED_WINDOWS_NAMES:
        raise ContractError(f"Folder name is reserved on Windows: {name}")
    if len(name) > 64:
        raise ContractError("Folder name must be 64 characters or fewer")
    return name


def project_plan(output_root: Path, project_name: str) -> dict[str, Any]:
    safe_name = normalize_folder_name(project_name)
    root = output_root.expanduser().resolve() / safe_name
    return {
        "status": "NAME_CONFIRMATION_REQUIRED",
        "requested_name": project_name,
        "normalized_name": safe_name,
        "project_root": str(root),
        "exists": root.exists(),
        "directories": [
            str(root / "sources"),
            str(root / "analysis"),
            str(root / "product"),
            str(root / "generated"),
            str(root / "receipts"),
        ],
    }


def create_project(output_root: Path, project_name: str, confirmed_name: str) -> dict[str, Any]:
    plan = project_plan(output_root, project_name)
    if confirmed_name != plan["normalized_name"]:
        raise ContractError("--confirm-name must exactly match normalized_name from plan-project")
    root = Path(plan["project_root"])
    if root.exists():
        raise ContractError(f"Project directory already exists; choose a new name: {root}")
    root.mkdir(parents=True, exist_ok=False)
    for child in ("sources", "analysis", "product", "generated", "receipts"):
        (root / child).mkdir()
    metadata = {
        "project_name": plan["normalized_name"],
        "project_root": str(root),
        "status": "CREATED",
    }
    (root / "project.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def batch_plan(project_root: Path, batch_name: str) -> dict[str, Any]:
    root = project_root.expanduser().resolve()
    if not (root / "project.json").is_file():
        raise ContractError(f"Not a valid project directory: {root}")
    safe_name = normalize_folder_name(batch_name)
    batch_root = root / "generated" / safe_name
    return {
        "status": "NAME_CONFIRMATION_REQUIRED",
        "requested_name": batch_name,
        "normalized_name": safe_name,
        "batch_root": str(batch_root),
        "exists": batch_root.exists(),
        "directories": [str(batch_root / child) for child in
                        ("images", "exports/无文案原图", "exports/亚马逊文案图")],
    }


def create_batch(project_root: Path, batch_name: str, confirmed_name: str) -> dict[str, Any]:
    plan = batch_plan(project_root, batch_name)
    if confirmed_name != plan["normalized_name"]:
        raise ContractError("--confirm-name must exactly match normalized_name from plan-batch")
    batch_root = Path(plan["batch_root"])
    if batch_root.exists():
        raise ContractError(f"Batch directory already exists; choose a new name: {batch_root}")
    (batch_root / "images").mkdir(parents=True, exist_ok=False)
    for folder in ("无文案原图", "亚马逊文案图"):
        (batch_root / "exports" / folder).mkdir(parents=True, exist_ok=False)
    metadata = {
        "batch_name": plan["normalized_name"],
        "batch_root": str(batch_root),
        "status": "CREATED",
    }
    (batch_root / "generation-manifest.json").write_text(
        json.dumps({**metadata, "images": []}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-intake")
    validate.add_argument("--manifest", type=Path, required=True)

    plan_project = subparsers.add_parser("plan-project")
    plan_project.add_argument("--output-root", type=Path, required=True)
    plan_project.add_argument("--project-name", required=True)

    create_project_parser = subparsers.add_parser("create-project")
    create_project_parser.add_argument("--output-root", type=Path, required=True)
    create_project_parser.add_argument("--project-name", required=True)
    create_project_parser.add_argument("--confirm-name", required=True)

    plan_batch_parser = subparsers.add_parser("plan-batch")
    plan_batch_parser.add_argument("--project-root", type=Path, required=True)
    plan_batch_parser.add_argument("--batch-name", required=True)

    create_batch_parser = subparsers.add_parser("create-batch")
    create_batch_parser.add_argument("--project-root", type=Path, required=True)
    create_batch_parser.add_argument("--batch-name", required=True)
    create_batch_parser.add_argument("--confirm-name", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "validate-intake":
            print_json(validate_intake(load_json(args.manifest)))
        elif args.command == "plan-project":
            print_json(project_plan(args.output_root, args.project_name))
        elif args.command == "create-project":
            print_json(create_project(args.output_root, args.project_name, args.confirm_name))
        elif args.command == "plan-batch":
            print_json(batch_plan(args.project_root, args.batch_name))
        elif args.command == "create-batch":
            print_json(create_batch(args.project_root, args.batch_name, args.confirm_name))
        else:
            raise ContractError(f"Unsupported command: {args.command}")
    except ContractError as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
