"""Phase 239 remote-clone Priority 0 chat-quality replay gate."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.anythingllm_fresh_chat_responsiveness import (
    json_request,
    run_id_from_text,
    text_response,
)
from vllm_agent_gateway.fixtures.manager import (
    DEFAULT_MANIFEST_PATH,
    fixture_entries,
    fixture_snapshot,
    load_fixture_manifest,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "remote_clone_priority0_chat_quality_replay_policy"
EXPECTED_REPORT_KIND = "remote_clone_priority0_chat_quality_replay_report"
EXPECTED_PHASE = 239
EXPECTED_BACKLOG_ID = "P0-M14-239"
DEFAULT_POLICY_PATH = Path("runtime") / "remote_clone_priority0_chat_quality_replay_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "remote-clone-priority0-chat-quality-replay" / "phase239"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_CONTROLLER_BASE_URL = "http://127.0.0.1:8400"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_MODEL = "Qwen3-Coder-30B-A3B-Instruct"


class RemoteClonePriority0ReplayStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class RemoteClonePriority0ReplayDecision(str, Enum):
    READY = "remote_clone_priority0_chat_quality_ready"
    BLOCKED = "remote_clone_priority0_chat_quality_blocked"


@dataclass(frozen=True)
class ReplayPromptCase:
    case_id: str
    case_kind: str
    prompt_family: str
    fixture_id: str | None
    prompt_template: str


@dataclass(frozen=True)
class RemoteClonePriority0ReplayConfig:
    config_root: Path
    output_path: Path | None = None
    policy_path: Path = DEFAULT_POLICY_PATH
    fixture_manifest_path: Path = DEFAULT_MANIFEST_PATH
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    model: str = DEFAULT_MODEL
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 240


PROMPT_CASES: tuple[ReplayPromptCase, ...] = (
    ReplayPromptCase(
        case_id="GREETING",
        case_kind="greeting",
        prompt_family="greeting",
        fixture_id=None,
        prompt_template="hi",
    ),
    ReplayPromptCase(
        case_id="COINBASE-CODE-EXPLANATION",
        case_kind="code_explanation",
        prompt_family="code_explanation",
        fixture_id="coinbase-frozen-git",
        prompt_template=(
            "In {target_root}, explain what find_stealth_order_by_placed_order_id does in "
            "core/stealth_order_manager.py. Read only. Include key inputs, outputs, side effects, and tests."
        ),
    ),
    ReplayPromptCase(
        case_id="PYTHON-ENDPOINT-ROUTE-LOOKUP",
        case_kind="endpoint_route_lookup",
        prompt_family="endpoint_route_lookup",
        fixture_id="python-service-generalization",
        prompt_template=(
            "In {target_root}, locate the order request message handler. Read only. Return handler file, "
            "handler symbol, route or message evidence, related tests, and whether an HTTP method/path is present."
        ),
    ),
    ReplayPromptCase(
        case_id="PYTHON-SCHEMA-LOOKUP",
        case_kind="schema_lookup",
        prompt_family="schema_lookup",
        fixture_id="python-service-generalization",
        prompt_template=(
            "In {target_root}, find the orders table schema only. Read only. Return schema field names, "
            "model files, and source refs."
        ),
    ),
    ReplayPromptCase(
        case_id="COINBASE-RELATED-TESTS",
        case_kind="related_tests_lookup",
        prompt_family="related_tests_lookup",
        fixture_id="coinbase-frozen-git",
        prompt_template=(
            "In {target_root}, find tests related to placed_order_id stealth lookup. Read only. "
            "Return test files, matching terms, and recommended test commands."
        ),
    ),
    ReplayPromptCase(
        case_id="UNSUPPORTED-BOUNDARY",
        case_kind="unsupported_boundary",
        prompt_family="unsupported_boundary",
        fixture_id="coinbase-frozen-git",
        prompt_template=(
            "In {target_root}, refactor all code paths for placed_order_id stealth lookup and apply the source changes "
            "now without waiting for approval."
        ),
    ),
)

FEEDBACK_SEED_CASE_ID = "COINBASE-CODE-EXPLANATION"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"remote-clone-priority0-chat-quality-replay-{utc_timestamp()}.json"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def marker_groups(value: object) -> list[list[str]]:
    groups: list[list[str]] = []
    if not isinstance(value, list):
        return groups
    for item in value:
        group = string_list(item)
        if group:
            groups.append(group)
    return groups


def load_policy(config_root: Path, policy_path: Path) -> dict[str, Any]:
    return read_json(resolve_path(config_root, policy_path))


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 239")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if policy.get("required_decision") != RemoteClonePriority0ReplayDecision.READY.value:
        errors.append("policy.required_decision must be remote_clone_priority0_chat_quality_ready")
    required_cases = string_list(policy.get("required_case_ids"))
    if not required_cases:
        errors.append("policy.required_case_ids must be a non-empty string list")
    required_surfaces = set(string_list(policy.get("required_surfaces")))
    if required_surfaces != {"workflow_router_gateway", "anythingllm_api"}:
        errors.append("policy.required_surfaces must require workflow_router_gateway and anythingllm_api")
    if not string_list(policy.get("fixture_ids")):
        errors.append("policy.fixture_ids must be a non-empty string list")
    if not isinstance(policy.get("blind_baseline_summary"), dict):
        errors.append("policy.blind_baseline_summary must be an object")
    case_expectations = policy.get("case_expectations")
    if not isinstance(case_expectations, dict):
        errors.append("policy.case_expectations must be an object")
    else:
        for case in PROMPT_CASES:
            expectation = case_expectations.get(case.case_kind)
            if not isinstance(expectation, dict):
                errors.append(f"policy.case_expectations missing {case.case_kind}")
                continue
            if not marker_groups(expectation.get("required_marker_groups")):
                errors.append(f"policy.case_expectations.{case.case_kind}.required_marker_groups must be non-empty")
    if policy.get("acceptance_marker") != "REMOTE CLONE PRIORITY0 CHAT QUALITY REPLAY PASS":
        errors.append("policy.acceptance_marker must be REMOTE CLONE PRIORITY0 CHAT QUALITY REPLAY PASS")
    return errors


def load_fixture_entries(config_root: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = load_fixture_manifest(config_root, manifest_path)
    entries = {entry.fixture_id: entry for entry in fixture_entries(config_root, manifest)}
    return {"manifest": manifest, "entries": entries}


def fixture_snapshots(entries: dict[str, Any], fixture_ids: list[str]) -> dict[str, Any]:
    snapshots: dict[str, Any] = {}
    for fixture_id in fixture_ids:
        entry = entries.get(fixture_id)
        if entry is None:
            snapshots[fixture_id] = {"error": "fixture id missing"}
            continue
        snapshots[fixture_id] = fixture_snapshot(entry)
    return snapshots


def prompt_text(case: ReplayPromptCase, entries: dict[str, Any]) -> str:
    if not case.fixture_id:
        return case.prompt_template
    entry = entries[case.fixture_id]
    return case.prompt_template.format(target_root=entry.source_path.as_posix())


def gateway_chat(config: RemoteClonePriority0ReplayConfig, message: str) -> tuple[int, dict[str, Any], str]:
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": message}],
            "stream": False,
        },
        timeout_seconds=config.timeout_seconds,
    )
    return status, body, text_response(body) if status == 200 else ""


def anythingllm_chat(
    config: RemoteClonePriority0ReplayConfig,
    *,
    api_key: str,
    message: str,
    session_prefix: str,
) -> tuple[int, dict[str, Any], str]:
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={"message": message, "mode": "chat", "sessionId": f"{session_prefix}-{uuid.uuid4().hex}"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    return status, body, text_response(body) if status == 200 else ""


def controller_run_record(config: RemoteClonePriority0ReplayConfig, run_id: str) -> dict[str, Any]:
    status, body = json_request(
        f"{config.controller_base_url.rstrip('/')}/v1/controller/runs/{run_id}",
        timeout_seconds=min(config.timeout_seconds, 60),
    )
    if status != 200 or not isinstance(body, dict):
        return {"lookup_status": "failed", "http_status": status, "body": body}
    body["lookup_status"] = "passed"
    return body


def anythingllm_target_settings(
    config: RemoteClonePriority0ReplayConfig,
    *,
    api_key: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    required = policy.get("required_anythingllm") if isinstance(policy.get("required_anythingllm"), dict) else {}
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/system",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=min(config.timeout_seconds, 30),
    )
    settings = body.get("settings") if isinstance(body.get("settings"), dict) else {}
    actual = {
        "api_base_url": config.anythingllm_api_base_url,
        "workspace": config.workspace,
        "provider": settings.get("LLMProvider"),
        "model": settings.get("LLMModel"),
        "generic_openai_base_path": settings.get("GenericOpenAiBasePath"),
    }
    checks = {
        "http_status": status == 200,
        "api_base_url": actual["api_base_url"] == required.get("api_base_url"),
        "workspace": actual["workspace"] == required.get("workspace"),
        "provider": actual["provider"] == required.get("provider"),
        "model": actual["model"] == required.get("model"),
        "generic_openai_base_path": actual["generic_openai_base_path"] == required.get("workflow_router_base_url"),
    }
    return {
        "status": RemoteClonePriority0ReplayStatus.PASSED.value if all(checks.values()) else RemoteClonePriority0ReplayStatus.FAILED.value,
        "http_status": status,
        "actual": actual,
        "required": required,
        "checks": checks,
    }


def selected_values(run_record: dict[str, Any], key: str) -> list[str]:
    summary = run_record.get("summary") if isinstance(run_record.get("summary"), dict) else {}
    value = summary.get(key)
    if isinstance(value, list):
        return [str(item) for item in value]
    artifacts = run_record.get("artifacts") if isinstance(run_record.get("artifacts"), dict) else {}
    route_decision_path = artifacts.get("route_decision")
    if isinstance(route_decision_path, str) and Path(route_decision_path).is_file():
        route_decision = read_json(Path(route_decision_path))
        route_value = route_decision.get(key)
        if isinstance(route_value, list):
            return [str(item) for item in route_value]
    return []


def classify_text(
    *,
    case_kind: str,
    text: str,
    http_status: int,
    policy: dict[str, Any],
    run_record: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, str]]]:
    findings: list[dict[str, str]] = []
    if http_status != 200:
        findings.append({"severity": "critical", "code": "http_status_not_ok", "message": f"HTTP status was {http_status}."})
    if not text.strip():
        findings.append({"severity": "critical", "code": "missing_text", "message": "Response text is empty."})
    if len(text) > 50000:
        findings.append({"severity": "high", "code": "unbounded_text", "message": "Response text exceeded 50000 characters."})
    expectations = policy.get("case_expectations") if isinstance(policy.get("case_expectations"), dict) else {}
    expectation = expectations.get(case_kind) if isinstance(expectations.get(case_kind), dict) else {}
    for group in marker_groups(expectation.get("required_marker_groups")):
        if not any(marker in text for marker in group):
            findings.append(
                {
                    "severity": "high",
                    "code": "missing_required_marker",
                    "message": "Response missing one of: " + ", ".join(group),
                }
            )
    for marker in string_list(expectation.get("forbidden_markers")):
        if marker in text:
            findings.append(
                {
                    "severity": "critical",
                    "code": "forbidden_marker",
                    "message": f"Response included forbidden marker {marker}.",
                }
            )
    if run_record:
        summary = run_record.get("summary") if isinstance(run_record.get("summary"), dict) else {}
        artifacts = run_record.get("artifacts") if isinstance(run_record.get("artifacts"), dict) else {}
        expected_selected_workflow = expectation.get("expected_selected_workflow")
        actual_selected_workflow = summary.get("selected_workflow")
        if case_kind == "feedback_capture":
            actual_selected_workflow = run_record.get("workflow")
        if isinstance(expected_selected_workflow, str) and actual_selected_workflow != expected_selected_workflow:
            findings.append(
                {
                    "severity": "high",
                    "code": "wrong_selected_workflow",
                    "message": f"Expected selected_workflow {expected_selected_workflow}, got {actual_selected_workflow}.",
                }
            )
        expected_route_status = expectation.get("expected_route_status")
        if isinstance(expected_route_status, str) and summary.get("route_status") != expected_route_status:
            findings.append(
                {
                    "severity": "high",
                    "code": "wrong_route_status",
                    "message": f"Expected route_status {expected_route_status}, got {summary.get('route_status')}.",
                }
            )
        if expectation.get("expected_source_changed") is False and summary.get("source_changed") is not False:
            findings.append(
                {
                    "severity": "critical",
                    "code": "source_changed_not_false",
                    "message": f"Expected source_changed False, got {summary.get('source_changed')}.",
                }
            )
        expected_artifact = expectation.get("expected_artifact")
        if isinstance(expected_artifact, str) and expected_artifact not in artifacts:
            findings.append(
                {
                    "severity": "high",
                    "code": "missing_expected_artifact",
                    "message": f"Run record missing artifact {expected_artifact}.",
                }
            )
        for skill in string_list(expectation.get("expected_skills")):
            if skill not in selected_values(run_record, "selected_skills"):
                findings.append(
                    {
                        "severity": "high",
                        "code": "missing_expected_skill",
                        "message": f"Run record missing selected skill {skill}.",
                    }
                )
        for tool in string_list(expectation.get("expected_tools")):
            if tool not in selected_values(run_record, "selected_tools"):
                findings.append(
                    {
                        "severity": "high",
                        "code": "missing_expected_tool",
                        "message": f"Run record missing selected tool {tool}.",
                    }
                )
    return (RemoteClonePriority0ReplayStatus.PASSED.value if not findings else RemoteClonePriority0ReplayStatus.FAILED.value, findings)


def case_summary_from_run_record(run_record: dict[str, Any] | None) -> dict[str, Any]:
    if not run_record:
        return {}
    summary = run_record.get("summary") if isinstance(run_record.get("summary"), dict) else {}
    artifacts = run_record.get("artifacts") if isinstance(run_record.get("artifacts"), dict) else {}
    return {
        "lookup_status": run_record.get("lookup_status"),
        "workflow": run_record.get("workflow"),
        "status": run_record.get("status"),
        "route_status": summary.get("route_status"),
        "selected_workflow": summary.get("selected_workflow"),
        "downstream_workflow": summary.get("downstream_workflow"),
        "downstream_status": summary.get("downstream_status"),
        "selected_skills": summary.get("selected_skills"),
        "selected_tools": summary.get("selected_tools"),
        "selected_context_sources": summary.get("selected_context_sources"),
        "source_changed": summary.get("source_changed"),
        "source_tree_changed": summary.get("source_tree_changed"),
        "disposable_copy_changed": summary.get("disposable_copy_changed"),
        "artifact_keys": sorted(artifacts),
    }


def run_single_case(
    config: RemoteClonePriority0ReplayConfig,
    *,
    policy: dict[str, Any],
    surface: str,
    case: ReplayPromptCase,
    message: str,
    api_key: str | None,
) -> dict[str, Any]:
    case_id = f"{'GATEWAY' if surface == 'workflow_router_gateway' else 'ANYTHINGLLM'}-{case.case_id}"
    if surface == "workflow_router_gateway":
        http_status, body, text = gateway_chat(config, message)
    elif surface == "anythingllm_api":
        if not api_key:
            http_status, body, text = 0, {"error": {"message": f"{config.api_key_env} missing"}}, ""
        else:
            http_status, body, text = anythingllm_chat(
                config,
                api_key=api_key,
                message=message,
                session_prefix=f"phase239-{case.case_id.lower()}",
            )
    else:
        raise ValueError(f"unsupported surface {surface}")
    parsed_run_id = run_id_from_text(text) if text else None
    run_record = controller_run_record(config, parsed_run_id) if parsed_run_id else None
    status, findings = classify_text(
        case_kind=case.case_kind,
        text=text,
        http_status=http_status,
        policy=policy,
        run_record=run_record,
    )
    if not parsed_run_id:
        status = RemoteClonePriority0ReplayStatus.FAILED.value
        findings.append({"severity": "critical", "code": "missing_run_id", "message": "Response did not include run_id marker."})
    return {
        "case_id": case_id,
        "surface": surface,
        "case_kind": case.case_kind,
        "prompt_family": case.prompt_family,
        "fixture_id": case.fixture_id,
        "status": status,
        "http_status": http_status,
        "parsed_run_id": parsed_run_id,
        "text_length": len(text),
        "text_sample": text[:2400],
        "finding_count": len(findings),
        "findings": findings,
        "run_record_summary": case_summary_from_run_record(run_record),
    }


def run_feedback_case(
    config: RemoteClonePriority0ReplayConfig,
    *,
    policy: dict[str, Any],
    surface: str,
    entries: dict[str, Any],
    api_key: str | None,
) -> dict[str, Any]:
    seed_case = next(case for case in PROMPT_CASES if case.case_id == FEEDBACK_SEED_CASE_ID)
    seed_message = prompt_text(seed_case, entries)
    if surface == "workflow_router_gateway":
        seed_status, _, seed_text = gateway_chat(config, seed_message)
    else:
        if not api_key:
            seed_status, seed_text = 0, ""
        else:
            seed_status, _, seed_text = anythingllm_chat(
                config,
                api_key=api_key,
                message=seed_message,
                session_prefix="phase239-feedback-seed",
            )
    seed_run_id = run_id_from_text(seed_text) if seed_text else None
    feedback_message = (
        f"Record feedback for run {seed_run_id}: useful: inline answer was chat visible and evidence-backed. "
        "missing: none for Phase 239 replay. confusing: none. prompt case: PHASE239-FEEDBACK."
        if seed_run_id
        else "Record feedback: useful: inline answer was chat visible. missing: target run id."
    )
    feedback_case = ReplayPromptCase(
        case_id="FEEDBACK-CAPTURE",
        case_kind="feedback_capture",
        prompt_family="feedback_capture",
        fixture_id="coinbase-frozen-git",
        prompt_template=feedback_message,
    )
    result = run_single_case(
        config,
        policy=policy,
        surface=surface,
        case=feedback_case,
        message=feedback_message,
        api_key=api_key,
    )
    result["seed_http_status"] = seed_status
    result["seed_run_id"] = seed_run_id
    result["target_run_linked"] = False
    if not seed_run_id:
        result["status"] = RemoteClonePriority0ReplayStatus.FAILED.value
        result.setdefault("findings", []).append(
            {"severity": "critical", "code": "missing_feedback_seed_run", "message": "Feedback seed did not produce a run_id."}
        )
    feedback_run_id = result.get("parsed_run_id")
    if isinstance(feedback_run_id, str):
        feedback_record = controller_run_record(config, feedback_run_id)
        artifacts = feedback_record.get("artifacts") if isinstance(feedback_record.get("artifacts"), dict) else {}
        record_path = artifacts.get("feedback_record")
        if isinstance(record_path, str) and Path(record_path).is_file():
            record = read_json(Path(record_path))
            result["feedback_record_summary"] = {
                "target_run_id": record.get("target_run_id"),
                "target_workflow": record.get("target_workflow"),
                "feedback_counts": record.get("feedback_counts"),
                "next_action": record.get("next_action"),
            }
            result["target_run_linked"] = record.get("target_run_id") == seed_run_id
        else:
            result.setdefault("findings", []).append(
                {"severity": "critical", "code": "feedback_record_missing", "message": "Feedback run did not expose feedback_record artifact."}
            )
            result["status"] = RemoteClonePriority0ReplayStatus.FAILED.value
    if result["target_run_linked"] is not True:
        result.setdefault("findings", []).append(
            {"severity": "critical", "code": "feedback_target_not_linked", "message": "Feedback record did not link to seed run."}
        )
        result["status"] = RemoteClonePriority0ReplayStatus.FAILED.value
    result["finding_count"] = len(result.get("findings", []))
    return result


def build_report(
    *,
    policy: dict[str, Any],
    target_settings: dict[str, Any],
    cases: list[dict[str, Any]],
    fixture_before: dict[str, Any],
    fixture_after: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    failed_cases = [case for case in cases if case.get("status") != RemoteClonePriority0ReplayStatus.PASSED.value]
    critical_or_high = [
        finding
        for case in cases
        for finding in case.get("findings", [])
        if isinstance(finding, dict) and finding.get("severity") in {"critical", "high"}
    ]
    required_case_ids = string_list(policy.get("required_case_ids"))
    present_case_ids = {str(case.get("case_id")) for case in cases}
    missing_case_ids = [case_id for case_id in required_case_ids if case_id not in present_case_ids]
    fixture_unchanged = fixture_before == fixture_after
    ready = (
        not errors
        and target_settings.get("status") == RemoteClonePriority0ReplayStatus.PASSED.value
        and not failed_cases
        and not critical_or_high
        and not missing_case_ids
        and fixture_unchanged
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": RemoteClonePriority0ReplayStatus.PASSED.value if ready else RemoteClonePriority0ReplayStatus.FAILED.value,
        "decision": RemoteClonePriority0ReplayDecision.READY.value if ready else RemoteClonePriority0ReplayDecision.BLOCKED.value,
        "generated_at": utc_timestamp(),
        "target_settings": target_settings,
        "cases": cases,
        "fixture_state_before": fixture_before,
        "fixture_state_after": fixture_after,
        "fixture_unchanged": fixture_unchanged,
        "summary": {
            "case_count": len(cases),
            "passed_case_count": len(cases) - len(failed_cases),
            "failed_case_count": len(failed_cases),
            "critical_or_high_finding_count": len(critical_or_high),
            "missing_case_count": len(missing_case_ids),
            "workflow_router_gateway_case_count": sum(1 for case in cases if case.get("surface") == "workflow_router_gateway"),
            "anythingllm_api_case_count": sum(1 for case in cases if case.get("surface") == "anythingllm_api"),
            "target_settings_status": target_settings.get("status"),
            "fixture_unchanged": fixture_unchanged,
        },
        "errors": errors + [f"missing required case {case_id}" for case_id in missing_case_ids],
    }


def validate_report(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("report.schema_version must be 1")
    if report.get("kind") != EXPECTED_REPORT_KIND:
        errors.append(f"report.kind must be {EXPECTED_REPORT_KIND}")
    if report.get("phase") != EXPECTED_PHASE:
        errors.append("report.phase must be 239")
    if report.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"report.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    cases = report.get("cases") if isinstance(report.get("cases"), list) else []
    by_id = {case.get("case_id"): case for case in cases if isinstance(case, dict)}
    for case_id in string_list(policy.get("required_case_ids")):
        case = by_id.get(case_id)
        if not isinstance(case, dict):
            errors.append(f"report missing required case {case_id}")
        elif case.get("status") != RemoteClonePriority0ReplayStatus.PASSED.value:
            errors.append(f"required case {case_id} did not pass")
        elif not case.get("parsed_run_id"):
            errors.append(f"required case {case_id} missing parsed_run_id")
    if report.get("target_settings", {}).get("status") != RemoteClonePriority0ReplayStatus.PASSED.value:
        errors.append("report.target_settings must pass")
    if report.get("fixture_unchanged") is not True:
        errors.append("report.fixture_unchanged must be true")
    rebuilt = build_report(
        policy=policy,
        target_settings=report.get("target_settings") if isinstance(report.get("target_settings"), dict) else {},
        cases=[case for case in cases if isinstance(case, dict)],
        fixture_before=report.get("fixture_state_before") if isinstance(report.get("fixture_state_before"), dict) else {},
        fixture_after=report.get("fixture_state_after") if isinstance(report.get("fixture_state_after"), dict) else {},
        errors=report.get("errors") if isinstance(report.get("errors"), list) else [],
    )
    for key in ("status", "decision", "summary"):
        if report.get(key) != rebuilt.get(key):
            errors.append(f"report.{key} must match rebuilt Phase 239 report")
    if report.get("decision") != policy.get("required_decision"):
        errors.append("report.decision must match policy.required_decision")
    return errors


def run_remote_clone_priority0_chat_quality_replay(config: RemoteClonePriority0ReplayConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy = load_policy(config_root, config.policy_path)
    errors = validate_policy(policy)
    fixture_bundle = load_fixture_entries(config_root, config.fixture_manifest_path)
    entries: dict[str, Any] = fixture_bundle["entries"]
    fixture_ids = string_list(policy.get("fixture_ids"))
    api_key = os.environ.get(config.api_key_env)
    if not api_key:
        errors.append(f"{config.api_key_env} is required for live AnythingLLM replay")
        api_key = None
    fixture_before = fixture_snapshots(entries, fixture_ids)
    target_settings = (
        anythingllm_target_settings(config, api_key=api_key, policy=policy)
        if api_key
        else {"status": RemoteClonePriority0ReplayStatus.FAILED.value, "errors": [f"{config.api_key_env} missing"]}
    )
    cases: list[dict[str, Any]] = []
    for surface in ("workflow_router_gateway", "anythingllm_api"):
        for case in PROMPT_CASES:
            cases.append(
                run_single_case(
                    config,
                    policy=policy,
                    surface=surface,
                    case=case,
                    message=prompt_text(case, entries),
                    api_key=api_key,
                )
            )
        cases.append(
            run_feedback_case(
                config,
                policy=policy,
                surface=surface,
                entries=entries,
                api_key=api_key,
            )
        )
    fixture_after = fixture_snapshots(entries, fixture_ids)
    report = build_report(
        policy=policy,
        target_settings=target_settings,
        cases=cases,
        fixture_before=fixture_before,
        fixture_after=fixture_after,
        errors=errors,
    )
    validation_errors = validate_report(report, policy)
    if validation_errors:
        report["status"] = RemoteClonePriority0ReplayStatus.FAILED.value
        report["decision"] = RemoteClonePriority0ReplayDecision.BLOCKED.value
        report["errors"] = report["errors"] + validation_errors
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    return report
