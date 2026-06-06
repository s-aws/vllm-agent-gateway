"""External tester onboarding prompt pack validation."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.v1 import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKSPACE,
    fixture_state,
    json_request,
    run_id_from_text,
    text_response,
)


SCHEMA_VERSION = 1
DEFAULT_ONBOARDING_PACK_PATH = Path("runtime") / "external_tester_onboarding.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "external-tester-onboarding"
CASE_ID_RE = re.compile(r"^ONB-\d{3}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
FORBIDDEN_FIRST_TEST_TERMS = (
    "refactor",
    "single path",
    "single-path",
    "apply",
    "mutate",
    "edit files",
    "draft only",
    "implementation prep",
    "packet_operations",
)
REQUIRED_FEEDBACK_CATEGORIES = (
    "confusing",
    "routing_miss",
    "answer_quality_miss",
    "setup_failure",
)


class OnboardingValidationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class OnboardingValidationConfig:
    config_root: Path
    pack_path: Path = DEFAULT_ONBOARDING_PACK_PATH
    output_path: Path | None = None
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 900
    live_anythingllm: bool = False
    include_feedback: bool = False
    case_ids: tuple[str, ...] = ()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"external-tester-onboarding-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_pack_path(config_root: Path, pack_path: Path) -> Path:
    return pack_path if pack_path.is_absolute() else config_root / pack_path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def relative_exists(config_root: Path, raw_path: object) -> bool:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return False
    path = Path(raw_path)
    return path.exists() if path.is_absolute() else (config_root / path).exists()


def check(check_id: str, status: OnboardingValidationStatus, message: str, *, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status.value,
        "message": message,
        "details": details or {},
    }


def pack_cases(pack: dict[str, Any]) -> list[dict[str, Any]]:
    raw_cases = pack.get("cases")
    if not isinstance(raw_cases, list):
        return []
    return [item for item in raw_cases if isinstance(item, dict)]


def selected_cases(pack: dict[str, Any], case_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    cases = pack_cases(pack)
    if not case_ids:
        return cases
    wanted = {case_id.upper() for case_id in case_ids}
    return [case for case in cases if str(case.get("case_id", "")).upper() in wanted]


def validate_pack_contract(pack: dict[str, Any], *, config_root: Path, pack_path: Path, case_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    if pack.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if pack.get("kind") != "external_tester_onboarding_pack":
        errors.append("kind must be external_tester_onboarding_pack")
    version = pack.get("version")
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        errors.append("version must be semantic version x.y.z")
    if pack.get("release_channel") != "release-candidate":
        errors.append("release_channel must be release-candidate")
    docs = string_list(pack.get("docs"))
    examples = string_list(pack.get("examples"))
    missing_docs = [item for item in docs if not relative_exists(config_root, item)]
    missing_examples = [item for item in examples if not relative_exists(config_root, item)]
    if missing_docs:
        errors.append(f"docs missing files: {missing_docs}")
    if missing_examples:
        errors.append(f"examples missing files: {missing_examples}")
    cases = pack_cases(pack)
    if not cases:
        errors.append("cases must contain at least one onboarding prompt")
    ids = [str(case.get("case_id", "")) for case in cases]
    if len(ids) != len(set(ids)):
        errors.append("case_id values must be unique")
    selected = selected_cases(pack, case_ids)
    missing_requested = sorted(set(case_ids) - {str(case.get("case_id", "")) for case in selected})
    if missing_requested:
        errors.append(f"requested case_id values are missing: {missing_requested}")
    feedback_templates = pack.get("feedback_templates")
    if not isinstance(feedback_templates, dict):
        errors.append("feedback_templates must be an object")
    else:
        missing_categories = [category for category in REQUIRED_FEEDBACK_CATEGORIES if category not in feedback_templates]
        if missing_categories:
            errors.append(f"feedback_templates missing categories: {missing_categories}")
    checks.append(
        check(
            "pack.contract",
            OnboardingValidationStatus.PASSED if not errors else OnboardingValidationStatus.FAILED,
            "Onboarding pack contract is valid." if not errors else "Onboarding pack contract is invalid.",
            details={
                "pack_path": str(pack_path),
                "version": version,
                "release_channel": pack.get("release_channel"),
                "case_count": len(cases),
                "selected_case_ids": [str(case.get("case_id")) for case in selected],
                "errors": errors,
            },
        )
    )
    return checks


def validate_case_contracts(pack: dict[str, Any], *, case_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for case in selected_cases(pack, case_ids):
        case_id = str(case.get("case_id", ""))
        errors: list[str] = []
        if not CASE_ID_RE.fullmatch(case_id):
            errors.append("case_id must match ONB-###")
        for field in ("title", "level", "target_root", "prompt", "expected_workflow", "mutation_policy"):
            if not isinstance(case.get(field), str) or not str(case.get(field)).strip():
                errors.append(f"{field} must be a non-empty string")
        if case.get("target_root") not in DEFAULT_TARGET_ROOTS:
            errors.append("target_root must be one of the frozen Coinbase fixtures")
        if case.get("mutation_policy") != "read_only":
            errors.append("mutation_policy must be read_only for first-test prompts")
        prompt_text = str(case.get("prompt", ""))
        forbidden = [term for term in FORBIDDEN_FIRST_TEST_TERMS if term in prompt_text.lower()]
        if forbidden:
            errors.append(f"prompt contains deferred or mutation-capable terms: {forbidden}")
        for field in ("expected_markers", "expected_artifact_keys", "troubleshooting_notes"):
            if not string_list(case.get(field)):
                errors.append(f"{field} must be a non-empty string array")
        checks.append(
            check(
                f"case.{case_id}.contract",
                OnboardingValidationStatus.PASSED if not errors else OnboardingValidationStatus.FAILED,
                f"Onboarding case {case_id} is valid." if not errors else f"Onboarding case {case_id} is invalid.",
                details={"case_id": case_id, "errors": errors},
            )
        )
    return checks


def response_markers(case: dict[str, Any]) -> list[str]:
    markers = [
        "workflow_router.plan completed",
        "run_id: workflow-router-",
        "Result:",
        "Skill Selection:",
        str(case.get("expected_workflow")),
    ]
    markers.extend(string_list(case.get("expected_markers")))
    markers.extend(string_list(case.get("expected_artifact_keys")))
    return markers


def require_markers(text: str, markers: list[str], *, label: str, case_id: str) -> list[str]:
    missing = sorted({marker for marker in markers if marker not in text})
    if missing:
        raise RuntimeError(f"{label} response for {case_id} missed markers: {missing}")
    return missing


def feedback_message(pack: dict[str, Any], run_id: str) -> str:
    templates = pack.get("feedback_templates") if isinstance(pack.get("feedback_templates"), dict) else {}
    answer_quality = templates.get("answer_quality_miss") if isinstance(templates.get("answer_quality_miss"), dict) else {}
    template = str(answer_quality.get("message_template") or "")
    if "{run_id}" not in template:
        return (
            f"Record feedback for run {run_id}: useful: onboarding answer was visible in chat. "
            "missing: none for Phase 88 onboarding validation."
        )
    return template.format(run_id=run_id)


def require_feedback_text(text: str, *, run_id: str) -> str:
    markers = ("workflow_feedback.record", "run_id: workflow-feedback-", "target_run_id", run_id, "feedback_record")
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise RuntimeError(f"feedback response missed markers: {missing}")
    return run_id_from_text(text)


def anythingllm_preflight(config: OnboardingValidationConfig, api_key: str) -> dict[str, Any]:
    ping_status, ping_body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/ping",
        timeout_seconds=min(30, config.timeout_seconds),
    )
    workspace_status, workspace_body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspaces",
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


def run_anythingllm_case(config: OnboardingValidationConfig, pack: dict[str, Any], case: dict[str, Any], api_key: str) -> dict[str, Any]:
    case_id = str(case.get("case_id"))
    target_root = str(case.get("target_root"))
    before_state = fixture_state((target_root,))
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload={
            "message": str(case.get("prompt")),
            "mode": "chat",
            "sessionId": f"external-onboarding-{case_id.lower()}-{uuid.uuid4().hex}",
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    result: dict[str, Any] = {
        "case_id": case_id,
        "target_root": target_root,
        "http_status": status,
        "status": OnboardingValidationStatus.FAILED.value,
        "run_id": "unknown",
        "feedback_run_id": None,
        "errors": [],
    }
    if status != 200:
        result["errors"].append(f"AnythingLLM returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        return result
    text = text_response(body)
    try:
        require_markers(text, response_markers(case), label="AnythingLLM", case_id=case_id)
        result["run_id"] = run_id_from_text(text)
        if result["run_id"] == "unknown":
            raise RuntimeError("response did not expose a workflow-router run_id")
        if config.include_feedback:
            feedback_status, feedback_body = json_request(
                f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
                payload={
                    "message": feedback_message(pack, str(result["run_id"])),
                    "mode": "chat",
                    "sessionId": f"external-onboarding-feedback-{uuid.uuid4().hex}",
                },
                headers={"Authorization": f"Bearer {api_key}"},
                timeout_seconds=config.timeout_seconds,
            )
            if feedback_status != 200:
                raise RuntimeError(f"AnythingLLM feedback returned HTTP {feedback_status}: {json.dumps(feedback_body, ensure_ascii=True)}")
            result["feedback_run_id"] = require_feedback_text(text_response(feedback_body), run_id=str(result["run_id"]))
        after_state = fixture_state((target_root,))
        if before_state != after_state:
            raise RuntimeError("onboarding prompt or feedback changed protected fixture state")
        result["status"] = OnboardingValidationStatus.PASSED.value
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    return result


def run_live_anythingllm(config: OnboardingValidationConfig, pack: dict[str, Any], api_key: str) -> dict[str, Any]:
    preflight = anythingllm_preflight(config, api_key)
    if preflight.get("status") != "passed":
        return {
            "status": OnboardingValidationStatus.FAILED.value,
            "preflight": preflight,
            "cases": [],
            "errors": ["AnythingLLM preflight failed"],
        }
    cases = selected_cases(pack, config.case_ids)
    results = [run_anythingllm_case(config, pack, case, api_key) for case in cases]
    errors = [
        error
        for result in results
        for error in result.get("errors", [])
        if isinstance(error, str)
    ]
    return {
        "status": OnboardingValidationStatus.PASSED.value if not errors else OnboardingValidationStatus.FAILED.value,
        "preflight": preflight,
        "cases": results,
        "errors": errors,
    }


def validate_external_tester_onboarding(config: OnboardingValidationConfig, *, api_key: str | None = None) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    pack_path = resolve_pack_path(config_root, config.pack_path)
    output_path = config.output_path or default_report_path(config_root)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "external_tester_onboarding_validation_report",
        "status": OnboardingValidationStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "pack_path": str(pack_path),
        "selected_case_ids": list(config.case_ids),
        "live_anythingllm": config.live_anythingllm,
        "include_feedback": config.include_feedback,
        "checks": [],
        "live": {"status": OnboardingValidationStatus.SKIPPED.value, "cases": [], "errors": []},
        "summary": {},
    }
    try:
        pack = read_json_object(pack_path)
        checks = [
            *validate_pack_contract(pack, config_root=config_root, pack_path=pack_path, case_ids=config.case_ids),
            *validate_case_contracts(pack, case_ids=config.case_ids),
        ]
        live = {"status": OnboardingValidationStatus.SKIPPED.value, "cases": [], "errors": []}
        if config.live_anythingllm:
            if not api_key:
                live = {
                    "status": OnboardingValidationStatus.FAILED.value,
                    "cases": [],
                    "errors": [f"{config.api_key_env} is required for live AnythingLLM onboarding validation"],
                }
            else:
                live = run_live_anythingllm(config, pack, api_key)
    except Exception as exc:  # noqa: BLE001
        checks = [
            check(
                "pack.load",
                OnboardingValidationStatus.FAILED,
                f"Onboarding pack could not be loaded: {type(exc).__name__}: {exc}",
            )
        ]
        live = {"status": OnboardingValidationStatus.SKIPPED.value, "cases": [], "errors": []}
    failed_check_ids = [item["id"] for item in checks if item.get("status") == OnboardingValidationStatus.FAILED.value]
    live_errors = live.get("errors") if isinstance(live.get("errors"), list) else []
    report["checks"] = checks
    report["live"] = live
    report["summary"] = {
        "check_count": len(checks),
        "failed_check_ids": failed_check_ids,
        "case_count": len([item for item in checks if str(item.get("id", "")).startswith("case.")]),
        "live_status": live.get("status"),
        "live_case_count": len(live.get("cases") if isinstance(live.get("cases"), list) else []),
        "live_error_count": len(live_errors),
        "feedback_count": sum(1 for item in live.get("cases", []) if isinstance(item, dict) and item.get("feedback_run_id")),
    }
    report["status"] = (
        OnboardingValidationStatus.PASSED.value
        if not failed_check_ids and not live_errors
        else OnboardingValidationStatus.FAILED.value
    )
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
