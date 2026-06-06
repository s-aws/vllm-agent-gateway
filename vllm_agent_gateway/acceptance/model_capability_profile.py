"""Advisory model capability profiles derived from portability reports."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.model_portability import ModelPortabilityIssue


DEFAULT_OUTPUT_DIR = Path("runtime-state") / "model-capability-profiles"
SCHEMA_VERSION = 1


class CapabilityStatus(str, Enum):
    PROVEN = "proven"
    PARTIALLY_PROVEN = "partially_proven"
    NOT_PROVEN = "not_proven"
    UNKNOWN = "unknown"
    NOT_APPROVED = "not_approved"


class TaskPolicyStatus(str, Enum):
    APPROVED = "approved"
    CONDITIONAL = "conditional"
    NOT_APPROVED = "not_approved"


class ProfileStatus(str, Enum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


@dataclass(frozen=True)
class ModelCapabilityProfileConfig:
    config_root: Path
    portability_report_path: Path
    output_path: Path | None = None
    markdown_output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object report: {path}")
    return value


def host_readable_path(path_text: str, *, config_root: Path) -> Path | None:
    if not path_text.strip():
        return None
    direct = Path(path_text)
    candidates = [direct]
    if not direct.is_absolute():
        candidates.append(config_root / direct)
    mount_match = re.match(r"^/mnt/([A-Za-z])/(.+)$", path_text)
    if mount_match and os.name == "nt":
        candidates.append(Path(f"{mount_match.group(1).upper()}:/{mount_match.group(2)}"))
    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue
    return None


def default_profile_path(config_root: Path, candidate_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", candidate_id).strip("-") or "candidate"
    return config_root / DEFAULT_OUTPUT_DIR / f"{safe_id}-profile-{utc_timestamp()}.json"


def default_markdown_path(profile_path: Path) -> Path:
    return profile_path.with_suffix(".md")


def count_classification(records: list[dict[str, Any]], classification: ModelPortabilityIssue) -> int:
    return sum(1 for record in records if record.get("classification") == classification.value)


def records_with_terms(records: list[dict[str, Any]], terms: tuple[str, ...]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for record in records:
        text = " ".join(
            str(record.get(key) or "")
            for key in ("source", "classification", "matched_terms", "message")
        ).lower()
        if any(term in text for term in terms):
            matches.append(record)
    return matches


def suite_statuses(acceptance_report: dict[str, Any]) -> dict[str, str]:
    suites = acceptance_report.get("suite_runs")
    if not isinstance(suites, list):
        return {}
    statuses: dict[str, str] = {}
    for item in suites:
        if not isinstance(item, dict):
            continue
        suite_id = item.get("id")
        status = item.get("status")
        if isinstance(suite_id, str) and isinstance(status, str):
            statuses[suite_id] = status
    return statuses


def suite_passed(statuses: dict[str, str], suite_id: str) -> bool:
    return statuses.get(suite_id) == "passed"


def capability(
    status: CapabilityStatus,
    *,
    evidence: list[str],
    limitations: list[str] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status.value,
        "evidence": evidence,
        "limitations": limitations or [],
        "metrics": metrics or {},
    }


def route_stability_capability(
    portability_report: dict[str, Any],
    failures: list[dict[str, Any]],
    statuses: dict[str, str],
) -> dict[str, Any]:
    classifier_failures = count_classification(failures, ModelPortabilityIssue.CLASSIFIER)
    if classifier_failures:
        return capability(
            CapabilityStatus.NOT_PROVEN,
            evidence=[f"classifier_failure_count={classifier_failures}"],
            limitations=["Route decisions are not stable enough for model-assisted routing policy expansion."],
            metrics={"classifier_failure_count": classifier_failures},
        )
    if portability_report.get("status") == "passed" and suite_passed(statuses, "representative_l1"):
        return capability(
            CapabilityStatus.PROVEN,
            evidence=["source portability report passed", "representative_l1 suite passed", "classifier_failure_count=0"],
            metrics={"classifier_failure_count": 0},
        )
    return capability(
        CapabilityStatus.PARTIALLY_PROVEN,
        evidence=["classifier_failure_count=0"],
        limitations=["The source portability report did not fully pass, so route stability is only partial."],
        metrics={"classifier_failure_count": 0},
    )


def output_contract_capability(portability_report: dict[str, Any], failures: list[dict[str, Any]]) -> dict[str, Any]:
    contract_failures = records_with_terms(
        failures,
        (
            "schema",
            "jsondecodeerror",
            "not valid json",
            "malformed",
            "invalid_model_route",
            "model route output",
            "output contract",
        ),
    )
    if contract_failures:
        return capability(
            CapabilityStatus.NOT_PROVEN,
            evidence=[f"output_contract_failure_count={len(contract_failures)}"],
            limitations=["At least one model or harness output contract failure was classified."],
            metrics={"output_contract_failure_count": len(contract_failures)},
        )
    if portability_report.get("status") == "passed":
        return capability(
            CapabilityStatus.PROVEN,
            evidence=["source portability report passed", "output_contract_failure_count=0"],
            metrics={"output_contract_failure_count": 0},
        )
    return capability(
        CapabilityStatus.PARTIALLY_PROVEN,
        evidence=["output_contract_failure_count=0"],
        limitations=["No output-contract failures were classified, but the source report did not fully pass."],
        metrics={"output_contract_failure_count": 0},
    )


def semantic_quality_capability(
    portability_report: dict[str, Any],
    failures: list[dict[str, Any]],
    acceptance_summary: dict[str, Any],
) -> dict[str, Any]:
    model_quality_failures = count_classification(failures, ModelPortabilityIssue.MODEL_QUALITY)
    founder_status = (
        acceptance_summary.get("founder_field_summary", {}).get("status")
        if isinstance(acceptance_summary.get("founder_field_summary"), dict)
        else None
    )
    if model_quality_failures:
        return capability(
            CapabilityStatus.NOT_PROVEN,
            evidence=[f"model_quality_failure_count={model_quality_failures}", f"founder_field_status={founder_status}"],
            limitations=["Semantic output quality misses must be fixed or routed away from this model profile."],
            metrics={"model_quality_failure_count": model_quality_failures},
        )
    if portability_report.get("status") == "passed" and founder_status == "passed":
        return capability(
            CapabilityStatus.PROVEN,
            evidence=["founder field prompt suite passed", "model_quality_failure_count=0"],
            metrics={"model_quality_failure_count": 0},
        )
    return capability(
        CapabilityStatus.PARTIALLY_PROVEN,
        evidence=[f"founder_field_status={founder_status}", "model_quality_failure_count=0"],
        limitations=["The source report did not fully prove semantic quality for this model profile."],
        metrics={"model_quality_failure_count": 0},
    )


def latency_capability(acceptance_report: dict[str, Any]) -> dict[str, Any]:
    durations: list[float] = []
    for item in acceptance_report.get("suite_runs") or []:
        if not isinstance(item, dict):
            continue
        for key in ("duration_seconds", "elapsed_seconds"):
            value = item.get(key)
            if isinstance(value, (int, float)):
                durations.append(float(value))
                break
    if not durations:
        return capability(
            CapabilityStatus.UNKNOWN,
            evidence=["source acceptance report does not include suite duration metrics"],
            limitations=["Latency is not approved for routing decisions until measured timing is recorded."],
            metrics={"duration_sample_count": 0},
        )
    return capability(
        CapabilityStatus.PROVEN,
        evidence=[f"duration_sample_count={len(durations)}"],
        metrics={
            "duration_sample_count": len(durations),
            "max_duration_seconds": max(durations),
            "total_duration_seconds": sum(durations),
        },
    )


def timeout_capability(portability_report: dict[str, Any], failures: list[dict[str, Any]]) -> dict[str, Any]:
    timeout_failures = records_with_terms(failures, ("timeout", "timed out", "body bytes"))
    harness_failures = count_classification(failures, ModelPortabilityIssue.HARNESS)
    if timeout_failures:
        return capability(
            CapabilityStatus.NOT_PROVEN,
            evidence=[f"timeout_failure_count={len(timeout_failures)}", f"harness_failure_count={harness_failures}"],
            limitations=["Timeout behavior is not acceptable for this profile until the failing path is fixed."],
            metrics={"timeout_failure_count": len(timeout_failures), "harness_failure_count": harness_failures},
        )
    if portability_report.get("status") == "passed":
        return capability(
            CapabilityStatus.PROVEN,
            evidence=["source portability report passed", "timeout_failure_count=0"],
            metrics={"timeout_failure_count": 0, "harness_failure_count": harness_failures},
        )
    return capability(
        CapabilityStatus.PARTIALLY_PROVEN,
        evidence=["timeout_failure_count=0"],
        limitations=["The source report did not fully pass, so timeout behavior remains only partially proven."],
        metrics={"timeout_failure_count": 0, "harness_failure_count": harness_failures},
    )


def safe_apply_capability(statuses: dict[str, str]) -> dict[str, Any]:
    if suite_passed(statuses, "controlled_apply"):
        return capability(
            CapabilityStatus.PARTIALLY_PROVEN,
            evidence=["controlled_apply suite passed"],
            limitations=[
                "Disposable-copy apply and dry-run packet proof are covered.",
                "Real repository mutation remains approval-gated and is not automatically approved by this profile.",
            ],
            metrics={"controlled_apply_passed": True},
        )
    return capability(
        CapabilityStatus.NOT_PROVEN,
        evidence=["controlled_apply suite did not pass or was not present"],
        limitations=["Apply-prep tasks must not be routed to this profile without another approved proof."],
        metrics={"controlled_apply_passed": False},
    )


def task_policy(capabilities: dict[str, dict[str, Any]], statuses: dict[str, str]) -> dict[str, Any]:
    route_ok = capabilities["route_stability"]["status"] == CapabilityStatus.PROVEN.value
    contract_ok = capabilities["output_contract_reliability"]["status"] == CapabilityStatus.PROVEN.value
    semantic_ok = capabilities["semantic_answer_quality"]["status"] == CapabilityStatus.PROVEN.value
    l1_ok = route_ok and contract_ok and semantic_ok and suite_passed(statuses, "representative_l1")
    l2_ok = route_ok and contract_ok and semantic_ok and suite_passed(statuses, "representative_l2")
    apply_ok = capabilities["safe_apply_readiness"]["status"] == CapabilityStatus.PARTIALLY_PROVEN.value
    return {
        "automatic_model_selection": {
            "status": TaskPolicyStatus.NOT_APPROVED.value,
            "reason": "Phase 78 profiles are advisory only; no automatic model selection behavior is enabled.",
        },
        "read_only_l1": {
            "status": TaskPolicyStatus.APPROVED.value if l1_ok else TaskPolicyStatus.NOT_APPROVED.value,
            "required_evidence": ["route_stability", "output_contract_reliability", "semantic_answer_quality", "representative_l1"],
        },
        "draft_only_l1": {
            "status": TaskPolicyStatus.APPROVED.value if l1_ok else TaskPolicyStatus.NOT_APPROVED.value,
            "required_evidence": ["representative_l1", "approval boundary remains controller-owned"],
        },
        "approval_gated_l1": {
            "status": TaskPolicyStatus.CONDITIONAL.value if l1_ok and apply_ok else TaskPolicyStatus.NOT_APPROVED.value,
            "required_evidence": ["representative_l1", "controlled_apply", "explicit approval remains required"],
        },
        "l2_read_only": {
            "status": TaskPolicyStatus.APPROVED.value if l2_ok else TaskPolicyStatus.NOT_APPROVED.value,
            "required_evidence": ["representative_l2", "route_stability", "semantic_answer_quality"],
        },
        "apply_prep": {
            "status": TaskPolicyStatus.CONDITIONAL.value if apply_ok and l1_ok else TaskPolicyStatus.NOT_APPROVED.value,
            "required_evidence": ["controlled_apply", "explicit approval", "disposable-copy or draft packet boundary"],
        },
        "real_apply": {
            "status": TaskPolicyStatus.NOT_APPROVED.value,
            "required_evidence": ["Later approved phase must explicitly authorize real repository mutation policy."],
        },
    }


def profile_status(portability_report: dict[str, Any], capabilities: dict[str, dict[str, Any]]) -> ProfileStatus:
    if portability_report.get("status") != "passed":
        return ProfileStatus.FAILED
    required = (
        "route_stability",
        "output_contract_reliability",
        "semantic_answer_quality",
        "timeout_behavior",
    )
    if any(capabilities[key]["status"] == CapabilityStatus.NOT_PROVEN.value for key in required):
        return ProfileStatus.FAILED
    if any(capabilities[key]["status"] in {CapabilityStatus.UNKNOWN.value, CapabilityStatus.PARTIALLY_PROVEN.value} for key in capabilities):
        return ProfileStatus.WARNING
    return ProfileStatus.PASSED


def load_acceptance_report(portability_report: dict[str, Any], *, config_root: Path) -> dict[str, Any]:
    acceptance_path = host_readable_path(str(portability_report.get("acceptance_report_path") or ""), config_root=config_root)
    if acceptance_path is not None:
        try:
            return load_json(acceptance_path)
        except (OSError, json.JSONDecodeError, RuntimeError):
            pass
    summary = portability_report.get("acceptance_report")
    return summary if isinstance(summary, dict) else {}


def render_markdown(profile: dict[str, Any]) -> str:
    candidate = profile.get("candidate", {})
    lines = [
        "# Model Capability Profile",
        "",
        f"- Candidate: {candidate.get('candidate_id', '')}",
        f"- Status: {profile.get('status')}",
        f"- Source portability report: {profile.get('source_portability_report_path')}",
        f"- Advisory only: {profile.get('routing_policy', {}).get('advisory_only')}",
        "",
        "## Capabilities",
        "",
        "| Capability | Status | Evidence | Limitations |",
        "| --- | --- | --- | --- |",
    ]
    for key, value in profile.get("capabilities", {}).items():
        evidence = "; ".join(value.get("evidence") or [])
        limitations = "; ".join(value.get("limitations") or [])
        lines.append(f"| {key} | {value.get('status')} | {evidence} | {limitations} |")
    lines.extend(["", "## Task Policy", "", "| Task | Status | Reason / Required Evidence |", "| --- | --- | --- |"])
    for key, value in profile.get("task_policy", {}).items():
        reason = value.get("reason") or "; ".join(value.get("required_evidence") or [])
        lines.append(f"| {key} | {value.get('status')} | {reason} |")
    lines.append("")
    return "\n".join(lines)


def run_model_capability_profile(config: ModelCapabilityProfileConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    portability_path = config.portability_report_path
    portability_report = load_json(portability_path)
    if portability_report.get("kind") != "model_portability_report":
        raise RuntimeError("portability report kind must be model_portability_report")
    candidate = portability_report.get("candidate") if isinstance(portability_report.get("candidate"), dict) else {}
    candidate_id = str(candidate.get("candidate_id") or "candidate")
    acceptance_report = load_acceptance_report(portability_report, config_root=config_root)
    statuses = suite_statuses(acceptance_report)
    failures = portability_report.get("classified_failures")
    failure_records = failures if isinstance(failures, list) else []
    capabilities = {
        "route_stability": route_stability_capability(portability_report, failure_records, statuses),
        "output_contract_reliability": output_contract_capability(portability_report, failure_records),
        "semantic_answer_quality": semantic_quality_capability(
            portability_report,
            failure_records,
            portability_report.get("acceptance_report") if isinstance(portability_report.get("acceptance_report"), dict) else {},
        ),
        "latency": latency_capability(acceptance_report),
        "timeout_behavior": timeout_capability(portability_report, failure_records),
        "safe_apply_readiness": safe_apply_capability(statuses),
    }
    report_path = config.output_path or default_profile_path(config_root, candidate_id)
    markdown_path = config.markdown_output_path or default_markdown_path(report_path)
    profile: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "model_capability_profile",
        "status": profile_status(portability_report, capabilities).value,
        "created_at": utc_timestamp(),
        "candidate": candidate,
        "candidate_model_probe": portability_report.get("candidate_model_probe", {}),
        "source_portability_report_path": str(portability_path.resolve()),
        "source_acceptance_report_path": str(portability_report.get("acceptance_report_path") or ""),
        "source_acceptance": portability_report.get("acceptance_report", {}),
        "source_suite_statuses": statuses,
        "classification_summary": portability_report.get("classification_summary", {}),
        "classified_failure_count": len(failure_records),
        "capabilities": capabilities,
        "task_policy": task_policy(capabilities, statuses),
        "routing_policy": {
            "advisory_only": True,
            "automatic_model_selection_enabled": False,
            "policy_doc": "docs/MODEL_CAPABILITY_ROUTING_POLICY.md",
            "must_not_change_runtime_behavior": True,
        },
        "limitations": [
            "Phase 78 does not enable automatic model selection.",
            "Latency remains unknown unless source acceptance reports include timing metrics.",
            "Real apply is not approved by any capability profile in this phase.",
        ],
    }
    profile["report_path"] = str(report_path.resolve())
    profile["markdown_report_path"] = str(markdown_path.resolve())
    write_json(report_path, profile)
    write_text(markdown_path, render_markdown(profile))
    return profile
