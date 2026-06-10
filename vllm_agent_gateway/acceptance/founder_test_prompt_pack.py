"""Founder test prompt-pack governance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_PACK_KIND = "founder_test_prompt_pack"
EXPECTED_REPORT_KIND = "founder_test_prompt_pack_validation"
EXPECTED_PHASE = 137
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_PACK_PATH = Path("runtime") / "founder_test_prompt_pack.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "founder-test-prompt-pack" / "phase137"
REQUIRED_WORKFLOWS = {"code_investigation.plan", "code_context.lookup", "task.decompose"}
REQUIRED_TARGET_ROOTS = {
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
}
FORBIDDEN_TAGS = {"draft-only", "apply-proof", "disposable-copy"}
REQUIRED_SMOKE_CASES = ["P01", "P02", "P03", "P22"]


class FounderTestPromptPackStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class FounderTestPromptPackConfig:
    config_root: Path
    pack_path: Path = DEFAULT_PACK_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"founder-test-prompt-pack-{utc_timestamp()}.json"


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def catalog_cases(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("case_id")): item
        for item in object_list(catalog.get("cases"))
        if isinstance(item.get("case_id"), str)
    }


def tier_case_ids(pack: dict[str, Any]) -> dict[str, list[str]]:
    return {
        str(tier.get("tier")): string_list(tier.get("case_ids"))
        for tier in object_list(pack.get("tiers"))
        if isinstance(tier.get("tier"), str)
    }


def duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def validate_pack(pack: dict[str, Any], *, catalog: dict[str, Any], config_root: Path) -> list[str]:
    errors: list[str] = []
    if pack.get("schema_version") != SCHEMA_VERSION:
        errors.append("pack.schema_version must be 1")
    if pack.get("kind") != EXPECTED_PACK_KIND:
        errors.append(f"pack.kind must be {EXPECTED_PACK_KIND}")
    if pack.get("phase") != EXPECTED_PHASE:
        errors.append("pack.phase must be 137")
    if pack.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"pack.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    catalog_path = pack.get("catalog_path")
    if not isinstance(catalog_path, str) or not resolve_path(config_root, catalog_path).is_file():
        errors.append("pack.catalog_path must reference an existing prompt catalog")
    if catalog.get("kind") != "prompt_catalog":
        errors.append("catalog.kind must be prompt_catalog")
    by_id = catalog_cases(catalog)
    tiers = tier_case_ids(pack)
    if tiers.get("smoke") != REQUIRED_SMOKE_CASES:
        errors.append("pack smoke tier must match the current Phase 134 smoke cases")
    if not tiers.get("expanded_read_only"):
        errors.append("pack must include expanded_read_only tier")
    selected_ids = [case_id for ids in tiers.values() for case_id in ids]
    if len(selected_ids) < 12:
        errors.append("pack must include at least 12 total founder prompt cases")
    duplicates = duplicate_values(selected_ids)
    if duplicates:
        errors.append("pack contains duplicate case IDs: " + ", ".join(duplicates))
    unknown = sorted(set(selected_ids) - set(by_id))
    if unknown:
        errors.append("pack references unknown case IDs: " + ", ".join(unknown))
    selected_cases = [by_id[case_id] for case_id in selected_ids if case_id in by_id]
    workflows = {str(case.get("expected_workflow")) for case in selected_cases}
    missing_workflows = sorted(REQUIRED_WORKFLOWS - workflows)
    if missing_workflows:
        errors.append("pack missing required workflow coverage: " + ", ".join(missing_workflows))
    target_roots = {str(case.get("target_root")) for case in selected_cases}
    missing_roots = sorted(REQUIRED_TARGET_ROOTS - target_roots)
    if missing_roots:
        errors.append("pack missing required target roots: " + ", ".join(missing_roots))
    for case in selected_cases:
        case_id = case.get("case_id")
        tags = set(string_list(case.get("tags")))
        forbidden = sorted(tags & FORBIDDEN_TAGS)
        if forbidden:
            errors.append(f"{case_id} includes forbidden founder-pack tag(s): " + ", ".join(forbidden))
        if case.get("expected_workflow") == "refactor.single_path":
            errors.append(f"{case_id} advanced refactor workflow is not allowed in Phase 137")
    return errors


def build_prompt_pack_report(
    *,
    config_root: Path,
    pack: dict[str, Any],
    catalog: dict[str, Any],
    pack_path: Path | None = None,
    catalog_path: Path | None = None,
) -> dict[str, Any]:
    tiers = tier_case_ids(pack)
    selected_ids = [case_id for ids in tiers.values() for case_id in ids]
    by_id = catalog_cases(catalog)
    selected_cases = [by_id[case_id] for case_id in selected_ids if case_id in by_id]
    errors = validate_pack(pack, catalog=catalog, config_root=config_root)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": FounderTestPromptPackStatus.PASSED.value if not errors else FounderTestPromptPackStatus.FAILED.value,
        "generated_at": utc_timestamp(),
        "pack_path": str(pack_path or DEFAULT_PACK_PATH),
        "pack_sha256": artifact_hash(pack_path) if pack_path else None,
        "catalog_path": str(catalog_path or pack.get("catalog_path")),
        "catalog_sha256": artifact_hash(catalog_path) if catalog_path else None,
        "tiers": tiers,
        "selected_case_ids": selected_ids,
        "summary": {
            "tier_count": len(tiers),
            "case_count": len(selected_ids),
            "workflow_count": len({str(case.get("expected_workflow")) for case in selected_cases}),
            "target_root_count": len({str(case.get("target_root")) for case in selected_cases}),
            "smoke_case_count": len(tiers.get("smoke", [])),
            "expanded_read_only_case_count": len(tiers.get("expanded_read_only", [])),
        },
        "errors": errors,
    }


def validate_prompt_pack_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    pack: dict[str, Any],
    catalog: dict[str, Any],
    pack_path: Path | None = None,
    catalog_path: Path | None = None,
) -> list[str]:
    expected = build_prompt_pack_report(
        config_root=config_root,
        pack=pack,
        catalog=catalog,
        pack_path=pack_path,
        catalog_path=catalog_path,
    )
    errors: list[str] = []
    for key in (
        "schema_version",
        "kind",
        "phase",
        "priority_backlog_id",
        "status",
        "pack_path",
        "pack_sha256",
        "catalog_path",
        "catalog_sha256",
        "tiers",
        "selected_case_ids",
        "summary",
        "errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append(f"report.{key} must match rebuilt founder test prompt pack")
    return errors


def run_prompt_pack_gate(config: FounderTestPromptPackConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    pack_path = resolve_path(config_root, config.pack_path)
    pack = read_json_object(pack_path) if pack_path.is_file() else {}
    catalog_path_value = pack.get("catalog_path") if isinstance(pack.get("catalog_path"), str) else ""
    catalog_path = resolve_path(config_root, catalog_path_value) if catalog_path_value else Path()
    catalog = read_json_object(catalog_path) if catalog_path.is_file() else {}
    report = build_prompt_pack_report(
        config_root=config_root,
        pack=pack,
        catalog=catalog,
        pack_path=pack_path,
        catalog_path=catalog_path,
    )
    errors = []
    for path in (pack_path, catalog_path):
        if config.require_artifacts and not path.is_file():
            errors.append(f"required artifact is missing: {path}")
    errors.extend(
        validate_prompt_pack_report(
            report,
            config_root=config_root,
            pack=pack,
            catalog=catalog,
            pack_path=pack_path,
            catalog_path=catalog_path,
        )
    )
    if errors:
        report["status"] = FounderTestPromptPackStatus.FAILED.value
        report["errors"] = report["errors"] + errors
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
