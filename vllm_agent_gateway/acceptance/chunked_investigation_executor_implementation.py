"""Phase 223 chunked-investigation executor implementation gate."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.context_index_prototype import (
    dict_value,
    object_list,
    read_json_object,
    resolve_path,
    sha256_file,
    string_list,
    write_json,
)
from vllm_agent_gateway.acceptance.skill_selection_hardening import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    assert_fixture_state_unchanged,
    controller_run_record,
    fixture_state,
    json_request,
    run_id_from_text,
    text_response,
)
from vllm_agent_gateway.controllers.workflow_router.plan import WorkflowRouterPlanRequest, invoke_workflow_router_plan


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "chunked_investigation_executor_implementation_policy"
EXPECTED_REPORT_KIND = "chunked_investigation_executor_implementation_report"
EXPECTED_PHASE = 223
EXPECTED_BACKLOG_ID = "P0-M6-223"
EXPECTED_MILESTONE_IDS = {"M6", "M8"}
DEFAULT_POLICY_PATH = Path("runtime") / "chunked_investigation_executor_implementation_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase223" / "phase223-chunked-investigation-executor-implementation-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase223" / "phase223-chunked-investigation-executor-implementation-report.md"
DEFAULT_PREFLIGHT_OUTPUT_PATH = (
    Path("runtime-state") / "phase223" / "phase223-chunked-investigation-executor-implementation-preflight-report.json"
)
DEFAULT_PREFLIGHT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state") / "phase223" / "phase223-chunked-investigation-executor-implementation-preflight-report.md"
)
REQUIRED_SURFACES = {"gateway", "anythingllm"}
REQUIRED_NEGATIVE_CONTROLS = {
    "single_step_prompt_not_chunked",
    "stale_index_or_source_hash",
    "ignored_private_or_secret_like_evidence",
    "large_context_mutation_risk",
    "raw_context_capacity_claim",
    "artifact_only_chat_answer",
    "protected_fixture_mutation",
}


class Phase223Status(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    PREFLIGHT_PASSED = "preflight_passed"


@dataclass(frozen=True)
class ChunkedInvestigationExecutorImplementationConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    markdown_output_path: Path | None = None
    include_gateway: bool = True
    include_anythingllm: bool = True
    live: bool = False
    allow_partial: bool = False
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 900
    require_artifacts: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def default_output_path(*, live: bool) -> Path:
    return DEFAULT_OUTPUT_PATH if live else DEFAULT_PREFLIGHT_OUTPUT_PATH


def default_markdown_output_path(*, live: bool) -> Path:
    return DEFAULT_MARKDOWN_OUTPUT_PATH if live else DEFAULT_PREFLIGHT_MARKDOWN_OUTPUT_PATH


def int_value(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def validation_error(error_id: str, message: str, *, source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "source": source, "message": message}


def selected_surfaces(config: ChunkedInvestigationExecutorImplementationConfig) -> list[str]:
    values: list[str] = []
    if config.include_gateway:
        values.append("gateway")
    if config.include_anythingllm:
        values.append("anythingllm")
    return values


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 223"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M6 and M8"))
    if set(string_list(policy.get("required_surfaces"))) != REQUIRED_SURFACES:
        errors.append(validation_error("policy.required_surfaces", "required_surfaces must be gateway and anythingllm"))
    for key in ("target_root", "context_index_policy_path", "chunked_prompt"):
        if not isinstance(policy.get(key), str) or not str(policy[key]).strip():
            errors.append(validation_error(f"policy.{key}", f"{key} must be non-empty"))
    if policy.get("expected_strategy") != "chunked_investigation":
        errors.append(validation_error("policy.expected_strategy", "expected_strategy must be chunked_investigation"))
    if policy.get("expected_execution_path") != "large_context.chunked_investigation":
        errors.append(validation_error("policy.expected_execution_path", "expected_execution_path must be large_context.chunked_investigation"))
    if policy.get("expected_downstream_workflow") != "large_context.chunked_investigation":
        errors.append(validation_error("policy.expected_downstream_workflow", "expected_downstream_workflow must be large_context.chunked_investigation"))
    precondition = dict_value(policy.get("phase222_precondition"))
    for key in ("report_path", "required_status"):
        if not isinstance(precondition.get(key), str) or not str(precondition[key]).strip():
            errors.append(validation_error(f"policy.phase222_precondition.{key}", f"{key} must be non-empty"))
    if precondition.get("required_phase223_ready") is not True:
        errors.append(validation_error("policy.phase222_precondition.required_phase223_ready", "required_phase223_ready must be true"))
    contract = dict_value(policy.get("answer_contract"))
    expected_contract = {
        "answer_first_required": True,
        "artifact_only_allowed": False,
        "raw_prompt_stuffing_allowed": False,
        "phase222_contract_satisfied_required": True,
        "chat_visible_chunked_metadata_required": True,
    }
    for key, expected in expected_contract.items():
        if contract.get(key) is not expected:
            errors.append(validation_error(f"policy.answer_contract.{key}", f"{key} must be {expected}"))
    if contract.get("source_text_retention") != "metadata_only":
        errors.append(validation_error("policy.answer_contract.source_text_retention", "source_text_retention must be metadata_only"))
    missing_controls = sorted(REQUIRED_NEGATIVE_CONTROLS - set(string_list(policy.get("negative_controls"))))
    if missing_controls:
        errors.append(validation_error("policy.negative_controls", f"missing negative controls: {missing_controls}"))
    if policy.get("acceptance_marker") != "PHASE223 CHUNKED INVESTIGATION EXECUTOR IMPLEMENTATION PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 223"))
    return errors


def load_report(
    config_root: Path,
    raw_path: object,
    *,
    source: str,
    require_artifacts: bool,
) -> tuple[Path | None, dict[str, Any], list[dict[str, str]]]:
    path = resolve_path(config_root, raw_path) if isinstance(raw_path, str) else None
    if path is None or not path.is_file():
        if require_artifacts:
            return path, {}, [validation_error(f"{source}.missing", f"{source} report is required", source=source)]
        return path, {}, []
    try:
        return path, read_json_object(path), []
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return path, {}, [validation_error(f"{source}.malformed", f"{source} report is malformed: {exc}", source=source)]


def validate_phase222_precondition(policy: dict[str, Any], phase222_report: dict[str, Any]) -> list[dict[str, str]]:
    if not phase222_report:
        return []
    errors: list[dict[str, str]] = []
    precondition = dict_value(policy.get("phase222_precondition"))
    summary = dict_value(phase222_report.get("summary"))
    if phase222_report.get("status") != precondition.get("required_status"):
        errors.append(validation_error("phase222_report.status", "Phase 222 report status must be passed", source="phase222"))
    if summary.get("phase223_ready") is not precondition.get("required_phase223_ready"):
        errors.append(validation_error("phase222_report.phase223_ready", "Phase 222 must mark phase223_ready", source="phase222"))
    return errors


def chunked_prompt(policy: dict[str, Any], target_root: Path) -> str:
    return str(policy.get("chunked_prompt") or "").replace("{target_root}", str(target_root))


def artifact_json(record: dict[str, Any], key: str) -> dict[str, Any]:
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    path = artifacts.get(key)
    if not isinstance(path, str) or not path:
        return {}
    try:
        return read_json_object(Path(path))
    except (OSError, RuntimeError, json.JSONDecodeError):
        return {}


def score_chunked_record(
    *,
    policy: dict[str, Any],
    text: str,
    record: dict[str, Any],
    artifact: dict[str, Any],
    live: bool,
) -> dict[str, Any]:
    errors: list[str] = []
    summary = dict_value(record.get("summary"))
    minimums = dict_value(policy.get("minimums"))
    if live and not text.startswith("Answer:"):
        errors.append("chat response must start with Answer:")
    if live:
        for marker in ("run_id:", "selected_context_strategy", "chunked_stage_count"):
            if marker not in text:
                errors.append(f"chat response missing marker {marker!r}")
    expected_strategy = policy.get("expected_strategy")
    expected_path = policy.get("expected_execution_path")
    expected_downstream = policy.get("expected_downstream_workflow")
    if summary.get("selected_context_strategy") != expected_strategy:
        errors.append("selected_context_strategy mismatch")
    if summary.get("context_strategy_execution_path") != expected_path:
        errors.append("context_strategy_execution_path mismatch")
    if summary.get("downstream_workflow") != expected_downstream:
        errors.append("downstream_workflow mismatch")
    if summary.get("chunked_status") != "answered":
        errors.append("chunked_status must be answered")
    if summary.get("raw_prompt_stuffing") is not False:
        errors.append("raw_prompt_stuffing must be false")
    if summary.get("phase222_contract_satisfied") is not True:
        errors.append("phase222 contract must be satisfied")
    if int_value(summary.get("chunked_stage_count")) < int_value(minimums.get("stage_count"), 3):
        errors.append("stage count below minimum")
    if int_value(summary.get("chunked_completed_stage_count")) < int_value(minimums.get("completed_stage_count"), 3):
        errors.append("completed stage count below minimum")
    if int_value(summary.get("chunked_evidence_count")) < int_value(minimums.get("evidence_ref_count"), 3):
        errors.append("evidence ref count below minimum")
    if int_value(summary.get("chunked_claim_count")) < int_value(minimums.get("claim_count"), 3):
        errors.append("claim count below minimum")
    if int_value(summary.get("chunked_artifact_page_count")) < int_value(minimums.get("artifact_page_count"), 1):
        errors.append("artifact page count below minimum")

    if artifact.get("kind") != "chunked_investigation_report":
        errors.append("chunked investigation report artifact missing or malformed")
    if artifact.get("status") != "answered":
        errors.append("artifact status must be answered")
    if artifact.get("strategy") != expected_strategy:
        errors.append("artifact strategy mismatch")
    final_answer = dict_value(artifact.get("final_answer"))
    final_answer_text = final_answer.get("answer")
    if not isinstance(final_answer_text, str) or not final_answer_text.strip():
        errors.append("final answer must be non-empty")
    if final_answer.get("answer_first") is not True:
        errors.append("final answer must be answer-first")
    if not object_list(final_answer.get("claim_map")):
        errors.append("final answer claim map missing")
    if final_answer.get("raw_prompt_stuffing") is not False:
        errors.append("final answer raw_prompt_stuffing must be false")
    flow_narrative = string_list(final_answer.get("flow_narrative"))
    if len(flow_narrative) < 4:
        errors.append("final answer flow narrative must include stage traces and a scope note")
    evidence_table = object_list(final_answer.get("evidence_table"))
    if len(evidence_table) < int_value(dict_value(policy.get("minimums")).get("evidence_ref_count"), 3):
        errors.append("final answer evidence table must include selected evidence rows")
    not_proven = string_list(final_answer.get("not_proven_by_selected_evidence"))
    if len(not_proven) < 3:
        errors.append("final answer must list what selected evidence does not prove")
    if isinstance(final_answer_text, str):
        for marker in (
            "Scope and limits:",
            "Evidence table:",
            "Flow narrative:",
            "Not proven by selected evidence:",
            "source_hash:",
            "chunk_hash:",
            "freshness:",
            "Entry point:",
            "Decision/output path:",
            "Verification surface:",
            "bounded cross-file trace",
        ):
            if marker not in final_answer_text:
                errors.append(f"chat answer missing marker {marker!r}")
    limits = dict_value(artifact.get("limits"))
    if limits.get("within_target_input_limit") is not True:
        errors.append("selected evidence must fit target input limit")
    if limits.get("source_text_retention") != "metadata_only":
        errors.append("source_text_retention must be metadata_only")
    evidence = object_list(artifact.get("evidence"))
    source_paths = [str(ref.get("source_path") or "") for ref in evidence if isinstance(ref.get("source_path"), str)]
    if len(set(source_paths)) < min(len(source_paths), int_value(dict_value(policy.get("minimums")).get("evidence_ref_count"), 3)):
        errors.append("evidence refs must prefer distinct source paths when available")
    verification_refs = [
        ref
        for ref in evidence
        if ref.get("retrieval_stage_id") == "verification_surfaces"
    ]
    if verification_refs and verification_refs[0].get("source_type") not in {"test", "doc", "case", "config"}:
        errors.append("verification stage must prefer test/doc/case/config evidence when available")
    for ref in evidence:
        for key in (
            "evidence_ref_id",
            "retrieval_stage_id",
            "claim_ids",
            "source_path",
            "line_start",
            "line_end",
            "source_sha256",
            "chunk_sha256",
            "freshness_status",
            "source_type",
            "retrieval_rank",
            "retrieval_score",
            "query_terms",
        ):
            if key not in ref:
                errors.append(f"evidence ref missing {key}")
                break
    serialized = json.dumps(artifact, sort_keys=True)
    for forbidden in ('"source_text"', '"snippet"', "PHASE216_DUMMY_SECRET_DO_NOT_EXPOSE"):
        if forbidden in serialized:
            errors.append(f"artifact leaked forbidden marker {forbidden}")
    return {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "selected_context_strategy": summary.get("selected_context_strategy"),
        "downstream_workflow": summary.get("downstream_workflow"),
        "chunked_status": summary.get("chunked_status"),
        "chunked_stage_count": summary.get("chunked_stage_count"),
        "chunked_completed_stage_count": summary.get("chunked_completed_stage_count"),
        "chunked_evidence_count": summary.get("chunked_evidence_count"),
        "chunked_claim_count": summary.get("chunked_claim_count"),
        "chunked_artifact_page_count": summary.get("chunked_artifact_page_count"),
        "raw_prompt_stuffing": summary.get("raw_prompt_stuffing"),
        "phase222_contract_satisfied": summary.get("phase222_contract_satisfied"),
    }


def offline_record(
    config: ChunkedInvestigationExecutorImplementationConfig,
    *,
    policy: dict[str, Any],
    target_root: Path,
    output_root: Path,
) -> tuple[str, dict[str, Any], str]:
    result = invoke_workflow_router_plan(
        WorkflowRouterPlanRequest(
            config_root=config.config_root,
            target_root=target_root,
            output_root=output_root,
            user_request=chunked_prompt(policy, target_root),
            mode="execute_read_only",
            budgets={"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
            context={"context_index_policy_path": str(resolve_path(config.config_root, policy.get("context_index_policy_path")))},
        )
    )
    text = f"Answer:\n{dict_value(result.report).get('summary', {}).get('answer', '')}"
    return text, dict_value(result.report), str(result.run_id or "unknown")


def gateway_live_response(
    config: ChunkedInvestigationExecutorImplementationConfig,
    *,
    prompt: str,
) -> tuple[str, dict[str, Any], str]:
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": prompt}],
            "role_base_url": config.model_base_url,
            "budgets": {"max_model_calls": 3, "max_selected_skills": 5, "max_selected_tools": 5},
        },
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    compact = body.get("agentic_controller_response") if isinstance(body.get("agentic_controller_response"), dict) else {}
    run_id = str(compact.get("run_id") or run_id_from_text(text))
    if run_id == "unknown":
        raise RuntimeError("gateway response did not include a workflow-router run_id")
    return text, controller_run_record(config, run_id), run_id


def anythingllm_live_response(
    config: ChunkedInvestigationExecutorImplementationConfig,
    *,
    prompt: str,
    api_key: str,
) -> tuple[str, dict[str, Any], str]:
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": prompt,
            "mode": "chat",
            "sessionId": f"phase223-chunked-investigation-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    run_id = run_id_from_text(text)
    if run_id == "unknown":
        raise RuntimeError("AnythingLLM response did not include a workflow-router run_id")
    return text, controller_run_record(config, run_id), run_id


def run_surface_case(
    config: ChunkedInvestigationExecutorImplementationConfig,
    *,
    policy: dict[str, Any],
    surface: str,
    target_root: Path,
    output_root: Path,
    api_key: str | None,
) -> dict[str, Any]:
    prompt = chunked_prompt(policy, target_root)
    try:
        if surface == "offline":
            text, record, run_id = offline_record(config, policy=policy, target_root=target_root, output_root=output_root)
        elif surface == "gateway":
            text, record, run_id = gateway_live_response(config, prompt=prompt)
        elif surface == "anythingllm":
            if not api_key:
                raise RuntimeError(f"{config.api_key_env} is required for AnythingLLM live validation")
            text, record, run_id = anythingllm_live_response(config, prompt=prompt, api_key=api_key)
        else:
            raise RuntimeError(f"unsupported surface {surface}")
        artifact = artifact_json(record, "downstream_chunked_investigation_report")
        scored = score_chunked_record(policy=policy, text=text, record=record, artifact=artifact, live=surface != "offline")
    except Exception as exc:  # noqa: BLE001 - validation report should classify all failures
        text = ""
        record = {}
        run_id = "unknown"
        scored = {"status": "failed", "errors": [str(exc)]}
    return {
        "surface": surface,
        "run_id": run_id,
        **scored,
        "chat_excerpt": text[:1200],
    }


def small_repo_prompt(root: str) -> str:
    return f"In {root}, explain what README.md is for. Read only. Include key sections and source refs."


def run_small_repo_non_regression(
    config: ChunkedInvestigationExecutorImplementationConfig,
    *,
    surface: str,
    root: str,
    api_key: str | None,
) -> dict[str, Any]:
    before = fixture_state(root)
    prompt = small_repo_prompt(root)
    try:
        if surface == "gateway":
            text, record, run_id = gateway_live_response(config, prompt=prompt)
        elif surface == "anythingllm":
            if not api_key:
                raise RuntimeError(f"{config.api_key_env} is required for AnythingLLM live validation")
            text, record, run_id = anythingllm_live_response(config, prompt=prompt, api_key=api_key)
        else:
            raise RuntimeError(f"unsupported surface {surface}")
        assert_fixture_state_unchanged(before, root, f"phase223 {surface} {root}")
        summary = dict_value(record.get("summary"))
        errors: list[str] = []
        if summary.get("selected_context_strategy") == "chunked_investigation":
            errors.append("small repo selected chunked_investigation")
        if summary.get("downstream_workflow") == "large_context.chunked_investigation":
            errors.append("small repo invoked chunked executor")
        status = "passed" if not errors else "failed"
    except Exception as exc:  # noqa: BLE001
        text = ""
        record = {}
        run_id = "unknown"
        errors = [str(exc)]
        status = "failed"
    return {
        "surface": surface,
        "target_root": root,
        "status": status,
        "errors": errors,
        "run_id": run_id,
        "selected_context_strategy": dict_value(record.get("summary")).get("selected_context_strategy"),
        "downstream_workflow": dict_value(record.get("summary")).get("downstream_workflow"),
        "chat_excerpt": text[:600],
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Phase 223 Chunked Investigation Executor Implementation",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Live: `{report.get('live')}`",
        f"- Response count: `{summary.get('response_count')}`",
        f"- Failed response count: `{summary.get('failed_response_count')}`",
        f"- Small-repo regression count: `{summary.get('small_repo_regression_count')}`",
        f"- Phase 224 ready: `{summary.get('phase224_ready')}`",
        "",
        "## Responses",
    ]
    for item in object_list(report.get("responses")):
        lines.append(
            f"- `{item.get('surface')}` run `{item.get('run_id')}` status `{item.get('status')}` "
            f"strategy `{item.get('selected_context_strategy')}` evidence `{item.get('chunked_evidence_count')}`"
        )
        if item.get("errors"):
            lines.append(f"  - Errors: `{item.get('errors')}`")
    if object_list(report.get("small_repo_regression_results")):
        lines.extend(["", "## Small-Repo Non-Regression"])
        for item in object_list(report.get("small_repo_regression_results")):
            lines.append(
                f"- `{item.get('surface')}` `{item.get('target_root')}` status `{item.get('status')}` "
                f"strategy `{item.get('selected_context_strategy')}` downstream `{item.get('downstream_workflow')}`"
            )
            if item.get("errors"):
                lines.append(f"  - Errors: `{item.get('errors')}`")
    if object_list(report.get("validation_errors")):
        lines.extend(["", "## Validation Errors"])
        for item in object_list(report.get("validation_errors")):
            lines.append(f"- `{item.get('id')}`: {item.get('message')}")
    return "\n".join(lines) + "\n"


def validate_chunked_investigation_executor_implementation(
    config: ChunkedInvestigationExecutorImplementationConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path or default_output_path(live=config.live))
    markdown_output_path = resolve_path(config_root, config.markdown_output_path or default_markdown_output_path(live=config.live))
    policy = read_json_object(policy_path)
    validation_errors = validate_policy(policy)
    phase222_path, phase222_report, phase222_errors = load_report(
        config_root,
        dict_value(policy.get("phase222_precondition")).get("report_path"),
        source="phase222",
        require_artifacts=config.require_artifacts,
    )
    validation_errors.extend(phase222_errors)
    validation_errors.extend(validate_phase222_precondition(policy, phase222_report))
    target_root = resolve_path(config_root, policy.get("target_root")).resolve()
    context_index_policy_path = resolve_path(config_root, policy.get("context_index_policy_path")).resolve()
    for label, path in (("target_root", target_root), ("context_index_policy_path", context_index_policy_path)):
        if not path.exists():
            validation_errors.append(validation_error(f"{label}.missing", f"{label} does not exist: {path}", source="artifact"))

    surfaces = selected_surfaces(config)
    if not config.allow_partial and config.live and set(surfaces) != set(string_list(policy.get("required_surfaces"))):
        validation_errors.append(validation_error("live.surfaces", "live validation must include gateway and AnythingLLM"))

    responses: list[dict[str, Any]] = []
    small_repo_results: list[dict[str, Any]] = []
    if not validation_errors:
        if config.live:
            api_key = os.environ.get(config.api_key_env)
            for surface in surfaces:
                responses.append(
                    run_surface_case(
                        config,
                        policy=policy,
                        surface=surface,
                        target_root=target_root,
                        output_root=output_path.parent / "offline-artifacts",
                        api_key=api_key,
                    )
                )
            for surface in surfaces:
                for root in string_list(policy.get("small_repo_regression_roots")):
                    small_repo_results.append(run_small_repo_non_regression(config, surface=surface, root=root, api_key=api_key))
        else:
            responses.append(
                run_surface_case(
                    config,
                    policy=policy,
                    surface="offline",
                    target_root=target_root,
                    output_root=output_path.parent / "offline-artifacts",
                    api_key=None,
                )
            )

    failed_responses = [item for item in responses if item.get("status") != "passed"]
    failed_small_repo = [item for item in small_repo_results if item.get("status") != "passed"]
    status = Phase223Status.FAILED.value
    if not validation_errors and not failed_responses and not failed_small_repo:
        status = Phase223Status.PASSED.value if config.live else Phase223Status.PREFLIGHT_PASSED.value
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": status,
        "live": config.live,
        "policy_path": str(policy_path),
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "phase222_report_path": str(phase222_path) if phase222_path is not None else None,
        "phase222_report_sha256": sha256_file(phase222_path) if phase222_path is not None and phase222_path.is_file() else None,
        "target_root": str(target_root),
        "responses": responses,
        "small_repo_regression_results": small_repo_results,
        "validation_errors": validation_errors,
        "summary": {
            "response_count": len(responses),
            "failed_response_count": len(failed_responses),
            "small_repo_regression_count": len(small_repo_results),
            "failed_small_repo_regression_count": len(failed_small_repo),
            "gateway_enabled": config.include_gateway,
            "anythingllm_enabled": config.include_anythingllm,
            "raw_prompt_stuffing_allowed": dict_value(policy.get("answer_contract")).get("raw_prompt_stuffing_allowed"),
            "phase222_contract_satisfied_required": dict_value(policy.get("answer_contract")).get(
                "phase222_contract_satisfied_required"
            ),
            "phase224_ready": status == Phase223Status.PASSED.value,
        },
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown_report(report))
    report["markdown_report_path"] = str(markdown_output_path.resolve())
    return report
