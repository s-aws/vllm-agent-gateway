"""Phase 273 live acceptance gate for the 500k candidate target."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.large_context_384k_live_acceptance import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    LargeContext384kLiveAcceptanceConfig,
    LargeContext384kLiveAcceptanceStatus,
    validate_large_context_384k_live_acceptance,
)
from vllm_agent_gateway.acceptance.large_context_500k_candidate_rebaseline import (
    dict_value,
    read_json_object,
    sha256_file,
    string_list,
    validation_error,
    write_json,
    write_text,
)
from vllm_agent_gateway.acceptance.large_context_500k_stale_index_rejection import (
    LargeContext500kStaleIndexRejectionConfig,
    LargeContext500kStaleIndexRejectionStatus,
    validate_large_context_500k_stale_index_rejection,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "large_context_500k_live_acceptance_policy"
EXPECTED_REPORT_KIND = "large_context_500k_live_acceptance_report"
EXPECTED_PHASE = 273
EXPECTED_BACKLOG_ID = "P0-M15-273"
EXPECTED_MILESTONE_IDS = {"M2", "M4", "M6", "M8", "M13", "M14", "M15", "M16"}
CANDIDATE_ESTIMATED_PROJECT_TOKENS = 500_000
REQUIRED_STRATEGIES = {"retrieval", "artifact_paging", "summarization", "refusal", "chunked_investigation"}
DEFAULT_POLICY_PATH = Path("runtime") / "large_context_500k_live_acceptance_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase273"
    / "phase273-large-context-500k-live-acceptance-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase273"
    / "phase273-large-context-500k-live-acceptance-report.md"
)


class LargeContext500kLiveAcceptanceStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class LargeContext500kLiveAcceptanceConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    include_gateway: bool = True
    include_anythingllm: bool = True
    live: bool = False
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    anythingllm_workflow_router_base_url: str | None = None
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 1200
    require_artifacts: bool = False
    validate_phase272_precondition: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 273"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M2, M4, M6, M8, M13, M14, M15, and M16"))
    if policy.get("candidate_estimated_project_tokens") != CANDIDATE_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("policy.candidate_estimated_project_tokens", "candidate target must be 500000"))
    phase272 = dict_value(policy.get("phase272_precondition"))
    if not phase272:
        errors.append(validation_error("policy.phase272_precondition", "phase272_precondition is required"))
    if phase272.get("required_status") != LargeContext500kStaleIndexRejectionStatus.PASSED.value:
        errors.append(validation_error("policy.phase272_precondition.required_status", "Phase 272 must be required to pass"))
    if phase272.get("required_phase273_ready") is not True:
        errors.append(validation_error("policy.phase272_precondition.required_phase273_ready", "Phase 272 must be phase273_ready"))
    delegate = dict_value(policy.get("phase261_live_delegate"))
    if not delegate:
        errors.append(validation_error("policy.phase261_live_delegate", "phase261_live_delegate is required"))
    if delegate.get("required_status") != LargeContext384kLiveAcceptanceStatus.PASSED.value:
        errors.append(validation_error("policy.phase261_live_delegate.required_status", "Phase 261 must be required to pass"))
    if delegate.get("required_phase262_ready") is not True:
        errors.append(validation_error("policy.phase261_live_delegate.required_phase262_ready", "Phase 261 must be phase262_ready"))
    if int(delegate.get("minimum_response_count", 0)) < 18:
        errors.append(validation_error("policy.phase261_live_delegate.minimum_response_count", "minimum response count must be at least 18"))
    if int(delegate.get("minimum_gateway_response_count", 0)) < 9:
        errors.append(validation_error("policy.phase261_live_delegate.minimum_gateway_response_count", "minimum gateway response count must be at least 9"))
    if int(delegate.get("minimum_anythingllm_response_count", 0)) < 9:
        errors.append(validation_error("policy.phase261_live_delegate.minimum_anythingllm_response_count", "minimum AnythingLLM response count must be at least 9"))
    if set(string_list(policy.get("required_strategy_ids"))) != REQUIRED_STRATEGIES:
        errors.append(validation_error("policy.required_strategy_ids", "all required strategy ids must be present"))
    safety = dict_value(policy.get("safety_requirements"))
    for key in (
        "raw_prompt_stuffing_allowed",
        "raw_500k_prompt_support_claim_allowed",
        "store_source_text",
        "store_rejected_content",
        "artifact_only_answers_allowed",
        "protected_fixture_mutation_allowed",
        "generated_corpus_mutation_allowed",
    ):
        if safety.get(key) is not False:
            errors.append(validation_error(f"policy.safety_requirements.{key}", f"{key} must be false"))
    if safety.get("source_text_retention") != "metadata_only":
        errors.append(validation_error("policy.safety_requirements.source_text_retention", "source_text_retention must be metadata_only"))
    if len(string_list(policy.get("required_docs"))) < 5:
        errors.append(validation_error("policy.required_docs", "required docs are missing"))
    if not dict_value(policy.get("required_doc_markers")):
        errors.append(validation_error("policy.required_doc_markers", "required_doc_markers is required"))
    if policy.get("acceptance_marker") != "PHASE273 LARGE CONTEXT 500K LIVE ACCEPTANCE PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 273"))
    return errors


def docs_checks(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    required_markers = dict_value(policy.get("required_doc_markers"))
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        result: dict[str, Any] = {"path": raw_path, "exists": path.is_file(), "sha256": None, "missing_markers": []}
        if not path.is_file():
            errors.append(validation_error(f"docs.{raw_path}.missing", "required doc is missing", source="docs"))
            results.append(result)
            continue
        text = path.read_text(encoding="utf-8")
        result["sha256"] = sha256_file(path)
        missing = [marker for marker in string_list(required_markers.get(raw_path)) if marker not in text]
        result["missing_markers"] = missing
        for marker in missing:
            errors.append(validation_error(f"docs.{raw_path}.marker", f"required marker missing: {marker}", source="docs"))
        results.append(result)
    return results, errors


def run_phase272(config_root: Path) -> dict[str, Any]:
    return validate_large_context_500k_stale_index_rejection(
        LargeContext500kStaleIndexRejectionConfig(config_root=config_root)
    )


def run_phase261(config: LargeContext500kLiveAcceptanceConfig, output_dir: Path) -> dict[str, Any]:
    return validate_large_context_384k_live_acceptance(
        LargeContext384kLiveAcceptanceConfig(
            config_root=config.config_root,
            output_path=output_dir / "phase273-phase261-large-context-384k-live-acceptance-report.json",
            markdown_output_path=output_dir / "phase273-phase261-large-context-384k-live-acceptance-report.md",
            include_gateway=config.include_gateway,
            include_anythingllm=config.include_anythingllm,
            live=config.live,
            model_base_url=config.model_base_url,
            workflow_router_gateway_base_url=config.workflow_router_gateway_base_url,
            anythingllm_workflow_router_base_url=config.anythingllm_workflow_router_base_url,
            controller_base_url=config.controller_base_url,
            anythingllm_api_base_url=config.anythingllm_api_base_url,
            workspace=config.workspace,
            api_key_env=config.api_key_env,
            timeout_seconds=config.timeout_seconds,
            require_artifacts=config.require_artifacts,
        )
    )


def phase272_errors(policy: dict[str, Any], phase272: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    required = dict_value(policy.get("phase272_precondition"))
    summary = dict_value(phase272.get("summary"))
    if phase272.get("status") != required.get("required_status"):
        errors.append(validation_error("phase272.status", "Phase 272 stale-index rejection must pass", source="phase272"))
    if summary.get("phase273_ready") is not required.get("required_phase273_ready"):
        errors.append(validation_error("phase272.phase273_ready", "Phase 272 must be ready for Phase 273", source="phase272"))
    return errors


def phase261_errors(policy: dict[str, Any], phase261: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    delegate = dict_value(policy.get("phase261_live_delegate"))
    summary = dict_value(phase261.get("summary"))
    if phase261.get("status") != delegate.get("required_status"):
        errors.append(validation_error("phase261.status", "Phase 261 live delegate must pass", source="phase261", severity="critical"))
    if summary.get("phase262_ready") is not delegate.get("required_phase262_ready"):
        errors.append(validation_error("phase261.phase262_ready", "Phase 261 must be phase262_ready", source="phase261"))
    if int(summary.get("response_count", 0)) < int(delegate.get("minimum_response_count", 0)):
        errors.append(validation_error("phase261.response_count", "response count below minimum", source="phase261"))
    if int(summary.get("gateway_response_count", 0)) < int(delegate.get("minimum_gateway_response_count", 0)):
        errors.append(validation_error("phase261.gateway_response_count", "gateway response count below minimum", source="phase261"))
    if int(summary.get("anythingllm_response_count", 0)) < int(delegate.get("minimum_anythingllm_response_count", 0)):
        errors.append(validation_error("phase261.anythingllm_response_count", "AnythingLLM response count below minimum", source="phase261"))
    if summary.get("target_settings_status") != "passed":
        errors.append(validation_error("phase261.target_settings_status", "AnythingLLM target settings must pass", source="phase261"))
    if summary.get("json_default_parity_status") != "passed":
        errors.append(validation_error("phase261.json_default_parity_status", "JSON/default parity must pass", source="phase261"))
    if int(summary.get("critical_or_high_finding_count", 0)):
        errors.append(validation_error("phase261.critical_or_high_finding_count", "critical/high findings must be zero", source="phase261", severity="critical"))
    if summary.get("raw_prompt_stuffing_allowed") is not False:
        errors.append(validation_error("phase261.raw_prompt_stuffing_allowed", "raw prompt stuffing must be false", source="phase261"))
    missing = sorted(REQUIRED_STRATEGIES - set(string_list(summary.get("strategy_ids"))))
    if missing:
        errors.append(validation_error("phase261.strategy_ids", "missing required strategies: " + ", ".join(missing), source="phase261", severity="critical"))
    return errors


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Large-Context 500k Live Acceptance",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Error count: `{summary.get('error_count')}`",
        f"- Candidate estimated project tokens: `{summary.get('candidate_estimated_project_tokens')}`",
        f"- Response count: `{summary.get('response_count')}`",
        f"- Gateway responses: `{summary.get('gateway_response_count')}`",
        f"- AnythingLLM responses: `{summary.get('anythingllm_response_count')}`",
        f"- Strategy ids: `{', '.join(string_list(summary.get('strategy_ids')))}`",
        f"- JSON/default parity: `{summary.get('json_default_parity_status')}`",
        f"- Critical/high findings: `{summary.get('critical_or_high_finding_count')}`",
        "",
        "## Errors",
    ]
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    if errors:
        lines.extend(f"- `{item.get('severity')}` `{item.get('id')}`: {item.get('message')}" for item in errors if isinstance(item, dict))
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_large_context_500k_live_acceptance(config: LargeContext500kLiveAcceptanceConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    output_dir = output_path.parent
    policy = read_json_object(policy_path)

    policy_errors = validate_policy(policy)
    docs, docs_errors = docs_checks(config_root, policy)
    phase272 = (
        run_phase272(config_root)
        if config.validate_phase272_precondition
        else {"status": LargeContext500kStaleIndexRejectionStatus.PASSED.value, "summary": {"phase273_ready": True}}
    )
    phase261 = run_phase261(config, output_dir)
    errors = policy_errors + docs_errors + phase272_errors(policy, phase272) + phase261_errors(policy, phase261)
    phase272_summary = dict_value(phase272.get("summary"))
    phase261_summary = dict_value(phase261.get("summary"))
    status = LargeContext500kLiveAcceptanceStatus.PASSED.value if not errors else LargeContext500kLiveAcceptanceStatus.FAILED.value
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
        "docs": docs,
        "phase272_summary": phase272_summary,
        "phase261_summary": phase261_summary,
        "phase261_report_path": phase261.get("report_path"),
        "phase261_run_ids": phase261.get("run_ids"),
        "errors": errors,
        "summary": {
            "error_count": len(errors),
            "candidate_estimated_project_tokens": policy.get("candidate_estimated_project_tokens"),
            "phase272_status": phase272.get("status"),
            "phase272_phase273_ready": phase272_summary.get("phase273_ready"),
            "phase261_status": phase261.get("status"),
            "phase261_phase262_ready": phase261_summary.get("phase262_ready"),
            "strategy_ids": string_list(phase261_summary.get("strategy_ids")),
            "response_count": phase261_summary.get("response_count"),
            "gateway_response_count": phase261_summary.get("gateway_response_count"),
            "anythingllm_response_count": phase261_summary.get("anythingllm_response_count"),
            "target_settings_status": phase261_summary.get("target_settings_status"),
            "json_default_parity_status": phase261_summary.get("json_default_parity_status"),
            "critical_or_high_finding_count": phase261_summary.get("critical_or_high_finding_count"),
            "raw_prompt_stuffing_allowed": phase261_summary.get("raw_prompt_stuffing_allowed"),
            "phase274_ready": not errors,
        },
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
