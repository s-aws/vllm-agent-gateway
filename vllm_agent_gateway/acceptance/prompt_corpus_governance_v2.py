"""Phase 179 prompt corpus governance V2."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "prompt_corpus_governance_v2_policy"
EXPECTED_REPORT_KIND = "prompt_corpus_governance_v2_report"
EXPECTED_CATALOG_KIND = "prompt_catalog"
EXPECTED_DELTA_KIND = "blind_baseline_delta_report"
EXPECTED_PHASE = 179
EXPECTED_BACKLOG_ID = "P0-BB-043"
DEFAULT_POLICY_PATH = Path("runtime") / "prompt_corpus_governance_v2.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase179" / "phase179-prompt-corpus-governance-v2-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase179" / "phase179-prompt-corpus-governance-v2-report.md"
ROLE_KEYS = ("target", "holdout", "regression", "promotion_candidate", "retired")
APPROVED_STATUSES = {"approved_for_promotion", "promoted"}


class PromptCorpusGovernanceStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class PromptCorpusGovernanceV2Config:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_OUTPUT_PATH


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


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


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def catalog_case_ids(catalog: dict[str, Any]) -> list[str]:
    return [str(case.get("case_id")) for case in object_list(catalog.get("cases")) if isinstance(case.get("case_id"), str)]


def role_sets(policy: dict[str, Any]) -> dict[str, set[str]]:
    roles = dict_value(policy.get("roles"))
    return {role: set(string_list(roles.get(role))) for role in ROLE_KEYS}


def delta_lookup(delta_report: dict[str, Any] | None) -> dict[tuple[str, str, str], dict[str, Any]]:
    if not delta_report:
        return {}
    lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in object_list(delta_report.get("deltas")):
        key = (str(item.get("family") or ""), str(item.get("role") or ""), str(item.get("case_id") or ""))
        lookup[key] = item
    return lookup


def validate_policy(policy: dict[str, Any], catalog: dict[str, Any], delta_report: dict[str, Any] | None = None) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append({"id": "policy.schema_version", "severity": "high", "message": "policy.schema_version must be 1"})
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append({"id": "policy.kind", "severity": "high", "message": f"policy.kind must be {EXPECTED_POLICY_KIND}"})
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append({"id": "policy.phase", "severity": "high", "message": "policy.phase must be 179"})
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append({"id": "policy.priority_backlog_id", "severity": "high", "message": f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}"})
    if catalog.get("kind") != EXPECTED_CATALOG_KIND:
        errors.append({"id": "catalog.kind", "severity": "high", "message": f"catalog.kind must be {EXPECTED_CATALOG_KIND}"})
    if delta_report is not None and delta_report.get("kind") != EXPECTED_DELTA_KIND:
        errors.append({"id": "delta.kind", "severity": "high", "message": f"delta.kind must be {EXPECTED_DELTA_KIND}"})
    if delta_report is not None and delta_report.get("status") != "passed":
        errors.append({"id": "delta.status", "severity": "high", "message": "delta report must pass before prompt-corpus promotion decisions"})

    case_ids = set(catalog_case_ids(catalog))
    if not case_ids:
        errors.append({"id": "catalog.cases", "severity": "high", "message": "catalog must contain prompt cases"})
    expected_case_count = policy.get("expected_catalog_case_count")
    if isinstance(expected_case_count, int) and expected_case_count != len(case_ids):
        errors.append({"id": "policy.expected_catalog_case_count", "severity": "high", "message": "expected catalog case count must match catalog"})
    roles = role_sets(policy)
    unknown_roles = set(dict_value(policy.get("roles"))) - set(ROLE_KEYS)
    if unknown_roles:
        errors.append({"id": "policy.roles", "severity": "high", "message": "unknown role keys: " + ", ".join(sorted(unknown_roles))})
    for role, ids in roles.items():
        unknown_ids = sorted(ids - case_ids)
        if unknown_ids:
            errors.append({"id": f"roles.{role}.unknown_case_ids", "severity": "high", "message": "unknown case IDs: " + ", ".join(unknown_ids)})
    assigned_ids = set().union(*roles.values()) if roles else set()
    unassigned = sorted(case_ids - assigned_ids)
    if unassigned:
        errors.append({"id": "roles.unassigned", "severity": "high", "message": "catalog cases missing corpus role: " + ", ".join(unassigned)})
    retired_overlap = sorted(roles["retired"] & (roles["target"] | roles["holdout"] | roles["regression"] | roles["promotion_candidate"]))
    if retired_overlap:
        errors.append({"id": "roles.retired_overlap", "severity": "high", "message": "retired cases cannot have active roles: " + ", ".join(retired_overlap)})
    if not roles["target"]:
        errors.append({"id": "roles.target", "severity": "high", "message": "target role must be non-empty"})
    if not roles["holdout"]:
        errors.append({"id": "roles.holdout", "severity": "high", "message": "holdout role must be non-empty"})
    if not roles["regression"]:
        errors.append({"id": "roles.regression", "severity": "high", "message": "regression role must be non-empty"})

    target_links = object_list(policy.get("target_holdout_links"))
    linked_targets = {str(item.get("target_case_id")) for item in target_links if isinstance(item.get("target_case_id"), str)}
    missing_links = sorted(roles["target"] - linked_targets)
    if missing_links:
        errors.append({"id": "target_holdout_links.missing", "severity": "high", "message": "target cases require explicit holdouts: " + ", ".join(missing_links)})
    delta_by_key = delta_lookup(delta_report)
    for index, link in enumerate(target_links):
        prefix = f"target_holdout_links[{index}]"
        family = str(link.get("family") or "")
        target_case_id = str(link.get("target_case_id") or "")
        holdout_ids = set(string_list(link.get("holdout_case_ids")))
        if not family:
            errors.append({"id": f"{prefix}.family", "severity": "high", "message": "family is required"})
        if target_case_id not in roles["target"]:
            errors.append({"id": f"{prefix}.target_case_id", "severity": "high", "message": "target_case_id must have target role"})
        if not holdout_ids:
            errors.append({"id": f"{prefix}.holdout_case_ids", "severity": "high", "message": "holdout_case_ids must be non-empty"})
        if target_case_id in holdout_ids:
            errors.append({"id": f"{prefix}.self_holdout", "severity": "high", "message": "target case cannot be its own holdout"})
        missing_holdout_role = sorted(holdout_ids - roles["holdout"])
        if missing_holdout_role:
            errors.append({"id": f"{prefix}.holdout_role", "severity": "high", "message": "holdouts must have holdout role: " + ", ".join(missing_holdout_role)})
        if delta_report is not None:
            target_delta = delta_by_key.get((family, "target", target_case_id))
            if not target_delta:
                errors.append({"id": f"{prefix}.target_delta", "severity": "high", "message": "target delta proof is missing"})
            for holdout_id in sorted(holdout_ids):
                holdout_delta = delta_by_key.get((family, "holdout", holdout_id))
                if not holdout_delta:
                    errors.append({"id": f"{prefix}.holdout_delta.{holdout_id}", "severity": "high", "message": "holdout delta proof is missing"})
                elif int(holdout_delta.get("score") or 0) < int(policy.get("minimum_holdout_score") or 85):
                    errors.append({"id": f"{prefix}.holdout_score.{holdout_id}", "severity": "high", "message": "holdout score is below minimum"})

    candidate_groups = object_list(policy.get("promotion_candidate_groups"))
    for index, group in enumerate(candidate_groups):
        prefix = f"promotion_candidate_groups[{index}]"
        case_ids_for_group = set(string_list(group.get("case_ids")))
        holdouts = set(string_list(group.get("required_holdout_case_ids")))
        status = str(group.get("decision_status") or "")
        if not case_ids_for_group:
            errors.append({"id": f"{prefix}.case_ids", "severity": "high", "message": "promotion candidate group must include case_ids"})
        if case_ids_for_group - roles["promotion_candidate"]:
            errors.append({"id": f"{prefix}.case_role", "severity": "high", "message": "group case_ids must have promotion_candidate role"})
        if not holdouts:
            errors.append({"id": f"{prefix}.required_holdout_case_ids", "severity": "high", "message": "promotion candidate group must include independent holdouts"})
        if holdouts - roles["holdout"]:
            errors.append({"id": f"{prefix}.holdout_role", "severity": "high", "message": "promotion candidate holdouts must have holdout role"})
        if status not in {"blocked_pending_evidence", "blocked_pending_founder_approval", "approved_for_promotion", "promoted"}:
            errors.append({"id": f"{prefix}.decision_status", "severity": "high", "message": "decision_status is unsupported"})
        if status == "promoted" and dict_value(policy.get("promotion_rules")).get("stable_corpus_update_requires_separate_phase") is True:
            errors.append({"id": f"{prefix}.promoted", "severity": "high", "message": "promoted status requires a separate stable-corpus update phase"})
        if status in APPROVED_STATUSES and dict_value(group.get("founder_approval")).get("status") != "approved":
            errors.append({"id": f"{prefix}.founder_approval", "severity": "high", "message": "approved promotion requires founder approval"})
        if status in APPROVED_STATUSES and delta_report is not None:
            missing_delta_holdouts = [
                holdout_id
                for holdout_id in sorted(holdouts)
                if not any(key[1] == "holdout" and key[2] == holdout_id for key in delta_by_key)
            ]
            if missing_delta_holdouts:
                errors.append({"id": f"{prefix}.delta_holdouts", "severity": "high", "message": "approved promotion missing delta holdout proof: " + ", ".join(missing_delta_holdouts)})
    if not candidate_groups:
        errors.append({"id": "promotion_candidate_groups", "severity": "high", "message": "at least one promotion candidate group is required"})
    return errors


def build_prompt_corpus_governance_v2_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    catalog: dict[str, Any],
    delta_report: dict[str, Any] | None,
    policy_path: Path | None = None,
    catalog_path: Path | None = None,
    delta_report_path: Path | None = None,
) -> dict[str, Any]:
    errors = validate_policy(policy, catalog, delta_report)
    roles = role_sets(policy)
    candidate_groups = object_list(policy.get("promotion_candidate_groups"))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": PromptCorpusGovernanceStatus.FAILED.value if errors else PromptCorpusGovernanceStatus.PASSED.value,
        "generated_at": utc_timestamp(),
        "policy_path": str(policy_path.resolve()) if policy_path else None,
        "policy_sha256": artifact_hash(policy_path),
        "source_catalog_path": str(catalog_path.resolve()) if catalog_path else None,
        "source_catalog_sha256": artifact_hash(catalog_path),
        "source_delta_report_path": str(delta_report_path.resolve()) if delta_report_path else None,
        "source_delta_report_sha256": artifact_hash(delta_report_path),
        "role_counts": {role: len(ids) for role, ids in roles.items()},
        "target_holdout_links": policy.get("target_holdout_links"),
        "promotion_candidate_groups": candidate_groups,
        "summary": {
            "catalog_case_count": len(catalog_case_ids(catalog)),
            "target_count": len(roles["target"]),
            "holdout_count": len(roles["holdout"]),
            "regression_count": len(roles["regression"]),
            "promotion_candidate_count": len(roles["promotion_candidate"]),
            "retired_count": len(roles["retired"]),
            "promotion_candidate_group_count": len(candidate_groups),
            "blocked_candidate_count": sum(1 for group in candidate_groups if str(group.get("decision_status") or "").startswith("blocked_")),
            "validation_error_count": len(errors),
            "next_action": "work Phase 180 next" if not errors else "fix prompt corpus governance findings before promotion",
        },
        "validation_errors": errors,
    }


def validate_prompt_corpus_governance_v2_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    catalog: dict[str, Any],
    delta_report: dict[str, Any] | None,
    policy_path: Path | None = None,
    catalog_path: Path | None = None,
    delta_report_path: Path | None = None,
) -> list[str]:
    expected = build_prompt_corpus_governance_v2_report(
        config_root=config_root,
        policy=policy,
        catalog=catalog,
        delta_report=delta_report,
        policy_path=policy_path,
        catalog_path=catalog_path,
        delta_report_path=delta_report_path,
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
        "source_catalog_path",
        "source_catalog_sha256",
        "source_delta_report_path",
        "source_delta_report_sha256",
        "role_counts",
        "target_holdout_links",
        "promotion_candidate_groups",
        "summary",
        "validation_errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append("report must match rebuilt prompt corpus governance V2 report")
            break
    return errors


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Prompt Corpus Governance V2",
        "",
        f"- Status: {report['status']}",
        f"- Catalog cases: {report['summary']['catalog_case_count']}",
        f"- Targets: {report['summary']['target_count']}",
        f"- Holdouts: {report['summary']['holdout_count']}",
        f"- Regression cases: {report['summary']['regression_count']}",
        f"- Promotion candidates: {report['summary']['promotion_candidate_count']}",
        f"- Blocked candidate groups: {report['summary']['blocked_candidate_count']}",
        f"- Next action: {report['summary']['next_action']}",
        "",
        "## Role Counts",
        "",
    ]
    for role, count in dict_value(report.get("role_counts")).items():
        lines.append(f"- {role}: {count}")
    lines.extend(["", "## Promotion Candidate Groups", ""])
    for group in object_list(report.get("promotion_candidate_groups")):
        lines.append(f"- {group.get('candidate_id')}: {group.get('decision_status')}")
    if report.get("validation_errors"):
        lines.extend(["", "## Validation Errors", ""])
        for error in object_list(report.get("validation_errors")):
            lines.append(f"- `{error.get('id')}`: {error.get('message')}")
    write_text(path, "\n".join(lines) + "\n")


def run_prompt_corpus_governance_v2(config: PromptCorpusGovernanceV2Config) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    catalog_path = resolve_path(config_root, str(policy.get("source_catalog_path") or ""))
    delta_report_path = resolve_path(config_root, str(policy.get("source_delta_report_path") or ""))
    delta_report = read_json_object(delta_report_path) if delta_report_path.is_file() else None
    report = build_prompt_corpus_governance_v2_report(
        config_root=config_root,
        policy=policy,
        catalog=read_json_object(catalog_path),
        delta_report=delta_report,
        policy_path=policy_path,
        catalog_path=catalog_path,
        delta_report_path=delta_report_path if delta_report_path.is_file() else None,
    )
    validation_errors = validate_prompt_corpus_governance_v2_report(
        report,
        config_root=config_root,
        policy=policy,
        catalog=read_json_object(catalog_path),
        delta_report=delta_report,
        policy_path=policy_path,
        catalog_path=catalog_path,
        delta_report_path=delta_report_path if delta_report_path.is_file() else None,
    )
    if validation_errors:
        report["status"] = PromptCorpusGovernanceStatus.FAILED.value
        report["validation_errors"] = object_list(report.get("validation_errors")) + [
            {"id": f"report.{index}", "severity": "high", "message": error} for index, error in enumerate(validation_errors)
        ]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
    output_path = resolve_path(config_root, config.output_path)
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    if config.markdown_output_path:
        markdown_path = resolve_path(config_root, config.markdown_output_path)
        write_markdown(markdown_path, report)
        report["markdown_path"] = str(markdown_path.resolve())
        write_json(output_path, report)
    return report
