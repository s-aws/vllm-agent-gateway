"""Phase 95 context-retrieval upgrade validation."""

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
DEFAULT_CASES_PATH = Path("runtime") / "context_retrieval_upgrade_cases.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "context-retrieval-upgrade"
DEFAULT_MODEL_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_LLM_GATEWAY_BASE_URL = "http://127.0.0.1:8300/v1"
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
    "tests/regression/test_order_id_regression.py",
)
PORT_HEALTH_PROBES = (
    ("localhost-model", "http://127.0.0.1:8000/v1/models"),
    ("llm-gateway", "http://127.0.0.1:8300/v1/models"),
    ("controller", "http://127.0.0.1:8400/health"),
    ("workflow-router-gateway", "http://127.0.0.1:8500/v1/models"),
    ("reviewer-code", "http://127.0.0.1:8101/v1/models"),
    ("tester-code", "http://127.0.0.1:8102/v1/models"),
    ("architect-default", "http://127.0.0.1:8201/v1/models"),
    ("dispatcher-default", "http://127.0.0.1:8202/v1/models"),
    ("implementer-default", "http://127.0.0.1:8203/v1/models"),
    ("researcher-default", "http://127.0.0.1:8204/v1/models"),
    ("documenter-default", "http://127.0.0.1:8205/v1/models"),
)


class ContextRetrievalUpgradeStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ContextRetrievalUpgradeConfig:
    config_root: Path
    cases_path: Path = DEFAULT_CASES_PATH
    output_path: Path | None = None
    target_roots: tuple[str, ...] = DEFAULT_TARGET_ROOTS
    include_direct: bool = True
    include_gateway: bool = False
    include_anythingllm: bool = False
    include_port_health: bool = False
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    llm_gateway_base_url: str = DEFAULT_LLM_GATEWAY_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 900


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"context-retrieval-upgrade-{utc_timestamp()}.json"


