"""Phase 166 generic chat and vague prompt contract validation."""

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
from typing import Any

from vllm_agent_gateway.controller_service.server import (
    ControllerServiceConfig,
    handle_workflow_router_chat_completion,
)


SCHEMA_VERSION = 1
EXPECTED_REPORT_KIND = "generic_chat_vague_prompt_contract_report"
EXPECTED_POLICY_KIND = "generic_chat_vague_prompt_contract_policy"
EXPECTED_PHASE = 166
DEFAULT_POLICY_PATH = Path("runtime") / "generic_chat_vague_prompt_contract_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "generic-chat-vague-prompt-contract" / "phase166"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_TARGET_ROOTS = (
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
)
WATCHED_RELATIVE_PATHS = (
    "core/stealth_order_manager.py",
    "tests/unit/test_order_id_and_followup_rules.py",
    "docs/agents/INVARIANTS.md",
)


class Phase166Status(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class GenericChatVaguePromptContractConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    target_roots: tuple[str, ...] = DEFAULT_TARGET_ROOTS
    timeout_seconds: int = 120
    run_live: bool = False
    include_anythingllm: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"generic-chat-vague-prompt-contract-{utc_timestamp()}.json"


def resolve_path(config_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else config_root / path


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def load_policy(config_root: Path, policy_path: Path) -> dict[str, Any]:
    return read_json_object(resolve_path(config_root, policy_path))


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
            body_text = response.read().decode("utf-8")
            try:
                body = json.loads(body_text)
            except json.JSONDecodeError:
                body = {"text": body_text}
            return response.status, body
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body_text)
        except json.JSONDecodeError:
            body = {"error": {"message": body_text, "code": "invalid_json_error_body"}}
        return exc.code, body


def assistant_text_from_body(body: dict[str, Any]) -> str:
    for key in ("textResponse", "response", "message", "text"):
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
    return ""


def compact_response(body: dict[str, Any]) -> dict[str, Any]:
    value = body.get("agentic_controller_response")
    return value if isinstance(value, dict) else {}


def response_summary(body: dict[str, Any]) -> dict[str, Any]:
    compact = compact_response(body)
    summary = compact.get("summary") if isinstance(compact.get("summary"), dict) else {}
    return summary


def response_run_id(body: dict[str, Any]) -> str:
    compact = compact_response(body)
    value = compact.get("run_id")
    if isinstance(value, str):
        return value
    return ""


def response_artifact_count(body: dict[str, Any]) -> int | None:
    compact = compact_response(body)
    if not compact:
        return None
    artifacts = compact.get("artifacts")
    return len(artifacts) if isinstance(artifacts, dict) else 0


def case_prompt(case: dict[str, Any], target_root: str | None = None) -> str:
    template = case.get("prompt_template")
    if isinstance(template, str):
        return template.format(target_root=target_root or "")
    prompt = case.get("prompt")
    if not isinstance(prompt, str):
        raise RuntimeError(f"case {case.get('case_id')} must include prompt or prompt_template")
    return prompt


def direct_messages_for_case(case: dict[str, Any], prompt: str) -> list[dict[str, str]]:
    if case.get("stale_history") is True:
        return [
            {
                "role": "user",
                "content": (
                    "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain what "
                    "find_stealth_order_by_placed_order_id does. Read only."
                ),
            },
            {"role": "assistant", "content": "prior workflow_router run_id: workflow-router-old"},
            {"role": "user", "content": prompt},
        ]
    return [{"role": "user", "content": prompt}]


def forbidden_workflow_markers(workflows: list[str]) -> list[str]:
    markers: list[str] = []
    for workflow in workflows:
        markers.extend(
            [
                f"Selected workflow: {workflow}",
                f"selected_workflow: {workflow}",
                f"{workflow} completed",
            ]
        )
    return markers


def classify_case_response(
    *,
    policy: dict[str, Any],
    case: dict[str, Any],
    surface: str,
    prompt: str,
    target_root: str | None,
    http_status: int,
    body: dict[str, Any],
) -> dict[str, Any]:
    text = assistant_text_from_body(body)
    summary = response_summary(body)
    selected_workflow = summary.get("selected_workflow")
    selected_workflow_display = "none" if selected_workflow is None and "Selected workflow: none" in text else selected_workflow
    findings: list[dict[str, str]] = []
    if http_status != 200:
        findings.append({"severity": "blocker", "code": "http_not_ok", "message": f"HTTP status was {http_status}."})
    if not text.strip():
        findings.append({"severity": "blocker", "code": "missing_chat_text", "message": "Assistant text was empty."})
    if len(text) > 12000:
        findings.append({"severity": "blocker", "code": "unbounded_chat_text", "message": "Assistant text was too long."})
    for marker in case.get("required_markers", []):
        if isinstance(marker, str) and marker not in text:
            findings.append(
                {
                    "severity": "blocker",
                    "code": "missing_required_marker",
                    "message": f"Missing required marker {marker!r}.",
                }
            )
    expected_route_status = case.get("expected_route_status")
    if isinstance(expected_route_status, str):
        route_status = summary.get("route_status")
        if route_status is not None and route_status != expected_route_status:
            findings.append(
                {
                    "severity": "blocker",
                    "code": "wrong_route_status",
                    "message": f"Expected route_status {expected_route_status!r}, got {route_status!r}.",
                }
            )
        elif route_status is None and expected_route_status not in text:
            findings.append(
                {
                    "severity": "blocker",
                    "code": "missing_route_status",
                    "message": f"Missing route status marker {expected_route_status!r}.",
                }
            )
    forbidden = forbidden_workflow_markers(
        [str(item) for item in policy.get("forbidden_repository_workflows", []) if isinstance(item, str)]
    )
    for marker in forbidden:
        if marker in text:
            findings.append(
                {
                    "severity": "blocker",
                    "code": "repository_workflow_started",
                    "message": f"Forbidden workflow marker appeared: {marker}.",
                }
            )
    compact = compact_response(body)
    if selected_workflow in policy.get("forbidden_repository_workflows", []):
        findings.append(
            {
                "severity": "blocker",
                "code": "repository_workflow_selected",
                "message": f"Forbidden selected_workflow {selected_workflow}.",
            }
        )
    artifacts = compact.get("artifacts") if isinstance(compact.get("artifacts"), dict) else {}
    if case.get("target_root_mode") == "none" and artifacts:
        findings.append(
            {
                "severity": "blocker",
                "code": "no_target_case_created_artifacts",
                "message": "No-target chat guidance must not create route or downstream artifacts.",
            }
        )
    if case.get("stale_history") is True and ("find_stealth_order_by_placed_order_id" in text or "placed_order_id" in text):
        findings.append(
            {
                "severity": "blocker",
                "code": "stale_context_leaked",
                "message": "Greeting response leaked stale repository context.",
            }
        )
    if "Summary:" not in text and "answer" not in text.lower():
        findings.append(
            {
                "severity": "blocker",
                "code": "artifact_only_or_unstructured_output",
                "message": "Response did not include visible answer or summary text.",
            }
        )
    return {
        "case_id": case.get("case_id"),
        "prompt_class": case.get("prompt_class"),
        "surface": surface,
        "target_root": target_root,
        "prompt": prompt,
        "status": Phase166Status.PASSED.value if not findings else Phase166Status.FAILED.value,
        "http_status": http_status,
        "run_id": response_run_id(body),
        "route_status": summary.get("route_status"),
        "selected_workflow": selected_workflow_display,
        "artifact_count": response_artifact_count(body),
        "text_sample": text[:1600],
        "finding_count": len(findings),
        "findings": findings,
    }


def direct_case(
    *,
    config_root: Path,
    output_root: Path,
    allowed_target_roots: tuple[str, ...],
    policy: dict[str, Any],
    case: dict[str, Any],
    target_root: str | None,
) -> dict[str, Any]:
    prompt = case_prompt(case, target_root)
    service_config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=tuple(Path(root) for root in allowed_target_roots),
        port=0,
    )
    body = handle_workflow_router_chat_completion(
        {"model": "agentic-workflow-router", "messages": direct_messages_for_case(case, prompt)},
        service_config,
    )
    return classify_case_response(
        policy=policy,
        case=case,
        surface="direct_controller",
        prompt=prompt,
        target_root=target_root,
        http_status=200,
        body=body,
    )


