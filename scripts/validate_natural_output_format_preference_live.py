#!/usr/bin/env python3
"""Validate natural output-format preferences through gateway and AnythingLLM."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_task_decomposition_live import (  # noqa: E402
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONFIG_ROOT,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    PORT_HEALTH_PROBES,
    WATCHED_RUNTIME_FILES,
    changed_hashes,
    git_status,
    json_request,
    validate_no_target_mutation,
    watched_files_for_root,
    watched_hashes,
    write_json,
)
from vllm_agent_gateway.acceptance.natural_output_format_preference import (  # noqa: E402
    DEFAULT_CASES_PATH,
    NATURAL_JSON_SELECTOR_KIND,
    NaturalOutputFormatPreferenceCase,
    load_natural_output_format_preference_cases,
    validate_default_format_a_response,
    validate_json_preference_response,
    validate_natural_output_format_preference_report,
    validate_preference_case_catalog,
)
from vllm_agent_gateway.acceptance.output_format_parity import (  # noqa: E402
    assistant_text_from_body,
    parse_assistant_json,
)


DEFAULT_OUTPUT_PATH = "runtime-state/natural-output-format-preference/phase144-natural-output-format-preference-live.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def with_natural_json_instruction(case: NaturalOutputFormatPreferenceCase) -> str:
    return f"{case.prompt}\n{case.natural_json_instruction}"


def with_natural_format_a_instruction(case: NaturalOutputFormatPreferenceCase) -> str:
    return f"{case.prompt}\nReturn the answer in plain English."


def gateway_payload(case: NaturalOutputFormatPreferenceCase, preference: str) -> dict[str, Any]:
    prompt = case.prompt
    payload: dict[str, Any] = {
        "model": "agentic-workflow-router",
        "messages": [{"role": "user", "content": prompt}],
    }
    if preference == "natural_format_a":
        payload["messages"] = [{"role": "user", "content": with_natural_format_a_instruction(case)}]
    elif preference == "natural_json":
        payload["messages"] = [{"role": "user", "content": with_natural_json_instruction(case)}]
    elif preference == "explicit_output_format_json":
        payload["output_format"] = "json"
    elif preference == "openai_response_format_json":
        payload["response_format"] = {"type": "json_object"}
    elif preference == "unsupported_explicit_output_format":
        payload["output_format"] = "markdown"
    elif preference == "unsupported_response_format":
        payload["response_format"] = {"type": "xml"}
    elif preference != "default_format_a":
        raise ValueError(f"unsupported gateway preference {preference!r}")
    return payload


def anythingllm_payload(case: NaturalOutputFormatPreferenceCase, preference: str) -> dict[str, Any]:
    if preference == "default_format_a":
        prompt = case.prompt
    elif preference == "natural_format_a":
        prompt = with_natural_format_a_instruction(case)
    elif preference == "natural_json":
        prompt = with_natural_json_instruction(case)
    else:
        raise ValueError(f"unsupported AnythingLLM preference {preference!r}")
    return {
        "message": prompt,
        "mode": "chat",
        "sessionId": f"natural-output-format-{case.case_id.lower()}-{preference}-{uuid.uuid4().hex}",
    }


def run_id_from_gateway_body(body: dict[str, Any]) -> str:
    compact = body.get("agentic_controller_response")
    if isinstance(compact, dict) and isinstance(compact.get("run_id"), str):
        return compact["run_id"]
    return ""


def selected_output_format_from_gateway_body(body: dict[str, Any]) -> str | None:
    compact = body.get("agentic_controller_response")
    if isinstance(compact, dict) and isinstance(compact.get("output_format"), str):
        return compact["output_format"]
    return None


def run_id_from_json_object(parsed: dict[str, Any]) -> str:
    value = parsed.get("run_id")
    return value if isinstance(value, str) else ""


def request_proof(preference: str) -> dict[str, Any]:
    if preference == "natural_json":
        return {
            "selector_kind": NATURAL_JSON_SELECTOR_KIND,
            "explicit_output_format_fields": [],
        }
    if preference == "natural_format_a":
        return {
            "selector_kind": "natural_text_format_a",
            "explicit_output_format_fields": [],
        }
    if preference == "explicit_output_format_json":
        return {
            "selector_kind": "explicit_output_format",
            "explicit_output_format_fields": ["output_format"],
        }
    if preference == "openai_response_format_json":
        return {
            "selector_kind": "openai_response_format",
            "explicit_output_format_fields": ["response_format"],
        }
    if preference == "unsupported_explicit_output_format":
        return {
            "selector_kind": "unsupported_explicit_output_format",
            "explicit_output_format_fields": ["output_format"],
        }
    if preference == "unsupported_response_format":
        return {
            "selector_kind": "unsupported_response_format",
            "explicit_output_format_fields": ["response_format"],
        }
    return {
        "selector_kind": "default",
        "explicit_output_format_fields": [],
    }


def unsupported_output_format_error_code(status: int, body: dict[str, Any]) -> str | None:
    if status == 400:
        error = body.get("error") if isinstance(body.get("error"), dict) else {}
        code = error.get("code")
        return code if isinstance(code, str) else None
    if status == 200:
        compact = body.get("agentic_controller_response")
        if not isinstance(compact, dict) or compact.get("status") != "failed":
            return None
        summary = compact.get("summary") if isinstance(compact.get("summary"), dict) else {}
        code = summary.get("error_code")
        if isinstance(code, str):
            return code
        failures = compact.get("failures") if isinstance(compact.get("failures"), list) else []
        for failure in failures:
            if isinstance(failure, dict) and isinstance(failure.get("code"), str):
                return failure["code"]
    return None


def collect_gateway_preferences(args: argparse.Namespace, case: NaturalOutputFormatPreferenceCase) -> dict[str, Any]:
    preferences: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload=gateway_payload(case, "default_format_a"),
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        errors.append(f"gateway default FormatA returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        preferences["default_format_a"] = {"status": "failed", "http_status": status, "errors": errors[:]}
        return {"status": "failed", "preferences": preferences, "errors": errors}
    format_a_text = assistant_text_from_body(body)
    default_errors = validate_default_format_a_response(
        case,
        text=format_a_text,
        selected_output_format=selected_output_format_from_gateway_body(body),
    )
    preferences["default_format_a"] = {
        "status": "passed" if not default_errors else "failed",
        "http_status": status,
        "run_id": run_id_from_gateway_body(body),
        "selected_output_format": selected_output_format_from_gateway_body(body),
        "request": request_proof("default_format_a"),
        "text": format_a_text,
        "errors": default_errors,
    }
    errors.extend(default_errors)

    natural_status, natural_body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload=gateway_payload(case, "natural_format_a"),
        timeout_seconds=args.timeout_seconds,
    )
    natural_format_errors: list[str] = []
    natural_format_text = ""
    if natural_status != 200:
        natural_format_errors.append(
            f"gateway natural_format_a returned HTTP {natural_status}: {json.dumps(natural_body, ensure_ascii=True)}"
        )
    else:
        natural_format_text = assistant_text_from_body(natural_body)
        natural_format_errors.extend(
            validate_default_format_a_response(
                case,
                text=natural_format_text,
                selected_output_format=selected_output_format_from_gateway_body(natural_body),
            )
        )
    preferences["natural_format_a"] = {
        "status": "passed" if not natural_format_errors else "failed",
        "http_status": natural_status,
        "run_id": run_id_from_gateway_body(natural_body),
        "selected_output_format": selected_output_format_from_gateway_body(natural_body),
        "request": request_proof("natural_format_a"),
        "text": natural_format_text,
        "errors": natural_format_errors,
    }
    errors.extend(natural_format_errors)

    for preference in ("natural_json", "explicit_output_format_json", "openai_response_format_json"):
        json_status, json_body = json_request(
            f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
            payload=gateway_payload(case, preference),
            timeout_seconds=args.timeout_seconds,
        )
        preference_errors: list[str] = []
        parsed: dict[str, Any] | None = None
        json_text = ""
        if json_status != 200:
            preference_errors.append(
                f"gateway {preference} returned HTTP {json_status}: {json.dumps(json_body, ensure_ascii=True)}"
            )
        else:
            json_text = assistant_text_from_body(json_body)
            try:
                parsed = parse_assistant_json(json_text)
            except ValueError as exc:
                preference_errors.append(str(exc))
            if parsed is not None:
                preference_errors.extend(
                    validate_json_preference_response(
                        case,
                        format_a_text=format_a_text,
                        json_object=parsed,
                        selector_kind=request_proof(preference)["selector_kind"],
                        selected_output_format=selected_output_format_from_gateway_body(json_body),
                        require_natural_selector=preference == "natural_json",
                    )
                )
        preferences[preference] = {
            "status": "passed" if not preference_errors else "failed",
            "http_status": json_status,
            "run_id": run_id_from_json_object(parsed or {}) or run_id_from_gateway_body(json_body),
            "selected_output_format": selected_output_format_from_gateway_body(json_body),
            "request": request_proof(preference),
            "text": json_text,
            "parsed": parsed,
            "errors": preference_errors,
        }
        errors.extend(preference_errors)

    for preference in ("unsupported_explicit_output_format", "unsupported_response_format"):
        unsupported_status, unsupported_body = json_request(
            f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
            payload=gateway_payload(case, preference),
            timeout_seconds=args.timeout_seconds,
        )
        preference_errors: list[str] = []
        error_code = unsupported_output_format_error_code(unsupported_status, unsupported_body)
        if unsupported_status not in {200, 400}:
            preference_errors.append(
                f"gateway {preference} returned HTTP {unsupported_status}; expected visible 200 failure or raw 400: "
                f"{json.dumps(unsupported_body, ensure_ascii=True)}"
            )
        if error_code != "unsupported_output_format":
            preference_errors.append(
                f"gateway {preference} error code was {error_code!r}; expected unsupported_output_format"
            )
        preferences[preference] = {
            "status": "passed" if not preference_errors else "failed",
            "http_status": unsupported_status,
            "request": request_proof(preference),
            "error": {"code": error_code},
            "errors": preference_errors,
        }
        errors.extend(preference_errors)
    return {
        "status": "passed" if not errors else "failed",
        "preferences": preferences,
        "errors": errors,
    }


def collect_anythingllm_preferences(
    args: argparse.Namespace,
    case: NaturalOutputFormatPreferenceCase,
    api_key: str,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"}
    preferences: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload=anythingllm_payload(case, "default_format_a"),
        headers=headers,
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        errors.append(f"AnythingLLM default FormatA returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        preferences["default_format_a"] = {"status": "failed", "http_status": status, "errors": errors[:]}
        return {"status": "failed", "preferences": preferences, "errors": errors}
    format_a_text = assistant_text_from_body(body)
    default_errors = validate_default_format_a_response(case, text=format_a_text)
    preferences["default_format_a"] = {
        "status": "passed" if not default_errors else "failed",
        "http_status": status,
        "request": request_proof("default_format_a"),
        "text": format_a_text,
        "errors": default_errors,
    }
    errors.extend(default_errors)

    natural_status, natural_body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload=anythingllm_payload(case, "natural_format_a"),
        headers=headers,
        timeout_seconds=args.timeout_seconds,
    )
    natural_format_errors: list[str] = []
    natural_format_text = ""
    if natural_status != 200:
        natural_format_errors.append(
            f"AnythingLLM natural_format_a returned HTTP {natural_status}: {json.dumps(natural_body, ensure_ascii=True)}"
        )
    else:
        natural_format_text = assistant_text_from_body(natural_body)
        natural_format_errors.extend(validate_default_format_a_response(case, text=natural_format_text))
    preferences["natural_format_a"] = {
        "status": "passed" if not natural_format_errors else "failed",
        "http_status": natural_status,
        "request": request_proof("natural_format_a"),
        "text": natural_format_text,
        "errors": natural_format_errors,
    }
    errors.extend(natural_format_errors)

    json_status, json_body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload=anythingllm_payload(case, "natural_json"),
        headers=headers,
        timeout_seconds=args.timeout_seconds,
    )
    preference_errors: list[str] = []
    parsed: dict[str, Any] | None = None
    json_text = ""
    if json_status != 200:
        preference_errors.append(
            f"AnythingLLM natural_json returned HTTP {json_status}: {json.dumps(json_body, ensure_ascii=True)}"
        )
    else:
        json_text = assistant_text_from_body(json_body)
        try:
            parsed = parse_assistant_json(json_text)
        except ValueError as exc:
            preference_errors.append(str(exc))
        if parsed is not None:
            preference_errors.extend(
                validate_json_preference_response(
                    case,
                    format_a_text=format_a_text,
                    json_object=parsed,
                    selector_kind=NATURAL_JSON_SELECTOR_KIND,
                    require_natural_selector=True,
                )
            )
    preferences["natural_json"] = {
        "status": "passed" if not preference_errors else "failed",
        "http_status": json_status,
        "run_id": run_id_from_json_object(parsed or {}),
        "request": request_proof("natural_json"),
        "text": json_text,
        "parsed": parsed,
        "errors": preference_errors,
    }
    errors.extend(preference_errors)
    return {
        "status": "passed" if not errors else "failed",
        "preferences": preferences,
        "errors": errors,
    }


def validate_port_health(timeout_seconds: int) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for label, url in PORT_HEALTH_PROBES:
        status, body = json_request(url, timeout_seconds=timeout_seconds, method="GET")
        if status != 200:
            raise RuntimeError(f"{label} health probe returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        checks.append({"label": label, "url": url, "status": "passed"})
        print(f"NATURAL OUTPUT FORMAT PORT PASS label={label} url={url}")
    return checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=DEFAULT_CONFIG_ROOT)
    parser.add_argument("--cases-path", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--skip-gateway", action="store_true")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--skip-port-health", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    output_path = Path(args.output_path)
    if not output_path.is_absolute():
        output_path = config_root / output_path

    all_cases = load_natural_output_format_preference_cases(Path(args.cases_path), repo_root=config_root)
    catalog_errors = validate_preference_case_catalog(all_cases)
    if catalog_errors:
        raise RuntimeError(f"natural output format preference case catalog failed: {catalog_errors}")
    if args.case_ids:
        requested = set(args.case_ids)
        cases = [case for case in all_cases if case.case_id in requested]
        missing = sorted(requested - {case.case_id for case in cases})
        if missing:
            raise RuntimeError(f"Unknown case ids requested: {missing}")
    else:
        cases = all_cases

    if args.skip_gateway and args.skip_anythingllm:
        raise RuntimeError("At least one live surface must be enabled")
    api_key = os.environ.get(args.api_key_env)
    if not args.skip_anythingllm and not api_key:
        raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")

    target_roots = sorted({case.target_root for case in cases})
    runtime_before = watched_hashes(config_root, WATCHED_RUNTIME_FILES)
    target_watch_files = {root: watched_files_for_root(Path(root)) for root in target_roots}
    target_before = {root: watched_hashes(Path(root), target_watch_files[root]) for root in target_roots}
    target_git_before = {root: git_status(Path(root)) for root in target_roots}

    report_cases: list[dict[str, Any]] = []
    for case in cases:
        case_report: dict[str, Any] = {
            "case_id": case.case_id,
            "source_case_id": case.source_case_id,
            "prompt_family": case.prompt_family,
            "target_root": case.target_root,
            "natural_json_instruction": case.natural_json_instruction,
            "responses": {},
            "errors": [],
        }
        if not args.skip_gateway:
            gateway_report = collect_gateway_preferences(args, case)
            case_report["responses"]["gateway"] = gateway_report
            case_report["errors"].extend(gateway_report.get("errors", []))
            validate_no_target_mutation(
                Path(case.target_root),
                target_watch_files[case.target_root],
                target_before[case.target_root],
                target_git_before[case.target_root],
                f"natural output format gateway {case.case_id}",
            )
            print(f"NATURAL OUTPUT FORMAT GATEWAY {gateway_report['status'].upper()} case={case.case_id}")
        if not args.skip_anythingllm:
            anythingllm_report = collect_anythingllm_preferences(args, case, str(api_key))
            case_report["responses"]["anythingllm"] = anythingllm_report
            case_report["errors"].extend(anythingllm_report.get("errors", []))
            validate_no_target_mutation(
                Path(case.target_root),
                target_watch_files[case.target_root],
                target_before[case.target_root],
                target_git_before[case.target_root],
                f"natural output format AnythingLLM {case.case_id}",
            )
            print(f"NATURAL OUTPUT FORMAT ANYTHINGLLM {anythingllm_report['status'].upper()} case={case.case_id}")
        report_cases.append(case_report)

    runtime_changed = changed_hashes(runtime_before, watched_hashes(config_root, WATCHED_RUNTIME_FILES))
    target_changed_files = {
        root: changed_hashes(target_before[root], watched_hashes(Path(root), target_watch_files[root]))
        for root in target_roots
    }
    target_git_changed = {
        root: git_status(Path(root))
        for root in target_roots
        if target_git_before[root] is not None and git_status(Path(root)) != target_git_before[root]
    }
    report = {
        "kind": "natural_output_format_preference_live_report",
        "schema_version": 1,
        "status": "passed",
        "created_at": utc_now(),
        "priority_backlog_id": "P0-BB-020",
        "phase": 144,
        "config_root": str(config_root),
        "cases_path": str(Path(args.cases_path)),
        "workflow_router_gateway_base_url": args.workflow_router_gateway_base_url,
        "anythingllm_api_base_url": args.anythingllm_api_base_url,
        "anythingllm_applicable": not args.skip_anythingllm,
        "port_health": [] if args.skip_port_health else validate_port_health(args.timeout_seconds),
        "case_count": len(report_cases),
        "target_roots": target_roots,
        "cases": report_cases,
        "mutation_proof": {
            "runtime_changed_files": runtime_changed,
            "target_changed_files": target_changed_files,
            "target_git_changed": target_git_changed,
        },
    }
    report_errors = validate_natural_output_format_preference_report(report)
    if report_errors:
        report["status"] = "failed"
        report["errors"] = report_errors
    write_json(output_path, report)
    print(f"NATURAL OUTPUT FORMAT REPORT {report['status'].upper()} path={output_path}")
    if report_errors:
        print(json.dumps(report_errors, ensure_ascii=True, indent=2, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
