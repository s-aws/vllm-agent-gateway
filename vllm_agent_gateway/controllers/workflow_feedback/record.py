"""Controller-owned workflow feedback recording."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus


WORKFLOW_ID = "workflow_feedback.record"
SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = "workflow-feedback"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
LIST_FEEDBACK_FIELDS = ("useful", "wrong", "missing", "too_slow", "too_noisy", "confusing", "unsafe")
SCALAR_FEEDBACK_FIELDS = {"notes"}
FEEDBACK_FIELDS = set(LIST_FEEDBACK_FIELDS) | SCALAR_FEEDBACK_FIELDS
CORE_CONTEXT_SKILLS = {"request-triage", "scope-and-assumptions", "entrypoint-finder", "context-plan-builder"}


class WorkflowFeedbackError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "workflow_feedback_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class WorkflowFeedbackRecordRequest:
    output_root: Path | str = ".agentic_controller"
    run_registry_root: Path | str = ".agentic_controller/controller-runs"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    target_workflow: str = ""
    target_run_id: str = ""
    target_root: Path | str | None = None
    feedback: dict[str, Any] = field(default_factory=dict)
    tester: dict[str, Any] = field(default_factory=dict)
    request_payload: dict[str, Any] = field(default_factory=dict)
    artifact_refs: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        output_root: Path,
        run_registry_root: Path,
        target_root: Path | None,
    ) -> "WorkflowFeedbackRecordRequest":
        values: dict[str, Any] = {
            "output_root": output_root,
            "run_registry_root": run_registry_root,
            "target_root": target_root,
        }
        names = {item.name for item in fields(cls)}
        for key, value in payload.items():
            if key in names:
                values[key] = value
        return cls(**values)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2) + "\n").encode("utf-8")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def bounded_string(value: str, limit: int = 4000) -> str:
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


def bounded_json_value(value: Any, *, depth: int = 0, max_depth: int = 5) -> Any:
    if depth > max_depth:
        return {"truncated": "max_depth"}
    if value is None or isinstance(value, bool) or isinstance(value, int) or isinstance(value, float):
        return value
    if isinstance(value, str):
        return bounded_string(value)
    if isinstance(value, list):
        items = [bounded_json_value(item, depth=depth + 1, max_depth=max_depth) for item in value[:50]]
        if len(value) > 50:
            items.append({"truncated_items": len(value) - 50})
        return items
    if isinstance(value, dict):
        selected: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 50:
                selected["truncated_keys"] = len(value) - 50
                break
            if isinstance(key, str):
                selected[bounded_string(key, 200)] = bounded_json_value(item, depth=depth + 1, max_depth=max_depth)
        return selected
    return bounded_string(str(value))


def require_string(value: Any, label: str, *, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowFeedbackError(f"{label} is required.", code=code, status=HTTPStatus.BAD_REQUEST)
    return value


def require_object(value: Any, label: str, *, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkflowFeedbackError(f"{label} must be a JSON object.", code=code, status=HTTPStatus.BAD_REQUEST)
    return value


def normalize_feedback(feedback: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(feedback) - FEEDBACK_FIELDS)
    if unknown:
        raise WorkflowFeedbackError(
            f"Unsupported feedback field(s): {', '.join(unknown)}",
            code="unsupported_feedback_field",
            status=HTTPStatus.BAD_REQUEST,
        )
    normalized: dict[str, Any] = {}
    has_signal = False
    for key in LIST_FEEDBACK_FIELDS:
        value = feedback.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise WorkflowFeedbackError(
                f"feedback.{key} must be a list of strings.",
                code="invalid_feedback_field",
                status=HTTPStatus.BAD_REQUEST,
            )
        selected = [bounded_string(item.strip(), 1000) for item in value if item.strip()]
        normalized[key] = selected
        has_signal = has_signal or bool(selected)
    notes = feedback.get("notes", "")
    if notes is None:
        notes = ""
    if not isinstance(notes, str):
        raise WorkflowFeedbackError(
            "feedback.notes must be a string.",
            code="invalid_feedback_field",
            status=HTTPStatus.BAD_REQUEST,
        )
    normalized["notes"] = bounded_string(notes.strip(), 4000)
    has_signal = has_signal or bool(normalized["notes"])
    if not has_signal:
        raise WorkflowFeedbackError(
            "feedback must include at least one useful, wrong, missing, too_slow, too_noisy, confusing, unsafe, or notes entry.",
            code="empty_feedback",
            status=HTTPStatus.BAD_REQUEST,
        )
    return normalized


def validate_request(request: WorkflowFeedbackRecordRequest) -> dict[str, Any]:
    if request.workflow != WORKFLOW_ID:
        raise WorkflowFeedbackError("workflow must be workflow_feedback.record.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise WorkflowFeedbackError("schema_version must be 1.", code="unsupported_schema_version")
    target_workflow = require_string(request.target_workflow, "target_workflow", code="missing_target_workflow")
    target_run_id = require_string(request.target_run_id, "target_run_id", code="missing_target_run_id")
    if not RUN_ID_RE.fullmatch(target_run_id):
        raise WorkflowFeedbackError("target_run_id has an invalid format.", code="invalid_target_run_id")
    feedback = normalize_feedback(require_object(request.feedback, "feedback", code="missing_feedback"))
    tester = require_object(request.tester, "tester", code="invalid_tester") if request.tester else {}
    request_payload = (
        require_object(request.request_payload, "request_payload", code="invalid_request_payload")
        if request.request_payload
        else {}
    )
    artifact_refs = (
        require_object(request.artifact_refs, "artifact_refs", code="invalid_artifact_refs")
        if request.artifact_refs
        else {}
    )
    return {
        "target_workflow": target_workflow,
        "target_run_id": target_run_id,
        "feedback": feedback,
        "tester": bounded_json_value(tester),
        "request_payload": bounded_json_value(request_payload),
        "artifact_refs": bounded_json_value(artifact_refs),
    }


def load_linked_run_record(run_registry_root: Path, target_run_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    path = run_registry_root / f"{target_run_id}.json"
    if not path.exists():
        warnings.append({"warning": "target_run_record_not_found", "target_run_id": target_run_id})
        return None, warnings
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        warnings.append({"warning": "target_run_record_invalid_json", "target_run_id": target_run_id, "detail": str(exc)})
        return None, warnings
    if not isinstance(value, dict) or value.get("kind") != "controller_run_record":
        warnings.append({"warning": "target_run_record_invalid_shape", "target_run_id": target_run_id})
        return None, warnings
    return value, warnings


def linked_run_summary(record: dict[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {"found": False}
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    return {
        "found": True,
        "run_id": record.get("run_id"),
        "workflow": record.get("workflow"),
        "status": record.get("status"),
        "artifact_keys": sorted(key for key in artifacts if isinstance(key, str)),
    }


def feedback_counts(feedback: dict[str, Any]) -> dict[str, int]:
    return {key: len(feedback.get(key, [])) for key in LIST_FEEDBACK_FIELDS}


def feedback_classifications(feedback: dict[str, Any]) -> list[str]:
    classifications: list[str] = []
    mapping = {
        "useful": "useful",
        "wrong": "wrong",
        "missing": "missing",
        "too_slow": "slow",
        "too_noisy": "noisy",
        "confusing": "confusing",
        "unsafe": "unsafe",
    }
    for field_name, classification in mapping.items():
        values = feedback.get(field_name)
        if isinstance(values, list) and values:
            classifications.append(classification)
    if not classifications and feedback.get("notes"):
        classifications.append("notes")
    return classifications


def feedback_text(feedback: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in feedback.values():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(item for item in value if isinstance(item, str))
    return "\n".join(parts).lower()


def feedback_governance_decision(
    classifications: list[str],
    context: dict[str, Any],
    feedback: dict[str, Any],
) -> dict[str, Any]:
    normalized = [item for item in classifications if isinstance(item, str)]
    text = feedback_text(feedback)
    prompt_case_id = context.get("prompt_case") if isinstance(context.get("prompt_case"), str) else None
    target_run_id = context.get("target_run_id") if isinstance(context.get("target_run_id"), str) else None
    target_workflow = context.get("selected_workflow") or context.get("target_workflow")
    base = {
        "kind": "manual_triage_required",
        "decision_status": "blocked",
        "gap_class": "none",
        "target_run_id": target_run_id,
        "feedback_run_id": None,
        "target_workflow": target_workflow,
        "prompt_case_id": prompt_case_id,
        "mutation_policy": "controller_artifacts_only",
        "validation_result": {
            "status": "failed",
            "reason": "feedback classifications did not map to a governed decision",
        },
    }
    if "unsafe" in normalized:
        return {
            **base,
            "kind": "repair_followup",
            "decision_status": "accepted",
            "gap_class": "safety_boundary",
            "validation_result": {"status": "recorded_pending_eval", "required_gate": "safety_boundary_review"},
        }
    if "wrong" in normalized:
        return {
            **base,
            "kind": "repair_followup",
            "decision_status": "accepted",
            "gap_class": "model_capability",
            "validation_result": {"status": "recorded_pending_eval", "required_gate": "eval_repair_loop"},
        }
    if "missing" in normalized:
        if "holdout" in text:
            return {
                **base,
                "kind": "holdout_prompt_candidate",
                "decision_status": "accepted",
                "gap_class": "test_coverage",
                "validation_result": {"status": "recorded_pending_eval", "required_gate": "holdout_prompt_bank"},
            }
        return {
            **base,
            "kind": "baseline_prompt_candidate",
            "decision_status": "accepted",
            "gap_class": "deterministic_formatter",
            "validation_result": {"status": "recorded_pending_eval", "required_gate": "baseline_corpus"},
        }
    if "confusing" in normalized or "noisy" in normalized:
        return {
            **base,
            "kind": "repair_followup",
            "decision_status": "accepted",
            "gap_class": "deterministic_formatter",
            "validation_result": {"status": "recorded_pending_eval", "required_gate": "answer_usefulness"},
        }
    if "slow" in normalized:
        return {
            **base,
            "kind": "repair_followup",
            "decision_status": "accepted",
            "gap_class": "model_capability",
            "validation_result": {"status": "recorded_pending_eval", "required_gate": "drift_gate"},
        }
    if "useful" in normalized:
        return {
            **base,
            "kind": "rejected_finding",
            "decision_status": "rejected",
            "gap_class": "none",
            "validation_result": {"status": "passed", "reason": "useful-only feedback does not create repair work"},
        }
    return base


def safe_json_artifact(path_value: Any, output_root: Path) -> dict[str, Any] | None:
    if not isinstance(path_value, str) or not path_value.strip():
        return None
    path = Path(path_value)
    try:
        resolved = path.resolve()
        resolved.relative_to(output_root.resolve())
    except (OSError, ValueError):
        return None
    if not resolved.is_file():
        return None
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def route_rules_from_decision(route_decision: dict[str, Any] | None) -> list[str]:
    if not isinstance(route_decision, dict):
        return []
    rules: list[str] = []
    evidence = route_decision.get("evidence")
    if not isinstance(evidence, list):
        return rules
    for item in evidence:
        if not isinstance(item, dict) or item.get("source") != "router_rule":
            continue
        rule = item.get("rule")
        if isinstance(rule, str) and rule not in rules:
            rules.append(rule)
    return rules


def prompt_case_from_refs(artifact_refs: dict[str, Any]) -> str | None:
    for key in ("prompt_case", "prompt_case_id", "case_id"):
        value = artifact_refs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def semantic_status_from_record(record: dict[str, Any] | None, artifact_refs: dict[str, Any]) -> str:
    explicit = artifact_refs.get("semantic_status")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if not isinstance(record, dict):
        return "target_run_not_found"
    failures = record.get("failures")
    if isinstance(failures, list) and failures:
        return "failed"
    status = record.get("status")
    if isinstance(status, str) and status == WorkflowStatus.COMPLETED.value:
        return "completed_no_failures"
    return status if isinstance(status, str) and status.strip() else "unknown"


def non_core_skill(selected_skills: list[str]) -> str | None:
    for skill_id in selected_skills:
        if skill_id not in CORE_CONTEXT_SKILLS:
            return skill_id
    return selected_skills[0] if selected_skills else None


def feedback_context(
    *,
    linked_record: dict[str, Any] | None,
    linked: dict[str, Any],
    artifact_refs: dict[str, Any],
    output_root: Path,
    target_root: str | None,
) -> dict[str, Any]:
    artifacts = linked_record.get("artifacts") if isinstance(linked_record, dict) and isinstance(linked_record.get("artifacts"), dict) else {}
    summary = linked_record.get("summary") if isinstance(linked_record, dict) and isinstance(linked_record.get("summary"), dict) else {}
    route_decision_path = artifacts.get("route_decision") if isinstance(artifacts, dict) else None
    route_decision = safe_json_artifact(route_decision_path, output_root)
    downstream = route_decision.get("downstream") if isinstance(route_decision, dict) and isinstance(route_decision.get("downstream"), dict) else {}
    downstream_artifacts = downstream.get("artifacts") if isinstance(downstream.get("artifacts"), dict) else {}
    selected_skills = route_decision.get("selected_skills") if isinstance(route_decision, dict) else None
    selected_tools = route_decision.get("selected_tools") if isinstance(route_decision, dict) else None
    return {
        "target_run_found": bool(linked.get("found")),
        "target_run_id": linked.get("run_id"),
        "target_workflow": linked.get("workflow"),
        "target_status": linked.get("status"),
        "target_root": target_root,
        "selected_workflow": (
            route_decision.get("selected_workflow")
            if isinstance(route_decision, dict)
            else summary.get("selected_workflow")
        ),
        "route_status": route_decision.get("status") if isinstance(route_decision, dict) else summary.get("route_status"),
        "route_rules": route_rules_from_decision(route_decision),
        "selected_skills": [item for item in selected_skills if isinstance(item, str)] if isinstance(selected_skills, list) else [],
        "selected_tools": [item for item in selected_tools if isinstance(item, str)] if isinstance(selected_tools, list) else [],
        "artifact_keys": linked.get("artifact_keys", []),
        "downstream_artifact_keys": sorted(key for key in downstream_artifacts if isinstance(key, str)),
        "downstream_run_id": downstream.get("run_id") if isinstance(downstream, dict) else summary.get("downstream_run_id"),
        "prompt_case": prompt_case_from_refs(artifact_refs),
        "prompt_case_status": "known" if prompt_case_from_refs(artifact_refs) else "unknown",
        "semantic_status": semantic_status_from_record(linked_record, artifact_refs),
        "route_decision": route_decision_path if isinstance(route_decision_path, str) else None,
    }


def feedback_next_action(classifications: list[str], context: dict[str, Any]) -> dict[str, Any]:
    selected_skills = context.get("selected_skills") if isinstance(context.get("selected_skills"), list) else []
    target_skill = non_core_skill([item for item in selected_skills if isinstance(item, str)])
    route_rules = context.get("route_rules") if isinstance(context.get("route_rules"), list) else []
    base = {
        "target_skill": target_skill,
        "target_workflow": context.get("selected_workflow") or context.get("target_workflow"),
        "route_rule": route_rules[0] if route_rules else None,
        "mutation_policy": "controller_artifacts_only",
    }
    if "unsafe" in classifications:
        return {**base, "kind": "safety_review", "reason": "Feedback reports unsafe behavior."}
    if "wrong" in classifications:
        return {**base, "kind": "semantic_gate_update", "reason": "Feedback says the answer or route was wrong."}
    if "missing" in classifications:
        return {**base, "kind": "prompt_or_artifact_gap_review", "reason": "Feedback reports missing information."}
    if "confusing" in classifications or "noisy" in classifications:
        return {**base, "kind": "chat_output_contract_review", "reason": "Feedback reports confusing or noisy output."}
    if "slow" in classifications:
        return {**base, "kind": "performance_profile_review", "reason": "Feedback reports slow response time."}
    if "useful" in classifications:
        return {**base, "kind": "keep_current_route", "reason": "Feedback confirms the route was useful."}
    return {**base, "kind": "manual_feedback_triage", "reason": "Feedback notes require maintainer review."}


def invoke_workflow_feedback_record(request: WorkflowFeedbackRecordRequest) -> InvocationResult:
    validated = validate_request(request)
    output_root = Path(request.output_root).resolve()
    run_registry_root = Path(request.run_registry_root).resolve()
    run_id = f"workflow-feedback-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    target_root = str(Path(request.target_root).resolve()) if request.target_root is not None else None
    linked_record, warnings = load_linked_run_record(run_registry_root, validated["target_run_id"])
    linked = linked_run_summary(linked_record)
    if linked.get("found") and linked.get("workflow") != validated["target_workflow"]:
        warnings.append(
            {
                "warning": "target_workflow_mismatch",
                "target_run_id": validated["target_run_id"],
                "requested_workflow": validated["target_workflow"],
                "recorded_workflow": linked.get("workflow"),
            }
        )
    classifications = feedback_classifications(validated["feedback"])
    context = feedback_context(
        linked_record=linked_record,
        linked=linked,
        artifact_refs=validated["artifact_refs"],
        output_root=output_root,
        target_root=target_root,
    )
    next_action = feedback_next_action(classifications, context)
    governed_decision = feedback_governance_decision(classifications, context, validated["feedback"])
    governed_decision["feedback_run_id"] = run_id

    artifacts: dict[str, str] = {}
    request_artifact = {
        "kind": "workflow_feedback_record_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "target_workflow": validated["target_workflow"],
        "target_run_id": validated["target_run_id"],
        "target_root": target_root,
        "tester": validated["tester"],
        "request_payload": validated["request_payload"],
        "artifact_refs": validated["artifact_refs"],
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)
    artifacts["request"] = str(run_dir / "request.json")

    summary = {
        "target_workflow": validated["target_workflow"],
        "target_run_id": validated["target_run_id"],
        "target_root": target_root,
        "feedback_counts": feedback_counts(validated["feedback"]),
        "classifications": classifications,
        "has_notes": bool(validated["feedback"].get("notes")),
        "linked_run_found": bool(linked.get("found")),
        "linked_run_status": linked.get("status"),
        "selected_workflow": context.get("selected_workflow"),
        "selected_skills": context.get("selected_skills"),
        "artifact_keys": context.get("artifact_keys"),
        "prompt_case": context.get("prompt_case"),
        "prompt_case_status": context.get("prompt_case_status"),
        "semantic_status": context.get("semantic_status"),
        "next_action": next_action,
        "governed_decision": governed_decision,
        "tester_surface": (
            validated["tester"].get("surface") if isinstance(validated["tester"], dict) else None
        ),
    }
    feedback_record = {
        "kind": "workflow_feedback_record",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "target_workflow": validated["target_workflow"],
        "target_run_id": validated["target_run_id"],
        "target_root": target_root,
        "feedback": validated["feedback"],
        "tester": validated["tester"],
        "request_payload": validated["request_payload"],
        "artifact_refs": validated["artifact_refs"],
        "linked_run": linked,
        "feedback_context": context,
        "classifications": classifications,
        "next_action": next_action,
        "governed_decision": governed_decision,
        "summary": summary,
        "warnings": warnings,
        "created_at": utc_now(),
    }
    write_json(run_dir / "feedback-record.json", feedback_record)
    artifacts["feedback_record"] = str(run_dir / "feedback-record.json")

    run_state = {
        "kind": "workflow_feedback_run_state",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "artifacts": artifacts,
        "updated_at": utc_now(),
    }
    write_json(run_dir / "run-state.json", run_state)
    artifacts["run_state"] = str(run_dir / "run-state.json")

    report = {
        "kind": "workflow_feedback_record_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "warnings": warnings,
        "artifacts": artifacts,
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed for {validated['target_workflow']} {validated['target_run_id']}",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