def gateway_case(
    *,
    config: GenericChatVaguePromptContractConfig,
    policy: dict[str, Any],
    case: dict[str, Any],
    target_root: str | None,
) -> dict[str, Any]:
    prompt = case_prompt(case, target_root)
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={
            "model": "agentic-workflow-router",
            "messages": direct_messages_for_case(case, prompt),
        },
        timeout_seconds=config.timeout_seconds,
    )
    return classify_case_response(
        policy=policy,
        case=case,
        surface="workflow_router_gateway",
        prompt=prompt,
        target_root=target_root,
        http_status=status,
        body=body,
    )


def anythingllm_preflight(config: GenericChatVaguePromptContractConfig, api_key: str) -> dict[str, Any]:
    base_url = config.anythingllm_api_base_url.rstrip("/")
    ping_status, ping_body = json_request(f"{base_url}/api/ping", timeout_seconds=min(30, config.timeout_seconds))
    workspace_status, workspace_body = json_request(
        f"{base_url}/api/v1/workspaces",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=min(30, config.timeout_seconds),
    )
    workspaces = workspace_body.get("workspaces") if isinstance(workspace_body, dict) else []
    slugs = [item.get("slug") for item in workspaces if isinstance(item, dict)]
    return {
        "status": "passed" if ping_status == 200 and workspace_status == 200 and config.workspace in slugs else "failed",
        "ping_status": ping_status,
        "workspace_status": workspace_status,
        "workspace": config.workspace,
        "workspace_found": config.workspace in slugs,
        "ping": ping_body,
    }