def resolve_path(config_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else config_root / path


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


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
    status: ContextRetrievalUpgradeStatus,
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
    return {"hashes": watched_hashes(target_root), "git_status": git_status(target_root)}


def assert_fixture_state_unchanged(before: dict[str, Any] | None, target_root: str, label: str) -> None:
    if before is None:
        return
    after = fixture_state(target_root)
    if after != before:
        raise RuntimeError(f"{label} changed protected fixture state for {target_root}")


def is_protected_target(config: ContextRetrievalUpgradeConfig, target_root: str) -> bool:
    resolved = str(Path(target_root).resolve())
    return any(str(Path(root).resolve()) == resolved for root in config.target_roots)


def protected_fixture_state(config: ContextRetrievalUpgradeConfig, target_root: str) -> dict[str, Any] | None:
    if not is_protected_target(config, target_root):
        return None
    return fixture_state(target_root)


def create_non_coinbase_fixture(config: ContextRetrievalUpgradeConfig) -> str:
    root = config.config_root / DEFAULT_REPORT_DIR / "fixtures" / f"non-coinbase-{utc_timestamp()}"
    write_text(
        root / "src" / "handlers" / "signup.py",
        "import os\n\n"
        "FEATURE_FLAG_ENABLED = os.getenv('FEATURE_FLAG_ENABLED', 'false')\n\n"
        "def handle_signup(payload):\n"
        "    if FEATURE_FLAG_ENABLED == 'true':\n"
        "        return {'mode': 'flagged', 'email': payload['email']}\n"
        "    return {'mode': 'default', 'email': payload['email']}\n",
    )
    write_text(
        root / "src" / "routes.py",
        "from handlers.signup import handle_signup\n\n"
        "def register_routes(app):\n"
        "    app.post('/signup', handle_signup)\n",
    )
    write_text(
        root / "tests" / "test_signup.py",
        "from src.handlers.signup import handle_signup\n\n"
        "def test_handle_signup_default_mode():\n"
        "    assert handle_signup({'email': 'a@example.com'})['mode'] == 'default'\n",
    )
    write_text(root / ".env.example", "FEATURE_FLAG_ENABLED=false\n")
    write_text(root / "README.md", "# Non-Coinbase context fixture\n")
    return str(root)


def create_unsupported_fixture(config: ContextRetrievalUpgradeConfig) -> str:
    root = config.config_root / DEFAULT_REPORT_DIR / "fixtures" / f"unsupported-empty-{utc_timestamp()}"
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


def validate_catalog(catalog: dict[str, Any], *, cases_path: Path) -> list[dict[str, Any]]:
    errors: list[str] = []
    if catalog.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if catalog.get("kind") != "context_retrieval_upgrade_cases":
        errors.append("kind must be context_retrieval_upgrade_cases")
    if catalog.get("phase") != 95:
        errors.append("phase must be 95")
    cases = catalog.get("cases")
    if not isinstance(cases, list):
        errors.append("cases must be an array")
        cases = []
    if len(cases) < 5:
        errors.append("cases must contain at least five representative prompts")
    case_ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    duplicate_ids = sorted({case_id for case_id in case_ids if isinstance(case_id, str) and case_ids.count(case_id) > 1})
    if duplicate_ids:
        errors.append(f"cases contain duplicate case_id values: {duplicate_ids}")
    profiles = {"coinbase", "non_coinbase", "unsupported_empty"}
    statuses = {"ready", "blocked", "unsupported"}
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"cases[{index}] must be an object")
            continue
        prefix = f"cases[{index}]"
        for field in ("case_id", "fixture_profile", "prompt_family", "prompt_template", "expected_route_status"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                errors.append(f"{prefix}.{field} must be a non-empty string")
        if case.get("fixture_profile") not in profiles:
            errors.append(f"{prefix}.fixture_profile must be one of {sorted(profiles)}")
        if "{target_root}" not in str(case.get("prompt_template", "")):
            errors.append(f"{prefix}.prompt_template must include {{target_root}}")
        if case.get("expected_route_status") not in statuses:
            errors.append(f"{prefix}.expected_route_status must be one of {sorted(statuses)}")
        if not string_list(case.get("expected_context_sources")):
            errors.append(f"{prefix}.expected_context_sources must be a non-empty string array")
        if not isinstance(case.get("expected_selected_workflow"), str):
            errors.append(f"{prefix}.expected_selected_workflow must be a string")
        if not string_list(case.get("expected_route_rules")):
            errors.append(f"{prefix}.expected_route_rules must be a non-empty string array")
        if not isinstance(case.get("expected_layout_status"), str):
            errors.append(f"{prefix}.expected_layout_status must be a string")
        if case.get("expected_route_status") == "ready":
            if not string_list(case.get("expected_downstream_artifacts")):
                errors.append(f"{prefix}.expected_downstream_artifacts must be non-empty for ready cases")
        else:
            if not string_list(case.get("expected_blocker_reasons")):
                errors.append(f"{prefix}.expected_blocker_reasons must be non-empty for fail-closed cases")
    return [
        check(
            "catalog.contract",
            ContextRetrievalUpgradeStatus.PASSED if not errors else ContextRetrievalUpgradeStatus.FAILED,
            "Context-retrieval upgrade case catalog is valid."
            if not errors
            else "Context-retrieval upgrade case catalog is invalid.",
            details={"cases_path": str(cases_path), "case_count": len(cases), "errors": errors},
            next_action="" if not errors else "Fix runtime/context_retrieval_upgrade_cases.json before closing Phase 95.",
        )
    ]


def prompt_for_case(case: dict[str, Any], target_root: str) -> str:
    return str(case["prompt_template"]).format(target_root=target_root)


def targets_for_case(
    config: ContextRetrievalUpgradeConfig,
    case: dict[str, Any],
    *,
    non_coinbase_target: str,
    unsupported_target: str,
) -> tuple[str, ...]:
    profile = case.get("fixture_profile")
    if profile == "coinbase":
        return config.target_roots
    if profile == "non_coinbase":
        return (non_coinbase_target,)
    if profile == "unsupported_empty":
        return (unsupported_target,)
    return ()


def assert_contains_all(actual: list[str], expected: list[str], label: str) -> None:
    missing = [item for item in expected if item not in actual]
    if missing:
        raise RuntimeError(f"{label} missing expected values: {missing}; actual={actual}")


def route_rules_from_decision(decision: dict[str, Any]) -> list[str]:
    audit = decision.get("selection_audit") if isinstance(decision.get("selection_audit"), dict) else {}
    selected = audit.get("selected") if isinstance(audit.get("selected"), dict) else {}
    return string_list(selected.get("route_rules"))


def blocker_reasons(decision: dict[str, Any]) -> list[str]:
    return [item["reason"] for item in object_list(decision.get("blockers")) if isinstance(item.get("reason"), str)]


def assert_context_audit(decision: dict[str, Any], case: dict[str, Any], *, target_root: str, label: str) -> None:
    audit = decision.get("context_source_audit")
    if not isinstance(audit, dict):
        raise RuntimeError(f"{label} missing context_source_audit for {case['case_id']} on {target_root}")
    policy = audit.get("selection_policy") if isinstance(audit.get("selection_policy"), dict) else {}
    expected_policy = {
        "metadata_only": True,
        "manual_tool_request_required": False,
        "unsupported_layout_fails_closed": True,
    }
    wrong_policy = {key: policy.get(key) for key, value in expected_policy.items() if policy.get(key) != value}
    if wrong_policy:
        raise RuntimeError(f"{label} context-source policy mismatch for {case['case_id']}: {wrong_policy}")
    selected_ids = string_list(audit.get("selected_source_ids"))
    assert_contains_all(selected_ids, string_list(case.get("expected_context_sources")), "context_source_ids")
    selected = object_list(audit.get("selected"))
    rejected = object_list(audit.get("rejected"))
    if not selected:
        raise RuntimeError(f"{label} did not record selected context sources for {case['case_id']}")
    if not rejected:
        raise RuntimeError(f"{label} did not record rejected context sources for {case['case_id']}")
    for source in selected:
        for key in ("source_id", "tool_ids", "artifact_keys", "budget", "reasons"):
            if key not in source:
                raise RuntimeError(f"{label} selected context source missing {key}: {source}")
    layout = audit.get("layout") if isinstance(audit.get("layout"), dict) else {}
    if layout.get("status") != case.get("expected_layout_status"):
        raise RuntimeError(
            f"{label} layout status mismatch for {case['case_id']} on {target_root}: "
            f"expected {case.get('expected_layout_status')} actual {layout.get('status')}"
        )
    budget = audit.get("budget") if isinstance(audit.get("budget"), dict) else {}
    if budget.get("max_selected_sources") != 5:
        raise RuntimeError(f"{label} did not record bounded context source budget for {case['case_id']}")
    if case.get("expected_route_status") == "ready" and not string_list(audit.get("evidence_files")):
        raise RuntimeError(f"{label} ready case did not record evidence file samples for {case['case_id']}")
    preview = decision.get("controller_request_preview")
    if isinstance(preview, dict) and preview:
        assert_contains_all(string_list(preview.get("context_sources")), selected_ids, "preview.context_sources")


def assert_decision_matches_case(decision: dict[str, Any], case: dict[str, Any], *, target_root: str, label: str) -> None:
    if decision.get("status") != case.get("expected_route_status"):
        raise RuntimeError(f"{label} route status mismatch for {case['case_id']} on {target_root}: {decision.get('status')}")
    if decision.get("selected_workflow") != case.get("expected_selected_workflow"):
        raise RuntimeError(f"{label} workflow mismatch for {case['case_id']} on {target_root}: {decision.get('selected_workflow')}")
    assert_contains_all(route_rules_from_decision(decision), string_list(case.get("expected_route_rules")), "route_rules")
    assert_context_audit(decision, case, target_root=target_root, label=label)
    if case.get("expected_route_status") == "ready":
        preview = decision.get("controller_request_preview")
        if not isinstance(preview, dict) or not preview:
            raise RuntimeError(f"{label} ready case did not produce controller_request_preview for {case['case_id']}")
    else:
        assert_contains_all(blocker_reasons(decision), string_list(case.get("expected_blocker_reasons")), "blocker_reasons")
        preview = decision.get("controller_request_preview")
        if isinstance(preview, dict) and preview:
            raise RuntimeError(f"{label} blocked case produced request preview for {case['case_id']}")


def direct_decision(config: ContextRetrievalUpgradeConfig, case: dict[str, Any], target_root: str) -> dict[str, Any]:
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


def assert_chat_markers(text: str, case: dict[str, Any], *, target_root: str, label: str) -> None:
    common_markers = ["workflow_router.plan", "run_id: workflow-router-", "Result:", "Context Sources:"]
    missing = [
        marker
        for marker in common_markers + string_list(case.get("required_chat_markers"))
        if marker not in text
    ]
    if missing:
        raise RuntimeError(f"{label} missing chat markers for {case['case_id']} on {target_root}: {missing}")


def artifact_json(record: dict[str, Any], key: str) -> dict[str, Any]:
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    path = artifacts.get(key)
    if not isinstance(path, str):
        raise RuntimeError(f"run record missing artifact {key}")
    return read_json_object(Path(path))


def controller_run_record(config: ContextRetrievalUpgradeConfig, run_id: str) -> dict[str, Any]:
    status, body = json_request(
        f"{config.controller_base_url.rstrip('/')}/v1/controller/runs/{run_id}",
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"controller run lookup returned HTTP {status} for {run_id}: {json.dumps(body, ensure_ascii=True)}")
    return body


def assert_live_record_matches_case(record: dict[str, Any], case: dict[str, Any], *, target_root: str, label: str) -> dict[str, Any]:
    decision = artifact_json(record, "route_decision")
    assert_decision_matches_case(decision, case, target_root=target_root, label=label)
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    if "context_source_audit" not in artifacts:
        raise RuntimeError(f"{label} did not expose context_source_audit artifact for {case['case_id']}")
    if case.get("expected_route_status") == "ready":
        missing = [
            artifact_key
            for artifact_key in string_list(case.get("expected_downstream_artifacts"))
            if artifact_key not in artifacts
        ]
        if missing:
            raise RuntimeError(f"{label} missing downstream artifacts for {case['case_id']}: {missing}")
    return decision


def gateway_decision(config: ContextRetrievalUpgradeConfig, case: dict[str, Any], target_root: str) -> tuple[dict[str, Any], str, str]:
    before = protected_fixture_state(config, target_root)
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
    text = text_response(body)
    assert_chat_markers(text, case, target_root=target_root, label="gateway")
    run_id = run_id_from_text(text)
    if run_id == "unknown":
        raise RuntimeError("gateway response did not include a workflow-router run_id")
    record = controller_run_record(config, run_id)
    decision = assert_live_record_matches_case(record, case, target_root=target_root, label="gateway")
    assert_fixture_state_unchanged(before, target_root, f"gateway {case['case_id']}")
    return decision, text, run_id


def anythingllm_decision(
    config: ContextRetrievalUpgradeConfig,
    case: dict[str, Any],
    target_root: str,
    *,
    api_key: str,
) -> tuple[dict[str, Any], str, str]:
    before = protected_fixture_state(config, target_root)
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": prompt_for_case(case, target_root),
            "mode": "chat",
            "sessionId": f"phase95-context-{case['case_id'].lower()}-{uuid.uuid4().hex}",
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
    decision = assert_live_record_matches_case(record, case, target_root=target_root, label="AnythingLLM")
    assert_fixture_state_unchanged(before, target_root, f"AnythingLLM {case['case_id']}")
    return decision, text, run_id


CaseRunner = Callable[[ContextRetrievalUpgradeConfig, dict[str, Any], str], tuple[dict[str, Any], str, str] | dict[str, Any]]


def run_case(
    config: ContextRetrievalUpgradeConfig,
    *,
    label: str,
    case: dict[str, Any],
    target_root: str,
    runner: CaseRunner,
) -> dict[str, Any]:
    try:
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
        return check(
            f"{label}.{case['case_id']}.{Path(target_root).name}",
            ContextRetrievalUpgradeStatus.PASSED,
            f"{label} context-source selection passed for {case['case_id']} on {target_root}.",
            details={
                "case_id": case["case_id"],
                "target_root": target_root,
                "run_id": run_id,
                "selected_context_sources": decision.get("selected_context_sources"),
                "layout_status": decision.get("context_source_audit", {}).get("layout", {}).get("status")
                if isinstance(decision.get("context_source_audit"), dict)
                else None,
            },
        )
    except Exception as exc:  # noqa: BLE001 - acceptance reports should classify all case failures
        return check(
            f"{label}.{case.get('case_id', 'unknown')}.{Path(target_root).name}",
            ContextRetrievalUpgradeStatus.FAILED,
            f"{label} context retrieval failed: {type(exc).__name__}: {exc}",
            details={"case_id": case.get("case_id"), "target_root": target_root},
            next_action="Inspect route_decision.context_source_audit, live run records, and protected fixture state.",
        )


def health_checks(timeout_seconds: int) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for label, url in PORT_HEALTH_PROBES:
        try:
            status, body = json_request(url, timeout_seconds=timeout_seconds)
            passed = status == 200
            checks.append(
                check(
                    f"port_health.{label}",
                    ContextRetrievalUpgradeStatus.PASSED if passed else ContextRetrievalUpgradeStatus.FAILED,
                    f"{label} returned HTTP {status}.",
                    details={"url": url, "http_status": status, "body": body},
                    next_action="" if passed else "Restart the Bash-hosted gateway/controller stack.",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                check(
                    f"port_health.{label}",
                    ContextRetrievalUpgradeStatus.FAILED,
                    f"{label} health probe failed: {type(exc).__name__}: {exc}",
                    details={"url": url},
                    next_action="Restart the Bash-hosted gateway/controller stack.",
                )
            )
    return checks


def validate_context_retrieval_upgrade(config: ContextRetrievalUpgradeConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    cases_path = resolve_path(config_root, config.cases_path)
    output_path = config.output_path or default_report_path(config_root)
    catalog = read_json_object(cases_path)
    cases = object_list(catalog.get("cases"))
    non_coinbase_target = create_non_coinbase_fixture(ContextRetrievalUpgradeConfig(**{**config.__dict__, "config_root": config_root}))
    unsupported_target = create_unsupported_fixture(ContextRetrievalUpgradeConfig(**{**config.__dict__, "config_root": config_root}))
    checks: list[dict[str, Any]] = []
    checks.extend(validate_catalog(catalog, cases_path=cases_path))
    if config.include_port_health:
        checks.extend(health_checks(min(config.timeout_seconds, 60)))
    if config.include_direct:
        for case in cases:
            for target_root in targets_for_case(
                config,
                case,
                non_coinbase_target=non_coinbase_target,
                unsupported_target=unsupported_target,
            ):
                checks.append(
                    run_case(
                        config,
                        label="direct",
                        case=case,
                        target_root=target_root,
                        runner=direct_decision,
                    )
                )
    if config.include_gateway:
        for case in cases:
            for target_root in targets_for_case(
                config,
                case,
                non_coinbase_target=non_coinbase_target,
                unsupported_target=unsupported_target,
            ):
                checks.append(
                    run_case(
                        config,
                        label="gateway",
                        case=case,
                        target_root=target_root,
                        runner=gateway_decision,
                    )
                )
    if config.include_anythingllm:
        api_key = os.environ.get(config.api_key_env)
        if not api_key:
            checks.append(
                check(
                    "anythingllm.api_key",
                    ContextRetrievalUpgradeStatus.FAILED,
                    f"{config.api_key_env} is missing.",
                    next_action="Export ANYTHINGLLM_API_KEY before running live AnythingLLM validation.",
                )
            )
        else:
            for case in cases:
                for target_root in targets_for_case(
                    config,
                    case,
                    non_coinbase_target=non_coinbase_target,
                    unsupported_target=unsupported_target,
                ):
                    checks.append(
                        run_case(
                            config,
                            label="AnythingLLM",
                            case=case,
                            target_root=target_root,
                            runner=lambda cfg, item, root, key=api_key: anythingllm_decision(
                                cfg, item, root, api_key=key
                            ),
                        )
                    )
    failed = [item for item in checks if item.get("status") == ContextRetrievalUpgradeStatus.FAILED.value]
    skipped = [item for item in checks if item.get("status") == ContextRetrievalUpgradeStatus.SKIPPED.value]
    report = {
        "kind": "context_retrieval_upgrade_report",
        "schema_version": SCHEMA_VERSION,
        "phase": 95,
        "status": "failed" if failed else "passed",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "config_root": str(config_root),
        "cases_path": str(cases_path),
        "target_roots": list(config.target_roots),
        "generated_fixtures": {
            "non_coinbase": non_coinbase_target,
            "unsupported_empty": unsupported_target,
        },
        "summary": {
            "case_count": len(cases),
            "check_count": len(checks),
            "failed_check_ids": [str(item.get("id")) for item in failed],
            "skipped_check_ids": [str(item.get("id")) for item in skipped],
            "direct_enabled": config.include_direct,
            "gateway_enabled": config.include_gateway,
            "anythingllm_enabled": config.include_anythingllm,
            "port_health_enabled": config.include_port_health,
        },
        "checks": checks,
    }
    report["report_path"] = str(output_path)
    write_json(output_path, report)
    return report
