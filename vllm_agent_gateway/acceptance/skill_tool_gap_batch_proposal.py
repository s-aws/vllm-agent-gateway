"""Phase 161 deterministic skill/tool gap batch proposal gate."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "skill_tool_gap_batch_proposal_policy"
EXPECTED_REPORT_KIND = "skill_tool_gap_batch_proposal_report"
EXPECTED_PHASE = 161
EXPECTED_BACKLOG_ID = "P0-BB-025"
DEFAULT_POLICY_PATH = Path("runtime") / "skill_tool_gap_batch_proposal_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "skill-tool-gap-batch-proposal" / "phase161"
DEFAULT_REPORT_PATH = DEFAULT_OUTPUT_DIR / "phase161-skill-tool-gap-batch-proposal-report.json"
DEFAULT_MARKDOWN_PATH = DEFAULT_OUTPUT_DIR / "phase161-skill-tool-gap-batch-proposal-report.md"


class BatchProposalStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class BatchProposalDecision(str, Enum):
    NO_BATCH = "no_new_batch_justified"
    PROPOSAL = "propose_batch_for_founder_approval"
    BLOCKED = "blocked"


class FindingCategory(str, Enum):
    PROMPT_ISSUE = "prompt_issue"
    HARNESS_ISSUE = "harness_issue"
    MISSING_SKILL_TOOL = "missing_skill_tool"
    MODEL_CAPABILITY = "model_capability"
    SAFETY_BOUNDARY = "safety_boundary"
    UNSUPPORTED_SCOPE = "unsupported_scope"
    DOCUMENTATION_ISSUE = "documentation_issue"


class CapabilityType(str, Enum):
    SKILL = "skill"
    TOOL = "tool"
    SKILL_AND_TOOL = "skill_and_tool"


class ValidationTier(str, Enum):
    OFFLINE = "offline"
    CONTROLLER = "controller"
    GATEWAY_ANYTHINGLLM = "gateway_anythingllm"
    GATEWAY_ANYTHINGLLM_FIXTURE_MUTATION = "gateway_anythingllm_fixture_mutation"
    UI_RELEASE_CANDIDATE = "ui_release_candidate"


class SafetyBoundary(str, Enum):
    PROPOSAL_ONLY = "proposal_only"
    FOUNDER_APPROVAL_REQUIRED = "founder_approval_required_before_implementation"
    NO_SOURCE_MUTATION = "no_source_mutation"
    NO_AUTO_REGISTRATION = "no_auto_registration"
    TARGET_PLUS_HOLDOUT_EVAL_REQUIRED = "target_plus_holdout_eval_required"
    ANYTHINGLLM_CHAT_QUALITY_REQUIRED = "anythingllm_chat_quality_required"


class Phase159RepairMode(str, Enum):
    NO_REPAIR_REQUIRED = "no_repair_required"
    REPAIRS_CLOSED = "repairs_closed"


@dataclass(frozen=True)
class SkillToolGapBatchProposalConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_REPORT_PATH
    markdown_output_path: Path | None = DEFAULT_MARKDOWN_PATH


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


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def enum_values(enum_class: type[Enum]) -> set[str]:
    return {item.value for item in enum_class}


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 161")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    inputs = dict_value(policy.get("inputs"))
    for key in ("phase157_report", "phase158_report", "phase159_report", "phase160_report"):
        if not isinstance(inputs.get(key), str) or not inputs[key].strip():
            errors.append(f"policy.inputs.{key} must be a path string")
    expected_sources = object_list(policy.get("expected_sources"))
    expected_ids = {"phase157_report", "phase158_report", "phase159_report", "phase160_report"}
    source_ids = {str(item.get("id")) for item in expected_sources if isinstance(item.get("id"), str)}
    if source_ids != expected_ids:
        errors.append("policy.expected_sources must include Phase 157, 158, 159, and 160 reports")
    for index, source in enumerate(expected_sources):
        prefix = f"policy.expected_sources[{index}]"
        for key in ("id", "kind", "status", "priority_backlog_id"):
            if not isinstance(source.get(key), str) or not source[key].strip():
                errors.append(f"{prefix}.{key} must be a non-empty string")
        if not isinstance(source.get("phase"), int):
            errors.append(f"{prefix}.phase must be an integer")
    if set(string_list(policy.get("skill_tool_gap_categories"))) != {FindingCategory.MISSING_SKILL_TOOL.value}:
        errors.append("policy.skill_tool_gap_categories must be missing_skill_tool")
    if not set(string_list(policy.get("non_batch_categories"))).issubset(enum_values(FindingCategory)):
        errors.append("policy.non_batch_categories must only include governed finding categories")
    candidate_policy = dict_value(policy.get("candidate_policy"))
    if set(string_list(candidate_policy.get("allowed_capability_types"))) != enum_values(CapabilityType):
        errors.append("candidate_policy.allowed_capability_types must include skill, tool, and skill_and_tool")
    required_fields = set(string_list(candidate_policy.get("required_candidate_fields")))
    required_minimum = {
        "candidate_id",
        "source_finding_id",
        "capability_type",
        "capability_id",
        "proposal_summary",
        "eval_gate",
        "approval_boundary",
        "implementation_status",
    }
    if required_fields != required_minimum:
        errors.append("candidate_policy.required_candidate_fields must match governed candidate fields")
    if not set(string_list(candidate_policy.get("allowed_validation_tiers"))).issuperset(
        set(string_list(candidate_policy.get("required_validation_tiers")))
    ):
        errors.append("candidate_policy.allowed_validation_tiers must include required validation tiers")
    if set(string_list(candidate_policy.get("required_validation_tiers"))) != {
        ValidationTier.CONTROLLER.value,
        ValidationTier.GATEWAY_ANYTHINGLLM.value,
        ValidationTier.GATEWAY_ANYTHINGLLM_FIXTURE_MUTATION.value,
    }:
        errors.append("candidate_policy.required_validation_tiers must include controller, gateway_anythingllm, and fixture mutation tiers")
    if set(string_list(candidate_policy.get("required_safety_boundaries"))) != enum_values(SafetyBoundary):
        errors.append("candidate_policy.required_safety_boundaries must match governed safety boundaries")
    if candidate_policy.get("approval_boundary") != "founder_approval_required":
        errors.append("candidate_policy.approval_boundary must be founder_approval_required")
    if candidate_policy.get("implementation_status") != "not_started":
        errors.append("candidate_policy.implementation_status must be not_started")
    if candidate_policy.get("source_mutation_required") is not False:
        errors.append("candidate_policy.source_mutation_required must be false")
    if candidate_policy.get("auto_register") is not False:
        errors.append("candidate_policy.auto_register must be false")
    if set(string_list(policy.get("required_target_roots"))) != {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    }:
        errors.append("policy.required_target_roots must include both frozen Coinbase fixtures")
    if set(string_list(policy.get("allowed_phase159_repair_modes"))) != enum_values(Phase159RepairMode):
        errors.append("policy.allowed_phase159_repair_modes must be no_repair_required and repairs_closed")
    if policy.get("required_phase160_readiness") != "ready_for_founder_testing":
        errors.append("policy.required_phase160_readiness must be ready_for_founder_testing")
    if policy.get("required_phase160_decision") != "release_for_founder_testing":
        errors.append("policy.required_phase160_decision must be release_for_founder_testing")
    decisions = dict_value(policy.get("decisions"))
    expected_decisions = {
        "no_batch": BatchProposalDecision.NO_BATCH.value,
        "proposal": BatchProposalDecision.PROPOSAL.value,
        "blocked": BatchProposalDecision.BLOCKED.value,
    }
    for key, value in expected_decisions.items():
        if decisions.get(key) != value:
            errors.append(f"policy.decisions.{key} must be {value}")
    if policy.get("implementation_authorized") is not False:
        errors.append("policy.implementation_authorized must be false")
    if policy.get("next_phase") != 162:
        errors.append("policy.next_phase must be 162")
    return errors


def expected_source_by_id(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in object_list(policy.get("expected_sources"))
        if isinstance(item.get("id"), str)
    }


def source_ref(path: Path | None, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path) if path else None,
        "sha256": artifact_hash(path),
        "kind": payload.get("kind"),
        "phase": payload.get("phase"),
        "status": payload.get("status"),
        "priority_backlog_id": payload.get("priority_backlog_id"),
        "readiness": payload.get("readiness"),
        "decision": payload.get("decision"),
        "repair_mode": payload.get("repair_mode"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
    }


def load_sources(
    config_root: Path,
    policy: dict[str, Any],
) -> tuple[dict[str, tuple[Path | None, dict[str, Any]]], list[str]]:
    inputs = dict_value(policy.get("inputs"))
    sources: dict[str, tuple[Path | None, dict[str, Any]]] = {}
    errors: list[str] = []
    for source_id in ("phase157_report", "phase158_report", "phase159_report", "phase160_report"):
        raw_path = inputs.get(source_id)
        if not isinstance(raw_path, str) or not raw_path.strip():
            sources[source_id] = (None, {})
            errors.append(f"policy.inputs.{source_id} is missing")
            continue
        path = resolve_path(config_root, raw_path)
        if not path.is_file():
            sources[source_id] = (path, {})
            errors.append(f"source report is missing: {raw_path}")
            continue
        try:
            sources[source_id] = (path, read_json_object(path))
        except Exception as exc:  # noqa: BLE001
            sources[source_id] = (path, {})
            errors.append(f"source report {source_id} is malformed: {type(exc).__name__}: {exc}")
    return sources, errors


def source_contract_errors(
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    load_errors: list[str],
) -> list[dict[str, Any]]:
    errors = [
        {
            "id": f"source_load.{index}",
            "source": "input_loading",
            "severity": "high",
            "message": error,
        }
        for index, error in enumerate(load_errors)
    ]
    for source_id, expected in expected_source_by_id(policy).items():
        path, payload = sources.get(source_id, (None, {}))
        checks = {
            "kind": expected.get("kind"),
            "phase": expected.get("phase"),
            "status": expected.get("status"),
            "priority_backlog_id": expected.get("priority_backlog_id"),
        }
        if (path is None and not payload) or (path is not None and not path.is_file()):
            errors.append(
                {
                    "id": f"{source_id}.missing",
                    "source": source_id,
                    "severity": "high",
                    "message": "required source report must exist",
                }
            )
        for key, expected_value in checks.items():
            if payload.get(key) != expected_value:
                errors.append(
                    {
                        "id": f"{source_id}.{key}",
                        "source": source_id,
                        "severity": "high",
                        "message": f"{key} must be {expected_value}",
                    }
                )
        if object_list(payload.get("validation_errors")):
            errors.append(
                {
                    "id": f"{source_id}.validation_errors",
                    "source": source_id,
                    "severity": "high",
                    "message": "source report validation_errors must be empty",
                }
            )
    return errors


def matching_phase160_ref_errors(
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    phase160 = sources.get("phase160_report", (None, {}))[1]
    phase160_refs = dict_value(phase160.get("source_refs"))
    mapped_refs = {
        "phase157_report": "founder_field_round1",
        "phase158_report": "transcript_quality_feedback_intake",
        "phase159_report": "priority0_repair_loop",
    }
    for source_id, phase160_ref_id in mapped_refs.items():
        path, payload = sources.get(source_id, (None, {}))
        ref = dict_value(phase160_refs.get(phase160_ref_id))
        actual_hash = artifact_hash(path)
        if actual_hash and ref.get("sha256") != actual_hash:
            errors.append(
                {
                    "id": f"phase160.source_refs.{phase160_ref_id}.sha256",
                    "source": "phase160_report",
                    "severity": "high",
                    "message": "Phase 160 source ref hash must match the loaded source report",
                }
            )
        if ref.get("kind") and payload.get("kind") and ref.get("kind") != payload.get("kind"):
            errors.append(
                {
                    "id": f"phase160.source_refs.{phase160_ref_id}.kind",
                    "source": "phase160_report",
                    "severity": "high",
                    "message": "Phase 160 source ref kind must match the loaded source report",
                }
            )
    return errors


def cross_chain_errors(
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    phase157 = sources.get("phase157_report", (None, {}))[1]
    phase158 = sources.get("phase158_report", (None, {}))[1]
    phase159 = sources.get("phase159_report", (None, {}))[1]
    phase160 = sources.get("phase160_report", (None, {}))[1]
    phase157_summary = dict_value(phase157.get("summary"))
    phase158_summary = dict_value(phase158.get("summary"))
    phase159_summary = dict_value(phase159.get("summary"))
    if set(string_list(phase157_summary.get("target_roots"))) != set(string_list(policy.get("required_target_roots"))):
        errors.append(
            {
                "id": "phase157.target_roots",
                "source": "phase157_report",
                "severity": "high",
                "message": "Phase 157 must cover both frozen Coinbase fixtures",
            }
        )
    if phase157_summary.get("blocker_case_count") != 0:
        errors.append(
            {
                "id": "phase157.blocker_case_count",
                "source": "phase157_report",
                "severity": "high",
                "message": "Phase 157 blockers must be zero before Phase 161 proposal review",
            }
        )
    if phase158_summary.get("source_case_count") != phase157_summary.get("case_count"):
        errors.append(
            {
                "id": "phase157_phase158.case_count_mismatch",
                "source": "phase158_report",
                "severity": "high",
                "message": "Phase 158 source_case_count must match Phase 157 case_count",
            }
        )
    expected_finding_count = (
        int(phase157_summary.get("advisory_case_count") or 0)
        + int(phase157_summary.get("blocker_case_count") or 0)
        + int(phase158_summary.get("founder_note_count") or 0)
    )
    if phase158_summary.get("accepted_finding_count") != expected_finding_count:
        errors.append(
            {
                "id": "phase157_phase158.finding_count_mismatch",
                "source": "phase158_report",
                "severity": "high",
                "message": "Phase 158 accepted findings must match Phase 157 advisory plus blocker cases",
            }
        )
    if phase159_summary.get("phase159_eligible_count") != phase158_summary.get("phase159_eligible_count"):
        errors.append(
            {
                "id": "phase158_phase159.eligible_count_mismatch",
                "source": "phase159_report",
                "severity": "high",
                "message": "Phase 159 eligible count must match Phase 158",
            }
        )
    if phase159_summary.get("open_repair_count") != 0:
        errors.append(
            {
                "id": "phase159.open_repair_count",
                "source": "phase159_report",
                "severity": "high",
                "message": "Phase 159 must have zero open repairs before Phase 161",
            }
        )
    if phase159.get("repair_mode") not in set(string_list(policy.get("allowed_phase159_repair_modes"))):
        errors.append(
            {
                "id": "phase159.repair_mode",
                "source": "phase159_report",
                "severity": "high",
                "message": "Phase 159 repair_mode must be no_repair_required or repairs_closed",
            }
        )
    if phase160.get("readiness") != policy.get("required_phase160_readiness"):
        errors.append(
            {
                "id": "phase160.readiness",
                "source": "phase160_report",
                "severity": "high",
                "message": "Phase 160 readiness must remain ready_for_founder_testing",
            }
        )
    if phase160.get("decision") != policy.get("required_phase160_decision"):
        errors.append(
            {
                "id": "phase160.decision",
                "source": "phase160_report",
                "severity": "high",
                "message": "Phase 160 decision must remain release_for_founder_testing",
            }
        )
    if dict_value(phase160.get("summary")).get("validation_error_count") != 0:
        errors.append(
            {
                "id": "phase160.validation_error_count",
                "source": "phase160_report",
                "severity": "high",
                "message": "Phase 160 validation_error_count must be zero",
            }
        )
    errors.extend(matching_phase160_ref_errors(sources))
    return errors


def phase158_finding_row_errors(policy: dict[str, Any], phase158_report: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    findings = object_list(phase158_report.get("accepted_findings"))
    summary = dict_value(phase158_report.get("summary"))
    known_categories = enum_values(FindingCategory)
    skill_categories = set(string_list(policy.get("skill_tool_gap_categories")))
    non_batch_categories = set(string_list(policy.get("non_batch_categories")))
    category_counts: dict[str, int] = {}
    owner_counts: dict[str, int] = {}
    eligible_count = 0
    finding_ids: list[str] = []
    for index, finding in enumerate(findings):
        prefix = f"phase158.accepted_findings[{index}]"
        finding_id = finding.get("finding_id")
        if not isinstance(finding_id, str) or not finding_id.strip():
            errors.append(
                {
                    "id": f"{prefix}.finding_id",
                    "source": "phase158_report",
                    "severity": "high",
                    "message": "accepted finding must include a non-empty finding_id",
                }
            )
        else:
            finding_ids.append(finding_id)
        category = finding.get("category")
        if category not in known_categories:
            errors.append(
                {
                    "id": f"{prefix}.category",
                    "source": "phase158_report",
                    "severity": "high",
                    "message": "accepted finding category must be governed",
                }
            )
        else:
            category_counts[str(category)] = category_counts.get(str(category), 0) + 1
        owner = finding.get("owner_path")
        if isinstance(owner, str) and owner.strip():
            owner_counts[owner] = owner_counts.get(owner, 0) + 1
        else:
            errors.append(
                {
                    "id": f"{prefix}.owner_path",
                    "source": "phase158_report",
                    "severity": "high",
                    "message": "accepted finding owner_path must be a non-empty string",
                }
            )
        if finding.get("phase159_eligible") is True:
            eligible_count += 1
        if owner == "skill_tool_gap_review" and category not in skill_categories:
            errors.append(
                {
                    "id": f"{prefix}.owner_category_mismatch",
                    "source": "phase158_report",
                    "severity": "high",
                    "message": "skill_tool_gap_review owner requires missing_skill_tool category",
                }
            )
        if category in skill_categories:
            if owner != "skill_tool_gap_review":
                errors.append(
                    {
                        "id": f"{prefix}.missing_skill_tool_owner",
                        "source": "phase158_report",
                        "severity": "high",
                        "message": "missing_skill_tool findings must be owned by skill_tool_gap_review",
                    }
                )
            if finding.get("phase159_eligible") is not True:
                errors.append(
                    {
                        "id": f"{prefix}.missing_skill_tool_phase159",
                        "source": "phase158_report",
                        "severity": "high",
                        "message": "missing_skill_tool findings must be Phase 159 eligible",
                    }
                )
            if finding.get("decision") != "accepted_for_phase159":
                errors.append(
                    {
                        "id": f"{prefix}.missing_skill_tool_decision",
                        "source": "phase158_report",
                        "severity": "high",
                        "message": "missing_skill_tool findings must be accepted_for_phase159",
                    }
                )
            if finding.get("required_rerun_gate") != "phase159_target_plus_holdout":
                errors.append(
                    {
                        "id": f"{prefix}.missing_skill_tool_rerun_gate",
                        "source": "phase158_report",
                        "severity": "high",
                        "message": "missing_skill_tool findings must require phase159_target_plus_holdout",
                    }
                )
            if not isinstance(finding.get("message"), str) or len(finding["message"].strip()) < 20:
                errors.append(
                    {
                        "id": f"{prefix}.missing_skill_tool_message",
                        "source": "phase158_report",
                        "severity": "high",
                        "message": "missing_skill_tool findings must include concrete evidence text",
                    }
                )
        elif category in non_batch_categories:
            pass
        elif category in known_categories:
            errors.append(
                {
                    "id": f"{prefix}.category_not_classified",
                    "source": "phase158_report",
                    "severity": "high",
                    "message": "accepted finding category must be classified as skill/tool or non-batch",
                }
            )
    for duplicate in sorted({item for item in finding_ids if finding_ids.count(item) > 1}):
        errors.append(
            {
                "id": f"phase158.accepted_findings.{duplicate}.duplicate",
                "source": "phase158_report",
                "severity": "high",
                "message": "accepted finding IDs must be unique",
            }
        )
    if summary.get("accepted_finding_count") != len(findings):
        errors.append(
            {
                "id": "phase158.summary.accepted_finding_count",
                "source": "phase158_report",
                "severity": "high",
                "message": "Phase 158 accepted_finding_count must match accepted_findings rows",
            }
        )
    if summary.get("phase159_eligible_count") != eligible_count:
        errors.append(
            {
                "id": "phase158.summary.phase159_eligible_count",
                "source": "phase158_report",
                "severity": "high",
                "message": "Phase 158 phase159_eligible_count must match accepted_findings rows",
            }
        )
    if summary.get("phase159_required") != (eligible_count > 0):
        errors.append(
            {
                "id": "phase158.summary.phase159_required",
                "source": "phase158_report",
                "severity": "high",
                "message": "Phase 158 phase159_required must match accepted_findings rows",
            }
        )
    if dict_value(summary.get("category_counts")) != category_counts:
        errors.append(
            {
                "id": "phase158.summary.category_counts",
                "source": "phase158_report",
                "severity": "high",
                "message": "Phase 158 category_counts must match accepted_findings rows",
            }
        )
    if dict_value(summary.get("owner_counts")) != owner_counts:
        errors.append(
            {
                "id": "phase158.summary.owner_counts",
                "source": "phase158_report",
                "severity": "high",
                "message": "Phase 158 owner_counts must match accepted_findings rows",
            }
        )
    return errors


def skill_tool_findings(policy: dict[str, Any], phase158_report: dict[str, Any]) -> list[dict[str, Any]]:
    categories = set(string_list(policy.get("skill_tool_gap_categories")))
    return [
        finding
        for finding in object_list(phase158_report.get("accepted_findings"))
        if finding.get("category") in categories
    ]


def non_batch_findings(policy: dict[str, Any], phase158_report: dict[str, Any]) -> list[dict[str, Any]]:
    categories = set(string_list(policy.get("skill_tool_gap_categories")))
    return [
        finding
        for finding in object_list(phase158_report.get("accepted_findings"))
        if finding.get("category") not in categories and finding.get("owner_path") != "skill_tool_gap_review"
    ]


def slug(value: object) -> str:
    text = str(value or "unknown").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "unknown"


def candidate_from_finding(policy: dict[str, Any], finding: dict[str, Any], index: int) -> dict[str, Any]:
    candidate_policy = dict_value(policy.get("candidate_policy"))
    required_tiers = string_list(candidate_policy.get("required_validation_tiers"))
    required_boundaries = string_list(candidate_policy.get("required_safety_boundaries"))
    case_id = str(finding.get("case_id") or f"case-{index}")
    selected_workflow = str(finding.get("selected_workflow") or "unknown_workflow")
    message = str(finding.get("message") or "Missing deterministic skill or tool capability was reported.")
    return {
        "candidate_id": f"P161-STG-{index:03d}",
        "source": "phase158_accepted_finding",
        "source_finding_id": finding.get("finding_id"),
        "case_id": finding.get("case_id"),
        "target_root": finding.get("target_root"),
        "run_id": finding.get("run_id"),
        "target_prompt_families": [selected_workflow],
        "capability_type": CapabilityType.SKILL_AND_TOOL.value,
        "capability_id": f"phase161.{slug(case_id)}.deterministic_gap",
        "proposal_summary": f"Create a bounded deterministic skill/tool candidate for {case_id}: {message[:180]}",
        "eval_gate": "phase161_target_holdout_gateway_anythingllm",
        "validation_tiers": required_tiers,
        "safety_boundaries": required_boundaries,
        "approval_boundary": candidate_policy.get("approval_boundary"),
        "implementation_status": candidate_policy.get("implementation_status"),
        "source_mutation_required": candidate_policy.get("source_mutation_required"),
        "auto_register": candidate_policy.get("auto_register"),
        "prompt_or_formatter_repair_insufficient": True,
        "status": "proposed_for_founder_approval",
    }


def build_candidates(policy: dict[str, Any], phase158_report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        candidate_from_finding(policy, finding, index)
        for index, finding in enumerate(skill_tool_findings(policy, phase158_report), start=1)
    ]


def validation_records_for_candidates(policy: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    candidate_policy = dict_value(policy.get("candidate_policy"))
    required_fields = string_list(candidate_policy.get("required_candidate_fields"))
    allowed_capability_types = set(string_list(candidate_policy.get("allowed_capability_types")))
    allowed_tiers = set(string_list(candidate_policy.get("allowed_validation_tiers")))
    required_tiers = set(string_list(candidate_policy.get("required_validation_tiers")))
    required_boundaries = set(string_list(candidate_policy.get("required_safety_boundaries")))
    for index, candidate in enumerate(candidates):
        prefix = f"candidates[{index}]"
        for field in required_fields:
            if not isinstance(candidate.get(field), str) or not candidate[field].strip():
                errors.append(
                    {
                        "id": f"{prefix}.{field}",
                        "source": "candidate",
                        "severity": "high",
                        "message": f"{field} must be a non-empty string",
                    }
                )
        if candidate.get("capability_type") not in allowed_capability_types:
            errors.append(
                {
                    "id": f"{prefix}.capability_type",
                    "source": "candidate",
                    "severity": "high",
                    "message": "capability_type must be governed",
                }
            )
        tiers = set(string_list(candidate.get("validation_tiers")))
        if not required_tiers.issubset(tiers):
            errors.append(
                {
                    "id": f"{prefix}.validation_tiers",
                    "source": "candidate",
                    "severity": "high",
                    "message": "validation_tiers must include required Phase 161 tiers",
                }
            )
        if tiers - allowed_tiers:
            errors.append(
                {
                    "id": f"{prefix}.validation_tiers.allowed",
                    "source": "candidate",
                    "severity": "high",
                    "message": "validation_tiers must be governed",
                }
            )
        if set(string_list(candidate.get("safety_boundaries"))) != required_boundaries:
            errors.append(
                {
                    "id": f"{prefix}.safety_boundaries",
                    "source": "candidate",
                    "severity": "high",
                    "message": "safety_boundaries must match required boundaries",
                }
            )
        if candidate.get("approval_boundary") != candidate_policy.get("approval_boundary"):
            errors.append(
                {
                    "id": f"{prefix}.approval_boundary",
                    "source": "candidate",
                    "severity": "high",
                    "message": "approval_boundary must match policy",
                }
            )
        if candidate.get("implementation_status") != candidate_policy.get("implementation_status"):
            errors.append(
                {
                    "id": f"{prefix}.implementation_status",
                    "source": "candidate",
                    "severity": "high",
                    "message": "implementation_status must match policy",
                }
            )
        if candidate.get("source_mutation_required") is not False:
            errors.append(
                {
                    "id": f"{prefix}.source_mutation_required",
                    "source": "candidate",
                    "severity": "high",
                    "message": "source_mutation_required must be false",
                }
            )
        if candidate.get("auto_register") is not False:
            errors.append(
                {
                    "id": f"{prefix}.auto_register",
                    "source": "candidate",
                    "severity": "high",
                    "message": "auto_register must be false",
                }
            )
    return errors


def build_skill_tool_gap_batch_proposal_report(
    *,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    load_errors: list[str],
    policy_path: Path | None = None,
) -> dict[str, Any]:
    validation_errors = [
        {
            "id": f"policy.{index}",
            "source": "policy",
            "severity": "high",
            "message": error,
        }
        for index, error in enumerate(validate_policy(policy))
    ]
    validation_errors.extend(source_contract_errors(policy, sources, load_errors))
    validation_errors.extend(cross_chain_errors(policy, sources))
    phase158_report = sources.get("phase158_report", (None, {}))[1]
    validation_errors.extend(phase158_finding_row_errors(policy, phase158_report))
    candidates = build_candidates(policy, phase158_report)
    validation_errors.extend(validation_records_for_candidates(policy, candidates))
    non_batch_records = [
        {
            "finding_id": finding.get("finding_id"),
            "case_id": finding.get("case_id"),
            "category": finding.get("category"),
            "owner_path": finding.get("owner_path"),
            "classified_as": "not_skill_tool_gap_batch",
            "reason": "Finding is governed by prompt, formatter, model, documentation, or unsupported-scope follow-up rather than a new deterministic skill/tool batch.",
        }
        for finding in non_batch_findings(policy, phase158_report)
    ]
    decision_policy = dict_value(policy.get("decisions"))
    if validation_errors:
        decision = BatchProposalDecision.BLOCKED.value
    elif candidates:
        decision = str(decision_policy.get("proposal") or BatchProposalDecision.PROPOSAL.value)
    else:
        decision = str(decision_policy.get("no_batch") or BatchProposalDecision.NO_BATCH.value)
    source_refs = {source_id: source_ref(path, payload) for source_id, (path, payload) in sorted(sources.items())}
    phase157_summary = dict_value(sources.get("phase157_report", (None, {}))[1].get("summary"))
    phase158_summary = dict_value(phase158_report.get("summary"))
    phase159_summary = dict_value(sources.get("phase159_report", (None, {}))[1].get("summary"))
    phase160_summary = dict_value(sources.get("phase160_report", (None, {}))[1].get("summary"))
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": BatchProposalStatus.PASSED.value if not validation_errors else BatchProposalStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "policy_ref": source_ref(policy_path, policy),
        "source_refs": source_refs,
        "decision": decision,
        "implementation_authorized": False,
        "gap_candidates": candidates,
        "non_batch_findings": non_batch_records,
        "validation_errors": validation_errors,
        "next_phase": policy.get("next_phase"),
        "summary": {
            "decision": decision,
            "phase157_case_count": phase157_summary.get("case_count"),
            "phase158_accepted_finding_count": phase158_summary.get("accepted_finding_count"),
            "phase158_category_counts": phase158_summary.get("category_counts"),
            "phase159_repair_mode": sources.get("phase159_report", (None, {}))[1].get("repair_mode"),
            "phase159_eligible_count": phase159_summary.get("phase159_eligible_count"),
            "phase160_readiness": sources.get("phase160_report", (None, {}))[1].get("readiness"),
            "phase160_decision": sources.get("phase160_report", (None, {}))[1].get("decision"),
            "phase160_model_ids": phase160_summary.get("model_ids"),
            "missing_skill_tool_finding_count": len(skill_tool_findings(policy, phase158_report)),
            "non_batch_finding_count": len(non_batch_records),
            "gap_candidate_count": len(candidates),
            "implementation_authorized": False,
            "validation_error_count": len(validation_errors),
        },
    }
    return report


def stable_view(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report.get(key)
        for key in (
            "schema_version",
            "kind",
            "phase",
            "priority_backlog_id",
            "status",
            "policy_ref",
            "source_refs",
            "decision",
            "implementation_authorized",
            "gap_candidates",
            "non_batch_findings",
            "validation_errors",
            "next_phase",
            "summary",
        )
    }


def validate_skill_tool_gap_batch_proposal_report(
    report: dict[str, Any],
    *,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    load_errors: list[str],
    policy_path: Path | None = None,
) -> list[str]:
    expected = build_skill_tool_gap_batch_proposal_report(
        policy=policy,
        sources=sources,
        load_errors=load_errors,
        policy_path=policy_path,
    )
    if stable_view(report) != stable_view(expected):
        return ["report must match rebuilt skill/tool gap batch proposal report"]
    return []


def markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Skill/Tool Gap Batch Proposal",
        "",
        f"- Status: {report.get('status')}",
        f"- Decision: {report.get('decision')}",
        f"- Implementation authorized: {report.get('implementation_authorized')}",
        f"- Missing skill/tool findings: {summary.get('missing_skill_tool_finding_count')}",
        f"- Gap candidates: {summary.get('gap_candidate_count')}",
        f"- Non-batch findings: {summary.get('non_batch_finding_count')}",
        f"- Validation errors: {summary.get('validation_error_count')}",
        "",
        "## Gap Candidates",
        "",
        "| Candidate | Source Finding | Capability | Eval Gate | Approval | Status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    candidates = object_list(report.get("gap_candidates"))
    if candidates:
        for candidate in candidates:
            lines.append(
                "| {candidate_id} | {source_finding_id} | {capability_id} | {eval_gate} | {approval_boundary} | {status} |".format(
                    candidate_id=candidate.get("candidate_id"),
                    source_finding_id=candidate.get("source_finding_id"),
                    capability_id=candidate.get("capability_id"),
                    eval_gate=candidate.get("eval_gate"),
                    approval_boundary=candidate.get("approval_boundary"),
                    status=candidate.get("status"),
                )
            )
    else:
        lines.append("| none | none | none | none | none | none |")
    lines.extend(["", "## Non-Batch Findings", ""])
    non_batch = object_list(report.get("non_batch_findings"))
    if non_batch:
        for item in non_batch:
            lines.append(
                f"- {item.get('finding_id')}: {item.get('category')} -> {item.get('classified_as')}"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Validation Errors", ""])
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(f"- {error.get('id')}: {error.get('message')}" for error in errors)
    else:
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"


def run_skill_tool_gap_batch_proposal(config: SkillToolGapBatchProposalConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path) if config.markdown_output_path else None
    policy = read_json_object(policy_path)
    sources, load_errors = load_sources(config_root, policy)
    report = build_skill_tool_gap_batch_proposal_report(
        policy=policy,
        sources=sources,
        load_errors=load_errors,
        policy_path=policy_path,
    )
    validation_errors = validate_skill_tool_gap_batch_proposal_report(
        report,
        policy=policy,
        sources=sources,
        load_errors=load_errors,
        policy_path=policy_path,
    )
    if validation_errors:
        report["status"] = BatchProposalStatus.FAILED.value
        report["decision"] = BatchProposalDecision.BLOCKED.value
        report["validation_errors"] = [
            *object_list(report.get("validation_errors")),
            *[
                {
                    "id": f"self_validation.{index}",
                    "source": "skill_tool_gap_batch_proposal",
                    "severity": "high",
                    "message": error,
                }
                for index, error in enumerate(validation_errors)
            ],
        ]
        report["summary"]["decision"] = BatchProposalDecision.BLOCKED.value
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    if markdown_output_path:
        write_text(markdown_output_path, markdown_report(report))
        report["markdown_report_path"] = str(markdown_output_path.resolve())
    write_json(output_path, report)
    if markdown_output_path:
        write_text(markdown_output_path, markdown_report(report))
    return report
