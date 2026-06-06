"""Prompt-to-skill coverage registry validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


DEFAULT_COVERAGE_PATH = Path("runtime") / "prompt_skill_coverage.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "prompt-skill-coverage"
WORKFLOW_ROUTER_PLAN_PATH = Path("vllm_agent_gateway") / "controllers" / "workflow_router" / "plan.py"
FOUNDER_FIELD_CATALOG_PATH = Path("runtime") / "prompt_catalogs" / "founder_field_v1.json"
REQUIRED_ADVANCED_DEFERRED_GAP_ID = "GAP-ADV-REFACTOR-SINGLE-PATH"


class CoverageEntryStatus(str, Enum):
    IMPLEMENTED = "implemented"
    PLANNED = "planned"
    DEFERRED = "deferred"


class PromptCoverageReportStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class PromptCoverageConfig:
    config_root: Path
    coverage_path: Path | None = None
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def default_output_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"prompt-skill-coverage-{utc_timestamp()}.json"


def workflow_ids(config_root: Path) -> set[str]:
    manifest = load_json(config_root / "runtime" / "workflows.json")
    return {
        str(item.get("id"))
        for item in manifest.get("workflows", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def tool_ids(config_root: Path) -> set[str]:
    manifest = load_json(config_root / "runtime" / "tools.json")
    return {
        str(item.get("id"))
        for item in manifest.get("tools", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def skill_registry(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = load_json(config_root / "runtime" / "skills.json")
    return {
        str(item.get("id")): item
        for item in manifest.get("skills", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def eval_registry(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = load_json(config_root / "runtime" / "skill_evals.json")
    return {
        str(item.get("id")): item
        for item in manifest.get("cases", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def router_rules(config_root: Path) -> set[str]:
    source = (config_root / WORKFLOW_ROUTER_PLAN_PATH).read_text(encoding="utf-8")
    return set(re.findall(r'"rule": "([^"]+)"', source))


def founder_field_expected_rules(config_root: Path) -> set[str]:
    path = config_root / FOUNDER_FIELD_CATALOG_PATH
    if not path.exists():
        return set()
    catalog = load_json(path)
    return {
        str(item.get("expected_rule"))
        for item in catalog.get("cases", [])
        if isinstance(item, dict) and isinstance(item.get("expected_rule"), str) and item.get("expected_rule")
    }


def list_strings(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def add_error(errors: list[dict[str, Any]], entry_id: str, field: str, message: str) -> None:
    errors.append({"entry_id": entry_id, "field": field, "message": message})


def validate_entry(
    *,
    entry: dict[str, Any],
    workflows: set[str],
    tools: set[str],
    skills: dict[str, dict[str, Any]],
    evals: dict[str, dict[str, Any]],
    rules: set[str],
    config_root: Path,
) -> list[dict[str, Any]]:
    entry_id = str(entry.get("id") or "<missing>")
    errors: list[dict[str, Any]] = []
    status = entry.get("status")
    if status not in {item.value for item in CoverageEntryStatus}:
        add_error(errors, entry_id, "status", "status must be implemented, planned, or deferred")
    if status != CoverageEntryStatus.IMPLEMENTED.value:
        return errors
    selected_workflow = entry.get("selected_workflow")
    if not isinstance(selected_workflow, str) or selected_workflow not in workflows:
        add_error(errors, entry_id, "selected_workflow", "selected_workflow must reference runtime/workflows.json")
    route_rule = entry.get("route_rule")
    if not isinstance(route_rule, str) or route_rule not in rules:
        add_error(errors, entry_id, "route_rule", "route_rule must exist in workflow_router.plan route evidence")
    expected_artifacts = list_strings(entry.get("expected_artifacts"))
    if not expected_artifacts:
        add_error(errors, entry_id, "expected_artifacts", "implemented entries must name expected artifacts")
    validation_suites = list_strings(entry.get("validation_suites"))
    if not validation_suites:
        add_error(errors, entry_id, "validation_suites", "implemented entries must name validation suites")
    docs_examples = list_strings(entry.get("docs_examples"))
    if not docs_examples:
        add_error(errors, entry_id, "docs_examples", "implemented entries must link docs/examples")
    for doc in docs_examples:
        if not (config_root / doc).exists():
            add_error(errors, entry_id, "docs_examples", f"linked doc does not exist: {doc}")
    for tool_id in list_strings(entry.get("tool_ids")):
        if tool_id not in tools:
            add_error(errors, entry_id, "tool_ids", f"unknown tool_id: {tool_id}")
    controller_owned = entry.get("controller_owned") is True
    skill_ids = list_strings(entry.get("skill_ids"))
    if not skill_ids and not controller_owned:
        add_error(errors, entry_id, "skill_ids", "implemented non-controller-owned entries must name at least one skill")
    for skill_id in skill_ids:
        skill = skills.get(skill_id)
        if skill is None:
            add_error(errors, entry_id, "skill_ids", f"unknown skill_id: {skill_id}")
            continue
        skill_workflows = list_strings(skill.get("workflows"))
        if isinstance(selected_workflow, str) and selected_workflow not in skill_workflows:
            add_error(errors, entry_id, "skill_ids", f"skill_id does not support selected_workflow: {skill_id}")
    eval_case_ids = list_strings(entry.get("eval_case_ids"))
    regression_refs = list_strings(entry.get("regression_test_refs"))
    if not eval_case_ids and not regression_refs:
        add_error(errors, entry_id, "eval_case_ids", "implemented entries must name eval cases or regression test refs")
    for eval_case_id in eval_case_ids:
        eval_case = evals.get(eval_case_id)
        if eval_case is None:
            add_error(errors, entry_id, "eval_case_ids", f"unknown eval_case_id: {eval_case_id}")
            continue
        if isinstance(selected_workflow, str) and eval_case.get("expected_workflow") != selected_workflow:
            add_error(errors, entry_id, "eval_case_ids", f"eval case expected_workflow mismatch: {eval_case_id}")
    for ref in regression_refs:
        if not (config_root / ref).exists():
            add_error(errors, entry_id, "regression_test_refs", f"regression test ref does not exist: {ref}")
    return errors


def validate_prompt_coverage(config: PromptCoverageConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    coverage_path = config.coverage_path or config_root / DEFAULT_COVERAGE_PATH
    manifest = load_json(coverage_path)
    entries = manifest.get("entries") if isinstance(manifest.get("entries"), list) else []
    gaps = manifest.get("gap_backlog") if isinstance(manifest.get("gap_backlog"), list) else []
    workflows = workflow_ids(config_root)
    tools = tool_ids(config_root)
    skills = skill_registry(config_root)
    evals = eval_registry(config_root)
    rules = router_rules(config_root)
    errors: list[dict[str, Any]] = []
    if manifest.get("kind") != "prompt_skill_coverage_registry":
        errors.append({"entry_id": "<manifest>", "field": "kind", "message": "kind must be prompt_skill_coverage_registry"})
    seen_ids: set[str] = set()
    covered_rules: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            errors.append({"entry_id": "<entries>", "field": "entries", "message": "entries must be objects"})
            continue
        entry_id = str(item.get("id") or "")
        if not entry_id:
            add_error(errors, "<missing>", "id", "entry id is required")
        elif entry_id in seen_ids:
            add_error(errors, entry_id, "id", "duplicate coverage entry id")
        seen_ids.add(entry_id)
        if isinstance(item.get("route_rule"), str) and item.get("status") == CoverageEntryStatus.IMPLEMENTED.value:
            covered_rules.add(str(item["route_rule"]))
        errors.extend(
            validate_entry(
                entry=item,
                workflows=workflows,
                tools=tools,
                skills=skills,
                evals=evals,
                rules=rules,
                config_root=config_root,
            )
        )
    gap_ids: set[str] = set()
    for gap in gaps:
        if not isinstance(gap, dict):
            errors.append({"entry_id": "<gap_backlog>", "field": "gap_backlog", "message": "gap entries must be objects"})
            continue
        gap_id = str(gap.get("id") or "")
        gap_ids.add(gap_id)
        if gap.get("status") not in {CoverageEntryStatus.PLANNED.value, CoverageEntryStatus.DEFERRED.value}:
            add_error(errors, gap_id or "<missing>", "status", "gap status must be planned or deferred")
        if not isinstance(gap.get("prompt_family"), str) or not gap.get("prompt_family"):
            add_error(errors, gap_id or "<missing>", "prompt_family", "gap prompt_family is required")
        if not isinstance(gap.get("reason"), str) or not gap.get("reason"):
            add_error(errors, gap_id or "<missing>", "reason", "gap reason is required")
    if REQUIRED_ADVANCED_DEFERRED_GAP_ID not in gap_ids:
        errors.append(
            {
                "entry_id": REQUIRED_ADVANCED_DEFERRED_GAP_ID,
                "field": "gap_backlog",
                "message": "advanced single-path refactor must remain recorded as deferred",
            }
        )
    founder_rules = founder_field_expected_rules(config_root)
    missing_founder_rules = sorted(founder_rules - covered_rules)
    for rule in missing_founder_rules:
        errors.append({"entry_id": "<founder_field_v1>", "field": "route_rule", "message": f"founder field rule is not covered: {rule}"})
    report = {
        "schema_version": 1,
        "kind": "prompt_skill_coverage_report",
        "status": PromptCoverageReportStatus.PASSED.value if not errors else PromptCoverageReportStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "coverage_path": str(coverage_path.resolve()),
        "summary": {
            "entry_count": len(entries),
            "implemented_count": sum(1 for item in entries if isinstance(item, dict) and item.get("status") == "implemented"),
            "gap_count": len(gaps),
            "founder_field_rule_count": len(founder_rules),
            "covered_founder_field_rule_count": len(founder_rules - set(missing_founder_rules)),
            "error_count": len(errors),
        },
        "errors": errors,
    }
    output_path = config.output_path or default_output_path(config_root)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
