"""V1 founder acceptance suite helpers."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.profiles import ReleaseGateProfile, release_gate_profile_contract_json


DEFAULT_MODEL_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_CONTROLLER_BASE_URL = "http://127.0.0.1:8400"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_TARGET_ROOTS = [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
]
DEFAULT_REPORT_DIR = Path("runtime-state") / "v1-acceptance"
WATCHED_RELATIVE_PATHS = [
    "configuration.py",
    "core/stealth_order_manager.py",
    "docs/agents/INVARIANTS.md",
    "tests/unit/test_order_id_and_followup_rules.py",
]
HEALTH_TARGETS = [
    {"name": "model", "port": 8000, "path": "/v1/models"},
    {"name": "llm_gateway", "port": 8300, "path": "/v1/models"},
    {"name": "workflow_router_gateway", "port": 8500, "path": "/v1/models"},
    {"name": "controller", "port": 8400, "path": "/health"},
    {"name": "reviewer_code", "port": 8101, "path": "/v1/models"},
    {"name": "tester_code", "port": 8102, "path": "/v1/models"},
    {"name": "architect_default", "port": 8201, "path": "/v1/models"},
    {"name": "dispatcher_default", "port": 8202, "path": "/v1/models"},
    {"name": "implementer_default", "port": 8203, "path": "/v1/models"},
    {"name": "researcher_default", "port": 8204, "path": "/v1/models"},
    {"name": "documenter_default", "port": 8205, "path": "/v1/models"},
]


@dataclass(frozen=True)
class V1AcceptanceConfig:
    config_root: Path
    candidate_model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    target_roots: tuple[str, ...] = tuple(DEFAULT_TARGET_ROOTS)
    timeout_seconds: int = 900
    command_timeout_seconds: int = 1800
    output_path: Path | None = None
    python_executable: str | None = None
    profile: ReleaseGateProfile = ReleaseGateProfile.RELEASE_CANDIDATE


V1_1_KNOWN_LIMITATIONS = [
    "Advanced broad refactor orchestration remains outside V1.1 acceptance.",
    "Real repository mutation remains blocked; V1.1 only proves existing approval-gated disposable-copy apply.",
    "Model capability profiles remain advisory and do not enable automatic model selection.",
    "V1.1 proves the current local stack and governed fixtures, not universal support for every repository or framework.",
]


def is_v1_1_profile(profile: ReleaseGateProfile) -> bool:
    return profile == ReleaseGateProfile.V1_1_RELEASE_CANDIDATE


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"v1-acceptance-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body_text)
        except json.JSONDecodeError:
            body = {"error": {"message": body_text, "code": "invalid_json_error_body"}}
        return exc.code, body


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
            delta = first.get("delta")
            if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                return delta["content"]
    raise RuntimeError("response did not include assistant text")


def run_id_from_text(text: str) -> str:
    marker = "run_id:"
    if marker not in text:
        return "unknown"
    return text.split(marker, 1)[1].strip().split()[0]


def explain_prompt(target_root: str, *, json_output: bool = False) -> str:
    suffix = " Return JSON." if json_output else ""
    return (
        f"In {target_root}, explain what find_stealth_order_by_placed_order_id does "
        "in core/stealth_order_manager.py. Read only. Include key inputs, outputs, "
        f"side effects, and tests.{suffix}"
    )


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


def git_status_summary(target_root: str) -> dict[str, Any] | None:
    status = git_status(target_root)
    if status is None:
        return None
    lines = status.splitlines()
    return {
        "clean": status == "",
        "line_count": len(lines),
        "sha256": hashlib.sha256(status.encode("utf-8")).hexdigest(),
        "sample": lines[:5],
    }


def fixture_state(target_roots: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    return {
        target_root: {
            "hashes": watched_hashes(target_root),
            "git_status": git_status_summary(target_root),
        }
        for target_root in target_roots
    }


def assert_fixture_state_unchanged(before: dict[str, dict[str, Any]], target_roots: tuple[str, ...], label: str) -> None:
    after = fixture_state(target_roots)
    if after != before:
        raise RuntimeError(f"{label} changed protected fixture state")


def health_check(timeout_seconds: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for target in HEALTH_TARGETS:
        url = f"http://127.0.0.1:{target['port']}{target['path']}"
        try:
            status, _body = json_request(url, timeout_seconds=timeout_seconds)
            results.append({**target, "url": url, "status": "passed", "http_status": status})
        except Exception as exc:  # noqa: BLE001
            results.append({**target, "url": url, "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
    return results


def suite_commands(config: V1AcceptanceConfig) -> list[dict[str, Any]]:
    python = config.python_executable or sys.executable
    common = [
        "--workflow-router-gateway-base-url",
        config.workflow_router_gateway_base_url,
        "--anythingllm-api-base-url",
        config.anythingllm_api_base_url,
        "--workspace",
        config.workspace,
        "--api-key-env",
        config.api_key_env,
        "--timeout-seconds",
        str(config.timeout_seconds),
    ]
    targets: list[str] = []
    for target_root in config.target_roots:
        targets.extend(["--target-root", target_root])
    setup_commands: list[dict[str, Any]] = []
    if is_v1_1_profile(config.profile):
        setup_commands = [
            {
                "id": "first_time_user_doctor",
                "description": "Setup preflight for localhost ports, AnythingLLM, controller roots, and protected fixtures",
                "command": [
                    python,
                    str(config.config_root / "scripts" / "run_first_time_user_doctor.py"),
                    "--workflow-router-gateway-base-url",
                    config.workflow_router_gateway_base_url,
                    "--controller-base-url",
                    config.controller_base_url,
                    "--anythingllm-api-base-url",
                    config.anythingllm_api_base_url,
                    "--workspace",
                    config.workspace,
                    "--api-key-env",
                    config.api_key_env,
                    "--timeout-seconds",
                    str(min(60, config.timeout_seconds)),
                    *targets,
                ],
            },
            {
                "id": "docs_index",
                "description": "Ordered project documentation index validation",
                "command": [
                    python,
                    str(config.config_root / "scripts" / "check_docs_index.py"),
                    "--repo-root",
                    str(config.config_root),
                ],
            },
            {
                "id": "release_channels",
                "description": "Release-channel metadata validation",
                "command": [
                    python,
                    str(config.config_root / "scripts" / "validate_release_channels.py"),
                    "--config-root",
                    str(config.config_root),
                ],
            },
        ]
    base_commands = [
        {
            "id": "representative_l1",
            "description": "L1 read-only plus draft-only representative cases",
            "command": [
                python,
                str(config.config_root / "scripts" / "validate_workflow_router_l1_suite.py"),
                *common,
                *targets,
                "--case-id",
                "L1-002",
                "--case-id",
                "L1-010",
            ],
        },
        {
            "id": "representative_l2",
            "description": "L2 read-only representative test-selection case",
            "command": [
                python,
                str(config.config_root / "scripts" / "validate_workflow_router_l2_suite.py"),
                *common,
                *targets,
                "--case-id",
                "L2-005",
            ],
        },
        {
            "id": "task_decomposition",
            "description": "Multi-step task decomposition through direct controller, gateway, and AnythingLLM",
            "command": [
                python,
                str(config.config_root / "scripts" / "validate_task_decomposition_live.py"),
                "--controller-base-url",
                config.controller_base_url,
                *common,
                *targets,
            ],
        },
        {
            "id": "controlled_apply",
            "description": "Controlled dry-run and disposable-copy apply through direct controller, gateway, and AnythingLLM",
            "command": [
                python,
                str(config.config_root / "scripts" / "validate_controlled_small_change_apply_live.py"),
                "--controller-base-url",
                config.controller_base_url,
                *common,
                *targets,
            ],
        },
        {
            "id": "inline_format_a",
            "description": "Chat-visible FormatA output through gateway and AnythingLLM",
            "command": [
                python,
                str(config.config_root / "scripts" / "validate_workflow_router_inline_answers.py"),
                *common,
                *targets,
            ],
        },
        {
            "id": "external_tester_onboarding",
            "description": "Contextless external-tester onboarding prompt and linked feedback through AnythingLLM",
            "command": [
                python,
                str(config.config_root / "scripts" / "validate_external_tester_onboarding.py"),
                "--anythingllm-api-base-url",
                config.anythingllm_api_base_url,
                "--workspace",
                config.workspace,
                "--api-key-env",
                config.api_key_env,
                "--timeout-seconds",
                str(config.timeout_seconds),
                "--live-anythingllm",
                "--include-feedback",
                "--case-id",
                "ONB-001",
            ],
        },
        {
            "id": "founder_field_prompts",
            "description": "Expanded natural founder prompts through AnythingLLM with fixture mutation proof",
            "command": [
                python,
                str(config.config_root / "scripts" / "run_founder_field_prompt_eval.py"),
                "--anythingllm-api-base-url",
                config.anythingllm_api_base_url,
                "--workspace",
                config.workspace,
                "--api-key-env",
                config.api_key_env,
                "--timeout-seconds",
                str(config.timeout_seconds),
            ],
        },
        {
            "id": "skill_library_release_gate",
            "description": "Skill registry, eval, selector-scale, prompt-matrix, and Batch D live proof",
            "command": [
                python,
                str(config.config_root / "scripts" / "validate_skill_release_gate.py"),
                "--profile",
                config.profile.value if is_v1_1_profile(config.profile) else ReleaseGateProfile.RELEASE_CANDIDATE.value,
                "--config-root",
                str(config.config_root),
                "--controller-base-url",
                config.controller_base_url,
                "--workflow-router-gateway-base-url",
                config.workflow_router_gateway_base_url,
                "--anythingllm-api-base-url",
                config.anythingllm_api_base_url,
                "--workspace",
                config.workspace,
                "--timeout-seconds",
                str(config.timeout_seconds),
                *targets,
            ],
        },
    ]
    final_commands: list[dict[str, Any]] = []
    if is_v1_1_profile(config.profile):
        final_commands = [
            {
                "id": "security_policy",
                "description": "Release-candidate security policy gate for secrets, roots, fixtures, commands, and onboarding prompts",
                "command": [
                    python,
                    str(config.config_root / "scripts" / "validate_security_policy.py"),
                    "--config-root",
                    str(config.config_root),
                ],
            },
            {
                "id": "run_observability",
                "description": "Recent workflow-router run observability report",
                "command": [
                    python,
                    str(config.config_root / "scripts" / "report_run_observability.py"),
                    "--config-root",
                    str(config.config_root),
                    "--workflow",
                    "workflow_router.plan",
                    "--limit",
                    "30",
                    "--format",
                    "json",
                    "--output-path",
                    str(config.config_root / "runtime-state" / "run-observability" / "v1-1-release-candidate.json"),
                ],
            },
        ]
    return [*setup_commands, *base_commands, *final_commands]


def execute_suite_commands(config: V1AcceptanceConfig) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in suite_commands(config):
        result = subprocess.run(
            item["command"],
            check=False,
            capture_output=True,
            text=True,
            timeout=config.command_timeout_seconds,
        )
        results.append(
            {
                **item,
                "status": "passed" if result.returncode == 0 else "failed",
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-4000:],
                "stderr_tail": result.stderr[-4000:],
            }
        )
    return results


def report_path_from_stdout(stdout: str, prefix: str) -> Path | None:
    for line in reversed(stdout.splitlines()):
        if line.startswith(prefix):
            path = line[len(prefix) :].strip()
            return Path(path) if path else None
    return None


def load_report_from_suite(suite_runs: list[dict[str, Any]], suite_id: str, prefix: str) -> dict[str, Any]:
    suite = next((item for item in suite_runs if item.get("id") == suite_id), None)
    if not suite:
        return {"status": "missing_suite", "suite_id": suite_id}
    path = report_path_from_stdout(str(suite.get("stdout_tail") or ""), prefix)
    if path is None:
        return {"status": "missing_report_path", "suite_id": suite_id}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed_to_load", "suite_id": suite_id, "report_path": str(path), "error": f"{type(exc).__name__}: {exc}"}
    if not isinstance(report, dict):
        return {"status": "invalid_report", "suite_id": suite_id, "report_path": str(path)}
    report["report_path"] = str(path)
    return report


def suite_by_id(suite_runs: list[dict[str, Any]], suite_id: str) -> dict[str, Any] | None:
    return next((item for item in suite_runs if item.get("id") == suite_id), None)


def suite_status_map(suite_runs: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(item.get("id")): str(item.get("status"))
        for item in suite_runs
        if isinstance(item.get("id"), str) and isinstance(item.get("status"), str)
    }


def command_arg_value(command: object, arg_name: str) -> str | None:
    if not isinstance(command, list):
        return None
    for index, item in enumerate(command):
        if item == arg_name and index + 1 < len(command) and isinstance(command[index + 1], str):
            return command[index + 1]
    return None


def load_report_from_suite_output_path(suite_runs: list[dict[str, Any]], suite_id: str) -> dict[str, Any]:
    suite = suite_by_id(suite_runs, suite_id)
    if not suite:
        return {"status": "missing_suite", "suite_id": suite_id}
    raw_path = command_arg_value(suite.get("command"), "--output-path")
    if not raw_path:
        return {"status": "missing_output_path", "suite_id": suite_id}
    path = Path(raw_path)
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed_to_load", "suite_id": suite_id, "report_path": str(path), "error": f"{type(exc).__name__}: {exc}"}
    if not isinstance(report, dict):
        return {"status": "invalid_report", "suite_id": suite_id, "report_path": str(path)}
    report["report_path"] = str(path)
    return report


def stdout_json_summary_from_suite(suite_runs: list[dict[str, Any]], suite_id: str, prefix: str) -> dict[str, Any]:
    suite = suite_by_id(suite_runs, suite_id)
    if not suite:
        return {"status": "missing_suite", "suite_id": suite_id}
    for line in str(suite.get("stdout_tail") or "").splitlines():
        if line.startswith(prefix):
            try:
                summary = json.loads(line[len(prefix) :].strip())
            except json.JSONDecodeError as exc:
                return {"status": "failed_to_parse", "suite_id": suite_id, "error": str(exc)}
            return summary if isinstance(summary, dict) else {"status": "invalid_summary", "suite_id": suite_id}
    return {"status": "missing_summary", "suite_id": suite_id}


def compact_report_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "kind": report.get("kind"),
        "report_path": report.get("report_path"),
        "summary": report.get("summary") if isinstance(report.get("summary"), dict) else {},
        "errors": report.get("errors") if isinstance(report.get("errors"), list) else [],
    }


def founder_field_summary_from_suites(suite_runs: list[dict[str, Any]]) -> dict[str, Any]:
    report = load_report_from_suite(suite_runs, "founder_field_prompts", "FOUNDER FIELD REPORT ")
    cases = report.get("cases") if isinstance(report.get("cases"), list) else []
    return {
        "status": report.get("status"),
        "report_path": report.get("report_path"),
        "prompt_count": len(cases),
        "summary": report.get("summary") if isinstance(report.get("summary"), dict) else {},
        "errors": report.get("errors") if isinstance(report.get("errors"), list) else [],
    }


def first_time_user_doctor_summary_from_suites(suite_runs: list[dict[str, Any]]) -> dict[str, Any]:
    return compact_report_summary(load_report_from_suite(suite_runs, "first_time_user_doctor", "FIRST TIME USER DOCTOR REPORT "))


def release_channel_summary_from_suites(suite_runs: list[dict[str, Any]]) -> dict[str, Any]:
    report = load_report_from_suite(suite_runs, "release_channels", "RELEASE CHANNEL REPORT ")
    summary = compact_report_summary(report)
    summary["channel_ids"] = report.get("channel_ids") if isinstance(report.get("channel_ids"), list) else []
    summary["selected_channel"] = report.get("selected_channel")
    return summary


def security_policy_summary_from_suites(suite_runs: list[dict[str, Any]]) -> dict[str, Any]:
    return compact_report_summary(load_report_from_suite(suite_runs, "security_policy", "SECURITY POLICY REPORT "))


def docs_index_summary_from_suites(suite_runs: list[dict[str, Any]]) -> dict[str, Any]:
    return stdout_json_summary_from_suite(suite_runs, "docs_index", "DOCS INDEX SUMMARY ")


def observability_summary_from_suites(suite_runs: list[dict[str, Any]]) -> dict[str, Any]:
    report = load_report_from_suite_output_path(suite_runs, "run_observability")
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    runs = report.get("runs") if isinstance(report.get("runs"), list) else []
    status = report.get("status")
    if status is None and report.get("kind") == "controller_run_observability_report":
        status = "passed"
    return {
        "status": status,
        "kind": report.get("kind"),
        "report_path": report.get("report_path"),
        "run_count": len(runs),
        "metrics": metrics,
        "filters": report.get("filters") if isinstance(report.get("filters"), dict) else {},
    }


def openai_base_url(base_url: str) -> str:
    value = base_url.rstrip("/")
    return value if value.endswith("/v1") else f"{value}/v1"


def model_probe_summary(config: V1AcceptanceConfig) -> dict[str, Any]:
    url = f"{openai_base_url(config.candidate_model_base_url)}/models"
    try:
        status, body = json_request(url, timeout_seconds=min(30, config.timeout_seconds))
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "url": url, "error": f"{type(exc).__name__}: {exc}", "model_ids": []}
    data = body.get("data") if isinstance(body, dict) else None
    model_ids = [
        item["id"]
        for item in data or []
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    return {
        "status": "passed" if status == 200 else "failed",
        "url": url,
        "http_status": status,
        "model_ids": model_ids,
    }


def model_portability_summary_for_acceptance(report: dict[str, Any], model_probe: dict[str, Any]) -> dict[str, Any]:
    error_count = len(report.get("errors") if isinstance(report.get("errors"), list) else [])
    failed_suites = [
        item.get("id")
        for item in report.get("suite_runs") or []
        if isinstance(item, dict) and item.get("status") != "passed"
    ]
    return {
        "status": "passed" if report.get("status") == "passed" and model_probe.get("status") == "passed" else "failed",
        "candidate_model_probe": model_probe,
        "classification_summary": {
            "harness": error_count,
            "suite": len(failed_suites),
            "model_quality": 0,
            "classifier": 0,
            "prompt": 0,
            "unknown": 0,
        },
        "failed_suites": failed_suites,
        "advisory_only": True,
    }


def v1_1_proof_summary(report: dict[str, Any]) -> dict[str, Any]:
    statuses = suite_status_map(report.get("suite_runs") if isinstance(report.get("suite_runs"), list) else [])
    return {
        "route": {
            "representative_l1": statuses.get("representative_l1"),
            "representative_l2": statuses.get("representative_l2"),
            "task_decomposition": statuses.get("task_decomposition"),
        },
        "skill": report.get("skill_library_health") if isinstance(report.get("skill_library_health"), dict) else {},
        "model": report.get("model_portability") if isinstance(report.get("model_portability"), dict) else {},
        "fixture": {
            "target_roots": report.get("target_roots"),
            "fixture_state_recorded": bool(report.get("fixture_state")),
        },
        "anythingllm": {
            "preflight": report.get("anythingllm_preflight"),
            "json_output_count": len(report.get("json_output") if isinstance(report.get("json_output"), list) else []),
            "feedback_count": len(report.get("feedback") if isinstance(report.get("feedback"), list) else []),
        },
        "mutation": {
            "controlled_apply": statuses.get("controlled_apply"),
            "policy": "disposable_copy_only",
        },
        "docs": report.get("docs_index") if isinstance(report.get("docs_index"), dict) else {},
        "security": report.get("security_policy") if isinstance(report.get("security_policy"), dict) else {},
        "onboarding": {
            "external_tester_onboarding": statuses.get("external_tester_onboarding"),
        },
        "observability": report.get("observability") if isinstance(report.get("observability"), dict) else {},
    }


def skill_library_health_from_suites(suite_runs: list[dict[str, Any]]) -> dict[str, Any]:
    report = load_report_from_suite(suite_runs, "skill_library_release_gate", "SKILL RELEASE GATE REPORT ")
    commands = report.get("commands") if isinstance(report.get("commands"), list) else []
    live_suite_statuses = {
        str(item.get("label")): item.get("status")
        for item in commands
        if isinstance(item, dict) and isinstance(item.get("label"), str)
    }
    generated_reports = report.get("generated_reports") if isinstance(report.get("generated_reports"), dict) else {}
    return {
        "status": report.get("status"),
        "profile": report.get("profile"),
        "profile_contract": report.get("profile_contract") if isinstance(report.get("profile_contract"), dict) else {},
        "report_path": report.get("report_path"),
        "catalog_summary": report.get("catalog_summary") if isinstance(report.get("catalog_summary"), dict) else {},
        "prompt_catalog_summary": report.get("prompt_catalog_summary")
        if isinstance(report.get("prompt_catalog_summary"), dict)
        else {},
        "generated_reports": generated_reports,
        "batch_d_live_report": generated_reports.get("batch_d_live_report"),
        "live_suite_statuses": live_suite_statuses,
        "errors": report.get("errors") if isinstance(report.get("errors"), list) else [],
    }


def validate_json_payload_text(text: str, label: str, target_root: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} JSON output was not valid JSON for {target_root}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} JSON output was not an object for {target_root}")
    if value.get("output_format") != "json":
        raise RuntimeError(f"{label} JSON output did not preserve output_format=json for {target_root}")
    summary = value.get("summary")
    if not isinstance(summary, dict) or summary.get("selected_workflow") != "code_investigation.plan":
        raise RuntimeError(f"{label} JSON output did not route to code_investigation.plan for {target_root}")
    return value


def validate_json_output(config: V1AcceptanceConfig, api_key: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for target_root in config.target_roots:
        status, body = json_request(
            f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
            payload={
                "model": "agentic-workflow-router",
                "output_format": "json",
                "messages": [{"role": "user", "content": explain_prompt(target_root, json_output=True)}],
            },
            timeout_seconds=config.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(f"gateway JSON output returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        gateway_json = validate_json_payload_text(text_response(body), "gateway", target_root)
        status, body = json_request(
            f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
            payload={
                "message": explain_prompt(target_root, json_output=True),
                "mode": "chat",
                "sessionId": f"v1-acceptance-json-{uuid.uuid4().hex}",
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout_seconds=config.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(f"AnythingLLM JSON output returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        anythingllm_json = validate_json_payload_text(text_response(body), "AnythingLLM", target_root)
        results.append(
            {
                "target_root": target_root,
                "gateway_run_id": gateway_json.get("run_id"),
                "anythingllm_run_id": anythingllm_json.get("run_id"),
                "status": "passed",
            }
        )
    return results


def require_format_a_text(text: str, label: str, target_root: str) -> str:
    required = [
        "workflow_router.plan completed",
        "run_id: workflow-router-",
        "Answer:",
        "Inputs:",
        "Outputs:",
        "Side effects:",
        "Related tests:",
    ]
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise RuntimeError(f"{label} FormatA text missing markers for {target_root}: {missing}")
    return run_id_from_text(text)


def validate_feedback(config: V1AcceptanceConfig, api_key: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for target_root in config.target_roots:
        status, body = json_request(
            f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
            payload={
                "model": "agentic-workflow-router",
                "messages": [{"role": "user", "content": explain_prompt(target_root)}],
            },
            timeout_seconds=config.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(f"gateway feedback seed returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        gateway_run_id = require_format_a_text(text_response(body), "gateway", target_root)
        feedback_message = (
            f"Record feedback for run {gateway_run_id}: useful: inline answer was chat visible. "
            "missing: none for V1 acceptance."
        )
        status, feedback_body = json_request(
            f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
            payload={"model": "agentic-workflow-router", "messages": [{"role": "user", "content": feedback_message}]},
            timeout_seconds=config.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(f"gateway feedback returned HTTP {status}: {json.dumps(feedback_body, ensure_ascii=True)}")
        gateway_feedback_text = text_response(feedback_body)
        if "workflow_feedback.record" not in gateway_feedback_text or "feedback_record" not in gateway_feedback_text:
            raise RuntimeError(f"gateway feedback text missing workflow markers for {target_root}")
        gateway_feedback_run_id = run_id_from_text(gateway_feedback_text)
        gateway_feedback_context = require_feedback_record_context(config, gateway_feedback_run_id, "gateway", target_root)

        status, body = json_request(
            f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
            payload={
                "message": explain_prompt(target_root),
                "mode": "chat",
                "sessionId": f"v1-acceptance-feedback-seed-{uuid.uuid4().hex}",
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout_seconds=config.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(f"AnythingLLM feedback seed returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        anythingllm_run_id = require_format_a_text(text_response(body), "AnythingLLM", target_root)
        feedback_message = (
            f"Record feedback for run {anythingllm_run_id}: useful: AnythingLLM response was chat visible. "
            "missing: none for V1 acceptance."
        )
        status, feedback_body = json_request(
            f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
            payload={
                "message": feedback_message,
                "mode": "chat",
                "sessionId": f"v1-acceptance-feedback-{uuid.uuid4().hex}",
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout_seconds=config.timeout_seconds,
        )
        if status != 200:
            raise RuntimeError(f"AnythingLLM feedback returned HTTP {status}: {json.dumps(feedback_body, ensure_ascii=True)}")
        anythingllm_feedback_text = text_response(feedback_body)
        if "workflow_feedback.record" not in anythingllm_feedback_text or "feedback_record" not in anythingllm_feedback_text:
            raise RuntimeError(f"AnythingLLM feedback text missing workflow markers for {target_root}")
        anythingllm_feedback_run_id = run_id_from_text(anythingllm_feedback_text)
        anythingllm_feedback_context = require_feedback_record_context(
            config,
            anythingllm_feedback_run_id,
            "AnythingLLM",
            target_root,
        )
        results.append(
            {
                "target_root": target_root,
                "gateway_seed_run_id": gateway_run_id,
                "gateway_feedback_run_id": gateway_feedback_run_id,
                "gateway_feedback_context": gateway_feedback_context,
                "anythingllm_seed_run_id": anythingllm_run_id,
                "anythingllm_feedback_run_id": anythingllm_feedback_run_id,
                "anythingllm_feedback_context": anythingllm_feedback_context,
                "status": "passed",
            }
        )
    return results


def require_feedback_record_context(
    config: V1AcceptanceConfig,
    feedback_run_id: str,
    label: str,
    target_root: str,
) -> dict[str, Any]:
    status, run_body = json_request(
        f"{config.controller_base_url.rstrip('/')}/v1/controller/runs/{feedback_run_id}",
        timeout_seconds=config.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"{label} feedback run lookup returned HTTP {status}: {json.dumps(run_body, ensure_ascii=True)}")
    artifacts = run_body.get("artifacts") if isinstance(run_body.get("artifacts"), dict) else {}
    feedback_record_path = artifacts.get("feedback_record")
    if not isinstance(feedback_record_path, str) or not feedback_record_path:
        raise RuntimeError(f"{label} feedback run missing feedback_record artifact for {target_root}")
    try:
        record = json.loads(Path(feedback_record_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} feedback record is not readable for {target_root}: {exc}") from exc
    context = record.get("feedback_context") if isinstance(record, dict) else None
    next_action = record.get("next_action") if isinstance(record, dict) else None
    classifications = record.get("classifications") if isinstance(record, dict) else None
    if not isinstance(context, dict) or not isinstance(next_action, dict) or not isinstance(classifications, list):
        raise RuntimeError(f"{label} feedback record missing Phase 67 structured fields for {target_root}")
    if context.get("selected_workflow") != "code_investigation.plan":
        raise RuntimeError(f"{label} feedback context selected wrong workflow for {target_root}: {context.get('selected_workflow')}")
    selected_skills = context.get("selected_skills") if isinstance(context.get("selected_skills"), list) else []
    if "code-explanation-summarizer" not in selected_skills:
        raise RuntimeError(f"{label} feedback context missing selected skill for {target_root}: {selected_skills}")
    if context.get("target_root") != target_root:
        raise RuntimeError(f"{label} feedback context target_root mismatch for {target_root}: {context.get('target_root')}")
    downstream_keys = context.get("downstream_artifact_keys") if isinstance(context.get("downstream_artifact_keys"), list) else []
    if "code_explanation" not in downstream_keys:
        raise RuntimeError(f"{label} feedback context missing code_explanation artifact for {target_root}")
    if not {"useful", "missing"}.issubset(set(str(item) for item in classifications)):
        raise RuntimeError(f"{label} feedback classifications missing useful/missing for {target_root}: {classifications}")
    if next_action.get("mutation_policy") != "controller_artifacts_only":
        raise RuntimeError(f"{label} feedback next action has unsafe mutation policy for {target_root}: {next_action}")
    return {
        "selected_workflow": context.get("selected_workflow"),
        "selected_skills": selected_skills,
        "route_rules": context.get("route_rules"),
        "downstream_artifact_keys": downstream_keys,
        "classifications": classifications,
        "next_action": next_action,
        "semantic_status": context.get("semantic_status"),
    }


def anythingllm_preflight(config: V1AcceptanceConfig, api_key: str) -> dict[str, Any]:
    ping_status, ping_body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/ping",
        timeout_seconds=config.timeout_seconds,
    )
    workspace_status, workspace_body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspaces",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    workspaces = workspace_body.get("workspaces") if isinstance(workspace_body, dict) else None
    slugs = [
        item["slug"]
        for item in workspaces or []
        if isinstance(item, dict) and isinstance(item.get("slug"), str)
    ]
    return {
        "status": "passed" if ping_status == 200 and workspace_status == 200 and config.workspace in slugs else "failed",
        "ping_status": ping_status,
        "workspace_status": workspace_status,
        "workspace": config.workspace,
        "workspace_found": config.workspace in slugs,
        "ping": ping_body,
    }


def acceptance_failure_guidance(errors: list[str]) -> list[str]:
    text = "\n".join(errors)
    guidance: list[str] = []
    if "ANYTHINGLLM_API_KEY" in text:
        guidance.append("Set ANYTHINGLLM_API_KEY in the Bash environment before running acceptance.")
    if "health check failed" in text:
        guidance.append("Restart the harness with start-agent-prompt-proxies.sh and confirm localhost 8000 is serving /v1/models.")
    if any(term in text.lower() for term in ("timed out", "timeout", "body bytes", "winerror 10055")):
        guidance.append("Run live validators from Bash; Windows clients can receive headers but time out waiting for body bytes against Bash-hosted localhost services.")
    if "AnythingLLM preflight failed" in text:
        guidance.append("Confirm AnythingLLM is running, the API key is valid, and the configured workspace exists.")
    if "acceptance suite command failed" in text:
        guidance.append("Open the acceptance report and inspect the failed suite stdout_tail and stderr_tail.")
    if "changed protected fixture state" in text:
        guidance.append("Stop testing, inspect the fixture diff, and restore the frozen test repo before another acceptance run.")
    if not guidance and errors:
        guidance.append("Open the acceptance report, fix the first listed error, and rerun the same command.")
    return guidance


def run_v1_acceptance(config: V1AcceptanceConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = config.output_path or default_report_path(config_root)
    api_key = os.environ.get(config.api_key_env)
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "v1_acceptance_report",
        "profile": config.profile.value,
        "profile_contract": release_gate_profile_contract_json(config.profile),
        "status": "failed",
        "config_root": str(config_root),
        "candidate_model_base_url": config.candidate_model_base_url,
        "target_roots": list(config.target_roots),
        "workflow_router_gateway_base_url": config.workflow_router_gateway_base_url,
        "controller_base_url": config.controller_base_url,
        "anythingllm_api_base_url": config.anythingllm_api_base_url,
        "workspace": config.workspace,
        "created_at": utc_timestamp(),
        "health": [],
        "anythingllm_preflight": {},
        "suite_runs": [],
        "first_time_user_doctor": {},
        "docs_index": {},
        "release_channels": {},
        "security_policy": {},
        "observability": {},
        "founder_field_summary": {},
        "skill_library_health": {},
        "model_portability": {},
        "proof_summary": {},
        "known_limitations": V1_1_KNOWN_LIMITATIONS if is_v1_1_profile(config.profile) else [],
        "next_recommended_phase": (
            "Review V1.1 release-candidate proof, then decide whether to promote stable or plan the next governed L1/L2 expansion."
            if is_v1_1_profile(config.profile)
            else ""
        ),
        "json_output": [],
        "feedback": [],
        "fixture_state": {},
        "errors": [],
    }
    try:
        if not api_key:
            raise RuntimeError(f"{config.api_key_env} is required")
        before = fixture_state(config.target_roots)
        report["health"] = health_check(min(30, config.timeout_seconds))
        failed_health = [item for item in report["health"] if item.get("status") != "passed" or item.get("http_status") != 200]
        if failed_health:
            raise RuntimeError(f"health check failed: {json.dumps(failed_health, ensure_ascii=True)}")
        report["anythingllm_preflight"] = anythingllm_preflight(config, api_key)
        if report["anythingllm_preflight"].get("status") != "passed":
            raise RuntimeError("AnythingLLM preflight failed")
        model_probe = model_probe_summary(config) if is_v1_1_profile(config.profile) else {}
        if is_v1_1_profile(config.profile) and model_probe.get("status") != "passed":
            raise RuntimeError(f"model probe failed: {json.dumps(model_probe, ensure_ascii=True)}")
        report["suite_runs"] = execute_suite_commands(config)
        if is_v1_1_profile(config.profile):
            report["first_time_user_doctor"] = first_time_user_doctor_summary_from_suites(report["suite_runs"])
            report["docs_index"] = docs_index_summary_from_suites(report["suite_runs"])
            report["release_channels"] = release_channel_summary_from_suites(report["suite_runs"])
            report["security_policy"] = security_policy_summary_from_suites(report["suite_runs"])
            report["observability"] = observability_summary_from_suites(report["suite_runs"])
        report["founder_field_summary"] = founder_field_summary_from_suites(report["suite_runs"])
        report["skill_library_health"] = skill_library_health_from_suites(report["suite_runs"])
        failed_suites = [item for item in report["suite_runs"] if item.get("status") != "passed"]
        if failed_suites:
            raise RuntimeError(f"acceptance suite command failed: {json.dumps(failed_suites, ensure_ascii=True)}")
        report["json_output"] = validate_json_output(config, api_key)
        assert_fixture_state_unchanged(before, config.target_roots, "json output")
        report["feedback"] = validate_feedback(config, api_key)
        assert_fixture_state_unchanged(before, config.target_roots, "feedback")
        report["fixture_state"] = fixture_state(config.target_roots)
        report["status"] = "passed"
        if is_v1_1_profile(config.profile):
            report["model_portability"] = model_portability_summary_for_acceptance(report, model_probe)
            report["proof_summary"] = v1_1_proof_summary(report)
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        if is_v1_1_profile(config.profile):
            report["model_portability"] = model_portability_summary_for_acceptance(report, report.get("model_portability", {}))
            report["proof_summary"] = v1_1_proof_summary(report)
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
