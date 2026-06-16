"""Phase 264 clean-clone replay gate for the 384k large-context target."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.large_context_384k_fixture_index_readiness import (
    DEFAULT_MARKDOWN_OUTPUT_PATH as PHASE259_DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH as PHASE259_DEFAULT_OUTPUT_PATH,
    LargeContext384kFixtureIndexReadinessConfig,
    validate_large_context_384k_fixture_index_readiness,
)
from vllm_agent_gateway.acceptance.large_context_384k_live_acceptance import (
    LargeContext384kLiveAcceptanceConfig,
    validate_large_context_384k_live_acceptance,
)
from vllm_agent_gateway.acceptance.large_context_384k_objective_rebaseline import (
    LargeContext384kObjectiveRebaselineConfig,
    validate_large_context_384k_objective_rebaseline,
)
from vllm_agent_gateway.acceptance.large_context_384k_stale_index_rejection import (
    DEFAULT_MARKDOWN_OUTPUT_PATH as PHASE260_DEFAULT_MARKDOWN_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH as PHASE260_DEFAULT_OUTPUT_PATH,
    LargeContext384kStaleIndexRejectionConfig,
    validate_large_context_384k_stale_index_rejection,
)
from vllm_agent_gateway.acceptance.large_context_384k_usability_acceptance_contract import (
    LargeContext384kUsabilityAcceptanceContractConfig,
    validate_large_context_384k_usability_acceptance_contract,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "large_context_384k_clean_clone_replay_policy"
EXPECTED_REPORT_KIND = "large_context_384k_clean_clone_replay_report"
EXPECTED_PHASE = 264
EXPECTED_BACKLOG_ID = "P0-M6-264"
EXPECTED_MILESTONE_IDS = {"M14", "M6", "M16"}
TARGET_ESTIMATED_PROJECT_TOKENS = 384_000
DEFAULT_POLICY_PATH = Path("runtime") / "large_context_384k_clean_clone_replay_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase264"
    / "phase264-large-context-384k-clean-clone-replay-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase264"
    / "phase264-large-context-384k-clean-clone-replay-report.md"
)


class LargeContext384kCleanCloneReplayStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class LargeContext384kCleanCloneReplayDecision(str, Enum):
    READY = "phase264_clean_clone_384k_usability_ready"
    BLOCKED = "phase264_clean_clone_384k_usability_blocked"


@dataclass(frozen=True)
class LargeContext384kCleanCloneReplayConfig:
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
    text = str(value)
    if os.name == "nt" and len(text) > 7 and text.startswith("/mnt/") and text[5].isalpha() and text[6] == "/":
        return Path(f"{text[5].upper()}:/{text[7:]}")
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


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def int_value(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def validation_error(error_id: str, message: str, *, source: str = "policy", severity: str = "high") -> dict[str, str]:
    return {"id": error_id, "message": message, "source": source, "severity": severity}


def run_command(argv: list[str], *, cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "command": argv,
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-4000:],
            "stderr_tail": result.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": argv,
            "returncode": None,
            "timed_out": True,
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
        }


def git_text(config_root: Path, args: list[str]) -> tuple[int | None, str]:
    result = run_command(["git", "-C", str(config_root), *args], cwd=config_root, timeout_seconds=30)
    output = (result.get("stdout_tail") or result.get("stderr_tail") or "").strip()
    return result.get("returncode"), output


def git_state(config_root: Path) -> dict[str, Any]:
    inside_rc, inside = git_text(config_root, ["rev-parse", "--is-inside-work-tree"])
    branch_rc, branch = git_text(config_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    commit_rc, commit = git_text(config_root, ["rev-parse", "HEAD"])
    remote_rc, remote = git_text(config_root, ["config", "--get", "remote.origin.url"])
    status_rc, status = git_text(config_root, ["status", "--short"])
    ignored = run_command(
        ["git", "-C", str(config_root), "check-ignore", "-q", "runtime-state/phase264/probe.txt"],
        cwd=config_root,
        timeout_seconds=30,
    )
    status_lines = [line for line in status.splitlines() if line.strip()]
    return {
        "inside_work_tree": inside_rc == 0 and inside == "true",
        "branch": branch if branch_rc == 0 else None,
        "commit": commit if commit_rc == 0 else None,
        "remote_origin_url": remote if remote_rc == 0 else None,
        "status_returncode": status_rc,
        "status_short": status,
        "dirty_line_count": len(status_lines) if status_rc == 0 else None,
        "runtime_state_ignored": ignored.get("returncode") == 0,
    }


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 264"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M14, M6, and M16"))
    if policy.get("required_decision") != LargeContext384kCleanCloneReplayDecision.READY.value:
        errors.append(validation_error("policy.required_decision", "required decision mismatch"))
    source = dict_value(policy.get("source_requirements"))
    if source.get("required_source_mode") != "remote_branch_clone":
        errors.append(validation_error("policy.source_requirements.required_source_mode", "must be remote_branch_clone"))
    if not source.get("required_branch"):
        errors.append(validation_error("policy.source_requirements.required_branch", "required_branch is required"))
    if not source.get("required_remote_url_fragment"):
        errors.append(validation_error("policy.source_requirements.required_remote_url_fragment", "required remote URL fragment is required"))
    if set(string_list(policy.get("required_static_gates"))) != {
        "docs_index",
        "phase251_objective_rebaseline",
        "phase258_acceptance_contract",
        "phase259_fixture_index_readiness",
        "phase260_stale_index_rejection",
    }:
        errors.append(validation_error("policy.required_static_gates", "static gate set mismatch"))
    if policy.get("required_live_gate") != "phase261_live_acceptance":
        errors.append(validation_error("policy.required_live_gate", "required live gate must be phase261_live_acceptance"))
    summary = dict_value(policy.get("required_phase261_summary"))
    if summary.get("target_estimated_project_tokens") != TARGET_ESTIMATED_PROJECT_TOKENS:
        errors.append(validation_error("policy.required_phase261_summary.target", "target must be 384000"))
    for key in (
        "minimum_response_count",
        "minimum_gateway_response_count",
        "minimum_anythingllm_response_count",
    ):
        if int_value(summary.get(key)) <= 0:
            errors.append(validation_error(f"policy.required_phase261_summary.{key}", "minimum must be positive"))
    if set(string_list(summary.get("required_strategy_ids"))) != {
        "retrieval",
        "artifact_paging",
        "summarization",
        "refusal",
        "chunked_investigation",
    }:
        errors.append(validation_error("policy.required_phase261_summary.required_strategy_ids", "strategy set mismatch"))
    safety = dict_value(policy.get("safety_requirements"))
    expected_safety = {
        "raw_prompt_stuffing_allowed": False,
        "raw_384k_prompt_support_claim_allowed": False,
        "post_384k_expansion_allowed": False,
        "runtime_state_tracked_allowed": False,
        "active_workspace_runtime_state_dependency_allowed": False,
        "protected_fixture_mutation_allowed": False,
    }
    for key, expected in expected_safety.items():
        if safety.get(key) is not expected:
            errors.append(validation_error(f"policy.safety_requirements.{key}", f"must be {expected!r}"))
    if len(string_list(policy.get("required_docs"))) < 5:
        errors.append(validation_error("policy.required_docs", "required docs list is too small"))
    if policy.get("acceptance_marker") != "PHASE264 LARGE CONTEXT 384K CLEAN CLONE REPLAY PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker mismatch"))
    return errors


def docs_checks(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    markers = dict_value(policy.get("required_doc_markers"))
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        result: dict[str, Any] = {"path": raw_path, "exists": path.is_file(), "missing_markers": []}
        if not path.is_file():
            errors.append(validation_error(f"docs.{raw_path}.missing", "required doc is missing", source="docs"))
            results.append(result)
            continue
        text = path.read_text(encoding="utf-8")
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
    result = run_command([sys.executable, "scripts/check_docs_index.py"], cwd=config_root, timeout_seconds=120)
    return {"id": "docs_index", "status": "passed" if result.get("returncode") == 0 else "failed", **result}


def exception_report(gate_id: str, exc: BaseException) -> dict[str, Any]:
    return {
        "id": gate_id,
        "status": LargeContext384kCleanCloneReplayStatus.FAILED.value,
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


def run_gate(gate_id: str, callback: Any) -> dict[str, Any]:
    try:
        report = callback()
    except Exception as exc:  # pragma: no cover - exercised by regression with concrete exception type
        return exception_report(gate_id, exc)
    return report if isinstance(report, dict) else exception_report(gate_id, RuntimeError("gate returned non-object report"))


def mirror_canonical_gate_report(
    report: dict[str, Any],
    *,
    canonical_output_path: Path,
    canonical_markdown_output_path: Path,
    mirror_output_path: Path,
    mirror_markdown_output_path: Path,
) -> dict[str, Any]:
    mirrored = dict(report)
    mirrored["canonical_report_path"] = str(canonical_output_path.resolve())
    mirrored["report_path"] = str(mirror_output_path.resolve())
    write_json(mirror_output_path, mirrored)
    if canonical_markdown_output_path.is_file():
        write_text(mirror_markdown_output_path, canonical_markdown_output_path.read_text(encoding="utf-8"))
    return mirrored


def run_phase259_canonical_with_phase264_mirror(config_root: Path, output_dir: Path) -> dict[str, Any]:
    canonical_output_path = resolve_path(config_root, PHASE259_DEFAULT_OUTPUT_PATH)
    canonical_markdown_output_path = resolve_path(config_root, PHASE259_DEFAULT_MARKDOWN_OUTPUT_PATH)
    report = validate_large_context_384k_fixture_index_readiness(
        LargeContext384kFixtureIndexReadinessConfig(config_root=config_root)
    )
    return mirror_canonical_gate_report(
        report,
        canonical_output_path=canonical_output_path,
        canonical_markdown_output_path=canonical_markdown_output_path,
        mirror_output_path=output_dir / "phase264-phase259-large-context-384k-fixture-index-readiness-report.json",
        mirror_markdown_output_path=output_dir / "phase264-phase259-large-context-384k-fixture-index-readiness-report.md",
    )


def run_phase260_canonical_with_phase264_mirror(config_root: Path, output_dir: Path) -> dict[str, Any]:
    canonical_output_path = resolve_path(config_root, PHASE260_DEFAULT_OUTPUT_PATH)
    canonical_markdown_output_path = resolve_path(config_root, PHASE260_DEFAULT_MARKDOWN_OUTPUT_PATH)
    report = validate_large_context_384k_stale_index_rejection(
        LargeContext384kStaleIndexRejectionConfig(config_root=config_root)
    )
    return mirror_canonical_gate_report(
        report,
        canonical_output_path=canonical_output_path,
        canonical_markdown_output_path=canonical_markdown_output_path,
        mirror_output_path=output_dir / "phase264-phase260-large-context-384k-stale-index-rejection-report.json",
        mirror_markdown_output_path=output_dir / "phase264-phase260-large-context-384k-stale-index-rejection-report.md",
    )


def run_static_gates(config_root: Path, output_dir: Path) -> dict[str, Any]:
    return {
        "docs_index": run_gate("docs_index", lambda: docs_index_check(config_root)),
        "phase251_objective_rebaseline": run_gate(
            "phase251_objective_rebaseline",
            lambda: validate_large_context_384k_objective_rebaseline(
                LargeContext384kObjectiveRebaselineConfig(
                    config_root=config_root,
                    output_path=output_dir / "phase264-phase251-large-context-384k-objective-rebaseline-report.json",
                    markdown_output_path=output_dir / "phase264-phase251-large-context-384k-objective-rebaseline-report.md",
                )
            )
        ),
        "phase258_acceptance_contract": run_gate(
            "phase258_acceptance_contract",
            lambda: validate_large_context_384k_usability_acceptance_contract(
                LargeContext384kUsabilityAcceptanceContractConfig(
                    config_root=config_root,
                    output_path=output_dir / "phase264-phase258-large-context-384k-usability-acceptance-contract-report.json",
                    markdown_output_path=output_dir / "phase264-phase258-large-context-384k-usability-acceptance-contract-report.md",
                )
            )
        ),
        "phase259_fixture_index_readiness": run_gate(
            "phase259_fixture_index_readiness",
            lambda: run_phase259_canonical_with_phase264_mirror(config_root, output_dir),
        ),
        "phase260_stale_index_rejection": run_gate(
            "phase260_stale_index_rejection",
            lambda: run_phase260_canonical_with_phase264_mirror(config_root, output_dir),
        ),
    }


def run_live_gate(config: LargeContext384kCleanCloneReplayConfig, output_dir: Path) -> dict[str, Any]:
    return validate_large_context_384k_live_acceptance(
        LargeContext384kLiveAcceptanceConfig(
            config_root=config.config_root,
            output_path=output_dir / "phase264-phase261-large-context-384k-live-acceptance-report.json",
            markdown_output_path=output_dir / "phase264-phase261-large-context-384k-live-acceptance-report.md",
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
    )


def static_gate_errors(static_gates: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for gate_id, report in static_gates.items():
        status = report.get("status")
        if status != "passed":
            errors.append(validation_error(f"{gate_id}.status", f"{gate_id} did not pass", source=gate_id, severity="critical"))
        for item in object_list(report.get("errors")):
            errors.append(
                validation_error(
                    f"{gate_id}.{item.get('id')}",
                    str(item.get("message") or "gate reported an error"),
                    source=gate_id,
                    severity=str(item.get("severity") or "high"),
                )
            )
    return errors


def phase261_errors(policy: dict[str, Any], report: dict[str, Any], *, live_required: bool) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if live_required and report.get("status") != "passed":
        errors.append(validation_error("phase261.status", "Phase 261 live acceptance did not pass", source="phase261", severity="critical"))
    summary = dict_value(report.get("summary"))
    required = dict_value(policy.get("required_phase261_summary"))
    exacts = {
        "target_estimated_project_tokens": required.get("target_estimated_project_tokens"),
        "failed_small_repo_regression_count": required.get("failed_small_repo_regression_count"),
        "critical_or_high_finding_count": required.get("critical_or_high_finding_count"),
        "json_default_parity_status": required.get("json_default_parity_status"),
        "target_settings_status": required.get("target_settings_status"),
    }
    for key, expected in exacts.items():
        if expected is not None and summary.get(key) != expected:
            errors.append(validation_error(f"phase261.{key}", f"{key} must be {expected!r}", source="phase261"))
    minimums = {
        "response_count": required.get("minimum_response_count"),
        "gateway_response_count": required.get("minimum_gateway_response_count"),
        "anythingllm_response_count": required.get("minimum_anythingllm_response_count"),
    }
    for key, minimum in minimums.items():
        if isinstance(minimum, int) and int_value(summary.get(key)) < minimum:
            errors.append(validation_error(f"phase261.{key}", f"{key} below {minimum}", source="phase261"))
    missing = sorted(set(string_list(required.get("required_strategy_ids"))) - set(string_list(summary.get("strategy_ids"))))
    if missing:
        errors.append(validation_error("phase261.strategy_ids", f"missing strategies: {', '.join(missing)}", source="phase261"))
    return errors


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Large-Context 384k Clean Clone Replay",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- Error count: `{summary.get('error_count')}`",
        f"- Source branch: `{summary.get('source_branch')}`",
        f"- Source dirty before: `{summary.get('source_dirty_line_count_before')}`",
        f"- Source dirty after: `{summary.get('source_dirty_line_count_after')}`",
        f"- Static gates passed: `{summary.get('passed_static_gate_count')}`",
        f"- Phase 261 status: `{summary.get('phase261_status')}`",
        f"- Strategy ids: `{', '.join(string_list(summary.get('strategy_ids')))}`",
        "",
        "## Errors",
    ]
    errors = object_list(report.get("errors"))
    if errors:
        lines.extend(f"- `{item.get('id')}`: {item.get('message')}" for item in errors)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_large_context_384k_clean_clone_replay(config: LargeContext384kCleanCloneReplayConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    output_dir = output_path.parent
    policy = read_json_object(policy_path)

    before_git = git_state(config_root)
    policy_errors = validate_policy(policy)
    docs, doc_errors = docs_checks(config_root, policy)
    static_gates = run_static_gates(config_root, output_dir)
    phase261 = run_gate("phase261_live_acceptance", lambda: run_live_gate(config, output_dir))
    after_git = git_state(config_root)

    errors = (
        policy_errors
        + doc_errors
        + source_checks(policy, before_git, after_git)
        + static_gate_errors(static_gates)
        + phase261_errors(policy, phase261, live_required=config.live)
    )
    status = LargeContext384kCleanCloneReplayStatus.PASSED.value if not errors else LargeContext384kCleanCloneReplayStatus.FAILED.value
    decision = (
        LargeContext384kCleanCloneReplayDecision.READY.value
        if status == LargeContext384kCleanCloneReplayStatus.PASSED.value
        else LargeContext384kCleanCloneReplayDecision.BLOCKED.value
    )
    phase261_summary = dict_value(phase261.get("summary"))
    passed_static = sum(1 for item in static_gates.values() if item.get("status") == "passed")
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
        "config_root": str(config_root),
        "source_mode": dict_value(policy.get("source_requirements")).get("required_source_mode"),
        "git_before": before_git,
        "git_after": after_git,
        "docs": docs,
        "static_gates": {
            key: {"status": value.get("status"), "summary": dict_value(value.get("summary")), "report_path": value.get("report_path")}
            for key, value in static_gates.items()
        },
        "phase261_live_acceptance": {
            "status": phase261.get("status"),
            "decision": phase261.get("decision"),
            "summary": phase261_summary,
            "report_path": phase261.get("report_path"),
            "run_ids": phase261.get("run_ids"),
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
            "static_gate_count": len(static_gates),
            "passed_static_gate_count": passed_static,
            "phase261_status": phase261.get("status"),
            "target_estimated_project_tokens": phase261_summary.get("target_estimated_project_tokens"),
            "response_count": phase261_summary.get("response_count"),
            "gateway_response_count": phase261_summary.get("gateway_response_count"),
            "anythingllm_response_count": phase261_summary.get("anythingllm_response_count"),
            "failed_small_repo_regression_count": phase261_summary.get("failed_small_repo_regression_count"),
            "critical_or_high_finding_count": phase261_summary.get("critical_or_high_finding_count"),
            "json_default_parity_status": phase261_summary.get("json_default_parity_status"),
            "target_settings_status": phase261_summary.get("target_settings_status"),
            "strategy_ids": string_list(phase261_summary.get("strategy_ids")),
            "phase265_ready": not errors,
        },
    }
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
