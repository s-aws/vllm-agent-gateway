"""Failure-to-roadmap proposal gate for Priority 0 hardening."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.failure_taxonomy import (
    FailureCategory,
    NEXT_ACTION_BY_CATEGORY,
    SEVERITY_BY_CATEGORY,
    classify_text,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "failure_to_roadmap_policy"
EXPECTED_REPORT_KIND = "failure_to_roadmap_report"
EXPECTED_PHASE = 148
EXPECTED_BACKLOG_ID = "P0-BB-020"
SUPPORTED_POLICY_BACKLOG_IDS = {
    148: "P0-BB-020",
    169: "P0-BB-033",
}
DEFAULT_POLICY_PATH = Path("runtime") / "failure_to_roadmap_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "failure-to-roadmap" / "phase148"
SUPPORTED_FINDING_EXTRACTORS = {
    "failed_status",
    "prompt_advisory_product_gap_escalations",
}


class FailureToRoadmapStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class FailureToRoadmapConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"failure-to-roadmap-{utc_timestamp()}.json"


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
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "unknown"


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    phase = policy.get("phase")
    if phase not in SUPPORTED_POLICY_BACKLOG_IDS:
        errors.append("policy.phase must be one of " + ", ".join(str(item) for item in sorted(SUPPORTED_POLICY_BACKLOG_IDS)))
    expected_backlog_id = SUPPORTED_POLICY_BACKLOG_IDS.get(phase)
    if expected_backlog_id is not None and policy.get("priority_backlog_id") != expected_backlog_id:
        errors.append(f"policy.priority_backlog_id must be {expected_backlog_id}")
    reports = object_list(policy.get("source_reports"))
    if not reports:
        errors.append("policy.source_reports must contain at least one report")
    ids = [str(item.get("id")) for item in reports if isinstance(item.get("id"), str)]
    if len(ids) != len(set(ids)):
        errors.append("policy.source_reports must have unique ids")
    for index, report in enumerate(reports):
        prefix = f"policy.source_reports[{index}]"
        if not isinstance(report.get("id"), str) or not report["id"].strip():
            errors.append(f"{prefix}.id is required")
        if not isinstance(report.get("path"), str) or not report["path"].strip():
            errors.append(f"{prefix}.path is required")
        if report.get("required") is not True:
            errors.append(f"{prefix}.required must be true")
        if report.get("expected_status") != "passed":
            errors.append(f"{prefix}.expected_status must be passed")
        extractors = string_list(report.get("finding_extractors")) or ["failed_status"]
        unsupported_extractors = sorted(set(extractors) - SUPPORTED_FINDING_EXTRACTORS)
        if unsupported_extractors:
            errors.append(f"{prefix}.finding_extractors contains unsupported value(s): {', '.join(unsupported_extractors)}")
    proposal_policy = dict_value(policy.get("proposal_policy"))
    if proposal_policy.get("default_approval_status") != "unapproved":
        errors.append("proposal_policy.default_approval_status must be unapproved")
    if proposal_policy.get("implementation_status") != "not_started":
        errors.append("proposal_policy.implementation_status must be not_started")
    if proposal_policy.get("roadmap_mutation_allowed") is not False:
        errors.append("proposal_policy.roadmap_mutation_allowed must be false")
    if proposal_policy.get("source_mutation_allowed") is not False:
        errors.append("proposal_policy.source_mutation_allowed must be false")
    if set(string_list(proposal_policy.get("allowed_approval_statuses"))) != {"unapproved", "approved_by_founder"}:
        errors.append("proposal_policy.allowed_approval_statuses must be unapproved and approved_by_founder")
    if set(string_list(proposal_policy.get("release_blocker_severities"))) != {"critical", "high"}:
        errors.append("proposal_policy.release_blocker_severities must be critical and high")
    if not string_list(proposal_policy.get("required_proposal_fields")):
        errors.append("proposal_policy.required_proposal_fields must be a non-empty list")
    return errors


def source_ref(path: Path | None, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path) if path else None,
        "sha256": artifact_hash(path),
        "kind": report.get("kind"),
        "status": report.get("status"),
        "phase": report.get("phase"),
    }


def source_message(report: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("errors", "failures", "findings"):
        value = report.get(key)
        if isinstance(value, list):
            parts.extend(json.dumps(item, ensure_ascii=True, sort_keys=True) for item in value)
    summary = report.get("summary")
    if isinstance(summary, dict):
        parts.append(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    return "\n".join(parts) if parts else json.dumps(report, ensure_ascii=True, sort_keys=True)


def finding_from_source(report_id: str, path: Path, report: dict[str, Any]) -> dict[str, Any] | None:
    status = report.get("status")
    errors = report.get("errors")
    if status == "passed" and errors in (None, []):
        return None
    message = source_message(report)
    category, matched_terms = classify_text(message)
    if category == FailureCategory.UNKNOWN and status != "passed":
        category = FailureCategory.HARNESS_ERROR
    severity = SEVERITY_BY_CATEGORY[category]
    return {
        "finding_id": f"FTR-{slug(report_id)}-001",
        "source_report_id": report_id,
        "source_path": str(path),
        "report_kind": report.get("kind"),
        "report_status": status,
        "category": category.value,
        "severity": severity,
        "message": message[:1200],
        "matched_terms": matched_terms,
        "recommended_next_action": NEXT_ACTION_BY_CATEGORY[category],
    }


def product_gap_findings_from_source(report_id: str, path: Path, report: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for record in object_list(report.get("closure_records")):
        if record.get("decision") != "product_gap_escalation":
            continue
        case_id = str(record.get("case_id") or "unknown")
        classification_message = json.dumps(
            {
                "case_id": case_id,
                "risk": record.get("risk"),
                "rationale": record.get("rationale"),
                "refined_prompt": record.get("refined_prompt"),
                "refined_score": record.get("refined_score"),
                "refined_classification": record.get("refined_classification"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
        message = json.dumps(
            {
                "case_id": case_id,
                "risk": record.get("risk"),
                "rationale": record.get("rationale"),
                "refined_prompt": record.get("refined_prompt"),
                "refined_score": record.get("refined_score"),
                "refined_classification": record.get("refined_classification"),
                "route_surface": record.get("route_surface"),
                "target_root": record.get("target_root"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
        category, matched_terms = classify_text(classification_message)
        if category == FailureCategory.UNKNOWN:
            category = FailureCategory.PROMPT_AMBIGUITY
        severity = SEVERITY_BY_CATEGORY[category]
        findings.append(
            {
                "finding_id": f"FTR-{slug(report_id)}-{slug(case_id)}",
                "source_report_id": report_id,
                "source_path": str(path),
                "report_kind": report.get("kind"),
                "report_status": report.get("status"),
                "category": category.value,
                "severity": severity,
                "message": message[:1200],
                "matched_terms": matched_terms,
                "recommended_next_action": NEXT_ACTION_BY_CATEGORY[category],
                "source_case_id": case_id,
                "phase158_finding_id": record.get("phase158_finding_id"),
                "refined_run_id": record.get("refined_run_id"),
                "refined_response_artifact_path": record.get("refined_response_artifact_path"),
                "refined_response_artifact_sha256": record.get("refined_response_artifact_sha256"),
            }
        )
    return findings


def findings_from_source(
    *,
    report_id: str,
    path: Path,
    report: dict[str, Any],
    extractors: list[str],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if "failed_status" in extractors:
        finding = finding_from_source(report_id, path, report)
        if finding is not None:
            findings.append(finding)
    if "prompt_advisory_product_gap_escalations" in extractors:
        findings.extend(product_gap_findings_from_source(report_id, path, report))
    return findings


def candidate_phase_title(finding: dict[str, Any]) -> str:
    return "Repair " + str(finding.get("category", "unknown")).replace("_", " ").title()


def recommended_position(finding: dict[str, Any], release_blocker_severities: set[str]) -> str:
    return "before continuing approved release phases" if finding.get("severity") in release_blocker_severities else "after Phase 156 proposal review"


def proposal_from_finding(
    finding: dict[str, Any],
    *,
    index: int,
    phase: int,
    proposal_policy: dict[str, Any],
) -> dict[str, Any]:
    release_blocker_severities = set(string_list(proposal_policy.get("release_blocker_severities")))
    approved_ids = set(string_list(proposal_policy.get("approved_proposal_ids")))
    source_suffix = slug(str(finding.get("source_case_id") or finding.get("source_report_id") or "source"))
    proposal_id = f"FTR-P{phase}-{index:03d}-{source_suffix}"
    approval_status = "approved_by_founder" if proposal_id in approved_ids else "unapproved"
    category = str(finding.get("category") or "unknown")
    severity = str(finding.get("severity") or "medium")
    title = candidate_phase_title(finding)
    return {
        "proposal_id": proposal_id,
        "approval_status": approval_status,
        "implementation_status": proposal_policy.get("implementation_status"),
        "release_blocker": severity in release_blocker_severities,
        "severity": severity,
        "category": category,
        "source_report_id": finding.get("source_report_id"),
        "source_path": finding.get("source_path"),
        "evidence": {
            "finding_id": finding.get("finding_id"),
            "report_kind": finding.get("report_kind"),
            "report_status": finding.get("report_status"),
            "matched_terms": finding.get("matched_terms"),
            "message": finding.get("message"),
        },
        "candidate_phase_title": title,
        "goal": f"Close {category} finding from {finding.get('source_report_id')} without changing unrelated product scope.",
        "implementation_tasks": [
            "Reproduce the source failure from the linked report.",
            "Identify whether the root cause is docs, setup, routing, formatter, model quality, skill/tool selection, or safety boundary.",
            "Repair the smallest existing path that owns the failure.",
            "Rerun the source gate and one holdout when applicable.",
            "Update roadmap state only after founder approval if this proposal expands scope.",
        ],
        "acceptance_proof": [
            "Source report reruns with status=passed.",
            "No protected fixture mutation is introduced.",
            "Full regression passes for any non-agent code change.",
            "Roadmap records the approved scope before implementation if this remains a new phase.",
        ],
        "dependencies": [
            str(finding.get("source_report_id")),
            str(finding.get("source_path")),
        ],
        "recommended_roadmap_position": recommended_position(finding, release_blocker_severities),
    }


def validate_proposal(proposal: dict[str, Any], *, proposal_policy: dict[str, Any], prefix: str) -> list[str]:
    errors: list[str] = []
    required = string_list(proposal_policy.get("required_proposal_fields"))
    for field in required:
        value = proposal.get(field)
        if isinstance(value, str):
            if not value.strip():
                errors.append(f"{prefix}.{field} must be non-empty")
        elif isinstance(value, list):
            if not value:
                errors.append(f"{prefix}.{field} must be non-empty")
        elif isinstance(value, dict):
            if not value:
                errors.append(f"{prefix}.{field} must be non-empty")
        elif value is None:
            errors.append(f"{prefix}.{field} is required")
    allowed_statuses = set(string_list(proposal_policy.get("allowed_approval_statuses")))
    if proposal.get("approval_status") not in allowed_statuses:
        errors.append(f"{prefix}.approval_status must be allowed")
    if proposal.get("implementation_status") != proposal_policy.get("implementation_status"):
        errors.append(f"{prefix}.implementation_status must be {proposal_policy.get('implementation_status')}")
    if proposal.get("approval_status") == "approved_by_founder" and not string_list(proposal_policy.get("approved_proposal_ids")):
        errors.append(f"{prefix}.approval_status cannot be approved without approved_proposal_ids")
    return errors


def build_failure_to_roadmap_report(
    *,
    policy: dict[str, Any],
    source_reports: dict[str, tuple[Path | None, dict[str, Any]]],
    policy_path: Path | None = None,
) -> dict[str, Any]:
    errors = validate_policy(policy)
    proposal_policy = dict_value(policy.get("proposal_policy"))
    report_phase = policy.get("phase") if isinstance(policy.get("phase"), int) else EXPECTED_PHASE
    priority_backlog_id = (
        policy.get("priority_backlog_id") if isinstance(policy.get("priority_backlog_id"), str) else EXPECTED_BACKLOG_ID
    )
    findings: list[dict[str, Any]] = []
    missing_report_ids: list[str] = []
    for source in object_list(policy.get("source_reports")):
        report_id = str(source.get("id"))
        path, report = source_reports.get(report_id, (None, {}))
        if path is None:
            missing_report_ids.append(report_id)
            continue
        extractors = string_list(source.get("finding_extractors")) or ["failed_status"]
        findings.extend(
            findings_from_source(
                report_id=report_id,
                path=path,
                report=report,
                extractors=extractors,
            )
        )
        if source.get("expected_status") == "passed" and report.get("status") != "passed":
            # The finding becomes a proposal; the report itself still records that this source is blocking.
            pass
    if missing_report_ids:
        errors.append("missing required source reports: " + ", ".join(sorted(missing_report_ids)))
    proposals = [
        proposal_from_finding(finding, index=index + 1, phase=report_phase, proposal_policy=proposal_policy)
        for index, finding in enumerate(findings)
    ]
    proposal_ids = [str(item.get("proposal_id")) for item in proposals]
    if len(proposal_ids) != len(set(proposal_ids)):
        errors.append("generated proposal ids must be unique")
    for index, proposal in enumerate(proposals):
        errors.extend(validate_proposal(proposal, proposal_policy=proposal_policy, prefix=f"proposals[{index}]"))
    release_blocker_count = sum(1 for proposal in proposals if proposal.get("release_blocker") is True)
    unapproved_count = sum(1 for proposal in proposals if proposal.get("approval_status") == "unapproved")
    approved_count = sum(1 for proposal in proposals if proposal.get("approval_status") == "approved_by_founder")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": report_phase,
        "priority_backlog_id": priority_backlog_id,
        "status": FailureToRoadmapStatus.PASSED.value if not errors else FailureToRoadmapStatus.FAILED.value,
        "generated_at": utc_timestamp(),
        "policy_ref": source_ref(policy_path, policy),
        "source_refs": {
            report_id: source_ref(path, report) for report_id, (path, report) in source_reports.items()
        },
        "findings": findings,
        "proposals": proposals,
        "summary": {
            "source_report_count": len(source_reports),
            "finding_count": len(findings),
            "proposal_count": len(proposals),
            "unapproved_proposal_count": unapproved_count,
            "approved_proposal_count": approved_count,
            "release_blocker_count": release_blocker_count,
            "roadmap_mutation_allowed": proposal_policy.get("roadmap_mutation_allowed"),
            "source_mutation_allowed": proposal_policy.get("source_mutation_allowed"),
            "error_count": len(errors),
        },
        "errors": errors,
    }


def validate_failure_to_roadmap_report(
    report: dict[str, Any],
    *,
    policy: dict[str, Any],
    source_reports: dict[str, tuple[Path | None, dict[str, Any]]],
    policy_path: Path | None = None,
) -> list[str]:
    expected = build_failure_to_roadmap_report(
        policy=policy,
        source_reports=source_reports,
        policy_path=policy_path,
    )
    errors: list[str] = []
    for key in (
        "schema_version",
        "kind",
        "phase",
        "priority_backlog_id",
        "status",
        "policy_ref",
        "source_refs",
        "findings",
        "proposals",
        "summary",
        "errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append(f"report.{key} must match rebuilt failure-to-roadmap report")
    return errors


def load_source_reports(
    *,
    config_root: Path,
    policy: dict[str, Any],
    require_artifacts: bool,
) -> tuple[dict[str, tuple[Path | None, dict[str, Any]]], list[str]]:
    reports: dict[str, tuple[Path | None, dict[str, Any]]] = {}
    errors: list[str] = []
    for source in object_list(policy.get("source_reports")):
        report_id = str(source.get("id"))
        path_value = source.get("path")
        if not isinstance(path_value, str):
            reports[report_id] = (None, {})
            errors.append(f"source report {report_id} path is invalid")
            continue
        path = resolve_path(config_root, path_value)
        if not path.is_file():
            reports[report_id] = (None, {})
            if require_artifacts or source.get("required") is True:
                errors.append(f"required source report is missing: {path_value}")
            continue
        reports[report_id] = (path, read_json_object(path))
    return reports, errors


def run_failure_to_roadmap(config: FailureToRoadmapConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path) if policy_path.is_file() else {}
    source_reports, load_errors = load_source_reports(
        config_root=config_root,
        policy=policy,
        require_artifacts=config.require_artifacts,
    )
    report = build_failure_to_roadmap_report(
        policy=policy,
        source_reports=source_reports,
        policy_path=policy_path if policy_path.is_file() else None,
    )
    if load_errors:
        report["status"] = FailureToRoadmapStatus.FAILED.value
        report["errors"] = list(report.get("errors", [])) + load_errors
        report["summary"]["error_count"] = len(report["errors"])
    validation_errors = validate_failure_to_roadmap_report(
        report,
        policy=policy,
        source_reports=source_reports,
        policy_path=policy_path if policy_path.is_file() else None,
    )
    if validation_errors:
        report["status"] = FailureToRoadmapStatus.FAILED.value
        report["errors"] = list(report.get("errors", [])) + validation_errors
        report["summary"]["error_count"] = len(report["errors"])
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
