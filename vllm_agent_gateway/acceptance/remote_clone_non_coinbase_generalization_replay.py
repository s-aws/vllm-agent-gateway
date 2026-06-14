"""Phase 240 remote-clone non-Coinbase generalization replay gate."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.multi_repo_baseline_comparison import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    object_list,
    run_live_case,
    string_list,
)
from vllm_agent_gateway.acceptance.remote_clone_priority0_chat_quality_replay import anythingllm_target_settings


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "remote_clone_non_coinbase_generalization_replay_policy"
EXPECTED_REPORT_KIND = "remote_clone_non_coinbase_generalization_replay_report"
EXPECTED_PHASE = 240
EXPECTED_BACKLOG_ID = "P0-M14-240"
EXPECTED_MILESTONE_ID = "M5"
DEFAULT_POLICY_PATH = Path("runtime") / "remote_clone_non_coinbase_generalization_replay_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "remote-clone-non-coinbase-generalization-replay" / "phase240"


class RemoteCloneGeneralizationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class RemoteCloneGeneralizationDecision(str, Enum):
    READY = "remote_clone_non_coinbase_generalization_ready"
    BLOCKED = "remote_clone_non_coinbase_generalization_blocked"


@dataclass(frozen=True)
class RemoteCloneGeneralizationReplayConfig:
    config_root: Path
    output_path: Path | None = None
    policy_path: Path = DEFAULT_POLICY_PATH
    include_gateway: bool = True
    include_anythingllm: bool = True
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 600


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"remote-clone-non-coinbase-generalization-replay-{utc_timestamp()}.json"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_policy(config_root: Path, policy_path: Path) -> dict[str, Any]:
    return read_json(resolve_path(config_root, policy_path))


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 240")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(f"policy.milestone_id must be {EXPECTED_MILESTONE_ID}")
    if policy.get("required_decision") != RemoteCloneGeneralizationDecision.READY.value:
        errors.append("policy.required_decision must be remote_clone_non_coinbase_generalization_ready")
    if set(string_list(policy.get("required_surfaces"))) != {"gateway", "anythingllm"}:
        errors.append("policy.required_surfaces must include gateway and anythingllm")
    for marker in ("Answer:", "Source mutation: false"):
        if marker not in string_list(policy.get("required_chat_markers")):
            errors.append(f"policy.required_chat_markers must include {marker!r}")
    cases = object_list(policy.get("cases"))
    if len(cases) < int(policy.get("minimum_case_count", 0)):
        errors.append("policy.cases below minimum_case_count")
    target_roots = {str(case.get("target_root")) for case in cases}
    non_coinbase_roots = {root for root in target_roots if "coinbase_testing_repo" not in root}
    if len(non_coinbase_roots) < int(policy.get("minimum_non_coinbase_root_count", 0)):
        errors.append("policy.cases below minimum_non_coinbase_root_count")
    for index, case in enumerate(cases):
        prefix = f"policy.cases[{index}]"
        for field in ("case_id", "category", "prompt_family", "target_root", "expected_workflow", "prompt"):
            if not isinstance(case.get(field), str) or not case.get(field):
                errors.append(f"{prefix}.{field} must be a non-empty string")
        if case.get("expected_workflow") != "code_investigation.plan":
            errors.append(f"{prefix}.expected_workflow must be code_investigation.plan")
        if not string_list(case.get("source_hints")):
            errors.append(f"{prefix}.source_hints must be a non-empty string list")
        if not string_list(case.get("test_hints")):
            errors.append(f"{prefix}.test_hints must be a non-empty string list")
    if "do not commit or push to s-aws/staterail" not in " ".join(string_list(policy.get("safety_boundaries"))).lower():
        errors.append("policy.safety_boundaries must include no commit/push to s-aws/staterail")
    if policy.get("acceptance_marker") != "REMOTE CLONE NON-COINBASE GENERALIZATION REPLAY PASS":
        errors.append("policy.acceptance_marker must be REMOTE CLONE NON-COINBASE GENERALIZATION REPLAY PASS")
    return errors


def materialize_case(case: dict[str, Any], config_root: Path) -> dict[str, Any]:
    root = config_root.as_posix()
    materialized: dict[str, Any] = {}
    for key, value in case.items():
        if isinstance(value, str):
            materialized[key] = value.replace("{config_root}", root)
        elif isinstance(value, list):
            materialized[key] = [item.replace("{config_root}", root) if isinstance(item, str) else item for item in value]
        else:
            materialized[key] = value
    return materialized


def selected_surfaces(config: RemoteCloneGeneralizationReplayConfig) -> list[str]:
    values: list[str] = []
    if config.include_gateway:
        values.append("gateway")
    if config.include_anythingllm:
        values.append("anythingllm")
    return values


def git_state(root: Path) -> dict[str, Any] | None:
    if not (root / ".git").exists():
        return None
    status = subprocess.run(["git", "-C", str(root), "status", "--short"], check=True, capture_output=True, text=True)
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True)
    remote = subprocess.run(["git", "-C", str(root), "remote", "-v"], check=True, capture_output=True, text=True)
    return {
        "path": root.as_posix(),
        "head": head.stdout.strip(),
        "status_clean": status.stdout == "",
        "status_lines": status.stdout.splitlines(),
        "remote_lines": remote.stdout.splitlines(),
    }


def repo_states(cases: list[dict[str, Any]]) -> dict[str, Any]:
    states: dict[str, Any] = {}
    for root_text in sorted({str(case.get("target_root")) for case in cases}):
        root = Path(root_text)
        state = git_state(root)
        states[root_text] = state or {"path": root_text, "git": False}
    return states


def build_report(
    *,
    policy: dict[str, Any],
    target_settings: dict[str, Any],
    cases: list[dict[str, Any]],
    responses: list[dict[str, Any]],
    repo_state_before: dict[str, Any],
    repo_state_after: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    gap_responses = [item for item in responses if string_list(item.get("gap_classes")) != ["none"]]
    low_score_responses = [
        item
        for item in responses
        if isinstance(item.get("score"), int) and item["score"] < int(policy.get("minimum_score_for_pass", 80))
    ]
    missing_response_count = max(0, int(policy.get("minimum_response_count", 0)) - len(responses))
    repo_state_unchanged = repo_state_before == repo_state_after
    required_response_count_met = missing_response_count == 0
    ready = (
        not errors
        and target_settings.get("status") == RemoteCloneGeneralizationStatus.PASSED.value
        and not gap_responses
        and not low_score_responses
        and required_response_count_met
        and repo_state_unchanged
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_id": EXPECTED_MILESTONE_ID,
        "status": RemoteCloneGeneralizationStatus.PASSED.value if ready else RemoteCloneGeneralizationStatus.FAILED.value,
        "decision": RemoteCloneGeneralizationDecision.READY.value if ready else RemoteCloneGeneralizationDecision.BLOCKED.value,
        "generated_at": utc_timestamp(),
        "target_settings": target_settings,
        "cases": cases,
        "responses": responses,
        "repo_state_before": repo_state_before,
        "repo_state_after": repo_state_after,
        "repo_state_unchanged": repo_state_unchanged,
        "summary": {
            "case_count": len(cases),
            "response_count": len(responses),
            "gateway_response_count": sum(1 for item in responses if item.get("surface") == "gateway"),
            "anythingllm_response_count": sum(1 for item in responses if item.get("surface") == "anythingllm"),
            "target_root_count": len({case.get("target_root") for case in cases}),
            "non_coinbase_root_count": len({case.get("target_root") for case in cases if "coinbase_testing_repo" not in str(case.get("target_root"))}),
            "gap_response_count": len(gap_responses),
            "low_score_response_count": len(low_score_responses),
            "missing_response_count": missing_response_count,
            "target_settings_status": target_settings.get("status"),
            "repo_state_unchanged": repo_state_unchanged,
        },
        "errors": errors
        + [f"gap response {item.get('surface')} {item.get('case_id')}: {item.get('errors')}" for item in gap_responses]
        + [f"low score response {item.get('surface')} {item.get('case_id')}: {item.get('score')}" for item in low_score_responses]
        + (["response count below policy.minimum_response_count"] if not required_response_count_met else []),
    }


def validate_report(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("report.schema_version must be 1")
    if report.get("kind") != EXPECTED_REPORT_KIND:
        errors.append(f"report.kind must be {EXPECTED_REPORT_KIND}")
    if report.get("phase") != EXPECTED_PHASE:
        errors.append("report.phase must be 240")
    if report.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"report.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if report.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(f"report.milestone_id must be {EXPECTED_MILESTONE_ID}")
    if report.get("target_settings", {}).get("status") != RemoteCloneGeneralizationStatus.PASSED.value:
        errors.append("report.target_settings must pass")
    if report.get("repo_state_unchanged") is not True:
        errors.append("report.repo_state_unchanged must be true")
    if report.get("decision") != policy.get("required_decision"):
        errors.append("report.decision must match policy.required_decision")
    responses = object_list(report.get("responses"))
    if len(responses) < int(policy.get("minimum_response_count", 0)):
        errors.append("report.responses below minimum_response_count")
    if any(string_list(item.get("gap_classes")) != ["none"] for item in responses):
        errors.append("report.responses must not contain gap classes")
    rebuilt = build_report(
        policy=policy,
        target_settings=report.get("target_settings") if isinstance(report.get("target_settings"), dict) else {},
        cases=object_list(report.get("cases")),
        responses=responses,
        repo_state_before=report.get("repo_state_before") if isinstance(report.get("repo_state_before"), dict) else {},
        repo_state_after=report.get("repo_state_after") if isinstance(report.get("repo_state_after"), dict) else {},
        errors=report.get("errors") if isinstance(report.get("errors"), list) else [],
    )
    for key in ("status", "decision", "summary"):
        if report.get(key) != rebuilt.get(key):
            errors.append(f"report.{key} must match rebuilt Phase 240 report")
    return errors


def run_remote_clone_non_coinbase_generalization_replay(config: RemoteCloneGeneralizationReplayConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy = load_policy(config_root, config.policy_path)
    errors = validate_policy(policy)
    api_key = os.environ.get(config.api_key_env)
    if config.include_anythingllm and not api_key:
        errors.append(f"{config.api_key_env} is required for live AnythingLLM replay")
        api_key = None
    cases = [materialize_case(case, config_root) for case in object_list(policy.get("cases"))]
    surfaces = selected_surfaces(config)
    if set(surfaces) != set(string_list(policy.get("required_surfaces"))):
        errors.append("selected surfaces must match policy.required_surfaces")
    target_settings = (
        anythingllm_target_settings(config, api_key=api_key, policy=policy)
        if api_key
        else {"status": RemoteCloneGeneralizationStatus.FAILED.value, "errors": [f"{config.api_key_env} missing"]}
    )
    before = repo_states(cases)
    responses: list[dict[str, Any]] = []
    if not errors:
        live_policy = {"required_chat_markers": string_list(policy.get("required_chat_markers"))}
        for surface in surfaces:
            for case in cases:
                responses.append(run_live_case(config, policy=live_policy, case=case, surface=surface, api_key=api_key))
    after = repo_states(cases)
    report = build_report(
        policy=policy,
        target_settings=target_settings,
        cases=cases,
        responses=responses,
        repo_state_before=before,
        repo_state_after=after,
        errors=errors,
    )
    validation_errors = validate_report(report, policy)
    if validation_errors:
        report["status"] = RemoteCloneGeneralizationStatus.FAILED.value
        report["decision"] = RemoteCloneGeneralizationDecision.BLOCKED.value
        report["errors"] = report["errors"] + validation_errors
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
