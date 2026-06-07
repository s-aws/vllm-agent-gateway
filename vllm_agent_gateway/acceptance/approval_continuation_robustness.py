"""Phase 97 approval-continuation robustness validation."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable

from vllm_agent_gateway.acceptance.context_retrieval_upgrade import PORT_HEALTH_PROBES
from vllm_agent_gateway.acceptance.implementation_prep_expansion import (
    assert_fixture_state_unchanged,
    controller_run_record,
    fixture_state,
    json_request,
    read_json_object,
    run_id_from_text,
    text_response,
)
from vllm_agent_gateway.controller_service.server import (
    ControllerServiceConfig,
    ControllerServiceError,
    handle_workflow_router_chat_completion,
    load_run_record,
)


SCHEMA_VERSION = 1
DEFAULT_CASES_PATH = Path("runtime") / "approval_continuation_robustness_cases.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "approval-continuation-robustness"
DEFAULT_MODEL_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_CONTROLLER_BASE_URL = "http://127.0.0.1:8400"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_TARGET_ROOTS = (
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
)


class ApprovalContinuationRobustnessStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ApprovalContinuationRobustnessConfig:
    config_root: Path
    cases_path: Path = DEFAULT_CASES_PATH
    output_path: Path | None = None
    target_roots: tuple[str, ...] = DEFAULT_TARGET_ROOTS
    include_direct: bool = True
    include_gateway: bool = False
    include_anythingllm: bool = False
    include_port_health: bool = False
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 900


@dataclass(frozen=True)
class ChatResult:
    status: int
    body: dict[str, Any]
    text: str
    run_id: str
    record: dict[str, Any] | None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"approval-continuation-robustness-{utc_timestamp()}.json"


def resolve_path(config_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else config_root / path


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def check(
    check_id: str,
    status: ApprovalContinuationRobustnessStatus,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    next_action: str = "",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status.value,
        "message": message,
        "details": details or {},
        "next_action": next_action,
    }


def validate_catalog(catalog: dict[str, Any], *, cases_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    if catalog.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if catalog.get("kind") != "approval_continuation_robustness_cases":
        errors.append("kind must be approval_continuation_robustness_cases")
    if catalog.get("phase") != 97:
        errors.append("phase must be 97")
    cases = catalog.get("cases")
    if not isinstance(cases, list) or len(cases) < 4:
        errors.append("cases must contain at least four approval-continuation cases")
        cases = cases if isinstance(cases, list) else []
    required_ids = {"APR-001", "APR-002", "APR-003", "APR-004"}
    case_ids = {case.get("case_id") for case in cases if isinstance(case, dict)}
    missing = sorted(required_ids - {case_id for case_id in case_ids if isinstance(case_id, str)})
    if missing:
        errors.append(f"cases missing required case IDs: {missing}")
    return check(
        "catalog",
        ApprovalContinuationRobustnessStatus.PASSED if not errors else ApprovalContinuationRobustnessStatus.FAILED,
        "Approval continuation case catalog is valid." if not errors else "Approval continuation case catalog is invalid.",
        details={"cases_path": str(cases_path), "case_count": len(cases), "errors": errors},
        next_action="" if not errors else "Fix runtime/approval_continuation_robustness_cases.json.",
    )


def create_direct_fixture(config: ApprovalContinuationRobustnessConfig, label: str) -> str:
    root = config.config_root / DEFAULT_REPORT_DIR / "fixtures" / f"{label}-{uuid.uuid4().hex}"
    write_text(root / "README.md", "# Phase 97 direct fixture\n")
    return str(root)


def initial_prompt(target_root: str, marker: str) -> str:
    return (
        f"In {target_root}, make a small documentation edit to README.md. "
        f"Add a note saying Phase 97 continuation marker {marker}. "
        "Show the proposed edit before applying."
    )


def packet_operations(marker: str) -> list[dict[str, Any]]:
    return [
        {
            "kind": "append_text",
            "path": "README.md",
            "content": f"\n<!-- Phase 97 continuation marker {marker} -->\n",
        }
    ]


def approval_message(run_id: str, operations: list[dict[str, Any]], *, prefix: str = "", suffix: str = "") -> str:
    return (
        f"{prefix}Approve packet design for run {run_id}. "
        f"Use packet operations: {json.dumps(operations, ensure_ascii=True)}{suffix}"
    )


def direct_chat(
    config_root: Path,
    output_root: Path,
    target_root: str,
    message: str,
) -> ChatResult:
    service_config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=(Path(target_root).resolve(),),
        port=0,
    )
    payload = {"model": "agentic-workflow-router", "messages": [{"role": "user", "content": message}]}
    try:
        body = handle_workflow_router_chat_completion(payload, service_config)
    except ControllerServiceError as exc:
        return ChatResult(
            status=int(exc.status),
            body={"error": {"code": exc.code, "message": str(exc)}},
            text=str(exc),
            run_id="unknown",
            record=None,
        )
    text = text_response(body)
    run_id = body.get("agentic_controller_response", {}).get("run_id") if isinstance(body.get("agentic_controller_response"), dict) else None
    if not isinstance(run_id, str):
        run_id = run_id_from_text(text)
    record = load_run_record(service_config, run_id) if run_id != "unknown" else None
    return ChatResult(status=200, body=body, text=text, run_id=run_id, record=record)


def gateway_chat(config: ApprovalContinuationRobustnessConfig, message: str) -> ChatResult:
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": message}],
            "role_base_url": config.model_base_url,
            "budgets": {"max_model_calls": 3, "max_selected_skills": 5, "max_selected_tools": 5},
        },
        timeout_seconds=config.timeout_seconds,
    )
    text = ""
    try:
        text = text_response(body)
    except RuntimeError:
        text = json.dumps(body, ensure_ascii=True)
    run_id = run_id_from_text(text)
    record = controller_run_record(config, run_id) if status == 200 and run_id != "unknown" else None
    return ChatResult(status=status, body=body, text=text, run_id=run_id, record=record)


def anythingllm_chat(
    config: ApprovalContinuationRobustnessConfig,
    message: str,
    *,
    api_key: str,
    session_prefix: str,
) -> ChatResult:
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={"message": message, "mode": "chat", "sessionId": f"{session_prefix}-{uuid.uuid4().hex}"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    text = ""
    try:
        text = text_response(body)
    except RuntimeError:
        text = json.dumps(body, ensure_ascii=True)
    run_id = run_id_from_text(text)
    record = controller_run_record(config, run_id) if status == 200 and run_id != "unknown" else None
    return ChatResult(status=status, body=body, text=text, run_id=run_id, record=record)


def error_code(result: ChatResult) -> str | None:
    error = result.body.get("error") if isinstance(result.body.get("error"), dict) else None
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        return error["code"]
    compact = result.body.get("agentic_controller_response")
    if isinstance(compact, dict):
        summary = compact.get("summary") if isinstance(compact.get("summary"), dict) else {}
        value = summary.get("error_code")
        if isinstance(value, str):
            return value
    known_codes = (
        "approval_already_consumed",
        "approval_denied",
        "approval_expired",
        "approval_not_pending",
        "approval_scope_changed",
    )
    for code in known_codes:
        if code in result.text:
            return code
    return None


def require_success(result: ChatResult, label: str) -> dict[str, Any]:
    if result.status != 200 or result.record is None:
        raise RuntimeError(f"{label} did not return a successful workflow-router response: {result.status} {result.text}")
    return result.record


def require_error(result: ChatResult, expected_code: str, label: str) -> None:
    actual_code = error_code(result)
    if actual_code != expected_code:
        raise RuntimeError(f"{label} expected {expected_code}, got {actual_code}: {result.status} {result.text}")
    if result.status == 200 and "Approval:" not in result.text:
        raise RuntimeError(f"{label} returned HTTP 200 without chat-visible approval failure text")


def artifact_json(record: dict[str, Any], key: str) -> dict[str, Any]:
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    path = artifacts.get(key)
    if not isinstance(path, str):
        raise RuntimeError(f"run record missing artifact {key}")
    return read_json_object(Path(path))


def assert_waiting_initial(result: ChatResult, label: str) -> dict[str, Any]:
    record = require_success(result, label)
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
    if summary.get("approval_state_status") != "waiting_for_approval" or summary.get("approval_type") != "packet_design":
        raise RuntimeError(f"{label} did not enter packet-design approval wait state: {summary}")
    if "Approval:" not in result.text or "waiting_for_approval" not in result.text:
        raise RuntimeError(f"{label} did not expose approval wait state in chat")
    return record


def assert_finished_continuation(result: ChatResult, source_run_id: str, label: str) -> dict[str, Any]:
    record = require_success(result, label)
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
    if summary.get("approval_state_status") != "finished" or summary.get("approval_type") != "packet_design":
        raise RuntimeError(f"{label} did not finish approval continuation: {summary}")
    if summary.get("source_changed") is not False:
        raise RuntimeError(f"{label} did not prove source_changed=false: {summary}")
    if "Approval:" not in result.text or "finished" not in result.text:
        raise RuntimeError(f"{label} did not expose finished approval state in chat")
    downstream_state = artifact_json(record, "downstream_run_state")
    downstream_summary = downstream_state.get("summary") if isinstance(downstream_state.get("summary"), dict) else {}
    if downstream_summary.get("deterministic_path") != "approval_continuation_packet_prep":
        raise RuntimeError(f"{label} did not use deterministic approval continuation path: {downstream_summary}")
    return record


def direct_sender(config: ApprovalContinuationRobustnessConfig, target_root: str) -> Callable[[str], ChatResult]:
    output_root = config.config_root / DEFAULT_REPORT_DIR / "direct-controller-output" / uuid.uuid4().hex
    return lambda message: direct_chat(config.config_root, output_root, target_root, message)


def gateway_sender(config: ApprovalContinuationRobustnessConfig, target_root: str) -> Callable[[str], ChatResult]:
    return lambda message: gateway_chat(config, message)


def anythingllm_sender(
    config: ApprovalContinuationRobustnessConfig,
    target_root: str,
    *,
    api_key: str,
    session_prefix: str,
) -> Callable[[str], ChatResult]:
    return lambda message: anythingllm_chat(config, message, api_key=api_key, session_prefix=session_prefix)


def run_surface_target(
    *,
    config: ApprovalContinuationRobustnessConfig,
    surface: str,
    target_root: str,
    other_target_root: str,
    send: Callable[[str], ChatResult],
) -> dict[str, Any]:
    marker = f"{surface}-{uuid.uuid4().hex[:10]}"
    operations = packet_operations(marker)
    before = fixture_state(target_root)
    initial = send(initial_prompt(target_root, marker))
    initial_record = assert_waiting_initial(initial, f"{surface}.initial")
    continuation = send(approval_message(initial.run_id, operations))
    continuation_record = assert_finished_continuation(continuation, initial.run_id, f"{surface}.continuation")
    duplicate = send(approval_message(initial.run_id, operations))
    require_error(duplicate, "approval_already_consumed", f"{surface}.duplicate")
    wrong_run = send(approval_message(continuation.run_id, operations))
    require_error(wrong_run, "approval_not_pending", f"{surface}.wrong_run")

    denied_initial = send(initial_prompt(target_root, f"{marker}-deny"))
    assert_waiting_initial(denied_initial, f"{surface}.denied_initial")
    denial = send(f"Deny packet design approval for run {denied_initial.run_id}.")
    require_error(denial, "approval_denied", f"{surface}.denial")
    denied_retry = send(approval_message(denied_initial.run_id, operations))
    require_error(denied_retry, "approval_denied", f"{surface}.denied_retry")

    scope_initial = send(initial_prompt(target_root, f"{marker}-scope"))
    assert_waiting_initial(scope_initial, f"{surface}.scope_initial")
    scope_change = send(approval_message(scope_initial.run_id, operations, suffix=" Apply the change to source now."))
    require_error(scope_change, "approval_scope_changed", f"{surface}.scope_change")

    mismatch_initial = send(initial_prompt(target_root, f"{marker}-target"))
    assert_waiting_initial(mismatch_initial, f"{surface}.mismatch_initial")
    target_mismatch = send(approval_message(mismatch_initial.run_id, operations, prefix=f"In {other_target_root}, "))
    require_error(target_mismatch, "approval_scope_changed", f"{surface}.target_mismatch")

    after = assert_fixture_state_unchanged(before, target_root, surface)
    source_registry_status = None
    if continuation_record:
        source_marker = initial_record.get("approval_continuation")
        if isinstance(source_marker, dict):
            source_registry_status = source_marker.get("status")
    return {
        "surface": surface,
        "target_root": target_root,
        "initial_run_id": initial.run_id,
        "continuation_run_id": continuation.run_id,
        "source_registry_status": source_registry_status,
        "duplicate_error": error_code(duplicate),
        "wrong_run_error": error_code(wrong_run),
        "denial_error": error_code(denial),
        "denied_retry_error": error_code(denied_retry),
        "scope_change_error": error_code(scope_change),
        "target_mismatch_error": error_code(target_mismatch),
        "fixture_state_before": before,
        "fixture_state_after": after,
        "fixture_state_unchanged": after == before,
    }


def run_port_health_checks(config: ApprovalContinuationRobustnessConfig) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for check_id, url in PORT_HEALTH_PROBES:
        status, body = json_request(url, timeout_seconds=min(config.timeout_seconds, 30))
        checks.append(
            check(
                f"runtime.{check_id}",
                ApprovalContinuationRobustnessStatus.PASSED if status == 200 else ApprovalContinuationRobustnessStatus.FAILED,
                f"{check_id} returned HTTP {status}.",
                details={"url": url, "status": status, "body": body},
                next_action="" if status == 200 else "Restart the controller/gateway stack before live Phase 97 validation.",
            )
        )
    return checks


def run_approval_continuation_robustness(
    config: ApprovalContinuationRobustnessConfig,
) -> dict[str, Any]:
    cases_path = resolve_path(config.config_root, config.cases_path)
    catalog = read_json_object(cases_path)
    checks = [validate_catalog(catalog, cases_path=cases_path)]
    if config.include_port_health and (config.include_gateway or config.include_anythingllm):
        checks.extend(run_port_health_checks(config))

    details: list[dict[str, Any]] = []
    try:
        if config.include_direct:
            first = create_direct_fixture(config, "direct-a")
            second = create_direct_fixture(config, "direct-b")
            details.append(
                run_surface_target(
                    config=config,
                    surface="direct",
                    target_root=first,
                    other_target_root=second,
                    send=direct_sender(config, first),
                )
            )
            checks.append(
                check(
                    "direct.approval_continuation",
                    ApprovalContinuationRobustnessStatus.PASSED,
                    "Direct controller approval continuation robustness passed.",
                    details=details[-1],
                )
            )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            check(
                "direct.approval_continuation",
                ApprovalContinuationRobustnessStatus.FAILED,
                "Direct controller approval continuation robustness failed.",
                details={"error": f"{type(exc).__name__}: {exc}"},
                next_action="Fix direct approval continuation before live validation.",
            )
        )

    if config.include_gateway:
        for index, target_root in enumerate(config.target_roots):
            other = config.target_roots[(index + 1) % len(config.target_roots)]
            try:
                detail = run_surface_target(
                    config=config,
                    surface=f"gateway.{index + 1}",
                    target_root=target_root,
                    other_target_root=other,
                    send=gateway_sender(config, target_root),
                )
                details.append(detail)
                checks.append(
                    check(
                        f"gateway.{index + 1}",
                        ApprovalContinuationRobustnessStatus.PASSED,
                        f"Gateway approval continuation robustness passed for {target_root}.",
                        details=detail,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                checks.append(
                    check(
                        f"gateway.{index + 1}",
                        ApprovalContinuationRobustnessStatus.FAILED,
                        f"Gateway approval continuation robustness failed for {target_root}.",
                        details={"target_root": target_root, "error": f"{type(exc).__name__}: {exc}"},
                        next_action="Fix live gateway approval continuation before closing Phase 97.",
                    )
                )

    api_key = os.environ.get(config.api_key_env) if config.include_anythingllm else None
    if config.include_anythingllm and not api_key:
        checks.append(
            check(
                "anythingllm.api_key",
                ApprovalContinuationRobustnessStatus.FAILED,
                f"{config.api_key_env} is required for AnythingLLM Phase 97 validation.",
                next_action=f"Set {config.api_key_env} and rerun with --live-anythingllm.",
            )
        )
    if config.include_anythingllm and api_key:
        for index, target_root in enumerate(config.target_roots):
            other = config.target_roots[(index + 1) % len(config.target_roots)]
            try:
                detail = run_surface_target(
                    config=config,
                    surface=f"anythingllm.{index + 1}",
                    target_root=target_root,
                    other_target_root=other,
                    send=anythingllm_sender(
                        config,
                        target_root,
                        api_key=api_key,
                        session_prefix=f"phase97-{index + 1}",
                    ),
                )
                details.append(detail)
                checks.append(
                    check(
                        f"anythingllm.{index + 1}",
                        ApprovalContinuationRobustnessStatus.PASSED,
                        f"AnythingLLM approval continuation robustness passed for {target_root}.",
                        details=detail,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                checks.append(
                    check(
                        f"anythingllm.{index + 1}",
                        ApprovalContinuationRobustnessStatus.FAILED,
                        f"AnythingLLM approval continuation robustness failed for {target_root}.",
                        details={"target_root": target_root, "error": f"{type(exc).__name__}: {exc}"},
                        next_action="Fix AnythingLLM approval continuation before closing Phase 97.",
                    )
                )

    failed = [item for item in checks if item["status"] == ApprovalContinuationRobustnessStatus.FAILED.value]
    report = {
        "kind": "approval_continuation_robustness_report",
        "schema_version": SCHEMA_VERSION,
        "phase": 97,
        "status": ApprovalContinuationRobustnessStatus.FAILED.value
        if failed
        else ApprovalContinuationRobustnessStatus.PASSED.value,
        "summary": {
            "check_count": len(checks),
            "failed_count": len(failed),
            "direct_enabled": config.include_direct,
            "gateway_enabled": config.include_gateway,
            "anythingllm_enabled": config.include_anythingllm,
            "target_roots": list(config.target_roots),
        },
        "checks": checks,
        "run_details": details,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    output_path = config.output_path or default_report_path(config.config_root)
    write_json(resolve_path(config.config_root, output_path), report)
    report["report_path"] = str(resolve_path(config.config_root, output_path))
    return report
