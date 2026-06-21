"""Phase 320 clone-safe context strategy router rebaseline replay."""

from __future__ import annotations

import copy
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
from vllm_agent_gateway.acceptance.context_strategy_fixture_bootstrap import (
    make_context_strategy_fixture_policy,
)
from vllm_agent_gateway.acceptance.context_strategy_router_rebaseline import (
    ContextStrategyRouterRebaselineConfig,
    run_context_strategy_router_rebaseline,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "context_strategy_router_clone_replay_policy"
EXPECTED_REPORT_KIND = "context_strategy_router_clone_replay_report"
EXPECTED_PHASE = 320
EXPECTED_BACKLOG_ID = "P0-M8-320"
EXPECTED_MILESTONE_IDS = {"M8", "M14"}
DEFAULT_POLICY_PATH = Path("runtime") / "context_strategy_router_clone_replay_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase320" / "phase320-context-strategy-router-clone-replay-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state") / "phase320" / "phase320-context-strategy-router-clone-replay-report.md"
)
REQUIRED_OUT_OF_SCOPE = {
    "live_vllm_context_ceiling_benchmark",
    "raw_500k_prompt_support_claim",
    "second_large_context_router",
    "persistent_runtime_state_dependency",
    "protected_fixture_mutation",
    "stable_corpus_promotion",
    "advanced_refactor_reactivation",
}


@dataclass(frozen=True)
class ContextStrategyRouterCloneReplayConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def validation_error(error_id: str, message: str, *, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "source": source, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "policy.schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"policy.kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "policy.phase must be 320"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be exactly M8 and M14"))
    for key in ("phase319_policy_path", "phase220_policy_path"):
        if not isinstance(policy.get(key), str) or not policy[key].strip():
            errors.append(validation_error(f"policy.{key}", f"{key} must be non-empty"))
    bootstrap = dict_value(policy.get("bootstrap_fixture"))
    if bootstrap.get("enabled") is not True:
        errors.append(validation_error("policy.bootstrap_fixture.enabled", "bootstrap fixture must be enabled"))
    if bootstrap.get("source_text_retention") != "metadata_only":
        errors.append(validation_error("policy.bootstrap_fixture.source_text_retention", "source text retention must be metadata_only"))
    if not isinstance(bootstrap.get("secret_fixture_must_not_leak"), str) or not bootstrap["secret_fixture_must_not_leak"].strip():
        errors.append(validation_error("policy.bootstrap_fixture.secret_fixture_must_not_leak", "secret sentinel must be non-empty"))
    expected = dict_value(policy.get("required_phase319_summary"))
    for key in (
        "case_count",
        "passed_case_count",
        "failed_case_count",
        "all_strategies_covered",
        "raw_500k_prompt_support_proven",
        "raw_prompt_stuffing_allowed",
        "sensitive_or_secret_request_refused",
        "deterministic_replay_passed",
    ):
        if key not in expected:
            errors.append(validation_error(f"policy.required_phase319_summary.{key}", f"missing {key}"))
    missing = sorted(REQUIRED_OUT_OF_SCOPE - set(string_list(policy.get("out_of_scope"))))
    if missing:
        errors.append(validation_error("policy.out_of_scope", f"missing boundaries: {missing}"))
    if policy.get("acceptance_marker") != "PHASE320 CONTEXT STRATEGY ROUTER CLONE REPLAY PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 320"))
    return errors


def build_phase220_policy(config_root: Path, policy: dict[str, Any], fixture: dict[str, Any], output_root: Path) -> Path:
    source_path = resolve_path(config_root, str(policy.get("phase220_policy_path")))
    source_policy = copy.deepcopy(read_json_object(source_path))
    source_policy["target_root"] = str(fixture["target_root"])
    source_policy["context_index_policy_path"] = str(fixture["context_index_policy_path"])
    derived_path = output_root / "phase220-clone-replay-policy.json"
    write_json(derived_path, source_policy)
    return derived_path


def build_phase319_policy(
    config_root: Path,
    policy: dict[str, Any],
    fixture: dict[str, Any],
    output_root: Path,
    phase220_policy_path: Path,
) -> Path:
    source_path = resolve_path(config_root, str(policy.get("phase319_policy_path")))
    source_policy = copy.deepcopy(read_json_object(source_path))
    source_policy["target_root"] = str(fixture["target_root"])
    source_policy["context_index_policy_path"] = str(fixture["context_index_policy_path"])
    source_policy["phase220_policy_path"] = str(phase220_policy_path)
    source_policy["phase318_report_path"] = str(output_root / "not-required-in-clone-static-replay.json")
    derived_path = output_root / "phase319-clone-replay-policy.json"
    write_json(derived_path, source_policy)
    return derived_path


