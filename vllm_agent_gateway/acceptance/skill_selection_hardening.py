"""Runtime skill-selection hardening validation.

Phase 94 treats skill and tool selection as a router contract. This module
validates the governed case catalog, deterministic direct routing, repeated
gateway stability, chat-visible selector evidence, and optional AnythingLLM
round-trips through stored controller run records.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from vllm_agent_gateway.controllers.workflow_router import plan as workflow_router_plan


SCHEMA_VERSION = 1
DEFAULT_CASES_PATH = Path("runtime") / "skill_selection_hardening_cases.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "skill-selection-hardening"
DEFAULT_MODEL_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_CONTROLLER_BASE_URL = "http://127.0.0.1:8400"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_TARGET_ROOTS = (
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
)
WATCHED_RELATIVE_PATHS = (
    "README.md",
    "agent.md",
    "configuration.py",
    "core/stealth_order_manager.py",
    "dashboard_server.py",
    "database/order.py",
    "docs/agents/INVARIANTS.md",
    "tests/unit/test_order_id_and_followup_rules.py",
    "tests/unit/test_orderbook_v2.py",
    "tests/test_dashboard_handler.py",
    "tests/test_lot_tracking_integration.py",
)


class SkillSelectionHardeningStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class SkillSelectionHardeningConfig:
    config_root: Path
    cases_path: Path = DEFAULT_CASES_PATH
    output_path: Path | None = None
    target_roots: tuple[str, ...] = DEFAULT_TARGET_ROOTS
    repeat_count: int | None = None
    include_direct: bool = True
    include_gateway: bool = False
    include_anythingllm: bool = False
    anythingllm_repeat_count: int = 1
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
    return config_root / DEFAULT_REPORT_DIR / f"skill-selection-hardening-{utc_timestamp()}.json"


def resolve_path(config_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else config_root / path


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: int,
) -> tuple[int, dict[str, Any]]:
    request_headers = dict(headers or {})
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = {"error": {"message": text, "code": "invalid_json_error_body"}}
        return exc.code, body


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def check(
    check_id: str,
    status: SkillSelectionHardeningStatus,
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


def text_response(body: dict[str, Any]) -> str:
    for key in ("textResponse", "response", "message"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
    raise RuntimeError("response did not include assistant text")


def run_id_from_text(text: str) -> str:
    marker = "run_id:"
    if marker not in text:
        return "unknown"
    return text.split(marker, 1)[1].strip().split()[0]


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def watched_hashes(target_root: str) -> dict[str, str]:
    root = Path(target_root)
    hashes: dict[str, str] = {}
    for relative_path in WATCHED_RELATIVE_PATHS:
        path = root / relative_path
        if path.exists():
            hashes[relative_path] = digest_file(path)
    if not hashes:
        raise RuntimeError(f"{target_root} did not contain any watched validation files")
    return hashes


def git_status(target_root: str) -> str | None:
    root = Path(target_root)
    if not (root / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", target_root, "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def fixture_state(target_root: str) -> dict[str, Any]:
    return {
        "hashes": watched_hashes(target_root),
        "git_status": git_status(target_root),
    }


def assert_fixture_state_unchanged(before: dict[str, Any], target_root: str, label: str) -> None:
    after = fixture_state(target_root)
    if after != before:
        raise RuntimeError(f"{label} changed protected fixture state for {target_root}")


def validate_catalog(catalog: dict[str, Any], *, cases_path: Path) -> list[dict[str, Any]]:
    errors: list[str] = []
    if catalog.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if catalog.get("kind") != "skill_selection_hardening_cases":
        errors.append("kind must be skill_selection_hardening_cases")
    if catalog.get("phase") != 94:
        errors.append("phase must be 94")
    repeat_count = catalog.get("repeat_count")
    if not isinstance(repeat_count, int) or repeat_count < 2 or repeat_count > 5:
        errors.append("repeat_count must be an integer from 2 through 5")
    cases = catalog.get("cases")
    if not isinstance(cases, list):
        errors.append("cases must be an array")
        cases = []
    if len(cases) < 6:
        errors.append("cases must contain at least six representative prompts")
    case_ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    duplicate_ids = sorted({case_id for case_id in case_ids if isinstance(case_id, str) and case_ids.count(case_id) > 1})
    if duplicate_ids:
        errors.append(f"cases contain duplicate case_id values: {duplicate_ids}")
    statuses = {"ready", "blocked", "unsupported"}
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"cases[{index}] must be an object")
            continue
        prefix = f"cases[{index}]"
        for field in ("case_id", "source", "prompt_family", "prompt_template", "expected_route_status", "mutation_policy"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                errors.append(f"{prefix}.{field} must be a non-empty string")
        if "{target_root}" not in str(case.get("prompt_template", "")):
            errors.append(f"{prefix}.prompt_template must include {{target_root}}")
        if case.get("expected_route_status") not in statuses:
            errors.append(f"{prefix}.expected_route_status must be one of {sorted(statuses)}")
        if not string_list(case.get("required_chat_markers")):
            errors.append(f"{prefix}.required_chat_markers must be a non-empty string array")
        if case.get("expected_route_status") == "ready":
            if not isinstance(case.get("expected_selected_workflow"), str):
                errors.append(f"{prefix}.expected_selected_workflow must be a string for ready cases")
            for field in ("expected_route_rules", "expected_selected_skills", "expected_selected_tools"):
                if not string_list(case.get(field)):
                    errors.append(f"{prefix}.{field} must be a non-empty string array for ready cases")
            if case.get("mutation_policy") != "read_only":
                errors.append(f"{prefix}.mutation_policy must be read_only for ready selector-hardening cases")
        else:
            if case.get("expected_selected_workflow") is not None:
                errors.append(f"{prefix}.expected_selected_workflow must be null for blocked/unsupported cases")
            if not string_list(case.get("expected_blocker_reasons")):
                errors.append(f"{prefix}.expected_blocker_reasons must be non-empty for blocked/unsupported cases")
            if case.get("expected_confidence") != "low":
                errors.append(f"{prefix}.expected_confidence must be low for fail-closed cases")
            if case.get("mutation_policy") != "blocked":
                errors.append(f"{prefix}.mutation_policy must be blocked for fail-closed cases")
    ready_count = sum(1 for case in object_list(cases) if case.get("expected_route_status") == "ready")
    fail_closed_count = sum(1 for case in object_list(cases) if case.get("expected_route_status") in {"blocked", "unsupported"})
    if ready_count < 3:
        errors.append("cases must include at least three ready supported prompts")
    if fail_closed_count < 3:
        errors.append("cases must include at least three fail-closed prompts")
    return [
        check(
            "catalog.contract",
            SkillSelectionHardeningStatus.PASSED if not errors else SkillSelectionHardeningStatus.FAILED,
            "Skill-selection hardening case catalog is valid."
            if not errors
            else "Skill-selection hardening case catalog is invalid.",
            details={
                "cases_path": str(cases_path),
                "case_count": len(cases),
                "ready_count": ready_count,
                "fail_closed_count": fail_closed_count,
                "errors": errors,
            },
            next_action="" if not errors else "Fix runtime/skill_selection_hardening_cases.json before closing Phase 94.",
        )
    ]


def prompt_for_case(case: dict[str, Any], target_root: str) -> str:
    template = str(case["prompt_template"])
    return template.format(target_root=target_root)


def rejected_count(audit: dict[str, Any], key: str) -> int:
    candidates = audit.get(key) if isinstance(audit.get(key), dict) else {}
    value = candidates.get("rejected_count")
    return value if isinstance(value, int) else -1


def selection_signature(decision: dict[str, Any]) -> dict[str, Any]:
    audit = decision.get("selection_audit") if isinstance(decision.get("selection_audit"), dict) else {}
    selected = audit.get("selected") if isinstance(audit.get("selected"), dict) else {}
    blockers = [item.get("reason") for item in object_list(decision.get("blockers")) if isinstance(item.get("reason"), str)]
    return {
        "status": decision.get("status"),
        "selected_workflow": decision.get("selected_workflow"),
        "confidence": decision.get("confidence"),
        "selected_skills": string_list(decision.get("selected_skills")),
        "selected_tools": string_list(decision.get("selected_tools")),
        "route_rules": string_list(selected.get("route_rules")),
        "coverage_entry_ids": string_list(selected.get("coverage_entry_ids")),
        "confidence_reasons": string_list(selected.get("confidence_reasons")),
        "blocker_reasons": blockers,
        "workflow_rejected_count": rejected_count(audit, "workflow_candidates"),
        "skill_rejected_count": rejected_count(audit, "skill_candidates"),
        "tool_rejected_count": rejected_count(audit, "tool_candidates"),
    }


def assert_contains_all(actual: list[str], expected: list[str], label: str) -> None:
    missing = [item for item in expected if item not in actual]
    if missing:
        raise RuntimeError(f"{label} missing expected values: {missing}; actual={actual}")


def assert_decision_matches_case(decision: dict[str, Any], case: dict[str, Any], *, target_root: str, label: str) -> None:
    signature = selection_signature(decision)
    expected_status = case["expected_route_status"]
    if signature["status"] != expected_status:
        raise RuntimeError(f"{label} route status mismatch for {case['case_id']} on {target_root}: {signature}")
    expected_workflow = case.get("expected_selected_workflow")
    if signature["selected_workflow"] != expected_workflow:
        raise RuntimeError(f"{label} workflow mismatch for {case['case_id']} on {target_root}: {signature}")
    audit = decision.get("selection_audit")
    if not isinstance(audit, dict):
        raise RuntimeError(f"{label} missing selection_audit for {case['case_id']} on {target_root}")
    policy = audit.get("selection_policy") if isinstance(audit.get("selection_policy"), dict) else {}
    expected_policy = {
        "metadata_only": True,
        "minimum_confidence": "medium",
        "low_confidence_fails_closed": True,
        "manual_skill_injection_required": False,
    }
    wrong_policy = {
        key: {"expected": value, "actual": policy.get(key)}
        for key, value in expected_policy.items()
        if policy.get(key) != value
    }
    if wrong_policy:
        raise RuntimeError(f"{label} selection policy mismatch for {case['case_id']} on {target_root}: {wrong_policy}")
    if expected_status == "ready":
        assert_contains_all(signature["route_rules"], string_list(case.get("expected_route_rules")), "route_rules")
        assert_contains_all(signature["selected_skills"], string_list(case.get("expected_selected_skills")), "selected_skills")
        assert_contains_all(signature["selected_tools"], string_list(case.get("expected_selected_tools")), "selected_tools")
        if not signature["coverage_entry_ids"]:
            raise RuntimeError(f"{label} did not record prompt-skill coverage entry IDs for {case['case_id']} on {target_root}")
        if "prompt_skill_coverage_match" not in signature["confidence_reasons"]:
            raise RuntimeError(f"{label} did not record coverage confidence reason for {case['case_id']} on {target_root}")
        for count_key in ("workflow_rejected_count", "skill_rejected_count", "tool_rejected_count"):
            if not isinstance(signature[count_key], int) or signature[count_key] < 1:
                raise RuntimeError(f"{label} did not record rejected {count_key} for {case['case_id']} on {target_root}")
    else:
        assert_contains_all(signature["blocker_reasons"], string_list(case.get("expected_blocker_reasons")), "blocker_reasons")
        if signature["confidence"] != case.get("expected_confidence"):
            raise RuntimeError(f"{label} confidence mismatch for {case['case_id']} on {target_root}: {signature}")
        if signature["selected_skills"] or signature["selected_tools"]:
            raise RuntimeError(f"{label} selected skills/tools on fail-closed case {case['case_id']} on {target_root}: {signature}")
        preview = decision.get("controller_request_preview")
        if isinstance(preview, dict) and preview:
            raise RuntimeError(f"{label} fail-closed case produced request preview for {case['case_id']} on {target_root}")


def assert_chat_markers(text: str, case: dict[str, Any], *, target_root: str, label: str) -> None:
    common_markers = [
        "workflow_router.plan",
        "run_id: workflow-router-",
        "Result:",
        "Skill Selection:",
        "- Confidence:",
        "- Rejected candidates:",
    ]
    missing = [
        marker
        for marker in common_markers + string_list(case.get("required_chat_markers"))
        if marker not in text
    ]
    if missing:
        raise RuntimeError(f"{label} missing chat markers for {case['case_id']} on {target_root}: {missing}")


def direct_decision(config: SkillSelectionHardeningConfig, case: dict[str, Any], target_root: str) -> dict[str, Any]:
    request = workflow_router_plan.WorkflowRouterPlanRequest(
        config_root=config.config_root,
        target_root=target_root,
        output_root=config.config_root / DEFAULT_REPORT_DIR / "direct-artifacts",
        user_request=prompt_for_case(case, target_root),
        mode="plan_only",
        budgets={"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
    )
    validation = workflow_router_plan.validate_request_basics(request)
    return workflow_router_plan.route_request(request, validation["budgets"])


def artifact_json(record: dict[str, Any], key: str) -> dict[str, Any]:
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    path = artifacts.get(key)
    if not isinstance(path, str):
        raise RuntimeError(f"run record missing artifact {key}")
    return read_json_object(Path(path))


def gateway_decision(config: SkillSelectionHardeningConfig, case: dict[str, Any], target_root: str) -> tuple[dict[str, Any], str, str]:
    before = fixture_state(target_root)
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": prompt_for_case(case, target_root)}],
            "role_base_url": config.model_base_url,
            "budgets": {"max_model_calls": 3, "max_selected_skills": 5, "max_selected_tools": 5},
        },
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    compact = body.get("agentic_controller_response") if isinstance(body.get("agentic_controller_response"), dict) else {}
    if not compact:
        raise RuntimeError("gateway response did not include agentic_controller_response")
    text = text_response(body)
    assert_chat_markers(text, case, target_root=target_root, label="gateway")
    assert_fixture_state_unchanged(before, target_root, f"gateway {case['case_id']}")
    return artifact_json(compact, "route_decision"), text, str(compact.get("run_id", "unknown"))


def controller_run_record(config: SkillSelectionHardeningConfig, run_id: str) -> dict[str, Any]:
    status, body = json_request(
        f"{config.controller_base_url.rstrip('/')}/v1/controller/runs/{run_id}",
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"controller run lookup returned HTTP {status} for {run_id}: {json.dumps(body, ensure_ascii=True)}")
    return body


def anythingllm_decision(
    config: SkillSelectionHardeningConfig,
    case: dict[str, Any],
    target_root: str,
    *,
    api_key: str,
) -> tuple[dict[str, Any], str, str]:
    before = fixture_state(target_root)
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": prompt_for_case(case, target_root),
            "mode": "chat",
            "sessionId": f"phase94-selection-{case['case_id'].lower()}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    text = text_response(body)
    assert_chat_markers(text, case, target_root=target_root, label="AnythingLLM")
    run_id = run_id_from_text(text)
    if run_id == "unknown":
        raise RuntimeError("AnythingLLM response did not include a workflow-router run_id")
    record = controller_run_record(config, run_id)
    assert_fixture_state_unchanged(before, target_root, f"AnythingLLM {case['case_id']}")
    return artifact_json(record, "route_decision"), text, run_id


CaseRunner = Callable[[SkillSelectionHardeningConfig, dict[str, Any], str], tuple[dict[str, Any], str, str] | dict[str, Any]]


def run_repeated_case(
    config: SkillSelectionHardeningConfig,
    *,
    label: str,
    case: dict[str, Any],
    target_root: str,
    repeat_count: int,
    runner: CaseRunner,
) -> dict[str, Any]:
    signatures: list[dict[str, Any]] = []
    run_ids: list[str] = []
    try:
        for _index in range(repeat_count):
            result = runner(config, case, target_root)
            text = ""
            run_id = "direct"
            if isinstance(result, tuple):
                decision, text, run_id = result
            else:
                decision = result
            assert_decision_matches_case(decision, case, target_root=target_root, label=label)
            if text:
                assert_chat_markers(text, case, target_root=target_root, label=label)
            signatures.append(selection_signature(decision))
            run_ids.append(run_id)
        first = signatures[0]
        unstable = [signature for signature in signatures[1:] if signature != first]
        if unstable:
            raise RuntimeError(f"{label} unstable selection signatures for {case['case_id']} on {target_root}: {unstable}")
        return check(
            f"{label}.{case['case_id']}.{Path(target_root).name}",
            SkillSelectionHardeningStatus.PASSED,
            f"{label} selection was stable for {case['case_id']} on {target_root}.",
            details={
                "case_id": case["case_id"],
                "target_root": target_root,
                "repeat_count": repeat_count,
                "signature": first,
                "run_ids": run_ids,
            },
        )
    except Exception as exc:  # noqa: BLE001 - acceptance reports should classify all case failures
        return check(
            f"{label}.{case.get('case_id', 'unknown')}.{Path(target_root).name}",
            SkillSelectionHardeningStatus.FAILED,
            f"{label} selection hardening failed: {type(exc).__name__}: {exc}",
            details={"case_id": case.get("case_id"), "target_root": target_root, "signatures": signatures, "run_ids": run_ids},
            next_action="Inspect the route-decision artifact, selector audit, and chat response for this case.",
        )


def load_catalog(config_root: Path, cases_path: Path) -> tuple[dict[str, Any], Path]:
    path = resolve_path(config_root, cases_path)
    return read_json_object(path), path


def validate_skill_selection_hardening(config: SkillSelectionHardeningConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "skill_selection_hardening_report",
        "phase": 94,
        "status": SkillSelectionHardeningStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "target_roots": list(config.target_roots),
        "checks": [],
        "summary": {},
    }
    try:
        catalog, cases_path = load_catalog(config_root, config.cases_path)
        report["cases_path"] = str(cases_path)
        checks = validate_catalog(catalog, cases_path=cases_path)
        cases = object_list(catalog.get("cases"))
        repeat_count = config.repeat_count or int(catalog.get("repeat_count", 3))
    except Exception as exc:  # noqa: BLE001
        checks = [
            check(
                "catalog.load",
                SkillSelectionHardeningStatus.FAILED,
                f"Skill-selection hardening input could not be loaded: {type(exc).__name__}: {exc}",
                next_action="Check the case catalog path and JSON syntax.",
            )
        ]
        cases = []
        repeat_count = config.repeat_count or 3
    if config.include_direct:
        for target_root in config.target_roots:
            for case in cases:
                checks.append(
                    run_repeated_case(
                        config,
                        label="direct",
                        case=case,
                        target_root=target_root,
                        repeat_count=repeat_count,
                        runner=direct_decision,
                    )
                )
    if config.include_gateway:
        for target_root in config.target_roots:
            for case in cases:
                checks.append(
                    run_repeated_case(
                        config,
                        label="gateway",
                        case=case,
                        target_root=target_root,
                        repeat_count=repeat_count,
                        runner=gateway_decision,
                    )
                )
    if config.include_anythingllm:
        api_key = os.environ.get(config.api_key_env)
        if not api_key:
            checks.append(
                check(
                    "anythingllm.api_key",
                    SkillSelectionHardeningStatus.FAILED,
                    f"{config.api_key_env} is required for AnythingLLM validation.",
                    next_action=f"Set {config.api_key_env} or rerun with --skip-anythingllm.",
                )
            )
        else:
            def anything_runner(
                runner_config: SkillSelectionHardeningConfig,
                case: dict[str, Any],
                target_root: str,
            ) -> tuple[dict[str, Any], str, str]:
                return anythingllm_decision(runner_config, case, target_root, api_key=api_key)

            for target_root in config.target_roots:
                for case in cases:
                    checks.append(
                        run_repeated_case(
                            config,
                            label="anythingllm",
                            case=case,
                            target_root=target_root,
                            repeat_count=max(1, config.anythingllm_repeat_count),
                            runner=anything_runner,
                        )
                    )
    failed_ids = [item["id"] for item in checks if item.get("status") == SkillSelectionHardeningStatus.FAILED.value]
    report["checks"] = checks
    report["summary"] = {
        "check_count": len(checks),
        "failed_check_ids": failed_ids,
        "case_count": len(cases),
        "target_root_count": len(config.target_roots),
        "repeat_count": repeat_count,
        "direct_enabled": config.include_direct,
        "gateway_enabled": config.include_gateway,
        "anythingllm_enabled": config.include_anythingllm,
    }
    report["status"] = SkillSelectionHardeningStatus.PASSED.value if not failed_ids else SkillSelectionHardeningStatus.FAILED.value
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
