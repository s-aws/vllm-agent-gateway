"""Phase 233 contextless handoff dry-run gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "contextless_handoff_dry_run_policy"
EXPECTED_REPORT_KIND = "contextless_handoff_dry_run_report"
EXPECTED_BLIND_AUDIT_KIND = "contextless_handoff_dry_run_blind_audit"
EXPECTED_PHASE = 233
EXPECTED_BACKLOG_ID = "P0-M14-233"
EXPECTED_MILESTONE_ID = "M14"
DEFAULT_POLICY_PATH = Path("runtime") / "contextless_handoff_dry_run_policy.json"
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase233" / "phase233-contextless-handoff-dry-run-report.json"


class ContextlessHandoffDryRunStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class ContextlessHandoffDryRunDecision(str, Enum):
    PASSED = "handoff_dry_run_passed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ContextlessHandoffDryRunConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validation_error(error_id: str, message: str, *, severity: str = "high", source: str = "policy") -> dict[str, str]:
    return {"id": error_id, "severity": severity, "source": source, "message": message}


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 233"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if policy.get("milestone_id") != EXPECTED_MILESTONE_ID:
        errors.append(validation_error("policy.milestone_id", "milestone_id must be M14"))
    if policy.get("required_decision") != ContextlessHandoffDryRunDecision.PASSED.value:
        errors.append(validation_error("policy.required_decision", "required_decision must be handoff_dry_run_passed"))
    if not isinstance(policy.get("required_reports"), dict):
        errors.append(validation_error("policy.required_reports", "required_reports must be an object"))
    if not isinstance(policy.get("required_cases"), dict):
        errors.append(validation_error("policy.required_cases", "required_cases must be an object"))
    required_surfaces = set(string_list(policy.get("required_surfaces")))
    expected_surfaces = {
        "handoff.phase232",
        "runtime_recovery.phase231",
        "release_channels.stable",
        "security_policy.release",
        "doctor.first_time_user",
        "onboarding.static",
        "onboarding.anythingllm",
        "feedback.workflow_feedback",
        "small_repo.gateway",
        "small_repo.anythingllm",
        "small_skill_admission.gate",
        "large_context.gateway",
        "large_context.anythingllm",
        "blind_audit.contextless",
    }
    if required_surfaces != expected_surfaces:
        errors.append(validation_error("policy.required_surfaces", "required_surfaces must match Phase 233 proof surfaces"))
    anythingllm = dict_value(policy.get("required_anythingllm"))
    if anythingllm.get("workflow_router_base_url") != "http://127.0.0.1:8500/v1":
        errors.append(validation_error("policy.required_anythingllm.workflow_router_base_url", "AnythingLLM must target 8500/v1"))
    if anythingllm.get("api_base_url") != "http://127.0.0.1:3001":
        errors.append(validation_error("policy.required_anythingllm.api_base_url", "AnythingLLM API base URL must be 3001"))
    if anythingllm.get("workspace") != "my-workspace":
        errors.append(validation_error("policy.required_anythingllm.workspace", "workspace must be my-workspace"))
    if set(string_list(policy.get("required_target_roots"))) != {
        "/mnt/c/coinbase_testing_repo_frozen_tmp",
        "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    }:
        errors.append(validation_error("policy.required_target_roots", "both frozen Coinbase fixtures are required"))
    if policy.get("acceptance_marker") != "PHASE233 CONTEXTLESS HANDOFF DRY RUN PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 233"))
    return errors


def load_report(config_root: Path, path_value: object) -> tuple[Path | None, dict[str, Any], dict[str, str] | None]:
    if not isinstance(path_value, str) or not path_value.strip():
        return None, {}, validation_error("reports.path", "report path must be a non-empty string", source="reports")
    path = resolve_path(config_root, path_value)
    if not path.is_file():
        return path, {}, validation_error(f"reports.{path_value}.missing", f"required report missing: {path_value}", source=path_value)
    try:
        return path, read_json_object(path), None
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return path, {}, validation_error(
            f"reports.{path_value}.malformed",
            f"required report is malformed: {type(exc).__name__}: {exc}",
            source=path_value,
        )


def load_sources(config_root: Path, policy: dict[str, Any]) -> tuple[dict[str, tuple[Path | None, dict[str, Any]]], list[dict[str, str]]]:
    reports = dict_value(policy.get("required_reports"))
    sources: dict[str, tuple[Path | None, dict[str, Any]]] = {}
    errors: list[dict[str, str]] = []
    for report_id, path_value in reports.items():
        path, report, error = load_report(config_root, path_value)
        sources[str(report_id)] = (path, report)
        if error:
            errors.append(error)
    blind_path, blind_report, blind_error = load_report(config_root, policy.get("required_blind_audit"))
    sources["blind_audit"] = (blind_path, blind_report)
    if blind_error:
        errors.append(blind_error)
    return sources, errors


def source_artifact(name: str, path: Path | None, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "path": str(path.resolve()) if path else None,
        "sha256": artifact_hash(path),
        "kind": report.get("kind"),
        "status": report.get("status"),
        "decision": report.get("decision"),
        "summary": report.get("summary"),
    }


def covered_small_repo_surfaces(report: dict[str, Any], case_ids: list[str]) -> set[str]:
    surfaces: set[str] = set()
    for client in ("gateway", "anythingllm"):
        passed_case_ids = {
            str(item.get("case_id"))
            for item in object_list(report.get("cases"))
            if item.get("status") == "passed" and item.get("client") == client and item.get("source_unchanged") is True
        }
        if set(case_ids).issubset(passed_case_ids):
            surfaces.add(f"small_repo.{client}")
    return surfaces


def covered_large_context_surfaces(report: dict[str, Any], case_id: str) -> set[str]:
    surfaces: set[str] = set()
    for item in object_list(report.get("responses")):
        if item.get("status") == "passed" and item.get("case_id") == case_id and item.get("surface") in {"gateway", "anythingllm"}:
            surfaces.add(f"large_context.{item['surface']}")
    return surfaces


def validate_sources(policy: dict[str, Any], sources: dict[str, tuple[Path | None, dict[str, Any]]]) -> tuple[set[str], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    covered: set[str] = set()
    cases = dict_value(policy.get("required_cases"))
    anythingllm = dict_value(policy.get("required_anythingllm"))

    phase232 = sources.get("phase232_handoff", (None, {}))[1]
    if phase232.get("kind") != "onboarding_release_handoff_refresh_report" or phase232.get("status") != "passed":
        errors.append(validation_error("phase232.status", "Phase 232 handoff report must pass", source="phase232_handoff"))
    if phase232.get("decision") == "handoff_ready":
        covered.add("handoff.phase232")

    runtime_recovery = sources.get("runtime_recovery", (None, {}))[1]
    if runtime_recovery.get("kind") != "runtime_recovery_reliability_rebaseline_report" or runtime_recovery.get("status") != "passed":
        errors.append(validation_error("runtime_recovery.status", "runtime recovery reliability report must pass", source="runtime_recovery"))
    if runtime_recovery.get("decision") == "ready_after_recovery" and dict_value(runtime_recovery.get("summary")).get("missing_required_surface_count") == 0:
        covered.add("runtime_recovery.phase231")

    release_channels = sources.get("release_channels", (None, {}))[1]
    if release_channels.get("kind") != "release_channel_validation_report" or release_channels.get("status") != "passed":
        errors.append(validation_error("release_channels.status", "release channel validation must pass", source="release_channels"))
    if dict_value(release_channels.get("summary")).get("failed_check_ids") == []:
        covered.add("release_channels.stable")

    security_policy = sources.get("security_policy", (None, {}))[1]
    if security_policy.get("kind") != "security_policy_validation_report" or security_policy.get("status") != "passed":
        errors.append(validation_error("security_policy.status", "security policy validation must pass", source="security_policy"))
    if dict_value(security_policy.get("summary")).get("failed_check_ids") == []:
        covered.add("security_policy.release")

    doctor = sources.get("first_time_user_doctor", (None, {}))[1]
    if doctor.get("kind") != "first_time_user_doctor_report" or doctor.get("status") != "passed":
        errors.append(validation_error("doctor.status", "first-time user doctor must pass", source="first_time_user_doctor"))
    if dict_value(doctor.get("summary")).get("failed_check_ids") == []:
        covered.add("doctor.first_time_user")

    external = sources.get("external_tester_dry_run", (None, {}))[1]
    if external.get("kind") != "external_tester_dry_run_report" or external.get("status") != "passed":
        errors.append(validation_error("external_tester.status", "external tester dry run must pass", source="external_tester_dry_run"))
    environment = dict_value(external.get("environment"))
    if environment.get("workflow_router_gateway_base_url") != anythingllm.get("workflow_router_base_url"):
        errors.append(validation_error("external_tester.workflow_router_gateway_base_url", "dry run must use workflow-router gateway 8500/v1", source="external_tester_dry_run"))
    if environment.get("anythingllm_api_base_url") != anythingllm.get("api_base_url"):
        errors.append(validation_error("external_tester.anythingllm_api_base_url", "dry run must use AnythingLLM API 3001", source="external_tester_dry_run"))
    if environment.get("workspace") != anythingllm.get("workspace"):
        errors.append(validation_error("external_tester.workspace", "dry run must use my-workspace", source="external_tester_dry_run"))
    summary = dict_value(external.get("summary"))
    if summary.get("live_runtime") is not True:
        errors.append(validation_error("external_tester.live_runtime", "dry run must be live", source="external_tester_dry_run"))
    if summary.get("onboarding_live_status") == "passed" and summary.get("onboarding_live_case_count") == 1:
        covered.add("onboarding.anythingllm")
    if summary.get("feedback_count") == 1 and str(dict_value(external.get("feedback_capture")).get("feedback_run_id", "")).startswith("workflow-feedback-"):
        covered.add("feedback.workflow_feedback")
    prompt_record = dict_value(external.get("manual_prompt")) or dict_value(external.get("onboarding_prompt"))
    if prompt_record.get("case_id") != cases.get("onboarding"):
        errors.append(validation_error("external_tester.onboarding_case", "dry run must exercise ONB-001", source="external_tester_dry_run"))

    onboarding_static = sources.get("external_onboarding_static", (None, {}))[1]
    if onboarding_static.get("kind") != "external_tester_onboarding_validation_report" or onboarding_static.get("status") != "passed":
        errors.append(validation_error("onboarding_static.status", "external onboarding static validation must pass", source="external_onboarding_static"))
    if dict_value(onboarding_static.get("summary")).get("case_count", 0) >= 1:
        covered.add("onboarding.static")

    onboarding_live = sources.get("external_onboarding_live", (None, {}))[1]
    if onboarding_live.get("kind") != "external_tester_onboarding_validation_report" or onboarding_live.get("status") != "passed":
        errors.append(validation_error("onboarding_live.status", "external onboarding live validation must pass", source="external_onboarding_live"))
    onboarding_live_summary = dict_value(onboarding_live.get("summary"))
    if onboarding_live_summary.get("live_status") == "passed" and onboarding_live_summary.get("live_case_count") == 1:
        covered.add("onboarding.anythingllm")
    if onboarding_live_summary.get("feedback_count") == 1:
        covered.add("feedback.workflow_feedback")

    small_repo = sources.get("small_repo_live", (None, {}))[1]
    if small_repo.get("kind") != "multi_repo_fixture_live_report" or small_repo.get("status") != "passed":
        errors.append(validation_error("small_repo.status", "small-repo live report must pass", source="small_repo_live"))
    covered.update(covered_small_repo_surfaces(small_repo, string_list(cases.get("small_repo"))))

    small_skill_gate = sources.get("small_skill_admission_gate", (None, {}))[1]
    if small_skill_gate.get("kind") != "small_skill_admission_pilot_report" or small_skill_gate.get("status") != "passed":
        errors.append(validation_error("small_skill_gate.status", "small skill admission gate must pass", source="small_skill_admission_gate"))
    if dict_value(small_skill_gate.get("summary")).get("phase231_ready") is True:
        covered.add("small_skill_admission.gate")

    large_context = sources.get("large_context_live", (None, {}))[1]
    if large_context.get("kind") != "large_context_usability_live_closeout_report" or large_context.get("status") != "passed":
        errors.append(validation_error("large_context.status", "large-context live report must pass", source="large_context_live"))
    if large_context.get("live") is not True:
        errors.append(validation_error("large_context.live", "large-context proof must be live", source="large_context_live"))
    covered.update(covered_large_context_surfaces(large_context, str(cases.get("large_context"))))

    blind = sources.get("blind_audit", (None, {}))[1]
    if blind.get("kind") != EXPECTED_BLIND_AUDIT_KIND or blind.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("blind_audit.kind", "blind audit must be a Phase 233 contextless audit", source="blind_audit"))
    if blind.get("status") == "passed" and dict_value(blind.get("summary")).get("contextless") is True:
        covered.add("blind_audit.contextless")
    return covered, errors


def build_contextless_handoff_dry_run_report(
    *,
    config_root: Path,
    policy: dict[str, Any],
    policy_path: Path | None = None,
    sources: dict[str, tuple[Path | None, dict[str, Any]]] | None = None,
    source_errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    errors = validate_policy(policy)
    if sources is None or source_errors is None:
        sources, source_errors = load_sources(config_root, policy)
    errors.extend(source_errors)
    covered, source_validation_errors = validate_sources(policy, sources)
    errors.extend(source_validation_errors)
    required_surfaces = set(string_list(policy.get("required_surfaces")))
    missing_surfaces = sorted(required_surfaces - covered)
    if missing_surfaces:
        errors.append(validation_error("required_surfaces.missing", "missing required surfaces: " + ", ".join(missing_surfaces), source="surfaces"))
    status = ContextlessHandoffDryRunStatus.FAILED.value if errors else ContextlessHandoffDryRunStatus.PASSED.value
    decision = (
        ContextlessHandoffDryRunDecision.PASSED.value
        if status == ContextlessHandoffDryRunStatus.PASSED.value
        else ContextlessHandoffDryRunDecision.BLOCKED.value
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_id": EXPECTED_MILESTONE_ID,
        "generated_at": utc_timestamp(),
        "status": status,
        "decision": decision,
        "policy_path": str(policy_path.resolve()) if policy_path else None,
        "policy_sha256": artifact_hash(policy_path),
        "source_artifacts": [source_artifact(name, path, report) for name, (path, report) in sorted(sources.items())],
        "required_surfaces": sorted(required_surfaces),
        "covered_surfaces": sorted(covered),
        "missing_required_surfaces": missing_surfaces,
        "validation_errors": errors,
        "summary": {
            "decision": decision,
            "source_report_count": len(sources),
            "required_surface_count": len(required_surfaces),
            "covered_surface_count": len(covered & required_surfaces),
            "missing_required_surface_count": len(missing_surfaces),
            "validation_error_count": len(errors),
            "handoff_ready": not errors,
            "next_action": "request next milestone-aligned roadmap batch" if not errors else "repair handoff dry-run proof",
        },
    }


def stable_report(value: dict[str, Any]) -> dict[str, Any]:
    stable = json.loads(json.dumps(value))
    stable.pop("generated_at", None)
    stable.pop("report_path", None)
    return stable


def validate_contextless_handoff_dry_run_report(
    report: dict[str, Any],
    *,
    config_root: Path,
    policy: dict[str, Any],
    policy_path: Path | None = None,
    sources: dict[str, tuple[Path | None, dict[str, Any]]] | None = None,
    source_errors: list[dict[str, str]] | None = None,
) -> list[str]:
    expected = build_contextless_handoff_dry_run_report(
        config_root=config_root,
        policy=policy,
        policy_path=policy_path,
        sources=sources,
        source_errors=source_errors,
    )
    if stable_report(report) != stable_report(expected):
        return ["report must match rebuilt contextless handoff dry-run report"]
    return []


def run_contextless_handoff_dry_run(config: ContextlessHandoffDryRunConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    policy = read_json_object(policy_path)
    sources, source_errors = load_sources(config_root, policy)
    report = build_contextless_handoff_dry_run_report(
        config_root=config_root,
        policy=policy,
        policy_path=policy_path,
        sources=sources,
        source_errors=source_errors,
    )
    validation_errors = validate_contextless_handoff_dry_run_report(
        report,
        config_root=config_root,
        policy=policy,
        policy_path=policy_path,
        sources=sources,
        source_errors=source_errors,
    )
    if validation_errors:
        report["status"] = ContextlessHandoffDryRunStatus.FAILED.value
        report["decision"] = ContextlessHandoffDryRunDecision.BLOCKED.value
        report["validation_errors"].extend(validation_error("report.rebuild", item, source="report") for item in validation_errors)
        report["summary"]["decision"] = report["decision"]
        report["summary"]["validation_error_count"] = len(report["validation_errors"])
        report["summary"]["handoff_ready"] = False
        report["summary"]["next_action"] = "repair handoff dry-run proof"
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