def validate_phase319_summary(policy: dict[str, Any], phase319_report: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    summary = dict_value(phase319_report.get("summary"))
    expected = dict_value(policy.get("required_phase319_summary"))
    if phase319_report.get("status") != "passed":
        errors.append(validation_error("phase319.status", "Phase 319 clone replay must pass", source="phase319"))
    for key, expected_value in expected.items():
        if summary.get(key) != expected_value:
            errors.append(
                validation_error(
                    f"phase319.summary.{key}",
                    f"expected {key}={expected_value!r}, got {summary.get(key)!r}",
                    source="phase319",
                )
            )
    return errors


def build_report(config: ContextStrategyRouterCloneReplayConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    output_root = output_path.parent / "bootstrap"
    policy = read_json_object(policy_path)
    policy_errors = validate_policy(policy)
    fixture = make_context_strategy_fixture_policy(config_root, output_root / "fixture")
    phase220_policy_path = build_phase220_policy(config_root, policy, fixture, output_root)
    phase319_policy_path = build_phase319_policy(config_root, policy, fixture, output_root, phase220_policy_path)
    phase319_output_path = output_root / "phase319-rebaseline-report.json"
    phase319_markdown_path = output_root / "phase319-rebaseline-report.md"
    phase319_report = run_context_strategy_router_rebaseline(
        ContextStrategyRouterRebaselineConfig(
            config_root=config_root,
            policy_path=phase319_policy_path,
            output_path=phase319_output_path,
            markdown_output_path=phase319_markdown_path,
            require_artifacts=False,
        )
    )
    validation_errors = policy_errors + validate_phase319_summary(policy, phase319_report)
    serialized = str(phase319_report)
    secret_sentinel = str(dict_value(policy.get("bootstrap_fixture")).get("secret_fixture_must_not_leak") or "")
    if secret_sentinel and secret_sentinel in serialized:
        validation_errors.append(
            validation_error("phase319.secret_fixture_leak", "secret sentinel leaked into Phase 319 report", source="phase319")
        )
    if object_list(phase319_report.get("validation_errors")):
        validation_errors.append(
            validation_error("phase319.validation_errors", "Phase 319 clone replay included validation errors", source="phase319")
        )
    status = "passed" if not validation_errors else "failed"
    phase319_summary = dict_value(phase319_report.get("summary"))
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
        "phase319_policy_path": str(phase319_policy_path),
        "phase220_policy_path": str(phase220_policy_path),
        "phase319_report_path": str(phase319_output_path),
        "phase319_report_sha256": sha256_file(phase319_output_path) if phase319_output_path.is_file() else None,
        "bootstrap_fixture": {
            "target_root": str(fixture["target_root"]),
            "context_index_policy_path": str(fixture["context_index_policy_path"]),
            "index_path": str(fixture["index_path"]),
            "indexed_file_count": fixture.get("indexed_file_count"),
            "chunk_count": fixture.get("chunk_count"),
            "estimated_indexed_token_count": fixture.get("estimated_indexed_token_count"),
            "source_text_retention": "metadata_only",
        },
        "validation_errors": validation_errors,
        "summary": {
            "phase319_status": phase319_report.get("status"),
            "phase319_case_count": phase319_summary.get("case_count"),
            "phase319_passed_case_count": phase319_summary.get("passed_case_count"),
            "phase319_failed_case_count": phase319_summary.get("failed_case_count"),
            "all_strategies_covered": phase319_summary.get("all_strategies_covered") is True,
            "raw_500k_prompt_support_proven": phase319_summary.get("raw_500k_prompt_support_proven") is True,
            "raw_prompt_stuffing_allowed": phase319_summary.get("raw_prompt_stuffing_allowed") is True,
            "sensitive_or_secret_request_refused": phase319_summary.get("sensitive_or_secret_request_refused") is True,
            "deterministic_replay_passed": phase319_summary.get("deterministic_replay_passed") is True,
            "bootstrap_fixture_created": Path(fixture["target_root"]).is_dir(),
            "persistent_runtime_state_required": False,
            "phase321_ready": status == "passed",
            "validation_error_count": len(validation_errors),
        },
    }
    return report


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    fixture = dict_value(report.get("bootstrap_fixture"))
    lines = [
        "# Context Strategy Router Clone Replay",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Phase 319 status: `{summary.get('phase319_status')}`",
        f"- Phase 319 cases: `{summary.get('phase319_passed_case_count')}/{summary.get('phase319_case_count')}`",
        f"- Bootstrap target: `{fixture.get('target_root')}`",
        f"- Bootstrap chunks: `{fixture.get('chunk_count')}`",
        f"- Persistent runtime-state required: `{summary.get('persistent_runtime_state_required')}`",
        f"- Raw 500k prompt support proven: `{summary.get('raw_500k_prompt_support_proven')}`",
        f"- Phase 321 ready: `{summary.get('phase321_ready')}`",
    ]
    errors = object_list(report.get("validation_errors"))
    if errors:
        lines.extend(["", "## Validation Errors"])
        for item in errors:
            lines.append(f"- `{item.get('id')}` ({item.get('severity')}): {item.get('message')}")
    return "\n".join(lines) + "\n"


def run_context_strategy_router_clone_replay(config: ContextStrategyRouterCloneReplayConfig) -> dict[str, Any]:
    report = build_report(config)
    output_path = resolve_path(config.config_root.resolve(), config.output_path)
    markdown_output_path = resolve_path(config.config_root.resolve(), config.markdown_output_path)
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown_report(report))
    return report
