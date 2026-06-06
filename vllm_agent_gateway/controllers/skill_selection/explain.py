"""Read-only skill selection explanation workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controllers.workflow_router.plan import workflow_kind_for_request
from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus
from vllm_agent_gateway.skills.registry import (
    SCHEMA_VERSION,
    SKILL_REGISTRY_PATH,
    explain_skill_selection_for_workflow,
    read_json_object,
)


WORKFLOW_ID = "skill.selection.explain"
DEFAULT_OUTPUT_DIR = "skill-selection-explanations"


class SkillSelectionExplainError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "skill_selection_explain_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class SkillSelectionExplainRequest:
    config_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    user_request: str | None = None
    workflow_id: str | None = None
    target_root: str | None = None
    max_candidate_count: int = 5
    role_id: str = "architect/default"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        output_root: Path,
    ) -> "SkillSelectionExplainRequest":
        values: dict[str, Any] = {
            "config_root": config_root,
            "output_root": output_root,
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


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def bounded_string(value: Any, label: str, *, limit: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillSelectionExplainError(f"{label} must be a non-empty string.")
    text = value.strip()
    return text[:limit]


def validate_request(request: SkillSelectionExplainRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise SkillSelectionExplainError("workflow must be skill.selection.explain.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise SkillSelectionExplainError("schema_version must be 1.", code="unsupported_schema_version")
    bounded_string(request.user_request, "user_request")
    if request.workflow_id is not None and (not isinstance(request.workflow_id, str) or not request.workflow_id.strip()):
        raise SkillSelectionExplainError("workflow_id must be a non-empty string when provided.")
    if (
        not isinstance(request.max_candidate_count, int)
        or isinstance(request.max_candidate_count, bool)
        or not 1 <= request.max_candidate_count <= 20
    ):
        raise SkillSelectionExplainError("max_candidate_count must be an integer from 1 through 20.")
    if request.metadata is not None and not isinstance(request.metadata, dict):
        raise SkillSelectionExplainError("metadata must be a JSON object.", code="invalid_metadata")


def metadata_skill_registry(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json_object(config_root / SKILL_REGISTRY_PATH, "skill registry")
    skills = manifest.get("skills")
    if not isinstance(skills, list):
        raise SkillSelectionExplainError("runtime/skills.json must contain a skills list.", code="invalid_skill_registry")
    registry: dict[str, dict[str, Any]] = {}
    for item in skills:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            registry[item["id"]] = item
    return registry


def route_namespace_summary(skill_registry: dict[str, dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for skill in skill_registry.values():
        contract = skill.get("capability_contract")
        route_key = contract.get("route_key") if isinstance(contract, dict) else None
        if isinstance(route_key, str) and "." in route_key:
            namespace = route_key.split(".", 1)[0]
            summary[namespace] = summary.get(namespace, 0) + 1
    return dict(sorted(summary.items()))


def infer_workflow_id(user_request: str) -> tuple[str | None, str, list[dict[str, Any]]]:
    workflow_id, status_reason, evidence = workflow_kind_for_request(user_request)
    return workflow_id, status_reason, evidence


def invoke_skill_selection_explain(request: SkillSelectionExplainRequest) -> InvocationResult:
    validate_request(request)
    config_root = Path(request.config_root).resolve()
    output_root = Path(request.output_root).resolve()
    run_id = f"skill-selection-explain-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    assert request.user_request is not None
    user_request = bounded_string(request.user_request, "user_request")
    requested_workflow_id = request.workflow_id.strip() if isinstance(request.workflow_id, str) else None
    inferred_workflow_id, inference_reason, inference_evidence = infer_workflow_id(user_request)
    workflow_id = requested_workflow_id or inferred_workflow_id
    skill_registry = metadata_skill_registry(config_root)

    request_artifact = {
        "kind": "skill_selection_explain_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "user_request": user_request,
        "requested_workflow_id": requested_workflow_id,
        "inferred_workflow_id": inferred_workflow_id,
        "target_root": request.target_root,
        "max_candidate_count": request.max_candidate_count,
        "metadata": request.metadata,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)

    if workflow_id is None:
        selection = {
            "workflow_id": None,
            "query_text": user_request,
            "limit": request.max_candidate_count,
            "selected_skill_ids": [],
            "selected": [],
            "candidate_count": 0,
            "filtered_count": len(skill_registry),
            "filtered": [],
            "deprecated_exclusions": [],
            "route_namespace_summary": route_namespace_summary(skill_registry),
            "body_reads_during_selection": 0,
            "blockers": [
                {
                    "reason": inference_reason,
                    "message": "No supported workflow was inferred for this request.",
                }
            ],
        }
    else:
        selection = explain_skill_selection_for_workflow(
            skill_registry,
            workflow_id,
            query_text=user_request,
            limit=request.max_candidate_count,
            max_filtered=50,
        )
        selection["blockers"] = []
        if not selection["selected_skill_ids"]:
            selection["blockers"].append(
                {
                    "reason": "no_matching_skill",
                    "message": "No skill matched the selected workflow and trigger requirements.",
                }
            )

    selected_route_keys = {
        item["skill_id"]: item.get("route_key")
        for item in selection.get("selected", [])
        if isinstance(item, dict) and isinstance(item.get("skill_id"), str)
    }
    explanation = {
        "kind": "skill_selection_explanation",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": "explained",
        "user_request": user_request,
        "requested_workflow_id": requested_workflow_id,
        "inferred_workflow_id": inferred_workflow_id,
        "workflow_id": workflow_id,
        "inference_reason": inference_reason,
        "inference_evidence": inference_evidence,
        "selection": selection,
        "selected_route_keys": selected_route_keys,
        "target_repository_changed": False,
        "created_at": utc_now(),
    }
    write_json(run_dir / "skill-selection-explanation.json", explanation)

    summary = {
        "explanation_status": "explained",
        "workflow_id": workflow_id,
        "inference_reason": inference_reason,
        "selected_skill_ids": selection["selected_skill_ids"],
        "selected_route_keys": selected_route_keys,
        "selected_count": len(selection["selected_skill_ids"]),
        "candidate_count": selection["candidate_count"],
        "filtered_count": selection["filtered_count"],
        "deprecated_exclusion_count": len(selection["deprecated_exclusions"]),
        "route_namespace_summary": selection["route_namespace_summary"],
        "body_reads_during_selection": selection["body_reads_during_selection"],
        "target_repository_changed": False,
        "next_action": "review_selection_or_run_target_workflow",
    }
    artifacts = {
        "request": str(run_dir / "request.json"),
        "skill_selection_explanation": str(run_dir / "skill-selection-explanation.json"),
    }
    run_state = {
        "kind": "skill_selection_explain_run_state",
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
        "kind": "skill_selection_explanation_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": WorkflowStatus.COMPLETED.value,
        "summary": summary,
        "explanation": explanation,
        "warnings": [],
        "artifacts": artifacts,
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=WorkflowStatus.COMPLETED,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed with selected_count={summary['selected_count']}",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
