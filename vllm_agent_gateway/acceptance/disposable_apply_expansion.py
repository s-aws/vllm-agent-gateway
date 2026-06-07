"""Phase 98 disposable-copy apply expansion validation."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.context_retrieval_upgrade import PORT_HEALTH_PROBES
from vllm_agent_gateway.acceptance.implementation_prep_expansion import (
    assert_fixture_state_unchanged,
    fixture_state,
    json_request,
    read_json_object,
    run_id_from_text,
    text_response,
    write_json,
    write_text,
)
from vllm_agent_gateway.controller_service.server import chat_completion_response, service_response_from_result
from vllm_agent_gateway.controllers.workflow_router import plan as workflow_router_plan


SCHEMA_VERSION = 1
DEFAULT_CASES_PATH = Path("runtime") / "disposable_apply_expansion_cases.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "disposable-apply-expansion"
DEFAULT_MODEL_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_CONTROLLER_BASE_URL = "http://127.0.0.1:8400"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_TARGET_ROOTS = (
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
)
FROZEN_INVARIANT_OLD = (
    "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n"
    "  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n"
    "  local rows."
)
FROZEN_INVARIANT_NEW = (
    "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n"
    "  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n"
    "  local rows, and stealth manager placed-order index keys."
)


class DisposableApplyExpansionStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class DisposableApplyExpansionConfig:
    config_root: Path
    cases_path: Path = DEFAULT_CASES_PATH
    output_path: Path | None = None
    target_roots: tuple[str, ...] = DEFAULT_TARGET_ROOTS
    case_ids: tuple[str, ...] = ()
    include_direct: bool = True
    include_gateway: bool = False
    include_anythingllm: bool = False
    include_port_health: bool = False
    include_protected_source_refusal: bool = True
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 900


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"disposable-apply-expansion-{utc_timestamp()}.json"


def resolve_path(config_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else config_root / path


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def selected_cases(cases: list[dict[str, Any]], case_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    if not case_ids:
        return cases
    by_id = {str(case.get("case_id")): case for case in cases if isinstance(case.get("case_id"), str)}
    missing = sorted(set(case_ids) - set(by_id))
    if missing:
        raise RuntimeError("unknown disposable apply case id(s): " + ", ".join(missing))
    return [by_id[case_id] for case_id in case_ids]


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def check(
    check_id: str,
    status: DisposableApplyExpansionStatus,
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


def create_direct_fixture(config_root: Path) -> str:
    root = config_root / DEFAULT_REPORT_DIR / "fixtures" / f"direct-{uuid.uuid4().hex}"
    write_text(root / "README.md", "# Phase 98 direct fixture\n\nInstall with Docker.\n")
    write_text(root / "docs" / "guide.md", "# Guide\n\nOriginal guide text.\n")
    write_text(root / "docs" / "agents" / "INVARIANTS.md", FROZEN_INVARIANT_OLD + "\n")
    return str(root)


def append_readme_operation(marker: str) -> dict[str, Any]:
    return {
        "kind": "append_text",
        "path": "README.md",
        "content": f"\n<!-- Phase 98 disposable apply marker {marker} -->\n",
    }


def replace_invariant_operation() -> dict[str, Any]:
    return {
        "kind": "replace_text",
        "path": "docs/agents/INVARIANTS.md",
        "old": FROZEN_INVARIANT_OLD,
        "new": FROZEN_INVARIANT_NEW,
    }


def create_file_operation(marker: str) -> dict[str, Any]:
    return {
        "kind": "create_file",
        "path": f"docs/phase98-created-{marker}.md",
        "content": "# Phase 98 created file\n",
    }


def operations_for_case(case: dict[str, Any], marker: str) -> list[dict[str, Any]]:
    operation_set = case.get("operation_set")
    if operation_set == "append_readme":
        return [append_readme_operation(marker)]
    if operation_set == "multi_replace_invariant_append_readme":
        return [replace_invariant_operation(), append_readme_operation(marker)]
    if operation_set == "create_file_refusal":
        return [create_file_operation(marker)]
    raise RuntimeError(f"Unsupported Phase 98 operation_set: {operation_set!r}")


def disposable_apply_approval() -> dict[str, Any]:
    return {
        "status": "approved_for_disposable_apply",
        "scope": "phase98_disposable_copy_apply",
        "apply_allowed": True,
        "apply_scope": "disposable_copy_only",
        "approval_refs": ["phase98-disposable-copy-apply"],
    }


def real_apply_approval() -> dict[str, Any]:
    return {
        "status": "approved_for_real_apply",
        "scope": "phase98_protected_apply_boundary",
        "apply_allowed": True,
        "apply_scope": "target_root",
        "explicit_real_apply": True,
        "approval_refs": ["phase98-protected-apply-boundary"],
    }


def natural_message(target_root: str, operations: list[dict[str, Any]]) -> str:
    packet_json = json.dumps({"packet_operations": operations}, ensure_ascii=True)
    return (
        f"In {target_root}, approved disposable copy apply only. Apply these exact packet_operations "
        f"to a disposable copy and do not mutate the source repo: {packet_json}"
    )


def direct_chat_body(result: Any) -> tuple[dict[str, Any], str]:
    body = chat_completion_response(
        {"model": "agentic-workflow-router"},
        service_response_from_result(result),
    )
    return body, text_response(body)


def invoke_direct_case(
    config: DisposableApplyExpansionConfig,
    case: dict[str, Any],
    target_root: str,
) -> tuple[dict[str, Any], str, str]:
    marker = f"{case['case_id'].lower()}-{uuid.uuid4().hex}"
    operations = operations_for_case(case, marker)
    output_root = config.config_root / DEFAULT_REPORT_DIR / "direct-artifacts" / case["case_id"].lower()
    request = workflow_router_plan.WorkflowRouterPlanRequest(
        config_root=config.config_root,
        target_root=target_root,
        output_root=output_root,
        user_request="Apply approved exact packet operations only to a disposable copy.",
        mode="apply_disposable_copy",
        approval=disposable_apply_approval(),
        packet_operations=operations,
        budgets={"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
    )
    try:
        result = workflow_router_plan.invoke_workflow_router_plan(request)
    except workflow_router_plan.WorkflowRouterError as exc:
        return {
            "status": "failed",
            "error": {"code": exc.code, "message": str(exc)},
            "operations": operations,
        }, str(exc), "unknown"
    body, text = direct_chat_body(result)
    compact = body.get("agentic_controller_response")
    if not isinstance(compact, dict):
        raise RuntimeError("direct response did not include agentic_controller_response")
    compact["operations"] = operations
    return compact, text, result.run_id


def controller_run_record(config: DisposableApplyExpansionConfig, run_id: str) -> dict[str, Any]:
    status, body = json_request(
        f"{config.controller_base_url.rstrip('/')}/v1/controller/runs/{run_id}",
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"controller run lookup returned HTTP {status} for {run_id}: {json.dumps(body, ensure_ascii=True)}")
    return body


def gateway_chat(
    config: DisposableApplyExpansionConfig,
    target_root: str,
    operations: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, str]:
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": natural_message(target_root, operations)}],
            "role_base_url": config.model_base_url,
            "budgets": {"max_model_calls": 3, "max_selected_skills": 5, "max_selected_tools": 5},
        },
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    run_id = run_id_from_text(text)
    if run_id == "unknown":
        raise RuntimeError("gateway response did not include a workflow-router run_id")
    return controller_run_record(config, run_id), text, run_id


def anythingllm_chat(
    config: DisposableApplyExpansionConfig,
    target_root: str,
    operations: list[dict[str, Any]],
    *,
    api_key: str,
) -> tuple[dict[str, Any], str, str]:
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": natural_message(target_root, operations),
            "mode": "chat",
            "sessionId": f"phase98-disposable-apply-{uuid.uuid4().hex}",
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
    return controller_run_record(config, run_id), text, run_id


def artifact_json(record: dict[str, Any], key: str) -> dict[str, Any]:
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    path_value = artifacts.get(key)
    if not isinstance(path_value, str):
        raise RuntimeError(f"run record missing artifact {key}")
    return read_json_object(Path(path_value))


def assert_chat_markers(text: str, case: dict[str, Any], label: str) -> None:
    if case.get("expected_status") != "applied":
        return
    expected_paths = string_list(case.get("expected_paths"))
    required = [
        "workflow_router.plan completed",
        "- downstream_workflow: implementation.workflow",
        "- source_changed: False",
        "- source_tree_changed: False",
        "- disposable_copy_changed: True",
        f"- mutation_diff_file_count: {case.get('expected_changed_file_count')}",
        "- mutation_rollback_status: restored",
        "Disposable Apply:",
        f"- Changed files: {case.get('expected_changed_file_count')}",
    ] + expected_paths
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise RuntimeError(f"{label} missing Phase 98 chat markers for {case['case_id']}: {missing}")


def assert_applied_record(
    record: dict[str, Any],
    case: dict[str, Any],
    text: str,
    label: str,
) -> dict[str, Any]:
    assert_chat_markers(text, case, label)
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
    expected_count = case.get("expected_changed_file_count")
    expected_paths = string_list(case.get("expected_paths"))
    expected_kinds = string_list(case.get("expected_operation_kinds"))
    expected_summary = {
        "downstream_workflow": "implementation.workflow",
        "source_changed": False,
        "source_tree_changed": False,
        "disposable_copy_changed": True,
        "copy_tree_restored": True,
        "mutation_diff_file_count": expected_count,
        "mutation_rollback_status": "restored",
        "approval_type": "disposable_copy_apply",
    }
    mismatches = {
        key: {"expected": value, "actual": summary.get(key)}
        for key, value in expected_summary.items()
        if summary.get(key) != value
    }
    if mismatches:
        raise RuntimeError(f"{label} summary mismatch for {case['case_id']}: {json.dumps(mismatches, sort_keys=True)}")
    if sorted(summary.get("mutation_diff_paths", [])) != sorted(expected_paths):
        raise RuntimeError(f"{label} mutation_diff_paths mismatch: {summary.get('mutation_diff_paths')}")
    proof = artifact_json(record, "disposable_mutation_proof")
    if proof.get("source_changed") != {} or proof.get("source_tree_changed") is not False:
        raise RuntimeError(f"{label} source mutation proof failed: {json.dumps(proof, ensure_ascii=True)[:1000]}")
    if proof.get("copy_tree_restored") is not True:
        raise RuntimeError(f"{label} copy tree was not restored")
    structured = proof.get("structured_diff") if isinstance(proof.get("structured_diff"), dict) else {}
    if structured.get("changed_file_count") != expected_count:
        raise RuntimeError(f"{label} structured diff count mismatch: {structured.get('changed_file_count')}")
    records = object_list(structured.get("records"))
    record_paths = [record.get("path") for record in records]
    if sorted(record_paths) != sorted(expected_paths):
        raise RuntimeError(f"{label} structured diff paths mismatch: {record_paths}")
    record_kinds = [record.get("operation_kind") for record in records]
    if record_kinds != expected_kinds:
        raise RuntimeError(f"{label} operation kind mismatch: {record_kinds}")
    rollback = proof.get("rollback") if isinstance(proof.get("rollback"), dict) else {}
    if rollback.get("status") != "restored":
        raise RuntimeError(f"{label} rollback status mismatch: {rollback.get('status')}")
    copy_root = Path(str(proof.get("disposable_copy_root")))
    source_root = Path(str(proof.get("source_root")))
    for path_value in expected_paths:
        source_file = source_root / path_value
        copy_file = copy_root / path_value
        if source_file.exists() and copy_file.exists() and source_file.read_bytes() != copy_file.read_bytes():
            raise RuntimeError(f"{label} rollback did not restore {path_value}")
    return proof


def assert_blocked_record(record: dict[str, Any], case: dict[str, Any], label: str) -> dict[str, Any]:
    error = record.get("error") if isinstance(record.get("error"), dict) else {}
    expected_code = case.get("expected_error_code")
    if error:
        if error.get("code") != expected_code:
            raise RuntimeError(f"{label} expected error {expected_code}, got {error}")
        return {"error_code": error.get("code"), "message": error.get("message")}
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
    if summary.get("route_status") != "blocked":
        raise RuntimeError(f"{label} expected blocked route, got summary {summary}")
    decision = artifact_json(record, "route_decision")
    blockers = object_list(decision.get("blockers"))
    reasons = [blocker.get("reason") for blocker in blockers]
    if expected_code not in reasons:
        raise RuntimeError(f"{label} expected blocker {expected_code}, got {reasons}")
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    if "disposable_mutation_proof" in artifacts:
        raise RuntimeError(f"{label} blocked route unexpectedly wrote disposable mutation proof")
    return {"error_code": expected_code, "blockers": reasons}


def run_case_check(
    *,
    config: DisposableApplyExpansionConfig,
    label: str,
    case: dict[str, Any],
    target_root: str,
    runner: Any,
) -> dict[str, Any]:
    before = fixture_state(target_root)
    try:
        record, text, run_id = runner()
        after = assert_fixture_state_unchanged(before, target_root, f"{label} {case['case_id']}")
        if case.get("expected_status") == "applied":
            proof = assert_applied_record(record, case, text, label)
            details = {
                "case_id": case["case_id"],
                "target_root": target_root,
                "surface": label,
                "run_id": run_id,
                "changed_file_count": proof.get("structured_diff", {}).get("changed_file_count"),
                "source_tree_changed": proof.get("source_tree_changed"),
                "copy_tree_restored": proof.get("copy_tree_restored"),
                "fixture_state_unchanged": before == after,
                "chat_excerpt": text[:2000],
            }
        else:
            blocked = assert_blocked_record(record, case, label)
            details = {
                "case_id": case["case_id"],
                "target_root": target_root,
                "surface": label,
                "run_id": run_id,
                "blocked": blocked,
                "fixture_state_unchanged": before == after,
            }
        return check(
            f"{label}.{case['case_id']}.{Path(target_root).name}",
            DisposableApplyExpansionStatus.PASSED,
            f"{label} Phase 98 case passed for {case['case_id']} on {target_root}.",
            details=details,
        )
    except Exception as exc:  # noqa: BLE001 - acceptance reports classify all failures
        return check(
            f"{label}.{case.get('case_id', 'unknown')}.{Path(target_root).name}",
            DisposableApplyExpansionStatus.FAILED,
            f"{label} Phase 98 case failed: {type(exc).__name__}: {exc}",
            details={"case_id": case.get("case_id"), "target_root": target_root},
            next_action="Inspect route_decision, disposable mutation proof, rollback proof, chat text, and fixture state.",
        )


def protected_source_apply_refusal_check(config: DisposableApplyExpansionConfig, target_root: str) -> dict[str, Any]:
    before = fixture_state(target_root)
    try:
        status, body = json_request(
            f"{config.controller_base_url.rstrip('/')}/v1/controller/implementation-runs",
            payload={
                "workflow": "implementation.workflow",
                "schema_version": 1,
                "target_root": target_root,
                "mode": "apply",
                "approval": real_apply_approval(),
                "packet_operations": [replace_invariant_operation()],
                "no_structure_index": True,
            },
            timeout_seconds=config.timeout_seconds,
        )
        if status != 403:
            raise RuntimeError(f"expected HTTP 403, got {status}: {json.dumps(body, ensure_ascii=True)}")
        error = body.get("error") if isinstance(body.get("error"), dict) else {}
        if error.get("code") != "protected_frozen_real_apply_denied":
            raise RuntimeError(f"unexpected error code: {error}")
        after = assert_fixture_state_unchanged(before, target_root, "protected source apply refusal")
        return check(
            f"protected_source_apply_refusal.{Path(target_root).name}",
            DisposableApplyExpansionStatus.PASSED,
            f"Real source apply remained blocked for {target_root}.",
            details={"target_root": target_root, "http_status": status, "fixture_state_unchanged": before == after},
        )
    except Exception as exc:  # noqa: BLE001
        return check(
            f"protected_source_apply_refusal.{Path(target_root).name}",
            DisposableApplyExpansionStatus.FAILED,
            f"Protected source apply refusal failed: {type(exc).__name__}: {exc}",
            details={"target_root": target_root},
            next_action="Verify protected frozen-root policy and implementation apply approval handling.",
        )


def runtime_surface_checks(config: DisposableApplyExpansionConfig, api_key: str | None) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for label, url in PORT_HEALTH_PROBES:
        try:
            status, body = json_request(url, timeout_seconds=min(config.timeout_seconds, 30))
            passed = status == 200
            checks.append(
                check(
                    f"runtime.{label}",
                    DisposableApplyExpansionStatus.PASSED if passed else DisposableApplyExpansionStatus.FAILED,
                    f"Runtime surface {label} is reachable." if passed else f"Runtime surface {label} failed.",
                    details={"url": url, "http_status": status, "body_keys": sorted(body) if isinstance(body, dict) else []},
                    next_action="" if passed else "Restart the Bash-hosted controller/gateway stack and rerun validation.",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                check(
                    f"runtime.{label}",
                    DisposableApplyExpansionStatus.FAILED,
                    f"Runtime surface {label} failed: {type(exc).__name__}: {exc}",
                    details={"url": url},
                    next_action="Restart the Bash-hosted controller/gateway stack and rerun validation.",
                )
            )
    if config.include_anythingllm:
        checks.append(
            check(
                "runtime.anythingllm_api_key",
                DisposableApplyExpansionStatus.PASSED if api_key else DisposableApplyExpansionStatus.FAILED,
                f"{config.api_key_env} is available." if api_key else f"{config.api_key_env} is not set.",
                next_action="" if api_key else "Export the AnythingLLM API key before live AnythingLLM validation.",
            )
        )
    return checks


def validate_catalog(catalog: dict[str, Any], *, cases_path: Path) -> list[dict[str, Any]]:
    errors: list[str] = []
    if catalog.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if catalog.get("kind") != "disposable_apply_expansion_cases":
        errors.append("kind must be disposable_apply_expansion_cases")
    if catalog.get("phase") != 98:
        errors.append("phase must be 98")
    cases = object_list(catalog.get("cases"))
    if len(cases) < 3:
        errors.append("cases must include at least three Phase 98 cases")
    required_ids = {"DAE-001", "DAE-002", "DAE-003"}
    case_ids = {case.get("case_id") for case in cases if isinstance(case.get("case_id"), str)}
    missing = sorted(required_ids - case_ids)
    if missing:
        errors.append(f"cases missing required IDs: {missing}")
    for case in cases:
        for key in ("case_id", "operation_set", "expected_status", "mutation_policy"):
            if not isinstance(case.get(key), str) or not case.get(key):
                errors.append(f"{case.get('case_id', '<missing>')}.{key} must be a non-empty string")
        if case.get("expected_status") == "applied":
            if not isinstance(case.get("expected_changed_file_count"), int):
                errors.append(f"{case.get('case_id')}.expected_changed_file_count must be an integer")
            if not string_list(case.get("expected_paths")):
                errors.append(f"{case.get('case_id')}.expected_paths must be a non-empty string list")
            if not string_list(case.get("expected_operation_kinds")):
                errors.append(f"{case.get('case_id')}.expected_operation_kinds must be a non-empty string list")
        elif case.get("expected_status") == "blocked":
            if not isinstance(case.get("expected_error_code"), str):
                errors.append(f"{case.get('case_id')}.expected_error_code must be a string")
        else:
            errors.append(f"{case.get('case_id')}.expected_status must be applied or blocked")
    return [
        check(
            "catalog.contract",
            DisposableApplyExpansionStatus.FAILED if errors else DisposableApplyExpansionStatus.PASSED,
            "Disposable apply expansion case catalog is valid." if not errors else "Catalog validation failed.",
            details={"cases_path": str(cases_path), "case_count": len(cases), "errors": errors},
            next_action="" if not errors else "Fix runtime/disposable_apply_expansion_cases.json.",
        )
    ]


def validate_disposable_apply_expansion(config: DisposableApplyExpansionConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    cases_path = resolve_path(config_root, config.cases_path)
    output_path = config.output_path or default_report_path(config_root)
    catalog = read_json_object(cases_path)
    all_cases = object_list(catalog.get("cases"))
    cases = selected_cases(all_cases, config.case_ids)
    live_cases = [case for case in cases if case.get("live") is True and case.get("expected_status") == "applied"]
    direct_target = create_direct_fixture(config_root)
    checks: list[dict[str, Any]] = []
    api_key = os.environ.get(config.api_key_env) if config.include_anythingllm else None
    checks.extend(validate_catalog(catalog, cases_path=cases_path))
    if config.include_port_health or config.include_gateway or config.include_anythingllm:
        checks.extend(runtime_surface_checks(config, api_key))
    if config.include_direct:
        for case in cases:
            checks.append(
                run_case_check(
                    config=config,
                    label="direct",
                    case=case,
                    target_root=direct_target,
                    runner=lambda case=case: invoke_direct_case(config, case, direct_target),
                )
            )
    if config.include_gateway:
        for target_root in config.target_roots:
            if config.include_protected_source_refusal:
                checks.append(protected_source_apply_refusal_check(config, target_root))
            for case in live_cases:
                marker = f"{case['case_id'].lower()}-{uuid.uuid4().hex}"
                operations = operations_for_case(case, marker)
                checks.append(
                    run_case_check(
                        config=config,
                        label="gateway",
                        case=case,
                        target_root=target_root,
                        runner=lambda target_root=target_root, operations=operations: gateway_chat(
                            config,
                            target_root,
                            operations,
                        ),
                    )
                )
    if config.include_anythingllm and api_key:
        for target_root in config.target_roots:
            if config.include_protected_source_refusal:
                checks.append(protected_source_apply_refusal_check(config, target_root))
            for case in live_cases:
                marker = f"{case['case_id'].lower()}-{uuid.uuid4().hex}"
                operations = operations_for_case(case, marker)
                checks.append(
                    run_case_check(
                        config=config,
                        label="AnythingLLM",
                        case=case,
                        target_root=target_root,
                        runner=lambda target_root=target_root, operations=operations: anythingllm_chat(
                            config,
                            target_root,
                            operations,
                            api_key=api_key,
                        ),
                    )
                )
    failed = [item for item in checks if item["status"] == DisposableApplyExpansionStatus.FAILED.value]
    report = {
        "kind": "disposable_apply_expansion_report",
        "schema_version": SCHEMA_VERSION,
        "phase": 98,
        "status": "failed" if failed else "passed",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "config_root": str(config_root),
        "cases_path": str(cases_path),
        "report_path": str(output_path),
        "target_roots": list(config.target_roots),
        "selected_case_ids": [str(case.get("case_id")) for case in cases],
        "generated_fixtures": {"direct": direct_target},
        "checks": checks,
        "summary": {
            "case_count": len(cases),
            "live_case_count": len(live_cases),
            "check_count": len(checks),
            "failed_check_ids": [item["id"] for item in failed],
            "direct_enabled": config.include_direct,
            "gateway_enabled": config.include_gateway,
            "anythingllm_enabled": config.include_anythingllm,
            "port_health_enabled": config.include_port_health,
            "protected_source_refusal_enabled": config.include_protected_source_refusal,
        },
    }
    write_json(output_path, report)
    return report
