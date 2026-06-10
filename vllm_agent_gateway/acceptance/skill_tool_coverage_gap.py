"""Skill/tool coverage gap gate for Priority 0 chat-quality evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "skill_tool_coverage_gap_policy.json"
DEFAULT_PRIORITY0_GAP_TAXONOMY_PATH = (
    Path("runtime-state") / "priority0-gap-taxonomy" / "phase123-priority0-gap-taxonomy-report.json"
)
DEFAULT_PROMPT_TIGHTENING_REPORT_PATH = (
    Path("runtime-state")
    / "prompt-tightening-recommendations"
    / "phase128"
    / "phase128-prompt-tightening-recommendations-report.json"
)
DEFAULT_CAPABILITY_BACKLOG_PATH = Path("runtime") / "natural_language_capability_gap_backlog.json"
DEFAULT_PROMPT_COVERAGE_PATH = Path("runtime") / "prompt_skill_coverage.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "skill-tool-coverage-gap" / "phase129"
EXPECTED_POLICY_KIND = "skill_tool_coverage_gap_policy"
EXPECTED_REPORT_KIND = "skill_tool_coverage_gap_report"
EXPECTED_PHASE = 129
EXPECTED_BACKLOG_ID = "P0-BB-014"
SKILL_TOOL_GAP_CLASS = "skill_tool_selection"


class SkillToolCoverageGapStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class SkillToolCoverageGapConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    priority0_gap_taxonomy_path: Path = DEFAULT_PRIORITY0_GAP_TAXONOMY_PATH
    prompt_tightening_report_path: Path = DEFAULT_PROMPT_TIGHTENING_REPORT_PATH
    capability_backlog_path: Path = DEFAULT_CAPABILITY_BACKLOG_PATH
    prompt_coverage_path: Path = DEFAULT_PROMPT_COVERAGE_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"skill-tool-coverage-gap-{utc_timestamp()}.json"


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


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 129")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if policy.get("skill_tool_gap_class") != SKILL_TOOL_GAP_CLASS:
        errors.append(f"policy.skill_tool_gap_class must be {SKILL_TOOL_GAP_CLASS}")
    for key in (
        "allowed_gap_sources",
        "allowed_repair_types",
        "required_proposal_fields",
        "allowed_validation_tiers",
        "approval_boundary_values",
    ):
        if not string_list(policy.get(key)):
            errors.append(f"policy.{key} must be a non-empty string array")
    return errors


def backlog_entries(backlog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("id")): entry
        for entry in object_list(backlog.get("entries"))
        if isinstance(entry.get("id"), str)
    }


def implemented_coverage_entries(coverage: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("id")): entry
        for entry in object_list(coverage.get("entries"))
        if entry.get("status") == "implemented" and isinstance(entry.get("id"), str)
    }


def extract_skill_tool_findings(priority0_gap_taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for finding in object_list(priority0_gap_taxonomy.get("findings")):
        evidence = dict_value(finding.get("evidence"))
        if evidence.get("gap_class") == SKILL_TOOL_GAP_CLASS:
            findings.append(finding)
    return findings


def prompt_tightening_non_skill_tool_records(prompt_tightening_report: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for candidate in object_list(prompt_tightening_report.get("candidates")):
        records.append(
            {
                "candidate_id": candidate.get("candidate_id"),
                "family_id": candidate.get("family_id"),
                "case_id": candidate.get("case_id"),
                "decision_status": dict_value(candidate.get("decision")).get("status"),
                "suggestion_class": candidate.get("suggestion_class"),
                "classified_as": "not_skill_tool_gap",
                "reason": "Prompt-tightening candidate is governed separately and does not require a missing skill or tool proposal.",
            }
        )
    return records


def candidate_from_finding(
    finding: dict[str, Any],
    *,
    index: int,
    capability_backlog: dict[str, Any],
) -> dict[str, Any]:
    evidence = dict_value(finding.get("evidence"))
    backlog = backlog_entries(capability_backlog)
    backlog_ref = evidence.get("capability_backlog_ref")
    backlog_entry = backlog.get(str(backlog_ref)) if isinstance(backlog_ref, str) else None
    if backlog_entry:
        expected_skills = string_list(backlog_entry.get("expected_skills"))
        expected_tools = string_list(backlog_entry.get("expected_tools"))
        capability_type = "skill" if expected_skills else "tool"
        capability_id = (expected_skills or expected_tools or [f"phase129-gap-{index}"])[0]
        eval_gate = backlog_entry.get("eval_gate")
        validation_tier = backlog_entry.get("validation_tier")
        proposal_summary = backlog_entry.get("rationale")
    else:
        capability_type = str(evidence.get("capability_type") or "skill")
        capability_id = str(evidence.get("capability_id") or f"phase129-gap-{index}")
        eval_gate = evidence.get("eval_gate")
        validation_tier = evidence.get("validation_tier")
        proposal_summary = evidence.get("proposal_summary") or finding.get("message")
    return {
        "candidate_id": f"STG-{index:03d}",
        "source": "priority0_gap_taxonomy",
        "source_finding": {
            "category": finding.get("category"),
            "severity": finding.get("severity"),
            "message": finding.get("message"),
            "report_label": finding.get("report_label"),
            "source": finding.get("source"),
        },
        "gap_class": evidence.get("gap_class"),
        "repair_action": evidence.get("bounded_repair_action"),
        "capability_type": capability_type,
        "capability_id": capability_id,
        "proposal_summary": proposal_summary,
        "eval_gate": eval_gate,
        "validation_tier": validation_tier,
        "approval_boundary": evidence.get("approval_boundary") or "roadmap_approval_required",
        "capability_backlog_ref": backlog_ref,
        "status": "proposed",
    }


def generate_gap_candidates(
    *,
    priority0_gap_taxonomy: dict[str, Any],
    capability_backlog: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        candidate_from_finding(finding, index=index + 1, capability_backlog=capability_backlog)
        for index, finding in enumerate(extract_skill_tool_findings(priority0_gap_taxonomy))
    ]


def build_skill_tool_coverage_gap_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    priority0_gap_taxonomy: dict[str, Any],
    prompt_tightening_report: dict[str, Any],
    capability_backlog: dict[str, Any],
    prompt_coverage: dict[str, Any],
    policy_path: Path | None = None,
    priority0_gap_taxonomy_path: Path | None = None,
    prompt_tightening_report_path: Path | None = None,
    capability_backlog_path: Path | None = None,
    prompt_coverage_path: Path | None = None,
) -> dict[str, Any]:
    del config_root
    candidates = generate_gap_candidates(
        priority0_gap_taxonomy=priority0_gap_taxonomy,
        capability_backlog=capability_backlog,
    )
    non_skill_tool_records = prompt_tightening_non_skill_tool_records(prompt_tightening_report)
    implemented = implemented_coverage_entries(prompt_coverage)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": SkillToolCoverageGapStatus.PASSED.value,
        "generated_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path) if policy_path else None,
        "priority0_gap_taxonomy_path": str(priority0_gap_taxonomy_path or DEFAULT_PRIORITY0_GAP_TAXONOMY_PATH),
        "priority0_gap_taxonomy_sha256": artifact_hash(priority0_gap_taxonomy_path)
        if priority0_gap_taxonomy_path
        else None,
        "prompt_tightening_report_path": str(prompt_tightening_report_path or DEFAULT_PROMPT_TIGHTENING_REPORT_PATH),
        "prompt_tightening_report_sha256": artifact_hash(prompt_tightening_report_path)
        if prompt_tightening_report_path
        else None,
        "capability_backlog_path": str(capability_backlog_path or DEFAULT_CAPABILITY_BACKLOG_PATH),
        "capability_backlog_sha256": artifact_hash(capability_backlog_path) if capability_backlog_path else None,
        "prompt_coverage_path": str(prompt_coverage_path or DEFAULT_PROMPT_COVERAGE_PATH),
        "prompt_coverage_sha256": artifact_hash(prompt_coverage_path) if prompt_coverage_path else None,
        "gap_candidates": candidates,
        "non_skill_tool_records": non_skill_tool_records,
        "summary": {
            "skill_tool_finding_count": len(extract_skill_tool_findings(priority0_gap_taxonomy)),
            "gap_candidate_count": len(candidates),
            "prompt_tightening_candidate_count": len(non_skill_tool_records),
            "implemented_coverage_entry_count": len(implemented),
            "new_capability_required": bool(candidates),
            "next_action": "none" if not candidates else "review proposed skill/tool gaps before adding skills or tools",
        },
        "errors": [],
    }


def validate_gap_candidate(candidate: dict[str, Any], *, policy: dict[str, Any], prefix: str) -> list[str]:
    errors: list[str] = []
    if candidate.get("gap_class") != SKILL_TOOL_GAP_CLASS:
        errors.append(f"{prefix}.gap_class must be {SKILL_TOOL_GAP_CLASS}")
    required = set(string_list(policy.get("required_proposal_fields")))
    for field in sorted(required):
        value = candidate.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{prefix}.{field} must be a non-empty string")
    if candidate.get("capability_type") not in {"skill", "tool", "skill_and_tool"}:
        errors.append(f"{prefix}.capability_type must be skill, tool, or skill_and_tool")
    if candidate.get("repair_type") and candidate.get("repair_type") not in set(string_list(policy.get("allowed_repair_types"))):
        errors.append(f"{prefix}.repair_type must be governed")
    if candidate.get("validation_tier") not in set(string_list(policy.get("allowed_validation_tiers"))):
        errors.append(f"{prefix}.validation_tier must be governed")
    if candidate.get("approval_boundary") not in set(string_list(policy.get("approval_boundary_values"))):
        errors.append(f"{prefix}.approval_boundary must be governed")
    if candidate.get("status") != "proposed":
        errors.append(f"{prefix}.status must be proposed")
    return errors


def validate_skill_tool_coverage_gap_report(
    report: dict[str, Any],
    *,
    policy: dict[str, Any],
    priority0_gap_taxonomy: dict[str, Any],
    prompt_tightening_report: dict[str, Any],
    capability_backlog: dict[str, Any],
    prompt_coverage: dict[str, Any],
) -> list[str]:
    errors = validate_policy(policy)
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("report.schema_version must be 1")
    if report.get("kind") != EXPECTED_REPORT_KIND:
        errors.append(f"report.kind must be {EXPECTED_REPORT_KIND}")
    if report.get("phase") != EXPECTED_PHASE:
        errors.append("report.phase must be 129")
    if report.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"report.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if priority0_gap_taxonomy.get("status") != "passed":
        errors.append("priority0_gap_taxonomy.status must be passed")
    if prompt_tightening_report.get("status") != "passed":
        errors.append("prompt_tightening_report.status must be passed")
    if capability_backlog.get("kind") != "natural_language_capability_gap_backlog":
        errors.append("capability_backlog.kind must be natural_language_capability_gap_backlog")
    if prompt_coverage.get("kind") != "prompt_skill_coverage_registry":
        errors.append("prompt_coverage.kind must be prompt_skill_coverage_registry")

    expected_candidates = generate_gap_candidates(
        priority0_gap_taxonomy=priority0_gap_taxonomy,
        capability_backlog=capability_backlog,
    )
    candidates = object_list(report.get("gap_candidates"))
    if len(candidates) != len(expected_candidates):
        errors.append("report.gap_candidates must match skill/tool findings")
    for index, candidate in enumerate(candidates):
        errors.extend(validate_gap_candidate(candidate, policy=policy, prefix=f"report.gap_candidates[{index}]"))

    expected_non_skill = prompt_tightening_non_skill_tool_records(prompt_tightening_report)
    if report.get("non_skill_tool_records") != expected_non_skill:
        errors.append("report.non_skill_tool_records must classify prompt-tightening candidates separately")
    summary = dict_value(report.get("summary"))
    skill_tool_count = len(extract_skill_tool_findings(priority0_gap_taxonomy))
    if summary.get("skill_tool_finding_count") != skill_tool_count:
        errors.append("summary.skill_tool_finding_count must match taxonomy findings")
    if summary.get("gap_candidate_count") != len(candidates):
        errors.append("summary.gap_candidate_count must match gap_candidates")
    if summary.get("prompt_tightening_candidate_count") != len(expected_non_skill):
        errors.append("summary.prompt_tightening_candidate_count must match prompt tightening records")
    if summary.get("new_capability_required") != bool(candidates):
        errors.append("summary.new_capability_required must match gap candidate presence")

    expected_status = SkillToolCoverageGapStatus.PASSED.value if not errors else SkillToolCoverageGapStatus.FAILED.value
    if report.get("status") != expected_status:
        errors.append(f"report.status must be {expected_status}")
    return errors


def run_skill_tool_coverage_gap_gate(config: SkillToolCoverageGapConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    priority0_path = resolve_path(config_root, config.priority0_gap_taxonomy_path)
    prompt_tightening_path = resolve_path(config_root, config.prompt_tightening_report_path)
    backlog_path = resolve_path(config_root, config.capability_backlog_path)
    coverage_path = resolve_path(config_root, config.prompt_coverage_path)
    required_paths = [policy_path, priority0_path, prompt_tightening_path, backlog_path, coverage_path]
    missing = [str(path) for path in required_paths if config.require_artifacts and not path.is_file()]
    policy = read_json_object(policy_path)
    priority0 = read_json_object(priority0_path) if priority0_path.is_file() else {}
    prompt_tightening = read_json_object(prompt_tightening_path) if prompt_tightening_path.is_file() else {}
    backlog = read_json_object(backlog_path) if backlog_path.is_file() else {}
    coverage = read_json_object(coverage_path) if coverage_path.is_file() else {}
    report = build_skill_tool_coverage_gap_report(
        config_root=config_root,
        policy=policy,
        priority0_gap_taxonomy=priority0,
        prompt_tightening_report=prompt_tightening,
        capability_backlog=backlog,
        prompt_coverage=coverage,
        policy_path=policy_path,
        priority0_gap_taxonomy_path=priority0_path,
        prompt_tightening_report_path=prompt_tightening_path,
        capability_backlog_path=backlog_path,
        prompt_coverage_path=coverage_path,
    )
    errors = [f"required artifact is missing: {path}" for path in missing]
    errors.extend(
        validate_skill_tool_coverage_gap_report(
            report,
            policy=policy,
            priority0_gap_taxonomy=priority0,
            prompt_tightening_report=prompt_tightening,
            capability_backlog=backlog,
            prompt_coverage=coverage,
        )
    )
    if errors:
        report["status"] = SkillToolCoverageGapStatus.FAILED.value
        report["errors"] = errors
        errors = [
            f"required artifact is missing: {path}" for path in missing
        ] + validate_skill_tool_coverage_gap_report(
            report,
            policy=policy,
            priority0_gap_taxonomy=priority0,
            prompt_tightening_report=prompt_tightening,
            capability_backlog=backlog,
            prompt_coverage=coverage,
        )
        report["errors"] = errors
    report["summary"]["error_count"] = len(report["errors"])
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
