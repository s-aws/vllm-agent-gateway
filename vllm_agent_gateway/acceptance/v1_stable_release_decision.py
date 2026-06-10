"""Final V1 stable founder-testing release decision gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "v1_stable_release_decision_policy"
EXPECTED_REPORT_KIND = "v1_stable_release_decision_report"
EXPECTED_PHASE = 156
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_POLICY_PATH = Path("runtime") / "v1_stable_release_decision_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "v1-stable-release-decision" / "phase156"
REQUIRED_REPORT_IDS = {
    "v1_product_readiness_review",
    "stable_chat_quality_release",
    "release_notes",
    "stable_release_reset_rehearsal",
    "model_swap_smoke_probe",
    "stable_proof",
}
REQUIRED_DECISIONS = {"release_for_founder_testing", "blocked"}
REQUIRED_RELEASE_SCOPE = {
    "local_founder_testing",
    "anythingllm_workflow_router_path",
    "current_localhost_model",
    "two_frozen_coinbase_fixtures",
    "format_a_and_json_output",
    "read_only_l1_l2_and_narrow_draft_workflows",
}
REQUIRED_RELEASE_LIMITATIONS = {
    "not_production_deployment",
    "not_advanced_broad_refactor_orchestration",
    "not_every_repository_language_or_coding_task",
    "not_direct_mutation_of_protected_fixtures",
    "not_unsupported_output_format_parity",
    "not_automatic_model_selection",
}


class V1StableReleaseDecisionStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class V1StableReleaseDecision(str, Enum):
    RELEASE = "release_for_founder_testing"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class V1StableReleaseDecisionConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    markdown_output_path: Path | None = None
    require_artifacts: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"v1-stable-release-decision-{utc_timestamp()}.json"


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


def string_value(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 156")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if set(string_list(policy.get("allowed_decisions"))) != REQUIRED_DECISIONS:
        errors.append("policy.allowed_decisions must contain release_for_founder_testing and blocked")
    reports = object_list(policy.get("required_reports"))
    ids = [str(item.get("id")) for item in reports if isinstance(item.get("id"), str)]
    if set(ids) != REQUIRED_REPORT_IDS:
        errors.append("policy.required_reports must contain the governed report IDs")
    if len(ids) != len(set(ids)):
        errors.append("policy.required_reports ids must be unique")
    for index, item in enumerate(reports):
        prefix = f"policy.required_reports[{index}]"
        for key in ("id", "path", "expected_kind", "expected_status"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(f"{prefix}.{key} must be a non-empty string")
    for field in ("required_docs", "required_final_markers"):
        if not string_list(policy.get(field)):
            errors.append(f"policy.{field} must be a non-empty list")
    if set(string_list(policy.get("release_scope"))) != REQUIRED_RELEASE_SCOPE:
        errors.append("policy.release_scope must match the governed release scope")
    if set(string_list(policy.get("release_limitations"))) != REQUIRED_RELEASE_LIMITATIONS:
        errors.append("policy.release_limitations must match the governed release limitations")
    if not string_value(policy.get("rollback_path")):
        errors.append("policy.rollback_path must be a non-empty string")
    if not string_value(policy.get("next_roadmap_batch")):
        errors.append("policy.next_roadmap_batch must be a non-empty string")
    return errors


def report_policy_by_id(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in object_list(policy.get("required_reports"))
        if isinstance(item.get("id"), str)
    }


def load_sources(config_root: Path, policy: dict[str, Any], *, require_artifacts: bool) -> tuple[dict[str, tuple[Path | None, dict[str, Any]]], list[str]]:
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
        "recommendation": payload.get("recommendation"),
        "decision": dict_value(payload.get("decision")).get("decision"),
        "profile": payload.get("profile"),
    }


def contract_blockers(
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    load_errors: list[str],
) -> list[dict[str, Any]]:
    blockers = [
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
        expected_phase = item.get("expected_phase")
        if isinstance(expected_phase, int) and payload.get("phase") != expected_phase:
            messages.append(f"phase must be {expected_phase}")
        expected_readiness = item.get("expected_readiness")
        if isinstance(expected_readiness, str) and payload.get("readiness") != expected_readiness:
            messages.append(f"readiness must be {expected_readiness}")
        expected_recommendation = item.get("expected_recommendation")
        if isinstance(expected_recommendation, str) and payload.get("recommendation") != expected_recommendation:
            messages.append(f"recommendation must be {expected_recommendation}")
        expected_decision = item.get("expected_decision")
        if isinstance(expected_decision, str) and dict_value(payload.get("decision")).get("decision") != expected_decision:
            messages.append(f"decision must be {expected_decision}")
        expected_profile = item.get("expected_profile")
        if isinstance(expected_profile, str) and payload.get("profile") != expected_profile:
            messages.append(f"profile must be {expected_profile}")
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
    docs: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        exists = path.is_file()
        docs.append({"path": str(path), "exists": exists, "sha256": artifact_hash(path)})
        if not exists:
            blockers.append(
                {
                    "id": f"doc_missing.{raw_path}",
                    "source": "documentation",
                    "severity": "medium",
                    "message": f"required doc is missing: {raw_path}",
                }
            )
    return docs, blockers


def marker_blockers(policy: dict[str, Any], report_text: str) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for marker in string_list(policy.get("required_final_markers")):
        if marker not in report_text:
            blockers.append(
                {
                    "id": f"final_marker_missing.{marker}",
                    "source": "final_decision",
                    "severity": "medium",
                    "message": f"final decision missing marker: {marker}",
                }
            )
    return blockers


def final_text(
    *,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    decision: str,
) -> str:
    readiness = sources.get("stable_chat_quality_release", (None, {}))[1].get("readiness")
    model_decision = dict_value(sources.get("model_swap_smoke_probe", (None, {}))[1].get("decision"))
    review = sources.get("v1_product_readiness_review", (None, {}))[1]
    lines = [
        f"decision={decision}",
        f"product_readiness_recommendation={review.get('recommendation')}",
        f"release_readiness={readiness}",
        f"model_swap_decision={model_decision.get('decision')}",
        "model_ids=" + ",".join(string_list(model_decision.get("actual_model_ids"))),
        "workflow_router_target=http://127.0.0.1:8500/v1",
        "stable_proof=runtime/release_proofs/v1-1-release-candidate-stable-proof.json",
        "scope=" + ",".join(string_list(policy.get("release_scope"))),
        "limitations=" + ",".join(string_list(policy.get("release_limitations"))),
        f"rollback_path={string_value(policy.get('rollback_path'))}",
        f"next_roadmap_batch={string_value(policy.get('next_roadmap_batch'))}",
    ]
    return "\n".join(lines)


def build_v1_stable_release_decision_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    load_errors: list[str] | None = None,
    policy_path: Path | None = None,
) -> dict[str, Any]:
    policy_errors = validate_policy(policy)
    blockers = [
        {"id": f"policy.{index}", "source": "policy", "severity": "high", "message": error}
        for index, error in enumerate(policy_errors)
    ]
    blockers.extend(contract_blockers(policy, sources, load_errors or []))
    docs, doc_blockers = doc_records(config_root, policy)
    blockers.extend(doc_blockers)
    decision = V1StableReleaseDecision.RELEASE.value if not blockers else V1StableReleaseDecision.BLOCKED.value
    decision_text = final_text(policy=policy, sources=sources, decision=decision)
    blockers.extend(marker_blockers(policy, decision_text))
    if blockers:
        decision = V1StableReleaseDecision.BLOCKED.value
        decision_text = final_text(policy=policy, sources=sources, decision=decision)
    source_refs = {source_id: source_ref(path, payload) for source_id, (path, payload) in sorted(sources.items())}
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": V1StableReleaseDecisionStatus.PASSED.value if decision == V1StableReleaseDecision.RELEASE.value else V1StableReleaseDecisionStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "policy_path": str(policy_path or DEFAULT_POLICY_PATH),
        "policy_sha256": artifact_hash(policy_path) if policy_path else None,
        "decision": decision,
        "decision_text": decision_text,
        "release_scope": string_list(policy.get("release_scope")),
        "release_limitations": string_list(policy.get("release_limitations")),
        "rollback_path": string_value(policy.get("rollback_path")),
        "next_roadmap_batch": string_value(policy.get("next_roadmap_batch")),
        "release_blockers": blockers,
        "source_refs": source_refs,
        "docs": docs,
        "summary": {
            "decision": decision,
            "release_blocker_count": len(blockers),
            "evidence_link_count": len(source_refs),
            "doc_count": len(docs),
            "limitation_count": len(string_list(policy.get("release_limitations"))),
            "scope_count": len(string_list(policy.get("release_scope"))),
            "rollback_path_present": bool(string_value(policy.get("rollback_path"))),
            "next_roadmap_batch_present": bool(string_value(policy.get("next_roadmap_batch"))),
            "product_readiness_recommendation": sources.get("v1_product_readiness_review", (None, {}))[1].get("recommendation"),
            "model_swap_decision": dict_value(sources.get("model_swap_smoke_probe", (None, {}))[1].get("decision")).get("decision"),
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
            "policy_path",
            "policy_sha256",
            "decision",
            "decision_text",
            "release_scope",
            "release_limitations",
            "rollback_path",
            "next_roadmap_batch",
            "release_blockers",
            "source_refs",
            "docs",
            "summary",
        )
    }


def validate_v1_stable_release_decision_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    sources: dict[str, tuple[Path | None, dict[str, Any]]],
    load_errors: list[str] | None = None,
    policy_path: Path | None = None,
) -> list[str]:
    expected = build_v1_stable_release_decision_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        load_errors=load_errors,
        policy_path=policy_path,
    )
    if stable_view(report) != stable_view(expected):
        return ["report must match rebuilt V1 stable release decision"]
    return []


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# V1 Stable Release Decision",
        "",
        f"- Status: {report.get('status')}",
        f"- Decision: {report.get('decision')}",
        f"- Release blockers: {report.get('summary', {}).get('release_blocker_count')}",
        "",
        "## Scope",
        "",
    ]
    lines.extend(f"- {item}" for item in string_list(report.get("release_scope")))
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in string_list(report.get("release_limitations")))
    lines.extend(["", "## Rollback Path", "", string_value(report.get("rollback_path"))])
    lines.extend(["", "## Next Roadmap Batch", "", string_value(report.get("next_roadmap_batch"))])
    lines.extend(["", "## Evidence", ""])
    for source_id, ref in sorted(dict_value(report.get("source_refs")).items()):
        lines.append(f"- {source_id}: {ref.get('path')}")
    lines.extend(["", "## Blockers", ""])
    blockers = object_list(report.get("release_blockers"))
    if blockers:
        lines.extend(f"- {item.get('id')}: {item.get('message')}" for item in blockers)
    else:
        lines.append("- none")
    return "\n".join(lines).rstrip() + "\n"


def run_v1_stable_release_decision(config: V1StableReleaseDecisionConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy = read_json_object(policy_path)
    sources, load_errors = load_sources(config_root, policy, require_artifacts=config.require_artifacts)
    report = build_v1_stable_release_decision_report(
        config_root=config_root,
        policy=policy,
        sources=sources,
        load_errors=load_errors,
        policy_path=policy_path,
    )
    validation_errors = validate_v1_stable_release_decision_report(
        report,
        config_root=config_root,
        policy=policy,
        sources=sources,
        load_errors=load_errors,
        policy_path=policy_path,
    )
    if validation_errors:
        report["status"] = V1StableReleaseDecisionStatus.FAILED.value
        report["decision"] = V1StableReleaseDecision.BLOCKED.value
        report["release_blockers"] = [
            *object_list(report.get("release_blockers")),
            *[
                {
                    "id": f"self_validation.{index}",
                    "source": "v1_stable_release_decision",
                    "severity": "high",
                    "message": error,
                }
                for index, error in enumerate(validation_errors)
            ],
        ]
        report["summary"]["decision"] = report["decision"]
        report["summary"]["release_blocker_count"] = len(report["release_blockers"])
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
