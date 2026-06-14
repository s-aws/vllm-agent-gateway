"""Phase 222 chunked-investigation executor contract gate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
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


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "chunked_investigation_executor_contract_policy"
EXPECTED_REPORT_KIND = "chunked_investigation_executor_contract_report"
EXPECTED_PHASE = 222
EXPECTED_BACKLOG_ID = "P0-M6-222"
EXPECTED_MILESTONE_IDS = {"M6", "M8"}
DEFAULT_POLICY_PATH = Path("runtime") / "chunked_investigation_executor_contract_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase222" / "phase222-chunked-investigation-executor-contract-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase222" / "phase222-chunked-investigation-executor-contract-report.md"

REQUIRED_STAGE_IDS = {
    "request_intake",
    "flow_decomposition",
    "bounded_retrieval",
    "stage_synthesis",
    "source_verification",
    "artifact_paging",
    "final_answer",
}
REQUIRED_ARTIFACT_IDS = {
    "chunked_investigation_report",
    "chunked_investigation_plan",
    "chunk_stage_records",
    "chunk_evidence_refs",
    "chunk_page_manifest",
    "chunk_final_answer",
}
REQUIRED_SOURCE_PROOF_FIELDS = {
    "evidence_ref_id",
    "source_path",
    "line_start",
    "line_end",
    "source_sha256",
    "chunk_sha256",
    "freshness_status",
    "retrieval_stage_id",
    "query_terms",
    "source_type",
    "retrieval_rank",
    "retrieval_score",
    "claim_ids",
}
REQUIRED_NEGATIVE_CONTROLS = {
    "single_step_prompt_not_chunked",
    "stale_index_or_source_hash",
    "ignored_private_or_secret_like_evidence",
    "large_context_mutation_risk",
    "ambiguous_multi_step_prompt",
    "contradictory_evidence_uncertainty",
    "raw_context_capacity_claim",
    "artifact_only_chat_answer",
    "new_index_or_vector_search_path",
    "protected_fixture_mutation",
}
REQUIRED_LIVE_SURFACES = {"workflow_router_gateway", "anythingllm"}


@dataclass(frozen=True)
class ChunkedInvestigationExecutorContractConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    require_artifacts: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def validation_error(error_id: str, message: str, *, source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "source": source, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 222"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M6 and M8"))

    precondition = dict_value(policy.get("phase221_precondition"))
    for key in ("report_path", "required_status"):
        if not isinstance(precondition.get(key), str) or not str(precondition[key]).strip():
            errors.append(validation_error(f"policy.phase221_precondition.{key}", f"{key} must be non-empty"))
    for key in ("required_m6_ready", "required_m8_ready"):
        if precondition.get(key) is not True:
            errors.append(validation_error(f"policy.phase221_precondition.{key}", f"{key} must be true"))

    executor = dict_value(policy.get("executor_contract"))
    if executor.get("executor_id") != "large_context.chunked_investigation":
        errors.append(validation_error("policy.executor_contract.executor_id", "executor_id must be large_context.chunked_investigation"))
    if executor.get("strategy_id") != "chunked_investigation":
        errors.append(validation_error("policy.executor_contract.strategy_id", "strategy_id must be chunked_investigation"))
    if executor.get("entry_path") != "workflow_router.execute_read_only.large_context_chunked_investigation":
        errors.append(
            validation_error(
                "policy.executor_contract.entry_path",
                "entry_path must stay inside workflow_router.execute_read_only.large_context_chunked_investigation",
            )
        )
    if executor.get("new_chat_endpoint_allowed") is not False:
        errors.append(validation_error("policy.executor_contract.new_chat_endpoint_allowed", "new chat endpoint must not be allowed"))
    if executor.get("raw_prompt_stuffing_allowed") is not False:
        errors.append(validation_error("policy.executor_contract.raw_prompt_stuffing_allowed", "raw prompt stuffing must not be allowed"))
    if executor.get("source_text_retention") != "metadata_only":
        errors.append(validation_error("policy.executor_contract.source_text_retention", "source_text_retention must be metadata_only"))

    stage_ids = {str(item.get("stage_id")) for item in object_list(policy.get("stage_contracts"))}
    missing_stages = sorted(REQUIRED_STAGE_IDS - stage_ids)
    if missing_stages:
        errors.append(validation_error("policy.stage_contracts", f"missing stage contracts: {missing_stages}"))
    for stage in object_list(policy.get("stage_contracts")):
        stage_id = str(stage.get("stage_id") or "")
        prefix = f"policy.stage_contracts.{stage_id or 'missing'}"
        if stage_id not in REQUIRED_STAGE_IDS:
            errors.append(validation_error(f"{prefix}.stage_id", "stage_id is not a required contract stage"))
        for key in ("purpose", "input_contract", "output_contract", "stop_condition"):
            if not string_list(stage.get(key)):
                errors.append(validation_error(f"{prefix}.{key}", f"{key} must be a non-empty list"))
        if stage.get("max_selected_tokens") not in (None, "within_phase214_target_input_limit"):
            errors.append(validation_error(f"{prefix}.max_selected_tokens", "stage token budget must fit Phase 214 target input limit"))

    artifact_ids = {str(item.get("artifact_id")) for item in object_list(policy.get("artifact_contracts"))}
    missing_artifacts = sorted(REQUIRED_ARTIFACT_IDS - artifact_ids)
    if missing_artifacts:
        errors.append(validation_error("policy.artifact_contracts", f"missing artifact contracts: {missing_artifacts}"))
    for artifact in object_list(policy.get("artifact_contracts")):
        artifact_id = str(artifact.get("artifact_id") or "")
        prefix = f"policy.artifact_contracts.{artifact_id or 'missing'}"
        if not string_list(artifact.get("required_fields")):
            errors.append(validation_error(f"{prefix}.required_fields", "required_fields must not be empty"))
        if artifact.get("stores_source_text") is not False:
            errors.append(validation_error(f"{prefix}.stores_source_text", "artifacts must not store source text"))
        if artifact.get("traceable_to_source_refs") is not True:
            errors.append(validation_error(f"{prefix}.traceable_to_source_refs", "artifacts must trace to source refs"))

    source_fields = set(string_list(policy.get("source_proof_fields")))
    missing_source_fields = sorted(REQUIRED_SOURCE_PROOF_FIELDS - source_fields)
    if missing_source_fields:
        errors.append(validation_error("policy.source_proof_fields", f"missing source proof fields: {missing_source_fields}"))

    answer_contract = dict_value(policy.get("answer_contract"))
    expected_answer_contract = {
        "answer_first_required": True,
        "artifact_only_allowed": False,
        "stage_summary_required": True,
        "unresolved_steps_required": True,
        "source_refs_required": True,
        "claim_map_required": True,
        "raw_prompt_stuffing_allowed": False,
        "format_a_and_json_parity_required": True,
    }
    for key, expected in expected_answer_contract.items():
        if answer_contract.get(key) is not expected:
            errors.append(validation_error(f"policy.answer_contract.{key}", f"{key} must be {expected}"))

    live_surfaces = set(string_list(policy.get("live_validation_surfaces")))
    if live_surfaces != REQUIRED_LIVE_SURFACES:
        errors.append(validation_error("policy.live_validation_surfaces", "live validation must cover gateway and AnythingLLM"))

    negative_controls = set(string_list(policy.get("negative_controls")))
    missing_negative_controls = sorted(REQUIRED_NEGATIVE_CONTROLS - negative_controls)
    if missing_negative_controls:
        errors.append(validation_error("policy.negative_controls", f"missing negative controls: {missing_negative_controls}"))

    implementation_boundaries = set(string_list(policy.get("implementation_boundaries")))
    for required in (
        "reuse_metadata_first_index",
        "reuse_retrieval_evidence_validation",
        "reuse_artifact_paging_contract",
        "no_second_large_context_router",
        "no_vector_search_replacement",
        "no_raw_1m_prompt_claim",
    ):
        if required not in implementation_boundaries:
            errors.append(validation_error("policy.implementation_boundaries", f"missing boundary {required}"))

    if policy.get("acceptance_marker") != "PHASE222 CHUNKED INVESTIGATION EXECUTOR CONTRACT PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 222"))
    return errors


def load_phase221_report(
    config_root: Path,
    policy: dict[str, Any],
    *,
    require_artifacts: bool,
) -> tuple[Path | None, dict[str, Any], list[dict[str, str]]]:
    raw_path = dict_value(policy.get("phase221_precondition")).get("report_path")
    path = resolve_path(config_root, raw_path) if isinstance(raw_path, str) else None
    if path is None or not path.is_file():
        if require_artifacts:
            return path, {}, [validation_error("phase221_report.missing", "Phase 221 report is required", source="phase221")]
        return path, {}, []
    try:
        return path, read_json_object(path), []
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return path, {}, [validation_error("phase221_report.malformed", f"Phase 221 report is malformed: {exc}", source="phase221")]


def validate_phase221_precondition(policy: dict[str, Any], report: dict[str, Any]) -> list[dict[str, str]]:
    if not report:
        return []
    errors: list[dict[str, str]] = []
    precondition = dict_value(policy.get("phase221_precondition"))
    summary = dict_value(report.get("summary"))
    if report.get("status") != precondition.get("required_status"):
        errors.append(validation_error("phase221_report.status", "Phase 221 report status must be passed", source="phase221"))
    if summary.get("m6_ready") is not precondition.get("required_m6_ready"):
        errors.append(validation_error("phase221_report.m6_ready", "Phase 221 must mark m6_ready", source="phase221"))
    if summary.get("m8_ready") is not precondition.get("required_m8_ready"):
        errors.append(validation_error("phase221_report.m8_ready", "Phase 221 must mark m8_ready", source="phase221"))
    if summary.get("raw_prompt_stuffing_allowed") is not False:
        errors.append(validation_error("phase221_report.raw_prompt_stuffing_allowed", "Phase 221 must keep raw stuffing disallowed", source="phase221"))
    if int(summary.get("failed_response_count", 1)) != 0:
        errors.append(validation_error("phase221_report.failed_response_count", "Phase 221 must have zero failed live responses", source="phase221"))
    return errors


def build_report(config: ChunkedInvestigationExecutorContractConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    policy = read_json_object(policy_path)
    validation_errors = validate_policy(policy)
    phase221_path, phase221_report, phase221_errors = load_phase221_report(
        config_root,
        policy,
        require_artifacts=config.require_artifacts,
    )
    validation_errors.extend(phase221_errors)
    validation_errors.extend(validate_phase221_precondition(policy, phase221_report))
    status = "passed" if not validation_errors else "failed"
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": status,
        "policy_path": str(policy_path),
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "phase221_report_path": str(phase221_path) if phase221_path is not None else None,
        "phase221_report_sha256": sha256_file(phase221_path) if phase221_path is not None and phase221_path.is_file() else None,
        "executor_contract": dict_value(policy.get("executor_contract")),
        "stage_contracts": object_list(policy.get("stage_contracts")),
        "artifact_contracts": object_list(policy.get("artifact_contracts")),
        "source_proof_fields": string_list(policy.get("source_proof_fields")),
        "negative_controls": string_list(policy.get("negative_controls")),
        "implementation_boundaries": string_list(policy.get("implementation_boundaries")),
        "validation_errors": validation_errors,
        "summary": {
            "stage_count": len(object_list(policy.get("stage_contracts"))),
            "artifact_contract_count": len(object_list(policy.get("artifact_contracts"))),
            "source_proof_field_count": len(string_list(policy.get("source_proof_fields"))),
            "negative_control_count": len(string_list(policy.get("negative_controls"))),
            "live_surface_count": len(string_list(policy.get("live_validation_surfaces"))),
            "phase223_ready": status == "passed",
            "validation_error_count": len(validation_errors),
        },
    }
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Chunked Investigation Executor Contract",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Stage count: `{summary.get('stage_count')}`",
        f"- Artifact contracts: `{summary.get('artifact_contract_count')}`",
        f"- Negative controls: `{summary.get('negative_control_count')}`",
        f"- Phase 223 ready: `{summary.get('phase223_ready')}`",
        "",
        "## Stages",
    ]
    for stage in object_list(report.get("stage_contracts")):
        lines.append(f"- `{stage.get('stage_id')}`: {', '.join(string_list(stage.get('purpose')))}")
    lines.extend(["", "## Artifacts"])
    for artifact in object_list(report.get("artifact_contracts")):
        lines.append(f"- `{artifact.get('artifact_id')}` fields `{len(string_list(artifact.get('required_fields')))}`")
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors"])
        for error in errors:
            lines.append(f"- `{error.get('id')}`: {error.get('message')}")
    return "\n".join(lines).rstrip() + "\n"


def run_chunked_investigation_executor_contract(config: ChunkedInvestigationExecutorContractConfig) -> dict[str, Any]:
    report = build_report(config)
    output_path = resolve_path(config.config_root.resolve(), config.output_path)
    markdown_output_path = resolve_path(config.config_root.resolve(), config.markdown_output_path)
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown_report(report))
    return report
