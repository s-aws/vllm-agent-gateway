"""Governed intake for Priority 0 skill/tool gap proposals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.skill_tool_coverage_gap import (
    artifact_hash,
    object_list,
    read_json_object,
    resolve_path,
    string_list,
    validate_policy as validate_skill_tool_gap_policy,
    validate_gap_candidate as validate_source_gap_candidate,
    write_json,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "skill_tool_gap_proposal_intake_policy"
EXPECTED_REPORT_KIND = "skill_tool_gap_proposal_intake_report"
EXPECTED_PHASE = 143
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_POLICY_PATH = Path("runtime") / "skill_tool_gap_proposal_intake_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "skill-tool-gap-proposal-intake" / "phase143"
IMPLEMENTATION_NOT_STARTED = "not_started"


class SkillToolGapProposalIntakeStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class SkillToolGapProposalIntakeConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"skill-tool-gap-proposal-intake-{utc_timestamp()}.json"


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def artifact_ref_errors(
    *,
    config_root: Path,
    prefix: str,
    ref: dict[str, Any],
    required: bool,
) -> list[str]:
    path_value = ref.get("path")
    hash_value = ref.get("sha256")
    errors: list[str] = []
    if not isinstance(path_value, str) or not path_value.strip():
        return [f"{prefix}.path is required"]
    if not isinstance(hash_value, str) or len(hash_value) != 64:
        errors.append(f"{prefix}.sha256 must be a 64-character hash")
    path = resolve_path(config_root, path_value)
    if not path.is_file():
        if required:
            errors.append(f"{prefix}.path does not exist: {path_value}")
        return errors
    actual = artifact_hash(path)
    if actual != hash_value:
        errors.append(f"{prefix}.sha256 is stale for {path_value}")
    return errors


def source_refs(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "source_skill_tool_gap_report": dict_value(policy.get("source_skill_tool_gap_report")),
        "source_policy": dict_value(policy.get("source_policy")),
        "source_prompt_coverage": dict_value(policy.get("source_prompt_coverage")),
        "source_capability_backlog": dict_value(policy.get("source_capability_backlog")),
    }


def validate_intake_policy_shape(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 143")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    proposal_policy = dict_value(policy.get("proposal_policy"))
    for key in (
        "allowed_sources",
        "allowed_capability_types",
        "allowed_statuses",
        "required_fields",
        "allowed_validation_tiers",
        "allowed_approval_boundaries",
    ):
        if not string_list(proposal_policy.get(key)):
            errors.append(f"proposal_policy.{key} must be a non-empty string array")
    for key in (
        "implementation_before_approval_allowed",
        "source_mutation_allowed",
        "auto_register_allowed",
    ):
        if proposal_policy.get(key) is not False:
            errors.append(f"proposal_policy.{key} must be false")
    if proposal_policy.get("prompt_or_formatter_repair_must_be_insufficient") is not True:
        errors.append("proposal_policy.prompt_or_formatter_repair_must_be_insufficient must be true")
    return errors


def source_candidate_by_id(source_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(candidate.get("candidate_id")): candidate
        for candidate in object_list(source_report.get("gap_candidates"))
        if isinstance(candidate.get("candidate_id"), str)
    }


def validate_source_reports(
    policy: dict[str, Any],
    *,
    config_root: Path,
    require_artifacts: bool,
) -> tuple[list[str], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    errors: list[str] = []
    refs = source_refs(policy)
    for key, ref in refs.items():
        errors.extend(artifact_ref_errors(config_root=config_root, prefix=key, ref=ref, required=require_artifacts))
    source_report: dict[str, Any] = {}
    source_policy: dict[str, Any] = {}
    prompt_coverage: dict[str, Any] = {}
    capability_backlog: dict[str, Any] = {}
    if errors:
        return errors, source_report, source_policy, prompt_coverage, capability_backlog
    source_report = read_json_object(resolve_path(config_root, str(refs["source_skill_tool_gap_report"]["path"])))
    source_policy = read_json_object(resolve_path(config_root, str(refs["source_policy"]["path"])))
    prompt_coverage = read_json_object(resolve_path(config_root, str(refs["source_prompt_coverage"]["path"])))
    capability_backlog = read_json_object(resolve_path(config_root, str(refs["source_capability_backlog"]["path"])))
    errors.extend(validate_skill_tool_gap_policy(source_policy))
    if source_report.get("kind") != "skill_tool_coverage_gap_report":
        errors.append("source_skill_tool_gap_report.kind must be skill_tool_coverage_gap_report")
    if source_report.get("errors") not in ([], None):
        errors.append("source_skill_tool_gap_report.errors must be empty")
    if prompt_coverage.get("kind") != "prompt_skill_coverage_registry":
        errors.append("source_prompt_coverage.kind must be prompt_skill_coverage_registry")
    if capability_backlog.get("kind") != "natural_language_capability_gap_backlog":
        errors.append("source_capability_backlog.kind must be natural_language_capability_gap_backlog")
    summary = dict_value(source_report.get("summary"))
    gap_candidates = object_list(source_report.get("gap_candidates"))
    if summary.get("gap_candidate_count") != len(gap_candidates):
        errors.append("source_skill_tool_gap_report.summary.gap_candidate_count must match gap_candidates")
    if summary.get("new_capability_required") != bool(gap_candidates):
        errors.append("source_skill_tool_gap_report.summary.new_capability_required must match gap_candidates")
    for index, candidate in enumerate(gap_candidates):
        errors.extend(validate_source_gap_candidate(candidate, policy=source_policy, prefix=f"source_gap_candidates[{index}]"))
    expected_status = refs["source_skill_tool_gap_report"].get("expected_status")
    if expected_status and source_report.get("status") != expected_status:
        errors.append("source_skill_tool_gap_report.status does not match expected_status")
    expected_capability = refs["source_skill_tool_gap_report"].get("expected_new_capability_required")
    summary = dict_value(source_report.get("summary"))
    if isinstance(expected_capability, bool) and summary.get("new_capability_required") != expected_capability:
        errors.append("source_skill_tool_gap_report.summary.new_capability_required does not match expected")
    return errors, source_report, source_policy, prompt_coverage, capability_backlog


def validate_proposal(
    proposal: dict[str, Any],
    *,
    source_candidates: dict[str, dict[str, Any]],
    proposal_policy: dict[str, Any],
    prefix: str,
) -> list[str]:
    errors: list[str] = []
    required_fields = string_list(proposal_policy.get("required_fields"))
    for field in required_fields:
        value = proposal.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{prefix}.{field} is required")
    source_candidate_id = str(proposal.get("source_candidate_id") or "")
    source_candidate = source_candidates.get(source_candidate_id)
    if source_candidate is None:
        errors.append(f"{prefix}.source_candidate_id must reference a source gap candidate")
    if proposal.get("source") not in set(string_list(proposal_policy.get("allowed_sources"))):
        errors.append(f"{prefix}.source must be an allowed source")
    if proposal.get("capability_type") not in set(string_list(proposal_policy.get("allowed_capability_types"))):
        errors.append(f"{prefix}.capability_type must be allowed")
    if proposal.get("status") not in set(string_list(proposal_policy.get("allowed_statuses"))):
        errors.append(f"{prefix}.status must be allowed")
    if proposal.get("validation_tier") not in set(string_list(proposal_policy.get("allowed_validation_tiers"))):
        errors.append(f"{prefix}.validation_tier must be allowed")
    if proposal.get("approval_boundary") not in set(string_list(proposal_policy.get("allowed_approval_boundaries"))):
        errors.append(f"{prefix}.approval_boundary must be allowed")
    if proposal.get("implementation_status") != IMPLEMENTATION_NOT_STARTED:
        errors.append(f"{prefix}.implementation_status must be {IMPLEMENTATION_NOT_STARTED}")
    if proposal.get("auto_register") is not False:
        errors.append(f"{prefix}.auto_register must be false")
    if proposal.get("source_mutation_required") is not False:
        errors.append(f"{prefix}.source_mutation_required must be false")
    if proposal.get("prompt_or_formatter_repair_insufficient") is not True:
        errors.append(f"{prefix}.prompt_or_formatter_repair_insufficient must be true")
    if not isinstance(proposal.get("scope"), str) or len(proposal["scope"].strip()) < 30:
        errors.append(f"{prefix}.scope must be concrete")
    if source_candidate is not None:
        for field in ("capability_type", "capability_id", "eval_gate", "validation_tier", "approval_boundary"):
            if proposal.get(field) != source_candidate.get(field):
                errors.append(f"{prefix}.{field} must match source gap candidate")
    return errors


def validate_intake_policy(policy: dict[str, Any], *, config_root: Path, require_artifacts: bool = False) -> list[str]:
    errors = validate_intake_policy_shape(policy)
    source_errors, source_report, _source_policy, _coverage, _backlog = validate_source_reports(
        policy,
        config_root=config_root,
        require_artifacts=require_artifacts,
    )
    errors.extend(source_errors)
    proposals = object_list(policy.get("proposals"))
    proposal_ids = [str(item.get("proposal_id")) for item in proposals if isinstance(item.get("proposal_id"), str)]
    duplicates = duplicate_values(proposal_ids)
    if duplicates:
        errors.append("proposals contain duplicate proposal_id values: " + ", ".join(duplicates))
    if not source_errors:
        source_candidates = source_candidate_by_id(source_report)
        source_ids = set(source_candidates)
        proposal_source_ids = {
            str(item.get("source_candidate_id"))
            for item in proposals
            if isinstance(item.get("source_candidate_id"), str)
        }
        missing_proposals = sorted(source_ids - proposal_source_ids)
        if missing_proposals:
            errors.append("proposals missing source gap candidate(s): " + ", ".join(missing_proposals))
        extra_proposals = sorted(proposal_source_ids - source_ids)
        if extra_proposals:
            errors.append("proposals reference unknown source gap candidate(s): " + ", ".join(extra_proposals))
        proposal_policy = dict_value(policy.get("proposal_policy"))
        for index, proposal in enumerate(proposals):
            errors.extend(
                validate_proposal(
                    proposal,
                    source_candidates=source_candidates,
                    proposal_policy=proposal_policy,
                    prefix=f"proposals[{proposal.get('proposal_id') or index}]",
                )
            )
    return errors


def build_intake_report(
    *,
    policy: dict[str, Any],
    config_root: Path,
    policy_path: Path | None = None,
    require_artifacts: bool = False,
) -> dict[str, Any]:
    errors = validate_intake_policy(policy, config_root=config_root, require_artifacts=require_artifacts)
    source_errors, source_report, _source_policy, _coverage, _backlog = validate_source_reports(
        policy,
        config_root=config_root,
        require_artifacts=require_artifacts,
    )
    del source_errors
    proposals = object_list(policy.get("proposals"))
    source_candidates = object_list(source_report.get("gap_candidates"))
    status_counts: dict[str, int] = {}
    for proposal in proposals:
        status = str(proposal.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    refs = source_refs(policy)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": SkillToolGapProposalIntakeStatus.PASSED.value if not errors else SkillToolGapProposalIntakeStatus.FAILED.value,
        "generated_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path) if policy_path else None,
        "source_skill_tool_gap_report_path": refs["source_skill_tool_gap_report"].get("path"),
        "source_skill_tool_gap_report_sha256": refs["source_skill_tool_gap_report"].get("sha256"),
        "source_gap_candidate_count": len(source_candidates),
        "proposals": [
            {
                "proposal_id": proposal.get("proposal_id"),
                "source_candidate_id": proposal.get("source_candidate_id"),
                "capability_type": proposal.get("capability_type"),
                "capability_id": proposal.get("capability_id"),
                "status": proposal.get("status"),
                "validation_tier": proposal.get("validation_tier"),
                "approval_boundary": proposal.get("approval_boundary"),
                "implementation_status": proposal.get("implementation_status"),
            }
            for proposal in proposals
        ],
        "summary": {
            "source_gap_candidate_count": len(source_candidates),
            "proposal_count": len(proposals),
            "pending_approval_count": status_counts.get("pending_approval", 0),
            "approved_for_future_phase_count": status_counts.get("approved_for_future_phase", 0),
            "rejected_count": status_counts.get("rejected", 0),
            "error_count": len(errors),
        },
        "errors": errors,
    }


def validate_intake_report(
    report: dict[str, Any],
    *,
    policy: dict[str, Any],
    config_root: Path,
    policy_path: Path | None = None,
    require_artifacts: bool = False,
) -> list[str]:
    expected = build_intake_report(
        policy=policy,
        config_root=config_root,
        policy_path=policy_path,
        require_artifacts=require_artifacts,
    )
    errors: list[str] = []
    for key in (
        "schema_version",
        "kind",
        "phase",
        "priority_backlog_id",
        "status",
        "policy_path",
        "policy_sha256",
        "source_skill_tool_gap_report_path",
        "source_skill_tool_gap_report_sha256",
        "source_gap_candidate_count",
        "proposals",
        "summary",
        "errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append(f"report.{key} must match rebuilt skill/tool gap proposal intake report")
    return errors


def run_skill_tool_gap_proposal_intake(config: SkillToolGapProposalIntakeConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path) if policy_path.is_file() else {}
    missing_errors = []
    if config.require_artifacts and not policy_path.is_file():
        missing_errors.append(f"required policy artifact is missing: {policy_path}")
    report = build_intake_report(
        policy=policy,
        config_root=config_root,
        policy_path=policy_path,
        require_artifacts=config.require_artifacts,
    )
    validation_errors = validate_intake_report(
        report,
        policy=policy,
        config_root=config_root,
        policy_path=policy_path,
        require_artifacts=config.require_artifacts,
    )
    if missing_errors or validation_errors:
        report["status"] = SkillToolGapProposalIntakeStatus.FAILED.value
        report["errors"] = missing_errors + validation_errors
        report["summary"]["error_count"] = len(report["errors"])
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
