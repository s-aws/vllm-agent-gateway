"""Consolidated current-local-model release adherence gate."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from vllm_agent_gateway.acceptance.model_capability_profile import (
    CapabilityStatus,
    ModelCapabilityProfileConfig,
    run_model_capability_profile,
)
from vllm_agent_gateway.acceptance.model_portability import (
    ModelPortabilityConfig,
    run_model_portability,
)
from vllm_agent_gateway.acceptance.profiles import ReleaseGateProfile
from vllm_agent_gateway.acceptance.v1 import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKSPACE,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    HEALTH_TARGETS,
    V1AcceptanceConfig,
    run_v1_acceptance,
)
from vllm_agent_gateway.anythingllm_ui_e2e import (
    AnythingLLMUiE2EConfig,
    run_anythingllm_ui_e2e,
)


SCHEMA_VERSION = 1
DEFAULT_REPORT_DIR = Path("runtime-state") / "release-adherence"
MAX_MESSAGE_CHARS = 1600
REQUIRED_V1_1_SUITE_IDS = {
    "first_time_user_doctor",
    "docs_index",
    "release_channels",
    "representative_l1",
    "representative_l2",
    "task_decomposition",
    "controlled_apply",
    "inline_format_a",
    "external_tester_onboarding",
    "founder_field_prompts",
    "skill_library_release_gate",
    "security_policy",
    "run_observability",
}
REQUIRED_UI_CASE_IDS = {"L1-001", "L1-002"}
PROVEN_CAPABILITY_KEYS = {
    "route_stability",
    "output_contract_reliability",
    "semantic_answer_quality",
    "latency",
    "timeout_behavior",
}


class ReleaseAdherenceStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class FindingSeverity(str, Enum):
    BLOCKER = "blocker"
    WARNING = "warning"
    INFO = "info"


class ReleaseAdherenceFailureClass(str, Enum):
    SETUP = "setup"
    ROUTE = "route"
    SKILL_TOOL_SELECTION = "skill_tool_selection"
    ANSWER_RENDERER = "answer_renderer"
    SEMANTIC_QUALITY = "semantic_quality"
    OUTPUT_CONTRACT = "output_contract"
    MODEL_QUALITY = "model_quality"
    LATENCY = "latency"
    ANYTHINGLLM_CONFIG = "anythingllm_config"
    FIXTURE_MUTATION = "fixture_mutation"
    STALE_ARTIFACT_CONFUSION = "stale_artifact_confusion"
    SECURITY = "security"
    UNKNOWN = "unknown"


CLASSIFICATION_TERMS: tuple[tuple[ReleaseAdherenceFailureClass, tuple[str, ...]], ...] = (
    (ReleaseAdherenceFailureClass.FIXTURE_MUTATION, ("fixture state", "protected fixture", "fixture_unchanged", "mutated", "changed")),
    (ReleaseAdherenceFailureClass.ANYTHINGLLM_CONFIG, ("anythingllm", "stream-chat", "workspace", "api key", "anythingllm_api_key")),
    (ReleaseAdherenceFailureClass.LATENCY, ("latency", "duration", "timeout", "timed out", "body bytes")),
    (ReleaseAdherenceFailureClass.SEMANTIC_QUALITY, ("semantic", "missing_semantic", "missing semantic", "rejected marker", "wrong answer")),
    (ReleaseAdherenceFailureClass.ANSWER_RENDERER, ("format_a", "inline answer", "answer:", "chat visible", "render")),
    (ReleaseAdherenceFailureClass.OUTPUT_CONTRACT, ("json", "schema", "contract", "malformed", "invalid")),
    (ReleaseAdherenceFailureClass.ROUTE, ("route", "selected_workflow", "wrong workflow", "expected_workflow")),
    (ReleaseAdherenceFailureClass.SKILL_TOOL_SELECTION, ("selected skills", "selected tools", "skill selection", "tool selection")),
    (ReleaseAdherenceFailureClass.SECURITY, ("security", "secret", "filesystem", "unsafe")),
    (ReleaseAdherenceFailureClass.STALE_ARTIFACT_CONFUSION, ("stale", "runtime-state", "debug-direct", "old report")),
    (ReleaseAdherenceFailureClass.SETUP, ("health check", "port", "connection refused", "preflight", "not reachable")),
    (ReleaseAdherenceFailureClass.MODEL_QUALITY, ("model_quality", "model quality", "model route output")),
)


@dataclass(frozen=True)
class ReleaseAdherenceConfig:
    config_root: Path
    candidate_id: str = "current-localhost-model"
    candidate_description: str = "Current localhost model behind the workflow-router gateway"
    candidate_model_base_url: str = DEFAULT_MODEL_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    target_roots: tuple[str, ...] = tuple(DEFAULT_TARGET_ROOTS)
    timeout_seconds: int = 900
    command_timeout_seconds: int = 3600
    output_path: Path | None = None
    markdown_output_path: Path | None = None
    python_executable: str | None = None
    ui_dist_root: Path | None = None
    app_asar_path: Path | None = None
    extract_root: Path | None = None
    refresh_extract: bool = False
    npx_command: str | None = None
    browser_channel: str = ""


AcceptanceRunner = Callable[[V1AcceptanceConfig], dict[str, Any]]
UiRunner = Callable[[AnythingLLMUiE2EConfig], dict[str, Any]]
PortabilityRunner = Callable[[ModelPortabilityConfig], dict[str, Any]]
ProfileRunner = Callable[[ModelCapabilityProfileConfig], dict[str, Any]]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"release-adherence-{utc_timestamp()}.json"


def default_markdown_path(report_path: Path) -> Path:
    return report_path.with_suffix(".md")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def bounded_text(value: object, *, limit: int = MAX_MESSAGE_CHARS) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 32] + "...[truncated]"


def classify_message(message: str) -> tuple[ReleaseAdherenceFailureClass, list[str]]:
    lowered = message.lower()
    for classification, terms in CLASSIFICATION_TERMS:
        matches = [term for term in terms if term in lowered]
        if matches:
            return classification, matches
    return ReleaseAdherenceFailureClass.UNKNOWN, []


def finding(
    source: str,
    severity: FindingSeverity,
    message: str,
    *,
    next_action: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    classification, terms = classify_message(message)
    return {
        "source": source,
        "severity": severity.value,
        "classification": classification.value,
        "matched_terms": terms,
        "message": bounded_text(message),
        "details": details or {},
        "next_action": next_action,
    }


def sibling_path(report_path: Path, suffix: str, extension: str = ".json") -> Path:
    return report_path.parent / f"{report_path.stem}-{suffix}{extension}"


def timed_step(step_id: str, action: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    started_at = time.monotonic()
    try:
        result = action()
        duration_seconds = time.monotonic() - started_at
        result_status = str(result.get("status") or "")
        status = (
            ReleaseAdherenceStatus.PASSED.value
            if result_status in {ReleaseAdherenceStatus.PASSED.value, "warning"}
            else ReleaseAdherenceStatus.FAILED.value
        )
        step = {
            "id": step_id,
            "status": status,
            "result_status": result_status,
            "duration_seconds": duration_seconds,
            "report_path": result.get("report_path") or result.get("markdown_report_path") or "",
        }
        return result, step, None
    except Exception as exc:  # noqa: BLE001
        duration_seconds = time.monotonic() - started_at
        message = f"{type(exc).__name__}: {exc}"
        step = {
            "id": step_id,
            "status": ReleaseAdherenceStatus.FAILED.value,
            "duration_seconds": duration_seconds,
            "report_path": "",
            "error": bounded_text(message),
        }
        return {}, step, finding(step_id, FindingSeverity.BLOCKER, message, next_action=f"Fix {step_id} before release.")


def suite_statuses(acceptance_report: dict[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for item in acceptance_report.get("suite_runs") or []:
        if not isinstance(item, dict):
            continue
        suite_id = item.get("id")
        status = item.get("status")
        if isinstance(suite_id, str) and isinstance(status, str):
            statuses[suite_id] = status
    return statuses


def suite_duration_values(acceptance_report: dict[str, Any]) -> list[float]:
    durations: list[float] = []
    for item in acceptance_report.get("suite_runs") or []:
        if isinstance(item, dict) and isinstance(item.get("duration_seconds"), (int, float)):
            durations.append(float(item["duration_seconds"]))
    return durations


def latency_summary(acceptance_report: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    suite_durations = suite_duration_values(acceptance_report)
    step_durations = {
        str(item.get("id")): float(item.get("duration_seconds"))
        for item in steps
        if isinstance(item.get("duration_seconds"), (int, float))
    }
    return {
        "suite_duration_sample_count": len(suite_durations),
        "max_suite_duration_seconds": max(suite_durations) if suite_durations else None,
        "total_suite_duration_seconds": sum(suite_durations) if suite_durations else None,
        "step_duration_seconds": step_durations,
        "latency_measured": bool(suite_durations) and bool(step_durations),
    }


def acceptance_findings(acceptance_report: dict[str, Any], *, expected_target_roots: tuple[str, ...]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if acceptance_report.get("status") != ReleaseAdherenceStatus.PASSED.value:
        findings.append(
            finding(
                "v1_acceptance",
                FindingSeverity.BLOCKER,
                f"V1.1 acceptance status is {acceptance_report.get('status')}",
                next_action="Open the V1.1 acceptance report and fix failed setup, suite, JSON, feedback, or fixture checks.",
            )
        )
    for index, error in enumerate(acceptance_report.get("errors") or []):
        findings.append(
            finding(
                f"v1_acceptance.errors[{index}]",
                FindingSeverity.BLOCKER,
                str(error),
                next_action="Fix the acceptance error before founder release.",
            )
        )
    for item in acceptance_report.get("suite_runs") or []:
        if not isinstance(item, dict) or item.get("status") == ReleaseAdherenceStatus.PASSED.value:
            continue
        findings.append(
            finding(
                f"v1_acceptance.suite[{item.get('id', 'unknown')}]",
                FindingSeverity.BLOCKER,
                "\n".join(str(item.get(key) or "") for key in ("description", "stdout_tail", "stderr_tail")),
                next_action="Rerun the failed suite command and repair the narrowed workflow or setup gap.",
            )
        )
    actual_targets = tuple(acceptance_report.get("target_roots") or ())
    if expected_target_roots and actual_targets != expected_target_roots:
        findings.append(
            finding(
                "v1_acceptance.target_roots",
                FindingSeverity.BLOCKER,
                f"V1.1 acceptance target roots mismatch: expected={expected_target_roots}, actual={actual_targets}",
                next_action="Rerun release adherence with both required frozen fixture roots.",
            )
        )
    health = acceptance_report.get("health") if isinstance(acceptance_report.get("health"), list) else []
    health_by_name = {str(item.get("name")): item for item in health if isinstance(item, dict)}
    for target in HEALTH_TARGETS:
        name = str(target.get("name"))
        item = health_by_name.get(name)
        if not item or item.get("status") != "passed" or item.get("http_status") != 200:
            findings.append(
                finding(
                    f"v1_acceptance.health[{name}]",
                    FindingSeverity.BLOCKER,
                    f"Required health target {name} did not pass: {item}",
                    next_action="Restart the Bash-hosted stack and confirm all featured localhost ports are healthy.",
                )
            )
    statuses = suite_statuses(acceptance_report)
    missing_suites = sorted(REQUIRED_V1_1_SUITE_IDS - set(statuses))
    if missing_suites:
        findings.append(
            finding(
                "v1_acceptance.required_suites",
                FindingSeverity.BLOCKER,
                f"V1.1 acceptance missing required suite IDs: {missing_suites}",
                next_action="Fix the V1.1 acceptance profile so every required release suite is executed.",
            )
        )
    expected_count = len(expected_target_roots)
    json_count = len(acceptance_report.get("json_output") if isinstance(acceptance_report.get("json_output"), list) else [])
    feedback_count = len(acceptance_report.get("feedback") if isinstance(acceptance_report.get("feedback"), list) else [])
    if expected_count and json_count != expected_count:
        findings.append(
            finding(
                "v1_acceptance.json_output_count",
                FindingSeverity.BLOCKER,
                f"V1.1 acceptance JSON output count mismatch: expected={expected_count}, actual={json_count}",
                next_action="Rerun JSON output validation for every target root.",
            )
        )
    if expected_count and feedback_count != expected_count:
        findings.append(
            finding(
                "v1_acceptance.feedback_count",
                FindingSeverity.BLOCKER,
                f"V1.1 acceptance feedback count mismatch: expected={expected_count}, actual={feedback_count}",
                next_action="Rerun feedback validation for every target root.",
            )
        )
    fixture_state = acceptance_report.get("fixture_state") if isinstance(acceptance_report.get("fixture_state"), dict) else {}
    missing_fixture_state = [root for root in expected_target_roots if root not in fixture_state]
    if missing_fixture_state:
        findings.append(
            finding(
                "v1_acceptance.fixture_state",
                FindingSeverity.BLOCKER,
                f"V1.1 acceptance fixture state missing target roots: {missing_fixture_state}",
                next_action="Record fixture hashes and git status for every protected target root.",
            )
        )
    return findings


def ui_findings(ui_report: dict[str, Any], *, expected_target_roots: tuple[str, ...]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if ui_report.get("status") != ReleaseAdherenceStatus.PASSED.value:
        findings.append(
            finding(
                "anythingllm_ui_e2e",
                FindingSeverity.BLOCKER,
                f"AnythingLLM UI E2E status is {ui_report.get('status')}; errors={ui_report.get('errors')}",
                next_action="Fix browser-visible chat quality, stream-chat transport, or fixture mutation before release.",
            )
        )
    if ui_report.get("fixture_unchanged") is False:
        findings.append(
            finding(
                "anythingllm_ui_e2e.fixture",
                FindingSeverity.BLOCKER,
                "AnythingLLM UI E2E changed protected fixture state",
                next_action="Inspect fixture hashes before running more live tests.",
            )
        )
    cases = (ui_report.get("ui") or {}).get("cases", []) if isinstance(ui_report.get("ui"), dict) else []
    expected_pairs = {(root, case_id) for root in expected_target_roots for case_id in REQUIRED_UI_CASE_IDS}
    actual_pairs = {
        (str(case.get("target_root")), str(case.get("case_id")))
        for case in cases
        if isinstance(case, dict)
    }
    missing_pairs = sorted(expected_pairs - actual_pairs)
    if missing_pairs:
        findings.append(
            finding(
                "anythingllm_ui_e2e.required_cases",
                FindingSeverity.BLOCKER,
                f"AnythingLLM UI E2E missing required target/case pairs: {missing_pairs}",
                next_action="Run UI semantic E2E for every required L1 case on both frozen fixtures.",
            )
        )
    for case in cases:
        if isinstance(case, dict) and case.get("status") != ReleaseAdherenceStatus.PASSED.value:
            findings.append(
                finding(
                    f"anythingllm_ui_e2e.case[{case.get('case_id', 'unknown')}]",
                    FindingSeverity.BLOCKER,
                    json.dumps(
                        {
                            "case_name": case.get("case_name"),
                            "target_root": case.get("target_root"),
                            "semantic_status": case.get("semantic_status"),
                            "missing_required_markers": case.get("missing_required_markers"),
                            "rejected_markers_present": case.get("rejected_markers_present"),
                        },
                        ensure_ascii=True,
                        sort_keys=True,
                    ),
                    next_action="Repair the chat-visible answer renderer or routed skill output for this UI case.",
                )
            )
    return findings


def portability_findings(portability_report: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    probe = portability_report.get("candidate_model_probe") if isinstance(portability_report.get("candidate_model_probe"), dict) else {}
    if probe and probe.get("status") != "passed":
        findings.append(
            finding(
                "model_portability.candidate_model_probe",
                FindingSeverity.BLOCKER,
                f"Candidate model probe did not pass: {json.dumps(probe, ensure_ascii=True, sort_keys=True)}",
                next_action="Fix localhost model availability before trusting release adherence.",
            )
        )
    if portability_report.get("status") != ReleaseAdherenceStatus.PASSED.value:
        findings.append(
            finding(
                "model_portability",
                FindingSeverity.BLOCKER,
                f"Model portability status is {portability_report.get('status')}",
                next_action="Review classified portability failures and fix harness, route, prompt, or model-quality gaps.",
            )
        )
    for record in portability_report.get("classified_failures") or []:
        if not isinstance(record, dict):
            continue
        findings.append(
            {
                "source": f"model_portability.{record.get('source', 'failure')}",
                "severity": FindingSeverity.BLOCKER.value,
                "classification": str(record.get("classification") or ReleaseAdherenceFailureClass.UNKNOWN.value),
                "matched_terms": record.get("matched_terms") or [],
                "message": bounded_text(record.get("message") or ""),
                "details": {"source_record": record},
                "next_action": str(record.get("recommended_next_action") or "Fix the classified portability failure."),
            }
        )
    return findings


def accepted_profile_warning(profile: dict[str, Any]) -> bool:
    capabilities = profile.get("capabilities") if isinstance(profile.get("capabilities"), dict) else {}
    safe_apply = capabilities.get("safe_apply_readiness") if isinstance(capabilities.get("safe_apply_readiness"), dict) else {}
    required_ok = all(
        isinstance(capabilities.get(key), dict) and capabilities[key].get("status") == CapabilityStatus.PROVEN.value
        for key in PROVEN_CAPABILITY_KEYS
    )
    return required_ok and safe_apply.get("status") == CapabilityStatus.PARTIALLY_PROVEN.value


def profile_warning_justification(profile: dict[str, Any]) -> str:
    capabilities = profile.get("capabilities") if isinstance(profile.get("capabilities"), dict) else {}
    latency = capabilities.get("latency") if isinstance(capabilities.get("latency"), dict) else {}
    if latency.get("status") == CapabilityStatus.UNKNOWN.value:
        return "Latency is unknown; this warning is release-blocking for Phase 109."
    if accepted_profile_warning(profile):
        return "Profile warning is accepted: all required capabilities are proven and safe apply is intentionally partial because real repository mutation is not approved."
    return "Profile warning requires review; inspect capability details."


def profile_findings(profile: dict[str, Any]) -> list[dict[str, Any]]:
    status = profile.get("status")
    capabilities = profile.get("capabilities") if isinstance(profile.get("capabilities"), dict) else {}
    latency = capabilities.get("latency") if isinstance(capabilities.get("latency"), dict) else {}
    findings: list[dict[str, Any]] = []
    if status == ReleaseAdherenceStatus.FAILED.value:
        findings.append(
            finding(
                "model_capability_profile",
                FindingSeverity.BLOCKER,
                "Model capability profile failed.",
                next_action="Fix failed route, output, semantic, timeout, or safe-apply capability before release.",
                details={"profile_status": status, "capabilities": capabilities},
            )
        )
    elif latency.get("status") == CapabilityStatus.UNKNOWN.value:
        findings.append(
            finding(
                "model_capability_profile.latency",
                FindingSeverity.BLOCKER,
                "Model capability profile latency remains unknown.",
                next_action="Record suite duration metrics or justify latency before release.",
                details={"latency": latency},
            )
        )
    elif status == "warning":
        accepted = accepted_profile_warning(profile)
        findings.append(
            finding(
                "model_capability_profile.warning",
                FindingSeverity.WARNING if accepted else FindingSeverity.BLOCKER,
                profile_warning_justification(profile),
                next_action="Keep warning visible in founder review; no code repair is required when only real-apply policy remains partial."
                if accepted
                else "Fix or explicitly classify the partial/unknown capability before release.",
                details={"profile_status": status, "capabilities": capabilities},
            )
        )
    return findings


def ui_summary(ui_report: dict[str, Any]) -> dict[str, Any]:
    ui = ui_report.get("ui") if isinstance(ui_report.get("ui"), dict) else {}
    cases = ui.get("cases") if isinstance(ui.get("cases"), list) else []
    return {
        "status": ui_report.get("status"),
        "case_count": len(cases),
        "failed_case_count": sum(1 for item in cases if isinstance(item, dict) and item.get("status") != "passed"),
        "case_ids": sorted({str(item.get("case_id")) for item in cases if isinstance(item, dict)}),
        "target_roots": sorted({str(item.get("target_root")) for item in cases if isinstance(item, dict)}),
        "fixture_unchanged": ui_report.get("fixture_unchanged"),
        "report_path": ui_report.get("report_path"),
    }


def acceptance_summary(acceptance_report: dict[str, Any]) -> dict[str, Any]:
    health = acceptance_report.get("health") if isinstance(acceptance_report.get("health"), list) else []
    fixture_state = acceptance_report.get("fixture_state") if isinstance(acceptance_report.get("fixture_state"), dict) else {}
    fixture_git_status = {
        root: {
            "clean": item.get("git_status", {}).get("clean") if isinstance(item.get("git_status"), dict) else None,
            "line_count": item.get("git_status", {}).get("line_count") if isinstance(item.get("git_status"), dict) else None,
            "warning": "unchanged during run, not pristine" if isinstance(item.get("git_status"), dict) and item.get("git_status", {}).get("clean") is False else "",
        }
        for root, item in fixture_state.items()
        if isinstance(item, dict)
    }
    return {
        "status": acceptance_report.get("status"),
        "profile": acceptance_report.get("profile"),
        "report_path": acceptance_report.get("report_path"),
        "target_roots": acceptance_report.get("target_roots"),
        "model_ids": (
            acceptance_report.get("model_portability", {})
            .get("candidate_model_probe", {})
            .get("model_ids", [])
            if isinstance(acceptance_report.get("model_portability"), dict)
            else []
        ),
        "health_count": len(health),
        "health_names": [str(item.get("name")) for item in health if isinstance(item, dict)],
        "failed_health_count": sum(1 for item in health if isinstance(item, dict) and item.get("status") != "passed"),
        "suite_statuses": suite_statuses(acceptance_report),
        "json_output_count": len(acceptance_report.get("json_output") if isinstance(acceptance_report.get("json_output"), list) else []),
        "feedback_count": len(acceptance_report.get("feedback") if isinstance(acceptance_report.get("feedback"), list) else []),
        "fixture_state_recorded": bool(acceptance_report.get("fixture_state")),
        "fixture_git_status": fixture_git_status,
    }


def finding_counts(findings: list[dict[str, Any]]) -> dict[str, Any]:
    by_severity = {severity.value: 0 for severity in FindingSeverity}
    by_classification = {classification.value: 0 for classification in ReleaseAdherenceFailureClass}
    for item in findings:
        by_severity[str(item.get("severity"))] = by_severity.get(str(item.get("severity")), 0) + 1
        by_classification[str(item.get("classification"))] = by_classification.get(str(item.get("classification")), 0) + 1
    return {"by_severity": by_severity, "by_classification": by_classification}


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    artifacts = report.get("artifacts", {})
    acceptance = summary.get("acceptance", {}) if isinstance(summary.get("acceptance"), dict) else {}
    ui = summary.get("ui", {}) if isinstance(summary.get("ui"), dict) else {}
    profile = summary.get("model_capability_profile", {}) if isinstance(summary.get("model_capability_profile"), dict) else {}
    portability = summary.get("model_portability", {}) if isinstance(summary.get("model_portability"), dict) else {}
    latency = summary.get("latency", {}) if isinstance(summary.get("latency"), dict) else {}
    lines = [
        "# Release Adherence Report",
        "",
        f"- Status: {report.get('status')}",
        f"- Readiness: {report.get('readiness_status')}",
        f"- Candidate: {report.get('candidate', {}).get('candidate_id')}",
        f"- Model IDs: {', '.join(acceptance.get('model_ids') or [])}",
        f"- Blockers: {summary.get('finding_counts', {}).get('by_severity', {}).get('blocker', 0)}",
        f"- Warnings: {summary.get('finding_counts', {}).get('by_severity', {}).get('warning', 0)}",
        f"- Latency measured: {latency.get('latency_measured')}",
        f"- UI semantic cases: {ui.get('case_count')} total, {ui.get('failed_case_count')} failed",
        "",
        "## Evidence Summary",
        "",
        f"- Health ports: {acceptance.get('health_count')} checked, {acceptance.get('failed_health_count')} failed",
        f"- Target roots: {', '.join(acceptance.get('target_roots') or [])}",
        f"- Suite statuses: {json.dumps(acceptance.get('suite_statuses') or {}, ensure_ascii=True, sort_keys=True)}",
        f"- JSON output cases: {acceptance.get('json_output_count')}",
        f"- Feedback cases: {acceptance.get('feedback_count')}",
        f"- UI case IDs: {', '.join(ui.get('case_ids') or [])}",
        f"- UI fixture unchanged: {ui.get('fixture_unchanged')}",
        f"- Model portability status: {portability.get('status')}",
        f"- Model capability profile status: {profile.get('status')}",
        f"- Capability statuses: {json.dumps(profile.get('capabilities') or {}, ensure_ascii=True, sort_keys=True)}",
        f"- Task policy: {json.dumps(profile.get('task_policy') or {}, ensure_ascii=True, sort_keys=True)}",
        "",
        "## Fixture Evidence",
        "",
        f"- Fixture state recorded: {acceptance.get('fixture_state_recorded')}",
        f"- Fixture git status: {json.dumps(acceptance.get('fixture_git_status') or {}, ensure_ascii=True, sort_keys=True)}",
        "",
        "## Latency Summary",
        "",
        f"- Suite duration samples: {latency.get('suite_duration_sample_count')}",
        f"- Max suite duration seconds: {latency.get('max_suite_duration_seconds')}",
        f"- Total suite duration seconds: {latency.get('total_suite_duration_seconds')}",
        "",
        "## Artifacts",
        "",
    ]
    for key, value in artifacts.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Step Durations", ""])
    for key, value in (latency.get("step_duration_seconds") or {}).items():
        lines.append(f"- {key}: {value:.3f}s")
    lines.extend(["", "## Findings", ""])
    for item in report.get("findings", []):
        lines.append(
            f"- {item.get('severity')} / {item.get('classification')} / {item.get('source')}: {item.get('message')}"
        )
    if not report.get("findings"):
        lines.append("- No findings.")
    lines.append("")
    return "\n".join(lines)


def run_release_adherence(
    config: ReleaseAdherenceConfig,
    *,
    acceptance_runner: AcceptanceRunner = run_v1_acceptance,
    ui_runner: UiRunner = run_anythingllm_ui_e2e,
    portability_runner: PortabilityRunner = run_model_portability,
    profile_runner: ProfileRunner = run_model_capability_profile,
) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    report_path = config.output_path or default_report_path(config_root)
    markdown_path = config.markdown_output_path or default_markdown_path(report_path)
    acceptance_path = sibling_path(report_path, "v1-acceptance")
    ui_path = sibling_path(report_path, "anythingllm-ui-e2e")
    portability_path = sibling_path(report_path, "model-portability")
    profile_path = sibling_path(report_path, "model-capability-profile")
    profile_markdown_path = sibling_path(report_path, "model-capability-profile", ".md")

    findings: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    acceptance_report, step, step_finding = timed_step(
        "v1_acceptance",
        lambda: acceptance_runner(
            V1AcceptanceConfig(
                config_root=config_root,
                candidate_model_base_url=config.candidate_model_base_url,
                workflow_router_gateway_base_url=config.workflow_router_gateway_base_url,
                controller_base_url=config.controller_base_url,
                anythingllm_api_base_url=config.anythingllm_api_base_url,
                workspace=config.workspace,
                api_key_env=config.api_key_env,
                target_roots=config.target_roots,
                timeout_seconds=config.timeout_seconds,
                command_timeout_seconds=config.command_timeout_seconds,
                output_path=acceptance_path,
                python_executable=config.python_executable,
                profile=ReleaseGateProfile.V1_1_RELEASE_CANDIDATE,
            )
        ),
    )
    steps.append(step)
    if step_finding:
        findings.append(step_finding)
    findings.extend(acceptance_findings(acceptance_report, expected_target_roots=config.target_roots))

    ui_report, step, step_finding = timed_step(
        "anythingllm_ui_e2e",
        lambda: ui_runner(
            AnythingLLMUiE2EConfig(
                config_root=config_root,
                anythingllm_api_base_url=config.anythingllm_api_base_url,
                workspace=config.workspace,
                api_key_env=config.api_key_env,
                target_roots=config.target_roots,
                output_path=ui_path,
                ui_dist_root=config.ui_dist_root,
                app_asar_path=config.app_asar_path,
                extract_root=config.extract_root,
                refresh_extract=config.refresh_extract,
                npx_command=config.npx_command,
                browser_channel=config.browser_channel,
                timeout_seconds=min(config.timeout_seconds, 420),
            )
        ),
    )
    steps.append(step)
    if step_finding:
        findings.append(step_finding)
    findings.extend(ui_findings(ui_report, expected_target_roots=config.target_roots))

    acceptance_report_path = Path(str(acceptance_report.get("report_path") or acceptance_path))
    portability_report, step, step_finding = timed_step(
        "model_portability",
        lambda: portability_runner(
            ModelPortabilityConfig(
                config_root=config_root,
                candidate_id=config.candidate_id,
                candidate_description=config.candidate_description,
                candidate_model_base_url=config.candidate_model_base_url,
                workflow_router_gateway_base_url=config.workflow_router_gateway_base_url,
                controller_base_url=config.controller_base_url,
                anythingllm_api_base_url=config.anythingllm_api_base_url,
                workspace=config.workspace,
                api_key_env=config.api_key_env,
                target_roots=config.target_roots,
                timeout_seconds=config.timeout_seconds,
                command_timeout_seconds=config.command_timeout_seconds,
                output_path=portability_path,
                acceptance_report_path=acceptance_report_path,
                python_executable=config.python_executable,
                skip_live_acceptance=True,
                skip_model_probe=False,
            )
        ),
    )
    steps.append(step)
    if step_finding:
        findings.append(step_finding)
    findings.extend(portability_findings(portability_report))

    profile, step, step_finding = timed_step(
        "model_capability_profile",
        lambda: profile_runner(
            ModelCapabilityProfileConfig(
                config_root=config_root,
                portability_report_path=Path(str(portability_report.get("report_path") or portability_path)),
                output_path=profile_path,
                markdown_output_path=profile_markdown_path,
            )
        ),
    )
    steps.append(step)
    if step_finding:
        findings.append(step_finding)
    findings.extend(profile_findings(profile))

    latency = latency_summary(acceptance_report, steps)
    if not latency["latency_measured"]:
        findings.append(
            finding(
                "release_adherence.latency",
                FindingSeverity.BLOCKER,
                "Release-adherence gate did not capture both suite and step duration metrics.",
                next_action="Record suite duration_seconds and step timing before release.",
                details=latency,
            )
        )

    blocker_count = sum(1 for item in findings if item.get("severity") == FindingSeverity.BLOCKER.value)
    status = ReleaseAdherenceStatus.PASSED.value if blocker_count == 0 else ReleaseAdherenceStatus.FAILED.value
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "release_adherence_report",
        "status": status,
        "readiness_status": "releasable" if status == ReleaseAdherenceStatus.PASSED.value else "blocked",
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "candidate": {
            "candidate_id": config.candidate_id,
            "candidate_description": config.candidate_description,
            "candidate_model_base_url": config.candidate_model_base_url,
            "workflow_router_gateway_base_url": config.workflow_router_gateway_base_url,
            "controller_base_url": config.controller_base_url,
            "anythingllm_api_base_url": config.anythingllm_api_base_url,
            "workspace": config.workspace,
            "target_roots": list(config.target_roots),
        },
        "steps": steps,
        "artifacts": {
            "v1_acceptance": acceptance_report.get("report_path") or str(acceptance_path.resolve()),
            "anythingllm_ui_e2e": ui_report.get("report_path") or str(ui_path.resolve()),
            "model_portability": portability_report.get("report_path") or str(portability_path.resolve()),
            "model_capability_profile": profile.get("report_path") or str(profile_path.resolve()),
            "model_capability_profile_markdown": profile.get("markdown_report_path") or str(profile_markdown_path.resolve()),
            "markdown_report": str(markdown_path.resolve()),
        },
        "summary": {
            "acceptance": acceptance_summary(acceptance_report),
            "ui": ui_summary(ui_report),
            "model_portability": {
                "status": portability_report.get("status"),
                "classification_summary": portability_report.get("classification_summary", {}),
                "failure_count": len(portability_report.get("classified_failures") or []),
                "candidate_model_probe": portability_report.get("candidate_model_probe", {}),
            },
            "model_capability_profile": {
                "status": profile.get("status"),
                "capabilities": {
                    key: value.get("status")
                    for key, value in (profile.get("capabilities") or {}).items()
                    if isinstance(value, dict)
                },
                "task_policy": {
                    key: value.get("status")
                    for key, value in (profile.get("task_policy") or {}).items()
                    if isinstance(value, dict)
                },
                "warning_justification": profile_warning_justification(profile)
                if profile.get("status") == "warning"
                else "",
            },
            "latency": latency,
            "finding_counts": finding_counts(findings),
        },
        "findings": findings,
    }
    report["report_path"] = str(report_path.resolve())
    report["markdown_report_path"] = str(markdown_path.resolve())
    write_json(report_path, report)
    write_text(markdown_path, render_markdown(report))
    write_json(report_path, report)
    return report
