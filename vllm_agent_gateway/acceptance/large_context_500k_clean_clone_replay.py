"""Phase 275 clean-clone replay gate for the 500k candidate target."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.large_context_384k_clean_clone_replay import (
    git_state,
    run_command,
)
from vllm_agent_gateway.acceptance.large_context_500k_answer_quality_repair import (
    LargeContext500kAnswerQualityRepairConfig,
    validate_large_context_500k_answer_quality_repair,
)
from vllm_agent_gateway.acceptance.large_context_500k_candidate_rebaseline import (
    LargeContext500kCandidateRebaselineConfig,
    dict_value,
    read_json_object,
    sha256_file,
    string_list,
    validate_large_context_500k_candidate_rebaseline,
    validation_error,
    write_json,
    write_text,
)
from vllm_agent_gateway.acceptance.large_context_500k_fixture_index_readiness import (
    LargeContext500kFixtureIndexReadinessConfig,
    validate_large_context_500k_fixture_index_readiness,
)
from vllm_agent_gateway.acceptance.large_context_500k_live_acceptance import (
    LargeContext500kLiveAcceptanceConfig,
    validate_large_context_500k_live_acceptance,
)
from vllm_agent_gateway.acceptance.large_context_500k_stale_index_rejection import (
    LargeContext500kStaleIndexRejectionConfig,
    validate_large_context_500k_stale_index_rejection,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "large_context_500k_clean_clone_replay_policy"
EXPECTED_REPORT_KIND = "large_context_500k_clean_clone_replay_report"
EXPECTED_PHASE = 275
EXPECTED_BACKLOG_ID = "P0-M15-275"
EXPECTED_MILESTONE_IDS = {"M14", "M15", "M16"}
CANDIDATE_ESTIMATED_PROJECT_TOKENS = 500_000
DEFAULT_POLICY_PATH = Path("runtime") / "large_context_500k_clean_clone_replay_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase275"
    / "phase275-large-context-500k-clean-clone-replay-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase275"
    / "phase275-large-context-500k-clean-clone-replay-report.md"
)


class LargeContext500kCleanCloneReplayStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class LargeContext500kCleanCloneReplayDecision(str, Enum):
    READY = "phase275_clean_clone_500k_candidate_ready"
    BLOCKED = "phase275_clean_clone_500k_candidate_blocked"


@dataclass(frozen=True)
class LargeContext500kCleanCloneReplayConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    live: bool = False
    model_base_url: str = "http://127.0.0.1:8000/v1"
    workflow_router_gateway_base_url: str = "http://127.0.0.1:8500/v1"
    anythingllm_workflow_router_base_url: str | None = None
    controller_base_url: str = "http://127.0.0.1:8400"
    anythingllm_api_base_url: str = "http://127.0.0.1:3001"
    workspace: str = "my-workspace"
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 1200


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
        errors.append(validation_error("policy.phase", "phase must be 275"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M14, M15, and M16"))
    if policy.get("candidate_estimated_project_tokens") != CANDIDATE_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("policy.candidate_estimated_project_tokens", "candidate target must be 500000"))
    if policy.get("required_decision") != LargeContext500kCleanCloneReplayDecision.READY.value:
        errors.append(validation_error("policy.required_decision", "required decision mismatch"))
    source = dict_value(policy.get("source_requirements"))
    if source.get("required_source_mode") != "remote_branch_clone":
        errors.append(validation_error("policy.source_requirements.required_source_mode", "must be remote_branch_clone"))
    if not source.get("required_branch"):
        errors.append(validation_error("policy.source_requirements.required_branch", "required_branch is required"))
    if not source.get("required_remote_url_fragment"):
        errors.append(validation_error("policy.source_requirements.required_remote_url_fragment", "required remote URL fragment is required"))
    if set(string_list(policy.get("required_gates"))) != {
        "docs_index",
        "phase270_candidate_rebaseline",
        "phase271_fixture_index_readiness",
        "phase272_stale_index_rejection",
        "phase273_live_acceptance",
        "phase274_answer_quality_repair",
    }:
        errors.append(validation_error("policy.required_gates", "gate set mismatch"))
    safety = dict_value(policy.get("safety_requirements"))
    for key in (
        "raw_prompt_stuffing_allowed",
        "raw_500k_prompt_support_claim_allowed",
        "runtime_state_tracked_allowed",
        "active_workspace_runtime_state_dependency_allowed",
        "protected_fixture_mutation_allowed",
    ):
        if safety.get(key) is not False:
            errors.append(validation_error(f"policy.safety_requirements.{key}", f"{key} must be false"))
    if len(string_list(policy.get("required_docs"))) < 5:
        errors.append(validation_error("policy.required_docs", "required docs are missing"))
    if not dict_value(policy.get("required_doc_markers")):
        errors.append(validation_error("policy.required_doc_markers", "required_doc_markers is required"))
    if policy.get("acceptance_marker") != "PHASE275 LARGE CONTEXT 500K CLEAN CLONE REPLAY PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 275"))
    return errors


def docs_checks(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    markers = dict_value(policy.get("required_doc_markers"))
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        result: dict[str, Any] = {"path": raw_path, "exists": path.is_file(), "sha256": None, "missing_markers": []}
        if not path.is_file():
            errors.append(validation_error(f"docs.{raw_path}.missing", "required doc is missing", source="docs"))
            results.append(result)
            continue
        text = path.read_text(encoding="utf-8")
        result["sha256"] = sha256_file(path)
        missing = [marker for marker in string_list(markers.get(raw_path)) if marker not in text]
        result["missing_markers"] = missing
        for marker in missing:
            errors.append(validation_error(f"docs.{raw_path}.marker", f"missing marker: {marker}", source="docs"))
        results.append(result)
    return results, errors


def source_checks(policy: dict[str, Any], before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    source = dict_value(policy.get("source_requirements"))
    if before.get("inside_work_tree") is not True:
        errors.append(validation_error("source.inside_work_tree", "config root must be a git worktree", source="source", severity="critical"))
    required_branch = source.get("required_branch")
    if isinstance(required_branch, str) and before.get("branch") != required_branch:
        errors.append(validation_error("source.branch", f"branch must be {required_branch}", source="source"))
    required_remote = source.get("required_remote_url_fragment")
    remote = str(before.get("remote_origin_url") or "")
    if isinstance(required_remote, str) and required_remote not in remote:
        errors.append(validation_error("source.remote_origin_url", f"remote must contain {required_remote}", source="source"))
    if source.get("require_clean_git_status_before") is True and before.get("dirty_line_count") != 0:
        errors.append(validation_error("source.clean_before", "git status must be clean before replay", source="source", severity="critical"))
    if source.get("require_clean_git_status_after") is True and after.get("dirty_line_count") != 0:
        errors.append(validation_error("source.clean_after", "git status must remain clean after replay", source="source", severity="critical"))
    if source.get("require_runtime_state_ignored") is True and before.get("runtime_state_ignored") is not True:
        errors.append(validation_error("source.runtime_state_ignored", "runtime-state must be ignored in the clean clone", source="source"))
    return errors


def docs_index_check(config_root: Path) -> dict[str, Any]:
    result = run_command(["python3", "scripts/check_docs_index.py"], cwd=config_root, timeout_seconds=120)
    return {"status": "passed" if result.get("returncode") == 0 else "failed", **result}


def run_gate(gate_id: str, callback: Any) -> dict[str, Any]:
    try:
        value = callback()
        if isinstance(value, dict):
            return value
        raise RuntimeError("gate returned non-object report")
    except Exception as exc:  # pragma: no cover - regression covers through public behavior
        return {
            "status": LargeContext500kCleanCloneReplayStatus.FAILED.value,
            "errors": [
                validation_error(
                    f"{gate_id}.exception",
                    f"{type(exc).__name__}: {exc}",
                    source=gate_id,
                    severity="critical",
                )
            ],
            "summary": {"error_count": 1},
        }


def run_gates(config: LargeContext500kCleanCloneReplayConfig) -> dict[str, dict[str, Any]]:
    root = config.config_root.resolve()
    return {
        "docs_index": run_gate("docs_index", lambda: docs_index_check(root)),
        "phase270_candidate_rebaseline": run_gate(
            "phase270_candidate_rebaseline",
            lambda: validate_large_context_500k_candidate_rebaseline(
                LargeContext500kCandidateRebaselineConfig(config_root=root)
            ),
        ),
        "phase271_fixture_index_readiness": run_gate(
            "phase271_fixture_index_readiness",
            lambda: validate_large_context_500k_fixture_index_readiness(
                LargeContext500kFixtureIndexReadinessConfig(config_root=root)
            ),
        ),
        "phase272_stale_index_rejection": run_gate(
            "phase272_stale_index_rejection",
            lambda: validate_large_context_500k_stale_index_rejection(
                LargeContext500kStaleIndexRejectionConfig(config_root=root)
            ),
        ),
        "phase273_live_acceptance": run_gate(
            "phase273_live_acceptance",
            lambda: validate_large_context_500k_live_acceptance(
                LargeContext500kLiveAcceptanceConfig(
                    config_root=root,
                    live=config.live,
                    model_base_url=config.model_base_url,
                    workflow_router_gateway_base_url=config.workflow_router_gateway_base_url,
                    anythingllm_workflow_router_base_url=config.anythingllm_workflow_router_base_url,
                    controller_base_url=config.controller_base_url,
                    anythingllm_api_base_url=config.anythingllm_api_base_url,
                    workspace=config.workspace,
                    api_key_env=config.api_key_env,
                    timeout_seconds=config.timeout_seconds,
                )
            ),
        ),
        "phase274_answer_quality_repair": run_gate(
            "phase274_answer_quality_repair",
            lambda: validate_large_context_500k_answer_quality_repair(
                LargeContext500kAnswerQualityRepairConfig(config_root=root)
            ),
        ),
    }


def gate_errors(gates: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for gate_id, report in gates.items():
        if report.get("status") != "passed":
            errors.append(validation_error(f"{gate_id}.status", f"{gate_id} did not pass", source=gate_id, severity="critical"))
        for item in report.get("errors") if isinstance(report.get("errors"), list) else []:
            if isinstance(item, dict):
                errors.append(
                    validation_error(
                        f"{gate_id}.{item.get('id')}",
                        str(item.get("message") or "gate reported an error"),
                        source=gate_id,
                        severity=str(item.get("severity") or "high"),
                    )
                )
    return errors


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Large-Context 500k Clean Clone Replay",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- Error count: `{summary.get('error_count')}`",
        f"- Source branch: `{summary.get('source_branch')}`",
        f"- Source dirty before: `{summary.get('source_dirty_line_count_before')}`",
        f"- Source dirty after: `{summary.get('source_dirty_line_count_after')}`",
        f"- Passed gate count: `{summary.get('passed_gate_count')}`",
        f"- Phase 273 responses: `{summary.get('phase273_response_count')}`",
        f"- Phase 274 decision: `{summary.get('phase274_decision')}`",
        "",
        "## Errors",
    ]
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    if errors:
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors if isinstance(item, dict))
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_large_context_500k_clean_clone_replay(
    config: LargeContext500kCleanCloneReplayConfig,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    policy = read_json_object(policy_path)

    before_git = git_state(config_root)
    policy_errors = validate_policy(policy)
    docs, docs_errors = docs_checks(config_root, policy)
    gates = run_gates(config)
    after_git = git_state(config_root)
    errors = policy_errors + docs_errors + source_checks(policy, before_git, after_git) + gate_errors(gates)
    status = LargeContext500kCleanCloneReplayStatus.PASSED.value if not errors else LargeContext500kCleanCloneReplayStatus.FAILED.value
    decision = (
        LargeContext500kCleanCloneReplayDecision.READY.value
        if status == LargeContext500kCleanCloneReplayStatus.PASSED.value
        else LargeContext500kCleanCloneReplayDecision.BLOCKED.value
    )
    phase273_summary = dict_value(dict_value(gates.get("phase273_live_acceptance")).get("summary"))
    phase274 = dict_value(gates.get("phase274_answer_quality_repair"))
    phase274_summary = dict_value(phase274.get("summary"))
    passed_gate_count = sum(1 for item in gates.values() if item.get("status") == "passed")
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": status,
        "decision": decision,
        "policy_path": str(policy_path),
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "config_root": str(config_root),
        "git_before": before_git,
        "git_after": after_git,
        "docs": docs,
        "gates": {
            key: {
                "status": value.get("status"),
                "summary": dict_value(value.get("summary")),
                "report_path": value.get("report_path"),
            }
            for key, value in gates.items()
        },
        "errors": errors,
        "summary": {
            "error_count": len(errors),
            "decision": decision,
            "source_branch": before_git.get("branch"),
            "source_commit": before_git.get("commit"),
            "source_remote_origin_url": before_git.get("remote_origin_url"),
            "source_dirty_line_count_before": before_git.get("dirty_line_count"),
            "source_dirty_line_count_after": after_git.get("dirty_line_count"),
            "runtime_state_ignored": before_git.get("runtime_state_ignored"),
            "gate_count": len(gates),
            "passed_gate_count": passed_gate_count,
            "phase273_response_count": phase273_summary.get("response_count"),
            "phase273_gateway_response_count": phase273_summary.get("gateway_response_count"),
            "phase273_anythingllm_response_count": phase273_summary.get("anythingllm_response_count"),
            "phase273_critical_or_high_finding_count": phase273_summary.get("critical_or_high_finding_count"),
            "phase273_json_default_parity_status": phase273_summary.get("json_default_parity_status"),
            "phase274_decision": phase274.get("decision"),
            "phase274_phase275_ready": phase274_summary.get("phase275_ready"),
            "phase276_ready": not errors,
        },
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