def anythingllm_case(
    *,
    config: GenericChatVaguePromptContractConfig,
    policy: dict[str, Any],
    case: dict[str, Any],
    target_root: str | None,
    api_key: str,
) -> dict[str, Any]:
    prompt = case_prompt(case, target_root)
    message = prompt
    session_id = f"phase166-{str(case.get('case_id')).lower()}-{uuid.uuid4().hex}"
    prelude: dict[str, Any] | None = None
    if case.get("stale_history") is True:
        seed_status, seed_body = json_request(
            f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
            payload={
                "message": (
                    "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain what "
                    "find_stealth_order_by_placed_order_id does. Read only."
                ),
                "mode": "chat",
                "sessionId": session_id,
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout_seconds=config.timeout_seconds,
        )
        prelude = {
            "http_status": seed_status,
            "text_sample": assistant_text_from_body(seed_body)[:500],
        }
        message = "hi"
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": message,
            "mode": "chat",
            "sessionId": session_id,
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    result = classify_case_response(
        policy=policy,
        case=case,
        surface="anythingllm",
        prompt=message,
        target_root=target_root,
        http_status=status,
        body=body,
    )
    if prelude is not None:
        result["prelude"] = prelude
        if prelude["http_status"] != 200:
            result["status"] = Phase166Status.FAILED.value
            result["finding_count"] += 1
            result["findings"].append(
                {
                    "severity": "blocker",
                    "code": "stale_history_prelude_failed",
                    "message": f"Stale-history seed prompt returned HTTP {prelude['http_status']}.",
                }
            )
    return result


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_status(target_root: str) -> str | None:
    root = Path(target_root)
    if not (root / ".git").exists():
        return None
    result = subprocess.run(["git", "-C", target_root, "status", "--short"], check=True, capture_output=True, text=True)
    return result.stdout


def fixture_state(target_roots: tuple[str, ...]) -> dict[str, Any]:
    roots: dict[str, Any] = {}
    for target_root in target_roots:
        root = Path(target_root)
        files: dict[str, str] = {}
        for relative_path in WATCHED_RELATIVE_PATHS:
            path = root / relative_path
            if path.exists():
                files[relative_path] = file_sha256(path)
        roots[target_root] = {
            "exists": root.is_dir(),
            "watched_files": files,
            "git_status": git_status(target_root),
        }
    return roots


def fixture_state_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return before != after


def expanded_cases(policy: dict[str, Any], target_roots: tuple[str, ...]) -> list[tuple[dict[str, Any], str | None]]:
    records: list[tuple[dict[str, Any], str | None]] = []
    for case in policy.get("required_cases", []):
        if not isinstance(case, dict):
            continue
        if case.get("target_root_mode") == "each_required":
            for target_root in target_roots:
                records.append((case, target_root))
        else:
            records.append((case, None))
    return records


def build_report(
    *,
    policy: dict[str, Any],
    cases: list[dict[str, Any]],
    fixture_before: dict[str, Any],
    fixture_after: dict[str, Any],
    anythingllm_preflight_result: dict[str, Any] | None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    current_errors = list(errors or [])
    failed_cases = [case for case in cases if case.get("status") != Phase166Status.PASSED.value]
    blocker_findings = [
        finding
        for case in cases
        for finding in case.get("findings", [])
        if isinstance(finding, dict) and finding.get("severity") == "blocker"
    ]
    changed = fixture_state_changed(fixture_before, fixture_after)
    if changed:
        current_errors.append("protected fixture state changed")
    if anythingllm_preflight_result and anythingllm_preflight_result.get("status") != "passed":
        current_errors.append("AnythingLLM preflight failed")
    surfaces = sorted({str(case.get("surface")) for case in cases if isinstance(case.get("surface"), str)})
    target_roots = sorted({str(case.get("target_root")) for case in cases if isinstance(case.get("target_root"), str)})
    summary = {
        "case_count": len(cases),
        "passed_case_count": len(cases) - len(failed_cases),
        "failed_case_count": len(failed_cases),
        "blocker_finding_count": len(blocker_findings),
        "surfaces": surfaces,
        "surface_count": len(surfaces),
        "target_roots": target_roots,
        "target_root_count": len(target_roots),
        "fixture_state_changed": changed,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "status": Phase166Status.PASSED.value
        if not failed_cases and not blocker_findings and not current_errors
        else Phase166Status.FAILED.value,
        "generated_at": utc_timestamp(),
        "policy_ref": {
            "kind": policy.get("kind"),
            "schema_version": policy.get("schema_version"),
            "phase": policy.get("phase"),
        },
        "blind_baseline": policy.get("blind_baseline") if isinstance(policy.get("blind_baseline"), dict) else {},
        "anythingllm_preflight": anythingllm_preflight_result or {},
        "summary": summary,
        "cases": cases,
        "fixture_state": {
            "before": fixture_before,
            "after": fixture_after,
            "changed": changed,
        },
        "errors": current_errors,
    }


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 166")
    cases = policy.get("required_cases")
    if not isinstance(cases, list) or len(cases) < 6:
        errors.append("policy.required_cases must include at least six cases")
    baseline = policy.get("blind_baseline")
    if not isinstance(baseline, dict) or baseline.get("source") != "contextless_blind_agent":
        errors.append("policy.blind_baseline must record contextless blind-agent source")
    return errors


def validate_generic_chat_vague_prompt_contract_report(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors = validate_policy(policy)
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("report.schema_version must be 1")
    if report.get("kind") != EXPECTED_REPORT_KIND:
        errors.append(f"report.kind must be {EXPECTED_REPORT_KIND}")
    if report.get("phase") != EXPECTED_PHASE:
        errors.append("report.phase must be 166")
    cases = [case for case in report.get("cases", []) if isinstance(case, dict)]
    fixture_state_record = report.get("fixture_state") if isinstance(report.get("fixture_state"), dict) else {}
    rebuilt = build_report(
        policy=policy,
        cases=cases,
        fixture_before=fixture_state_record.get("before") if isinstance(fixture_state_record.get("before"), dict) else {},
        fixture_after=fixture_state_record.get("after") if isinstance(fixture_state_record.get("after"), dict) else {},
        anythingllm_preflight_result=report.get("anythingllm_preflight")
        if isinstance(report.get("anythingllm_preflight"), dict)
        else {},
        errors=report.get("errors") if isinstance(report.get("errors"), list) else [],
    )
    for key in ("status", "summary"):
        if report.get(key) != rebuilt.get(key):
            errors.append(f"report.{key} must match rebuilt Phase 166 report")
    actual_surfaces = {case.get("surface") for case in cases}
    live_surface_present = bool(actual_surfaces & {"workflow_router_gateway", "anythingllm"}) or bool(
        report.get("anythingllm_preflight")
    )
    if live_surface_present:
        required_surfaces = set(policy.get("required_surfaces", []))
        missing_surfaces = sorted(str(surface) for surface in required_surfaces - actual_surfaces)
        if missing_surfaces:
            errors.append(f"report missing required surfaces: {missing_surfaces}")
    required_case_ids = {case.get("case_id") for case in policy.get("required_cases", []) if isinstance(case, dict)}
    actual_case_ids = {case.get("case_id") for case in cases}
    missing_cases = sorted(str(case_id) for case_id in required_case_ids - actual_case_ids)
    if missing_cases:
        errors.append(f"report missing required case ids: {missing_cases}")
    required_roots = set(policy.get("required_target_roots", []))
    actual_roots = {case.get("target_root") for case in cases if case.get("target_root")}
    missing_roots = sorted(str(root) for root in required_roots - actual_roots)
    if missing_roots and report.get("anythingllm_preflight"):
        errors.append(f"report missing required target roots: {missing_roots}")
    return errors


def run_generic_chat_vague_prompt_contract(config: GenericChatVaguePromptContractConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy = load_policy(config_root, config.policy_path)
    target_roots = tuple(config.target_roots)
    fixture_before = fixture_state(target_roots)
    cases: list[dict[str, Any]] = []
    errors = validate_policy(policy)
    direct_output = config_root / DEFAULT_OUTPUT_DIR / "direct-controller-artifacts"
    for case, target_root in expanded_cases(policy, target_roots):
        cases.append(
            direct_case(
                config_root=config_root,
                output_root=direct_output,
                allowed_target_roots=target_roots,
                policy=policy,
                case=case,
                target_root=target_root,
            )
        )
    preflight: dict[str, Any] = {}
    api_key = os.environ.get(config.api_key_env)
    if config.run_live:
        for case, target_root in expanded_cases(policy, target_roots):
            cases.append(gateway_case(config=config, policy=policy, case=case, target_root=target_root))
        if config.include_anythingllm:
            if not api_key:
                errors.append(f"{config.api_key_env} is required for live AnythingLLM validation")
            else:
                preflight = anythingllm_preflight(config, api_key)
                if preflight.get("status") == "passed":
                    for case, target_root in expanded_cases(policy, target_roots):
                        cases.append(
                            anythingllm_case(
                                config=config,
                                policy=policy,
                                case=case,
                                target_root=target_root,
                                api_key=api_key,
                            )
                        )
    fixture_after = fixture_state(target_roots)
    report = build_report(
        policy=policy,
        cases=cases,
        fixture_before=fixture_before,
        fixture_after=fixture_after,
        anythingllm_preflight_result=preflight,
        errors=errors,
    )
    validation_errors = validate_generic_chat_vague_prompt_contract_report(report, policy)
    if validation_errors:
        report["status"] = Phase166Status.FAILED.value
        report["errors"] = list(report.get("errors") or []) + validation_errors
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
