"""Read-only paired export verification. Usage: --manifest export-manifest.json."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import warnings
from pathlib import Path

try:
    from PIL import Image, ImageFile
except ImportError:
    Image = ImageFile = None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dimensions(path: Path) -> tuple[int, int]:
    """Verify and fully decode PNG/JPEG without changing the original bytes."""
    if Image is None:
        raise RuntimeError("Pillow is required for full image integrity checks")
    allow_truncated = ImageFile.LOAD_TRUNCATED_IMAGES
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as picture:
                if picture.format not in ("PNG", "JPEG"):
                    raise ValueError("Only PNG/JPEG images are supported")
                picture.verify()
            with Image.open(path) as picture:
                picture.load()
                return picture.size
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValueError(f"Image integrity check failed: {path.name}: {exc}") from exc
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = allow_truncated


def output_path(root: Path, value: str, folder: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("Output path must be a nonempty string")
    path = (root / value).resolve()
    if not path.is_relative_to((root / folder).resolve()):
        raise ValueError(f"Output outside {folder}: {value}")
    return path


def asset_ids(value: object, field: str) -> list[str]:
    if (not isinstance(value, list) or not value
            or any(not isinstance(item, str) or not item.strip() for item in value)
            or len(set(value)) != len(value)):
        raise ValueError(f"{field} must contain unique nonempty asset IDs")
    return value


def check_hash(value: object, actual: str, field: str) -> None:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value.lower())
            or value.lower() != actual):
        raise ValueError(f"{field} hash mismatch or invalid SHA-256")


def validate_supporting(data: dict, root: Path, formal_ids: set, outputs: set) -> int:
    """Validate collage inputs without counting them as paired design slots."""
    supporting = data.get("supporting_assets", [])
    if not isinstance(supporting, list):
        raise ValueError("supporting_assets must be a list")
    referenced = set()
    for row in data["assets"]:
        if isinstance(row, dict) and "component_asset_ids" in row:
            referenced.update(asset_ids(row["component_asset_ids"], "component_asset_ids"))
    seen = set()
    for row in supporting:
        if not isinstance(row, dict):
            raise ValueError("Supporting asset must be an object")
        identity = row.get("asset_id")
        if not isinstance(identity, str) or not identity.strip() or identity in seen or identity in formal_ids:
            raise ValueError("Missing, duplicate or conflicting supporting asset_id")
        seen.add(identity)
        source = Path(row["source_path"])
        if not source.is_absolute():
            raise ValueError("Supporting source_path must be absolute")
        original = output_path(root, row["no_copy_path"], "无文案原图")
        if original in outputs:
            raise ValueError("Duplicate supporting output mapping")
        outputs.add(original)
        digest = sha256(source)
        check_hash(row["source_sha256"], digest, "supporting source_sha256")
        check_hash(row["reviewed_sha256"], digest, "supporting reviewed_sha256")
        if sha256(original) != digest:
            raise ValueError("Supporting original/source hash mismatch")
        if list(dimensions(source)) != row["native_dimensions"] or dimensions(original) != dimensions(source):
            raise ValueError("Supporting native dimensions mismatch")
        if row.get("visual_qa") != "PASS":
            raise ValueError("Supporting visual QA has not passed")
        for field in ("status", "asset_status", "source_status"):
            if field in row and row[field] not in ("PASS", "APPROVED", "ACCEPTED", "COMPLETE", "COMPLETED"):
                raise ValueError("Supporting draft/rejected asset cannot be promoted")
    if referenced != seen:
        raise ValueError("Missing or unreferenced supporting assets")
    return len(seen)


def validate_variant(data: dict, root: Path) -> None:
    """Check declared lineage and output isolation; this does not prove visual fidelity."""
    if "variant_template" not in data:
        return
    variant = data["variant_template"]
    if not isinstance(variant, dict):
        raise ValueError("variant_template must be an object")
    for field in ("variant_id", "approval_source"):
        if not isinstance(variant.get(field), str) or not variant[field].strip():
            raise ValueError(f"Missing variant {field}")
    if variant.get("master_approval") != "user_confirmed":
        raise ValueError("Variant master is not user confirmed")
    changes = asset_ids(variant.get("changed_attributes"), "changed_attributes")
    if not set(changes) <= {"color", "material"}:
        raise ValueError("Variant structural/dimension/function changes require product review")
    if variant.get("sample_visual_qa") != "PASS" or variant.get("copy_review") != "PASS":
        raise ValueError("Variant sample or copy review has not passed")
    references = variant.get("reference_paths")
    if not isinstance(references, list) or not references:
        raise ValueError("Variant requires reference_paths")
    for reference in references:
        if not isinstance(reference, str) or not Path(reference).is_absolute() or not Path(reference).is_file():
            raise ValueError("Variant reference must be an existing absolute file path")
    master_path = Path(variant["master_manifest_path"])
    if not master_path.is_absolute():
        raise ValueError("master_manifest_path must be absolute")
    check_hash(variant["master_manifest_sha256"], sha256(master_path), "master_manifest_sha256")
    master = json.loads(master_path.read_text(encoding="utf-8-sig"))
    if not isinstance(master, dict) or master.get("schema") != "amazon-listing-image-studio/dual-export/v1":
        raise ValueError("Invalid master export manifest")
    master_root = Path(master["export_root"])
    if not master_root.is_absolute():
        raise ValueError("Master export_root must be absolute")
    master_root, variant_root = master_root.resolve(), root.resolve()
    if variant_root.is_relative_to(master_root) or master_root.is_relative_to(variant_root):
        raise ValueError("Variant output must not overlap master export_root")


def validate(data: object) -> dict:
    """Report file validity separately from the whole approved task scope."""
    try:
        if not isinstance(data, dict):
            raise ValueError("Manifest root must be an object")
        if data.get("schema") != "amazon-listing-image-studio/dual-export/v1":
            raise ValueError("Invalid dual-export schema")
        if not isinstance(data.get("export_root"), str):
            raise ValueError("export_root must be an absolute path string")
        root = Path(data["export_root"])
        if not root.is_absolute():
            raise ValueError("export_root must be absolute")
        assets = data.get("assets")
        count = data.get("expected_assets")
        if (not isinstance(assets, list) or not assets or type(count) is not int
                or count <= 0 or len(assets) != count):
            raise ValueError("Pair count does not match expected_assets")
        expected = asset_ids(data["expected_asset_ids"], "expected_asset_ids") if "expected_asset_ids" in data else None
        selected = asset_ids(data["selected_asset_ids"], "selected_asset_ids") if "selected_asset_ids" in data else None
        if expected is not None and selected is not None and not set(selected) <= set(expected):
            raise ValueError("selected_asset_ids contains IDs outside expected_asset_ids")
        if Image is None:
            raise RuntimeError("Pillow is required; full integrity checks were not run")
    except (ValueError, KeyError, TypeError, RuntimeError) as exc:
        return {"status": "ERROR", "message": str(exc), "errors": [],
                "task_scope": {"status": "UNVERIFIED"},
                "selected_subset": {"status": "UNVERIFIED"}}
    seen_ids, seen_outputs, verified_ids, errors, limits = set(), set(), set(), [], []
    for index, row in enumerate(assets):
        asset_id = row.get("asset_id") if isinstance(row, dict) else None
        label = asset_id if isinstance(asset_id, str) else f"row_{index + 1}"
        try:
            if not isinstance(row, dict):
                raise ValueError("Asset row must be an object")
            if not isinstance(asset_id, str) or not asset_id.strip() or asset_id in seen_ids:
                raise ValueError("Missing or duplicate asset_id")
            seen_ids.add(asset_id)
            source = Path(row["source_path"])
            if not source.is_absolute():
                raise ValueError("source_path must be absolute")
            original = output_path(root, row["no_copy_path"], "无文案原图")
            copy = output_path(root, row["with_copy_path"], "亚马逊文案图")
            if original in seen_outputs or copy in seen_outputs:
                raise ValueError("Duplicate output mapping")
            seen_outputs.update((original, copy))
            source_digest = sha256(source)
            check_hash(row["source_sha256"], source_digest, "source_sha256")
            if sha256(original) != source_digest:
                raise ValueError("Original copy/source hash mismatch")
            native, exported = dimensions(source), dimensions(copy)
            if dimensions(original) != native or list(native) != row["native_dimensions"]:
                raise ValueError("Native dimensions mismatch")
            if list(exported) != row["export_dimensions"]:
                raise ValueError("Export dimensions mismatch")
            copy_digest = sha256(copy)
            output_hashes = [key for key in ("with_copy_sha256", "output_sha256") if key in row]
            for field in output_hashes:
                check_hash(row[field], copy_digest, field)
            if "reviewed_sha256" in row:
                check_hash(row["reviewed_sha256"], copy_digest, "reviewed_sha256")
            with copy.open("rb") as stream:
                if copy.suffix.lower() != ".png" or stream.read(8) != b"\x89PNG\r\n\x1a\n":
                    raise ValueError("Copy master must be lossless PNG")
            scale = row["scale_factor"]
            if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale) or scale <= 0:
                raise ValueError("Invalid scale_factor")
            if "placement_dimensions" in row:
                placement = row["placement_dimensions"]
                if (not isinstance(placement, list) or len(placement) != 2
                        or any(isinstance(value, bool) or not isinstance(value, (int, float))
                               or not math.isfinite(value) or value <= 0 for value in placement)):
                    raise ValueError("Invalid placement_dimensions")
                # Canvas size includes layout margins; only placed photo size proves scaling.
                if any(not math.isclose(placed, size * scale, abs_tol=0.01)
                       for placed, size in zip(placement, native)):
                    raise ValueError("placement_dimensions do not match scale_factor or preserve aspect ratio")
            if row["upscaled"] is not (scale > 1.000001):
                raise ValueError("Upscaling declaration mismatch")
            if scale > 1.000001 and not row.get("detail_limit"):
                raise ValueError("Upscaling requires detail_limit")
            if not row.get("resampling"):
                raise ValueError("Missing resampling")
            if row["asset_type"] not in ("main", "secondary", "a_plus"):
                raise ValueError("Invalid asset_type")
            if not isinstance(row["copy_applied"], bool):
                raise ValueError("copy_applied must be boolean")
            if row["asset_type"] == "main" and row["copy_applied"]:
                raise ValueError("Main image must not receive marketing copy")
            if row.get("visual_qa") != "PASS":
                raise ValueError("Visual QA has not passed")
            for field in ("status", "asset_status", "source_status"):
                if field in row and row[field] not in ("PASS", "APPROVED", "ACCEPTED", "COMPLETE", "COMPLETED"):
                    raise ValueError(f"{field} is not approved; draft/rejected assets cannot be promoted")
            if not output_hashes or "reviewed_sha256" not in row:
                limits.append({"asset_id": asset_id, "limitation": "Missing output or reviewed SHA-256; review binding is UNVERIFIED"})
            else:
                verified_ids.add(asset_id)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            errors.append({"asset_id": label, "error": str(exc)})
    if selected is not None and set(selected) != seen_ids:
        errors.append({"asset_id": "scope", "error": "Manifest asset IDs do not match selected_asset_ids"})
    if expected is not None and not seen_ids <= set(expected):
        errors.append({"asset_id": "scope", "error": "Manifest contains asset IDs outside expected_asset_ids"})
    supporting_count = 0
    try:
        supporting_count = validate_supporting(data, root, seen_ids, seen_outputs)
        validate_variant(data, root)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        errors.append({"asset_id": "dependencies", "error": str(exc)})
    subset_status = "PARTIAL" if errors else "PASS_WITH_LIMITS" if limits else "PASS"
    missing = sorted(set(expected) - verified_ids) if expected is not None else None
    task_status = "UNVERIFIED" if expected is None else "PARTIAL" if missing or errors else "COMPLETE"
    status = ("PARTIAL" if errors or task_status == "PARTIAL" else
              "PASS_WITH_LIMITS" if limits or expected is None else "PASS")
    return {"status": status, "pair_count": len(assets), "verified_pair_count": len(verified_ids),
            "supporting_asset_count": supporting_count,
            "errors": errors, "limits": limits,
            "selected_subset": {"status": subset_status, "selected_asset_ids": selected,
                                "provided_asset_ids": sorted(seen_ids)},
            "task_scope": {"status": task_status, "expected_asset_ids": expected,
                           "missing_or_unverified_asset_ids": missing},
            "limitation": "File checks do not independently prove visual fidelity, approval provenance or the truth of declared task scope."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate(json.loads(args.manifest.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {"status": "ERROR", "message": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
