"""Founder feedback triage dashboard for Priority 0 release hardening."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_KIND = "founder_feedback_triage_dashboard"
EXPECTED_POLICY_KIND = "founder_feedback_triage_dashboard_policy"
EXPECTED_PHASE = 145
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_POLICY_PATH = Path("runtime") / "founder_feedback_triage_dashboard_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "founder-feedback-triage-dashboard" / "phase145"


@dataclass(frozen=True)
class FounderFeedbackTriageConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    require_artifacts: bool = False


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"founder-feedback-triage-dashboard-{utc_timestamp()}.json"


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


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"policy.schema_version must be {SCHEMA_VERSION}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(f"policy.phase must be {EXPECTED_PHASE}")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    inputs = policy.get("inputs")
    if not isinstance(inputs, dict):
        errors.append("policy.inputs must be an object")
    else:
        for key in (
            "founder_feedback_loop_report",
            "founder_feedback_loop_cases",
            "founder_smoke_feedback_report",
            "founder_smoke_report",
            "stable_release_blocker_closure_report",
            "stable_release_blocker_closure_policy",
        ):
            if not isinstance(inputs.get(key), str) or not inputs[key]:
                errors.append(f"policy.inputs.{key} must be a path string")
    roadmap_refs = policy.get("roadmap_refs")
    if not isinstance(roadmap_refs, dict):
        errors.append("policy.roadmap_refs must be an object")
    else:
        for key in ("feedback_loop", "blocker_closure", "founder_smoke_feedback", "release_candidate_hardening"):
            ref = roadmap_refs.get(key)
            if not isinstance(ref, dict):
                errors.append(f"policy.roadmap_refs.{key} must be an object")
                continue
            if not isinstance(ref.get("phase"), int):
                errors.append(f"policy.roadmap_refs.{key}.phase must be an integer")
            if not isinstance(ref.get("backlog_id"), str) or not ref["backlog_id"]:
                errors.append(f"policy.roadmap_refs.{key}.backlog_id must be a string")
    next_actions = policy.get("decision_next_actions")
    if not isinstance(next_actions, dict):
        errors.append("policy.decision_next_actions must be an object")
    else:
        for decision in (
            "baseline_prompt_candidate",
            "baseline_candidate",
            "holdout_prompt_candidate",
            "holdout_candidate",
            "repair_followup",
            "rejected_finding",
            "skill_tool_gap",
        ):
            if not isinstance(next_actions.get(decision), str) or len(next_actions[decision]) < 20:
                errors.append(f"policy.decision_next_actions.{decision} must explain the action")
    return errors


def source_ref(path: Path | None, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path) if path else None,
        "sha256": artifact_hash(path),
        "kind": payload.get("kind"),
        "status": payload.get("status"),
        "phase": payload.get("phase"),
        "priority_backlog_id": payload.get("priority_backlog_id"),
    }


def source_artifact_errors(label: str, payload: dict[str, Any], *, expected_kind: str, require_passed: bool = False) -> list[str]:
    errors: list[str] = []
    if payload.get("kind") != expected_kind:
        errors.append(f"{label}.kind must be {expected_kind}")
    if require_passed and payload.get("status") != "passed":
        errors.append(f"{label}.status must be passed")
    artifact_errors = payload.get("errors")
    if isinstance(artifact_errors, list) and artifact_errors:
        errors.append(f"{label}.errors must be empty")
    return errors


def duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def closure_by_case(closure_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("case_id")): item
        for item in object_list(closure_report.get("founder_feedback_closures"))
        if isinstance(item.get("case_id"), str)
    }


def decision_next_action(policy: dict[str, Any], decision_kind: str) -> str:
    next_actions = policy.get("decision_next_actions") if isinstance(policy.get("decision_next_actions"), dict) else {}
    value = next_actions.get(decision_kind)
    return value if isinstance(value, str) else "Review this feedback manually before creating implementation work."


def roadmap_refs_for_decision(policy: dict[str, Any], decision_kind: str, closure: dict[str, Any] | None) -> list[dict[str, Any]]:
    refs = policy.get("roadmap_refs") if isinstance(policy.get("roadmap_refs"), dict) else {}
    keys = ["feedback_loop", "release_candidate_hardening"]
    if closure is not None:
        keys.append("blocker_closure")
    if decision_kind == "rejected_finding":
        keys.append("founder_smoke_feedback")
    return [refs[key] for key in keys if isinstance(refs.get(key), dict)]


def build_feedback_loop_records(
    *,
    policy: dict[str, Any],
    feedback_report: dict[str, Any],
    closure_report: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    closure_ids = [
        str(item.get("case_id"))
        for item in object_list(closure_report.get("founder_feedback_closures"))
        if isinstance(item.get("case_id"), str)
    ]
    closures = closure_by_case(closure_report)
    records: list[dict[str, Any]] = []
    next_actions: list[dict[str, Any]] = []
    errors: list[str] = []
    for duplicate in duplicate_values(closure_ids):
        errors.append(f"closure[{duplicate}]: duplicate closure case_id")
    for case in object_list(feedback_report.get("cases")):
        case_id = str(case.get("case_id"))
        decision = case.get("decision") if isinstance(case.get("decision"), dict) else {}
        feedback_record = case.get("feedback_record") if isinstance(case.get("feedback_record"), dict) else {}
        feedback_context = (
            feedback_record.get("feedback_context") if isinstance(feedback_record.get("feedback_context"), dict) else {}
        )
        artifact_refs = feedback_record.get("artifact_refs") if isinstance(feedback_record.get("artifact_refs"), dict) else {}
        linked_run = feedback_record.get("linked_run") if isinstance(feedback_record.get("linked_run"), dict) else {}
        record_next_action = feedback_record.get("next_action") if isinstance(feedback_record.get("next_action"), dict) else {}
        decision_kind = str(decision.get("kind") or "")
        decision_status = str(decision.get("decision_status") or "")
        target_run_id = decision.get("target_run_id")
        feedback_run_id = decision.get("feedback_run_id")
        closure = closures.get(case_id)
        validation_result = decision.get("validation_result") if isinstance(decision.get("validation_result"), dict) else {}
        required_gate = validation_result.get("required_gate")
        closure_status = closure.get("closure_status") if closure else None
        release_blocker_resolved = closure.get("release_blocker_resolved") if closure else decision_status == "rejected"
        blockers: list[str] = []
        if not isinstance(target_run_id, str) or not target_run_id:
            blockers.append("missing target_run_id")
        if not isinstance(feedback_run_id, str) or not feedback_run_id:
            blockers.append("missing feedback_run_id")
        if feedback_record.get("run_id") != feedback_run_id:
            blockers.append("feedback_run_id does not match feedback_record.run_id")
        if decision_status == "accepted" and closure is None:
            blockers.append("accepted feedback missing closure record")
        if decision_status == "accepted" and closure is not None and closure.get("release_blocker_resolved") is not True:
            blockers.append("accepted feedback closure did not resolve release blocker")
        if decision_status == "accepted" and closure is not None and required_gate != closure.get("required_gate"):
            blockers.append("closure required_gate does not match decision validation_result.required_gate")
        if decision_status == "accepted" and closure is not None and decision_kind != closure.get("decision_kind"):
            blockers.append("closure decision_kind does not match feedback decision kind")
        if decision_status == "accepted" and linked_run.get("found") is not True:
            blockers.append("accepted feedback linked target run was not found")
        if decision_status == "accepted" and not record_next_action:
            blockers.append("accepted feedback missing record next_action")
        related_run_ids = string_list(artifact_refs.get("mentioned_run_ids"))
        downstream_run_id = feedback_context.get("downstream_run_id")
        if isinstance(downstream_run_id, str) and downstream_run_id and downstream_run_id not in related_run_ids:
            related_run_ids.append(downstream_run_id)
        action_reason = (
            "Release blocker resolved."
            if release_blocker_resolved
            else decision_next_action(policy, decision_kind)
        )
        record = {
            "source": "founder_feedback_loop",
            "decision_namespace": "founder_feedback_loop",
            "case_id": case_id,
            "status": case.get("status"),
            "surface": case.get("surface"),
            "target_root": case.get("target_root"),
            "target_run_id": target_run_id,
            "feedback_run_id": feedback_run_id,
            "related_run_ids": related_run_ids,
            "linked_run": {
                "found": linked_run.get("found"),
                "run_id": linked_run.get("run_id"),
                "workflow": linked_run.get("workflow"),
                "status": linked_run.get("status"),
            },
            "target_workflow": decision.get("target_workflow"),
            "selected_workflow": feedback_context.get("selected_workflow"),
            "selected_skills": feedback_context.get("selected_skills") if isinstance(feedback_context.get("selected_skills"), list) else [],
            "selected_tools": feedback_context.get("selected_tools") if isinstance(feedback_context.get("selected_tools"), list) else [],
            "classifications": feedback_record.get("classifications") if isinstance(feedback_record.get("classifications"), list) else [],
            "decision_kind": decision_kind,
            "decision_status": decision_status,
            "gap_class": decision.get("gap_class"),
            "required_gate": required_gate,
            "validation_status": validation_result.get("status"),
            "closure_status": closure_status,
            "release_blocker_resolved": release_blocker_resolved,
            "roadmap_refs": roadmap_refs_for_decision(policy, decision_kind, closure),
            "record_next_action": record_next_action,
            "next_action": {
                "kind": "none" if release_blocker_resolved else decision_kind,
                "reason": action_reason,
            },
            "blockers": blockers,
        }
        if blockers:
            next_actions.append(
                {
                    "source": "founder_feedback_loop",
                    "case_id": case_id,
                    "severity": "blocker",
                    "action": decision_next_action(policy, decision_kind),
                    "blockers": blockers,
                }
            )
            errors.extend(f"feedback_loop[{case_id}]: {blocker}" for blocker in blockers)
        records.append(record)
    return records, next_actions, errors


def build_smoke_records(
    *,
    policy: dict[str, Any],
    smoke_feedback_report: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    next_actions: list[dict[str, Any]] = []
    errors: list[str] = []
    refs = policy.get("roadmap_refs") if isinstance(policy.get("roadmap_refs"), dict) else {}
    seen_rows: set[str] = set()
    for item in object_list(smoke_feedback_report.get("classifications")):
        decision_kind = str(item.get("decision_kind") or "")
        case_id = str(item.get("case_id") or "")
        action = decision_next_action(policy, decision_kind)
        row_key = f"founder_smoke_feedback:{case_id}"
        blockers: list[str] = []
        if row_key in seen_rows:
            blockers.append("duplicate smoke feedback classification row")
        seen_rows.add(row_key)
        if decision_kind != "rejected_finding" and not isinstance(item.get("run_id"), str):
            blockers.append("actionable smoke feedback missing source run_id")
        if decision_kind != "rejected_finding" and action.startswith("Review this feedback manually"):
            blockers.append("actionable smoke feedback cannot map to governed next action")
        record = {
            "source": "founder_smoke_feedback",
            "decision_namespace": "founder_smoke_feedback",
            "case_id": case_id,
            "status": item.get("status"),
            "run_id": item.get("run_id"),
            "related_run_ids": [item["run_id"]] if isinstance(item.get("run_id"), str) else [],
            "expected_workflow": item.get("expected_workflow"),
            "decision_kind": decision_kind,
            "gap_class": item.get("gap_class"),
            "roadmap_refs": [
                refs[key]
                for key in ("founder_smoke_feedback", "release_candidate_hardening")
                if isinstance(refs.get(key), dict)
            ],
            "next_action": {
                "kind": "none" if decision_kind == "rejected_finding" else decision_kind,
                "reason": action,
            },
            "blockers": blockers,
        }
        if decision_kind != "rejected_finding":
            next_actions.append(
                {
                    "source": "founder_smoke_feedback",
                    "case_id": case_id,
                    "severity": "blocker" if blockers else "actionable",
                    "action": action,
                    "blockers": blockers,
                }
            )
        errors.extend(f"smoke_feedback[{case_id}]: {blocker}" for blocker in blockers)
        records.append(record)
    actionable_count = sum(1 for item in records if item.get("decision_kind") != "rejected_finding")
    summary = smoke_feedback_report.get("summary") if isinstance(smoke_feedback_report.get("summary"), dict) else {}
    if actionable_count != int(summary.get("actionable_feedback_count", actionable_count)):
        errors.append("smoke actionable feedback count does not match classification records")
    return records, next_actions, errors


def build_founder_feedback_triage_dashboard(
    *,
    policy: dict[str, Any],
    feedback_report: dict[str, Any],
    feedback_cases_catalog: dict[str, Any] | None = None,
    smoke_feedback_report: dict[str, Any],
    smoke_source_report: dict[str, Any] | None = None,
    closure_report: dict[str, Any],
    closure_policy: dict[str, Any] | None = None,
    policy_path: Path | None = None,
    feedback_report_path: Path | None = None,
    feedback_cases_path: Path | None = None,
    smoke_feedback_report_path: Path | None = None,
    smoke_source_report_path: Path | None = None,
    closure_report_path: Path | None = None,
    closure_policy_path: Path | None = None,
) -> dict[str, Any]:
    errors = validate_policy(policy)
    feedback_cases_catalog = feedback_cases_catalog or {}
    smoke_source_report = smoke_source_report or {}
    closure_policy = closure_policy or {}
    errors.extend(
        source_artifact_errors(
            "founder_feedback_loop_report",
            feedback_report,
            expected_kind="founder_feedback_loop_live_report",
            require_passed=True,
        )
    )
    errors.extend(
        source_artifact_errors(
            "founder_feedback_loop_cases",
            feedback_cases_catalog,
            expected_kind="founder_feedback_loop_cases",
        )
    )
    errors.extend(
        source_artifact_errors(
            "founder_smoke_feedback_report",
            smoke_feedback_report,
            expected_kind="founder_smoke_feedback_classification",
            require_passed=True,
        )
    )
    errors.extend(
        source_artifact_errors(
            "founder_smoke_report",
            smoke_source_report,
            expected_kind="founder_field_prompt_evaluation",
            require_passed=True,
        )
    )
    errors.extend(
        source_artifact_errors(
            "stable_release_blocker_closure_report",
            closure_report,
            expected_kind="stable_release_blocker_closure_report",
            require_passed=True,
        )
    )
    errors.extend(
        source_artifact_errors(
            "stable_release_blocker_closure_policy",
            closure_policy,
            expected_kind="stable_release_blocker_closure_policy",
        )
    )

    feedback_records, feedback_actions, feedback_errors = build_feedback_loop_records(
        policy=policy,
        feedback_report=feedback_report,
        closure_report=closure_report,
    )
    smoke_records, smoke_actions, smoke_errors = build_smoke_records(
        policy=policy,
        smoke_feedback_report=smoke_feedback_report,
    )
    errors.extend(feedback_errors)
    errors.extend(smoke_errors)
    feedback_case_ids = [
        str(item.get("case_id"))
        for item in object_list(feedback_report.get("cases"))
        if isinstance(item.get("case_id"), str)
    ]
    closure_case_ids = [
        str(item.get("case_id"))
        for item in object_list(closure_report.get("founder_feedback_closures"))
        if isinstance(item.get("case_id"), str)
    ]
    for duplicate in duplicate_values(feedback_case_ids):
        errors.append(f"feedback_loop[{duplicate}]: duplicate feedback case_id")
    feedback_run_ids = [
        str(item.get("feedback_run_id"))
        for item in feedback_records
        if isinstance(item.get("feedback_run_id"), str) and item.get("feedback_run_id")
    ]
    for duplicate in duplicate_values(feedback_run_ids):
        errors.append(f"feedback_run_id[{duplicate}]: duplicate feedback_run_id")
    extra_closure_ids = sorted(set(closure_case_ids) - set(feedback_case_ids))
    errors.extend(f"closure[{case_id}]: extra closure ID has no current feedback case" for case_id in extra_closure_ids)
    rows = [f"{item.get('source')}:{item.get('case_id')}" for item in feedback_records + smoke_records]
    for duplicate in duplicate_values(rows):
        errors.append(f"dashboard_row[{duplicate}]: duplicate source/case row")
    open_actions = feedback_actions + smoke_actions
    accepted_records = [item for item in feedback_records if item.get("decision_status") == "accepted"]
    rejected_records = [item for item in feedback_records if item.get("decision_status") == "rejected"]
    closed_records = [
        item
        for item in feedback_records
        if item.get("decision_status") == "rejected" or item.get("release_blocker_resolved") is True
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": "passed" if not errors else "failed",
        "generated_at": utc_timestamp(),
        "source_refs": {
            "policy": source_ref(policy_path, policy),
            "founder_feedback_loop_report": source_ref(feedback_report_path, feedback_report),
            "founder_feedback_loop_cases": source_ref(feedback_cases_path, feedback_cases_catalog),
            "founder_smoke_feedback_report": source_ref(smoke_feedback_report_path, smoke_feedback_report),
            "founder_smoke_report": source_ref(smoke_source_report_path, smoke_source_report),
            "stable_release_blocker_closure_report": source_ref(closure_report_path, closure_report),
            "stable_release_blocker_closure_policy": source_ref(closure_policy_path, closure_policy),
        },
        "summary": {
            "feedback_loop_case_count": len(feedback_records),
            "feedback_record_count": len(feedback_records),
            "accepted_feedback_count": len(accepted_records),
            "rejected_feedback_count": len(rejected_records),
            "closed_feedback_count": len(closed_records),
            "unresolved_feedback_count": len(feedback_records) - len(closed_records),
            "smoke_classification_count": len(smoke_records),
            "smoke_actionable_feedback_count": sum(
                1 for item in smoke_records if item.get("decision_kind") != "rejected_finding"
            ),
            "open_next_action_count": len(open_actions),
            "blocker_count": sum(1 for item in open_actions if item.get("severity") == "blocker"),
        },
        "feedback_records": feedback_records,
        "smoke_feedback_records": smoke_records,
        "next_actions": open_actions,
        "errors": errors,
    }


def validate_founder_feedback_triage_dashboard(
    report: dict[str, Any],
    *,
    policy: dict[str, Any],
    feedback_report: dict[str, Any],
    feedback_cases_catalog: dict[str, Any] | None = None,
    smoke_feedback_report: dict[str, Any],
    smoke_source_report: dict[str, Any] | None = None,
    closure_report: dict[str, Any],
    closure_policy: dict[str, Any] | None = None,
    policy_path: Path | None = None,
    feedback_report_path: Path | None = None,
    feedback_cases_path: Path | None = None,
    smoke_feedback_report_path: Path | None = None,
    smoke_source_report_path: Path | None = None,
    closure_report_path: Path | None = None,
    closure_policy_path: Path | None = None,
) -> list[str]:
    expected = build_founder_feedback_triage_dashboard(
        policy=policy,
        feedback_report=feedback_report,
        feedback_cases_catalog=feedback_cases_catalog,
        smoke_feedback_report=smoke_feedback_report,
        smoke_source_report=smoke_source_report,
        closure_report=closure_report,
        closure_policy=closure_policy,
        policy_path=policy_path,
        feedback_report_path=feedback_report_path,
        feedback_cases_path=feedback_cases_path,
        smoke_feedback_report_path=smoke_feedback_report_path,
        smoke_source_report_path=smoke_source_report_path,
        closure_report_path=closure_report_path,
        closure_policy_path=closure_policy_path,
    )
    errors: list[str] = []
    for key in (
        "schema_version",
        "kind",
        "phase",
        "priority_backlog_id",
        "status",
        "source_refs",
        "summary",
        "feedback_records",
        "smoke_feedback_records",
        "next_actions",
        "errors",
    ):
        if report.get(key) != expected.get(key):
            errors.append(f"report.{key} must match rebuilt founder feedback triage dashboard")
    return errors


def run_founder_feedback_triage_dashboard(config: FounderFeedbackTriageConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    policy_missing = config.require_artifacts and not policy_path.is_file()
    policy = read_json_object(policy_path) if policy_path.is_file() else {}
    input_paths = policy.get("inputs") if isinstance(policy.get("inputs"), dict) else {}
    feedback_path = resolve_path(config_root, str(input_paths.get("founder_feedback_loop_report", "")))
    feedback_cases_path = resolve_path(config_root, str(input_paths.get("founder_feedback_loop_cases", "")))
    smoke_path = resolve_path(config_root, str(input_paths.get("founder_smoke_feedback_report", "")))
    smoke_source_path = resolve_path(config_root, str(input_paths.get("founder_smoke_report", "")))
    closure_path = resolve_path(config_root, str(input_paths.get("stable_release_blocker_closure_report", "")))
    closure_policy_path = resolve_path(config_root, str(input_paths.get("stable_release_blocker_closure_policy", "")))
    missing_paths = [
        path
        for path in (policy_path, feedback_path, feedback_cases_path, smoke_path, smoke_source_path, closure_path, closure_policy_path)
        if config.require_artifacts and not path.is_file()
    ]
    feedback_report = read_json_object(feedback_path) if feedback_path.is_file() else {}
    feedback_cases = read_json_object(feedback_cases_path) if feedback_cases_path.is_file() else {}
    smoke_report = read_json_object(smoke_path) if smoke_path.is_file() else {}
    smoke_source_report = read_json_object(smoke_source_path) if smoke_source_path.is_file() else {}
    closure_report = read_json_object(closure_path) if closure_path.is_file() else {}
    closure_policy = read_json_object(closure_policy_path) if closure_policy_path.is_file() else {}
    report = build_founder_feedback_triage_dashboard(
        policy=policy,
        feedback_report=feedback_report,
        feedback_cases_catalog=feedback_cases,
        smoke_feedback_report=smoke_report,
        smoke_source_report=smoke_source_report,
        closure_report=closure_report,
        closure_policy=closure_policy,
        policy_path=policy_path if not policy_missing else None,
        feedback_report_path=feedback_path if feedback_path.is_file() else None,
        feedback_cases_path=feedback_cases_path if feedback_cases_path.is_file() else None,
        smoke_feedback_report_path=smoke_path if smoke_path.is_file() else None,
        smoke_source_report_path=smoke_source_path if smoke_source_path.is_file() else None,
        closure_report_path=closure_path if closure_path.is_file() else None,
        closure_policy_path=closure_policy_path if closure_policy_path.is_file() else None,
    )
    if missing_paths:
        report["status"] = "failed"
        report["errors"] = list(report.get("errors", [])) + [
            f"required artifact is missing: {path}" for path in missing_paths
        ]
    validation_errors = validate_founder_feedback_triage_dashboard(
        report,
        policy=policy,
        feedback_report=feedback_report,
        feedback_cases_catalog=feedback_cases,
        smoke_feedback_report=smoke_report,
        smoke_source_report=smoke_source_report,
        closure_report=closure_report,
        closure_policy=closure_policy,
        policy_path=policy_path if not policy_missing else None,
        feedback_report_path=feedback_path if feedback_path.is_file() else None,
        feedback_cases_path=feedback_cases_path if feedback_cases_path.is_file() else None,
        smoke_feedback_report_path=smoke_path if smoke_path.is_file() else None,
        smoke_source_report_path=smoke_source_path if smoke_source_path.is_file() else None,
        closure_report_path=closure_path if closure_path.is_file() else None,
        closure_policy_path=closure_policy_path if closure_policy_path.is_file() else None,
    )
    if validation_errors:
        report["status"] = "failed"
        report["errors"] = list(report.get("errors", [])) + validation_errors
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
