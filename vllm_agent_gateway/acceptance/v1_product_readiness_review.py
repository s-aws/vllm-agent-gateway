"""V1 product readiness review gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "v1_product_readiness_review_policy"
EXPECTED_REPORT_KIND = "v1_product_readiness_review_report"
EXPECTED_PHASE = 155
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_POLICY_PATH = Path("runtime") / "v1_product_readiness_review_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "v1-product-readiness-review" / "phase155"
REQUIRED_REPORT_IDS = {
    "stable_chat_quality_release",
    "release_notes",
    "stable_release_reset_rehearsal",
    "model_swap_smoke_probe",
    "current_model_compatibility",
}
REQUIRED_SUPPORTED_WORKFLOWS = {
    "natural_language_workflow_routing_through_anythingllm",
    "read_only_l1_l2_chat_answers",
    "format_a_and_json_output",
    "task_decomposition",
    "draft_only_implementation_planning",
    "approval_gated_disposable_copy_apply_proof",
    "founder_feedback_capture_and_triage",
    "setup_health_reset_and_model_swap_validation",
}
REQUIRED_UNSUPPORTED_WORKFLOWS = {
    "advanced_broad_refactor_orchestration",
    "production_deployment",
    "support_for_every_repository_language_or_coding_task",
    "direct_mutation_of_protected_frozen_fixtures",
    "unsupported_output_format_parity",
    "automatic_model_selection",
}


class V1ProductReadinessStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class V1ProductRecommendation(str, Enum):
    GO = "go_for_founder_testing"
    NO_GO = "no_go"


@dataclass(frozen=True)
class V1ProductReadinessReviewConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    markdown_output_path: Path | None = None
    require_artifacts: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"v1-product-readiness-review-{utc_timestamp()}.json"


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


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


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 155")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if set(string_list(policy.get("allowed_recommendations"))) != {item.value for item in V1ProductRecommendation}:
        errors.append("policy.allowed_recommendations must contain go_for_founder_testing and no_go")
    reports = object_list(policy.get("required_reports"))
    report_ids = [str(item.get("id")) for item in reports if isinstance(item.get("id"), str)]
    if set(report_ids) != REQUIRED_REPORT_IDS:
        errors.append("policy.required_reports must include the governed report IDs")
    if len(report_ids) != len(set(report_ids)):
        errors.append("policy.required_reports ids must be unique")
    for index, item in enumerate(reports):
        prefix = f"policy.required_reports[{index}]"
        for key in ("id", "path", "expected_kind", "expected_status"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(f"{prefix}.{key} must be a non-empty string")
        if not isinstance(item.get("expected_phase"), int):
            errors.append(f"{prefix}.expected_phase must be an integer")
    if set(string_list(policy.get("supported_workflows"))) != REQUIRED_SUPPORTED_WORKFLOWS:
        errors.append("policy.supported_workflows must match the governed supported workflow set")
    if set(string_list(policy.get("unsupported_workflows"))) != REQUIRED_UNSUPPORTED_WORKFLOWS:
        errors.append("policy.unsupported_workflows must match the governed unsupported workflow set")
    if not string_list(policy.get("required_docs")):
        errors.append("policy.required_docs must be a non-empty list")
    if not string_list(policy.get("required_evidence_markers")):
        errors.append("policy.required_evidence_markers must be a non-empty list")
    risks = object_list(policy.get("monitored_risks"))
    if len(risks) < 3:
        errors.append("policy.monitored_risks must include at least three risks")
    for index, risk in enumerate(risks):
        prefix = f"policy.monitored_risks[{index}]"
        for key in ("id", "severity", "source", "condition", "statement"):
            if not isinstance(risk.get(key), str) or not risk[key].strip():
                errors.append(f"{prefix}.{key} must be a non-empty string")
    return errors


def report_policy_by_id(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in object_list(policy.get("required_reports"))
        if isinstance(item.get("id"), str)
    }


def load_report_inputs(config_root: Path, policy: dict[str, Any], *, require_artifacts: bool) -> tuple[dict[str, tuple[Path | None, dict[str, Any]]], list[str]]:
    sources: dict[str, tuple[Path | None, dict[str, Any]]] = {}
    errors: list[str] = []
    for item in object_list(policy.get("required_reports")):
        report_id = str(item.get("id"))
        raw_path = item.get("path")
        if not isinstance(raw_path, str):
            sources[report_id] = (None, {})
            errors.append(f"required report {report_id} path is invalid")
            continue
        path = resolve_path(config_root, raw_path)
        if not path.is_file():
            sources[report_id] = (path, {})
            if require_artifacts:
                errors.append(f"required report is missing: {raw_path}")
            continue
        try:
            sources[report_id] = (path, read_json_object(path))
        except Exception as exc:  # noqa: BLE001
            sources[report_id] = (path, {})
            errors.append(f"required report {report_id} is malformed: {type(exc).__name__}: {exc}")
    return sources, errors


def source_ref(path: Path | None, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path) if path else None,
        "sha256": artifact_hash(path),
        "kind": payload.get("kind"),
        "status": payload.get("status"),
        "phase": payload.get("phase"),
        "readiness": payload.get("readiness"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
    }


def validate_report_contract(
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    load_errors: list[str],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = [
        {"id": f"load_error.{index}", "source": "input_loading", "severity": "high", "message": error}
        for index, error in enumerate(load_errors)
    ]
    for report_id, item in report_policy_by_id(policy).items():
        path, payload = sources.get(report_id, (None, {}))
        messages: list[str] = []
        if path is None or not path.is_file():
            messages.append("required report is missing")
        if payload.get("kind") != item.get("expected_kind"):
            messages.append(f"kind must be {item.get('expected_kind')}")
        if payload.get("status") != item.get("expected_status"):
            messages.append(f"status must be {item.get('expected_status')}")
        if payload.get("phase") != item.get("expected_phase"):
            messages.append(f"phase must be {item.get('expected_phase')}")
        expected_readiness = item.get("expected_readiness")
        if isinstance(expected_readiness, str) and payload.get("readiness") != expected_readiness:
            messages.append(f"readiness must be {expected_readiness}")
        expected_decision = item.get("expected_decision")
        if isinstance(expected_decision, str):
            decision = dict_value(payload.get("decision")).get("decision")
            if decision != expected_decision:
                messages.append(f"decision must be {expected_decision}")
        source_errors = payload.get("errors")
        if isinstance(source_errors, list) and source_errors:
            messages.append("errors must be empty")
        for message in messages:
            blockers.append(
                {
                    "id": f"{report_id}.{message.replace(' ', '_')}",
                    "source": report_id,
                    "severity": "high",
                    "message": message,
                    "path": str(path) if path else None,
                }
            )
    return blockers


def doc_records(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        exists = path.is_file()
        records.append({"path": str(path), "exists": exists, "sha256": artifact_hash(path)})
        if not exists:
            blockers.append(
                {
                    "id": f"doc_missing.{raw_path}",
                    "source": "documentation",
                    "severity": "medium",
                    "message": f"required doc is missing: {raw_path}",
                    "path": str(path),
                }
            )
    return records, blockers


def evidence_marker_blockers(policy: dict[str, Any], release_notes_text: str) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for marker in string_list(policy.get("required_evidence_markers")):
        if marker not in release_notes_text:
            blockers.append(
                {
                    "id": f"evidence_marker_missing.{marker}",
                    "source": "release_notes",
                    "severity": "medium",
                    "message": f"release notes missing required evidence marker: {marker}",
                }
            )
    return blockers


def risk_applies(risk: dict[str, Any], sources: dict[str, tuple[Path | None, dict[str, Any]]]) -> bool:
    condition = risk.get("condition")
    if condition == "always":
        return True
    if condition == "model_profile_status_warning":
        compatibility = sources.get("current_model_compatibility", (None, {}))[1]
        summary = dict_value(compatibility.get("summary"))
        return summary.get("model_profile_status") == "warning"
    return False


def monitored_risks(policy: dict[str, Any], sources: dict[str, tuple[Path | None, dict[str, Any]]]) -> list[dict[str, Any]]:
    return [
        {
            "id": risk.get("id"),
            "severity": risk.get("severity"),
            "source": risk.get("source"),
            "statement": risk.get("statement"),
        }
        for risk in object_list(policy.get("monitored_risks"))
        if risk_applies(risk, sources)
    ]


def readiness_summary(
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
) -> dict[str, Any]:
    stable = sources.get("stable_chat_quality_release", (None, {}))[1]
    model_swap = sources.get("model_swap_smoke_probe", (None, {}))[1]
    compatibility = sources.get("current_model_compatibility", (None, {}))[1]
    stable_summary = dict_value(stable.get("summary"))
    compatibility_summary = dict_value(compatibility.get("summary"))
    model_decision = dict_value(model_swap.get("decision"))
    return {
        "release_readiness": stable.get("readiness"),
        "stable_gate_count": stable_summary.get("gate_count"),
        "stable_blocker_count": stable_summary.get("blocker_count"),
        "model_swap_decision": model_decision.get("decision"),
        "model_swap_detected": model_decision.get("model_swap_detected"),
        "full_drift_gate_required": model_decision.get("full_drift_gate_required"),
        "expected_model_ids": model_decision.get("expected_model_ids"),
        "actual_model_ids": model_decision.get("actual_model_ids"),
        "supported_prompt_family_count": compatibility_summary.get("supported_prompt_family_count"),
        "l1_prompt_family_count": compatibility_summary.get("l1_prompt_family_count"),
        "l2_prompt_family_count": compatibility_summary.get("l2_prompt_family_count"),
        "governed_output_format_count": compatibility_summary.get("governed_output_format_count"),
        "known_failure_mode_count": compatibility_summary.get("known_failure_mode_count"),
        "supported_workflow_count": len(string_list(policy.get("supported_workflows"))),
        "unsupported_workflow_count": len(string_list(policy.get("unsupported_workflows"))),
    }


def build_v1_product_readiness_review_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    load_errors: list[str] | None = None,
    policy_path: Path | None = None,
) -> dict[str, Any]:
    policy_errors = validate_policy(policy)
    release_notes_path, _release_notes_report = sources.get("release_notes", (None, {}))
    release_notes_policy_path = resolve_path(config_root, Path("README.release-notes.md"))
    release_notes_text = release_notes_policy_path.read_text(encoding="utf-8") if release_notes_policy_path.is_file() else ""
    blockers: list[dict[str, Any]] = [
        {"id": f"policy.{index}", "source": "policy", "severity": "high", "message": error}
        for index, error in enumerate(policy_errors)
    ]
    blockers.extend(validate_report_contract(policy, sources, load_errors or []))
    docs, doc_blockers = doc_records(config_root, policy)
    blockers.extend(doc_blockers)
    blockers.extend(evidence_marker_blockers(policy, release_notes_text))
    risks = monitored_risks(policy, sources)
    recommendation = V1ProductRecommendation.GO.value if not blockers else V1ProductRecommendation.NO_GO.value
    source_refs = {source_id: source_ref(path, payload) for source_id, (path, payload) in sorted(sources.items())}
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": V1ProductReadinessStatus.PASSED.value if not blockers else V1ProductReadinessStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path) if policy_path else None,
        "recommendation": recommendation,
        "supported_workflows": string_list(policy.get("supported_workflows")),
        "unsupported_workflows": string_list(policy.get("unsupported_workflows")),
        "release_blockers": blockers,
        "monitored_risks": risks,
        "source_refs": source_refs,
        "docs": docs,
        "summary": {
            **readiness_summary(policy, sources),
            "release_blocker_count": len(blockers),
            "monitored_risk_count": len(risks),
            "recommendation": recommendation,
        },
    }
    # Keep this reference visible for auditability even though the release notes
    # report path is also present in source_refs.
    report["release_notes_validation_report_path"] = str(release_notes_path) if release_notes_path else None
    return report


def stable_report_view(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report.get(key)
        for key in (
            "schema_version",
            "kind",
            "phase",
            "priority_backlog_id",
            "status",
            "policy_path",
            "policy_sha256",
            "recommendation",
            "supported_workflows",
            "unsupported_workflows",
            "release_blockers",
            "monitored_risks",
            "source_refs",
            "docs",
            "summary",
            "release_notes_validation_report_path",
        )
    }


def validate_v1_product_readiness_review_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    load_errors: list[str] | None = None,
    policy_path: Path | None = None,
) -> list[str]:
    expected = build_v1_product_readiness_review_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        load_errors=load_errors,
        policy_path=policy_path,
    )
    errors: list[str] = []
    if stable_report_view(report) != stable_report_view(expected):
        errors.append("report must match rebuilt V1 product readiness review")
    return errors


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# V1 Product Readiness Review",
        "",
        f"- Status: {report.get('status')}",
        f"- Recommendation: {report.get('recommendation')}",
        f"- Release blockers: {report.get('summary', {}).get('release_blocker_count')}",
        f"- Monitored risks: {report.get('summary', {}).get('monitored_risk_count')}",
        "",
        "## Supported Workflows",
        "",
    ]
    lines.extend(f"- {item}" for item in string_list(report.get("supported_workflows")))
    lines.extend(["", "## Unsupported Workflows", ""])
    lines.extend(f"- {item}" for item in string_list(report.get("unsupported_workflows")))
    lines.extend(["", "## Release Blockers", ""])
    blockers = object_list(report.get("release_blockers"))
    if blockers:
        lines.extend(f"- {item.get('id')}: {item.get('message')}" for item in blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Monitored Risks", ""])
    for risk in object_list(report.get("monitored_risks")):
        lines.append(f"- {risk.get('id')}: {risk.get('statement')}")
    return "\n".join(lines).rstrip() + "\n"


def run_v1_product_readiness_review(config: V1ProductReadinessReviewConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    sources, load_errors = load_report_inputs(config_root, policy, require_artifacts=config.require_artifacts)
    report = build_v1_product_readiness_review_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        load_errors=load_errors,
        policy_path=policy_path,
    )
    validation_errors = validate_v1_product_readiness_review_report(
        report,
        config_root=config_root,
        policy=policy,
        sources=sources,
        load_errors=load_errors,
        policy_path=policy_path,
    )
    if validation_errors:
        report["status"] = V1ProductReadinessStatus.FAILED.value
        report["recommendation"] = V1ProductRecommendation.NO_GO.value
        report["release_blockers"] = [
            *object_list(report.get("release_blockers")),
            *[
                {
                    "id": f"self_validation.{index}",
                    "source": "v1_product_readiness_review",
                    "severity": "high",
                    "message": error,
                }
                for index, error in enumerate(validation_errors)
            ],
        ]
        report["summary"]["release_blocker_count"] = len(report["release_blockers"])
        report["summary"]["recommendation"] = report["recommendation"]
    output_path = config.output_path or default_report_path(config_root)
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    if config.markdown_output_path:
        write_text(config.markdown_output_path, markdown_report(report))
        report["markdown_report_path"] = str(config.markdown_output_path.resolve())
    write_json(output_path, report)
    if config.markdown_output_path:
        write_text(config.markdown_output_path, markdown_report(report))
    return report
